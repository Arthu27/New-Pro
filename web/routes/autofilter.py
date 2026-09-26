# -*- coding: utf-8 -*-
"""Автофильтр чата (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _safe_json_obj,
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone)

def register(ctx):
    app = ctx.app
    ROLES = ctx.ROLES
    login_required = ctx.login_required
    role_required = ctx.role_required
    MAIN_GUILD_ID = ctx.MAIN_GUILD_ID
    active_guild_id = ctx.active_guild_id
    _resolve_member_async = ctx._resolve_member_async


    # ── АВТОФИЛЬТР чата ───────────────────────────────────────────
    def _autofilter_gid() -> str:
        """MAIN_GUILD_ID, иначе первый сервер бота (как в остальных API)."""
        if MAIN_GUILD_ID:
            return str(MAIN_GUILD_ID)
        import web.app as _app
        bot = _app.bot_instance
        try:
            guilds = getattr(bot, 'guilds', None) or []
            if guilds:
                return str(guilds[0].id)
        except Exception as _ex:
            _log.debug('_autofilter_gid(): бот без guilds: %s', _ex)
        # Демо-витрина без MAIN_GUILD_ID: конфиг автофильтра не должен
        # «не выбираться» — тот же демо-сервер 777, что в /api/guilds.
        if _app._demo_mode():
            return '777'
        return ''


    @app.route('/autofilter')
    @login_required
    @role_required('mod')
    def autofilter_page():
        return render_template('autofilter.html', role=session.get('role'),
                               username=session.get('username'))


    @app.route('/api/autofilter')
    @login_required
    @role_required('mod')
    def api_autofilter_get():
        from cogs.auto_filter import load_config
        gid = _autofilter_gid()
        if not gid:
            return jsonify({'ok': False, 'error': 'Сервер не выбран (MAIN_GUILD_ID / бот офлайн)'}), 503
        return jsonify({'ok': True, 'guild_id': gid, 'config': load_config(gid)})


    @app.route('/api/autofilter/save', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_autofilter_save():
        from cogs.auto_filter import validate_config, save_config, FILTER_NAMES
        gid = _autofilter_gid()
        if not gid:
            return jsonify({'ok': False, 'error': 'Сервер не выбран'}), 503
        data = _safe_json_obj()
        # Страховка от сброса настроек: POST без НИ ОДНОГО известного
        # ключа (мусор/частичный запрос) раньше молча сохранял ДЕФОЛТЫ
        # поверх боевого конфига. Теперь отклоняем.
        if not any(k in data for k in FILTER_NAMES):
            return jsonify({'ok': False,
                            'error': 'Конфиг пуст: отклонено, чтобы не сбросить настройки'}), 400
        cfg, errors = validate_config(data)
        if errors:
            return jsonify({'ok': False, 'errors': errors}), 400
        save_config(gid, cfg)
        return jsonify({'ok': True, 'config': cfg})


    @app.route('/api/autofilter/test', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_autofilter_test():
        from cogs.auto_filter import load_config, classify_message
        gid = _autofilter_gid()
        if not gid:
            return jsonify({'ok': False, 'error': 'Сервер не выбран'}), 503
        data = _safe_json_obj()
        text = str(data.get('text') or '')[:500]
        return jsonify({'ok': True,
                        'violations': classify_message(load_config(gid), text)})
