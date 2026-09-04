# -*- coding: utf-8 -*-
"""Лимиты команды + Логи сервера — панельная сторона.

Лимиты (services/staff_limits.py): глобальные и ПЕР-РОЛЬНЫЕ дневные лимиты
действий модерации. Редактирование — только владелец: зачем лимитам от
«обнаглевших» админов, если их же может поднять сам админ.
Настройки логов (services/log_settings.py): какие категории логировать и
каким разрешено СОЗДАВАТЬ канал самим (по умолчанию — никаким).
"""
from web.routes._common import (
    _safe_json_obj,
    _log, render_template, session, request, jsonify, redirect,
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


def _channels_cache_path(guild_id):
    import os as _os
    _os.makedirs('data', exist_ok=True)
    return f'data/panel_channels_cache_{int(guild_id)}.json'


def _channels_cache_save(guild_id, channels):
    """Запомнить список каналов с живого бота — пикеры логов не пустеют,
    даже если бот перезапускается (владелец всё равно может выбрать канал)."""
    import json as _json
    try:
        with open(_channels_cache_path(guild_id), 'w', encoding='utf-8') as fh:
            _json.dump({'channels': channels or []}, fh, ensure_ascii=False)
    except Exception as ex:
        _log.debug('channels_cache_save: подавлено: %s', ex)


def _channels_cache_load(guild_id):
    import json as _json
    import os as _os
    path = _channels_cache_path(guild_id)
    if not _os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = _json.load(fh)
        chans = data.get('channels') if isinstance(data, dict) else None
        return [c for c in (chans or []) if c.get('id') and c.get('name')]
    except Exception as ex:
        _log.debug('channels_cache_load: подавлено: %s', ex)
        return []


def _guild_channels(bot, guild_id):
    """Текстовые каналы гильдии для пикера «куда писать логи».

    Живой бот → список и кэш; бот офлайн → последний известный список из
    кэша; демо — встроенная структура. Пикеры не пустуют никогда.
    Возвращает (каналы, источник: 'bot'|'cache'|'settings')."""
    live = _guild_channels_live(bot, guild_id)
    if live:
        _channels_cache_save(guild_id, live)
        return live, 'bot'
    cached = _channels_cache_load(guild_id)
    if cached:
        return cached, 'cache'
    return _guild_channels_fallback(guild_id), 'settings'


def _guild_channels_live(bot, guild_id):
    guild = None
    if bot:
        guild = bot.get_guild(int(guild_id))
        if guild is None:
            for g in bot.guilds:
                if str(g.id) == str(guild_id):
                    guild = g
                    break
    channels = []
    if guild:
        # Логи можно писать и в ФОРУМ-канал (владелец держит логи форумом) —
        # показываем текстовые и форумы, форум помечаем в названии.
        import discord as _dc
        pool = [c for c in guild.channels
                if isinstance(c, _dc.TextChannel)
                or c.type == _dc.ChannelType.forum]
        channels = [{'id': str(c.id),
                     'name': (f'{c.name} · форум'
                              if c.type == _dc.ChannelType.forum
                              else f'#{c.name}')}
                    for c in sorted(pool, key=lambda x: x.position)]
    else:
        import web.app as _app
        if _app._demo_mode():
            try:
                import json as _json
                import os as _os
                path = _os.path.join('data', 'demo_channels.json')
                if _os.path.exists(path):
                    with open(path, 'r', encoding='utf-8') as fh:
                        for c in _json.load(fh):
                            _t = c.get('type')
                            _is_forum = _t == 'forum' or bool(c.get('forum'))
                            if _t in ('text', '') or _is_forum:
                                channels.append({
                                    'id': str(c.get('id')),
                                    'name': (str(c.get('name', '')) + ' · форум')
                                            if _is_forum
                                            else '#' + str(c.get('name', ''))})
            except Exception as ex:
                _log.debug('staff_limits_panel: демо-каналы: %s', ex)
            # файла нет (пересборка/чистый data) — вшитый демо-набор, чтобы
            # селекты «куда писать логи» не пустовали в превью
            if not channels:
                channels = [
                    {'id': '1001', 'name': '#правила'},
                    {'id': '1002', 'name': '#новости'},
                    {'id': '1004', 'name': '#флудилка'},
                    {'id': '1005', 'name': '#мемы'},
                    {'id': '1015', 'name': 'журнал-модерации · форум'},
                    {'id': '1010', 'name': '#варны'},
                    {'id': '1009', 'name': '#тикет-логи'},
                    {'id': '1016', 'name': '#анонс-бота'},
                ]
    return channels


def _guild_channels_fallback(guild_id):
    """Совсем без бота и без кэша: каналы, НАСТРОЕННЫЕ ранее для категорий
    логов, — чтобы выбранные значения не пропадали из селектов."""
    try:
        from services import log_settings as _LS
        settings = _LS.get_log_settings(guild_id) or {}
        seen, out = set(), []
        for _k, cid in (settings.get('channels') or {}).items():
            cid = str(cid or '').strip()
            if cid and cid not in seen:
                seen.add(cid)
                out.append({'id': cid, 'name': f'канал {cid}'})
        return out
    except Exception as ex:
        _log.debug('channels_fallback: подавлено: %s', ex)
        return []


def _role_name(bot, guild_id, role_id):
    """Имя роли для журнала изменений (бот офлайн — из демо-набора)."""
    for r in _guild_roles(bot, guild_id):
        if r['id'] == str(role_id):
            return r['name']
    return None


def _win_to_api(sec, default=None):
    """Секунды → {n, unit} для панели (unit: 'h' | 'd')."""
    sec = int(sec or 0) or (default or 86400)
    if sec % 86400 == 0:
        return {'n': max(1, sec // 86400), 'unit': 'd'}
    return {'n': max(1, sec // 3600), 'unit': 'h'}


def _win_to_sec(w):
    """{n, unit} из панели → секунды (клампим 1 час..31 день)."""
    try:
        n = max(1, min(31, int(w.get('n', 1))))
    except (TypeError, ValueError):
        n = 1
    return n * 86400 if str(w.get('unit')) == 'd' else n * 3600


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
        # Лимиты команды живут СЕКЦИЕЙ внутри Щита сервера (заказ владельца)
        return redirect('/guardian#limits')

    @app.route('/log-settings')
    @login_required
    @role_required('admin')
    def log_settings_page():
        return render_template('log_settings.html',
                               role=session.get('role'),
                               username=session.get('username'),
                               main_guild_id=session.get('main_guild_id', ''))

    # ── API: лимиты ────────────────────────────────────────────────────
    @app.route('/api/guild/<guild_id>/staff-limits')
    @login_required
    @role_required('mod')
    def api_staff_limits_get(guild_id):
        overrides = SL.get_role_overrides(guild_id)
        roles = _guild_roles(_app.bot_instance, guild_id)
        for r in roles:
            ov = overrides.get(r['id']) or {}
            r['limits'] = ov.get('limits') or {}
            r['windows'] = {k: _win_to_api(v)
                            for k, v in (ov.get('windows') or {}).items()} or {}
            r['durations'] = ov.get('durations') or {}
        defaults = SL.get_limits(guild_id)
        windows = {k: _win_to_api(v) for k, v in SL.get_windows(guild_id).items()}
        durations = SL.get_durations(guild_id)
        return jsonify({
            'success': True,
            'defaults': defaults,
            'windows': windows,
            'durations': durations,
            'action_titles': SL.ACTION_TITLES,
            'action_meta': SL.action_meta(),
            'roles': roles,
        })

    @app.route('/api/guild/<guild_id>/staff-limits', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_staff_limits_set(guild_id):
        data = _safe_json_obj()
        limits = data.get('limits')
        if (not isinstance(limits, dict) and not isinstance(data.get('windows'), dict)
                and not isinstance(data.get('durations'), dict)):
            return jsonify({'success': False, 'error': 'Неверный формат'}), 400
        clean = {k: int(v) for k, v in (limits or {}).items()
                 if k in SL.DEFAULT_LIMITS and isinstance(v, int) and v > 0}
        wins = {}
        for k, w in (data.get('windows') or {}).items():
            if k in SL.DEFAULT_LIMITS and isinstance(w, dict):
                wins[k] = _win_to_sec(w)
        # потолки длительности: {'mute': 3600} (секунды, 0 = снять)
        durs = {}
        for k, v in (data.get('durations') or {}).items():
            if k in SL.DURATION_KEYS and isinstance(v, int):
                durs[k] = v
        if not clean and not wins and not durs:
            return jsonify({'success': False, 'error': 'Пустые лимиты'}), 400
        if clean:
            SL.set_limits(guild_id, who=session.get('username', '?'), **clean)
        if wins:
            SL.set_windows(guild_id, who=session.get('username', '?'), **wins)
        if durs:
            SL.set_durations(guild_id, who=session.get('username', '?'), **durs)
        return jsonify({'success': True, 'defaults': SL.get_limits(guild_id),
                        'windows': {k: _win_to_api(v)
                                    for k, v in SL.get_windows(guild_id).items()},
                        'durations': SL.get_durations(guild_id)})

    @app.route('/api/guild/<guild_id>/staff-limits/role', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_staff_limits_role_set(guild_id):
        data = _safe_json_obj()
        role_id = str(data.get('role_id') or '').strip()
        limits = data.get('limits')
        if not role_id or (not isinstance(limits, dict)
                           and not isinstance(data.get('windows'), dict)
                           and not isinstance(data.get('clear'), list)
                           and not isinstance(data.get('durations'), dict)):
            return jsonify({'success': False, 'error': 'Неверный формат'}), 400
        clean = {k: int(v) for k, v in (limits or {}).items()
                 if k in SL.DEFAULT_LIMITS and isinstance(v, int) and v > 0}
        wins = {}
        for k, w in (data.get('windows') or {}).items():
            if k in SL.DEFAULT_LIMITS and isinstance(w, dict):
                wins[k] = _win_to_sec(w)
        who = session.get('username', '?')
        rname = _role_name(_app.bot_instance, guild_id, role_id)
        # ключи, которые стёрли в панели: их переопределения снимаем точечно
        clear = [str(k) for k in (data.get('clear') or [])
                 if k in SL.DEFAULT_LIMITS]
        if clear:
            SL.unset_role_keys(guild_id, role_id,
                               limit_keys=clear, window_keys=clear,
                               who=who, role_name=rname)
        saved = SL.set_role_limits(guild_id, role_id, who=who,
                                   role_name=rname, **clean)
        if wins:
            SL.set_role_windows(guild_id, role_id, who=who,
                                role_name=rname, **wins)
        rdurs = {}
        for k, v in (data.get('durations') or {}).items():
            if k in SL.DURATION_KEYS and isinstance(v, int):
                rdurs[k] = v
        if rdurs:
            SL.set_role_durations(guild_id, role_id, who=who,
                                  role_name=rname, **rdurs)
        return jsonify({'success': True, 'limits': saved,
                        'windows': {k: _win_to_api(v) for k, v in wins.items()},
                        'durations': SL.get_role_overrides(guild_id)
                                     .get(role_id, {}).get('durations', {})})

    @app.route('/api/guild/<guild_id>/staff-limits/role/delete', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_staff_limits_role_delete(guild_id):
        data = _safe_json_obj()
        role_id = str(data.get('role_id') or '').strip()
        if not role_id:
            return jsonify({'success': False, 'error': 'Не указана роль'}), 400
        SL.clear_role_limits(guild_id, role_id,
                             who=session.get('username', '?'),
                             role_name=_role_name(_app.bot_instance,
                                                  guild_id, role_id))
        return jsonify({'success': True})

    # ── API: журнал изменений лимитов («кто/когда/что» + откат) ────────
    @app.route('/api/guild/<guild_id>/staff-limits/changes')
    @login_required
    @role_required('admin')
    def api_staff_limits_changes(guild_id):
        return jsonify({'success': True,
                        'changes': SL.get_changes(guild_id, 60)})

    @app.route('/api/guild/<guild_id>/staff-limits/changes/revert',
               methods=['POST'])
    @login_required
    @role_required('owner')
    def api_staff_limits_revert(guild_id):
        data = _safe_json_obj()
        cid = str(data.get('id') or '').strip()
        if not cid:
            return jsonify({'success': False,
                            'error': 'Не указано изменение'}), 400
        done, entry = SL.revert_change(guild_id, cid,
                                       who=session.get('username', '?'))
        if not done:
            return jsonify({'success': False,
                            'error': 'Изменение не найдено'}), 404
        return jsonify({'success': True, 'entry': entry,
                        'changes': SL.get_changes(guild_id, 60)})

    # ── API: настройки логов ───────────────────────────────────────────
    @app.route('/api/guild/<guild_id>/log-settings')
    @login_required
    @role_required('mod')
    def api_log_settings_get(guild_id):
        channels, src = _guild_channels(_app.bot_instance, guild_id)
        return jsonify({'success': True,
                        'settings': LS.get_log_settings(guild_id),
                        'channels': channels,
                        'channels_source': src,
                        'categories': [{'key': k, 'label': l, 'emoji': e}
                                       for k, l, e in LS.LOG_CATEGORIES]})

    @app.route('/api/guild/<guild_id>/log-settings', methods=['POST'])
    @login_required
    @role_required('owner')
    def api_log_settings_set(guild_id):
        data = _safe_json_obj()
        settings = LS.set_log_settings(guild_id,
                                       enabled=data.get('enabled'),
                                       autocreate=data.get('autocreate'),
                                       channels=data.get('channels'))
        # Владелец явно выбрал каналы в панели — категория снова может
        # автосоздаваться, если канал когда-нибудь пропадёт (маркер
        # «удалено владельцем» снимается осознанной настройкой).
        try:
            chosen = {k: v for k, v in (settings.get('channels') or {}).items()
                      if str(v or '').strip()}
            if chosen:
                from services import log_settings as _LS
                for cat in chosen:
                    _LS.autocreate_forget(guild_id, cat)
        except Exception as _ex:
            _log.debug('log-settings: autocreate_forget подавлено: %s', _ex)
        return jsonify({'success': True, 'settings': settings})
