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

from cogs import anti_alt, night_mode, welcome_pro, mod_digest, server_stats, night_summary

from datetime import timedelta

from json_store import load_json as _js_load, save_json as _js_save

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
    'server_stats': {
        'title': 'Каналы-счётчики',
        'icon': 'fa-chart-simple',
        'desc': 'Имена каналов с живой статистикой («Участники: {members}»). '
                'Переменные: {members} {bots} {people} {channels} {text} '
                '{voice} {roles} {boosts} {online}.',
        'ns': 'server_stats',
        'merge': staticmethod(server_stats.merge_settings),
        'fields': [
            {'key': 'enabled', 'label': 'Включены', 'kind': 'bool'},
            {'key': 'channels', 'label': 'Счётчики (каждый с новой строки)',
             'kind': 'counters'},
        ],
    },
}


def parse_counters(text):
    """Текст 'ID | шаблон' построчно -> (каналы {cid: шаблон}, замечания [str]).

    Правила 1:1 с cmd_add кога server_stats: шаблон обязан содержать
    переменную ('{'), режется до 80 символов, ID канала — только цифры.
    Текст — это ПОЛНОЕ желаемое состояние (как textarea у шаблонов).
    """
    channels = {}
    issues = []
    for ln, raw in enumerate(str(text or '').splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if '|' not in line:
            issues.append('строка %d: нет разделителя «|»' % ln)
            continue
        cid, tpl = (p.strip() for p in line.split('|', 1))
        if not cid.isdigit():
            issues.append('строка %d: ID канала должен быть числом' % ln)
            continue
        if not tpl:
            issues.append('строка %d: пустой шаблон' % ln)
            continue
        if '{' not in tpl:
            issues.append('строка %d: шаблону нужна переменная, напр. {members}' % ln)
            continue
        channels[cid] = tpl[:80]
    return channels, issues


def night_phase(settings, now=None):
    """Фаза ночного режима: сейчас ночь?, когда перелом, что настроено.

    Вся логика окна — чистые функции кога (is_night/window_text /
    plan_settings_lines), панель только досчитывает секунды до границы.
    """
    s = night_mode.merge_settings(settings)
    now = now or datetime.now(timezone.utc)
    night = night_mode.is_night(now, s['start_hour'], s['end_hour'])
    if s['start_hour'] == s['end_hour']:
        next_in = None
        next_label = None
    else:
        target = s['end_hour'] if night else s['start_hour']
        next_in = ((target - now.hour) % 24) * 3600 - now.minute * 60 - now.second
        next_label = 'утро' if night else 'ночь'
    return {'enabled': bool(s['enabled']), 'is_night': night,
            'window': night_mode.window_text(s),
            'next_change_in_s': next_in, 'next_change': next_label,
            'lines': night_mode.plan_settings_lines(s)}


MEDIALOCK_PATH = 'data/media_only.json'
# Панельные подписи режимов — без эмодзи (в Discord-боках они есть в MODES кога)
MEDIALOCK_MODES = {
    'media': {'label': 'Только медиа', 'desc': 'картинки и видео'},
    'text': {'label': 'Только текст', 'desc': 'без вложений и ссылок'},
    'link': {'label': 'Только ссылки', 'desc': 'сообщение должно содержать ссылку'},
}

NIGHT_SUMMARY_PATH = 'data/night_summary.json'
NIGHT_TZ_MIN, NIGHT_TZ_MAX = -12, 14


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
        elif field['kind'] == 'counters':
            value = '\n'.join('%s | %s' % (cid, tpl)
                               for cid, tpl in (value or {}).items())
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
        elif kind == 'counters':
            raw[key] = parse_counters(value)[0]
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
        issues = []
        for field in spec['fields']:
            if field['kind'] == 'counters' and field['key'] in payload:
                issues.extend(parse_counters(payload[field['key']])[1])
        return jsonify({'success': True,
                        'values': _serialize(module_key, merged),
                        'issues': issues})

    # ── Автоматика v3: предпросмотр мод-дайджеста ────────────────────────────
    @app.route('/api/automation/digest-preview')
    @login_required
    @role_required('admin')
    def api_digest_preview():
        """Живой предпросмотр дайджеста: та же агрегация и те же строки эмбеда,
        что ког шлёт в Discord — настройки крутятся не вслепую."""
        from cogs import mod_digest as _md
        gid = active_guild_id()
        try:
            days = max(1, min(90, int(request.args.get('days', 7))))
        except (TypeError, ValueError):
            days = 7
        events = _md.load_events(gid)
        summary = _md.aggregate_digest(events, days=days)
        guild_name = 'сервер'
        import web.app as _app
        bot = _app.bot_instance
        if bot is not None:
            try:
                g = bot.get_guild(int(gid))
                if g is not None:
                    guild_name = g.name
            except Exception as _ex:
                _log.debug('digest-preview: имя гильдии не резолвится: %s', _ex)
        return jsonify({'success': True, 'days': days,
                        'summary': {'total': summary['total'],
                                    'per_category': summary['per_category'],
                                    'top_mods': summary['top_mods'],
                                    'busiest_day': summary['busiest_day']},
                        'embed': _md.digest_embed_dict(summary, days, guild_name)})

    # ── Автоматика v3: редактор триггеров (автоответы) ───────────────────────
    def _trigger_state(gid):
        from cogs.triggers import empty_state
        return _db('triggers').get(gid, 'state', empty_state()) or empty_state()

    def _save_trigger_state(gid, state, action_label):
        _db('triggers').set(gid, 'state', state)
        try:
            _fire_panel_notification(
                'automation', f'Триггеры: {action_label}',
                f'Через панель ({session.get("username", "?")}), сервер {gid}')
        except Exception as _ex:
            _log.debug('triggers: уведомление не ушло: %s', _ex)
        return jsonify({'success': True, 'state': state,
                        'max': _triggers_max()})

    def _triggers_max():
        from cogs.triggers import MAX_TRIGGERS
        return MAX_TRIGGERS

    def _apply_trigger_items(state, items):
        """Строки импорта через add_trigger кога: лимит/дубли/валидация 1:1."""
        from cogs.triggers import add_trigger
        added = 0
        skipped = []
        for idx, raw in enumerate(items, 1):
            if not isinstance(raw, dict):
                skipped.append({'trigger': '#%d' % idx, 'reason': 'не объект'})
                continue
            _item, err = add_trigger(state, raw.get('trigger'),
                                     raw.get('response'), raw.get('exact'))
            if err:
                skipped.append({'trigger': str(raw.get('trigger') or ('#%d' % idx))[:60],
                                'reason': err})
            else:
                added += 1
        return added, skipped

    @app.route('/api/automation/triggers/state')
    @login_required
    @role_required('admin')
    def api_triggers_state():
        """Список триггеров с кулдауном (редактор на странице автоматики)."""
        return jsonify({'success': True,
                        'state': _trigger_state(active_guild_id()),
                        'max': _triggers_max()})

    @app.route('/api/automation/triggers/add', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_triggers_add():
        """Добавить триггер. Валидация — та самая из кога (add_trigger):
        те же ошибки, тот же лимит, та же защита от дублей."""
        from cogs.triggers import add_trigger
        data = request.get_json(silent=True) or {}
        gid = active_guild_id()
        state = _trigger_state(gid)
        _item, err = add_trigger(state, data.get('trigger'),
                                 data.get('response'), data.get('exact'))
        if err:
            return jsonify({'success': False, 'error': err}), 400
        return _save_trigger_state(gid, state, f'добавлен «{state["items"][-1]["trigger"]}»')

    @app.route('/api/automation/triggers/remove', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_triggers_remove():
        from cogs.triggers import remove_trigger
        data = request.get_json(silent=True) or {}
        try:
            item_id = int(data.get('id'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'id триггера — число'}), 400
        gid = active_guild_id()
        state = _trigger_state(gid)
        if not remove_trigger(state, item_id):
            return jsonify({'success': False, 'error': f'триггер №{item_id} не найден'}), 404
        return _save_trigger_state(gid, state, f'удалён №{item_id}')

    @app.route('/api/automation/triggers/cooldown', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_triggers_cooldown():
        data = request.get_json(silent=True) or {}
        try:
            secs = int(data.get('seconds'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'кулдаун — число секунд'}), 400
        if not 0 <= secs <= 3600:
            return jsonify({'success': False, 'error': 'кулдаун: 0–3600 сек'}), 400
        gid = active_guild_id()
        state = _trigger_state(gid)
        state['cooldown'] = secs
        return _save_trigger_state(gid, state, f'кулдаун {secs} с')

    # ── #42: сухой прогон триггеров ──────────────────────────────────────
    @app.route('/api/automation/triggers/test', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_triggers_test():
        """Какой триггер ответит на сообщение — матчинг 1:1 с когом
        (find_match: самое длинное слово, кулдаун). Живая карта кулдаунов
        есть только у запущенного бота; без неё — честный флаг."""
        from cogs.triggers import find_match, matches, DEFAULT_COOLDOWN
        data = request.get_json(silent=True) or {}
        text = str(data.get('text') or '').strip()
        if not text:
            return jsonify({'success': False,
                            'error': 'Введите текст сообщения'}), 400
        gid = active_guild_id()
        state = _trigger_state(gid)
        items = state.get('items') or []
        cooldowns = None
        import web.app as _app
        bot = _app.bot_instance
        if bot is not None:
            cog = bot.get_cog('Triggers')
            cds = getattr(cog, '_cooldowns', None)
            if isinstance(cds, dict):
                try:
                    cooldowns = cds.get(int(gid)) or {}
                except (TypeError, ValueError) as _ex:
                    _log.debug('triggers-test: битый gid %r: %s', gid, _ex)
        now = datetime.now(timezone.utc)
        winner = find_match(items, text, cooldowns or {}, now,
                            state.get('cooldown', DEFAULT_COOLDOWN))
        hits = [it for it in items if matches(it, text)]
        return jsonify({
            'success': True,
            'matched': winner is not None,
            'winner': ({'id': winner.get('id'), 'trigger': winner.get('trigger'),
                        'response': winner.get('response'),
                        'exact': bool(winner.get('exact'))} if winner else None),
            'hits': [{'id': it.get('id'), 'trigger': it.get('trigger'),
                      'exact': bool(it.get('exact'))} for it in hits[:6]],
            'hits_total': len(hits),
            'cooldown': state.get('cooldown', DEFAULT_COOLDOWN),
            'cooldown_known': cooldowns is not None,
            'on_cooldown': bool(cooldowns is not None and hits and winner is None),
        })

    # ── #43: живой предпросмотр каналов-счётчиков ────────────────────────
    @app.route('/api/automation/counters-preview')
    @login_required
    @role_required('admin')
    def api_counters_preview():
        """Текущие имена счётчиков глазами Discord: те же render_counter /
        gather_stats, что у кога. Без живого бота чисел нет — честный 503."""
        gid = active_guild_id()
        import web.app as _app
        bot = _app.bot_instance
        guild = None
        if bot is not None:
            try:
                guild = bot.get_guild(int(gid))
            except (TypeError, ValueError) as _ex:
                _log.debug('counters-preview: битый gid %r: %s', gid, _ex)
        if guild is None:
            import web.app as _app
            if _app._demo_mode():
                # демо: предпросмотр счётчиков на демо-структуре каналов
                rows = []
                try:
                    with open('data/demo_channels.json', encoding='utf-8') as fp:
                        demo = json.load(fp)
                    text = [c for c in demo if c.get('type') == 'text'][:4]
                    stats = {'members': 1247, 'online': 213, 'bots': 12, 'boosts': 7, 'channels': 16}
                    tpls = ['{members} участников', 'онлайн: {online}', 'бустов: {boosts}']
                    for i, c in enumerate(text):
                        tpl = tpls[i % len(tpls)]
                        rendered = (tpl
                                    .replace('{members}', '1 247')
                                    .replace('{online}', '213')
                                    .replace('{boosts}', '7'))
                        rows.append({'channel_id': str(c.get('id')),
                                     'channel_name': str(c.get('name') or ''),
                                     'template': tpl,
                                     'rendered': rendered,
                                     'missing': False})
                except Exception as _ex:
                    _log.debug('counters-preview demo: подавлено: %s', _ex)
                return jsonify({'success': True, 'enabled': True, 'rows': rows})
            return jsonify({'success': False,
                            'error': 'Бот офлайн — живые числа недоступны'}), 503
        settings = server_stats.merge_settings(
            _db('server_stats').get(gid, 'settings', {}))
        stats = server_stats.gather_stats(guild)
        rows = []
        for cid, tpl in settings['channels'].items():
            ch = guild.get_channel(int(cid)) if str(cid).isdigit() else None
            rows.append({'channel_id': str(cid),
                         'channel_name': getattr(ch, 'name', None),
                         'template': tpl,
                         'rendered': server_stats.render_counter(tpl, stats),
                         'missing': ch is None})
        return jsonify({'success': True,
                        'enabled': bool(settings.get('enabled')), 'rows': rows})

    # ── #44: экспорт/импорт триггеров ────────────────────────────────────
    @app.route('/api/automation/triggers/export')
    @login_required
    @role_required('admin')
    def api_triggers_export():
        gid = active_guild_id()
        state = _trigger_state(gid)
        from cogs.triggers import DEFAULT_COOLDOWN
        payload = {
            'app': 'hakumo-triggers',
            'version': 1,
            'guild_id': str(gid),
            'cooldown': state.get('cooldown', DEFAULT_COOLDOWN),
            'items': [{'trigger': it.get('trigger'),
                       'response': it.get('response'),
                       'exact': bool(it.get('exact'))}
                      for it in (state.get('items') or [])],
        }
        return Response(json.dumps(payload, ensure_ascii=False, indent=2),
                        mimetype='application/json; charset=utf-8',
                        headers={'Content-Disposition':
                                 'attachment; filename="triggers_%s.json"' % gid})

    @app.route('/api/automation/triggers/import', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_triggers_import():
        """Импорт экспорта: merge — доливаем к текущим, replace — начисто.
        Каждая строка проходит add_trigger кога: те же лимиты и защита
        от дублей, поэтому повторный merge того же файла ничего не дублирует."""
        from cogs.triggers import empty_state
        data = request.get_json(silent=True) or {}
        mode = data.get('mode')
        if mode not in ('merge', 'replace'):
            return jsonify({'success': False,
                            'error': 'Неизвестный режим импорта'}), 400
        items = data.get('items')
        if not isinstance(items, list):
            return jsonify({'success': False,
                            'error': 'Файл не похож на экспорт триггеров'}), 400
        gid = active_guild_id()
        state = _trigger_state(gid) if mode == 'merge' else empty_state()
        added, skipped = _apply_trigger_items(state, items)
        cd = data.get('cooldown')
        if cd is not None:
            try:
                secs = int(cd)
                if 0 <= secs <= 3600:
                    state['cooldown'] = secs
            except (TypeError, ValueError) as _ex:
                _log.debug('triggers-import: битый кулдаун %r: %s', cd, _ex)
        _db('triggers').set(gid, 'state', state)
        try:
            _fire_panel_notification(
                'automation',
                'Триггеры: импорт (%s): %d добавлено, %d пропущено' % (mode, added, len(skipped)),
                f'Через панель ({session.get("username", "?")}), сервер {gid}')
        except Exception as _ex:
            _log.debug('triggers-import: уведомление не ушло: %s', _ex)
        return jsonify({'success': True, 'state': state, 'max': _triggers_max(),
                        'added': added, 'skipped': skipped[:20],
                        'skipped_total': len(skipped), 'mode': mode})

    # ── #45: медиа-лок каналов (cogs/media_only.py, data/media_only.json) ───
    def _medialock_all():
        raw = _js_load(MEDIALOCK_PATH, {})
        return raw if isinstance(raw, dict) else {}

    def _medialock_list(gid):
        guild = None
        import web.app as _app
        bot = _app.bot_instance
        if bot is not None:
            try:
                guild = bot.get_guild(int(gid))
            except (TypeError, ValueError) as _ex:
                _log.debug('medialock: битый gid %r: %s', gid, _ex)
        items = []
        gmap = _medialock_all().get(str(gid))
        if not isinstance(gmap, dict):
            gmap = {}
        for cid, rec in sorted(gmap.items(), key=lambda kv: str(kv[0])):
            if not isinstance(rec, dict):
                continue
            mode = str(rec.get('mode') or 'media')
            meta = MEDIALOCK_MODES.get(mode)
            if meta is None:
                continue  # неизвестный режим не выдумываем — пропускаем
            ch = guild.get_channel(int(cid)) if guild and str(cid).isdigit() else None
            items.append({'channel_id': str(cid), 'mode': mode,
                          'mode_label': meta['label'], 'desc': meta['desc'],
                          'exempt_mods': bool(rec.get('exempt_mods', True)),
                          'channel_name': getattr(ch, 'name', None)})
        return items

    def _medialock_save(store):
        _js_save(MEDIALOCK_PATH, store)

    @app.route('/api/automation/medialock')
    @login_required
    @role_required('admin')
    def api_medialock_list():
        return jsonify({'success': True,
                        'modes': [{'key': k, 'label': v['label'], 'desc': v['desc']}
                                  for k, v in MEDIALOCK_MODES.items()],
                        'channels': _medialock_list(active_guild_id())})

    @app.route('/api/automation/medialock/set', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_medialock_set():
        data = request.get_json(silent=True) or {}
        cid = str(data.get('channel_id') or '').strip()
        if not cid.isdigit():
            return jsonify({'success': False,
                            'error': 'ID канала должен быть числом'}), 400
        mode = str(data.get('mode') or '')
        if mode not in MEDIALOCK_MODES:
            return jsonify({'success': False,
                            'error': 'Неизвестный режим канала'}), 400
        gid = active_guild_id()
        store = _medialock_all()
        # запись 1:1 с ml_set кога: mode + exempt_mods (дефолт «моды свободны»)
        store.setdefault(str(gid), {})[cid] = {
            'mode': mode,
            'exempt_mods': bool(data.get('exempt_mods', True)),
        }
        _medialock_save(store)
        try:
            _fire_panel_notification(
                'automation', f'Медиа-лок: канал {cid} — {MEDIALOCK_MODES[mode]["label"]}',
                f'Через панель ({session.get("username", "?")}), сервер {gid}')
        except Exception as _ex:
            _log.debug('medialock: уведомление не ушло: %s', _ex)
        return jsonify({'success': True, 'channels': _medialock_list(gid)})

    @app.route('/api/automation/medialock/remove', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_medialock_remove():
        data = request.get_json(silent=True) or {}
        cid = str(data.get('channel_id') or '').strip()
        gid = active_guild_id()
        store = _medialock_all()
        gmap = store.get(str(gid)) if isinstance(store.get(str(gid)), dict) else {}
        removed = gmap.pop(cid, None)
        if removed is None:
            return jsonify({'success': False,
                            'error': 'На канале замка не было'}), 404
        store[str(gid)] = gmap
        _medialock_save(store)
        try:
            _fire_panel_notification(
                'automation', f'Медиа-лок: замок с канала {cid} снят',
                f'Через панель ({session.get("username", "?")}), сервер {gid}')
        except Exception as _ex:
            _log.debug('medialock: уведомление не ушло: %s', _ex)
        return jsonify({'success': True,
                        'removed': {'channel_id': cid,
                                    'mode': str(removed.get('mode') or 'media'),
                                    'exempt_mods': bool(removed.get('exempt_mods', True))},
                        'channels': _medialock_list(gid)})

    # ── #46-47: ночная сводка (cogs/night_summary.py) ────────────────────
    def _night_state():
        raw = _js_load(NIGHT_SUMMARY_PATH, {})
        return raw if isinstance(raw, dict) else {}

    def _night_cfg(gid):
        # дефолты + слияние 1:1 с NightSummary.cfg(); last_date не трогаем
        cfg = {'enabled': True, 'channel_id': 0, 'tz_offset': 3}
        saved = _night_state().get(str(gid))
        if isinstance(saved, dict):
            cfg.update(saved)
        return cfg

    def _night_today(tz_offset):
        local = datetime.now(timezone.utc) + timedelta(hours=tz_offset)
        return local.strftime('%Y-%m-%d')

    def _night_public(gid):
        cfg = _night_cfg(gid)
        saved = _night_state().get(str(gid))
        last_sent = saved.get('last_date') if isinstance(saved, dict) else None
        return {'enabled': bool(cfg['enabled']),
                'channel_id': int(cfg.get('channel_id') or 0),
                'tz_offset': int(cfg.get('tz_offset') or 0),
                'today': _night_today(int(cfg.get('tz_offset') or 0)),
                'last_sent': last_sent or None}

    def _night_validate(data):
        """Правки настроек сводки -> (updates, err). Те же тексты, что раньше."""
        updates = {}
        if 'enabled' in data:
            updates['enabled'] = bool(data['enabled'])
        if 'channel_id' in data:
            try:
                cid = int(data['channel_id'])
            except (TypeError, ValueError):
                return None, 'ID канала — число (0 — авто)'
            if cid < 0:
                return None, 'ID канала — число (0 — авто)'
            updates['channel_id'] = cid
        if 'tz_offset' in data:
            try:
                tz = int(data['tz_offset'])
            except (TypeError, ValueError):
                return None, 'Смещение — число часов'
            if not NIGHT_TZ_MIN <= tz <= NIGHT_TZ_MAX:
                return None, 'Смещение: от -12 до +14 часов'
            updates['tz_offset'] = tz
        if not updates:
            return None, 'Нечего сохранять'
        return updates, ''

    def _night_apply(gid, updates):
        state = _night_state()
        saved = state.get(str(gid))
        cur = dict(saved) if isinstance(saved, dict) else {}
        cur.update(updates)
        state[str(gid)] = cur
        _js_save(NIGHT_SUMMARY_PATH, state)

    @app.route('/api/automation/night-summary')
    @login_required
    @role_required('admin')
    def api_night_summary_get():
        return jsonify(dict(_night_public(active_guild_id()), success=True))

    @app.route('/api/automation/night-summary', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_night_summary_save():
        data = request.get_json(silent=True) or {}
        updates, err = _night_validate(data)
        if err:
            return jsonify({'success': False, 'error': err}), 400
        gid = active_guild_id()
        _night_apply(gid, updates)
        try:
            _fire_panel_notification(
                'automation', 'Ночная сводка: настройки обновлены',
                f'Через панель ({session.get("username", "?")}), сервер {gid}')
        except Exception as _ex:
            _log.debug('night-summary: уведомление не ушло: %s', _ex)
        return jsonify(dict(_night_public(gid), success=True))

    @app.route('/api/automation/night-summary/preview')
    @login_required
    @role_required('admin')
    def api_night_summary_preview():
        """Статистика «золотой карты дня» — тот же collect_day, что рисует
        картинку для Discord. Работает и без бота: источники — файлы/БД."""
        gid = active_guild_id()
        cfg = _night_cfg(gid)
        try:
            gid_int = int(gid)
        except (TypeError, ValueError) as _ex:
            _log.debug('night-summary preview: битый gid %r: %s', gid, _ex)
            return jsonify({'success': False,
                            'error': 'Некорректный сервер'}), 400
        tz = int(cfg.get('tz_offset') or 0)
        day = datetime.now(timezone.utc) + timedelta(hours=tz)
        stats = night_summary.NightSummary.collect_day(gid_int, day, tz)
        return jsonify({'success': True,
                        'date': day.strftime('%Y-%m-%d'), 'tz_offset': tz,
                        'enabled': bool(cfg['enabled']),
                        'stats': stats})

    # ── #48: фаза ночного режима ─────────────────────────────────────────
    @app.route('/api/automation/night-phase')
    @login_required
    @role_required('admin')
    def api_night_phase():
        """Сейчас ночь или до неё сколько? — window/is_night кога 1:1."""
        gid = active_guild_id()
        settings = _db('night_mode').get(gid, 'settings', {})
        return jsonify(dict(night_phase(settings), success=True))

    # ── #49: предпросмотр приветствий PRO ────────────────────────────────
    @app.route('/api/automation/welcome-preview')
    @login_required
    @role_required('admin')
    def api_welcome_preview():
        """Каждый шаблон, отрендеренный тем render_welcome, что шлёт ког.
        Живые имя сервера и номер — при онлайн-боте, иначе пометка sample."""
        gid = active_guild_id()
        s = welcome_pro.merge_settings(_db('welcome_pro').get(gid, 'settings', {}))
        import web.app as _app
        bot = _app.bot_instance
        guild = None
        if bot is not None:
            try:
                guild = bot.get_guild(int(gid))
            except (TypeError, ValueError) as _ex:
                _log.debug('welcome-preview: битый gid %r: %s', gid, _ex)
        server = str(getattr(guild, 'name', '') or '') if guild else ''
        count = int(getattr(guild, 'member_count', 0) or 0) + 1 if guild else 128
        if not server:
            server = 'Сервер'
        items = [{'index': idx, 'source': tpl,
                  'rendered': welcome_pro.render_welcome(tpl, 'Новенький',
                                                         '@Новенький', server, count)}
                 for idx, tpl in enumerate(s['templates'], 1)]
        return jsonify({'success': True,
                        'enabled': bool(s['enabled']),
                        'templates': items,
                        'dm_enabled': bool(s.get('dm_enabled')),
                        'dm_rendered': welcome_pro.render_welcome(
                            s.get('dm_text') or '', 'Новенький', '@Новенький',
                            server, count),
                        'server': server, 'count': count,
                        'sample': guild is not None})

    # ── #50: перенос автоматики (экспорт/импорт одним файлом) ────────────
    def _export_bundle(gid):
        gid_s = str(gid)
        from cogs.triggers import DEFAULT_COOLDOWN
        state = _trigger_state(gid_s)
        channels = {}
        gmap = _medialock_all().get(gid_s)
        for cid, rec in (gmap if isinstance(gmap, dict) else {}).items():
            if not isinstance(rec, dict):
                continue
            mode = str(rec.get('mode') or 'media')
            if mode not in MEDIALOCK_MODES:
                continue
            channels[str(cid)] = {'mode': mode,
                                  'exempt_mods': bool(rec.get('exempt_mods', True))}
        ns_cfg = _night_cfg(gid_s)
        return {
            'app': 'hakumo-automation',
            'version': 1,
            'guild_id': gid_s,
            'modules': {key: _serialize(key, spec['merge'](_db(spec['ns']).get(gid, 'settings', {})))
                        for key, spec in MODULE_EDITORS.items()},
            'triggers': {'cooldown': state.get('cooldown', DEFAULT_COOLDOWN),
                         'items': [{'trigger': it.get('trigger'),
                                    'response': it.get('response'),
                                    'exact': bool(it.get('exact'))}
                                   for it in (state.get('items') or [])]},
            'medialock': {'channels': channels},
            'night_summary': {'enabled': bool(ns_cfg['enabled']),
                              'channel_id': int(ns_cfg.get('channel_id') or 0),
                              'tz_offset': int(ns_cfg.get('tz_offset') or 0)},
        }

    @app.route('/api/automation/export-all')
    @login_required
    @role_required('admin')
    def api_automation_export_all():
        gid = active_guild_id()
        bundle = _export_bundle(gid)
        return Response(json.dumps(bundle, ensure_ascii=False, indent=2),
                        mimetype='application/json; charset=utf-8',
                        headers={'Content-Disposition':
                                 'attachment; filename="automation_%s.json"' % gid})

    @app.route('/api/automation/import-all', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_automation_import_all():
        """Мягкий перенос: merge по всем секциям. Модули проходят тот же
        _clean_payload + merge_settings, что и их карточки; триггеры —
        add_trigger кога; замки и сводка — те же проверки, что у их POST."""
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or data.get('app') != 'hakumo-automation':
            return jsonify({'success': False,
                            'error': 'Файл не похож на экспорт автоматики'}), 400
        gid = active_guild_id()
        applied = {'modules': [], 'triggers': 0, 'medialock': 0, 'night_summary': False}
        skipped = []
        issues = []

        modules = data.get('modules')
        if isinstance(modules, dict):
            for key, values in modules.items():
                spec = MODULE_EDITORS.get(key)
                if spec is None:
                    skipped.append({'section': 'modules', 'what': str(key),
                                    'reason': 'неизвестный модуль'})
                    continue
                if not isinstance(values, dict):
                    skipped.append({'section': 'modules', 'what': str(key),
                                    'reason': 'не объект'})
                    continue
                store = _db(spec['ns'])
                current = spec['merge'](store.get(gid, 'settings', {}))
                current.update(_clean_payload(key, values))
                store.set(gid, 'settings', spec['merge'](current))
                for field in spec['fields']:
                    if field['kind'] == 'counters' and field['key'] in values:
                        issues.extend(parse_counters(values[field['key']])[1])
                applied['modules'].append(key)

        trg = data.get('triggers')
        if isinstance(trg, dict):
            items = trg.get('items')
            if isinstance(items, list):
                state = _trigger_state(gid)
                added, trg_skipped = _apply_trigger_items(state, items)
                for row in trg_skipped:
                    skipped.append({'section': 'triggers', 'what': row['trigger'],
                                    'reason': row['reason']})
                cd = trg.get('cooldown')
                if cd is not None:
                    try:
                        secs = int(cd)
                        if 0 <= secs <= 3600:
                            state['cooldown'] = secs
                    except (TypeError, ValueError) as _ex:
                        _log.debug('import-all: битый кулдаун %r: %s', cd, _ex)
                _db('triggers').set(gid, 'state', state)
                applied['triggers'] = added

        ml = data.get('medialock')
        if isinstance(ml, dict) and isinstance(ml.get('channels'), dict):
            store = _medialock_all()
            gmap = store.setdefault(str(gid), {})
            for cid, rec in ml['channels'].items():
                cid = str(cid)
                mode = rec.get('mode') if isinstance(rec, dict) else None
                if not cid.isdigit() or mode not in MEDIALOCK_MODES:
                    skipped.append({'section': 'medialock', 'what': cid,
                                    'reason': 'битый канал или режим'})
                    continue
                gmap[cid] = {'mode': mode,
                             'exempt_mods': bool(rec.get('exempt_mods', True))}
                applied['medialock'] += 1
            _medialock_save(store)

        ns = data.get('night_summary')
        if isinstance(ns, dict):
            updates, err = _night_validate({
                k: ns[k] for k in ('enabled', 'channel_id', 'tz_offset') if k in ns})
            if err:
                skipped.append({'section': 'night_summary', 'what': 'настройки',
                                'reason': err})
            else:
                _night_apply(gid, updates)
                applied['night_summary'] = True

        try:
            _fire_panel_notification(
                'automation',
                'Импорт автоматики: модулей %d, триггеров %d, замков %d' % (
                    len(applied['modules']), applied['triggers'], applied['medialock']),
                f'Через панель ({session.get("username", "?")}), сервер {gid}')
        except Exception as _ex:
            _log.debug('import-all: уведомление не ушло: %s', _ex)
        return jsonify({'success': True, 'applied': applied,
                        'skipped': skipped[:20], 'skipped_total': len(skipped),
                        'issues': issues})
