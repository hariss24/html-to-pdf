"""
Convertisseur HTML/CSS -> PDF (interface web locale).

Utilisation :
    Double-cliquez sur ce fichier. Le navigateur s'ouvre sur http://127.0.0.1:5050

Pour quitter :
    Cliquez sur le bouton "Quitter" dans la petite fenetre de controle.
"""

import io
import json as _json
import os
import secrets
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

try:
    import tkinter as tk
    _HAS_TKINTER = True
except ImportError:
    _HAS_TKINTER = False

from flask import (
    Flask, Response, abort, jsonify, redirect,
    render_template, request, send_file, session, stream_with_context,
)

import archive
from pdf_engine import html_to_pdf_bytes, VALID_FORMATS, VALID_MARGINS
import ai_engine
import quota
import json as _json_ai

PORT = 5050
URL  = f"http://127.0.0.1:{PORT}"
MAX_HTML_BYTES = 8 * 1024 * 1024   # 8 Mo
MAX_PDF_BYTES  = 20 * 1024 * 1024  # 20 Mo

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)


# ---- Jeton CSRF léger -------------------------------------------------------
# Les endpoints JSON (Content-Type: application/json) sont implicitement sûrs
# contre le CSRF car les navigateurs ne peuvent pas envoyer ce content-type
# depuis une autre origine via un formulaire HTML.
# Les requêtes multipart (upload PDF) vérifient le header X-CSRF-Token.

def _get_csrf_token() -> str:
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(32)
    return session["_csrf"]

# Expose csrf_token() aux templates Jinja2
app.jinja_env.globals["csrf_token"] = _get_csrf_token


@app.before_request
def _csrf_protect() -> None:
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    ct = request.content_type or ""
    if "application/json" in ct:
        return  # safe : Content-Type non-simple bloque le CSRF cross-origin
    if request.path.startswith("/api/pdf-to-html"):
        client_token = request.headers.get("X-CSRF-Token", "")
        server_token = session.get("_csrf", "")
        if not server_token or not secrets.compare_digest(client_token, server_token):
            abort(403)


# ---------------------------------------------------------------------------
# Pages HTML
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/history")
def history_page():
    return render_template("history.html", is_serverless=archive._IS_SERVERLESS)


# ---------------------------------------------------------------------------
# Conversion PDF
# ---------------------------------------------------------------------------

@app.route("/convert", methods=["POST"])
def convert():
    if request.content_length and request.content_length > MAX_HTML_BYTES:
        return jsonify({"error": f"Corps de requête trop grand (max {MAX_HTML_BYTES // 1024} Ko)."}), 413

    data = request.get_json(silent=True) or {}
    html = data.get("html", "")
    if not html.strip():
        return jsonify({"error": "HTML vide."}), 400
    if len(html.encode()) > MAX_HTML_BYTES:
        return jsonify({"error": "HTML trop grand."}), 413

    fmt    = data.get("format", "A4")
    margin = data.get("margin", "0")
    if fmt not in VALID_FORMATS:
        return jsonify({"error": f"Format invalide : {fmt!r}. Valeurs acceptées : {sorted(VALID_FORMATS)}"}), 400
    if margin not in VALID_MARGINS:
        return jsonify({"error": f"Marge invalide : {margin!r}. Valeurs acceptées : {sorted(VALID_MARGINS)}"}), 400

    background      = bool(data.get("background", True))
    doc_type        = data.get("doc_type", "CV")
    company         = (data.get("company") or "").strip()
    role            = (data.get("role") or "").strip()
    notes           = (data.get("notes") or "").strip()
    job_desc        = (data.get("job_desc") or "").strip()
    custom_filename = (data.get("filename") or "").strip()

    try:
        pdf_bytes = html_to_pdf_bytes(html, page_format=fmt, margin=margin, background=background)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({
            "error": f"Erreur de rendu PDF : {e}",
            "hint": "Vérifiez que le HTML est valide et ne contient pas de ressources externes bloquées.",
        }), 500

    # Archivage best-effort
    entry: dict
    try:
        entry = archive.save_document(
            html=html, pdf_bytes=pdf_bytes, doc_type=doc_type,
            company=company, role=role, notes=notes,
            custom_filename=custom_filename, job_desc=job_desc,
        )
    except Exception:
        import uuid as _uuid
        from datetime import datetime as _dt
        entry = {
            "id": str(_uuid.uuid4()),
            "filename": custom_filename or f"document_{_dt.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            "created_at": _dt.now().isoformat(timespec="seconds"),
        }

    # Upload Vercel Blob (optionnel)
    pdf_blob_url  = ""
    html_blob_url = ""
    if archive._BLOB_TOKEN:
        try:
            pdf_blob_url  = archive.upload_to_blob(pdf_bytes, entry["filename"], "application/pdf")
            html_filename = Path(entry["filename"]).stem + ".html"
            html_blob_url = archive.upload_to_blob(html.encode("utf-8"), html_filename, "text/html")
            try:
                archive.update_document_blob_urls(entry["id"], pdf_blob_url, html_blob_url)
            except Exception:
                pass
        except Exception:
            pass

    response = send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=entry["filename"],
    )
    response.headers["X-Archive-Entry"] = _json.dumps({
        "id":         entry.get("id", ""),
        "filename":   entry.get("filename", "document.pdf"),
        "created_at": entry.get("created_at", ""),
    })
    response.headers["X-Blob-PDF-URL"]  = pdf_blob_url
    response.headers["X-Blob-HTML-URL"] = html_blob_url
    response.headers["Access-Control-Expose-Headers"] = (
        "X-Archive-Entry, X-Blob-PDF-URL, X-Blob-HTML-URL"
    )
    return response


