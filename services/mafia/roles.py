# -*- coding: utf-8 -*-
"""Роли и пресеты состава для бота Мафии (по ТЗ)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Role:
    key: str
    name: str
    emoji: str
    team: str  # 'mafia' | 'town'
    description: str

    @property
    def label(self) -> str:
        return f'{self.emoji} {self.name}'


ROLES: Dict[str, Role] = {
    'mafia': Role(
        'mafia', 'Мафия', '🔴', 'mafia',
        'Ночью вместе с мафией выбираете жертву. Днём притворяйтесь мирным.',
    ),
    'don': Role(
        'don', 'Дон', '👑', 'mafia',
        'Глава мафии. Ночью можете проверить игрока: шериф это или нет.',
    ),
    'sheriff': Role(
        'sheriff', 'Шериф', '🕵️', 'town',
        'Ночью проверяете игрока: мафия это или мирный. В ТЗ также «комиссар».',
    ),
    'doctor': Role(
        'doctor', 'Доктор', '💉', 'town',
        'Ночью лечите одного игрока — он не умрёт от выстрела мафии.',
    ),
    'courtesan': Role(
        'courtesan', 'Путана', '💋', 'town',
        'Ночью блокируете действие одного игрока.',
    ),
    'citizen': Role(
        'citizen', 'Мирный', '👤', 'town',
        'Днём голосуете за изгнание. Ночью спите. Цель — найти всю мафию.',
    ),
}


def preset_for_count(n: int) -> Dict[str, int]:
    """Состав ролей по числу игроков (ТЗ)."""
    if n < 6:
        raise ValueError('Нужно минимум 6 игроков в голосе (без ведущего)')
    if n == 6:
        return {'mafia': 1, 'sheriff': 1, 'citizen': 4}
    if n == 7:
        return {'mafia': 1, 'sheriff': 1, 'doctor': 1, 'citizen': 4}
    if n in (8, 9):
        return {'mafia': 2, 'sheriff': 1, 'doctor': 1, 'courtesan': 1, 'citizen': n - 5}
    if n in (10, 11):
        return {'mafia': 3, 'sheriff': 1, 'doctor': 1, 'courtesan': 1, 'citizen': n - 6}
    # 12+
    return {'mafia': 3, 'don': 1, 'sheriff': 1, 'doctor': 1, 'courtesan': 1, 'citizen': n - 7}


def expand_roles(counts: Dict[str, int]) -> List[str]:
    """Список ключей ролей длиной = числу игроков."""
    out: List[str] = []
    for key, cnt in counts.items():
        if key not in ROLES:
            raise ValueError(f'Неизвестная роль: {key}')
        if cnt < 0:
            raise ValueError(f'Отрицательное число ролей: {key}')
        out.extend([key] * int(cnt))
    return out


def preset_summary(n: int) -> str:
    counts = preset_for_count(n)
    parts = []
    for key, cnt in counts.items():
        if cnt:
            try:
                from services.mafia.ui_v2 import role_mark
                mark = role_mark(key)
            except Exception:
                mark = ROLES[key].emoji
            parts.append(f'{mark} {ROLES[key].name} ×{cnt}')
    return ' · '.join(parts)


def is_mafia_team(role_key: str) -> bool:
    return ROLES[role_key].team == 'mafia'


def check_result_for_sheriff(role_key: str) -> Tuple[str, str]:
    """Результат проверки шерифа: (кратко, подробно)."""
    if is_mafia_team(role_key):
        return '🔴 Мафия', f'{ROLES[role_key].label} — команда мафии'
    return '👤 Мирный', f'{ROLES[role_key].label} — мирный город'


def check_result_for_don(role_key: str) -> Tuple[str, str]:
    """Результат проверки дона: ищет шерифа."""
    if role_key == 'sheriff':
        return '🕵️ Шериф', 'Это шериф'
    return '❌ Не шериф', f'{ROLES[role_key].label} — не шериф'
