# -*- coding: utf-8 -*-
"""Автобан по запрещённым никам/именам при входе и смене ника.

Владелец: «АртемаВавилова» именно так + английский вариант.
Сравнение без регистра, пробелов, `_` `.` `-`.
"""
from __future__ import annotations

import re
import unicodedata

# Канонические запрещённые имена (после нормализации).
# RU: АртемаВавилова; EN: ArtemaVavilova / ArtyomaVavilova.
_BANNED_CANON = frozenset({
    'артемававилова',
    'artemavavilova',
    'artyomavavilova',
    'artemvavilova',
    'artyomvavilova',
})

_STRIP_RE = re.compile(r'[\s_\.\-·•]+', re.UNICODE)


def normalize_name(value: str) -> str:
    """Сжать имя к сравнимому виду: NFKC, lower, без пробелов/разделителей."""
    if not value:
        return ''
    s = unicodedata.normalize('NFKC', str(value))
    s = s.casefold()
    s = _STRIP_RE.sub('', s)
    return s


def is_banned_name(*names: str) -> bool:
    """True, если любое из имён совпадает с запрещённым списком."""
    for raw in names:
        n = normalize_name(raw)
        if n and n in _BANNED_CANON:
            return True
    return False


def member_banned_identity(member) -> str | None:
    """Вернуть совпавшее сырое имя или None."""
    candidates = [
        getattr(member, 'nick', None),
        getattr(member, 'display_name', None),
        getattr(member, 'global_name', None),
        getattr(member, 'name', None),
    ]
    user = getattr(member, '_user', None) or getattr(member, 'user', None)
    if user is not None:
        candidates.extend([
            getattr(user, 'global_name', None),
            getattr(user, 'name', None),
        ])
    for raw in candidates:
        if not raw:
            continue
        if normalize_name(raw) in _BANNED_CANON:
            return str(raw)
    return None


BAN_REASON = 'Автобан: запрещённое имя (АртемаВавилова / ArtemaVavilova)'
