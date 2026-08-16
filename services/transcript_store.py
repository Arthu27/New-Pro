# -*- coding: utf-8 -*-
"""Хранилище транскриптов закрытых тикетов: запись при закрытии (ког/автозакрытие),
чтение и экспорт в панели.

До этого сервиса панель читала data/transcripts.json, в который НИКТО не писал —
страница транскриптов была вечно пустой. Теперь единый источник правды здесь:
ког и автозакрытие вызывают record(), панель — load/render.

Формат записи (data/transcripts.json — список, свежие в конце, кап 300):
    {
        'id': 'ticket-ivan-123 · 777',
        'guild_id': 777,
        'channel_name': 'ticket-ivan-123',
        'user_id': 123,
        'user_name': 'Иван',
        'category': 'Вопрос',
        'status': 'done',
        'claimed_by': None,
        'closed_by': 'moder',
        'opened_at': '...ISO aware...' | None,
        'closed_at': '...ISO aware...',
        'duration': '2 ч 5 мин',
        'messages': [
            {'timestamp': '...ISO aware...', 'author': 'Иван',
             'content': 'текст', 'is_bot': False}, ...
        ],
    }
"""

import html as _html
import json
import os
import re
from datetime import datetime, timedelta, timezone

from logger import get_logger

_log = get_logger("transcript_store")

PATH = 'data/transcripts.json'
MAX_RECORDS = 300
MAX_MESSAGE_LEN = 2000

_CAT_NAMES = {
    'sikayet': 'Жалоба',
    'soru': 'Вопрос',
    'teknik': 'Техническая проблема',
    'oneri': 'Предложение',
    'diger': 'Другое',
    'complaint': 'Жалоба',
    'question': 'Вопрос',
    'suggestion': 'Предложение',
    'other': 'Другое',
}


def category_label(category):
    """Человеческое имя категории (стейт хранит турецкие/английские ключи)."""
    if not category:
        return 'Без категории'
    return _CAT_NAMES.get(str(category).strip().lower(), str(category))


