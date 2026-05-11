"""Archive des PDFs générés et de leurs sources HTML.

Les documents sont stockés dans ~/Documents/CV-Archive/ (local) ou
/tmp/CV-Archive/ (serverless) avec un index history.json.
Quand BLOB_READ_WRITE_TOKEN est défini, les fichiers sont aussi uploadés
sur Vercel Blob Storage pour une persistance permanente.
"""

import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request as _urllib_req
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable

OWNER = "Hariss"

# ---- Vercel Blob Storage (optionnel) ----------------------------------------
# Défini automatiquement quand un Blob store est créé dans le dashboard Vercel.
_BLOB_TOKEN: str | None = os.environ.get("BLOB_READ_WRITE_TOKEN")

# ---- Détection de l'environnement serverless --------------------------------
_IS_SERVERLESS: bool = bool(
    os.environ.get("VERCEL")
    or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    or os.environ.get("PDF_ENGINE", "").lower() == "weasyprint"
)

# ---- Répertoire d'archive ---------------------------------------------------
ARCHIVE_DIR: Path = (
    Path("/tmp") / "CV-Archive"
    if _IS_SERVERLESS
    else Path.home() / "Documents" / "CV-Archive"
)
HISTORY_FILE: Path = ARCHIVE_DIR / "history.json"

DOC_TYPES: tuple[str, ...] = ("CV", "Lettre", "Autre")

# Nombre maximal de tentatives pour trouver un nom de fichier unique
_MAX_UNIQUE_TRIES: int = 100


# ---- Gestion du répertoire d'archive ----------------------------------------

def ensure_archive_dir() -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    if not HISTORY_FILE.exists():
        _write_history([])
    return ARCHIVE_DIR


# ---- Utilitaires de nommage -------------------------------------------------

def _slug(value: str) -> str:
    """Convertit une chaîne en slug ASCII sans espaces ni caractères spéciaux."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^\w\s-]", "", normalized).strip()
    return re.sub(r"[\s_-]+", "", cleaned)


def _safe_filename(name: str) -> str:
    """Sanitise un nom de fichier fourni par l'utilisateur.

    Empêche la traversée de répertoire et les caractères dangereux.
    """
    # Extraire seulement le basename (pas de chemin)
    name = Path(name).name
    # Supprimer les caractères dangereux sous Windows et Linux
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    # Éviter les noms réservés Windows
    if re.match(r'^(CON|PRN|AUX|NUL|COM\d|LPT\d)(\..*)?$', name, re.I):
        name = f"_{name}"
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
    """Retourne un chemin unique dans `directory` pour `filename`."""
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    for n in range(2, _MAX_UNIQUE_TRIES + 2):
        candidate = directory / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
    # Dernier recours : UUID
    return directory / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"


# ---- Lecture / écriture de l'historique -------------------------------------

def _read_history() -> list[dict]:
    ensure_archive_dir()
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write_history(entries: Iterable[dict]) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = HISTORY_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(list(entries), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(HISTORY_FILE)


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
        # Rempli par /convert après upload Blob (optionnel)
        "pdf_blob_url": "",
        "html_blob_url": "",
    }

    history = _read_history()
    history.insert(0, entry)
    _write_history(history)
    return entry


def update_document_blob_urls(doc_id: str, pdf_blob_url: str, html_blob_url: str) -> None:
    """Met à jour les URLs Blob d'un document existant dans history.json."""
    history = _read_history()
    for entry in history:
        if entry.get("id") == doc_id:
            entry["pdf_blob_url"] = pdf_blob_url
            entry["html_blob_url"] = html_blob_url
            break
    _write_history(history)


def list_documents(limit: int | None = None) -> list[dict]:
    history = _read_history()
    return history[:limit] if limit else history


def get_document(doc_id: str) -> dict | None:
    for entry in _read_history():
        if entry.get("id") == doc_id:
            return entry
    return None


def delete_document(doc_id: str) -> bool:
    history = _read_history()
    remaining: list[dict] = []
    found: dict | None = None
    for entry in history:
        if entry.get("id") == doc_id:
            found = entry
        else:
            remaining.append(entry)
    if not found:
        return False

    # Supprimer les fichiers locaux (ignorer les erreurs)
    for key in ("pdf_path", "html_path"):
        path = Path(found.get(key, ""))
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass

    # Supprimer les blobs Vercel si disponibles
    if _BLOB_TOKEN:
        for key in ("pdf_blob_url", "html_blob_url"):
            url = found.get(key, "")
            if url:
                try:
                    _delete_blob(url)
                except Exception:
                    pass  # Non bloquant

    _write_history(remaining)
    return True


# ---- Vercel Blob Storage ----------------------------------------------------

def upload_to_blob(data: bytes, filename: str, content_type: str = "application/octet-stream") -> str:
    """Uploade `data` vers Vercel Blob, retourne l'URL publique permanente.

    Nécessite BLOB_READ_WRITE_TOKEN (créé automatiquement par Vercel quand
    on ajoute un Blob store dans le dashboard → Storage → Create → Blob).

    Raises:
        RuntimeError: si le token est absent ou si l'upload échoue.
    """
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
    """Supprime un blob Vercel via l'API REST (best-effort)."""
    if not _BLOB_TOKEN:
        return
    encoded = urllib.parse.quote(blob_url, safe="")
    req = _urllib_req.Request(
        f"https://blob.vercel-storage.com/delete",
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
