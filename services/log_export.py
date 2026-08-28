# -*- coding: utf-8 -*-
"""HTML-экспорт журнала модерации (audit_log.json -> портативный отчёт).

Источник — тот же data/audit_log.json, что кормит панель и мод-дайджест.
Все функции чистые: загрузка/фильтрация/рендер тестируются без Discord
и без Flask. Результат рендера — самодостаточный standalone HTML-файл
(тёмная тема, без внешних ресурсов), который модерация может приложить
к разбору, апелляции или показать «на бумаге».
"""
import html
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

from services.audit_labels import human_action

UTC = timezone.utc
DEFAULT_PATH = 'data/audit_log.json'

# Ключи, которые выводятся в отдельные колонки; остальные детали собираем
# в «прочие поля» строкой k=v.
_SKIP_DETAIL_KEYS = {
    'category', 'action', 'timestamp', 'guild_id',
    'mod_name', 'mod_id', 'moderator', 'moderator_id',
    'target_name', 'target_id', 'user_name', 'user_id', 'member_name', 'member_id',
}
_MAX_EVENTS = 2000  # защита от гигантского html


def parse_ts(text):
    """ISO-метка -> aware datetime; мусор -> None."""
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def load_events(guild_id, path=DEFAULT_PATH):
    """События гильдии из audit_log.json; битый/отсутствующий файл -> []."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, dict):
        return []
    events = data.get(str(guild_id), [])
    return [ev for ev in events if isinstance(ev, dict)] if isinstance(events, list) else []


def filter_events(events, days=None, category=None, mod=None, query=None, now=None):
    """Отфильтровать события: период, категория, модератор (подстрока),
    произвольный текст (по действию/цели/причине/деталям)."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    since = None
    try:
        if days:
            since = now - timedelta(days=max(1, int(days)))
    except (TypeError, ValueError):
        since = None
    category_l = str(category or '').strip().lower() or None
    mod_l = str(mod or '').strip().lower() or None
    query_l = str(query or '').strip().lower() or None

    out = []
    for ev in events or []:
        ts = parse_ts(ev.get('timestamp'))
        if since and (ts is None or ts < since):
            continue
        if category_l and str(ev.get('category') or '').strip().lower() != category_l:
            continue
        if mod_l and mod_l not in str(ev.get('mod_name') or '').lower():
            continue
        if query_l and query_l not in event_haystack(ev):
            continue
        out.append(ev)
    return out[-_MAX_EVENTS:]


def event_haystack(ev):
    """Всё текстовое содержимое события одной строкой (для поиска)."""
    return ' '.join(str(v) for v in ev.values()).lower()


def row_fields(ev):
    """(время, категория, действие, модератор, цель, прочие) для таблицы."""
    ts = parse_ts(ev.get('timestamp'))
    when = ts.strftime('%d.%m.%Y %H:%M UTC') if ts else str(ev.get('timestamp') or '—')
    moderator = str(ev.get('mod_name') or ev.get('mod_id') or ev.get('moderator') or '—')
    target = str(ev.get('target_name') or ev.get('target_id') or ev.get('user_name')
                 or ev.get('user_id') or ev.get('member_name') or ev.get('member_id') or '—')
    extra = '; '.join(f'{k}={v}' for k, v in ev.items() if k not in _SKIP_DETAIL_KEYS and v not in (None, ''))
    # сырые коды старых записей (bot_add и т.п.) — по-русски и в экспорте
    return when, str(ev.get('category') or 'прочее'), human_action(ev.get('action') or '?'), moderator, target, extra or '—'


