import importlib
import pytest


def _fresh(limit=3):
    import quota
    importlib.reload(quota)
    quota._state["date"] = ""
    quota._state["count"] = 0
    quota.DAILY_LIMIT = limit
    return quota


def test_allows_requests_up_to_limit():
    q = _fresh(3)
    assert q.check_and_increment() is True
    assert q.check_and_increment() is True
    assert q.check_and_increment() is True


def test_blocks_after_limit_reached():
    q = _fresh(3)
    q.check_and_increment()
    q.check_and_increment()
    q.check_and_increment()
    assert q.check_and_increment() is False


def test_resets_on_new_day():
    q = _fresh(1)
    q._state["date"] = "1999-01-01"
    q._state["count"] = 1
    # Un nouveau jour → reset → doit autoriser
    assert q.check_and_increment() is True


def test_remaining_decrements():
    q = _fresh(5)
    assert q.remaining() == 5
    q.check_and_increment()
    assert q.remaining() == 4


def test_remaining_on_new_day_returns_full_limit():
    q = _fresh(5)
    q._state["date"] = "1999-01-01"
    q._state["count"] = 5
    assert q.remaining() == 5
