# -*- coding: utf-8 -*-
"""Сводка активности staff для веб-панели.

Склеивает: наказания, сообщения в чате, время в войсе.
Орг-ветки (Moderator / Helper / Event / …): в каждой — свои
админы/мастера/кураторы/ассистенты/стафф вместе.
Сроки: день · текущая неделя (пн→сегодня) · месяц.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional


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

# Организационные ветки сервера (не ранги!).
# В ветку — только grant/curator этой ветки. Старшие без ветки → «Админы».
BRANCH_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ('moderator', 'Moderator', ()),
    ('helper', 'Helper', ()),
    ('event', 'Event', ()),
    ('support', 'Support', ()),
    ('closemod', 'Close mod', ()),
    ('creative', 'Creative', ()),
    ('broadcaster', 'Broadcaster', ()),
    ('leadership', 'Админы / старшие', ()),
)

BRANCH_KEYS = tuple(k for k, _, __ in BRANCH_GROUPS)

# fallback по role_tag, если нет Discord role_ids
_TAG_TO_BRANCH: dict[str, str] = {
    'mod': 'moderator',
    'moderator': 'moderator',
    'helper': 'helper',
    'creative': 'creative',
    'broadcaster': 'broadcaster',
    'event': 'event',
    'support': 'support',
    'closemod': 'closemod',
    'owner': 'leadership',
    'admin': 'leadership',
    'staff-admin': 'leadership',
    # без role_ids НЕ кидаем кураторов/мастеров в Helper
    'curator': 'leadership',
    'master': 'leadership',
    'assistent': 'leadership',
    'staff-assistent': 'leadership',
}


def branch_of_tag(tag: str) -> str:
    """Legacy: один ключ ветки по role_tag (лучше org_branches_of)."""
    return _TAG_TO_BRANCH.get(str(tag or ''), 'helper')


def org_branches_of(role_ids) -> list[str]:
    """Орг-ветки участника по Discord role IDs.

    В ветку попадают ТОЛЬКО grant или curator ЭТОЙ ветки.
    Master / Assistent без grant/curator → не засоряют Helper/Mod
    (идут в leadership / «Старшие»).
    """
    try:
        ids = {int(x) for x in (role_ids or []) if x is not None and str(x).isdigit()}
    except Exception:
        ids = set()
    if not ids:
        return []

    out: list[str] = []
    try:
        from services import staff_roles as SR
    except Exception:
        return []

    for kind in SR.POSITIONS:
        grant = int(SR.KNOWN_GRANT_BY_KIND.get(kind) or 0)
        curator = int(SR.KNOWN_CURATOR_BY_KIND.get(kind) or 0)
        if (grant and grant in ids) or (curator and curator in ids):
            if kind not in out:
                out.append(kind)

    if out:
        return out

    # Нет орг-grant/curator — старшие / админы в отдельный блок
    senior = {
        int(SR.KNOWN_MASTER_ROLE_ID),
        int(SR.KNOWN_ASSISTENT_ROLE_ID),
        int(SR.KNOWN_STAFF_ASSISTENT_ROLE_ID),
        int(SR.KNOWN_ADMIN_ROLE_ID),
        int(SR.KNOWN_STAFF_ADMIN_ROLE_ID),
    }
    if ids & senior:
        return ['leadership']

    common = int(getattr(SR, 'KNOWN_COMMON_STAFF_ROLE_ID', 0) or 0)
    if common and common in ids:
        # общая staff-роль без ветки — не угадываем Helper
        return ['leadership']

    return []


def person_org_branches(person: dict) -> list[str]:
    """Ветки человека: role_ids → branch из кэша → осторожный fallback по tag."""
    rids = person.get('role_ids') if isinstance(person, dict) else None
    branches = org_branches_of(rids or [])
    if branches:
        return branches
    # members_cache / staff_info уже знает орг-ветку (helper/moderators/…)
    raw_br = ''
    if isinstance(person, dict):
        raw_br = str(person.get('branch') or person.get('org_branch') or '').strip().lower()
    if raw_br:
        # staff_manager keys: moderators → moderator; leadership/admins
        alias = {
            'moderators': 'moderator',
            'mod': 'moderator',
            'helpers': 'helper',
            'admins': 'leadership',
            'admin': 'leadership',
            'senior': 'leadership',
            'старшие': 'leadership',
        }
        key = alias.get(raw_br, raw_br)
        if key in BRANCH_KEYS:
            return [key]
        if key in _TAG_TO_BRANCH:
            return [_TAG_TO_BRANCH[key]]
    role = ''
    tag = ''
    if isinstance(person, dict):
        role = str(person.get('role') or '')
        tag = str(person.get('role_tag') or role or '')
    # Прямые орг-теги (creative/event/…) — ок
    if tag in ('helper', 'mod', 'moderator', 'creative', 'broadcaster',
               'event', 'support', 'closemod'):
        return [branch_of_tag(tag)]
    # curator/master/assistent/admin без role_ids — НЕ в Helper
    if role in ('owner', 'admin', 'assistent', 'master', 'curator',
                'staff-admin', 'staff-assistent') or tag in (
            'owner', 'admin', 'staff-admin', 'staff-assistent', 'assistent',
            'master', 'curator'):
        return ['leadership']
    # нет ветки и нет ранга — не засоряем «Админы / старшие» скрытой оболочкой
    if not tag:
        return []
    return [branch_of_tag(tag)]


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


def resolve_span(span: str | None = None) -> dict[str, Any]:
    """День / текущая неделя (пн→сегодня) / 30 дней."""
    today = date.today()
    raw = (span or 'week').strip().lower()
    if raw in ('day', 'today', 'день'):
        keys = [str(today)]
        monday = today - timedelta(days=today.weekday())
        return {
            'span': 'day',
            'days': 1,
            'keys': keys,
            'label': 'сегодня',
            'range_label': today.strftime('%d.%m.%Y'),
            'week_end': (monday + timedelta(days=6)).strftime('%d.%m'),
        }
    if raw in ('month', 'месяц'):
        keys = [str(today - timedelta(days=i)) for i in range(30)]
        return {
            'span': 'month',
            'days': 30,
            'keys': keys,
            'label': 'месяц',
            'range_label': f'{(today - timedelta(days=29)).strftime("%d.%m")}–{today.strftime("%d.%m")}',
            'week_end': '',
        }
    # week (default): Monday → today (следить до конца недели)
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    keys: list[str] = []
    d = monday
    while d <= today:
        keys.append(str(d))
        d += timedelta(days=1)
    return {
        'span': 'week',
        'days': max(1, len(keys)),
        'keys': keys,
        'label': 'неделя',
        'range_label': f'{monday.strftime("%d.%m")}–{sunday.strftime("%d.%m")}',
        'week_end': sunday.strftime('%d.%m'),
    }


def voice_window_map(guild_id, days: int = 7,
                     date_keys: Optional[Iterable[str]] = None
                     ) -> dict[str, dict]:
    """uid -> {seconds, name, avatar} за окно дней / явные даты."""
    out: dict[str, dict] = {}
    try:
        from cogs.voice_tracker import voice_all
        raw = voice_all(guild_id) or {}
    except Exception:
        return out
    if date_keys is not None:
        keys = [str(k) for k in date_keys]
    else:
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


def messages_window_map(guild_id, days: int, staff_ids: set[str],
                        date_keys: Optional[Iterable[str]] = None
                        ) -> dict[str, int]:
    """Сообщения staff за окно: message_stats + mod_activity."""
    counts: dict[str, int] = {}
    if not staff_ids:
        return counts
    if date_keys is not None:
        key_set = set(str(k) for k in date_keys)
        days = max(1, len(key_set))
        # edge = earliest key 00:00 UTC-ish (local date string compare via iso)
        try:
            first = min(date.fromisoformat(k) for k in key_set)
            edge = datetime(first.year, first.month, first.day,
                            tzinfo=timezone.utc)
        except Exception:
            edge = datetime.now(timezone.utc) - timedelta(days=days)
    else:
        days = max(1, int(days))
        key_set = None
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
            if key_set is not None:
                if ts.astimezone().date().isoformat() not in key_set:
                    continue
            elif ts < edge:
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


def _bucket_summary(bucket: list[dict]) -> dict[str, Any]:
    return {
        'count': len(bucket),
        'active': sum(1 for x in bucket if int(x.get('score') or 0) > 0),
        'actions': sum(int(x['actions']) for x in bucket),
        'messages': sum(int(x['messages']) for x in bucket),
        'voice_s': sum(int(x['voice_s']) for x in bucket),
        'voice': fmt_voice(sum(int(x['voice_s']) for x in bucket)),
    }


def build_staff_board(
        *,
        guild_id,
        days: int = 7,
        people: list[dict],
        mod_rows: list[dict],
        hidden_kinds: set | list | None = None,
        span: str | None = None,
        date_keys: Optional[Iterable[str]] = None,
        include_zero: bool = True,
) -> dict[str, Any]:
    """Полная доска активности staff + ветки."""
    meta = resolve_span(span) if span else None
    if meta:
        days = int(meta['days'])
        keys = list(meta['keys'])
        span_name = meta['span']
        range_label = meta['range_label']
        span_label = meta['label']
    else:
        days = max(1, min(30, int(days or 7)))
        keys = list(date_keys) if date_keys is not None else [
            str(date.today() - timedelta(days=i)) for i in range(days)
        ]
        span_name = 'custom'
        span_label = f'{days} дн.'
        range_label = ''

    hidden = set(hidden_kinds or ())
    people = list(people or [])
    staff_ids = {str(p.get('id')) for p in people if str(p.get('id') or '').isdigit()}
    by_id = {str(p.get('id')): p for p in people if str(p.get('id') or '').isdigit()}

    mods = {}
    for m in mod_rows or []:
        uid = str(m.get('id') or '')
        if uid.isdigit():
            mods[uid] = m

    voice = voice_window_map(guild_id, days, date_keys=keys)
    msgs = messages_window_map(guild_id, days, staff_ids, date_keys=keys)

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
        score = actions * 12 + messages + (voice_s // 60)
        if (not include_zero
                and score <= 0 and actions <= 0
                and messages <= 0 and voice_s <= 0):
            continue
        tag = str(p.get('role_tag') or p.get('role') or 'helper')
        rids = p.get('role_ids') or []
        branches = person_org_branches(p)
        primary = branches[0] if branches else branch_of_tag(tag)
        rows.append({
            'id': uid,
            'name': p.get('name') or m.get('name') or (voice.get(uid) or {}).get('name') or uid,
            'handle': p.get('handle') or '',
            'avatar': p.get('avatar') or (voice.get(uid) or {}).get('avatar') or '',
            'role': p.get('role') or '',
            'role_tag': tag,
            'role_label': p.get('role_label') or ROLE_TITLE.get(tag, tag),
            'role_ids': list(rids) if rids else [],
            'branches': branches,
            'branch': primary,
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

    # Только текущий staff из people — без «призраков» из старой mod_activity
    rows.sort(key=lambda r: (-int(r['score']), -int(r['actions']),
                             -int(r['messages']), -int(r['voice_s']),
                             str(r['name']).lower()))
    max_score = max((int(r['score']) for r in rows), default=1) or 1
    for i, r in enumerate(rows, 1):
        r['rank'] = i
        r['place'] = i
        r['bar'] = max(4, int(round(100 * int(r['score']) / max_score)))

    by_role: dict[str, list] = {}
    by_branch: dict[str, list] = {}
    for r in rows:
        by_role.setdefault(r['role_tag'], []).append(r)
        for bk in (r.get('branches') or [r.get('branch') or 'helper']):
            by_branch.setdefault(str(bk), []).append(r)

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

    # иерархия внутри ветки: админ → ассистент → куратор → мастер → стафф
    _rank_order = {
        'owner': 0, 'staff-admin': 1, 'admin': 2,
        'staff-assistent': 3, 'assistent': 4,
        'curator': 5, 'master': 6,
        'mod': 7, 'helper': 8,
        'creative': 8, 'broadcaster': 8, 'event': 8,
        'support': 8, 'closemod': 8,
    }

    def _hier_key(r):
        tag = str(r.get('role_tag') or r.get('role') or '')
        return (
            _rank_order.get(tag, 50),
            -int(r.get('score') or 0),
            str(r.get('name') or '').lower(),
        )

    branches = []
    for key, title, _tags in BRANCH_GROUPS:
        # КОПИИ строк — иначе rank/bar ветки портят общий рейтинг
        bucket = [dict(x) for x in (by_branch.get(key) or [])]
        people_in = [p for p in people if key in person_org_branches(p)]
        if not bucket and not people_in:
            continue
        seen = {str(x['id']) for x in bucket}
        for p in people_in:
            pid = str(p.get('id') or '')
            if not pid or pid in seen:
                continue
            if not include_zero:
                continue
            tag = str(p.get('role_tag') or p.get('role') or 'helper')
            bucket.append({
                'id': pid,
                'name': p.get('name') or pid,
                'handle': p.get('handle') or '',
                'avatar': p.get('avatar') or '',
                'role': p.get('role') or '',
                'role_tag': tag,
                'role_label': p.get('role_label') or ROLE_TITLE.get(tag, tag),
                'role_ids': list(p.get('role_ids') or []),
                'branches': person_org_branches(p),
                'branch': key,
                'actions': 0, 'warns': 0, 'mutes': 0, 'kicks': 0, 'bans': 0,
                'messages': 0, 'voice_s': 0, 'voice': '0 мин', 'score': 0,
                'rank': 0, 'place': 0, 'bar': 4,
            })
        bucket.sort(key=_hier_key)
        bmax = max((int(r['score']) for r in bucket), default=1) or 1
        for i, r in enumerate(bucket, 1):
            r['rank'] = i
            r['place'] = i
            r['bar'] = max(4, int(round(100 * int(r['score']) / bmax)))
        sm = _bucket_summary(bucket)
        branches.append({
            'key': key,
            'title': title,
            'rows': bucket,
            'top': [x for x in bucket if int(x.get('score') or 0) > 0][:5],
            **sm,
        })
        by_branch[key] = bucket

    active_rows = [r for r in rows if int(r.get('score') or 0) > 0]
    # место в общем списке — строго 1..n по score (после веток!)
    for i, r in enumerate(active_rows, 1):
        r['rank'] = i
        r['place'] = i
    summary = {
        'staff_active': len(active_rows),
        'staff_total': len(staff_ids),
        'actions': sum(int(r['actions']) for r in rows),
        'messages': sum(int(r['messages']) for r in rows),
        'voice_s': sum(int(r['voice_s']) for r in rows),
        'voice': fmt_voice(sum(int(r['voice_s']) for r in rows)),
        'days': days,
        'span': span_name,
        'span_label': span_label,
        'range_label': range_label,
    }
    return {
        'summary': summary,
        'rows': active_rows,
        'podium': active_rows[:3],
        'role_tops': role_tops,
        'by_role': by_role,
        'by_branch': by_branch,
        'branches': branches,
    }
