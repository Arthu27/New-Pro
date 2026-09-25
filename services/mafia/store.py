# -*- coding: utf-8 -*-
"""Персистентность партий мафии на диск."""
from __future__ import annotations

import os
from typing import Dict, Optional

from json_store import load_json, save_json
from logger import get_logger
from services.mafia.game import Game

log = get_logger('mafia.store')
DATA_DIR = 'data'


def _path(guild_id: int) -> str:
    return os.path.join(DATA_DIR, f'mafia_{int(guild_id)}.json')


def load_guild(guild_id: int) -> dict:
    return load_json(_path(guild_id), {'active': None, 'history': []}, log=log)


def save_guild(guild_id: int, payload: dict) -> None:
    save_json(_path(guild_id), payload, log=log)


class GameStore:
    """Активные игры в памяти + снимок на диск."""

    def __init__(self):
        self._by_guild: Dict[int, Game] = {}

    def get(self, guild_id: int) -> Optional[Game]:
        return self._by_guild.get(int(guild_id))

    def set(self, game: Game) -> None:
        self._by_guild[int(game.guild_id)] = game
        self.persist(game)

    def clear(self, guild_id: int, archive: bool = True) -> None:
        g = self._by_guild.pop(int(guild_id), None)
        payload = load_guild(guild_id)
        if archive and g is not None:
            hist = list(payload.get('history') or [])
            hist.append(g.to_dict())
            payload['history'] = hist[-30:]
        payload['active'] = None
        save_guild(guild_id, payload)

    def persist(self, game: Game) -> None:
        payload = load_guild(game.guild_id)
        payload['active'] = game.to_dict()
        save_guild(game.guild_id, payload)

    def restore_all(self) -> int:
        """Поднять активные игры после рестарта."""
        n = 0
        if not os.path.isdir(DATA_DIR):
            return 0
        for name in os.listdir(DATA_DIR):
            if not (name.startswith('mafia_') and name.endswith('.json')):
                continue
            try:
                gid = int(name[len('mafia_'):-len('.json')])
            except ValueError:
                continue
            payload = load_guild(gid)
            active = payload.get('active')
            if not active:
                continue
            try:
                game = Game.from_dict(active)
                if game.phase == 'ended':
                    continue
                self._by_guild[gid] = game
                n += 1
            except Exception as e:
                log.warning('mafia restore %s: %s', name, e)
        return n


STORE = GameStore()