# ---------------------------------------------------------------------------
# API Historique
# ---------------------------------------------------------------------------

@app.route("/api/history")
def api_history():
    return jsonify(archive.list_documents())


@app.route("/api/history/<doc_id>")
def api_history_get(doc_id):
    entry = archive.get_document(doc_id)
    if not entry:
        abort(404)
    return jsonify(entry)


@app.route("/api/history/<doc_id>/html")
def api_history_html(doc_id):
    entry = archive.get_document(doc_id)
    if not entry:
        abort(404)
    html_path = Path(entry.get("html_path", ""))
    if html_path.exists():
        return html_path.read_text(encoding="utf-8"), 200, {"Content-Type": "text/plain; charset=utf-8"}
    blob_url = entry.get("html_blob_url", "")
    if blob_url:
        return redirect(blob_url)
    abort(404)


@app.route("/api/history/<doc_id>/pdf")
def api_history_pdf(doc_id):
    entry = archive.get_document(doc_id)
    if not entry:
        abort(404)
    pdf_path = Path(entry.get("pdf_path", ""))
    if pdf_path.exists():
        return send_file(pdf_path, mimetype="application/pdf", as_attachment=False, download_name=entry["filename"])
    blob_url = entry.get("pdf_blob_url", "")
    if blob_url:
        return redirect(blob_url)
    abort(404)


@app.route("/api/history/<doc_id>/open", methods=["POST"])
def api_history_open(doc_id):
    if archive._IS_SERVERLESS:
        return jsonify({"error": "Non disponible en mode serverless."}), 400
    entry = archive.get_document(doc_id)
    if not entry:
        abort(404)
    pdf_path = Path(entry["pdf_path"])
    if not pdf_path.exists():
        abort(404)
    try:
        os.startfile(str(pdf_path))
        return jsonify({"ok": True})
    except (AttributeError, OSError) as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/<doc_id>", methods=["DELETE"])
def api_history_delete(doc_id):
    if archive.delete_document(doc_id):
        return jsonify({"ok": True})
    abort(404)


# ---------------------------------------------------------------------------
# API IA
# ---------------------------------------------------------------------------

_SYSTEM_TEXT_TO_HTML_BASE = (
    "Tu reçois le contenu texte brut d'un CV. "
    "Retourne uniquement le HTML structuré correspondant : utilise des balises sémantiques "
    "(h1, h2, h3, p, ul, li, strong). Ne génère pas de CSS. Ne génère pas de design. "
    "Uniquement la structure HTML du contenu, fidèle au texte fourni."
)

