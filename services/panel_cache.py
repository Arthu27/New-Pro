# -*- coding: utf-8 -*-
"""Оперативный in-memory кэш панели (TTL).

Инвалидация: invalidate('warns') / invalidate_all() после действий.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

_LOCK = threading.RLock()
_STORE: dict[str, tuple[float, Any]] = {}


def _ttl() -> float:
    try:
        from services.warn_config import panel_cache_ttl_sec
        return float(panel_cache_ttl_sec())
    except Exception:
        return 45.0


def get(key: str) -> Optional[Any]:
    now = time.monotonic()
    with _LOCK:
        item = _STORE.get(key)
        if not item:
            return None
        exp, val = item
        if exp < now:
            _STORE.pop(key, None)
            return None
        return val


def set(key: str, value: Any, ttl: float | None = None) -> None:
    t = float(ttl if ttl is not None else _ttl())
    with _LOCK:
        _STORE[key] = (time.monotonic() + t, value)


def invalidate(prefix: str = '') -> None:
    with _LOCK:
        if not prefix:
            _STORE.clear()
            return
        dead = [k for k in _STORE if k == prefix or k.startswith(prefix + ':')]
        for k in dead:
            _STORE.pop(k, None)


def invalidate_all() -> None:
    invalidate('')
