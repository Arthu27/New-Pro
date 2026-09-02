# -*- coding: utf-8 -*-
"""Права ролей и доступ к панели (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

import hashlib
import threading

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone)

# ── Кэш раздела «Доступ» (права команд) ────────────────────────────────────
# Список ролей сервера и ACL не меняются каждую секунду, но страница живёт
# на SSE-обновлениях и раньше на каждый сигнал пересобирала весь ответ
# (роли с подсчётом участников + повторный парс каталога + два чтения БД).
# На крупном сервере (тысячи участников, десятки ролей) это давало
# «данные долго грузятся». Держим готовый payload за TTL, по ETag отдаём
# 304 (мгновенно, без тела), а любая запись прав сбрасывает кэш и шлёт
# точечный SSE-сигнал — данные остаются свежими.
_ROLE_TTL = 30.0          # сек: состав ролей сервера меняется редко
_PAYLOAD_TTL = 5.0        # сек: склейка ролей + каталог + ACL
_perm_cache_lock = threading.Lock()
_roles_cache = {}         # gid -> (ts, [role_dict])
_payload_cache = {}       # gid -> (ts, raw_json, etag)


def _guild_roles(gid, bot, guild):
    """Список ролей гильдии с коротким TTL-кэшем.

    discord.py отдаёт r.members из КЭША бота (без HTTP), но для крупной
    гильдии это проход по всем участникам на КАЖДУЮ роль (O(roles×members))
    на каждый опрос страницы — кэш убирает повторный счёт.
    """
    now = time.time()
    with _perm_cache_lock:
        hit = _roles_cache.get(gid)
        if hit and now - hit[0] < _ROLE_TTL:
            return list(hit[1])

    roles = []
    if guild:
        roles = [
            {'id': str(r.id), 'name': r.name, 'color': str(r.color),
             'position': r.position, 'hoist': r.hoist,
             'permissions': r.permissions.value,
             'members': len(getattr(r, 'members', []) or [])}
            for r in guild.roles
        ]
        roles.sort(key=lambda x: x['position'], reverse=True)
    else:
        # демо-превью без бота: роли из демо-набора (тот же источник, что
        # /api/role-map) — страница «Права команд» живая в превью.
        import web.app as _app
        if _app._demo_mode():
            try:
                from web.routes.guild_admin import _demo_roles_seed
                roles = [
                    {'id': str(r['id']), 'name': r['name'], 'color': r['color'],
                     'position': int(r['id']) if str(r['id']).isdigit() else 0,
                     'hoist': False, 'permissions': 0,
                     'members': int(r.get('members') or 0)}
                    for r in _demo_roles_seed()
                ]
                roles.sort(key=lambda x: x['position'])
            except Exception as _ex:
                _log.debug("роли: демо-набор недоступен: %s", _ex)

    with _perm_cache_lock:
        _roles_cache[gid] = (now, list(roles))
    return roles


def _invalidate_perm_cache(gid):
    """Сбросить кэш после любой записи прав + пнуть открытые страницы по SSE."""
    try:
        gid = int(gid)
    except (TypeError, ValueError):
        return
    with _perm_cache_lock:
        _roles_cache.pop(gid, None)
        _payload_cache.pop(gid, None)
    try:
        from services.live_bus import publish
        publish(gid, 'permissions')
    except Exception as _ex:
        _log.debug("permissions SSE-сигнал не отправлен: %s", _ex)


def _gid(guild_id):
    """int(id сервера) или None. Без него int('не-число') ронял обработчик
    с трейсбеком (глобальный guard MAIN_GUILD_ID ловит такое только когда
    MAIN_GUILD_ID задан)."""
    try:
        return int(guild_id)
    except (TypeError, ValueError):
        return None


def register(ctx):
    app = ctx.app
    ROLES = ctx.ROLES
    login_required = ctx.login_required
    role_required = ctx.role_required
    MAIN_GUILD_ID = ctx.MAIN_GUILD_ID
    active_guild_id = ctx.active_guild_id
    _resolve_member_async = ctx._resolve_member_async

    # ═══════════════════════════════════════════════════════════════════
    #  РОЛИ И ДОСТУП (Command ACL) — управление доступом к командам
    # ═══════════════════════════════════════════════════════════════════
    @app.route('/role-permissions')
    @login_required
    @role_required('owner')
    def role_permissions_page():
        return render_template(
            'role_permissions.html',
            role=session.get('role'),
            username=session.get('username'),
            guild_id=active_guild_id())

    @app.route('/api/panel/visibility', methods=['GET', 'POST'])
    @login_required
    @role_required('owner')
    def api_panel_visibility():
        """Кому видны уведомления и лента активности (min-роль)."""
        f = 'data/panel_visibility.json'
        defaults = {'notifications_min_role': 'mod', 'activity_min_role': 'mod'}
        cur = dict(defaults)
        try:
            if os.path.exists(f):
                with open(f, encoding='utf-8') as fp:
                    d = json.load(fp)
                if isinstance(d, dict):
                    cur.update({k: v for k, v in d.items() if k in defaults})
        except Exception as _ex:
            _log.debug("api_panel_visibility(): подавлено: %s", _ex)
        if request.method == 'GET':
            return jsonify({'success': True, 'visibility': cur})
        data = request.get_json(silent=True) or {}
        changed = False
        for k in defaults:
            v = str(data.get(k, cur[k]) or '').strip()
            if v in ROLES:
                changed = changed or (cur[k] != v)
                cur[k] = v
        os.makedirs('data', exist_ok=True)
        with open(f, 'w', encoding='utf-8') as fp:
            json.dump(cur, fp, indent=2, ensure_ascii=False)
        if changed:
            try:
                from services.live_bus import publish_global
                publish_global('panel_visibility')
            except Exception as _ex:
                _log.debug("visibility SSE: %s", _ex)
        return jsonify({'success': True, 'visibility': cur})

    @app.route('/panel-access')
    @login_required
    @role_required('owner')
    def panel_access_page():
        """Панели и роли: какие Discord-роли получают панель
        Владелец / Администратор / Модератор / Участник."""
        return render_template(
            'panel_access.html',
            role=session.get('role'),
            username=session.get('username'),
            guild_id=active_guild_id())

    @app.route('/panel-menu')
    @login_required
    @role_required('owner')
    def panel_menu_page():
        """Меню панели: какие категории (группы) и страницы (комнаты)
        видны в панели Модератора и Администратора."""
        return render_template(
            'panel_menu.html',
            role=session.get('role'),
            username=session.get('username'),
            guild_id=active_guild_id())

    @app.route('/api/role-permissions/<guild_id>')
    @login_required
    @role_required('owner')
    def api_role_permissions_get(guild_id):
        """Вернуть: все роли сервера, категории команд, текущие ACL, действия.

        Горячий путь SSE-страницы: готовый payload держим в памяти за TTL,
        а клиенту по ETag отдаём 304 (без тела) — опрос «не изменилось»
        стоит миллисекунды и не пересчитывает роли/каталог/ACL.
        """
        gid = _gid(guild_id)
        if gid is None:
            return jsonify({'success': False, 'error': 'Неверный ID сервера'}), 400
        from services.permission_acl import (all_categories, ACTIONS,
                                            load_action_acl, effective_acl)
        now = time.time()

        with _perm_cache_lock:
            hit = _payload_cache.get(gid)
        if hit and now - hit[0] < _PAYLOAD_TTL:
            raw, etag = hit[1], hit[2]
            if etag in request.headers.get('If-None-Match', ''):
                return Response(status=304,
                                headers={'ETag': etag, 'Cache-Control': 'no-cache'})
            return Response(raw, mimetype='application/json',
                            headers={'ETag': etag, 'Cache-Control': 'no-cache'})

        import web.app as _app
        bot = _app.bot_instance
        guild = None
        if bot:
            guild = bot.get_guild(gid)
            if guild is None:
                for g in bot.guilds:
                    if str(g.id) == str(guild_id):
                        guild = g
                        break
        roles = _guild_roles(gid, bot, guild)
        payload = {
            'success': True,
            'roles': roles,
            # ПОЛНЫЙ список команд (живой каталог видимых slash + реальные
            # префиксные/мод-команды вроде staff-stats): страница «Права
            # команд» должна давать разрешить ЛЮБУЮ рабочую команду, а не
            # только 6 видимых в «/» slash (заказ владельца — новая команда
            # статистики не отображалась). Призраков удалённых тут нет —
            # список статически сверен с реальными когами.
            'categories': all_categories(),
            'acl': effective_acl(gid),
            'actions': ACTIONS,
            'action_acl': load_action_acl(gid),
        }
        raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        etag = '"' + hashlib.md5(raw.encode('utf-8')).hexdigest() + '"'
        with _perm_cache_lock:
            _payload_cache[gid] = (now, raw, etag)

        if etag in request.headers.get('If-None-Match', ''):
            return Response(status=304,
                            headers={'ETag': etag, 'Cache-Control': 'no-cache'})
        return Response(raw, mimetype='application/json',
                        headers={'ETag': etag, 'Cache-Control': 'no-cache'})

    @app.route('/api/role-permissions/<guild_id>/action/set', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_role_permissions_action_set(guild_id):
        """Классические разрешения: установить роли для действия (бан/мут/…).
        Строгая модель: видит действие ТОЛЬКО роль из списка. Пустой role_ids —
        снять правило, и тогда действие ЗАПРЕЩЕНО всем (default-deny)."""
        gid = _gid(guild_id)
        if gid is None:
            return jsonify({'success': False, 'error': 'Неверный ID сервера'}), 400
        from services.permission_acl import ACTIONS, set_action_rule
        data = request.get_json(silent=True) or {}
        action = data.get('action', '').strip()
        role_ids = data.get('role_ids', []) or []
        if action not in ACTIONS:
            return jsonify({'success': False, 'error': 'Неизвестное действие'}), 400
        set_action_rule(gid, action, [str(r) for r in role_ids])
        _invalidate_perm_cache(guild_id)
        return jsonify({'success': True, 'action': action, 'role_ids': role_ids})

    @app.route('/api/role-permissions/<guild_id>/actions/clear', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_role_permissions_actions_clear(guild_id):
        """Снять все классические ограничения (все действия доступны всем)."""
        gid = _gid(guild_id)
        if gid is None:
            return jsonify({'success': False, 'error': 'Неверный ID сервера'}), 400
        from services.permission_acl import clear_action_rules
        clear_action_rules(gid)
        _invalidate_perm_cache(guild_id)
        return jsonify({'success': True})

    @app.route('/api/role-permissions/<guild_id>/set', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_role_permissions_set(guild_id):
        """Установить роли для команды/категории."""
        gid = _gid(guild_id)
        if gid is None:
            return jsonify({'success': False, 'error': 'Неверный ID сервера'}), 400
        from services.permission_acl import (set_rule, clear_rule, load_acl,
                                            save_acl, materialize_category,
                                            all_categories)
        data = request.get_json(silent=True) or {}
        command = data.get('command', '').strip()
        role_ids = data.get('role_ids', []) or []
        if not command:
            return jsonify({'success': False, 'error': 'Нет команды'}), 400
        # у команды может быть правило на КАТЕГОРИЮ — разворачиваем его в
        # явные правила на команды категории, чтобы правка одной команды не
        # пересекалась с категорийным ограничением (иначе «выдал — а не дал»)
        for cat, cmds in all_categories().items():
            if command in cmds:
                acl = load_acl(gid)
                if cat in acl:
                    materialize_category(acl, cat)
                    save_acl(gid, acl)
                break
        if role_ids:
            set_rule(gid, command, [str(r) for r in role_ids])
        else:
            clear_rule(gid, command)
        _invalidate_perm_cache(guild_id)
        return jsonify({'success': True})

    @app.route('/api/role-permissions/<guild_id>/clear', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_role_permissions_clear(guild_id):
        """Сбросить все ограничения (всё доступно всем)."""
        gid = _gid(guild_id)
        if gid is None:
            return jsonify({'success': False, 'error': 'Неверный ID сервера'}), 400
        from services.permission_acl import save_acl
        save_acl(gid, {})
        _invalidate_perm_cache(guild_id)
        return jsonify({'success': True})

    @app.route('/api/role-permissions/<guild_id>/preset', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_role_permissions_preset(guild_id):
        """Применить пресет: moderator / admin / member / everyone."""
        gid = _gid(guild_id)
        if gid is None:
            return jsonify({'success': False, 'error': 'Неверный ID сервера'}), 400
        from services.permission_acl import all_categories, save_acl
        data = request.get_json(silent=True) or {}
        preset = data.get('preset', '')
        role_ids = [str(r) for r in (data.get('role_ids', []) or [])]
        if not role_ids:
            return jsonify({'success': False, 'error': 'Выберите хотя бы одну роль'}), 400
        from services.permission_acl import materialize_category
        cats_by_preset = {
            'mod': {'Модерация'},
            'staff': {'Модерация', 'Тикеты', 'Логи'},
            'all': set(all_categories().keys()),
        }.get(preset)
        if cats_by_preset is None:
            return jsonify({'success': False, 'error': 'Неизвестный пресет'}), 400
        acl = {}
        for cat, cmds in all_categories().items():
            if cat in cats_by_preset:
                acl[cat] = role_ids
                materialize_category(acl, cat)  # правило на КАЖДУЮ команду
        save_acl(gid, acl)
        _invalidate_perm_cache(guild_id)
        return jsonify({'success': True, 'preset': preset})

    @app.route('/api/role-permissions/<guild_id>/category/everyone', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_role_permissions_category_everyone(guild_id):
        """Открыть категорию для всех: снять ограничения с категории и всех её команд."""
        gid = _gid(guild_id)
        if gid is None:
            return jsonify({'success': False, 'error': 'Неверный ID сервера'}), 400
        from services.permission_acl import all_categories, load_acl, save_acl
        data = request.get_json(silent=True) or {}
        category = data.get('category', '').strip()
        if not category:
            return jsonify({'success': False, 'error': 'Не указана категория'}), 400
        cmds = all_categories().get(category, [])
        acl = load_acl(gid)
        acl.pop(category, None)   # снять ограничение с категории
        for c in cmds:
            acl.pop(c, None)      # снять ограничение с каждой команды
        save_acl(gid, acl)
        _invalidate_perm_cache(guild_id)
        return jsonify({'success': True, 'category': category,
                        'commands_cleared': len(cmds)})

    @app.route('/api/role-permissions/<guild_id>/category/assign', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_role_permissions_category_assign(guild_id):
        """Топливо: назначить несколько ролей сразу на целую категорию (все её команды)."""
        gid = _gid(guild_id)
        if gid is None:
            return jsonify({'success': False, 'error': 'Неверный ID сервера'}), 400
        from services.permission_acl import (load_acl, save_acl,
                                            materialize_category, all_categories)
        data = request.get_json(silent=True) or {}
        category = data.get('category', '').strip()
        role_ids = [str(r) for r in (data.get('role_ids', []) or [])]
        if not category:
            return jsonify({'success': False, 'error': 'Не указана категория'}), 400
        # ЖИВОЙ каталог (как на странице) + legacy: раньше искали только в
        # статическом списке, названия не совпадали — «Дать ролям» писал пусто
        cmds = all_categories().get(category, [])
        acl = load_acl(gid)
        materialize_category(acl, category)
        if role_ids:
            for c in cmds:
                acl[c] = role_ids
        else:
            for c in cmds:
                acl.pop(c, None)
        save_acl(gid, acl)
        _invalidate_perm_cache(guild_id)
        return jsonify({'success': True, 'category': category,
                        'role_ids': role_ids, 'commands': len(cmds)})
