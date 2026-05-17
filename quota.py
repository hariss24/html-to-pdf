"""Compteur journalier d'utilisation de la clé API serveur."""
import os
import threading
from datetime import date as _date

_state: dict = {"date": "", "count": 0}
_lock = threading.Lock()
DAILY_LIMIT: int = int(os.environ.get("DAILY_QUOTA", "50"))


def check_and_increment() -> bool:
    """Vérifie si le quota est disponible et l'incrémente si oui.

    Returns True si l'appel est autorisé, False si le quota est épuisé.
    Le compteur se remet à zéro automatiquement chaque nouveau jour.
    Thread-safe.
    """
    with _lock:
        today = str(_date.today())
        if _state["date"] != today:
            _state["date"] = today
            _state["count"] = 0
        if _state["count"] >= DAILY_LIMIT:
            return False
        _state["count"] += 1
        return True


def remaining() -> int:
    """Retourne le nombre de requêtes restantes aujourd'hui."""
    with _lock:
        today = str(_date.today())
        if _state["date"] != today:
            return DAILY_LIMIT
        return max(0, DAILY_LIMIT - _state["count"])