_SYSTEM_TEXT_TO_HTML_WITH_CSS = (
    "Tu reçois le contenu texte brut d'un CV et une feuille de style CSS. "
    "Retourne uniquement le HTML structuré correspondant en utilisant les classes CSS "
    "présentes dans la feuille de style fournie pour chaque élément approprié. "
    "N'ajoute aucune balise <style>, aucun attribut style inline, aucun CSS. "
    "Uniquement la structure HTML avec les classes CSS adéquates, fidèle au texte fourni.\n\n"
    "CSS de référence :\n{css}"
)

_SYSTEM_PDF_PAGE_BASE = (
    "Voici une page d'un CV en image. "
    "Retourne uniquement le HTML structuré du contenu visible : titres, paragraphes, listes, "
    "dates, intitulés. Pas de CSS, pas de style inline, uniquement les balises HTML sémantiques. "
    "Texte en français si c'est en français, anglais si c'est en anglais."
)

_SYSTEM_PDF_PAGE_WITH_CSS = (
    "Voici une page d'un CV en image et une feuille de style CSS. "
    "Retourne uniquement le HTML structuré du contenu visible en utilisant les classes CSS "
    "présentes dans la feuille de style fournie pour chaque élément approprié. "
    "Pas de balise <style>, pas de style inline. Uniquement les balises HTML avec les classes adéquates. "
    "Texte en français si c'est en français, anglais si c'est en anglais.\n\n"
    "CSS de référence :\n{css}"
)


def _build_import_system(base: str, with_css_template: str, css: str) -> str:
    """Retourne le prompt système adapté selon que du CSS est fourni ou non."""
    css = (css or "").strip()
    if not css:
        return base
    return with_css_template.format(css=css)

