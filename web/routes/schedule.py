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
                # демо: каналы из демо-структуры + пара примеров анонсов
                demo_chs = []
                try:
                    with open('data/demo_channels.json', 'r', encoding='utf-8') as fp:
                        demo = json.load(fp)
                    demo_chs = [{'id': str(c['id']), 'name': c['name']}
                                for c in demo if c.get('type') == 'text'][:80]
                except Exception as _ex:
                    _log.debug("api_schedule_state() demo: подавлено: %s", _ex)
                return jsonify({
                    'ok': True,
                    'channels': demo_chs,
                    'items': [{
                        'id': 'demo-1',
                        'channel_id': demo_chs[0]['id'] if demo_chs else '1002',
                        'content': 'Добро пожаловать! Читай правила в #инфо.',
                        'embed_title': '',
                        'repeat': 'once', 'repeat_label': 'Один раз',
                        'time': '20:00', 'weekday': 0, 'weekday_label': '',
                        'tz_offset': 3, 'enabled': True,
                    }],
                    'tz_offset': 3,
                })
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
