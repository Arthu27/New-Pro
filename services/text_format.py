# -*- coding: utf-8 -*-
"""Русское форматирование текста — общий слой для когов, сервисов и панели.

До этого каждый модуль склонял слова и собирал «1 ч 5 мин» по-своему
(и местами турецкими единицами «dk/sa»). Теперь одна точка входа:

    plural_ru(5, 'минута', 'минуты', 'минут')      -> 'минут'
    fmt_seconds(3661)                              -> '1 ч 1 мин'
    fmt_seconds_short(3661)                        -> '1ч 1м'
    parse_duration('1ч 30м')                       -> 5400
    parse_deadline('через 2ч', now)                -> aware datetime
    rel_time(future, now)                          -> 'через 2 ч'
    clamp_text(str, 1024)                          -> строка не длиннее лимита

Всё чистые функции (без Discord/БД) — покрыты tests/test_text_format.py.
Метки времени — только aware UTC (datetime.now(timezone.utc)).
"""
import re
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

_WORD_RE = re.compile(r'\d+|[a-zA-Zа-яА-ЯёЁ]+')


# ─── склонения ──────────────────────────────────────────────────────────────

def plural_ru(n, one, few, many):
    """Выбрать форму слова для числа n: (1) минута / (3) минуты / (5) минут.

    n приводится к abs(int) — отрицательные и строки-числа тоже работают.
    Мусор на входе -> форма many (самая безопасная для «0/неизвестно»).
    """
    try:
        n = abs(int(n))
    except (TypeError, ValueError):
        return many
    if n % 100 in range(11, 15):
        return many
    last = n % 10
    if last == 1:
        return one
    if last in (2, 3, 4):
        return few
    return many


def spell(n, one, few, many):
    """Число + склонённая форма: spell(3, 'день', 'дня', 'дней') -> '3 дня'."""
    return f'{n} {plural_ru(n, one, few, many)}'


# ─── длительности ───────────────────────────────────────────────────────────

def fmt_seconds(sec):
    """Секунды -> '1 д 2 ч 5 мин' (до 3 значащих единиц, нули пропускаются).

    Осознанно отличается от cogs.voice_tracker.fmt_duration (та — «часы+мин»
    для таблиц войса): эта — универсальная, с днями и склонениями.
    """
    try:
        sec = int(sec)
    except (TypeError, ValueError):
        sec = 0
    if sec < 0:
        sec = 0
    if sec == 0:
        return '0 сек'
    days, rem = divmod(sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(spell(days, 'день', 'дня', 'дней'))
    if hours:
        parts.append(spell(hours, 'час', 'часа', 'часов'))
    if minutes:
        parts.append(spell(minutes, 'минута', 'минуты', 'минут'))
    if seconds and not days:
        # секунды показываем только для сроков короче суток — иначе шум
        parts.append(spell(seconds, 'секунда', 'секунды', 'секунд'))
    return ' '.join(parts[:3])


def fmt_seconds_short(sec):
    """Секунды -> '1д 2ч 5м' — компактный вариант для узких эмбедов."""
    try:
        sec = max(0, int(sec))
    except (TypeError, ValueError):
        sec = 0
    if sec == 0:
        return '0с'
    days, rem = divmod(sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f'{days}д')
    if hours:
        parts.append(f'{hours}ч')
    if minutes:
        parts.append(f'{minutes}м')
    if seconds and not days:
        parts.append(f'{seconds}с')
    return ' '.join(parts[:3])


# ─── парсинг сроков ─────────────────────────────────────────────────────────

_UNIT_SECONDS = {
    # русские
    'с': 1, 'сек': 1, 'секунда': 1, 'секунды': 1, 'секунд': 1,
    'м': 60, 'мин': 60, 'минута': 60, 'минуты': 60, 'минут': 60,
    'ч': 3600, 'час': 3600, 'часа': 3600, 'часов': 3600,
    'д': 86400, 'день': 86400, 'дня': 86400, 'дней': 86400,
    'нед': 604800, 'неделя': 604800, 'недели': 604800, 'недель': 604800,
    'мес': 2592000, 'месяц': 2592000, 'месяца': 2592000, 'месяцев': 2592000,
    # английские (короткие)
    's': 1, 'sec': 1, 'secs': 1, 'second': 1, 'seconds': 1,
    'min': 60, 'mins': 60, 'minute': 60, 'minutes': 60,
    'h': 3600, 'hr': 3600, 'hrs': 3600, 'hour': 3600, 'hours': 3600,
    'w': 604800, 'week': 604800, 'weeks': 604800,
    'mo': 2592000, 'month': 2592000, 'months': 2592000,
}
# английские короткие буквы, не совпадающие с русскими
_UNIT_SECONDS['m'] = 60
_UNIT_SECONDS['d'] = 86400

_DURATION_RE = re.compile(
    r'(\d+)\s*([a-zA-Zа-яА-ЯёЁ]+)', re.IGNORECASE)


def parse_duration(text):
    """'1ч 30м' / '2 дня' / '45' -> секунды. None, если разобрать не удалось.

    Голое число трактуется как секунды. Единицы русские и английские,
    несколько групп складываются: '1 день 2 часа' -> 93600.
    """
    if text is None:
        return None
    text = str(text).strip().lower()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total = 0
    matched = False
    for num, unit in _DURATION_RE.findall(text):
        mult = _UNIT_SECONDS.get(unit.lower())
        if mult is None:
            return None  # неизвестная единица — весь парсинг недоверенный
        total += int(num) * mult
        matched = True
    return total if (matched and total > 0) else None


def parse_deadline(text, now=None):
    """Текст -> aware UTC datetime: 'через 5м', '5м', '18:30', '2026-08-13 18:30'.

    'через X' / голая длительность — относительно now. 'ЧЧ:ММ' — ближайшее
    такое время в будущем (сегодня или завтра). None, если ничего не подошло.
    """
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    text = str(text or '').strip().lower()
    if not text:
        return None

    rel = text
    if rel.startswith('через '):
        rel = rel[6:].strip()
    seconds = parse_duration(rel)
    if seconds:
        return now + timedelta(seconds=seconds)

    m = re.fullmatch(r'(\d{1,2})[.:](\d{2})', text)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        if 0 <= hh < 24 and 0 <= mm < 60:
            candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            return candidate

    m = re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})[ т](\d{1,2})[.:](\d{2})', text)
    if m:
        try:
            candidate = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                 int(m.group(4)), int(m.group(5)), tzinfo=UTC)
        except ValueError:
            return None
        return candidate if candidate > now else None
    return None


# ─── относительное время ────────────────────────────────────────────────────

def rel_time(moment, now=None):
    """'(в) 5 мин назад' / 'через 2 ч' — человеческая относительная метка."""
    now = now or datetime.now(UTC)
    if isinstance(moment, str):
        try:
            moment = datetime.fromisoformat(moment)
        except ValueError:
            return '?'
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    delta = (moment - now).total_seconds()
    suffix = 'назад' if delta < 0 else ''
    body = fmt_seconds(abs(int(delta)))
    return f'{body} {suffix}'.strip() if suffix else f'через {body}'


# ─── прочее ─────────────────────────────────────────────────────────────────

def clamp_text(text, limit=1024, tail='…'):
    """Обрезать текст до limit символов (для embed-полей Discord)."""
    text = str(text if text is not None else '')
    if limit <= 0:
        return ''
    if len(text) <= limit:
        return text
    return text[:max(0, limit - len(tail))] + tail


def extract_words(text):
    """Слова и числа из текста — для анализа/рекапов без стоп-символов."""
    return _WORD_RE.findall(str(text or '').lower())
