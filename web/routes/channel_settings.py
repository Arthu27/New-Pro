# -*- coding: utf-8 -*-
"""Каналы и маршруты: единая страница настройки «куда бот что пишет».

Маршруты (см. ROUTE_SPECS в services/channel_routes.py):
  • proof_channel     — канал доказательств (native: data/channel_routes.json,
                        бот читает через cogs/proof_cog._proof_channel);
  • appeals_channel   — карточки апелляций (GuildData('appeals').state);
  • welcome_channel   — приветствия PRO (GuildData('welcome_pro').settings);
  • antiraid/security/anticrash — логи живых систем защиты (их же конфиги).

Настройки вырезанных/спящих систем (тикеты, считалка, starboard, ночные
сводки, смены, tag jail) на странице не показываются — маршрутов нет.

Просмотр — mod+ (чтобы у команды не было вопросов «почему улетело туда»),
изменение — admin+ (остальные просто видят, как настроено).
"""
from web.routes._common import (
    _log, _fire_panel_notification, _live_publish,
    render_template, session, request, jsonify,
    os, json,
)

from db import GuildData
from services import channel_routes as CHR


def _active_gid(ctx):
    import web.app as _app
    bot = _app.bot_instance
    gid = ctx.active_guild_id()
    if bot and gid:
        try:
            g = bot.get_guild(int(gid))
            if g is not None:
                return g.id
        except (TypeError, ValueError) as _ex:
            _log.debug('channel-settings: %s', _ex)
    try:
        return int(gid or 0)
    except (TypeError, ValueError):
        return 0


# ─────────────────────────────────────────────────────────────────────
# Адаптеры: читаем/пишем ровно те хранилища, что использует бот.
# ─────────────────────────────────────────────────────────────────────
def _appeals_get(gid):
    state = GuildData('appeals').get(gid, 'state', {}) or {}
    return int(state.get('log_channel_id') or 0)


def _appeals_set(gid, cid):
    db = GuildData('appeals')
    state = db.get(gid, 'state', {}) or {}
    state.setdefault('next_id', 1)
    state.setdefault('items', [])
    state['log_channel_id'] = int(cid)
    db.set(gid, 'state', state)
    return True


def _welcome_get(gid):
    st = GuildData('welcome_pro').get(gid, 'settings', {}) or {}
    return int(st.get('channel_id') or 0)


def _welcome_set(gid, cid):
    db = GuildData('welcome_pro')
    st = db.get(gid, 'settings', {}) or {}
    st['channel_id'] = int(cid)
    db.set(gid, 'settings', st)
    return True


def _json_load(path):
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _json_save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _antiraid_path(gid):
    return f'data/antiraid_{gid}.json'


def _antiraid_get(gid):
    return int(_json_load(_antiraid_path(gid)).get('alert_channel_id') or 0)


def _antiraid_set(gid, cid):
    path = _antiraid_path(gid)
    data = _json_load(path)
    data['alert_channel_id'] = int(cid) or None
    _json_save(path, data)
    return True


def _security_path(gid):
    return f'data/security_{gid}.json'


def _security_get(gid):
    try:
        return int(_json_load(_security_path(gid)).get('log_channel') or 0)
    except (TypeError, ValueError):
        return 0


def _security_set(gid, cid):
    path = _security_path(gid)
    data = _json_load(path)
    data['log_channel'] = int(cid) or None
    _json_save(path, data)
    return True


# Анти-краш — глобальный конфиг бота (error_handler.CONFIG_PATH).
ANTICRASH_CFG = 'data/anticrash_config.json'


def _anticrash_get(_gid):
    return int(_json_load(ANTICRASH_CFG).get('log_channel_id') or 0)


def _anticrash_set(_gid, cid):
    data = _json_load(ANTICRASH_CFG)
    data['log_channel_id'] = int(cid)
    _json_save(ANTICRASH_CFG, data)
    return True


# ── Заявки в команду: ветки и общий канал (services/staff_roles) ──────────
from services import staff_roles as _SR

