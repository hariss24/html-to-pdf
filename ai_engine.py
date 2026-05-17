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
