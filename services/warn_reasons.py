# -*- coding: utf-8 -*-
"""Причины варна: отдельно для участников и для стаффа.

Списки в конфиге — меняются здесь (или через OVERRIDE JSON), без хардкода
в модалках /modpanel и веб-панели.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Literal, Optional, Tuple

from logger import get_logger

_log = get_logger('warn_reasons')

ReasonKind = Literal['member', 'staff']

# ── Участники: текущие правила сервера (варн-допустимые 1.x) ──────────
MEMBER_WARN_REASONS: Tuple[Tuple[str, str, str], ...] = (
    ('1.1', 'Реклама',
     'Реклама сторонних серверов/продуктов, прямые запросы денег или услуг'),
    ('1.2', '18+ / хейт / вред',
     'Шокирующий/сексуальный контент, хейт, пропаганда вреда'),
    ('1.3', 'Обход / твинк',
     'Обход наказаний другой учёткой или фарм валюты'),
    ('1.4', 'Личка / докс',
     'Личная информация без согласия, угрозы сватом/доксом'),
    ('1.5', 'Аватар / баннер',
     'Оскорбительный или запрещённый контент в профиле'),
    ('1.6', 'Помеха серверу',
     'Помеха работе стаффа, призывы уйти, багоюз, спам жалобами'),
    ('1.7', 'SoundPad / голос',
     'SoundPad, громкие звуки, изменение голоса'),
    ('1.8', 'Капс / спам / флуд',
     'Капс, спам, флуд, массовые упоминания, оффтоп'),
    ('1.9', 'Провокации / травля',
     'Провокации, травля, неадекватное поведение'),
    ('chat', 'Нарушение правил чата',
     'Нарушение правил текстового канала / тематики'),
    ('insult', 'Оскорбления',
     'Оскорбления участников или токсичное общение'),
)

# ── Стафф: служебные причины (регламент) ──────────────────────────────
STAFF_WARN_REASONS: Tuple[Tuple[str, str, str], ...] = (
    ('abuse', 'Злоупотребление правами',
     'Использование полномочий не по назначению'),
    ('inactive', 'Неактивность',
     'Длительная неактивность без предупреждения'),
    ('regulation', 'Нарушение регламента',
     'Нарушение внутреннего регламента стаффа'),
    ('misconduct', 'Неподобающее поведение',
     'Неподобающее поведение при исполнении обязанностей'),
    ('ignore_tickets', 'Игнорирование жалоб / тикетов',
     'Игнорирование жалоб, тикетов или обращений'),
    ('insubordination', 'Нарушение субординации',
     'Нарушение субординации, игнор указаний куратора/администрации'),
    ('leak', 'Разглашение внутренней информации',
     'Разглашение внутренней / служебной информации'),
    ('branch_rules', 'Правила своей ветки',
     'Несоблюдение правил своей ветки'),
)


def _override_path() -> str:
    return os.path.join('data', 'warn_reasons.json')


def _load_override() -> dict:
    path = _override_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except Exception as ex:
        _log.debug('warn_reasons override: %s', ex)
        return {}


def _parse_list(raw) -> List[Tuple[str, str, str]]:
    out: List[Tuple[str, str, str]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            code = str(item[0]).strip()
            label = str(item[1]).strip()
            desc = str(item[2]).strip() if len(item) > 2 else label
            if code and label:
                out.append((code, label, desc[:100]))
        elif isinstance(item, dict):
            code = str(item.get('code') or item.get('id') or '').strip()
            label = str(item.get('label') or item.get('name') or '').strip()
            desc = str(item.get('description') or item.get('desc') or label).strip()
            if code and label:
                out.append((code, label, desc[:100]))
    return out


def reasons_for(kind: ReasonKind) -> List[Tuple[str, str, str]]:
    """Список (code, label, description) для member|staff."""
    ov = _load_override()
    key = 'member' if kind == 'member' else 'staff'
    custom = _parse_list(ov.get(key) or ov.get(f'{key}_reasons'))
    if custom:
        return custom
    return list(MEMBER_WARN_REASONS if kind == 'member' else STAFF_WARN_REASONS)


def reason_type_for_target(guild, target) -> ReasonKind:
    """member или staff по роли цели."""
    try:
        from services.warn_acl import is_staff_target
        if is_staff_target(guild, target):
            return 'staff'
    except Exception as ex:
        _log.debug('reason_type_for_target: %s', ex)
    return 'member'


def find_reason(kind: ReasonKind, code: str) -> Optional[Tuple[str, str, str]]:
    code = (code or '').strip()
    if not code:
        return None
    for row in reasons_for(kind):
        if row[0] == code:
            return row
    return None


def format_reason(kind: ReasonKind, code: str, detail: str = '') -> str:
    """Текст причины для БД/лога: «код · ярлык — деталь»."""
    row = find_reason(kind, code)
    detail = (detail or '').strip()
    if row:
        base = f'{row[0]} · {row[1]}'
        return f'{base} — {detail}' if detail else base
    return detail or (code or 'Не указана')


def select_options_data(kind: ReasonKind) -> List[Dict[str, str]]:
    """Для discord.ui.Select / веб JSON."""
    out = []
    for code, label, desc in reasons_for(kind):
        out.append({
            'value': code,
            'label': f'{code} · {label}'[:100],
            'description': (desc or label)[:100],
            'code': code,
            'name': label,
        })
    return out


def is_known(kind: ReasonKind, code: str) -> bool:
    return find_reason(kind, code) is not None


def as_public_dict() -> Dict[str, Any]:
    return {
        'member': [
            {'code': c, 'label': l, 'description': d}
            for c, l, d in reasons_for('member')],
        'staff': [
            {'code': c, 'label': l, 'description': d}
            for c, l, d in reasons_for('staff')],
    }
