# -*- coding: utf-8 -*-
"""Планировщик анонсов (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _load_ai_tickets, _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, calculate_ai_ticket_stats, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone,
)

def register(ctx):
    app = ctx.app
    ROLES = ctx.ROLES
    login_required = ctx.login_required
    role_required = ctx.role_required
    MAIN_GUILD_ID = ctx.MAIN_GUILD_ID
    active_guild_id = ctx.active_guild_id
    _resolve_member_async = ctx._resolve_member_async


    # ── SCHEDULER (расписание анонсов) ──────────────────────────
    def _demo_sched_file():
        return f"data/schedule_demo_{session.get('selected_guild') or MAIN_GUILD_ID}.json"

    def _demo_sched_seed():
        """Стартовый анонс для превью: сегодня/завтра в 20:00."""
        import datetime as _dt
        _now = _dt.datetime.now()
        _t = _now.replace(hour=20, minute=0, second=0, microsecond=0)
        if _t <= _now:
            _t += _dt.timedelta(days=1)
        return [{
            'id': 1,
            'channel_id': 1002,
            'content': 'Добро пожаловать на сервер! Читай правила в #rules.',
            'embed': {},
            'repeat': 'once',
            'time': '20:00',
            'weekday': 0,
            'tz_offset': 3,
            'enabled': True,
            'next_ts': _t.timestamp(),
        }]

    def _demo_sched_load():
        f = _demo_sched_file()
        if os.path.exists(f):
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    items = json.load(fp)
                if isinstance(items, list):
                    return items
            except Exception as _ex:
                _log.debug("_demo_sched_load(): подавлено: %s", _ex)
        items = _demo_sched_seed()
        _demo_sched_store(items)
        return items

    def _demo_sched_store(items):
        try:
            with open(_demo_sched_file(), 'w', encoding='utf-8') as fp:
                json.dump(items, fp, ensure_ascii=False, indent=2)
        except Exception as _ex:
            _log.debug("_demo_sched_store(): подавлено: %s", _ex)

    def _demo_sched_next(item):
        """Дата следующего запуска в формате панели («20.08 20:00»)."""
        import datetime as _dt
        ts = item.get('next_ts') or 0
        if not ts:
            return '—'
        tz = int(item.get('tz_offset', 3) or 0)
        d = _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc) + _dt.timedelta(hours=tz)
        return d.strftime('%d.%m %H:%M')

    def _sched_ctx():
        import web.app as _app
        bot = _app.bot_instance
        cog = bot.get_cog('Scheduler') if bot else None
        guild = None
        if bot and getattr(bot, 'guilds', None):
            gid = active_guild_id()
            guild = next((g for g in bot.guilds if str(g.id) == str(gid)), None)
            if guild is None:
                guild = bot.guilds[0]
        return bot, cog, guild


    @app.route('/schedule')
    @login_required
    @role_required('admin')
    def schedule_page():
        return render_template('schedule.html', role=session.get('role'), username=session.get('username'))


    @app.route('/api/schedule/state')
    @login_required
    @role_required('admin')
    def api_schedule_state():
        bot, cog, guild = _sched_ctx()
        if not cog or not guild:
            import web.app as _app
            if _app._demo_mode():
                # демо: хранилище анонсов работает локально — список, пауза, удаление живые
                try:
                    with open('data/demo_channels.json', 'r', encoding='utf-8') as fp:
                        demo = json.load(fp)
                    demo_chs = [{'id': str(c['id']), 'name': c['name']}
                                for c in demo if c.get('type') == 'text'][:80]
                except Exception as _ex:
                    _log.debug("api_schedule_state() demo: подавлено: %s", _ex)
                    demo_chs = []
                items = []
                for it in _demo_sched_load():
                    items.append({
                        'id': it['id'],
                        'channel_id': str(it.get('channel_id', '')),
                        'content': (it.get('content') or '')[:400],
                        'embed_title': (it.get('embed') or {}).get('title', ''),
                        'repeat': it.get('repeat', 'once'),
                        'repeat_label': {'once': 'Один раз', 'daily': 'Каждый день', 'weekly': 'Каждую неделю'}.get(it.get('repeat'), it.get('repeat')),
                        'time': it.get('time', '12:00'),
                        'weekday': it.get('weekday', 0),
                        'weekday_label': ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'][it.get('weekday', 0)] if it.get('repeat') == 'weekly' else '',
                        'tz_offset': it.get('tz_offset', 3),
                        'enabled': bool(it.get('enabled', True)),
                        'next': _demo_sched_next(it),
                    })
                return jsonify({'ok': True, 'channels': demo_chs, 'items': items, 'tz_offset': 3})
            return jsonify({'ok': False, 'error': 'Модуль офлайн (бот не запущен)'})
        from cogs.scheduler import REPEAT_LABEL, WEEKDAYS_RU, human_next
        channels = [{'id': str(c.id), 'name': c.name} for c in
                    sorted(guild.text_channels, key=lambda x: x.position)[:80]]
        items = []
        for it in cog.get_items(guild.id):
            items.append({
                'id': it['id'],
                'channel_id': str(it['channel_id']),
                'content': (it.get('content') or '')[:400],
                'embed_title': (it.get('embed') or {}).get('title', ''),
                'repeat': it.get('repeat', 'once'),
                'repeat_label': REPEAT_LABEL.get(it.get('repeat'), it.get('repeat')),
                'time': it.get('time', '12:00'),
                'weekday': it.get('weekday', 0),
                'weekday_label': WEEKDAYS_RU[it.get('weekday', 0)] if it.get('repeat') == 'weekly' else '',
                'tz_offset': it.get('tz_offset', 3),
                'enabled': bool(it.get('enabled', True)),
                'next': human_next(it),
                'last_sent_ts': it.get('last_sent_ts', 0),
            })
        return jsonify({'ok': True, 'items': list(reversed(items)), 'channels': channels,
                        'guild': guild.name})


    @app.route('/api/schedule/save', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_schedule_save():
        bot, cog, guild = _sched_ctx()
        if not cog or not guild:
            import web.app as _app
            if _app._demo_mode():
                import datetime as _dt
                data = request.get_json(silent=True) or {}
                content = str(data.get('content', '') or '').strip()
                etitle = str(data.get('embed_title', '') or '').strip()
                edesc = str(data.get('embed_desc', '') or '').strip()
                if not content and not etitle and not edesc:
                    return jsonify({'ok': False, 'error': 'Пустой анонс — текст или embed обязателен'}), 400
                repeat = data.get('repeat', 'once')
                if repeat not in ('once', 'daily', 'weekly'):
                    return jsonify({'ok': False, 'error': 'repeat: once|daily|weekly'}), 400
                items = _demo_sched_load()
                new_id = max([it.get('id', 0) for it in items] + [0]) + 1
                _now = _dt.datetime.now()
                _t = _now.replace(hour=20, minute=0, second=0, microsecond=0)
                if _t <= _now:
                    _t += _dt.timedelta(days=1)
                items.append({
                    'id': new_id,
                    'channel_id': int(data.get('channel_id', 0) or 0),
                    'content': content[:400],
                    'embed': ({'title': etitle[:240], 'description': edesc[:1800]} if (etitle or edesc) else {}),
                    'repeat': repeat,
                    'time': str(data.get('time', '20:00')),
                    'weekday': int(data.get('weekday', 0) or 0),
                    'tz_offset': int(data.get('tz_offset', 3) or 3),
                    'enabled': True,
                    'next_ts': _t.timestamp(),
                })
                _demo_sched_store(items)
                return jsonify({'ok': True, 'id': new_id})
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        from cogs.scheduler import parse_time_hhmm
        data = request.get_json(silent=True) or {}
        try:
            channel_id = int(data.get('channel_id', 0))
        except Exception:
            channel_id = 0
        if not guild.get_channel(channel_id):
            return jsonify({'ok': False, 'error': 'Канал не найден'}), 400
        if not parse_time_hhmm(data.get('time', '')):
            return jsonify({'ok': False, 'error': 'Время в формате ЧЧ:ММ'}), 400
        repeat = data.get('repeat', 'once')
        if repeat not in ('once', 'daily', 'weekly'):
            return jsonify({'ok': False, 'error': 'repeat: once|daily|weekly'}), 400
        content = str(data.get('content', '') or '')
        embed = None
        etitle = str(data.get('embed_title', '') or '').strip()
        edesc = str(data.get('embed_desc', '') or '').strip()
        if etitle or edesc:
            try:
                ecolor = int(str(data.get('embed_color', '0xD4AF37')).replace('#', '0x'), 16)
            except Exception:
                ecolor = 0xD4AF37
            embed = {'title': etitle[:240], 'description': edesc[:1800], 'color': ecolor}
        if not content.strip() and embed is None:
            return jsonify({'ok': False, 'error': 'Пустой анонс — текст или embed обязателен'}), 400
        try:
            tz = max(-12, min(14, int(data.get('tz_offset', 3))))
        except Exception:
            tz = 3
        try:
            wd = max(0, min(6, int(data.get('weekday', 0))))
        except Exception:
            wd = 0
        item = cog.add_item(
            guild.id, channel_id=channel_id, content=content, embed=embed,
            repeat=repeat, time=str(data.get('time')), weekday=wd, tz_offset=tz,
            created_by=session.get('user_id', 0) or 0)
        return jsonify({'ok': True, 'id': item['id']})


    @app.route('/api/schedule/toggle', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_schedule_toggle():
        bot, cog, guild = _sched_ctx()
        if not cog or not guild:
            import web.app as _app
            if _app._demo_mode():
                data = request.get_json(silent=True) or {}
                items = _demo_sched_load()
                try:
                    aid = int(data.get('id', 0) or 0)
                except Exception:
                    aid = 0
                for it in items:
                    if it.get('id') == aid:
                        it['enabled'] = not bool(it.get('enabled', True))
                        _demo_sched_store(items)
                        return jsonify({'ok': True, 'enabled': bool(it['enabled'])})
                return jsonify({'ok': False, 'error': 'Анонс не найден'}), 404
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        data = request.get_json(silent=True) or {}
        it = cog.toggle_item(guild.id, int(data.get('id', 0) or 0))
        if not it:
            return jsonify({'ok': False, 'error': 'Анонс не найден'}), 404
        return jsonify({'ok': True, 'enabled': bool(it.get('enabled', True))})


    @app.route('/api/schedule/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_schedule_delete():
        bot, cog, guild = _sched_ctx()
        if not cog or not guild:
            import web.app as _app
            if _app._demo_mode():
                data = request.get_json(silent=True) or {}
                try:
                    aid = int(data.get('id', 0) or 0)
                except Exception:
                    aid = 0
                items = _demo_sched_load()
                kept = [it for it in items if it.get('id') != aid]
                if len(kept) == len(items):
                    return jsonify({'ok': False, 'error': 'Анонс не найден'}), 404
                _demo_sched_store(kept)
                return jsonify({'ok': True})
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        data = request.get_json(silent=True) or {}
        if cog.remove_item(guild.id, int(data.get('id', 0) or 0)):
            return jsonify({'ok': True})
        return jsonify({'ok': False, 'error': 'Анонс не найден'}), 404


    @app.route('/api/schedule/test', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_schedule_test():
        bot, cog, guild = _sched_ctx()
        if not cog or not guild:
            import web.app as _app
            if _app._demo_mode():
                data = request.get_json(silent=True) or {}
                try:
                    aid = int(data.get('id', 0) or 0)
                except Exception:
                    aid = 0
                if not any(it.get('id') == aid for it in _demo_sched_load()):
                    return jsonify({'ok': False, 'error': 'Анонс не найден'}), 404
                return jsonify({'ok': True})
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        data = request.get_json(silent=True) or {}
        it = cog.get_item(guild.id, int(data.get('id', 0) or 0))
        if not it:
            return jsonify({'ok': False, 'error': 'Анонс не найден'}), 404
        try:
            import asyncio as _aio
            _aio.run_coroutine_threadsafe(cog.send_item(guild, it), bot.loop)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500
