# -*- coding: utf-8 -*-
"""Мафия — игровая логика: роли, пресеты составов, победа (ТЗ «Бот по Мафии»).

Модуль чистый (без discord) — покрыт tests/test_mafia_core.py. Дискорд-слой
(команды, кнопки, ЛС) — cogs/mafia.py.

Хранение партий — В ПАМЯТИ процесса (см. GameRegistry): живая партия
«Мафии» короткая (один вечер), рестарт бота посреди игры её обрывает —
ведущий просто открывает /mafia start заново. Постоянного хранилища
намеренно нет, чтобы не тащить полу-мёртвые партии через рестарты.
"""
import random
import time
from itertools import count as _count

# ── роли ──────────────────────────────────────────────────────────────
MAFIA = 'mafia'
DON = 'don'
SHERIFF = 'sheriff'
DOCTOR = 'doctor'
PUTANA = 'putana'
CIVILIAN = 'civilian'

MAFIA_SIDE = frozenset({MAFIA, DON})
GOOD_SIDE = frozenset({SHERIFF, DOCTOR, PUTANA, CIVILIAN})

ROLE_LABELS = {
    MAFIA: 'Мафия',
    DON: 'Дон',
    SHERIFF: 'Шериф',
    DOCTOR: 'Доктор',
    PUTANA: 'Путана',
    CIVILIAN: 'Мирный',
}
ROLE_EMOJI = {
    MAFIA: '🔴',
    DON: '👑',
    SHERIFF: '🕵️',
    DOCTOR: '💉',
    PUTANA: '💋',
    CIVILIAN: '👤',
}


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


def role_emoji(role: str) -> str:
    return ROLE_EMOJI.get(role, '❔')


def role_side(role: str) -> str:
    return 'mafia' if role in MAFIA_SIDE else 'good'


# ── пресеты составов (ТЗ, раздел 2) ─────────────────────────────────────
# (мин.игроков, макс.игроков|None, {роль: количество}, текст-описание)
PRESETS = [
    (6, 6, {MAFIA: 1, SHERIFF: 1},
     '1 мафия, 1 шериф, 4 мирных'),
    (7, 7, {MAFIA: 1, SHERIFF: 1, DOCTOR: 1},
     '1 мафия, 1 шериф, 1 доктор, 4 мирных'),
    (8, 9, {MAFIA: 2, SHERIFF: 1, DOCTOR: 1, PUTANA: 1},
     '2 мафии, 1 шериф, 1 доктор, 1 путана, 3-4 мирных'),
    (10, 11, {MAFIA: 3, SHERIFF: 1, DOCTOR: 1, PUTANA: 1},
     '3 мафии, 1 шериф, 1 доктор, 1 путана, 4-5 мирных'),
    (12, None, {MAFIA: 3, DON: 1, SHERIFF: 1, DOCTOR: 1, PUTANA: 1},
     '3 мафии + 1 дон, 1 шериф, 1 доктор, 1 путана, 5+ мирных'),
]

MIN_PLAYERS = PRESETS[0][0]


def preset_range_label(idx: int) -> str:
    lo, hi, _roles, _desc = PRESETS[idx]
    if hi is None:
        return f'{lo}+ игроков'
    if hi == lo:
        return f'{lo} игроков'
    return f'{lo}-{hi} игроков'


def preset_description(idx: int) -> str:
    return PRESETS[idx][3]


def preset_for_count(n: int) -> int:
    """Индекс пресета, подходящего под n игроков (авто-подбор по ТЗ).

    Меньше минимума (6) — None (набирать смысла нет). Больше любого
    диапазона — последний пресет (12+, растущий состав мирных).
    """
    if n < MIN_PLAYERS:
        return None
    best = 0
    for i, (lo, hi, _roles, _desc) in enumerate(PRESETS):
        if n >= lo:
            best = i
    return best


def roles_for_preset(idx: int, player_count: int) -> dict:
    """{роль: количество} для конкретного числа игроков — остаток мирные."""
    _lo, _hi, roles, _desc = PRESETS[idx]
    out = dict(roles)
    used = sum(out.values())
    out[CIVILIAN] = max(0, player_count - used)
    return out


def build_roles_list(idx: int, player_count: int) -> list:
    """Плоский список ролей длиной player_count (для shuffle+assign)."""
    roles = roles_for_preset(idx, player_count)
    out = []
    for role, cnt in roles.items():
        out.extend([role] * cnt)
    # защита от рассинхрона округления — довесить/подрезать мирными
    if len(out) < player_count:
        out.extend([CIVILIAN] * (player_count - len(out)))
    return out[:player_count]


def assign_roles(player_ids, preset_idx: int, *, rng=None) -> dict:
    """{player_id: role} — случайное распределение по составу пресета."""
    players = list(player_ids)
    roles = build_roles_list(preset_idx, len(players))
    r = rng or random
    r.shuffle(roles)
    return dict(zip(players, roles))


def check_winner(roles: dict, alive_ids) -> str:
    """'mafia' | 'good' | None — итог партии по живым игрокам.

    Мирные победили — мафии (и дона) не осталось в живых.
    Мафия победила — её живых стало >= живых «мирной» стороны (шериф,
    доктор, путана и мирные считаются одной стороной, ТЗ раздел
    «Финал игры»: 4:4, 3:3, 2:2, 1:1 и любой перекос дальше — тоже мафия).
    """
    alive = set(alive_ids)
    mafia_alive = sum(1 for uid, role in roles.items()
                      if uid in alive and role in MAFIA_SIDE)
    good_alive = sum(1 for uid, role in roles.items()
                     if uid in alive and role in GOOD_SIDE)
    if mafia_alive == 0:
        return 'good'
    if mafia_alive >= good_alive:
        return 'mafia'
    return None


