# -*- coding: utf-8 -*-
"""Сводка активности staff для веб-панели.

Склеивает: наказания, сообщения в чате, время в войсе.
Топы общие и по ролям (Helper / Mod / …).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any


ROLE_ORDER = (
    'owner', 'staff-admin', 'staff-assistent', 'admin',
    'assistent', 'curator', 'master', 'mod',
    'creative', 'broadcaster', 'event', 'support', 'closemod',
    'helper',
)

ROLE_TITLE = {
    'owner': 'Owner',
    'staff-admin': 'Staff Admin',
    'staff-assistent': 'Staff Assistent',
    'admin': 'Admin',
    'assistent': 'Assistent',
    'curator': 'Curator',
    'master': 'Master',
    'mod': 'Moderator',
    'creative': 'Creative',
    'broadcaster': 'Broadcaster',
    'event': 'Event',
    'support': 'Support',
    'closemod': 'Close mod',
    'helper': 'Helper',
}


def fmt_voice(seconds: int) -> str:
    try:
        secs = max(0, int(seconds or 0))
    except (TypeError, ValueError):
        secs = 0
    if secs <= 0:
        return '0 мин'
    h, rem = divmod(secs, 3600)
    m = rem // 60
    if h:
        return f'{h} ч {m} мин'
    return f'{m} мин'


def voice_window_map(guild_id, days: int) -> dict[str, dict]:
    """uid -> {seconds, name, avatar} за последние days дней."""
    out: dict[str, dict] = {}
    try:
        from cogs.voice_tracker import voice_all
        raw = voice_all(guild_id) or {}
    except Exception:
        return out
    days = max(1, int(days))
    keys = [str(date.today() - timedelta(days=i)) for i in range(days)]
    for uid, rec in raw.items():
        if not isinstance(rec, dict):
            continue
        daily = rec.get('daily') or {}
        if not isinstance(daily, dict):
            daily = {}
        total = 0
        for d in keys:
            try:
                total += max(0, int(daily.get(d, 0) or 0))
            except (TypeError, ValueError):
                continue
        if total <= 0:
            continue
        out[str(uid)] = {
            'seconds': total,
            'name': str(rec.get('name') or uid),
            'avatar': str(rec.get('avatar') or ''),
        }
    return out


def messages_window_map(guild_id, days: int, staff_ids: set[str]) -> dict[str, int]:
    """Сообщения staff за окно: message_stats + mod_activity."""
    counts: dict[str, int] = {}
    if not staff_ids:
        return counts
    days = max(1, int(days))
    edge = datetime.now(timezone.utc) - timedelta(days=days)

    # 1) message_stats (уже пишется на каждое сообщение)
    try:
        from services import message_stats as ms
        try:
            ms.flush_all()
        except Exception:
            pass
        events = list(ms.load_full(guild_id) or [])
        try:
            with ms._LOCK:
                events.extend(list(ms._PENDING.get(str(guild_id), []) or []))
        except Exception:
            pass
        for ev in events:
            if not isinstance(ev, dict):
                continue
            uid = str(ev.get('uid') or '')
            if uid not in staff_ids:
                continue
            ts_raw = ev.get('timestamp')
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace('Z', '+00:00'))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if ts < edge:
                continue
            counts[uid] = counts.get(uid, 0) + 1
    except Exception:
        pass

    # 2) mod_activity (дневная сетка) — max, не сумма (разные источники)
    try:
        from services import mod_activity as ma
        for uid, row in (ma.message_counts(guild_id, days=days) or {}).items():
            if str(uid) not in staff_ids:
                continue
            n = int((row or {}).get('messages') or 0)
            if n > counts.get(str(uid), 0):
                counts[str(uid)] = n
    except Exception:
        pass
    return counts


def build_staff_board(
        *,
        guild_id,
        days: int,
        people: list[dict],
        mod_rows: list[dict],
        hidden_kinds: set | list | None = None,
) -> dict[str, Any]:
    """Полная доска активности staff."""
    days = 30 if int(days) >= 30 else 7
    hidden = set(hidden_kinds or ())
    people = list(people or [])
    staff_ids = {str(p.get('id')) for p in people if str(p.get('id') or '').isdigit()}
    by_id = {str(p.get('id')): p for p in people if str(p.get('id') or '').isdigit()}

    mods = {}
    for m in mod_rows or []:
        uid = str(m.get('id') or '')
        if uid.isdigit():
            mods[uid] = m

    voice = voice_window_map(guild_id, days)
    msgs = messages_window_map(guild_id, days, staff_ids)

    rows = []
    for uid in staff_ids:
        p = by_id.get(uid) or {}
        m = mods.get(uid) or {}
        actions = int(m.get('total') or 0)
        warns = int(m.get('warns') or 0)
        mutes = int(m.get('mutes') or 0)
        kicks = 0 if 'kick' in hidden else int(m.get('kicks') or 0)
        bans = 0 if 'ban' in hidden else int(m.get('bans') or 0)
        messages = int(msgs.get(uid) or 0)
        voice_s = int((voice.get(uid) or {}).get('seconds') or 0)
        # вес: мера важнее сообщений, войс — минуты
        score = actions * 12 + messages + (voice_s // 60)
        if score <= 0 and actions <= 0 and messages <= 0 and voice_s <= 0:
            # всё равно показываем staff с нулями в общем списке? нет — только активных
            continue
        tag = str(p.get('role_tag') or p.get('role') or 'helper')
        rows.append({
            'id': uid,
            'name': p.get('name') or m.get('name') or (voice.get(uid) or {}).get('name') or uid,
            'handle': p.get('handle') or '',
            'avatar': p.get('avatar') or (voice.get(uid) or {}).get('avatar') or '',
            'role': p.get('role') or '',
            'role_tag': tag,
            'role_label': p.get('role_label') or ROLE_TITLE.get(tag, tag),
            'actions': actions,
            'warns': warns,
            'mutes': mutes,
            'kicks': kicks,
            'bans': bans,
            'messages': messages,
            'voice_s': voice_s,
            'voice': fmt_voice(voice_s),
            'score': score,
        })

    # модеры без карточки people, но с мерами
    for uid, m in mods.items():
        if uid in staff_ids:
            continue
        actions = int(m.get('total') or 0)
        if actions <= 0:
            continue
        messages = int(msgs.get(uid) or 0)
        voice_s = int((voice.get(uid) or {}).get('seconds') or 0)
        rows.append({
            'id': uid,
            'name': m.get('name') or uid,
            'handle': '',
            'avatar': (voice.get(uid) or {}).get('avatar') or '',
            'role': 'mod',
            'role_tag': 'mod',
            'role_label': 'Moderator',
            'actions': actions,
            'warns': int(m.get('warns') or 0),
            'mutes': int(m.get('mutes') or 0),
            'kicks': 0 if 'kick' in hidden else int(m.get('kicks') or 0),
            'bans': 0 if 'ban' in hidden else int(m.get('bans') or 0),
            'messages': messages,
            'voice_s': voice_s,
            'voice': fmt_voice(voice_s),
            'score': actions * 12 + messages + (voice_s // 60),
        })

    rows.sort(key=lambda r: (-int(r['score']), -int(r['actions']),
                             -int(r['messages']), -int(r['voice_s']),
                             str(r['name']).lower()))
    max_score = max((int(r['score']) for r in rows), default=1) or 1
    for i, r in enumerate(rows, 1):
        r['rank'] = i
        r['bar'] = max(4, int(round(100 * int(r['score']) / max_score)))

    by_role: dict[str, list] = {}
    for r in rows:
        by_role.setdefault(r['role_tag'], []).append(r)

    role_tops = []
    for key in ROLE_ORDER:
        bucket = by_role.get(key) or []
        if not bucket:
            continue
        role_tops.append({
            'key': key,
            'title': ROLE_TITLE.get(key, key),
            'count': len(bucket),
            'top': bucket[:5],
            'actions': sum(int(x['actions']) for x in bucket),
            'messages': sum(int(x['messages']) for x in bucket),
            'voice_s': sum(int(x['voice_s']) for x in bucket),
            'voice': fmt_voice(sum(int(x['voice_s']) for x in bucket)),
        })

    summary = {
        'staff_active': len(rows),
        'staff_total': len(staff_ids),
        'actions': sum(int(r['actions']) for r in rows),
        'messages': sum(int(r['messages']) for r in rows),
        'voice_s': sum(int(r['voice_s']) for r in rows),
        'voice': fmt_voice(sum(int(r['voice_s']) for r in rows)),
        'days': days,
    }
    return {
        'summary': summary,
        'rows': rows,
        'podium': rows[:3],
        'role_tops': role_tops,
        'by_role': by_role,
    }
