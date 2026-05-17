"""Archive des PDFs générés et de leurs sources HTML.

Backend local : SQLite (history.db) — thread-safe, transactionnel.
Backend serverless : MongoDB ou SQLite dans /tmp.
Blob Storage optionnel : Vercel Blob via BLOB_READ_WRITE_TOKEN.
"""

import json
import os
import re
import sqlite3
import threading
import unicodedata
import urllib.parse
import urllib.request as _urllib_req
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable

OWNER = "Hariss"

# ---- MongoDB & Vercel Blob Storage ------------------------------------------
_BLOB_TOKEN: str | None = os.environ.get("BLOB_READ_WRITE_TOKEN")
_MONGO_URI: str | None = os.environ.get("MONGODB_URI")

_mongo_client = None
_history_collection = None
if _MONGO_URI:
    try:
        import pymongo
        _mongo_client = pymongo.MongoClient(_MONGO_URI, serverSelectionTimeoutMS=5000)
        _history_collection = _mongo_client.get_database("cv_generator").get_collection("history")
    except Exception as e:
        print("Erreur d'initialisation MongoDB :", e)
        _history_collection = None

# ---- Détection de l'environnement serverless --------------------------------
_IS_SERVERLESS: bool = bool(
    os.environ.get("VERCEL")
    or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    or os.environ.get("PDF_ENGINE", "").lower() == "weasyprint"
    or _MONGO_URI
)

# ---- Répertoire d'archive ---------------------------------------------------
ARCHIVE_DIR: Path = (
    Path("/tmp") / "CV-Archive"
    if _IS_SERVERLESS
    else Path.home() / "Documents" / "CV-Archive"
)
HISTORY_FILE: Path = ARCHIVE_DIR / "history.json"
_DB_PATH: Path = ARCHIVE_DIR / "history.db"

DOC_TYPES: tuple[str, ...] = ("CV", "Lettre", "Autre")
_MAX_UNIQUE_TRIES: int = 100