_PAGE_CSS = """
:root{color-scheme:dark}
* {box-sizing:border-box;margin:0;padding:0}
body {background:#0f1117;color:#e6e9f0;font:14px/1.55 system-ui,'Segoe UI',Roboto,sans-serif;padding:32px}
.wrap {max-width:1100px;margin:0 auto}
h1 {font-size:24px;font-weight:800;letter-spacing:.2px}
.sub {color:#8b93a7;margin-top:6px;font-size:13px}
.stats {display:flex;flex-wrap:wrap;gap:10px;margin:22px 0}
.chip {background:#171b26;border:1px solid #262c3d;border-radius:12px;padding:10px 16px;font-weight:700}
.chip small {display:block;color:#8b93a7;font-weight:600;font-size:11px;letter-spacing:.4px;text-transform:uppercase}
table {width:100%;border-collapse:collapse;background:#141824;border:1px solid #232a3b;border-radius:14px;overflow:hidden}
thead th {background:#171b26;color:#9aa3b8;text-align:left;font-size:11px;letter-spacing:.6px;text-transform:uppercase;padding:10px 12px}
tbody td {padding:10px 12px;border-top:1px solid #1f2534;vertical-align:top;word-break:break-word}
tbody tr:nth-child(even){background:#12151f}
.cat {display:inline-block;background:#222b45;color:#b8c5ff;border-radius:999px;padding:2px 12px;font-size:12px;font-weight:700;white-space:nowrap}
.act {font-weight:700;color:#ffd166;white-space:nowrap}
.muted {color:#8b93a7}
.empty {padding:48px;text-align:center;color:#8b93a7}
footer {margin-top:18px;color:#5d6579;font-size:12px;text-align:center}
@media print{body{background:#fff;color:#000;padding:12px}.chip,table{filter:grayscale(1)}}
"""


def render_html(events, guild_name='', filters_desc='', generated_at=None):
    """Самодостаточный HTML-отчёт (str). Новые события — сверху."""
    generated_at = generated_at or datetime.now(UTC)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    per_category = Counter(str(ev.get('category') or 'прочее') for ev in events)
    per_mod = Counter(str(ev.get('mod_name') or '') for ev in events if ev.get('mod_name'))

    chips = [f'<div class="chip"><small>Всего событий</small>{len(events)}</div>']
    for cat, n in per_category.most_common(12):
        chips.append(f'<div class="chip"><small>{html.escape(cat)}</small>{n}</div>')
    top_mods = ', '.join(f'{html.escape(m)} ({n})' for m, n in per_mod.most_common(5))

    rows_html = []
    for ev in reversed(events):
        when, cat, act, mod, target, extra = row_fields(ev)
        rows_html.append(
            '<tr>'
            f'<td class="muted" style="white-space:nowrap">{html.escape(when)}</td>'
            f'<td><span class="cat">{html.escape(cat)}</span></td>'
            f'<td class="act">{html.escape(act)}</td>'
            f'<td>{html.escape(mod)}</td>'
            f'<td>{html.escape(target)}</td>'
            f'<td class="muted">{html.escape(extra)}</td>'
            '</tr>'
        )
    body = '\n'.join(rows_html) if rows_html else '<tr><td colspan="6" class="empty">За выбранный период событий нет</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Журнал модерации — {html.escape(guild_name or 'сервер')}</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>Журнал модерации</h1>
  <div class="sub">{html.escape(guild_name or 'Сервер')} · сформировано {html.escape(generated_at.strftime('%d.%m.%Y %H:%M UTC'))}{' · ' + html.escape(filters_desc) if filters_desc else ''}</div>
  <div class="stats">{''.join(chips)}</div>
  {f'<p class="sub" style="margin-bottom:14px">Активные модераторы: {top_mods}</p>' if top_mods else ''}
  <table>
    <thead><tr><th>Время</th><th>Категория</th><th>Действие</th><th>Модератор</th><th>Цель</th><th>Детали</th></tr></thead>
    <tbody>
{body}
    </tbody>
  </table>
  <footer>Hakumo · выгрузка audit_log · файл автономный, открывается в любом браузере</footer>
</div>
</body>
</html>"""


def export_filename(guild_name='server', now=None):
    """Имя файла вида modlog_гильдия_2026-08-17.html (только безопасные символы)."""
    now = now or datetime.now(UTC)
    safe = ''.join(ch if (ch.isalnum() or ch in '-') else '_' for ch in str(guild_name or 'server'))
    while '__' in safe:
        safe = safe.replace('__', '_')
    safe = safe.strip('_')[:40] or 'server'
    return f'modlog_{safe}_{now.strftime("%Y-%m-%d")}.html'
