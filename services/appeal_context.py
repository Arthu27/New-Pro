# -*- coding: utf-8 -*-
"""Контекст модератора по апелляции: кем человек наказан раньше.

Источники — только синхронные и локальные (без Discord API), поэтому одни и
те же данные видят и бот (карточка в канале), и панель (очередь /appeals):

- data/mod_data.json — дела из /modpanel (бан/мут + кто выдал);
- data/punish_roles.json — активные временные роли мута;
- data/discord_audit_cache.json — зеркало аудита Discord;
- GuildData('warnings') — варны;
- state апелляций — сколько раз подавал и чем кончилась последняя.

Любой источник может отсутствовать (свежий сервер, чистка) — контекст
собирается из того, что есть, ничего не выдумывая.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from logger import get_logger
log = get_logger('appeal_context')

CACHE_FILE = 'data/discord_audit_cache.json'
MOD_DATA_FILE = 'data/mod_data.json'
PUNISH_ROLES_FILE = 'data/punish_roles.json'

# действие из зеркала аудита → наше ведро
_PUNISH_BUCKETS = {
    'Бан': 'ban',
    'Кик': 'kick',
    'Мут': 'mute',
    'Таймаут': 'mute',
    'Мут (чат)': 'mute',
    'Войс-мут': 'mute',
    'Предупреждение': 'warn',
    'Варн': 'warn',
}
_LABELS = {'ban': 'Баны', 'kick': 'Кики', 'mute': 'Муты', 'warn': 'Варны'}

# активные наказания из дел панели
_ACTIVE_ACTIONS = {
    'ban': 'Бан',
    'timeout': 'Мут (чат + войс)',
    'mute_chat': 'Мут чата',
    'vmute': 'Войс-мут',
}
_LIFT_ACTIONS = {
    'ban': frozenset({'unban'}),
    'timeout': frozenset({'untimeout', 'unmute_chat', 'vunmute'}),
    'mute_chat': frozenset({'unmute_chat', 'untimeout'}),
    'vmute': frozenset({'vunmute', 'untimeout'}),
}


def _parse_ts(value):
    """ISO-строка → aware datetime (UTC). Кривое/пустое → None."""
    s = str(value or '').strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _fmt_when(value):
    dt = _parse_ts(value)
    if dt is None:
        return ''
    return dt.astimezone(timezone.utc).strftime('%d.%m.%Y %H:%M')


def _read_json(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def audit_punish_counts(gid, user_id):
    """Сколько банов/киков/мутов нашёл аудит-зеркало у этого user_id."""
    counts = {'ban': 0, 'kick': 0, 'mute': 0, 'warn': 0}
    uid = str(user_id)
    try:
        cache = _read_json(CACHE_FILE, {})
        for ev in cache.get(str(gid), []) or []:
            if str(ev.get('target_id')) != uid:
                continue
            bucket = _PUNISH_BUCKETS.get(str(ev.get('action') or ''))
            if bucket:
                counts[bucket] += 1
    except Exception:
        return counts
    return counts


def mod_cases_for(gid, user_id):
    """Дела участника из data/mod_data.json (новые сверху по timestamp)."""
    uid = str(user_id)
    data = _read_json(MOD_DATA_FILE, {})
    cases = (data.get('cases') or {}).get(str(gid)) or []
    mine = [c for c in cases if str(c.get('user_id')) == uid]
    mine.sort(key=lambda c: str(c.get('timestamp') or ''))
    return mine


def mod_case_counts(gid, user_id):
    """Счётчики из дел панели (надёжнее аудита для ролевого бана)."""
    counts = {'ban': 0, 'kick': 0, 'mute': 0, 'warn': 0}
    for c in mod_cases_for(gid, user_id):
        act = str(c.get('action') or '')
        if act == 'ban':
            counts['ban'] += 1
        elif act in ('timeout', 'mute_chat', 'vmute'):
            counts['mute'] += 1
        elif act == 'kick':
            counts['kick'] += 1
        elif act == 'warn':
            counts['warn'] += 1
    return counts


def _case_still_active(cases, idx, action):
    """После дела idx нет снятия этого наказания."""
    lifts = _LIFT_ACTIONS.get(action) or frozenset()
    if not lifts:
        return True
    for later in cases[idx + 1:]:
        if str(later.get('action') or '') in lifts:
            return False
    return True


def active_from_mod_data(gid, user_id):
    """Текущее наказание из дел панели: последнее неснятое."""
    cases = mod_cases_for(gid, user_id)
    # идём с конца — самое свежее активное
    for i in range(len(cases) - 1, -1, -1):
        c = cases[i]
        act = str(c.get('action') or '')
        if act not in _ACTIVE_ACTIONS:
            continue
        if not _case_still_active(cases, i, act):
            continue
        return {
            'kind': act,
            'label': _ACTIVE_ACTIONS[act],
            'mod_name': str(c.get('mod_name') or c.get('mod_id') or '—'),
            'mod_id': str(c.get('mod_id') or ''),
            'reason': str(c.get('reason') or '').strip(),
            'when': _fmt_when(c.get('timestamp')),
            'source': 'mod_data',
        }
    return None


def active_from_temps(gid, user_id):
    """Активный мут по журналу сроков punish_roles."""
    data = _read_json(PUNISH_ROLES_FILE, {})
    row = data.get(str(gid)) or {}
    roles = row.get('roles') or {}
    temps = (row.get('temps') or {}).get(str(user_id)) or {}
    now = time.time()
    mute_id = int(roles.get('mute') or 0)
    vmute_id = int(roles.get('vmute') or 0)
    ban_id = int(roles.get('ban') or 0)
    # temps не хранит бан (бессрочный) — только mute/vmute
    try:
        if mute_id and float(temps.get(str(mute_id)) or 0) > now:
            return {
                'kind': 'mute_chat',
                'label': 'Мут чата',
                'mod_name': '—',
                'mod_id': '',
                'reason': '',
                'when': '',
                'source': 'temps',
            }
        if vmute_id and float(temps.get(str(vmute_id)) or 0) > now:
            return {
                'kind': 'vmute',
                'label': 'Войс-мут',
                'mod_name': '—',
                'mod_id': '',
                'reason': '',
                'when': '',
                'source': 'temps',
            }
    except (TypeError, ValueError) as _ex:
        log.debug('appeal_context: except@199: %s', _ex)
    _ = ban_id  # бан смотрим по ролям/делам
    return None


def active_from_roles(gid, role_ids):
    """Текущее наказание по ролям участника (если передали id ролей)."""
    if not role_ids:
        return None
    have = {int(r) for r in role_ids if r}
    data = _read_json(PUNISH_ROLES_FILE, {})
    roles = (data.get(str(gid)) or {}).get('roles') or {}
    mapping = (
        ('ban', int(roles.get('ban') or 0), 'Бан'),
        ('mute_chat', int(roles.get('mute') or 0), 'Мут чата'),
        ('vmute', int(roles.get('vmute') or 0), 'Войс-мут'),
    )
    for kind, rid, label in mapping:
        if rid and rid in have:
            return {
                'kind': kind,
                'label': label,
                'mod_name': '—',
                'mod_id': '',
                'reason': '',
                'when': '',
                'source': 'roles',
            }
    return None


def current_punishment(gid, user_id, *, role_ids=None):
    """Активное наказание сейчас + кто выдал (если известно).

    Приоритет: дела панели → роли на участнике → журнал сроков мута.
    Если роль/temps знают вид, а дело — модератора, склеиваем.
    """
    from_case = active_from_mod_data(gid, user_id)
    from_role = active_from_roles(gid, role_ids)
    from_temp = active_from_temps(gid, user_id)

    cur = from_case or from_role or from_temp
    if cur is None:
        return None
    # дополнить модератора из дела, если роль/temps его не знают
    if (not cur.get('mod_id') or cur.get('mod_name') in ('—', '')) and from_case:
        if from_case.get('kind') == cur.get('kind') or not from_case:
            cur = dict(cur)
            cur['mod_name'] = from_case.get('mod_name') or cur.get('mod_name')
            cur['mod_id'] = from_case.get('mod_id') or cur.get('mod_id')
            cur['reason'] = cur.get('reason') or from_case.get('reason') or ''
            cur['when'] = cur.get('when') or from_case.get('when') or ''
    return cur


def format_current(cur):
    """Многострочный блок «сейчас / кто выдал» для карточки."""
    if not cur:
        return 'Сейчас: наказания нет (или уже снято)'
    lines = [f"**Сейчас:** {cur.get('label') or 'наказание'}"]
    mod = str(cur.get('mod_name') or '').strip()
    mid = str(cur.get('mod_id') or '').strip()
    if mod and mod != '—':
        who = mod
        if mid:
            who = f'{mod} · `{mid}`'
        lines.append(f'**Выдал:** {who}')
    elif mid:
        lines.append(f'**Выдал:** `{mid}`')
    else:
        lines.append('**Выдал:** неизвестно')
    when = str(cur.get('when') or '').strip()
    if when:
        lines.append(f'**Когда:** {when} UTC')
    reason = str(cur.get('reason') or '').strip()
    if reason:
        if len(reason) > 220:
            reason = reason[:217] + '…'
        lines.append(f'**Причина:** {reason}')
    return '\n'.join(lines)


def warns_count(gid, user_id):
    """Варны из основного хранилища cogs/warnings.py."""
    try:
        from db import GuildData
        warns = GuildData('warnings').get(int(gid), str(user_id), []) or []
        return len(warns)
    except Exception:
        return 0


def appeals_stats(state, user_id):
    """Апелляции пользователя из state: всего + последняя (статус, дата)."""
    uid = int(user_id)
    mine = [i for i in (state or {}).get('items', [])
            if int(i.get('user_id') or 0) == uid]
    mine.sort(key=lambda i: str(i.get('created_at') or ''))
    last = None
    if mine:
        it = mine[-1]
        last = {'status': it.get('status'),
                'created_at': str(it.get('created_at') or '')[:16].replace('T', ' ')}
    return {'total': len(mine), 'last': last}


_STATUS_RU = {
    'pending': 'ожидает',
    'accepted': 'принята',
    'rejected': 'отклонена',
    'auto_closed': 'закрыта автоматически',
}


def build_context(state, gid, user_id, *, role_ids=None):
    """Полный контекст: словари + готовые строки для карточки.

    Возвращает dict:
      current: {...} | None — активное наказание
      current_block: многострочный блок «Сейчас / Выдал / …»
      punishes: {'ban': n, ...}
      punish_line: 'Варны: 2 · Муты: 1 · Баны: 0 · Кики: 0'
      appeals_total / appeals_last
      line: одна строка (для компактных мест)
      rich: полный текст поля «Контекст модератора»
    """
    punishes = audit_punish_counts(gid, user_id)
    # дела панели — точнее для ролевого бана (аудит пишет «Изменение ролей»)
    for k, v in mod_case_counts(gid, user_id).items():
        punishes[k] = max(int(punishes.get(k) or 0), int(v or 0))
    punishes['warn'] = max(int(punishes.get('warn') or 0),
                           warns_count(gid, user_id))
    parts = [f'{_LABELS[k]}: {punishes[k]}' for k in ('warn', 'mute', 'ban', 'kick')]
    punish_line = ' · '.join(parts)
    ap = appeals_stats(state, user_id)
    last_line = None
    if ap['last']:
        lbl = _STATUS_RU.get(str(ap['last']['status']), str(ap['last']['status']))
        last_line = f"{lbl} · {ap['last']['created_at']}"

    cur = current_punishment(gid, user_id, role_ids=role_ids)
    current_block = format_current(cur)

    line = punish_line
    if cur:
        who = cur.get('mod_name') or '—'
        line = f"Сейчас: {cur.get('label')} · выдал {who}"
        if cur.get('when'):
            line += f" · {cur['when']}"
        line += f' · {punish_line}'
    if ap['total'] > 1:
        line += f' · Апелляций: {ap["total"]} (последняя — {last_line})'

    rich_bits = [current_block, punish_line]
    if ap['total'] > 1 and last_line:
        rich_bits.append(f'Апелляций: {ap["total"]} (последняя — {last_line})')
    rich = '\n'.join(rich_bits)

    return {
        'current': cur,
        'current_block': current_block,
        'punishes': punishes,
        'punish_line': punish_line,
        'appeals_total': ap['total'],
        'appeals_last': last_line,
        'line': line,
        'rich': rich,
    }