_TAILOR_SYSTEMS = {
    "peu": (
        "Tu reçois un CV en HTML et une offre d'emploi. "
        "Niveau d'adaptation : SUBTIL (peu adapté). "
        "Tu peux UNIQUEMENT modifier : "
        "(1) le titre/tagline sous le nom (pour refléter le poste visé de façon générique) ; "
        "(2) la section résumé/accroche pour l'orienter vers ce type de poste avec 2-3 mots-clés naturels. "
        "Le résumé doit rester générique : il reflète le profil du candidat orienté vers ce type de poste, "
        "PAS une candidature spécifique à une entreprise. "
        "RÈGLE ABSOLUE ANTI-DÉTECTION : N'écris JAMAIS le nom de l'entreprise ciblée, "
        "ni 'chez [entreprise]', ni 'au sein de [entreprise]', ni aucune référence directe à l'employeur cible "
        "dans le résumé, le titre, ou n'importe quelle autre section. "
        "INTERDIT : toucher aux compétences (ni en ajouter, ni en retirer, ni les réordonner), "
        "modifier les descriptions de postes ou les listes à puces des expériences, "
        "supprimer ou modifier les langues, les centres d'intérêt, la formation, "
        "les dates, les entreprises du parcours, les intitulés de poste. "
        "Le CV doit rester à 95% identique à l'original. "
        "Retourne uniquement le HTML complet, sans commentaire, sans markdown."
    ),
    "adapte": (
        "Tu reçois un CV en HTML et une offre d'emploi. "
        "Niveau d'adaptation : MODÉRÉ (adapté). "
        "Tu peux : "
        "(1) ajuster le titre/tagline sous le nom pour refléter le poste visé de façon générique ; "
        "(2) réécrire le résumé/accroche pour ce type de poste ; "
        "(3) réordonner les compétences existantes pour mettre les plus pertinentes en premier "
        "(SANS EN AJOUTER NI EN SUPPRIMER) ; "
        "(4) enrichir et reformuler les puces des expériences existantes (maximum 4 puces par expérience). "
        "Pour les puces : développe et enrichis ce qui est déjà écrit (ajoute contexte, métriques si disponibles "
        "dans le reste du CV), mais ne fabrique pas de contenu absent du CV original. "
        "RÈGLE ABSOLUE ANTI-DÉTECTION : N'écris JAMAIS le nom de l'entreprise ciblée, "
        "ni 'chez [entreprise]', ni 'au sein de [entreprise]', ni aucune référence directe à l'employeur cible "
        "dans le résumé, le titre, ou n'importe quelle autre section. "
        "Le résumé doit rester générique : profil orienté vers ce type de poste, pas une candidature nominative. "
        "INTERDIT : inventer ou supprimer des compétences, "
        "toucher à la section langues (doit rester intacte avec TOUTES les langues listées), "
        "toucher à la section centres d'intérêt (doit rester intacte), "
        "modifier les dates, entreprises du parcours, intitulés de poste ou diplômes. "
        "Retourne uniquement le HTML complet, sans commentaire, sans markdown."
    ),
    "hyper": (
        "Tu reçois un CV en HTML et une offre d'emploi. "
        "Niveau d'adaptation : MAXIMUM (hyper-adapté). "
        "Tu peux : "
        "(1) ajuster le titre/tagline sous le nom pour refléter le poste visé de façon générique ; "
        "(2) réécrire complètement le résumé/accroche ; "
        "(3) réorganiser ET reformuler les compétences existantes pour maximiser la pertinence "
        "(SANS en inventer de nouvelles, uniquement celles déjà présentes dans le CV original) ; "
        "(4) réécrire entièrement les puces d'expériences pour aligner au maximum avec les mots-clés "
        "du poste (maximum 4 puces par expérience, sans fabriquer de contenu absent du CV). "
        "RÈGLE ABSOLUE ANTI-DÉTECTION : N'écris JAMAIS le nom de l'entreprise ciblée, "
        "ni 'chez [entreprise]', ni 'au sein de [entreprise]', ni aucune référence directe à l'employeur cible "
        "dans le résumé, le titre, ou n'importe quelle autre section. "
        "Le résumé doit rester générique : profil orienté vers ce type de poste, pas une candidature nominative. "
        "ABSOLUMENT INTERDIT : "
        "supprimer la section langues ou retirer une seule langue (toutes doivent rester), "
        "supprimer ou modifier la section centres d'intérêt, "
        "inventer des compétences absentes du CV original, "
        "modifier les dates, entreprises du parcours, intitulés de poste, diplômes ou noms propres. "
        "Retourne uniquement le HTML complet, sans commentaire, sans markdown."
    ),
}


