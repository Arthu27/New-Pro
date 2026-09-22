# -*- coding: utf-8 -*-
"""Пакет логики бота Мафии."""
from services.mafia.game import Game, PHASE_CONFIRM, PHASE_ENDED, PHASE_LOBBY, PHASE_PLAYING, PHASE_READY
from services.mafia.roles import ROLES, preset_for_count, preset_summary
from services.mafia.store import STORE

__all__ = [
    'Game', 'STORE', 'ROLES', 'preset_for_count', 'preset_summary',
    'PHASE_LOBBY', 'PHASE_CONFIRM', 'PHASE_READY', 'PHASE_PLAYING', 'PHASE_ENDED',
]
