# -*- coding: utf-8 -*-
"""«Автоматика» — страница панели для новых автономных модулей бота.

Карточки настроек четырёх когов: ночной режим, анти-альт, приветствия PRO,
мод-дайджест. Панель пишет настройки в те же SQLite-нейспейсы, которые
читают коги (GuildData <namespace>, key 'settings') — без файлов, без
перезапуска, одна точка правды. Валидация на обеих сторонах: merge_settings
каждого кога применён и здесь.
"""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _load_ai_tickets, _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, calculate_ai_ticket_stats, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone,
)

from cogs import anti_alt, night_mode, welcome_pro, mod_digest

# Реестр редактируемых модулей. kind: bool|int|select|text|channels|templates
MODULE_EDITORS = {
    'night_mode': {
        'title': 'Ночной режим',
        'icon': 'fa-moon',
        'desc': 'Слоумод и лок каналов по расписанию: утром всё возвращается.',
        'ns': 'night_mode',
        'merge': staticmethod(night_mode.merge_settings),
        'fields': [
            {'key': 'enabled', 'label': 'Включён', 'kind': 'bool'},
            {'key': 'start_hour', 'label': 'Начало ночи (час UTC)', 'kind': 'int',
             'min': 0, 'max': 23},
            {'key': 'end_hour', 'label': 'Конец ночи (час UTC)', 'kind': 'int',
             'min': 0, 'max': 23},
            {'key': 'slowmode_seconds', 'label': 'Слоумод ночью, сек (0 — не трогать)',
             'kind': 'int', 'min': 0, 'max': 21600},
            {'key': 'lock_channels', 'label': 'Лок каналов ночью', 'kind': 'bool'},
            {'key': 'report_channel_id', 'label': 'ID канала репортов (0 — авто)',
             'kind': 'int', 'min': 0},
        ],
    },
    'anti_alt': {
        'title': 'Анти-альт',
        'icon': 'fa-user-shield',
        'desc': 'Ловит свежесозданные аккаунты при входе на сервер.',
        'ns': 'anti_alt',
        'merge': staticmethod(anti_alt.merge_settings),
        'fields': [
            {'key': 'enabled', 'label': 'Включён', 'kind': 'bool'},
            {'key': 'min_age_days', 'label': 'Мин. возраст аккаунта, дней',
             'kind': 'int', 'min': 0, 'max': 3650},
            {'key': 'action', 'label': 'Действие', 'kind': 'select',
             'options': [('alert', 'Только тревога'), ('kick', 'Кик'),
                         ('ban', 'Бан')]},
            {'key': 'log_channel_id', 'label': 'ID канала карточек (0 — авто)',
             'kind': 'int', 'min': 0},
        ],
    },
    'welcome_pro': {
        'title': 'Приветствия PRO',
        'icon': 'fa-hand-sparkles',
        'desc': 'Ротируемые шаблоны приветствий + опциональное ЛС новичку. '
                'Переменные: {mention} {user} {server} {count}.',
        'ns': 'welcome_pro',
        'merge': staticmethod(welcome_pro.merge_settings),
        'fields': [
            {'key': 'enabled', 'label': 'Включены', 'kind': 'bool'},
            {'key': 'channel_id', 'label': 'ID канала приветствий (0 — авто)',
             'kind': 'int', 'min': 0},
            {'key': 'dm_enabled', 'label': 'ЛС новичкам', 'kind': 'bool'},
            {'key': 'dm_text', 'label': 'Текст ЛС', 'kind': 'text'},
            {'key': 'templates', 'label': 'Шаблоны (каждый с новой строки)',
             'kind': 'templates'},
        ],
    },
    'mod_digest': {
        'title': 'Мод-дайджест',
        'icon': 'fa-newspaper',
        'desc': 'Еженедельная сводка модерации для админов сервера.',
        'ns': 'mod_digest',
        'merge': staticmethod(mod_digest.merge_settings),
        'fields': [
            {'key': 'enabled', 'label': 'Включён', 'kind': 'bool'},
            {'key': 'channel_id', 'label': 'ID канала дайджеста', 'kind': 'int',
             'min': 0},
            {'key': 'hour_utc', 'label': 'Час отправки (UTC)', 'kind': 'int',
             'min': 0, 'max': 23},
        ],
    },
}


def _db(ns):
    from db import GuildData
    return GuildData(ns)


def _serialize(module_key, settings):
    """Настройки -> JSON-формат формы (списки -> строки textarea)."""
    out = {}
    for field in MODULE_EDITORS[module_key]['fields']:
        key = field['key']
        value = settings.get(key)
        if field['kind'] == 'templates':
            value = '\n'.join(value or [])
        out[key] = value
    return out


def _clean_payload(module_key, payload):
    """Вход из формы -> очищенные настройки (только разрешённые ключи)."""
    spec = MODULE_EDITORS[module_key]
    raw = {}
    for field in spec['fields']:
        key, kind = field['key'], field['kind']
        if key not in payload:
            continue
        value = payload[key]
        if kind == 'bool':
            raw[key] = bool(value)
        elif kind == 'int':
            try:
                value = int(value)
            except (TypeError, ValueError) as _ex:
                _log.debug('automation: поле %s не число (%r): %s', key, value, _ex)
                continue
            if 'min' in field:
                value = max(field['min'], value)
            if 'max' in field:
                value = min(field['max'], value)
            raw[key] = value
        elif kind == 'select':
            allowed = {v for v, _l in field['options']}
            if value in allowed:
                raw[key] = value
        elif kind == 'templates':
            rows = [t.strip()[:500] for t in str(value or '').splitlines()]
            raw[key] = [t for t in rows if t][:15]
        else:  # text
            raw[key] = str(value or '')[:500]
    return raw


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    @app.route('/automation')
    @login_required
    @role_required('admin')
    def automation_page():
        return render_template('automation.html',
                               role=session.get('role'),
                               username=session.get('username'))

    @app.route('/api/automation')
    @login_required
    @role_required('admin')
    def api_automation_index():
        gid = active_guild_id()
        out = {}
        for key, spec in MODULE_EDITORS.items():
            settings = spec['merge'](_db(spec['ns']).get(gid, 'settings', {}))
            out[key] = {
                'title': spec['title'], 'icon': spec['icon'], 'desc': spec['desc'],
                'fields': spec['fields'],
                'values': _serialize(key, settings),
            }
        return jsonify({'success': True, 'modules': out})

    @app.route('/api/automation/<module_key>', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_automation_save(module_key):
        spec = MODULE_EDITORS.get(module_key)
        if spec is None:
            return jsonify({'success': False,
                            'error': f'неизвестный модуль «{module_key}»'}), 404
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({'success': False, 'error': 'ожидался JSON-объект'}), 400
        gid = active_guild_id()
        store = _db(spec['ns'])
        current = spec['merge'](store.get(gid, 'settings', {}))
        current.update(_clean_payload(module_key, payload))
        merged = spec['merge'](current)  # финальная санитаризация — как в коге
        store.set(gid, 'settings', merged)

        meta = spec['title']
        try:
            _fire_panel_notification(
                'automation',
                f'Настройки «{meta}» обновлены',
                f'Через панель ({session.get("username", "?")}), сервер {gid}')
        except Exception as _ex:
            _log.debug('automation: уведомление не ушло: %s', _ex)
        return jsonify({'success': True,
                        'values': _serialize(module_key, merged)})