def _stream_ai(generator_fn):
    """Wrapper SSE commun pour tous les endpoints IA."""
    return Response(
        stream_with_context(generator_fn()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _check_quota(user_key: str | None) -> Response | None:
    """Retourne une réponse d'erreur si le quota est dépassé, None sinon."""
    if not user_key and not quota.check_and_increment():
        return jsonify({"error": (
            "Quota journalier atteint. Colle ton texte manuellement "
            "ou ajoute ta propre clé dans les paramètres."
        )}), 429
    return None


@app.route("/api/status", methods=["GET"])
def api_status():
    key = os.environ.get("GEMINI_API_KEY", "")
    return jsonify({
        "server_key_configured": bool(key),
        "server_key_preview":    (key[:4] + "…") if key else None,
        "quota_remaining":       quota.remaining(),
        "quota_limit":           quota.DAILY_LIMIT,
    })


@app.route("/api/text-to-html", methods=["POST"])
def api_text_to_html():
    data     = request.get_json(force=True) or {}
    text     = (data.get("text") or "").strip()
    css      = (data.get("css") or "").strip()
    if not text:
        return jsonify({"error": "Texte vide."}), 400
    user_key = (request.headers.get("X-Api-Key") or "").strip() or None
    err = _check_quota(user_key)
    if err:
        return err

    system = _build_import_system(
        _SYSTEM_TEXT_TO_HTML_BASE, _SYSTEM_TEXT_TO_HTML_WITH_CSS, css
    )

    def generate():
        try:
            for chunk in ai_engine.stream_completion(text, system, api_key=user_key):
                yield f"data: {_json_ai.dumps(chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            yield f"data: [ERROR] {exc}\n\n"

    return _stream_ai(generate)


@app.route("/api/pdf-to-html", methods=["POST"])
def api_pdf_to_html():
    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier reçu."}), 400
    f = request.files["file"]
    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Le fichier doit être un PDF (.pdf)."}), 400
    pdf_bytes = f.read()
    if len(pdf_bytes) > MAX_PDF_BYTES:
        return jsonify({"error": "PDF trop volumineux (max 20 Mo)."}), 413

    css      = (request.form.get("css") or "").strip()
    user_key = (request.headers.get("X-Api-Key") or "").strip() or None
    err = _check_quota(user_key)
    if err:
        return err

    system = _build_import_system(
        _SYSTEM_PDF_PAGE_BASE, _SYSTEM_PDF_PAGE_WITH_CSS, css
    )

    def generate():
        import fitz
        doc = None
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix  = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                for chunk in ai_engine.stream_completion(
                    f"Page {page_num + 1} du CV :",
                    system,
                    images=[img_bytes],
                    api_key=user_key,
                ):
                    yield f"data: {_json_ai.dumps(chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            yield f"data: [ERROR] {exc}\n\n"
        finally:
            if doc is not None:
                doc.close()

    return _stream_ai(generate)


@app.route("/api/tailor", methods=["POST"])
def api_tailor():
    data     = request.get_json(force=True) or {}
    html     = (data.get("html") or "").strip()
    job_desc = (data.get("job_desc") or "").strip()
    level    = (data.get("level") or "adapte").strip()
    if level not in _TAILOR_SYSTEMS:
        level = "adapte"
    if not html or not job_desc:
        return jsonify({"error": "Le HTML du CV et la description du poste sont requis."}), 400

    user_key = (request.headers.get("X-Api-Key") or "").strip() or None
    err = _check_quota(user_key)
    if err:
        return err

    system_prompt = _TAILOR_SYSTEMS[level]
    prompt = f"CV HTML :\n{html}\n\nOffre d'emploi :\n{job_desc}"

    def generate():
        try:
            for chunk in ai_engine.stream_completion(prompt, system_prompt, api_key=user_key):
                yield f"data: {_json_ai.dumps(chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            yield f"data: [ERROR] {exc}\n\n"

    return _stream_ai(generate)


# ---------------------------------------------------------------------------
# Lanceur local (desktop)
# ---------------------------------------------------------------------------

def _wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.05)


def lancer_serveur() -> None:
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)


def lancer_navigateur() -> None:
    _wait_for_port(PORT)
    webbrowser.open(URL)


def fenetre_controle() -> None:
    if not _HAS_TKINTER:
        print(f"Serveur disponible sur {URL}  (Ctrl-C pour quitter)")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            sys.exit(0)
        return

    root = tk.Tk()
    root.title("Convertisseur HTML -> PDF")
    root.resizable(False, False)
    largeur, hauteur = 360, 160
    x = (root.winfo_screenwidth()  - largeur) // 2
    y = (root.winfo_screenheight() - hauteur) // 2
    root.geometry(f"{largeur}x{hauteur}+{x}+{y}")

    tk.Label(root, text="Le serveur tourne sur :", pady=8).pack()
    lien = tk.Label(root, text=URL, fg="#1a73e8", cursor="hand2", font=("Segoe UI", 10, "underline"))
    lien.pack()
    lien.bind("<Button-1>", lambda _e: webbrowser.open(URL))
    tk.Label(root, text="Fermez cette fenetre pour arreter.", fg="#666", pady=8).pack()

    def quitter() -> None:
        root.destroy()
        sys.exit(0)

    tk.Button(root, text="Quitter", width=14, command=quitter).pack(pady=6)
    root.protocol("WM_DELETE_WINDOW", quitter)
    root.mainloop()


def main() -> None:
    archive.ensure_archive_dir()
    threading.Thread(target=lancer_serveur,    daemon=True).start()
    threading.Thread(target=lancer_navigateur, daemon=True).start()
    fenetre_controle()


if __name__ == "__main__":
    main()
