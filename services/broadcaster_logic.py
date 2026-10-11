# -*- coding: utf-8 -*-
"""Чистая логика Broadcaster: даты, права, пожелания, доступ к своим трибунам."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

LOBBY_NAME = 'войти в лав руму'
ROOM_NAME = 'лав рума'
MAX_AHEAD_DAYS = 90


def zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo((name or '').strip() or 'Europe/Moscow')
    except Exception:
        return ZoneInfo('Europe/Moscow')


def channel_name(title: str) -> str:
    name = ' '.join((title or '').replace('\n', ' ').replace('\r', ' ').split())
    name = name.replace('#', '').strip()
    return (name or 'трибуна')[:100]


def parse_start(date_s: str, time_s: str, tz: ZoneInfo) -> tuple[Optional[datetime], str]:
    """Дата ДД.ММ.ГГГГ и время ЧЧ:ММ в часовом поясе сервера."""
    date_s = (date_s or '').strip()
    time_s = (time_s or '').strip().replace('.', ':').replace(' ', '')
    parsed = None
    for fmt in ('%d.%m.%Y', '%d.%m.%y', '%Y-%m-%d'):
        try:
            parsed = datetime.strptime(date_s, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        return None, 'Дата нужна в виде ДД.ММ.ГГГГ'
    try:
        clock = datetime.strptime(time_s, '%H:%M')
    except ValueError:
        return None, 'Время нужно в виде ЧЧ:ММ'
    try:
        local = datetime(
            parsed.year, parsed.month, parsed.day,
            clock.hour, clock.minute, tzinfo=tz,
        )
    except Exception:
        return None, 'Такой даты не бывает'
    return local, ''


def validate_start(local: datetime, now: datetime) -> str:
    if local.tzinfo is None or now.tzinfo is None:
        return 'Время без часового пояса'
    if local < now - timedelta(minutes=1):
        return 'Это время уже прошло'
    if local > now + timedelta(days=MAX_AHEAD_DAYS):
        return f'Слишком далеко: максимум {MAX_AHEAD_DAYS} дней'
    return ''


def member_is_broadcaster(role_ids: Iterable[int], broadcaster_role_id: int) -> bool:
    rid = int(broadcaster_role_id or 0)
    if not rid:
        return False
    return rid in {int(x) for x in (role_ids or []) if int(x or 0)}


def can_touch(actor_id: int, row: dict | None) -> tuple[bool, str]:
    if not row or (row.get('status') or '') == 'deleted':
        return False, 'Трибуна не найдена'
    if int(row.get('owner_id') or 0) != int(actor_id):
        return False, 'Можно управлять только своими трибунами'
    return True, ''


def can_edit_schedule(row: dict | None) -> tuple[bool, str]:
    if not row or (row.get('status') or '') == 'deleted':
        return False, 'Трибуна не найдена'
    if (row.get('status') or '') != 'scheduled':
        return False, 'Трибуна уже открыта — дату и время не меняем'
    return True, ''


def permission_plan(*, opened: bool, has_gender: bool) -> dict:
    """Кто что может до открытия и после.

    До старта канал скрыт. В момент старта его видно всем.
    Если гендерные роли заданы — заходить могут они.
    Если ролей нет — заходить может everyone, иначе трибуна останется закрытой.
    """
    host = {
        'view_channel': True,
        'connect': True,
        'speak': True,
        'mute_members': True,
        'move_members': True,
        'manage_channels': True,
        'request_to_speak': True,
    }
    bot = {
        'view_channel': True,
        'connect': True,
        'manage_channels': True,
        'move_members': True,
        'send_messages': True,
    }
    if not opened:
        return {
            'everyone': {'view_channel': False, 'connect': False, 'speak': False},
            'broadcaster': host,
            'bot': bot,
        }
    everyone_join = not has_gender
    plan = {
        'everyone': {
            'view_channel': True,
            'connect': everyone_join,
            'speak': everyone_join,
        },
        'broadcaster': host,
        'bot': bot,
    }
    if has_gender:
        plan['gender'] = {
            'view_channel': True,
            'connect': True,
            'speak': True,
            'request_to_speak': True,
        }
    return plan


def parse_hhmm(raw: str) -> tuple[int, int]:
    text = (raw or '').strip()
    hour_s, _, min_s = text.partition(':')
    hour, minute = int(hour_s), int(min_s or '0')
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(raw)
    return hour, minute


def wish_slot_key(now: datetime, hour: int, minute: int) -> str:
    return now.strftime('%Y-%m-%d') + f' {hour:02d}:{minute:02d}'


def due_wish_slots(
    now: datetime,
    times: Iterable[str],
    sent: Iterable[str],
    *,
    grace_minutes: int = 20,
) -> list[str]:
    """Слоты сегодня, чьё время уже наступило и ещё не вышло из окна."""
    sent_set = set(sent or [])
    due = []
    for raw in times or []:
        try:
            hour, minute = parse_hhmm(str(raw))
        except Exception:
            continue
        start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < start:
            continue
        if (now - start).total_seconds() > max(1, int(grace_minutes)) * 60:
            continue
        key = wish_slot_key(now, hour, minute)
        if key not in sent_set:
            due.append(key)
    return due


def pick_wish(
    messages: Iterable[str],
    deck: list | None,
    last: str | None,
    rng: random.Random | None = None,
) -> tuple[Optional[str], list, Optional[str]]:
    """Случайное пожелание без мгновенного повтора. Колода кончается — мешаем заново."""
    rng = rng or random
    pool = []
    seen = set()
    for item in messages or []:
        text = str(item or '').strip()
        if not text or text in seen:
            continue
        seen.add(text)
        pool.append(text)
    if not pool:
        return None, [], last
    fresh = [x for x in (deck or []) if x in seen]
    if not fresh:
        fresh = pool[:]
        rng.shuffle(fresh)
        if len(fresh) > 1 and last and fresh[-1] == last:
            fresh[0], fresh[-1] = fresh[-1], fresh[0]
    choice = fresh.pop()
    if last and choice == last and fresh:
        fresh.insert(0, choice)
        choice = fresh.pop()
    return choice, fresh, choice


def tribune_is_due(starts_at: str, now_utc: datetime, status: str) -> bool:
    if (status or '') != 'scheduled':
        return False
    try:
        start = datetime.fromisoformat(starts_at)
    except Exception:
        return False
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start <= now_utc.astimezone(timezone.utc)


def match_named_channel(names: Iterable[str], needles: Iterable[str]) -> Optional[str]:
    lowered = [(n, (n or '').lower()) for n in names]
    for needle in needles:
        n = (needle or '').lower()
        if not n:
            continue
        for original, low in lowered:
            if n in low:
                return original
    return None
