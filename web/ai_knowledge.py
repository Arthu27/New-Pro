# -*- coding: utf-8 -*-
"""База знаний ИИ о панели Aether и боте.

Один источник правды для всех AI-промптов (чат-ког, тикеты, панельный AI):
- роли панели (включая Куратора);
- полная карта разделов и страниц панели — генерируется из
  services.panel_menu.MENU, поэтому обновляется автоматически
  при добавлении страниц (ничего вручную не дублируем);
- краткая справка о боте.

Тексты кешируются на минуту, чтобы не пересобирать MENU на каждый запрос.
"""

import os
import time

from logger import get_logger

_log = get_logger("ai_knowledge")

ROLE_LABELS = {
    'uye': 'Участник',
    'mod': 'Модератор',
    'curator': 'Куратор',
    'admin': 'Администратор',
    'owner': 'Владелец',
}

ROLE_ORDER = ('uye', 'mod', 'curator', 'admin', 'owner')

ROLE_DESCRIPTIONS = {
    'uye': 'обычный участник — только своя заявка в команду и AI-чат',
    'mod': 'модератор — модерация, участники, логи, AI',
    'curator': 'куратор — старший модератор: всё модерское + тикеты и сообщество',
    'admin': 'администратор — почти всё, кроме настроек владельца',
    'owner': 'владелец — полный доступ ко всему',
}

_cache = {}
_CACHE_TTL = 60.0


def _menu_snapshot():
    """Список (key, название группы, [(path, label), ...]) из живого MENU."""
    try:
        import sys
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if repo not in sys.path:
            sys.path.insert(0, repo)
        from services.panel_menu import MENU
        groups = []
        for g in MENU:
            pages = [(p.get('path', ''), p.get('label', ''))
                     for p in g.get('pages', [])]
            groups.append((g.get('key', ''), g.get('group', ''), pages))
        return groups
    except Exception as _ex:
        _log.debug("_menu_snapshot(): подавлено: %s", _ex)
        return []


def _cached(key):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    return None


def _store(key, text):
    _cache[key] = (time.time(), text)
    return text


def build_panel_knowledge(compact=False, full_menu=True):
    """Полная справка о панели для системного промпта ИИ.

    compact=True — страницы разделов перечисляются одной строкой на раздел;
    full_menu=False — только названия разделов без списка страниц.
    """
    key = ('panel', bool(compact), bool(full_menu))
    hit = _cached(key)
    if hit is not None:
        return hit

    lines = [
        'Ты — ИИ-помощник сервера, который РАЗБИРАЕТСЯ в веб-панели Aether и боте.',
        'Вот полная справка (используй её, отвечая на вопросы о панели, ролях и боте):',
        '',
        'РОЛИ ДОСТУПА ПАНЕЛИ (от младшей к старшей):',
    ]
    for r in ROLE_ORDER:
        lines.append(f'- {r} ({ROLE_LABELS[r]}) — {ROLE_DESCRIPTIONS[r]}')
    lines += [
        '',
        'КАК ВЫДАЮТСЯ РОЛИ: владелец открывает панель → «Доступ к панели» (/panel-access)',
        'и привязывает Discord-роль сервера к роли панели (участник/модератор/куратор/',
        'администратор/владелец). Там же настраивается, кому видны уведомления и лента активности.',
        'Куратор настраивается так же, как модератор и администратор: в «Доступ к меню»',
        '(/panel-menu) есть отдельная вкладка «Куратор».',
        '',
    ]
    groups = _menu_snapshot()
    if full_menu:
        lines.append(f'РАЗДЕЛЫ И СТРАНИЦЫ ПАНЕЛИ (всего {len(groups)} разделов):')
        for key_, label, pages in groups:
            lines.append(f'• {label} ({key_}):')
            if compact:
                lines.append('  ' + ', '.join(f'{lbl} ({path})' for path, lbl in pages))
            else:
                for path, lbl in pages:
                    lines.append(f'  - {lbl}: {path}')
    else:
        lines.append('ОСНОВНЫЕ РАЗДЕЛЫ ПАНЕЛИ: '
                     + ', '.join(lbl for _k, lbl, _p in groups) + '.')
    lines += [
        '',
        'ДРУГОЕ О ПАНЕЛИ:',
        '- Вход по логину/паролю или PIN; из Discord панель открывается командой /modpanel.',
        '- Адрес панели даёт владелец сервера; статус бота: /health.',
        '- Панель показывает реальные данные сервера: модерация, тикеты, экономика,',
        '  уровни, роли, музыка, статистика и т.д.',
        '- НЕ выдумывай ссылки и страницы: сверяйся со списком выше.',
    ]
    return _store(key, '\n'.join(lines))


def build_panel_faq():
    """Короткая человекочитаемая справка для ответа участникам в чате."""
    key = ('faq',)
    hit = _cached(key)
    if hit is not None:
        return hit
    groups = _menu_snapshot()
    lines = [
        'Панель Aether — веб-управление сервером. Адрес даёт владелец, статус бота: /health.',
        '',
        'Роли доступа: Участник → Модератор → Куратор → Администратор → Владелец.',
        'Куратор — старший модератор: всё модерское + тикеты и сообщество. Владелец настраивает',
        'его в панели: «Доступ к панели» (привязка Discord-ролей к ролям панели) и',
        '«Доступ к меню» (отдельная вкладка «Куратор»).',
        '',
        'Разделы панели: ' + ', '.join(lbl for _k, lbl, _p in groups) + '.',
        '',
        'Популярное: варны и журнал — «Модерация»; тикеты — «Тикеты»;',
        'баланс, магазин и рейтинги — «Сообщество»; кому виден колокольчик уведомлений —',
        '«Доступ к панели» у владельца.',
    ]
    return _store(key, '\n'.join(lines))


def build_bot_summary():
    """Краткая справка о командах бота."""
    key = ('bot',)
    hit = _cached(key)
    if hit is not None:
        return hit
    return _store(key, (
        'БОТ AETHER (кратко): модерация (/warn, /moderate, /jail, /history, /watchlist), '
        'тикеты (/ticket), экономика с префиксом ! (!balance, !daily, !work, !shop, !top), '
        'уровни (!xp-rank, /leaderboard), музыка (!play), верификация, дни рождения '
        '(/birthday-set), дежурства (/duty-panel), реакционные роли, автомодерация. '
        'Полный справочник: напиши боту «команды» или «помощь».'
    ))
