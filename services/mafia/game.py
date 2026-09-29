# -*- coding: utf-8 -*-
"""Состояние одной партии мафии (чистая логика без Discord).

Авто-цикл: старт → ночь (действия в ЛС) → день → голосование → ночь…
Ведущий не кликает «убийство/шериф/дон» — роли ходят сами.
"""
from __future__ import annotations

import random
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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

CYCLE_NONE = ''
CYCLE_NIGHT = 'night'
CYCLE_DAY = 'day'
CYCLE_VOTE = 'vote'


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
    deal_token: str = ''
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
    # авто-цикл
    day_number: int = 0
    cycle: str = CYCLE_NONE
    # actor_id -> {'kind': kill|heal|block|sheriff|don|skip, 'target_id': int|None}
    night_actions: Dict[int, dict] = field(default_factory=dict)
    # очередь ночи: [{step, actors:[uid], kind}] — шериф не раньше мафии/доктора
    night_queue: List[dict] = field(default_factory=list)
    night_step: int = 0
    # voter_id -> target_id (0 = воздержался)
    votes: Dict[int, int] = field(default_factory=dict)
    # голосование по очереди
    vote_order: List[int] = field(default_factory=list)
    vote_index: int = 0
    last_night_report: str = ''
    last_vote_report: str = ''
    # публичные msg id для очистки в конце
    public_message_ids: List[int] = field(default_factory=list)

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

    def cycle_label(self) -> str:
        if self.phase != PHASE_PLAYING:
            return ''
        if self.cycle == CYCLE_NIGHT:
            return f'Ночь {self.day_number}'
        if self.cycle == CYCLE_DAY:
            return f'День {self.day_number}'
        if self.cycle == CYCLE_VOTE:
            return f'Голосование · день {self.day_number}'
        return 'Игра'

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
        self.day_number = 0
        self.cycle = CYCLE_NONE
        self.night_actions = {}
        self.night_queue = []
        self.night_step = 0
        self.votes = {}
        self.vote_order = []
        self.vote_index = 0
        self.last_night_report = ''
        self.last_vote_report = ''
        self.add_event(f'Роли разданы (токен `{self.deal_token[:6]}`)')
        return counts

    def confirm(self, user_id: int, deal_token: str) -> bool:
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
            self.phase = PHASE_LOBBY
            for pl in self.players.values():
                pl.role = None
                pl.confirmed = False
            self.deal_token = ''
            self.add_event('Состав изменился — нужна новая раздача')
        return p

    def leave_player(self, user_id: int) -> Player:
        if self.phase != PHASE_LOBBY:
            raise RuntimeError('Выйти можно только пока идёт набор')
        uid = int(user_id)
        p = self.players.pop(uid, None)
        if p is None:
            raise RuntimeError('Вас нет в составе')
        self.add_event(f'Вышел: {p.display_name}')
        return p

    def add_player(self, user_id: int, display_name: str, *,
                   allow_reset: bool = False) -> Player:
        if self.phase == PHASE_LOBBY:
            pass
        elif allow_reset and self.phase in (PHASE_CONFIRM, PHASE_READY):
            pass
        else:
            raise RuntimeError('Набор закрыт — нельзя записаться')
        uid = int(user_id)
        if uid == self.host_id:
            raise RuntimeError('Ведущий не участвует')
        if uid in self.players:
            raise RuntimeError('Вы уже в составе')
        p = Player(user_id=uid, display_name=str(display_name))
        self.players[uid] = p
        self.add_event(f'Записался: {p.display_name}')
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
        self.cycle = CYCLE_NONE
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
        self.begin_night()

    def begin_night(self) -> None:
        """Город засыпает · ночные действия по очереди."""
        if self.phase != PHASE_PLAYING:
            raise RuntimeError('Игра не идёт')
        self.day_number = int(self.day_number or 0) + 1
        self.cycle = CYCLE_NIGHT
        self.night_actions = {}
        self.votes = {}
        self.vote_order = []
        self.vote_index = 0
        self.last_night_report = ''
        self.night_queue = self._build_night_queue()
        self.night_step = 0
        self.add_event(f'🌙 Ночь {self.day_number} · город засыпает')

    def begin_day(self) -> None:
        if self.phase != PHASE_PLAYING:
            raise RuntimeError('Игра не идёт')
        self.cycle = CYCLE_DAY
        self.votes = {}
        self.vote_order = []
        self.vote_index = 0
        self.add_event(f'☀️ День {self.day_number} · город просыпается')

    def begin_vote(self) -> None:
        if self.phase != PHASE_PLAYING:
            raise RuntimeError('Игра не идёт')
        if self.cycle not in (CYCLE_DAY, CYCLE_VOTE):
            raise RuntimeError('Голосование только днём')
        self.cycle = CYCLE_VOTE
        self.votes = {}
        self.last_vote_report = ''
        # живые по порядку стола — голосуют по одному
        self.vote_order = [p.user_id for p in self.alive_players()]
        self.vote_index = 0
        self.add_event(f'🗳️ Голосование · день {self.day_number} · по очереди')

    def _build_night_queue(self) -> List[dict]:
        """Очередь ночи: путана → мафия → доктор → шериф → дон-проверка.

        Шериф не получает ход раньше мафии/доктора.
        """
        alive = {p.user_id: p for p in self.alive_players()}
        q: List[dict] = []

        def _uids(*roles: str) -> List[int]:
            return [uid for uid, p in alive.items() if p.role in roles]

        block = _uids('courtesan')
        if block:
            q.append({'step': 'block', 'kind': 'block', 'actors': block,
                      'label': 'Путана'})
        kill = _uids('mafia', 'don')
        if kill:
            q.append({'step': 'kill', 'kind': 'kill', 'actors': kill,
                      'label': 'Мафия'})
        heal = _uids('doctor')
        if heal:
            q.append({'step': 'heal', 'kind': 'heal', 'actors': heal,
                      'label': 'Доктор'})
        sher = _uids('sheriff')
        if sher:
            q.append({'step': 'sheriff', 'kind': 'sheriff', 'actors': sher,
                      'label': 'Шериф'})
        dons = _uids('don')
        if dons:
            q.append({'step': 'don_check', 'kind': 'don', 'actors': dons,
                      'label': 'Дон · проверка', 'optional': True})
        return q

    def current_night_step(self) -> Optional[dict]:
        if self.cycle != CYCLE_NIGHT or not self.night_queue:
            return None
        if self.night_step < 0 or self.night_step >= len(self.night_queue):
            return None
        return self.night_queue[self.night_step]

    def night_step_label(self) -> str:
        step = self.current_night_step()
        if not step:
            return 'ночь готова'
        return f'{self.night_step + 1}/{len(self.night_queue)} · {step.get("label", "?")}'

    def night_actors_needed(self) -> List[Player]:
        """Все, кто ходит ночью (для сводки)."""
        keys = {'mafia', 'don', 'sheriff', 'doctor', 'courtesan'}
        return [p for p in self.alive_players() if p.role in keys]

    def _actor_night_done(self, p: Player, *, for_kind: str = None) -> bool:
        a = self.night_actions.get(int(p.user_id))
        if not a:
            return False
        if for_kind == 'don' or (for_kind is None and False):
            return bool(a.get('don_check')) or a.get('kind') == 'don'
        if for_kind == 'kill' and p.role == 'don':
            return a.get('kind') in ('kill', 'skip') or bool(a.get('kill_done'))
        if p.role == 'don' and for_kind is None:
            return a.get('kind') in ('kill', 'skip') or bool(a.get('kill_done'))
        return True

    def step_actors_pending(self) -> List[Player]:
        """Кто ещё не сходил на текущем шаге очереди."""
        step = self.current_night_step()
        if not step:
            return []
        kind = step.get('kind')
        out = []
        for uid in step.get('actors') or []:
            p = self.players.get(int(uid))
            if not p or not p.alive:
                continue
            a = self.night_actions.get(int(uid)) or {}
            if kind == 'don':
                if not a.get('don_check'):
                    out.append(p)
            elif kind == 'kill':
                if not (a.get('kind') in ('kill', 'skip') or a.get('kill_done')):
                    out.append(p)
            else:
                # heal / block / sheriff
                if a.get('kind') not in (kind, 'skip'):
                    out.append(p)
        return out

    def night_pending(self) -> List[Player]:
        return self.step_actors_pending()

    def night_step_ready(self) -> bool:
        step = self.current_night_step()
        if step is None:
            return True
        return not self.step_actors_pending()

    def advance_night_step(self) -> bool:
        """Перейти к следующему шагу очереди. True если ночь ещё идёт."""
        if not self.night_queue:
            return False
        self.night_step += 1
        while self.night_step < len(self.night_queue):
            step = self.night_queue[self.night_step]
            # пропуск пустых (все мертвы)
            actors = [uid for uid in (step.get('actors') or [])
                      if (self.players.get(int(uid)) or Player(0, '')).alive]
            if actors:
                step['actors'] = actors
                self.add_event(f'🌙 Ход: {step.get("label")}')
                return True
            self.night_step += 1
        return False

    def night_ready(self) -> bool:
        """Очередь ночи пройдена (все шаги)."""
        if not self.night_queue:
            return True
        return self.night_step >= len(self.night_queue)

    def track_public_message(self, message_id: int) -> None:
        mid = int(message_id or 0)
        if not mid:
            return
        ids = list(self.public_message_ids or [])
        if mid not in ids:
            ids.append(mid)
        self.public_message_ids = ids[-80:]

    def current_voter_id(self) -> Optional[int]:
        if self.cycle != CYCLE_VOTE or not self.vote_order:
            return None
        if self.vote_index < 0 or self.vote_index >= len(self.vote_order):
            return None
        return int(self.vote_order[self.vote_index])

    def vote_turn_label(self) -> str:
        if not self.vote_order:
            return ''
        cur = self.vote_index + 1
        total = len(self.vote_order)
        vid = self.current_voter_id()
        name = ''
        if vid and vid in self.players:
            name = f' · {self.players[vid].display_name}'
        return f'{cur}/{total}{name}'

    def submit_night_action(self, actor_id: int, kind: str,
                            target_id: Optional[int] = None) -> dict:
        if self.phase != PHASE_PLAYING or self.cycle != CYCLE_NIGHT:
            raise RuntimeError('Сейчас не ночь')
        actor = self.players.get(int(actor_id))
        if not actor or not actor.alive or not actor.role:
            raise RuntimeError('Вы вне игры')
        # только текущий шаг очереди
        step = self.current_night_step()
        if step is None:
            raise RuntimeError('Ночные ходы уже закончены')
        if int(actor_id) not in [int(x) for x in (step.get('actors') or [])]:
            raise RuntimeError(
                f'Сейчас ход: **{step.get("label")}** · ваш ход позже')
        want = step.get('kind')
        kind = (kind or '').strip().lower()
        role = actor.role
        # на шаге kill дон/мафия шлют kill|skip; на don_check — don|skip
        if want == 'don':
            if kind == 'skip':
                kind = 'don'
                target_id = 0
            elif kind != 'don':
                raise RuntimeError('Сейчас проверка дона')
        elif want == 'kill':
            if kind not in ('kill', 'skip'):
                raise RuntimeError('Сейчас ход мафии')
        elif kind not in (want, 'skip'):
            raise RuntimeError(f'Сейчас ход: {step.get("label")}')

        allowed = {
            'mafia': {'kill', 'skip'},
            'don': {'kill', 'don', 'skip'},
            'sheriff': {'sheriff', 'skip'},
            'doctor': {'heal', 'skip'},
            'courtesan': {'block', 'skip'},
        }.get(role)
        if not allowed or kind not in allowed:
            raise RuntimeError('Ваша роль так не ходит')
        tid = None if target_id in (None, 0) or kind == 'skip' else int(target_id)
        if tid is not None:
            tgt = self.players.get(tid)
            if not tgt or not tgt.alive:
                raise RuntimeError('Цель недоступна')
            if tid == actor.user_id and kind == 'kill':
                raise RuntimeError('Нельзя выбрать себя')

        prev = dict(self.night_actions.get(int(actor_id)) or {})

        if role == 'don' and kind == 'don':
            rec = prev or {'kind': 'kill', 'target_id': None, 'role': role}
            rec['role'] = role
            rec['at'] = time.time()
            if tid is not None:
                result = self.don_check(tid)
                rec['don_check'] = result
                rec['result'] = result
            else:
                rec['don_check'] = {'skipped': True}
            if rec.get('kind') not in ('kill', 'skip') and not rec.get('kill_done'):
                rec['kind'] = prev.get('kind') or 'pending'
            self.night_actions[int(actor_id)] = rec
            return rec

        rec = {
            'kind': kind if kind != 'skip' else (
                'skip' if want != 'sheriff' else 'skip'),
            'target_id': tid,
            'role': role,
            'at': time.time(),
            'kill_done': kind in ('kill', 'skip') and want == 'kill',
        }
        if kind == 'skip' and want in ('heal', 'block', 'sheriff'):
            rec['kind'] = 'skip'
        elif kind != 'skip':
            rec['kind'] = kind
        if prev.get('don_check'):
            rec['don_check'] = prev['don_check']
        if prev.get('result') and kind != 'sheriff':
            rec['result'] = prev['result']
        self.night_actions[int(actor_id)] = rec

        if kind == 'sheriff' and tid is not None:
            result = self.sheriff_check(tid)
            rec['result'] = result
        else:
            label = {
                'kill': 'жертва выбрана',
                'heal': 'лечение',
                'block': 'блок',
                'skip': 'пас',
            }.get(kind, kind)
            self.add_event(f'🌙 {actor.display_name} · {label}')
        return rec

    def resolve_night(self) -> dict:
        """Итог ночи: убийство/лечение/блок. Возвращает отчёт."""
        if self.phase != PHASE_PLAYING or self.cycle != CYCLE_NIGHT:
            raise RuntimeError('Сейчас не ночь')

        actions = list(self.night_actions.values())
        # блок путаны
        blocked = {
            int(a['target_id'])
            for a in actions
            if a.get('kind') == 'block' and a.get('target_id')
        }
        # лечение
        healed = {
            int(a['target_id'])
            for a in actions
            if a.get('kind') == 'heal' and a.get('target_id')
            and int(a.get('target_id') or 0) not in blocked
            # если доктора заблокировали — heal не срабатывает
        }
        doctor_ids = {p.user_id for p in self.alive_players() if p.role == 'doctor'}
        if doctor_ids & blocked:
            healed = set()

        # голоса мафии на kill (дон + мафия), игнор если актёр заблокирован
        kill_votes: List[int] = []
        for actor_id, a in self.night_actions.items():
            if a.get('kind') != 'kill' or not a.get('target_id'):
                continue
            if int(actor_id) in blocked:
                continue
            kill_votes.append(int(a['target_id']))

        victim_id = None
        if kill_votes:
            # большинство; при ничьей — выбор дона, иначе первый
            counts = Counter(kill_votes)
            top = counts.most_common()
            best_n = top[0][1]
            contenders = [uid for uid, n in top if n == best_n]
            if len(contenders) == 1:
                victim_id = contenders[0]
            else:
                don_pick = None
                for actor_id, a in self.night_actions.items():
                    ap = self.players.get(int(actor_id))
                    if ap and ap.role == 'don' and a.get('kind') == 'kill':
                        don_pick = a.get('target_id')
                victim_id = int(don_pick) if don_pick in contenders else contenders[0]

        killed = None
        saved = False
        if victim_id is not None:
            if victim_id in healed:
                saved = True
                self.add_event(
                    f'💉 Выстрел в {self.players[victim_id].display_name} — спасён')
            else:
                killed = self.kill(victim_id, by='мафия')

        if killed is None and not saved:
            report = '🌙 Ночь тихая — никто не погиб.'
        elif saved:
            report = '💉 Ночью был выстрел, но жертву спасли.'
        else:
            report = f'💀 Этой ночью погиб {_name(killed)}.'

        self.last_night_report = report
        self.add_event(report)
        return {
            'report': report,
            'killed_id': killed.user_id if killed else None,
            'saved': saved,
            'victim_id': victim_id,
            'winner': self.winner,
        }

    def submit_vote(self, voter_id: int, target_id: int) -> None:
        if self.phase != PHASE_PLAYING or self.cycle != CYCLE_VOTE:
            raise RuntimeError('Сейчас не голосование')
        voter = self.players.get(int(voter_id))
        if not voter or not voter.alive:
            raise RuntimeError('Вы вне игры')
        cur = self.current_voter_id()
        if cur is not None and int(voter_id) != int(cur):
            raise RuntimeError('Сейчас голосует другой игрок · ждите очереди')
        tid = int(target_id or 0)
        if tid != 0:
            tgt = self.players.get(tid)
            if not tgt or not tgt.alive:
                raise RuntimeError('Цель недоступна')
            if tid == voter.user_id:
                raise RuntimeError('Нельзя голосовать за себя')
        self.votes[int(voter_id)] = tid
        self.add_event(f'🗳️ {voter.display_name} проголосовал')
        # следующий в очереди
        self.vote_index = int(self.vote_index or 0) + 1

    def vote_pending(self) -> List[Player]:
        if self.vote_order:
            return [self.players[uid] for uid in self.vote_order[self.vote_index:]
                    if uid in self.players and self.players[uid].alive]
        return [p for p in self.alive_players()
                if int(p.user_id) not in self.votes]

    def vote_ready(self) -> bool:
        if self.vote_order:
            return self.vote_index >= len(self.vote_order)
        return not self.vote_pending()

    def resolve_vote(self) -> dict:
        if self.phase != PHASE_PLAYING or self.cycle != CYCLE_VOTE:
            raise RuntimeError('Сейчас не голосование')
        tallies = Counter(
            tid for tid in self.votes.values() if int(tid or 0) != 0)
        eliminated = None
        if tallies:
            top = tallies.most_common()
            best_n = top[0][1]
            contenders = [uid for uid, n in top if n == best_n]
            if len(contenders) == 1:
                eliminated = self.vote_out(contenders[0])
                report = (
                    f'🗳️ Город изгнал **{eliminated.display_name}** '
                    f'({best_n} голос.)'
                )
            else:
                report = '🗳️ Ничья — никто не изгнан.'
        else:
            report = '🗳️ Голосов нет — никто не изгнан.'
        self.last_vote_report = report
        self.add_event(report)
        return {
            'report': report,
            'eliminated_id': eliminated.user_id if eliminated else None,
            'winner': self.winner,
            # без детализации «кто за кого» — ведущему не светим
            'voted': len(self.votes),
            'alive': len(self.alive_players()),
        }

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
            self.cycle = CYCLE_NONE
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
        # без имени цели в общем логе — результат только шерифу в ЛС
        self.add_event('🕵️ Шериф провёл проверку')
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
        self.add_event('👑 Дон провёл проверку')
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
            'day_number': self.day_number,
            'cycle': self.cycle,
            'night_actions': {
                str(k): dict(v) for k, v in (self.night_actions or {}).items()
            },
            'night_queue': list(self.night_queue or []),
            'night_step': int(self.night_step or 0),
            'votes': {str(k): int(v) for k, v in (self.votes or {}).items()},
            'vote_order': [int(x) for x in (self.vote_order or [])],
            'vote_index': int(self.vote_index or 0),
            'last_night_report': self.last_night_report,
            'last_vote_report': self.last_vote_report,
            'public_message_ids': [int(x) for x in (self.public_message_ids or [])],
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Game':
        players = {
            int(k): Player.from_dict(v)
            for k, v in (d.get('players') or {}).items()
        }
        night_raw = d.get('night_actions') or {}
        night_actions = {int(k): dict(v) for k, v in night_raw.items()}
        votes_raw = d.get('votes') or {}
        votes = {int(k): int(v) for k, v in votes_raw.items()}
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
            day_number=int(d.get('day_number') or 0),
            cycle=str(d.get('cycle') or CYCLE_NONE),
            night_actions=night_actions,
            night_queue=list(d.get('night_queue') or []),
            night_step=int(d.get('night_step') or 0),
            votes=votes,
            vote_order=[int(x) for x in (d.get('vote_order') or [])],
            vote_index=int(d.get('vote_index') or 0),
            last_night_report=str(d.get('last_night_report') or ''),
            last_vote_report=str(d.get('last_vote_report') or ''),
            public_message_ids=[int(x) for x in (d.get('public_message_ids') or [])],
        )


def _name(p: Player) -> str:
    return f'**{p.display_name}**'
