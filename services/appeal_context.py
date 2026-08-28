# -*- coding: utf-8 -*-
"""Контекст модератора по апелляции: кем человек наказан раньше.

Источники — только синхронные и локальные (без Discord API), поэтому одни и
те же данные видят и бот (карточка в канале), и панель (очередь /appeals):

- data/discord_audit_cache.json — зеркало аудита Discord (пишет cogs/logs.py):
  баны, кики, муты по target_id;
- GuildData('warnings') — варны (основное хранилище cogs/warnings.py);
- state апелляций — сколько раз подавал и чем кончилась последняя.

Любой источник может отсутствовать (свежий сервер, чистка) — контекст
собирается из того, что есть, ничего не выдумывая.
"""
import json
import os
from datetime import datetime, timezone

CACHE_FILE = 'data/discord_audit_cache.json'

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


def audit_punish_counts(gid, user_id):
    """Сколько банов/киков/мутов нашёл аудит-зеркало у этого user_id."""
    counts = {'ban': 0, 'kick': 0, 'mute': 0, 'warn': 0}
    uid = str(user_id)
    try:
        if not os.path.exists(CACHE_FILE):
            return counts
        with open(CACHE_FILE, 'r', encoding='utf-8') as fp:
            cache = json.load(fp)
        for ev in cache.get(str(gid), []) or []:
            if str(ev.get('target_id')) != uid:
                continue
            bucket = _PUNISH_BUCKETS.get(str(ev.get('action') or ''))
            if bucket:
                counts[bucket] += 1
    except Exception:
        return counts
    return counts


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
    mine = [i for i in (state or {}).get('items', []) if int(i.get('user_id') or 0) == uid]
    mine.sort(key=lambda i: str(i.get('created_at') or ''))
    last = None
    if mine:
        it = mine[-1]
        last = {'status': it.get('status'),
                'created_at': str(it.get('created_at') or '')[:16].replace('T', ' ')}
    return {'total': len(mine), 'last': last}


_STATUS_RU = {'pending': 'ожидает', 'accepted': 'принята', 'rejected': 'отклонена',
              'auto_closed': 'закрыта автоматически'}


def build_context(state, gid, user_id):
    """Полный контекст: словари + готовые короткие строки для карточки.

    Возвращает dict:
      punishes: {'ban': n, 'kick': n, 'mute': n, 'warn': n}
      punish_line: 'Варны: 2 · Муты: 1 · Баны: 0 · Кики: 0'
      appeals_total: n, appeals_last: 'отклонена · 21.08.2026 15:20' | None
      line: одна строка для embed/панели
    """
    punishes = audit_punish_counts(gid, user_id)
    punishes['warn'] += warns_count(gid, user_id)
    parts = [f'{_LABELS[k]}: {punishes[k]}' for k in ('warn', 'mute', 'ban', 'kick')]
    punish_line = ' · '.join(parts)
    ap = appeals_stats(state, user_id)
    last_line = None
    if ap['last']:
        lbl = _STATUS_RU.get(str(ap['last']['status']), str(ap['last']['status']))
        last_line = f"{lbl} · {ap['last']['created_at']}"
    line = punish_line
    if ap['total'] > 1:
        line += f' · Апелляций: {ap["total"]} (последняя — {last_line})'
    return {
        'punishes': punishes,
        'punish_line': punish_line,
        'appeals_total': ap['total'],
        'appeals_last': last_line,
        'line': line,
    }
