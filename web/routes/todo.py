# -*- coding: utf-8 -*-
"""Список задач команды (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
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


    # ── TODO: общие задачи команды (страница /todo) ─────────────
    @app.route('/api/todo')
    @login_required
    @role_required('owner')
    def api_todo_list():
        from services.panel_todo import list_tasks
        return jsonify({'ok': True, 'tasks': list_tasks()})


    @app.route('/api/todo/add', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_todo_add():
        from services.panel_todo import add_task
        data = request.get_json(silent=True) or {}
        try:
            task = add_task(data.get('text'), session.get('username'))
        except ValueError as e:
            return jsonify({'ok': False, 'error': str(e)}), 400
        return jsonify({'ok': True, 'task': task})


    @app.route('/api/todo/toggle', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_todo_toggle():
        from services.panel_todo import toggle_task
        data = request.get_json(silent=True) or {}
        if not toggle_task(data.get('id')):
            return jsonify({'ok': False, 'error': 'Задача не найдена'}), 404
        return jsonify({'ok': True})


    @app.route('/api/todo/delete', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_todo_delete():
        from services.panel_todo import delete_task
        data = request.get_json(silent=True) or {}
        if not delete_task(data.get('id')):
            return jsonify({'ok': False, 'error': 'Задача не найдена'}), 404
        return jsonify({'ok': True})
