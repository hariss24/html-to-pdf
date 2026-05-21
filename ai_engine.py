"""Appels IA (Gemini et Anthropic) avec streaming.

Usage :
    for chunk in stream_completion(prompt, system, api_key="AIza..."):
        print(chunk, end="", flush=True)
"""
import os
import re
from typing import Generator

# gemini-2.0-flash : meilleur rapport qualité/quota sur le free tier.
# gemini-2.0-flash-lite : plus rapide mais quota journalier plus faible.
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")


def stream_completion(
    prompt: str,
    system: str,
    images: list[bytes] | None = None,
    api_key: str | None = None,
) -> Generator[str, None, None]:
    """Appelle l'IA et génère les chunks de réponse un par un.

    Args:
        prompt:   Texte envoyé à l'IA (contenu du CV, offre d'emploi…)
        system:   Instructions système définissant le comportement de l'IA
        images:   Liste d'images PNG en bytes (pour la conversion PDF page par page)
        api_key:  Clé utilisateur. Si absente, utilise GEMINI_API_KEY env var.

    Yields:
        Morceaux de texte HTML au fur et à mesure qu'ils arrivent.

    Raises:
        ValueError: si aucune clé API n'est disponible, ou si Anthropic reçoit des images.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ValueError(
            "Aucune clé API configurée. "
            "Ajoutez GEMINI_API_KEY dans les variables d'environnement "
            "ou une clé personnelle dans ⚙️ Paramètres."
        )

    if _is_anthropic_key(key):
        if images:
            raise ValueError(
                "La clé Anthropic ne supporte pas la conversion PDF. "
                "Utilisez une clé Gemini pour cette fonction."
            )
        yield from _stream_anthropic(prompt, system, key)
    else:
        yield from _stream_gemini(prompt, system, images or [], key)


def _is_anthropic_key(key: str) -> bool:
    return key.startswith("sk-ant-")


def _parse_retry_delay(exc_str: str) -> str | None:
    """Extrait le délai de retry depuis un message d'erreur Google (ex: '34s')."""
    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+)s", exc_str)
    if m:
        secs = int(m.group(1))
        return f"{secs // 60} min {secs % 60} s" if secs >= 60 else f"{secs} s"
    return None


def _stream_gemini(
    prompt: str,
    system: str,
    images: list[bytes],
    api_key: str,
) -> Generator[str, None, None]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    contents: list = []
    for img_bytes in images:
        contents.append(
            types.Part.from_bytes(data=img_bytes, mime_type="image/png")
        )
    contents.append(prompt)

    config = types.GenerateContentConfig(system_instruction=system)

    try:
        for chunk in client.models.generate_content_stream(
            model=GEMINI_MODEL,
            contents=contents,
            config=config,
        ):
            if chunk.text:
                yield chunk.text
    except Exception as exc:
        exc_str = str(exc)
        if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str or "quota" in exc_str.lower():
            delay = _parse_retry_delay(exc_str)
            retry_hint = f" Réessayez dans {delay}." if delay else " Réessayez dans quelques minutes."
            raise RuntimeError(
                f"Quota Gemini épuisé ({GEMINI_MODEL}).{retry_hint} "
                "Pour ne plus avoir cette limite, ajoutez votre propre clé dans ⚙️ Paramètres."
            ) from None
        raise


