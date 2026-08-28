# -*- coding: utf-8 -*-
"""Тег-карцер (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

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


    # ── TAG JAIL paneli ──────────────────────────────────────────────
    def _tagjail_ctx():
        import web.app as _app
        bot = _app.bot_instance
        cog = bot.get_cog('TagJail') if bot else None
        guild = None
        if bot and getattr(bot, 'guilds', None):
            gid = active_guild_id()
            guild = next((g for g in bot.guilds if str(g.id) == str(gid)), None)
            if guild is None:
                guild = bot.guilds[0]
        return bot, cog, guild


    @app.route('/tagjail')
    @login_required
    @role_required('admin')
    def tagjail_page():
        return render_template('tagjail.html', role=session.get('role'), username=session.get('username'))


    @app.route('/api/tagjail/state')
    @login_required
    @role_required('admin')
    def api_tagjail_state():
        bot, cog, guild = _tagjail_ctx()
        if not cog or not guild:
            import web.app as _app
            if _app._demo_mode():
                # демо: карцер пуст и выключен — страница живая
                return jsonify({
                    'ok': True,
                    'config': {
                        'enabled': False, 'auto_release': True, 'on_join': True,
                        'on_name_change': True, 'dm_notify': True, 'scan_on_boot': False,
                        'min_account_days': 7, 'jail_role_id': 0, 'log_channel_id': 0,
                    },
                    'jailed': [],
                    'guild': 'Главный сервер',
                })
            return jsonify({'ok': False, 'error': 'Модуль офлайн (бот не запущен)'})
        c = cog.cfg(guild.id)
        jailed = []
        for uid, rec in list(cog._jailed.get(str(guild.id), {}).items())[:100]:
            try:
                m = guild.get_member(int(uid))
            except Exception:
                m = None
            jailed.append({
                'user_id': uid,
                'name': m.display_name if m else f'ID {uid}',
                'in_guild': bool(m),
                'since': rec.get('since', 0),
                'tag': rec.get('tag', ''),
                'reason': str(rec.get('reason', ''))[:90],
                'roles_saved': len(rec.get('roles', [])),
            })
        return jsonify({'ok': True, 'config': c, 'jailed': jailed,
                        'guild': guild.name, 'gid': str(guild.id)})


    @app.route('/api/tagjail/config', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_tagjail_config():
        bot, cog, guild = _tagjail_ctx()
        if not cog or not guild:
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        data = request.get_json(silent=True) or {}
        updated, errors = {}, {}
        BOOL_KEYS = ('enabled', 'auto_release', 'on_join', 'on_name_change', 'dm_notify', 'scan_on_boot')
        INT_KEYS = ('min_account_days', 'jail_role_id', 'log_channel_id')
        for k, v in data.items():
            try:
                if k in BOOL_KEYS:
                    cog.set_cfg(guild.id, k, bool(v))
                    updated[k] = bool(v)
                elif k in INT_KEYS:
                    iv = int(v or 0)  # пустая строка (нет выбора) = 0 = выкл
                    if iv < 0:
                        raise ValueError('>= 0')
                    cog.set_cfg(guild.id, k, iv)
                    updated[k] = iv
                elif k == 'jail_style':
                    if v not in ('remove', 'keep'):
                        raise ValueError('remove|keep')
                    cog.set_cfg(guild.id, k, v)
                    updated[k] = v
                elif k == 'age_action':
                    if v not in ('jail', 'kick'):
                        raise ValueError('jail|kick')
                    cog.set_cfg(guild.id, k, v)
                    updated[k] = v
                else:
                    errors[k] = 'недоступно для правки'
            except (ValueError, TypeError) as e:
                errors[k] = str(e)
        if errors and not updated:
            return jsonify({'ok': False, 'errors': errors}), 400
        return jsonify({'ok': True, 'updated': updated, 'errors': errors})


    @app.route('/api/tagjail/tag', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_tagjail_tag():
        bot, cog, guild = _tagjail_ctx()
        if not cog or not guild:
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        data = request.get_json(silent=True) or {}
        tag = str(data.get('tag', '')).strip()
        action = data.get('action')
        if not tag:
            return jsonify({'ok': False, 'error': 'Пустой тег'}), 400
        tags = list(cog.cfg(guild.id).get('banned_tags', []))
        if action == 'add':
            if tag not in tags:
                tags.append(tag)
        elif action == 'del':
            if tag in tags:
                tags.remove(tag)
        else:
            return jsonify({'ok': False, 'error': 'action: add|del'}), 400
        cog.set_cfg(guild.id, 'banned_tags', tags)
        return jsonify({'ok': True, 'tags': tags})


    @app.route('/api/tagjail/unjail', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_tagjail_unjail():
        bot, cog, guild = _tagjail_ctx()
        if not cog or not guild:
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        data = request.get_json(silent=True) or {}
        uid = str(data.get('user_id', '')).strip()
        if not uid.isdigit():
            return jsonify({'ok': False, 'error': 'user_id?'}), 400
        member = guild.get_member(int(uid))
        try:
            if member:
                _run_async(cog.release(member, 'Освобождён через веб-панель'))
            else:
                # покинул сервер — просто чистим запись
                cog._del_jail_rec(guild.id, int(uid))
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500


    @app.route('/api/tagjail/scan', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_tagjail_scan():
        bot, cog, guild = _tagjail_ctx()
        if not cog or not guild:
            return jsonify({'ok': False, 'error': 'Модуль офлайн'}), 503
        if not cog.cfg(guild.id).get('enabled'):
            return jsonify({'ok': False, 'error': 'Система выключена'}), 400
        try:
            import asyncio as _aio
            _aio.run_coroutine_threadsafe(cog._sweep_guild(guild), bot.loop)
            return jsonify({'ok': True, 'started': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500
