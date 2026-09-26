# -*- coding: utf-8 -*-
"""Щит сервера (анти-нюк): страница /guardian + API настройки.

Движок — cogs/guardian.py; конфиг — data/guardian_<gid>.json (тот же файл,
что читает бот: меняешь в панели — бот подхватывает мгновенно).

Доступы: страница и настройка — Админ+ (как Анти-рейд);
компактная сводка /summary — Мод+ (её читает Центр безопасности).
Канал тревог настраивается на хабе «Каналы и маршруты» (guardian_channel).
"""
from web.routes._common import (
    _log, _fire_panel_notification, _live_publish,
    render_template, session, request, jsonify,
)

from cogs import guardian as G


def _gid(ctx):
    try:
        return int(ctx.active_guild_id() or 0)
    except (TypeError, ValueError):
        return 0


def _int_gid(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _resolve_names(gid, cfg):
    """Имена для ID белого списка, когда бот онлайн (иначе — None)."""
    users = {}
    roles = {}
    try:
        import web.app as _app
        bot = _app.bot_instance
    except Exception as _ex:
        _log.debug('guardian: resolve bot: %s', _ex)
        bot = None
    guild = bot.get_guild(int(gid)) if bot and gid else None
    if guild is None:
        return users, roles
    for uid in cfg.get('whitelist_users') or []:
        try:
            m = guild.get_member(int(uid))
        except (TypeError, ValueError) as _ex:
            _log.debug('guardian: resolve member %s: %s', uid, _ex)
            m = None
        users[str(uid)] = str(m) if m else None
    for rid in cfg.get('whitelist_roles') or []:
        try:
            r = guild.get_role(int(rid))
        except (TypeError, ValueError) as _ex:
            _log.debug('guardian: resolve role %s: %s', rid, _ex)
            r = None
        roles[str(rid)] = getattr(r, 'name', None) if r else None
    for uid in cfg.get('bot_whitelist_users') or []:
        if str(uid) in users:
            continue
        try:
            m = guild.get_member(int(uid))
        except (TypeError, ValueError) as _ex:
            _log.debug('guardian: resolve bot-wl member %s: %s', uid, _ex)
            m = None
        users[str(uid)] = str(m) if m else None
    for rid in cfg.get('bot_whitelist_roles') or []:
        if str(rid) in roles:
            continue
        try:
            r = guild.get_role(int(rid))
        except (TypeError, ValueError) as _ex:
            _log.debug('guardian: resolve bot-wl role %s: %s', rid, _ex)
            r = None
        roles[str(rid)] = getattr(r, 'name', None) if r else None
    return users, roles


def _roles_for_pick(gid):
    """Роли сервера для пикера в Щите (бот офлайн — демо-набор превью)."""
    import web.app as _app
    bot = _app.bot_instance
    guild = None
    if bot:
        try:
            guild = bot.get_guild(int(gid))
            if guild is None:
                guild = next((g for g in bot.guilds if str(g.id) == str(gid)), None)
        except (TypeError, ValueError):
            guild = None
    out = []
    if guild:
        out = [{'id': str(r.id), 'name': r.name, 'color': str(r.color)}
               for r in guild.roles if r.name != '@everyone']
    elif _app._demo_mode():
        try:
            from web.routes.guild_admin import _demo_roles_seed
            out = [{'id': str(r['id']), 'name': r['name'], 'color': r['color']}
                   for r in _demo_roles_seed() if r.get('name') != '@everyone']
        except Exception as ex:
            _log.debug('guardian: демо-роли: %s', ex)
    return out


def _members_for_pick(gid):
    """Участники сервера для пикера в Щите (бот офлайн — демо-набор превью)."""
    import web.app as _app
    bot = _app.bot_instance
    guild = None
    if bot:
        try:
            guild = bot.get_guild(int(gid))
            if guild is None:
                guild = next((g for g in bot.guilds if str(g.id) == str(gid)), None)
        except (TypeError, ValueError):
            guild = None
    out = []
    if guild:
        try:
            for m in sorted(guild.members,
                            key=lambda x: (getattr(x, 'display_name', '') or '').lower()):
                label = (getattr(m, 'display_name', None)
                         or str(m)) + (' · бот' if getattr(m, 'bot', False) else '')
                out.append({'id': str(m.id), 'name': label})
                if len(out) >= 1000:      # огромные серверы — пикер не душим
                    break
        except Exception as ex:
            _log.debug('guardian: участники: %s', ex)
    elif _app._demo_mode():
        try:
            from web.routes._common import DEMO_MEMBERS
            for m in DEMO_MEMBERS:
                label = (m.get('display_name') or m.get('name') or m.get('id', '')) \
                    + (' · бот' if m.get('bot') else '')
                out.append({'id': str(m.get('id')), 'name': label})
        except Exception as ex:
            _log.debug('guardian: демо-участники: %s', ex)
    return out


def guardian_view(gid):
    """Полный витринный вид конфига для страницы (и для тестов)."""
    cfg = G.load_cfg(gid)
    events = []
    for spec in G.EVENT_SPECS:
        ev = (cfg.get('events') or {}).get(spec['key']) or {}
        events.append({
            'key': spec['key'], 'label': spec['label'], 'icon': spec['icon'],
            'desc': spec['desc'],
            'enabled': bool(ev.get('enabled')),
            'threshold': int(ev.get('threshold', 3)),
            'window': int(ev.get('window', 10)),
            'action': ev.get('action'),
        })
    incidents = list(reversed(cfg.get('incidents') or []))
    users_r, roles_r = _resolve_names(gid, cfg)
    resolved = {'users': users_r, 'roles': roles_r}
    return {
        'enabled': bool(cfg.get('enabled')),
        'punishment': cfg.get('punishment'),
        'bot_action': cfg.get('bot_action'),
        'kick_unauthorized_bots': bool(cfg.get('kick_unauthorized_bots')),
        'events': events,
        'punishments': [{'key': k, 'label': v} for k, v in G.PUNISHMENTS],
        'whitelist_users': list(cfg.get('whitelist_users') or []),
        'whitelist_roles': list(cfg.get('whitelist_roles') or []),
        'bot_whitelist_users': list(cfg.get('bot_whitelist_users') or []),
        'bot_whitelist_roles': list(cfg.get('bot_whitelist_roles') or []),
        'incidents': incidents,
        'resolved': resolved,
        'events_on': sum(1 for e in events if e['enabled']),
        'events_total': len(events),
    }


def guardian_summary(gid):
    """Компактная сводка для Центра безопасности и виджетов."""
    cfg = G.load_cfg(gid)
    events = cfg.get('events') or {}
    incidents = cfg.get('incidents') or []
    return {
        'enabled': bool(cfg.get('enabled')),
        'events_on': sum(1 for e in events.values() if isinstance(e, dict)
                         and e.get('enabled')),
        'events_total': len(events),
        'incidents_total': len(incidents),
        'last_incident': incidents[-1] if incidents else None,
        'punishment': cfg.get('punishment'),
        'link': '/guardian',
    }


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/guardian')
    @login_required
    @role_required('admin')
    def guardian_page():
        return render_template('guardian.html',
                               role=session.get('role'),
                               username=session.get('username'),
                               guild_id=_gid(ctx))

    @app.route('/api/guild/<gid>/guardian', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_guardian(gid):
        gid = _gid(ctx) or _int_gid(gid)
        if request.method == 'GET':
            # Тяжёлые списки (роли/участники) нужны только пикерам и почти не
            # меняются. Частый live-опрос (каждые несколько секунд) ходит с
            # ?light=1 и получает ТОЛЬКО конфиг — раньше каждый тик собирал до
            # 1000 участников, чем грузил event-loop бота и тормозил страницу.
            # Первый (без light) ответ приносит роли/участники для пикеров.
            light = str(request.args.get('light', '')).lower() in ('1', 'true', 'yes')
            body = {'success': True, 'cfg': guardian_view(gid)}
            if not light:
                body['roles'] = _roles_for_pick(gid)
                body['members'] = _members_for_pick(gid)
            return jsonify(body)

        # POST: принять витрину, нормализовать, сохранить (файл бота)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'success': False,
                            'error': 'Пустой или битый JSON'}), 400
        if not isinstance(data.get('events'), dict):
            return jsonify({'success': False,
                            'error': 'Нет блока событий (events)'}), 400
        pun = str(data.get('punishment') or 'strip')
        if pun not in G.PUNISH_LABELS:
            return jsonify({'success': False,
                            'error': 'Неизвестная мера наказания'}), 400
        bact = str(data.get('bot_action') or 'strip')
        if bact not in G.PUNISH_LABELS:
            return jsonify({'success': False,
                            'error': 'Неизвестная мера для ботов'}), 400
        # инциденты не доверяем клиенту — берём с диска
        current = G.load_cfg(gid)
        data['incidents'] = current.get('incidents') or []
        cfg = G.save_cfg(gid, data)
        who = session.get('username', '?')
        _fire_panel_notification(
            'guardian', 'Щит сервера: настройки обновлены',
            f'{who}: мера — {G.PUNISH_LABELS.get(cfg["punishment"], "?")}, '
            f'событий активно — {sum(1 for e in (cfg.get("events") or {}).values() if e.get("enabled"))}')
        _live_publish(gid, 'guardian')   # живой пуш: страница Щита обновится сразу
        _live_publish(gid, 'security')   # и Центр безопасности (он показывает статус Щита)
        return jsonify({'success': True, 'cfg': guardian_view(gid)})

    @app.route('/api/guild/<gid>/guardian/summary')
    @login_required
    @role_required('mod')
    def api_guardian_summary(gid):
        gid = _gid(ctx) or _int_gid(gid)
        return jsonify({'success': True, 'guardian': guardian_summary(gid)})