def _stream_anthropic(
    prompt: str,
    system: str,
    api_key: str,
) -> Generator[str, None, None]:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    with client.messages.stream(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text


# ---------------------------------------------------------------------------
# Chat IA éditeur — réponse JSON non-streaming
# ---------------------------------------------------------------------------

_SYSTEM_EDITOR_CHAT = (
    "Tu es un assistant expert en rédaction de CV et lettres de motivation.\n"
    "Tu reçois le HTML et CSS actuels du document, ainsi qu'une demande de l'utilisateur.\n\n"
    "RÈGLES ABSOLUES — NE JAMAIS ENFREINDRE :\n"
    "1. Ne FABRIQUE JAMAIS d'informations absentes du document : pas d'expérience inventée,\n"
    "   pas de diplôme fictif, pas de date approximée, pas de métrique inventée.\n"
    "2. PRÉSERVE tous les faits existants : noms, dates, diplômes, compétences, langues.\n"
    "3. Tu peux : réécrire, reformuler, réorganiser, améliorer le style, corriger l'orthographe.\n\n"
    "FORMAT DE RÉPONSE OBLIGATOIRE — JSON PUR, RIEN D'AUTRE :\n"
    '{"reply":"Message court (1-3 phrases)","proposals":[{"id":"p1","title":"Titre court",'
    '"summary":"Ce qui change (1-2 phrases)","html":"HTML COMPLET","css":"CSS COMPLET ou \'\'"}]}\n\n'
    "CONTRAINTES :\n"
    "- Maximum 2 propositions (sauf demande explicite).\n"
    "- Si aucun changement utile n'est possible sans inventer du contenu, proposals=[] et explique dans reply.\n"
    "- 'html' = document HTML COMPLET (pas un extrait).\n"
    "- 'css' = CSS COMPLET si modifié, ou chaîne vide '' si inchangé.\n"
    "- JSON PUR : aucune balise markdown, aucun ```json, aucun texte avant ou après le JSON."
)


def _complete_gemini(messages: list[dict], system: str, api_key: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=90))

    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(
            role=role,
            parts=[types.Part.from_text(text=str(msg["content"]))],
        ))

    config = types.GenerateContentConfig(system_instruction=system)

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=config,
        )
        return response.text or ""
    except Exception as exc:
        exc_str = str(exc)
        if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str or "quota" in exc_str.lower():
            delay = _parse_retry_delay(exc_str)
            retry_hint = f" Réessayez dans {delay}." if delay else " Réessayez dans quelques minutes."
            raise RuntimeError(
                f"Quota Gemini épuisé ({GEMINI_MODEL}).{retry_hint} "
                "Pour ne plus avoir cette limite, ajoutez votre propre clé dans ⚙️ Paramètres."
            ) from None
        raise


def _complete_anthropic(messages: list[dict], system: str, api_key: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        system=system,
        messages=messages,
    )
    return response.content[0].text if response.content else ""


def complete_chat(
    messages: list[dict],
    html: str,
    css: str,
    doc_type: str = "CV",
    job_desc: str = "",
    active_tab: str = "html",
    api_key: str | None = None,
) -> dict:
    """Appelle l'IA en mode non-streaming et retourne {"reply": str, "proposals": list}.

    Raises:
        ValueError: clé manquante, JSON invalide, ou structure incorrecte.
        RuntimeError: quota épuisé.
    """
    import json as _json

    key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ValueError(
            "Aucune clé API configurée. "
            "Ajoutez GEMINI_API_KEY dans les variables d'environnement "
            "ou une clé personnelle dans ⚙️ Paramètres."
        )

    context = f"Document actuel ({doc_type}) :\n\nHTML :\n{html}"
    if css:
        context += f"\n\nCSS :\n{css}"
    if job_desc:
        context += f"\n\nOffre d'emploi cible :\n{job_desc}"

    # Contexte injecté en tête comme premier échange user/assistant
    augmented = [
        {"role": "user",      "content": context},
        {"role": "assistant", "content": "Contexte reçu. Que souhaitez-vous modifier ?"},
    ] + list(messages)

    if _is_anthropic_key(key):
        raw = _complete_anthropic(augmented, _SYSTEM_EDITOR_CHAT, key)
    else:
        raw = _complete_gemini(augmented, _SYSTEM_EDITOR_CHAT, key)

    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw.strip())
        raw = raw.strip()

    try:
        result = _json.loads(raw)
    except _json.JSONDecodeError as exc:
        raise ValueError(f"Réponse IA invalide (JSON malformé) : {exc}") from None

    if not isinstance(result, dict) or "reply" not in result or "proposals" not in result:
        raise ValueError("Réponse IA invalide : champs 'reply' et 'proposals' attendus.")

    proposals = []
    for p in result.get("proposals", []):
        if not isinstance(p, dict):
            continue
        p_html = str(p.get("html", "")).strip()
        p_css  = str(p.get("css",  "")).strip()
        if p_html == html.strip() and p_css == css.strip():
            continue
        proposals.append({
            "id":      str(p.get("id", f"p{len(proposals) + 1}")),
            "title":   str(p.get("title",   "Proposition"))[:100],
            "summary": str(p.get("summary", ""))[:500],
            "html":    p_html,
            "css":     p_css,
        })

    return {
        "reply":     str(result.get("reply", ""))[:1000],
        "proposals": proposals,
    }