def _as_utc(dt):
    """Нормализация datetime к aware-UTC (наивные считаем UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_ts(value):
    """Терпимый разбор timestamp: ISO (в т.ч. с Z, наивные) -> aware datetime|None."""
    if isinstance(value, datetime):
        return _as_utc(value)
    if not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(str(value).replace('Z', '+00:00')))
    except (ValueError, TypeError) as _ex:
        _log.debug("_parse_ts(): нераспарсенный timestamp %r: %s", value, _ex)
        return None


def fmt_ts(dt):
    return _as_utc(dt).strftime('%d.%m.%Y %H:%M')


def human_duration(seconds):
    """Секунды -> '2 ч 15 мин' / '45 мин'."""
    try:
        seconds = max(0, int(seconds))
    except (TypeError, ValueError):
        return '0 мин'
    hours, minutes = divmod(seconds // 60, 60)
    if hours and minutes:
        return f'{hours} ч {minutes} мин'
    if hours:
        return f'{hours} ч'
    return f'{minutes} мин'


# ── Хранилище ─────────────────────────────────────────────────────────────

def load():
    """Прочитать все транскрипты (список). Битый/не-список JSON — как пусто."""
    if not os.path.exists(PATH):
        return []
    try:
        with open(PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as _ex:
        _log.debug("load(): битый файл, считаем пустым: %s", _ex)
        return []
    if not isinstance(data, list):
        return []
    return [t for t in data if isinstance(t, dict)]


def _save_all(records):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(records[-MAX_RECORDS:], f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)


def record(*, guild_id, channel_id, channel_name, user_id=None, user_name=None,
           category=None, status=None, claimed_by=None, closed_by=None,
           opened_at=None, closed_at=None, messages=()):
    """Сохранить транскрипт закрытого тикета. Возвращает запись.

    messages — iterable dict'ов с ключами timestamp/author/content/is_bot;
    timestamp может быть datetime или ISO-строкой. Ошибки нормализации
    отдельных сообщений не роняют запись целиком.
    """
    closed_dt = _parse_ts(closed_at) or datetime.now(timezone.utc)
    opened_dt = _parse_ts(opened_at)
    duration = human_duration((closed_dt - opened_dt).total_seconds()) if opened_dt else '—'

    msgs = []
    for m in messages or ():
        try:
            ts = _parse_ts(m.get('timestamp'))
            content = str(m.get('content') or '')[:MAX_MESSAGE_LEN]
            if not content.strip():
                continue
            msgs.append({
                'timestamp': ts.isoformat() if ts else '',
                'author': str(m.get('author') or 'Неизвестный'),
                'content': content,
                'is_bot': bool(m.get('is_bot')),
            })
        except Exception as _ex:  # одно битое сообщение не должно ронять транскрипт
            _log.debug("record(): пропущено битое сообщение: %s", _ex)
            continue

    rec = {
        'id': f'{channel_name} · {channel_id}',
        'guild_id': guild_id,
        'channel_name': channel_name,
        'user_id': user_id,
        'user_name': user_name or 'Неизвестный',
        'category': category_label(category),
        'status': status,
        'claimed_by': claimed_by,
        'closed_by': closed_by or 'Неизвестный',
        'opened_at': opened_dt.isoformat() if opened_dt else None,
        'closed_at': closed_dt.isoformat(),
        'duration': duration,
        'messages': msgs,
    }
    records = load()
    records.append(rec)
    _save_all(records)
    _log.info("record(): транскрипт %s сохранён (%d сообщений)", rec['id'], len(msgs))
    return rec


# ── Фильтры для панели ────────────────────────────────────────────────────

def _norm(text):
    return str(text or '').strip().lower()


def filter_records(records, search='', days='', category=''):
    """Применить фильтры поиска/периода/категории (все необязательные).
    Странные значения (days='abc') фильтр мягко игнорирует, а не роняет запрос."""
    search = _norm(search)
    category = _norm(category)
    days_i = None
    if days not in ('', None):
        try:
            days_i = int(days)
        except (TypeError, ValueError):
            _log.debug("filter_records(): странный days=%r — игнорирую", days)
    out = []
    for t in records:
        if category and _norm(t.get('category')) != category:
            continue
        if days_i:
            closed_dt = _parse_ts(t.get('closed_at'))
            if not closed_dt or closed_dt < datetime.now(timezone.utc) - timedelta(days=days_i):
                continue
        if search:
            hay = (str(t.get('id', '')), t.get('user_name', ''),
                   t.get('channel_name', ''), t.get('category', ''))
            if not any(search in _norm(field) for field in hay):
                continue
        out.append(t)
    out.sort(key=lambda x: str(x.get('closed_at', '')), reverse=True)
    return out


def summary(t):
    """Лёгкая проекция записи для списка (без массива сообщений)."""
    return {
        'id': t.get('id'),
        'user_name': t.get('user_name', 'Неизвестный'),
        'category': t.get('category', 'Без категории'),
        'closed_at': t.get('closed_at', ''),
        'closed_by': t.get('closed_by', ''),
        'channel_name': t.get('channel_name', ''),
        'message_count': len(t.get('messages') or []),
        'duration': t.get('duration', '—'),
    }


def find(records, transcript_id):
    tid = str(transcript_id)
    for t in records:
        if str(t.get('id')) == tid:
            return t
    return None


# ── Экспорт ───────────────────────────────────────────────────────────────

_SAFE_ID = re.compile(r'[^0-9A-Za-zА-Яа-я_.-]+')


def export_filename(t, ext):
    base = _SAFE_ID.sub('_', str(t.get('channel_name') or t.get('id') or 'ticket')).strip('_')
    base = re.sub(r'_+', '_', base) or 'ticket'
    return f'{base}_transcript.{ext}'


def render_txt(t):
    """Плоский текст транскрипта (для файла-вложения)."""
    lines = [f"Транскрипт тикета {t.get('channel_name') or t.get('id')}",
             f"Пользователь: {t.get('user_name', 'Неизвестный')}",
             f"Категория: {t.get('category', 'Без категории')}",
             f"Открыт: {t.get('opened_at') or '—'}",
             f"Закрыт: {t.get('closed_at', '')} · закрыл: {t.get('closed_by', 'Неизвестный')}",
             '=' * 80, '']
    for msg in t.get('messages') or []:
        stamp = msg.get('timestamp') or ''
        parsed = _parse_ts(stamp)
        if parsed:
            stamp = fmt_ts(parsed)
        lines.append(f"[{stamp}] {msg.get('author', 'Неизвестный')}:")
        lines.append(msg.get('content', ''))
        lines.append('')
    return '\n'.join(lines)


_CSS = """
body{margin:0;padding:32px 16px;background:#0f0d0a;color:#efe9dc;
font-family:'Segoe UI',system-ui,-apple-system,sans-serif}
.wrap{max-width:860px;margin:0 auto}
.head{background:linear-gradient(165deg,#1d1810,#14100b);border:1px solid #2c2415;
border-radius:14px;padding:20px 22px;margin-bottom:20px}
.head h1{margin:0 0 10px;font-size:20px;color:#f2b33d}
.meta{display:flex;flex-wrap:wrap;gap:8px 18px;font-size:12.5px;color:#a99e83}
.meta b{color:#e8ddc4;font-weight:600}
.msg{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.09);
border-radius:10px;padding:12px 14px;margin-bottom:10px}
.msg.bot{background:rgba(242,179,61,.06);border-color:rgba(242,179,61,.25)}
.top{display:flex;justify-content:space-between;gap:12px;margin-bottom:5px}
.who{font-weight:600;font-size:13px}
.msg.bot .who{color:#f2b33d}
.msg.bot .who::after{content:'БОТ';margin-left:8px;font-size:10px;letter-spacing:.06em;
border:1px solid rgba(242,179,61,.4);border-radius:4px;padding:1px 5px;color:#f2b33d}
.when{font-size:11px;color:#8d8371}
.body{font-size:13.5px;line-height:1.55;white-space:pre-wrap;word-break:break-word}
.foot{margin-top:22px;font-size:11.5px;color:#6f6653;text-align:center}
@media print{body{background:#fff;color:#222;padding:0}
.head,.msg{border-color:#ddd;background:#fff}
.head h1,.msg.bot .who{color:#8a6514}.meta{color:#555}.when,.foot{color:#777}}
"""


def render_html(t):
    """Автономный HTML транскрипта: дискорд-тёмный, без внешних URL, XSS-safe."""
    e = _html.escape
    title = str(t.get('channel_name') or t.get('id') or 'тикет')
    opened = _parse_ts(t.get('opened_at'))
    closed = _parse_ts(t.get('closed_at'))
    meta = [
        ('Пользователь', t.get('user_name', 'Неизвестный')),
        ('Категория', t.get('category', 'Без категории')),
        ('Открыт', fmt_ts(opened) if opened else '—'),
        ('Закрыт', fmt_ts(closed) if closed else '—'),
        ('Закрыл', t.get('closed_by', 'Неизвестный')),
        ('Длительность', t.get('duration', '—')),
    ]
    msgs = t.get('messages') or []
    meta.append(('Сообщений', str(len(msgs))))

    parts = ['<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">',
             f'<title>Транскрипт {e(title)}</title>',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             f'<style>{_CSS}</style></head><body><div class="wrap">',
             f'<div class="head"><h1>Транскрипт · {e(title)}</h1><div class="meta">']
    for label, value in meta:
        parts.append(f'<span>{e(label)}: <b>{e(str(value))}</b></span>')
    parts.append('</div></div>')

    for msg in msgs:
        cls = 'msg bot' if msg.get('is_bot') else 'msg'
        parsed = _parse_ts(msg.get('timestamp'))
        stamp = fmt_ts(parsed) if parsed else ''
        parts.append(
            f'<div class="{cls}"><div class="top">'
            f'<span class="who">{e(str(msg.get("author", "Неизвестный")))}</span>'
            f'<span class="when">{e(stamp)}</span></div>'
            f'<div class="body">{e(str(msg.get("content", "")))}</div></div>')

    parts.append('<div class="foot">Aether Panel · транскрипт закрытого тикета</div>')
    parts.append('</div></body></html>')
    return ''.join(parts)