_STAFF_CHANNEL_KEYS = {
    'staff_helper_channel': 'helper_channel',
    'staff_moderator_channel': 'moderator_channel',
    'staff_apply_channel': 'apply_channel',
}


def _staff_get(key):
    def _get(gid):
        return int(_SR.load_settings(gid).get(_STAFF_CHANNEL_KEYS[key]) or 0)
    return _get


def _staff_set(key):
    def _set(gid, cid):
        return _SR.save_setting(gid, _STAFF_CHANNEL_KEYS[key], cid)
    return _set


ADAPTERS = {
    'ban_appeal_channel': (CHR.get_route, CHR.set_route),
    'appeal_menu_channel': (CHR.get_route, CHR.set_route),
    'pagerduty_channel': (CHR.get_route, CHR.set_route),
    'proof_channel': (CHR.get_route, CHR.set_route),
    'appeals_channel': (_appeals_get, _appeals_set),
    'welcome_channel': (_welcome_get, _welcome_set),
    'guardian_channel': (CHR.get_route, CHR.set_route),
    'antiraid_channel': (_antiraid_get, _antiraid_set),
    'security_channel': (_security_get, _security_set),
    'anticrash_channel': (_anticrash_get, _anticrash_set),
    'staff_helper_channel': (_staff_get('staff_helper_channel'), _staff_set('staff_helper_channel')),
    'staff_moderator_channel': (_staff_get('staff_moderator_channel'), _staff_set('staff_moderator_channel')),
    'staff_apply_channel': (_staff_get('staff_apply_channel'), _staff_set('staff_apply_channel')),
}


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/channel-settings')
    @login_required
    @role_required('mod')
    def channel_settings_page():
        # Метки/описания маршрутов отдаём сразу с сервера: каркас страницы
        # (строки и селекты) рисуется мгновенно, до любых fetch — каналы и
        # сохранённые значения лишь наполняют уже готовые селекты.
        specs = [{
            'key': s['key'],
            'label': s['label'],
            'icon': s['icon'],
            'what': s['what'],
            'empty': s['empty'],
            'access': s.get('access', 'Админ'),
            'step': s.get('step'),
            'create_hint': s.get('create_hint', ''),
        } for s in CHR.ROUTE_SPECS]
        return render_template('channel_settings.html',
                               role=session.get('role'),
                               username=session.get('username'),
                               route_specs=specs)

    @app.route('/api/channel-routes', methods=['GET'])
    @login_required
    @role_required('mod')
    def api_channel_routes_list():
        gid = _active_gid(ctx)
        out = []
        for spec in CHR.ROUTE_SPECS:
            get_fn = ADAPTERS[spec['key']][0]
            try:
                cid = int(get_fn(gid, spec['key']) if spec['kind'] == 'native'
                          else get_fn(gid))
            except Exception as _ex:
                _log.debug('channel-routes get %s: %s', spec['key'], _ex)
                cid = 0
            out.append({
                'key': spec['key'],
                'label': spec['label'],
                'icon': spec['icon'],
                'what': spec['what'],
                'empty': spec['empty'],
                'access': spec['access'],
                'step': spec.get('step'),
                'create_hint': spec.get('create_hint', ''),
                'channel_id': cid,
            })
        return jsonify({'success': True, 'routes': out, 'gid': str(gid)})

    @app.route('/api/channel-routes/<key>', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_channel_routes_set(key):
        spec = CHR.spec_for(key)
        if spec is None:
            return jsonify({'success': False, 'error': 'Такого маршрута нет'}), 404
        payload = request.get_json(silent=True) or {}
        raw = str(payload.get('channel_id') or '').strip()
        if raw and not raw.isdigit():
            return jsonify({'success': False,
                            'error': 'ID канала должен быть числом (0 — очистить)'}), 400
        cid = int(raw or 0)
        gid = _active_gid(ctx)
        # если бот онлайн — проверим, что канал реально существует и текстовый
        import web.app as _app
        bot = _app.bot_instance
        if bot and gid and cid:
            guild = bot.get_guild(int(gid))
            if guild is not None:
                ch = guild.get_channel(cid)
                if ch is None:
                    return jsonify({'success': False,
                                    'error': 'Такого канала на сервере нет'}), 404
        set_fn = ADAPTERS[key][1]
        try:
            ok = set_fn(gid, key, cid) if spec['kind'] == 'native' else set_fn(gid, cid)
        except Exception as _ex:
            _log.debug('channel-routes set %s: %s', key, _ex)
            return jsonify({'success': False,
                            'error': 'Не удалось сохранить — попробуйте ещё раз'}), 500
        if not ok:
            return jsonify({'success': False,
                            'error': 'Не удалось сохранить — попробуйте ещё раз'}), 500
        who = session.get('username', '?')
        if cid:
            _fire_panel_notification(
                'channels', f'Маршрут обновлён: {spec["label"]}',
                f'{who}: канал #{cid}')
        else:
            _fire_panel_notification(
                'channels', f'Маршрут очищен: {spec["label"]}',
                f'{who}: вернули поведение по умолчанию')
        _live_publish(gid, 'channels')   # живой пуш: маршруты/каналы обновились
        return jsonify({'success': True, 'key': key, 'channel_id': cid})

    @app.route('/api/staff-role-routes', methods=['GET'])
    @login_required
    @role_required('mod')
    def api_staff_role_routes_get():
        """Роли заявок: настройки + список ролей сервера для селектов."""
        gid = _active_gid(ctx)
        roles_out = []
        for spec in _SR.ROLE_SPECS:
            try:
                rid = int(_SR.load_settings(gid).get(spec['key']) or 0)
            except Exception:
                rid = 0
            roles_out.append({
                'key': spec['key'],
                'label': spec['label'],
                'icon': spec['icon'],
                'what': spec['what'],
                'empty': spec['empty'],
                'role_id': rid,
            })
        guild_roles = []
        import web.app as _app
        bot = _app.bot_instance
        guild = bot.get_guild(int(gid)) if (bot and gid) else None
        if guild is not None:
            guild_roles = [{'id': str(r.id), 'name': r.name}
                           for r in getattr(guild, 'roles', [])]
        elif _app._demo_mode():
            try:
                from web.routes.guild_admin import _demo_roles_seed
                guild_roles = [{'id': str(r['id']), 'name': r['name']}
                               for r in _demo_roles_seed()]
            except Exception as _ex:
                _log.debug('staff-role-routes: демо-роли: %s', _ex)
        return jsonify({'success': True, 'roles': roles_out,
                        'guild_roles': guild_roles, 'gid': str(gid)})

    @app.route('/api/staff-role-routes/<key>', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_staff_role_routes_set(key):
        spec = next((sp for sp in _SR.ROLE_SPECS if sp['key'] == key), None)
        if spec is None:
            return jsonify({'success': False, 'error': 'Такой настройки нет'}), 404
        payload = request.get_json(silent=True) or {}
        raw = str(payload.get('role_id') or '').strip()
        if raw and not raw.isdigit():
            return jsonify({'success': False,
                            'error': 'ID роли должен быть числом (0 — авто)'}), 400
        rid = int(raw or 0)
        gid = _active_gid(ctx)
        # если бот онлайн — роль должна существовать на сервере
        import web.app as _app
        bot = _app.bot_instance
        if bot and gid and rid:
            guild = bot.get_guild(int(gid))
            if guild is not None and guild.get_role(rid) is None:
                return jsonify({'success': False,
                                'error': 'Такой роли на сервере нет'}), 404
        if not _SR.save_setting(gid, key, rid):
            return jsonify({'success': False,
                            'error': 'Не удалось сохранить — попробуйте ещё раз'}), 500
        who = session.get('username', '?')
        _fire_panel_notification(
            'channels', f'Роль заявок: {spec["label"]}',
            f'{who}: ' + (f'роль {rid}' if rid else 'авто (по имени/из .env)'))
        return jsonify({'success': True, 'key': key, 'role_id': rid})