# ---- SQLite init (mode local) -----------------------------------------------
_init_lock = threading.Lock()
_db_initialized = False

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS documents (
    id           TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL,
    doc_type     TEXT DEFAULT 'CV',
    company      TEXT DEFAULT '',
    role         TEXT DEFAULT '',
    notes        TEXT DEFAULT '',
    job_desc     TEXT DEFAULT '',
    filename     TEXT DEFAULT '',
    pdf_path     TEXT DEFAULT '',
    html_path    TEXT DEFAULT '',
    pdf_blob_url TEXT DEFAULT '',
    html_blob_url TEXT DEFAULT ''
)
"""


def _get_db() -> sqlite3.Connection:
    """Ouvre une connexion SQLite en mode WAL (lecture concurrente sans lock)."""
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _sqlite_init() -> None:
    """Crée la table si absente, migre history.json si présent."""
    with _get_db() as conn:
        conn.execute(_CREATE_TABLE)
        conn.commit()
    _migrate_from_json()


def _migrate_from_json() -> None:
    """Migration one-shot : history.json → history.db."""
    if not HISTORY_FILE.exists():
        return
    try:
        entries = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if entries:
            with _get_db() as conn:
                for e in entries:
                    conn.execute(
                        "INSERT OR IGNORE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            e.get("id", ""),
                            e.get("created_at", ""),
                            e.get("doc_type", "CV"),
                            e.get("company", ""),
                            e.get("role", ""),
                            e.get("notes", ""),
                            e.get("job_desc", ""),
                            e.get("filename", ""),
                            e.get("pdf_path", ""),
                            e.get("html_path", ""),
                            e.get("pdf_blob_url", ""),
                            e.get("html_blob_url", ""),
                        ),
                    )
                conn.commit()
        HISTORY_FILE.rename(HISTORY_FILE.with_suffix(".json.migrated"))
        print(f"Migré {len(entries)} entrées de history.json → history.db")
    except Exception as e:
        print(f"Erreur migration JSON→SQLite : {e}")


def ensure_archive_dir() -> Path:
    global _db_initialized
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    if not _IS_SERVERLESS and not _db_initialized:
        with _init_lock:
            if not _db_initialized:
                _sqlite_init()
                _db_initialized = True
    return ARCHIVE_DIR


# ---- Utilitaires de nommage -------------------------------------------------

def _slug(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^\w\s-]", "", normalized).strip()
    return re.sub(r"[\s_-]+", "", cleaned)


def _safe_filename(name: str) -> str:
    """Sanitise un nom de fichier et prévient la traversée de répertoire."""
    name = Path(name).name  # basename seulement
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    if re.match(r'^(CON|PRN|AUX|NUL|COM\d|LPT\d)(\..*)?$', name, re.I):
        name = f"_{name}"
    # Empêche les chemins absolus qui auraient survécu
    name = name.lstrip("/\\.")
    return name or "document"


def make_filename(
    doc_type: str,
    company: str = "",
    role: str = "",
    when: datetime | None = None,
    ext: str = "pdf",
) -> str:
    when = when or datetime.now()
    parts = [doc_type or "Document", OWNER]
    company_slug = _slug(company)
    role_slug = _slug(role)
    if company_slug:
        parts.append(company_slug)
    elif role_slug:
        parts.append(role_slug)
    parts.append(when.strftime("%Y-%m-%d"))
    base = "_".join(p for p in parts if p)
    return f"{base}.{ext}"


def _unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    for n in range(2, _MAX_UNIQUE_TRIES + 2):
        candidate = directory / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
    return directory / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"


# ---- Backend local SQLite ---------------------------------------------------

def _local_save(entry: dict) -> None:
    with _get_db() as conn:
        conn.execute(
            "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                entry["id"], entry["created_at"], entry.get("doc_type", "CV"),
                entry.get("company", ""), entry.get("role", ""),
                entry.get("notes", ""), entry.get("job_desc", ""),
                entry.get("filename", ""), entry.get("pdf_path", ""),
                entry.get("html_path", ""), entry.get("pdf_blob_url", ""),
                entry.get("html_blob_url", ""),
            ),
        )
        conn.commit()


def _local_read_all() -> list[dict]:
    try:
        with _get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM documents ORDER BY created_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"Erreur lecture SQLite : {e}")
        return []


def _local_get(doc_id: str) -> dict | None:
    try:
        with _get_db() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id=?", (doc_id,)
            ).fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def _local_update_blobs(doc_id: str, pdf_url: str, html_url: str) -> None:
    try:
        with _get_db() as conn:
            conn.execute(
                "UPDATE documents SET pdf_blob_url=?, html_blob_url=? WHERE id=?",
                (pdf_url, html_url, doc_id),
            )
            conn.commit()
    except Exception as e:
        print(f"Erreur update SQLite : {e}")


def _local_delete(doc_id: str) -> dict | None:
    """Supprime et retourne l'entrée, ou None si absente."""
    try:
        with _get_db() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id=?", (doc_id,)
            ).fetchone()
            if not row:
                return None
            conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
            conn.commit()
            return dict(row)
    except Exception as e:
        print(f"Erreur delete SQLite : {e}")
        return None


# ---- Lecture / écriture de l'historique (routage MongoDB / SQLite) ----------

def _read_history() -> list[dict]:
    if _history_collection is not None:
        try:
            return list(_history_collection.find({}, {"_id": 0}).sort("created_at", -1))
        except Exception as e:
            print("Erreur lecture MongoDB :", e)
            return []
    ensure_archive_dir()
    return _local_read_all()


# ---- API publique -----------------------------------------------------------

