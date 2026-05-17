"""Tests pour archive.py — backend SQLite local."""
import os
import sys
import threading
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

# Forcer le mode local (pas serverless) pour tous les tests
os.environ.pop("VERCEL", None)
os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
os.environ.pop("MONGODB_URI", None)
os.environ["PDF_ENGINE"] = ""  # pas weasyprint → pas serverless via ce flag

import archive


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    """Chaque test utilise un répertoire d'archive temporaire isolé."""
    monkeypatch.setattr(archive, "ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(archive, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(archive, "_DB_PATH", tmp_path / "history.db")
    monkeypatch.setattr(archive, "_IS_SERVERLESS", False)
    monkeypatch.setattr(archive, "_history_collection", None)
    monkeypatch.setattr(archive, "_db_initialized", False)
    yield


def _fake_pdf() -> bytes:
    return b"%PDF-1.4 fake"


def _fake_html() -> str:
    return "<html><body><h1>Test CV</h1></body></html>"


# ---- Tests de base ----------------------------------------------------------

def test_ensure_archive_dir_creates_directory(tmp_path, monkeypatch):
    target = tmp_path / "new_archive"
    monkeypatch.setattr(archive, "ARCHIVE_DIR", target)
    monkeypatch.setattr(archive, "_DB_PATH", target / "history.db")
    assert not target.exists()
    archive.ensure_archive_dir()
    assert target.exists()


def test_save_document_creates_files():
    entry = archive.save_document(
        html=_fake_html(),
        pdf_bytes=_fake_pdf(),
        doc_type="CV",
        company="TestCorp",
        role="Dev",
    )
    assert "id" in entry
    assert entry["doc_type"] == "CV"
    assert entry["company"] == "TestCorp"
    assert Path(entry["pdf_path"]).exists()
    assert Path(entry["html_path"]).exists()


def test_save_document_custom_filename():
    entry = archive.save_document(
        html=_fake_html(),
        pdf_bytes=_fake_pdf(),
        custom_filename="mon_cv_special.pdf",
    )
    assert entry["filename"] == "mon_cv_special.pdf"
    assert Path(entry["pdf_path"]).name == "mon_cv_special.pdf"


def test_save_document_sanitizes_dangerous_filename():
    entry = archive.save_document(
        html=_fake_html(),
        pdf_bytes=_fake_pdf(),
        custom_filename="../../etc/passwd",
    )
    # Le chemin ne doit pas traverser le répertoire
    pdf_path = Path(entry["pdf_path"])
    assert archive.ARCHIVE_DIR in pdf_path.parents or pdf_path.parent == archive.ARCHIVE_DIR


def test_list_documents_empty():
    archive.ensure_archive_dir()
    docs = archive.list_documents()
    assert docs == []


def test_list_documents_returns_all():
    archive.save_document(_fake_html(), _fake_pdf(), company="A")
    archive.save_document(_fake_html(), _fake_pdf(), company="B")
    docs = archive.list_documents()
    assert len(docs) == 2


def test_list_documents_ordered_by_date_desc():
    import time
    archive.save_document(_fake_html(), _fake_pdf(), company="First")
    time.sleep(1.1)  # created_at a une précision à la seconde
    archive.save_document(_fake_html(), _fake_pdf(), company="Second")
    docs = archive.list_documents()
    # Le plus récent en premier
    assert docs[0]["company"] == "Second"
    assert docs[1]["company"] == "First"


def test_get_document_found():
    entry = archive.save_document(_fake_html(), _fake_pdf(), company="GetTest")
    found = archive.get_document(entry["id"])
    assert found is not None
    assert found["company"] == "GetTest"


def test_get_document_not_found():
    archive.ensure_archive_dir()
    assert archive.get_document("nonexistent-id") is None


def test_delete_document_removes_files():
    entry = archive.save_document(_fake_html(), _fake_pdf())
    pdf_path  = Path(entry["pdf_path"])
    html_path = Path(entry["html_path"])
    assert pdf_path.exists()
    assert html_path.exists()

    result = archive.delete_document(entry["id"])
    assert result is True
    assert not pdf_path.exists()
    assert not html_path.exists()


def test_delete_document_removes_from_db():
    entry = archive.save_document(_fake_html(), _fake_pdf())
    archive.delete_document(entry["id"])
    assert archive.get_document(entry["id"]) is None


def test_delete_document_not_found():
    archive.ensure_archive_dir()
    assert archive.delete_document("no-such-id") is False


def test_update_document_blob_urls():
    entry = archive.save_document(_fake_html(), _fake_pdf())
    archive.update_document_blob_urls(entry["id"], "https://blob/a.pdf", "https://blob/a.html")
    found = archive.get_document(entry["id"])
    assert found["pdf_blob_url"]  == "https://blob/a.pdf"
    assert found["html_blob_url"] == "https://blob/a.html"


def test_list_documents_limit():
    for i in range(5):
        archive.save_document(_fake_html(), _fake_pdf(), company=f"Co{i}")
    assert len(archive.list_documents(limit=3)) == 3


# ---- Unicité des noms de fichiers -------------------------------------------

def test_unique_path_collision():
    """Deux documents avec le même nom auto génèrent des fichiers distincts."""
    e1 = archive.save_document(_fake_html(), _fake_pdf(), doc_type="CV", company="Acme", role="Dev")
    e2 = archive.save_document(_fake_html(), _fake_pdf(), doc_type="CV", company="Acme", role="Dev")
    assert e1["pdf_path"] != e2["pdf_path"]


# ---- Concurrence ------------------------------------------------------------

def test_concurrent_saves_no_corruption():
    """Plusieurs threads sauvegardent simultanément sans corrompre la DB."""
    results = []
    errors  = []

    def worker(idx):
        try:
            e = archive.save_document(_fake_html(), _fake_pdf(), company=f"Co{idx}")
            results.append(e["id"])
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Erreurs en concurrence : {errors}"
    docs = archive.list_documents()
    assert len(docs) == 10
    # Tous les IDs sont uniques
    assert len({d["id"] for d in docs}) == 10


# ---- Migration JSON → SQLite ------------------------------------------------

def test_migrate_from_json(tmp_path, monkeypatch):
    import json

    # Préparer un history.json avec 2 entrées
    hist_file = tmp_path / "history.json"
    entries = [
        {
            "id": str(uuid.uuid4()), "created_at": "2024-01-01T10:00:00",
            "doc_type": "CV", "company": "Migré", "role": "Dev",
            "notes": "", "job_desc": "", "filename": "CV_Migré.pdf",
            "pdf_path": "", "html_path": "", "pdf_blob_url": "", "html_blob_url": "",
        },
    ]
    hist_file.write_text(json.dumps(entries))

    monkeypatch.setattr(archive, "ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(archive, "HISTORY_FILE", hist_file)
    monkeypatch.setattr(archive, "_DB_PATH", tmp_path / "history.db")
    monkeypatch.setattr(archive, "_IS_SERVERLESS", False)
    monkeypatch.setattr(archive, "_history_collection", None)
    monkeypatch.setattr(archive, "_db_initialized", False)

    archive.ensure_archive_dir()
    docs = archive.list_documents()
    assert len(docs) == 1
    assert docs[0]["company"] == "Migré"
    # Le JSON original doit avoir été renommé
    assert not hist_file.exists()
    assert (tmp_path / "history.json.migrated").exists()


# ---- Utilitaires de nommage -------------------------------------------------

def test_slug_basic():
    assert archive._slug("Société Générale") == "SocieteGenerale"


def test_slug_empty():
    assert archive._slug("") == ""


def test_safe_filename_removes_traversal():
    assert ".." not in archive._safe_filename("../../etc/passwd")


def test_safe_filename_removes_forbidden_chars():
    result = archive._safe_filename('file<>:"/\\|?*.pdf')
    assert "<" not in result
    assert ">" not in result
    assert "/" not in result


def test_make_filename_includes_parts():
    name = archive.make_filename("CV", company="Acme", role="Dev")
    assert "CV" in name
    assert archive.OWNER in name
    assert "Acme" in name
    assert name.endswith(".pdf")