# ── партия ────────────────────────────────────────────────────────────
PHASE_SETUP = 'setup'          # набор игроков, пресет ещё не разыгран
PHASE_CONFIRM = 'confirm'      # роли разданы, ждём подтверждений
PHASE_ACTIVE = 'active'        # «Начать игру» нажата — состав зафиксирован
PHASE_ENDED = 'ended'

STATUS_PENDING = 'pending'
STATUS_CONFIRMED = 'confirmed'


class Player:
    __slots__ = ('uid', 'name', 'role', 'status', 'alive', 'dm_ok')

    def __init__(self, uid, name):
        self.uid = uid
        self.name = name
        self.role = None
        self.status = STATUS_PENDING
        self.alive = True
        self.dm_ok = None  # None — ещё не пытались, True/False — итог ЛС


class MafiaGame:
    """Одна партия: набор игроков, роли, фаза, журнал событий."""

    def __init__(self, game_id, guild_id, channel_id, voice_channel_id,
                host_id, host_name):
        self.id = game_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.voice_channel_id = voice_channel_id
        self.host_id = host_id
        self.host_name = host_name
        self.phase = PHASE_SETUP
        self.preset_idx = None
        self.players = {}           # uid -> Player
        self.log = []               # [(ts, text)]
        self.winner = None
        self.created = time.monotonic()
        self.panel_message_ref = None   # discord-слой хранит своё
        self.host_summary_ref = None

    # ── состав ────────────────────────────────────────────────────────
    def add_player(self, uid, name) -> bool:
        if uid == self.host_id or uid in self.players:
            return False
        self.players[uid] = Player(uid, name)
        return True

    def remove_player(self, uid) -> bool:
        return self.players.pop(uid, None) is not None

    def player_count(self) -> int:
        return len(self.players)

    def suggested_preset(self):
        return preset_for_count(self.player_count())

    # ── раздача ───────────────────────────────────────────────────────
    def deal(self, preset_idx=None, *, rng=None):
        idx = preset_idx if preset_idx is not None else self.suggested_preset()
        if idx is None:
            raise ValueError(f'нужно минимум {MIN_PLAYERS} игроков')
        self.preset_idx = idx
        mapping = assign_roles(list(self.players.keys()), idx, rng=rng)
        for uid, role in mapping.items():
            p = self.players[uid]
            p.role = role
            p.status = STATUS_PENDING
            p.alive = True
        self.phase = PHASE_CONFIRM
        self.winner = None
        self.log_event(f'Роли разданы (пресет: {preset_range_label(idx)})')
        return mapping

    def confirmed_count(self) -> int:
        return sum(1 for p in self.players.values()
                  if p.status == STATUS_CONFIRMED)

    def all_confirmed(self) -> bool:
        return self.players and self.confirmed_count() == self.player_count()

    def confirm(self, uid) -> bool:
        """True — статус реально сменился (для идемпотентности повторного клика)."""
        p = self.players.get(uid)
        if p is None or p.status == STATUS_CONFIRMED:
            return False
        p.status = STATUS_CONFIRMED
        return True

    # ── активная игра ────────────────────────────────────────────────
    def start(self):
        if not self.all_confirmed():
            raise ValueError('не все подтвердили участие')
        self.phase = PHASE_ACTIVE
        self.log_event('Игра началась — состав и роли зафиксированы')

    def alive_ids(self):
        return {uid for uid, p in self.players.items() if p.alive}

    def roles_map(self):
        return {uid: p.role for uid, p in self.players.items()}

    def eliminate(self, uid, reason: str) -> str:
        """Убить/исключить игрока, вернуть 'mafia'|'good'|None (итог)."""
        p = self.players.get(uid)
        if p is None or not p.alive:
            return self.winner
        p.alive = False
        self.log_event(f'{reason}: {p.name}')
        winner = check_winner(self.roles_map(), self.alive_ids())
        if winner:
            self.winner = winner
            self.phase = PHASE_ENDED
            self.log_event('Победа мирных' if winner == 'good' else 'Победа мафии')
        return winner

    def log_event(self, text):
        self.log.append((time.time(), text))

    def sheriff_check(self, uid) -> bool:
        """True — проверяемый на стороне мафии."""
        p = self.players.get(uid)
        is_mafia = bool(p and p.role in MAFIA_SIDE)
        self.log_event(f'Проверка шерифа: {p.name if p else uid} — '
                       f'{"мафия" if is_mafia else "мирный"}')
        return is_mafia

    def don_check(self, uid) -> bool:
        """True — проверяемый шериф."""
        p = self.players.get(uid)
        is_sheriff = bool(p and p.role == SHERIFF)
        self.log_event(f'Проверка дона: {p.name if p else uid} — '
                       f'{"шериф" if is_sheriff else "не шериф"}')
        return is_sheriff


class GameRegistry:
    """Активные партии по guild — одна партия на текстовый канал."""

    def __init__(self):
        self._by_channel = {}
        self._ids = _count(1000)

    def next_id(self):
        return next(self._ids)

    def get(self, channel_id):
        return self._by_channel.get(channel_id)

    def set(self, channel_id, game):
        self._by_channel[channel_id] = game

    def remove(self, channel_id):
        self._by_channel.pop(channel_id, None)

    def all(self):
        return list(self._by_channel.values())


REGISTRY = GameRegistry()
