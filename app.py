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
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path

try:
    import tkinter as tk
    _HAS_TKINTER = True
except ImportError:
    _HAS_TKINTER = False

from flask import (
    Flask, Response, abort, jsonify, redirect,
    render_template, request, send_file, session, stream_with_context, url_for,
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


# ---------------------------------------------------------------------------
# Mode local / remote
# ---------------------------------------------------------------------------

_login_lock = threading.Lock()
_login_attempts: dict[str, list[float]] = {}
_LOGIN_WINDOW = 60      # secondes
_LOGIN_MAX_ATTEMPTS = 5


def _login_rate_limit_ok() -> bool:
    if app.config.get("TESTING"):
        return True
    ip = request.remote_addr or "unknown"
    now = time.monotonic()
    with _login_lock:
        recent = [t for t in _login_attempts.get(ip, []) if now - t < _LOGIN_WINDOW]
        _login_attempts[ip] = recent
        return len(recent) < _LOGIN_MAX_ATTEMPTS


def _login_record_failure() -> None:
    if app.config.get("TESTING"):
        return
    ip = request.remote_addr or "unknown"
    now = time.monotonic()
    with _login_lock:
        recent = [t for t in _login_attempts.get(ip, []) if now - t < _LOGIN_WINDOW]
        recent.append(now)
        _login_attempts[ip] = recent

_TRUE_VALUES = {"1", "true", "yes", "on", "remote", "production"}


def _remote_auth_password() -> str:
    return (
        os.environ.get("REMOTE_AUTH_PASSWORD")
        or os.environ.get("AUTH_PASSWORD")
        or ""
    )


def _is_remote_mode() -> bool:
    app_mode = os.environ.get("APP_MODE", "").strip().lower()
    return (
        app_mode in _TRUE_VALUES
        or bool(os.environ.get("RENDER"))
        or bool(_remote_auth_password())
    )


def _is_api_request() -> bool:
    return request.path.startswith("/api/") or request.path == "/convert"


def _auth_error(message: str, status: int):
    if _is_api_request():
        return jsonify({"error": message}), status
    return message, status


def _auth_required_response():
    if _is_api_request():
        return jsonify({"error": "Authentication required."}), 401
    return redirect(url_for("login_page", next=request.full_path if request.query_string else request.path))


def _is_auth_exempt_path(path: str) -> bool:
    return (
        path == "/login"
        or path == "/logout"
        or path.startswith("/static/")
    )


@app.before_request
def _remote_auth_protect():
    if not _is_remote_mode() or _is_auth_exempt_path(request.path):
        return
    if not _remote_auth_password():
        return _auth_error("REMOTE_AUTH_PASSWORD must be configured in remote mode.", 503)
    if session.get("remote_authenticated") is True:
        return
    return _auth_required_response()


@app.route("/login", methods=["GET"])
def login_page():
    if not _is_remote_mode():
        return redirect(url_for("index"))
    if not _remote_auth_password():
        return _auth_error("REMOTE_AUTH_PASSWORD must be configured in remote mode.", 503)
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    if not _is_remote_mode():
        session["remote_authenticated"] = True
        return jsonify({"ok": True, "mode": "local"})
    expected = _remote_auth_password()
    if not expected:
        return jsonify({"error": "REMOTE_AUTH_PASSWORD must be configured in remote mode."}), 503
    if not _login_rate_limit_ok():
        return jsonify({"error": "Trop de tentatives. Réessayez dans une minute."}), 429
    data = request.get_json(silent=True) or request.form
    supplied = (data.get("password") or "").strip()
    if not secrets.compare_digest(supplied, expected):
        _login_record_failure()
        return jsonify({"error": "Invalid password."}), 401
    session["remote_authenticated"] = True
    return jsonify({"ok": True})


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("remote_authenticated", None)
    return jsonify({"ok": True})


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
    return render_template("history.html")


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

    # Générer les métadonnées de téléchargement (pas de persistance serveur)
    when = datetime.now()
    doc_type_safe = doc_type if doc_type in archive.DOC_TYPES else "Autre"
    filename = (
        archive._safe_filename(custom_filename)
        if custom_filename
        else archive.make_filename(doc_type_safe, company, role, when)
    )
    entry = {
        "id":         str(uuid.uuid4()),
        "filename":   filename,
        "created_at": when.isoformat(timespec="seconds"),
    }

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
    response.headers["Access-Control-Expose-Headers"] = "X-Archive-Entry"
    return response


# ---------------------------------------------------------------------------
# API IA
# ---------------------------------------------------------------------------

_CV_HTML_SKELETON = """\
<div class="resume-template-1 resume-template-renderer">

  <section class="resume-template-renderer-section personal-data">
    <h2 class="resume-template-renderer-section__title">Informations personnelles</h2>
    <div class="personal-data__photo" style="background:#eee;">
      <!-- URL_DE_VOTRE_PHOTO_ICI -->
    </div>
    <div class="personal-data__title-row">
      <span class="personal-data__name">Prenom Nom</span><span class="personal-data__desired-job-title">Titre du poste</span>
    </div>
    <div class="personal-data__contact-row">
      Ville, Pays &middot; email@example.com &middot; +33 6 00 00 00 00 &middot; linkedin.com/in/profil
    </div></section>

  <section class="resume-template-renderer-section summary-objective">
    <h2 class="resume-template-renderer-section__title summary-objective__title">A propos</h2>
    <div class="summary-objective__content">
      Bref resume professionnel.
    </div>
  </section>

  <section class="resume-template-renderer-section entry-list">
    <h2 class="resume-template-renderer-section__title">Experience</h2>
    <div class="entry-list__item">
      <span class="entry-list__title">Poste occupe</span>
      <span class="entry-list__date">Jan 2024 - Present</span>
      <div class="entry-list__company-row">
        <span class="entry-list__subtitle">Entreprise</span><span class="entry-list__location">Ville</span>
      </div>
      <div class="entry-list__description">
        <ul>
          <li>Realisation.</li>
        </ul>
      </div>
    </div>
  </section>

  <section class="resume-template-renderer-section entry-list">
    <h2 class="resume-template-renderer-section__title">Formation</h2>
    <div class="entry-list__item">
      <span class="entry-list__title">Diplome</span>
      <span class="entry-list__date">2020 - 2022</span>
      <div class="entry-list__company-row">
        <span class="entry-list__subtitle">Etablissement</span><span class="entry-list__location">Ville</span>
      </div>
      <div class="entry-list__description">
        <p>Description, specialites ou matieres principales.</p>
      </div>
    </div>
  </section>

  <section class="resume-template-renderer-section plain-list">
    <h2 class="resume-template-renderer-section__title">Competences</h2>
    <div class="plain-list__items">
      <span class="plain-list__item">Competence 1</span>
    </div>
  </section>

  <section class="resume-template-renderer-section languages">
    <h2 class="resume-template-renderer-section__title">Langues</h2>
    <div class="languages__items">
      <div class="languages__item">
        <span class="languages__name">Francais</span>
        <span class="languages__description">Natif</span>
      </div>
    </div>
  </section>

</div>"""

_LETTRE_SKELETON = """\
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>Lettre de Motivation</title>
  <style>
    @page { size: A4; margin: 0; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: "Helvetica", "Arial", sans-serif; font-size: 9.5pt; line-height: 1.6; color: #333; padding: 48px 58px 40px; }
    .header { display: flex; justify-content: space-between; margin-bottom: 36px; }
    .sender strong, .recipient strong { font-size: 10.5pt; color: #000; }
    .sender p, .recipient p { margin-top: 2px; color: #555; font-size: 9pt; }
    .recipient { text-align: right; }
    .subject { font-weight: 600; font-size: 9.5pt; color: #000; margin-bottom: 24px; border-bottom: 2px solid #c9c6c1; padding-bottom: 8px; }
    .salutation { margin-bottom: 16px; }
    .body p { margin-bottom: 16px; text-align: justify; }
    .closing { margin-top: 32px; }
    .closing p { margin-bottom: 6px; }
    .signature { margin-top: 24px; font-weight: 600; font-size: 10pt; color: #000; }
  </style>
</head>
<body>
  <div class="header">
    <div class="sender">
      <strong>Prenom Nom</strong>
      <p>Titre du poste</p>
      <p>Ville, Pays</p>
      <p>+33 6 00 00 00 00</p>
      <p>email@example.com</p>
    </div>
    <div class="recipient">
      <strong>A l'attention du responsable de recrutement</strong>
      <p>Ville, le JJ mois AAAA</p>
    </div>
  </div>
  <div class="subject">Objet : Candidature au poste de [Poste]</div>
  <div class="salutation">Madame, Monsieur,</div>
  <div class="body">
    <p>Paragraphe d'introduction.</p>
    <p>Paragraphe sur les competences et experiences.</p>
    <p>Paragraphe de conclusion.</p>
  </div>
  <div class="closing">
    <p>Je vous adresse mes sinceres salutations,</p>
  </div>
  <div class="signature">Prenom Nom</div>
</body>
</html>"""

_SYSTEM_CV_IMPORT = (
    "Tu reçois le contenu d'un CV (texte ou image). Remplis ce squelette HTML avec les données du CV fourni.\n\n"
    "RÈGLES — RESPECTE-LES À LA LETTRE :\n"
    "1. Conserve EXACTEMENT la structure HTML et toutes les classes CSS du squelette. Ne les modifie jamais.\n"
    "2. Remplace uniquement le contenu textuel par les données réelles du CV.\n"
    "3. Blocs répétables — inclus TOUS les éléments du CV, sans en omettre aucun :\n"
    "   • entry-list__item : un bloc par expérience professionnelle, un bloc par diplôme\n"
    "     → Pour chaque diplôme : inclus la description (matières, spécialités, programme) dans entry-list__description si présente dans le CV.\n"
    "     → Pour chaque expérience : inclus TOUTES les réalisations/puces dans entry-list__description.\n"
    "   • plain-list__item : un <span> par compétence\n"
    "   • languages__item : un bloc par langue\n"
    "4. Si une section est absente du CV (pas de résumé, pas de langues…), omets la section entière.\n"
    "5. N'ajoute AUCUNE balise <style>, AUCUN attribut style inline (sauf style=\"background:#eee;\" déjà présent).\n"
    "6. Laisse <!-- URL_DE_VOTRE_PHOTO_ICI --> exactement tel quel, sans le modifier.\n"
    "7. Retourne UNIQUEMENT le HTML rempli, sans balise markdown, sans commentaire, sans explication.\n\n"
    "Squelette à remplir :\n" + _CV_HTML_SKELETON
)

_SYSTEM_LETTRE_IMPORT = (
    "Tu reçois le contenu d'une lettre de motivation (texte ou image). Remplis ce squelette HTML.\n\n"
    "RÈGLES — RESPECTE-LES À LA LETTRE :\n"
    "1. Conserve EXACTEMENT la structure HTML, toutes les classes CSS, et la balise <style> du squelette.\n"
    "2. Remplace uniquement le contenu textuel par les données réelles de la lettre.\n"
    "3. Ne modifie PAS les styles CSS.\n"
    "4. Retourne le document HTML COMPLET (DOCTYPE inclus), sans markdown, sans commentaire.\n\n"
    "Squelette à remplir :\n" + _LETTRE_SKELETON
)

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
    doc_type = (data.get("doc_type") or "CV").strip()
    if not text:
        return jsonify({"error": "Texte vide."}), 400
    user_key = (request.headers.get("X-Api-Key") or "").strip() or None
    err = _check_quota(user_key)
    if err:
        return err

    system = _SYSTEM_LETTRE_IMPORT if doc_type == "Lettre" else _SYSTEM_CV_IMPORT

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

    doc_type = (request.form.get("doc_type") or "CV").strip()
    user_key = (request.headers.get("X-Api-Key") or "").strip() or None
    err = _check_quota(user_key)
    if err:
        return err

    system = _SYSTEM_LETTRE_IMPORT if doc_type == "Lettre" else _SYSTEM_CV_IMPORT

    def generate():
        import fitz
        doc = None
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            images = []
            for page_num in range(len(doc)):
                pix = doc[page_num].get_pixmap(dpi=150)
                images.append(pix.tobytes("png"))
            n = len(images)
            prompt = (
                f"Voici le document en {n} page{'s' if n > 1 else ''}. "
                "Remplis le squelette avec TOUTES les informations visibles. "
                "N'omet AUCUN détail : descriptions de formations, spécialités, sous-matières, "
                "réalisations des expériences, dates précises, coordonnées complètes."
            )
            for chunk in ai_engine.stream_completion(prompt, system, images=images, api_key=user_key):
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
