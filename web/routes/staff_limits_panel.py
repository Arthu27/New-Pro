# -*- coding: utf-8 -*-
"""Лимиты команды + Логи сервера — панельная сторона.

Лимиты (services/staff_limits.py): глобальные и ПЕР-РОЛЬНЫЕ дневные лимиты
действий модерации. Редактирование — только владелец: зачем лимитам от
«обнаглевших» админов, если их же может поднять сам админ.
Настройки логов (services/log_settings.py): какие категории логировать и
каким разрешено СОЗДАВАТЬ канал самим (по умолчанию — никаким).
"""
from web.routes._common import (
    _log, render_template, session, request, jsonify,
)


def _guild_roles(bot, guild_id):
    """Роли гильдии (или демо-набор в превью без бота)."""
    guild = None
    if bot:
        guild = bot.get_guild(int(guild_id))
        if guild is None:
            for g in bot.guilds:
                if str(g.id) == str(guild_id):
                    guild = g
                    break
    roles = []
    if guild:
        roles = [{'id': str(r.id), 'name': r.name, 'color': str(r.color),
                  'position': r.position, 'members': len(getattr(r, 'members', []) or [])}
                 for r in guild.roles]
    else:
        import web.app as _app
        if _app._demo_mode():
            try:
                from web.routes.guild_admin import _demo_roles_seed
                roles = [{'id': str(r['id']), 'name': r['name'], 'color': r['color'],
                          'position': i, 'members': int(r.get('members') or 0)}
                         for i, r in enumerate(_demo_roles_seed())]
            except Exception as ex:
                _log.debug('staff_limits_panel: демо-роли: %s', ex)
    roles = [r for r in roles if r['name'] != '@everyone']
    roles.sort(key=lambda x: x['position'], reverse=True)
    return roles


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    import web.app as _app
    from services import staff_limits as SL
    from services import log_settings as LS

    # ── страницы ────────────────────────────────────────────────────────
    @app.route('/staff-limits')
    @login_required
    @role_required('admin')
    def staff_limits_page():
        return render_template('staff_limits.html',
                               role=session.get('role'),
                               username=session.get('username'))

    @app.route('/log-settings')
    @login_required
    @role_required('admin')
    def log_settings_page():
        return render_template('log_settings.html',
                               role=session.get('role'),
                               username=session.get('username'))

    # ── API: лимиты ────────────────────────────────────────────────────
    @app.route('/api/guild/<guild_id>/staff-limits')
    @login_required
    @role_required('mod')
    def api_staff_limits_get(guild_id):
        overrides = SL.get_role_limits(guild_id)
        roles = _guild_roles(_app.bot_instance, guild_id)
        for r in roles:
            r['limits'] = overrides.get(r['id']) or {}
        return jsonify({
            'success': True,
            'defaults': SL.get_limits(guild_id),
            'action_titles': SL.ACTION_TITLES,
            'action_meta': SL.action_meta(),
            'roles': roles,
        })

    @app.route('/api/guild/<guild_id>/staff-limits', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_staff_limits_set(guild_id):
        data = request.get_json(silent=True) or {}
        limits = data.get('limits')
        if not isinstance(limits, dict):
            return jsonify({'success': False, 'error': 'Неверный формат'}), 400
        clean = {k: int(v) for k, v in limits.items()
                 if k in SL.DEFAULT_LIMITS and isinstance(v, int) and v > 0}
        if not clean:
            return jsonify({'success': False, 'error': 'Пустые лимиты'}), 400
        SL.set_limits(guild_id, **clean)
        return jsonify({'success': True, 'defaults': SL.get_limits(guild_id)})

    @app.route('/api/guild/<guild_id>/staff-limits/role', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_staff_limits_role_set(guild_id):
        data = request.get_json(silent=True) or {}
        role_id = str(data.get('role_id') or '').strip()
        limits = data.get('limits')
        if not role_id or not isinstance(limits, dict):
            return jsonify({'success': False, 'error': 'Неверный формат'}), 400
        clean = {k: int(v) for k, v in limits.items()
                 if k in SL.DEFAULT_LIMITS and isinstance(v, int) and v > 0}
        saved = SL.set_role_limits(guild_id, role_id, **clean)
        return jsonify({'success': True, 'limits': saved})

    @app.route('/api/guild/<guild_id>/staff-limits/role/delete', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_staff_limits_role_delete(guild_id):
        data = request.get_json(silent=True) or {}
        role_id = str(data.get('role_id') or '').strip()
        if not role_id:
            return jsonify({'success': False, 'error': 'Не указана роль'}), 400
        SL.clear_role_limits(guild_id, role_id)
        return jsonify({'success': True})

    # ── API: настройки логов ───────────────────────────────────────────
    @app.route('/api/guild/<guild_id>/log-settings')
    @login_required
    @role_required('mod')
    def api_log_settings_get(guild_id):
        return jsonify({'success': True,
                        'settings': LS.get_log_settings(guild_id),
                        'categories': [{'key': k, 'label': l, 'emoji': e}
                                       for k, l, e in LS.LOG_CATEGORIES]})

    @app.route('/api/guild/<guild_id>/log-settings', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_log_settings_set(guild_id):
        data = request.get_json(silent=True) or {}
        settings = LS.set_log_settings(guild_id,
                                       enabled=data.get('enabled'),
                                       autocreate=data.get('autocreate'))
        return jsonify({'success': True, 'settings': settings})