def save_document(
    html: str,
    pdf_bytes: bytes,
    doc_type: str = "CV",
    company: str = "",
    role: str = "",
    notes: str = "",
    custom_filename: str = "",
    job_desc: str = "",
) -> dict:
    ensure_archive_dir()
    when = datetime.now()
    if doc_type not in DOC_TYPES:
        doc_type = "Autre"

    if custom_filename:
        sanitized = _safe_filename(custom_filename)
        pdf_filename = sanitized if sanitized.lower().endswith(".pdf") else f"{sanitized}.pdf"
    else:
        pdf_filename = make_filename(doc_type, company, role, when, ext="pdf")

    pdf_path = _unique_path(ARCHIVE_DIR, pdf_filename)
    html_path = pdf_path.with_suffix(".html")

    pdf_path.write_bytes(pdf_bytes)
    html_path.write_text(html, encoding="utf-8")

    entry: dict = {
        "id": str(uuid.uuid4()),
        "created_at": when.isoformat(timespec="seconds"),
        "doc_type": doc_type,
        "company": company,
        "role": role,
        "notes": notes,
        "job_desc": job_desc,
        "filename": pdf_path.name,
        "pdf_path": str(pdf_path),
        "html_path": str(html_path),
        "pdf_blob_url": "",
        "html_blob_url": "",
    }

    if _history_collection is not None:
        try:
            _history_collection.insert_one(entry.copy())
            return entry
        except Exception as e:
            print("Erreur insertion MongoDB :", e)
    else:
        _local_save(entry)

    return entry


def update_document_blob_urls(doc_id: str, pdf_blob_url: str, html_blob_url: str) -> None:
    if _history_collection is not None:
        try:
            _history_collection.update_one(
                {"id": doc_id},
                {"$set": {"pdf_blob_url": pdf_blob_url, "html_blob_url": html_blob_url}},
            )
            return
        except Exception as e:
            print("Erreur update MongoDB :", e)
    else:
        _local_update_blobs(doc_id, pdf_blob_url, html_blob_url)


def list_documents(limit: int | None = None) -> list[dict]:
    history = _read_history()
    return history[:limit] if limit else history


def get_document(doc_id: str) -> dict | None:
    if _history_collection is not None:
        try:
            found = _history_collection.find_one({"id": doc_id}, {"_id": 0})
            return found or None
        except Exception:
            return None
    ensure_archive_dir()
    return _local_get(doc_id)


def delete_document(doc_id: str) -> bool:
    if _history_collection is not None:
        try:
            found = _history_collection.find_one({"id": doc_id})
            if not found:
                return False
            if _BLOB_TOKEN:
                for key in ("pdf_blob_url", "html_blob_url"):
                    url = found.get(key, "")
                    if url:
                        try:
                            _delete_blob(url)
                        except Exception:
                            pass
            _history_collection.delete_one({"id": doc_id})
            return True
        except Exception as e:
            print("Erreur delete MongoDB :", e)
            return False

    ensure_archive_dir()
    found = _local_delete(doc_id)
    if not found:
        return False

    for key in ("pdf_path", "html_path"):
        path = Path(found.get(key, ""))
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass

    if _BLOB_TOKEN:
        for key in ("pdf_blob_url", "html_blob_url"):
            url = found.get(key, "")
            if url:
                try:
                    _delete_blob(url)
                except Exception:
                    pass

    return True


# ---- Vercel Blob Storage ----------------------------------------------------

def upload_to_blob(data: bytes, filename: str, content_type: str = "application/octet-stream") -> str:
    if not _BLOB_TOKEN:
        raise RuntimeError("BLOB_READ_WRITE_TOKEN non défini")

    safe_name = urllib.parse.quote(filename, safe="-_.")
    req = _urllib_req.Request(
        f"https://blob.vercel-storage.com/{safe_name}",
        data=data,
        method="PUT",
        headers={
            "Authorization": f"Bearer {_BLOB_TOKEN}",
            "x-api-version": "7",
            "Content-Type": content_type,
        },
    )
    try:
        with _urllib_req.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except Exception as exc:
        raise RuntimeError(f"Upload Blob échoué : {exc}") from exc

    url = body.get("url")
    if not url:
        raise RuntimeError(f"Réponse Blob invalide (pas de 'url') : {body}")
    return url


def _delete_blob(blob_url: str) -> None:
    if not _BLOB_TOKEN:
        return
    req = _urllib_req.Request(
        "https://blob.vercel-storage.com/delete",
        data=json.dumps({"urls": [blob_url]}).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {_BLOB_TOKEN}",
            "x-api-version": "7",
            "Content-Type": "application/json",
        },
    )
    with _urllib_req.urlopen(req, timeout=10) as _:
        pass
