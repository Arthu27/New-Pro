# -*- coding: utf-8 -*-
"""Состояние одной партии мафии (чистая логика без Discord)."""
from __future__ import annotations

import random
import time
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from services.mafia.roles import (
    ROLES,
    check_result_for_don,
    check_result_for_sheriff,
    expand_roles,
    is_mafia_team,
    preset_for_count,
)


PHASE_LOBBY = 'lobby'
PHASE_CONFIRM = 'confirm'
PHASE_READY = 'ready'
PHASE_PLAYING = 'playing'
PHASE_ENDED = 'ended'


@dataclass
class Player:
    user_id: int
    display_name: str
    role: Optional[str] = None
    confirmed: bool = False
    alive: bool = True
    dm_ok: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'Player':
        return cls(
            user_id=int(d['user_id']),
            display_name=str(d.get('display_name') or d['user_id']),
            role=d.get('role'),
            confirmed=bool(d.get('confirmed', False)),
            alive=bool(d.get('alive', True)),
            dm_ok=bool(d.get('dm_ok', True)),
        )


@dataclass
class Game:
    game_id: str
    guild_id: int
    host_id: int
    voice_channel_id: int
    text_channel_id: int
    phase: str = PHASE_LOBBY
    players: Dict[int, Player] = field(default_factory=dict)
    deal_token: str = ''  # инвалидирует старые DM при перераздаче
    host_summary_channel_id: Optional[int] = None
    host_summary_message_id: Optional[int] = None
    lobby_message_id: Optional[int] = None
    winner: Optional[str] = None  # 'town' | 'mafia'
    log: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    sheriff_checks: List[dict] = field(default_factory=list)
    don_checks: List[dict] = field(default_factory=list)

    # ── helpers ──────────────────────────────────────────────
    def alive_players(self) -> List[Player]:
        return [p for p in self.players.values() if p.alive]

    def alive_mafia(self) -> List[Player]:
        return [p for p in self.alive_players() if p.role and is_mafia_team(p.role)]

    def alive_town(self) -> List[Player]:
        return [p for p in self.alive_players() if p.role and not is_mafia_team(p.role)]

    def confirmed_count(self) -> int:
        return sum(1 for p in self.players.values() if p.confirmed)

    def all_confirmed(self) -> bool:
        return bool(self.players) and all(p.confirmed for p in self.players.values())

    def unconfirmed(self) -> List[Player]:
        return [p for p in self.players.values() if not p.confirmed]

    def add_event(self, text: str) -> None:
        ts = time.strftime('%H:%M:%S', time.localtime())
        self.log.append(f'`{ts}` {text}')
        if len(self.log) > 80:
            self.log = self.log[-80:]

    # ── lifecycle ────────────────────────────────────────────
    @classmethod
    def create(
        cls,
        guild_id: int,
        host_id: int,
        voice_channel_id: int,
        text_channel_id: int,
        members: List[tuple],
    ) -> 'Game':
        """members: list[(user_id, display_name)] без ведущего."""
        gid = uuid.uuid4().hex[:6].upper()
        g = cls(
            game_id=gid,
            guild_id=int(guild_id),
            host_id=int(host_id),
            voice_channel_id=int(voice_channel_id),
            text_channel_id=int(text_channel_id),
            phase=PHASE_LOBBY,
        )
        for uid, name in members:
            if int(uid) == int(host_id):
                continue
            g.players[int(uid)] = Player(user_id=int(uid), display_name=str(name))
        g.add_event(f'Лобби создано · игроков: **{len(g.players)}**')
        return g

    def set_players_from_voice(self, members: List[tuple]) -> None:
        """Обновить список из войса (до раздачи)."""
        if self.phase not in (PHASE_LOBBY,):
            raise RuntimeError('Состав можно менять только в лобби')
        new: Dict[int, Player] = {}
        for uid, name in members:
            if int(uid) == self.host_id:
                continue
            uid = int(uid)
            if uid in self.players:
                p = self.players[uid]
                p.display_name = str(name)
                new[uid] = p
            else:
                new[uid] = Player(user_id=uid, display_name=str(name))
        self.players = new
        self.add_event(f'Состав обновлён из войса · **{len(self.players)}**')

    def set_players_from_ids(self, members: List[tuple]) -> None:
        """Состав из списка [(uid, name), ...] — только для тестов/ручного add."""
        self.set_players_from_voice(members)

    def deal(self, rng: random.Random | None = None) -> Dict[str, int]:
        if len(self.players) < 6:
            raise RuntimeError('Нужно минимум 6 игроков')
        if self.phase in (PHASE_PLAYING, PHASE_ENDED):
            raise RuntimeError('Игра уже идёт или завершена')
        rng = rng or random.Random()
        counts = preset_for_count(len(self.players))
        bag = expand_roles(counts)
        if len(bag) != len(self.players):
            raise RuntimeError('Пресет не совпал с числом игроков')
        rng.shuffle(bag)
        self.deal_token = uuid.uuid4().hex
        for player, role in zip(self.players.values(), bag):
            player.role = role
            player.confirmed = False
            player.alive = True
            player.dm_ok = True
        self.phase = PHASE_CONFIRM
        self.winner = None
        self.started_at = None
        self.ended_at = None
        self.add_event(f'Роли разданы (токен `{self.deal_token[:6]}`)')
        return counts

    def confirm(self, user_id: int, deal_token: str) -> bool:
        """True если впервые подтвердил. False если уже было / чужой токен."""
        if deal_token != self.deal_token:
            raise RuntimeError('Эта раздача уже недействительна')
        if self.phase not in (PHASE_CONFIRM, PHASE_READY):
            raise RuntimeError('Сейчас нельзя подтверждать')
        p = self.players.get(int(user_id))
        if not p:
            raise RuntimeError('Вас нет в этой игре')
        if p.confirmed:
            return False
        p.confirmed = True
        self.add_event(f'✅ {p.display_name} подтвердил')
        if self.all_confirmed():
            self.phase = PHASE_READY
            self.add_event('Все подтвердили — можно начинать')
        return True

    def mark_dm_failed(self, user_id: int) -> None:
        p = self.players.get(int(user_id))
        if p:
            p.dm_ok = False

    def exclude_player(self, user_id: int) -> Player:
        if self.phase in (PHASE_PLAYING, PHASE_ENDED):
            raise RuntimeError('Во время игры исключайте через голосование/убийство')
        p = self.players.pop(int(user_id), None)
        if not p:
            raise RuntimeError('Игрок не найден')
        self.add_event(f'Исключён из состава: {p.display_name}')
        if self.phase in (PHASE_CONFIRM, PHASE_READY):
            # роли больше не валидны — ведущий должен перераздать
            self.phase = PHASE_LOBBY
            for pl in self.players.values():
                pl.role = None
                pl.confirmed = False
            self.deal_token = ''
            self.add_event('Состав изменился — нужна новая раздача')
        return p

    def add_player(self, user_id: int, display_name: str) -> Player:
        if self.phase not in (PHASE_LOBBY, PHASE_CONFIRM, PHASE_READY):
            raise RuntimeError('Нельзя добавить игрока сейчас')
        uid = int(user_id)
        if uid == self.host_id:
            raise RuntimeError('Ведущий не участвует')
        if uid in self.players:
            raise RuntimeError('Игрок уже в составе')
        p = Player(user_id=uid, display_name=str(display_name))
        self.players[uid] = p
        self.add_event(f'Добавлен: {p.display_name}')
        if self.phase in (PHASE_CONFIRM, PHASE_READY):
            self.phase = PHASE_LOBBY
            for pl in self.players.values():
                pl.role = None
                pl.confirmed = False
            self.deal_token = ''
            self.add_event('Состав изменился — нужна новая раздача')
        return p

    def cancel(self) -> None:
        self.phase = PHASE_ENDED
        self.ended_at = time.time()
        self.deal_token = ''
        self.add_event('Игра отменена ведущим')

    def start(self) -> None:
        if not self.all_confirmed():
            raise RuntimeError('Не все подтвердили участие')
        if self.phase not in (PHASE_READY, PHASE_CONFIRM):
            raise RuntimeError('Нельзя начать сейчас')
        if not all(p.role for p in self.players.values()):
            raise RuntimeError('Роли не разданы')
        self.phase = PHASE_PLAYING
        self.started_at = time.time()
        self.add_event('🎮 Игра началась — состав зафиксирован')

    def _check_win(self) -> Optional[str]:
        mafia_n = len(self.alive_mafia())
        town_n = len(self.alive_town())
        if mafia_n == 0:
            return 'town'
        if mafia_n > 0 and mafia_n >= town_n:
            return 'mafia'
        return None

    def _finish_if_won(self) -> Optional[str]:
        w = self._check_win()
        if w:
            self.winner = w
            self.phase = PHASE_ENDED
            self.ended_at = time.time()
            label = 'мирный город' if w == 'town' else 'мафия'
            self.add_event(f'🏁 Победа: **{label}**')
        return w

    def kill(self, user_id: int, by: str = 'мафия') -> Player:
        if self.phase != PHASE_PLAYING:
            raise RuntimeError('Игра не идёт')
        p = self.players.get(int(user_id))
        if not p or not p.alive:
            raise RuntimeError('Игрок не найден или уже вне игры')
        p.alive = False
        role = ROLES.get(p.role).label if p.role and p.role in ROLES else '?'
        self.add_event(f'💀 {p.display_name} убит ({by}) · был {role}')
        self._finish_if_won()
        return p

    def vote_out(self, user_id: int) -> Player:
        return self.kill(user_id, by='голосованием')

    def sheriff_check(self, target_id: int) -> dict:
        if self.phase != PHASE_PLAYING:
            raise RuntimeError('Игра не идёт')
        p = self.players.get(int(target_id))
        if not p or not p.alive or not p.role:
            raise RuntimeError('Цель недоступна')
        short, detail = check_result_for_sheriff(p.role)
        rec = {
            'target_id': p.user_id,
            'target_name': p.display_name,
            'role': p.role,
            'result': short,
            'detail': detail,
            'at': time.time(),
        }
        self.sheriff_checks.append(rec)
        self.add_event(f'🕵️ Шериф проверил {p.display_name}: {short}')
        return rec

    def don_check(self, target_id: int) -> dict:
        if self.phase != PHASE_PLAYING:
            raise RuntimeError('Игра не идёт')
        p = self.players.get(int(target_id))
        if not p or not p.alive or not p.role:
            raise RuntimeError('Цель недоступна')
        short, detail = check_result_for_don(p.role)
        rec = {
            'target_id': p.user_id,
            'target_name': p.display_name,
            'role': p.role,
            'result': short,
            'detail': detail,
            'at': time.time(),
        }
        self.don_checks.append(rec)
        self.add_event(f'👑 Дон проверил {p.display_name}: {short}')
        return rec

    def to_dict(self) -> dict:
        return {
            'game_id': self.game_id,
            'guild_id': self.guild_id,
            'host_id': self.host_id,
            'voice_channel_id': self.voice_channel_id,
            'text_channel_id': self.text_channel_id,
            'phase': self.phase,
            'players': {str(k): v.to_dict() for k, v in self.players.items()},
            'deal_token': self.deal_token,
            'host_summary_channel_id': self.host_summary_channel_id,
            'host_summary_message_id': self.host_summary_message_id,
            'lobby_message_id': self.lobby_message_id,
            'winner': self.winner,
            'log': list(self.log),
            'created_at': self.created_at,
            'started_at': self.started_at,
            'ended_at': self.ended_at,
            'sheriff_checks': list(self.sheriff_checks),
            'don_checks': list(self.don_checks),
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Game':
        players = {
            int(k): Player.from_dict(v)
            for k, v in (d.get('players') or {}).items()
        }
        return cls(
            game_id=str(d['game_id']),
            guild_id=int(d['guild_id']),
            host_id=int(d['host_id']),
            voice_channel_id=int(d['voice_channel_id']),
            text_channel_id=int(d['text_channel_id']),
            phase=str(d.get('phase') or PHASE_LOBBY),
            players=players,
            deal_token=str(d.get('deal_token') or ''),
            host_summary_channel_id=d.get('host_summary_channel_id'),
            host_summary_message_id=d.get('host_summary_message_id'),
            lobby_message_id=d.get('lobby_message_id'),
            winner=d.get('winner'),
            log=list(d.get('log') or []),
            created_at=float(d.get('created_at') or time.time()),
            started_at=d.get('started_at'),
            ended_at=d.get('ended_at'),
            sheriff_checks=list(d.get('sheriff_checks') or []),
            don_checks=list(d.get('don_checks') or []),
        )
