# -*- coding: utf-8 -*-
"""Общие цвета и эмодзи Staff Manager (не билдер экранов)."""
from __future__ import annotations

BLACK = 0x000000
MIRROR_BLACK = 0x0A0A0C
GOLD = 0xF0CD7A
PROMOTE = 0xF0CD7A
DEMOTE = 0xE67E22
REMOVE = 0xE74C3C
ASSIGN = 0x2ECC71
TRANSFER = 0x9B59B6
VACATION = 0x1ABC9C
HISTORY = 0x5865F2
REQUEST = 0x3498DB
CONSENT = 0x9B59B6
FAILED = 0x992D22
PARTIAL = 0xE67E22

ACTION_ICONS = {
    'assign': '🟢',
    'promote': '⬆',
    'demote': '⬇',
    'remove': '🔴',
    'transfer': '🟣',
    'vacation': '🏝',
    'vacation_end': '🏝',
    'probation': '🕘',
    'undo': '↩',
    'manual': '✋',
    'request': '🎫',
    'self_leave': '🔴',
}

STATUS_ICONS = {
    'ok': '✅',
    'done': '✅',
    'undone': '↩',
    'failed': '❌',
    'partial': '⚠',
    'pending': '⏳',
}

ACTION_COLORS = {
    'promote': PROMOTE,
    'demote': DEMOTE,
    'remove': REMOVE,
    'assign': ASSIGN,
    'transfer': TRANSFER,
    'self_leave': REMOVE,
    'vacation': VACATION,
    'history': HISTORY,
    'request': REQUEST,
    'probation': HISTORY,
}
