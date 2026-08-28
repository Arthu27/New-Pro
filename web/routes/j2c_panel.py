# -*- coding: utf-8 -*-
"""Панель «Комнаты join-to-create» (идеи #76-80): статус системы, реестр
живых комнат, настройки лобби/категории/лимита/шаблона, уборка сирот.

Хранилище кога cogs/join_to_create.py:
    data/j2c.json        {gid: {enabled, lobby_id, category_id (0 — как у лобби),
                                user_limit (0 — безлимит), name_template}}
    data/j2c_rooms.json  {gid: {channel_id: owner_id}} — реестр переживает
                         рестарт, ког его подчищает в on_ready.
Ког держит конфиг и реестр В ПАМЯТИ: при живом боте панель работает через
экземпляр кога (set_cfg/_del_room пишут и память, и диск), при офлайне —
напрямую в файлы. Типы и рамки — как у команд /j2c (лимит 0..99, шаблон
[:96], 0 вместо отсутствующих ID).

Чтение и превью — mod+, настройки и уборка — admin+.
"""
import os

from web.routes._common import (
    _log,
    render_template, session, request, jsonify,
)

from web.routes.mod_control import names_from_audit

from cogs import join_to_create as JC

SAMPLE_USER = 'Мария'   # образец владельца для превью имени комнаты


def _cog(bot):
    """Живой экземпляр кога, если бот онлайн и ког загружен."""
    if not bot:
        return None
    try:
        return bot.get_cog('JoinToCreate')
    except Exception as _ex:
        _log.debug('j2c: get_cog: %s', _ex)
        return None


def read_cfg(bot, gid):
    """Конфиг гильдии: у живого кога — из памяти, иначе файл + DEFAULT_CFG.

    -> (cfg, live). Как cfg() кога: дефолты подмешаны к записи.
    """
    cog = _cog(bot)
    if cog is not None:
        try:
            return dict(cog.cfg(int(gid))), True
        except Exception as _ex:
            _log.debug('j2c: cfg кога недоступен: %s', _ex)
    data = JC._load(JC.CFG_PATH, {})
    rec = data.get(str(gid)) if isinstance(data, dict) else None
    cfg = dict(JC.DEFAULT_CFG)
    if isinstance(rec, dict):
        cfg.update(rec)
    return cfg, False


def read_rooms(bot, gid):
    """Реестр комнат {channel_id: owner_id}: живой ког или файл. -> (map, live)."""
    cog = _cog(bot)
    if cog is not None:
        try:
            return dict(cog._room_map(int(gid))), True
        except Exception as _ex:
            _log.debug('j2c: реестр кога недоступен: %s', _ex)
    data = JC._load(JC.ROOMS_PATH, {})
    rooms = data.get(str(gid)) if isinstance(data, dict) else None
    return (dict(rooms) if isinstance(rooms, dict) else {}), False


def _guild(bot, gid):
    try:
        return bot.get_guild(int(gid)) if bot else None
    except Exception as _ex:
        _log.debug('j2c: get_guild(%s): %s', gid, _ex)
        return None


def readiness(cfg, lobby_state, category_state):
    """Диагностика системы. lobby_state/category_state:
    True — канал на месте, False — потерян, None — бот офлайн.
    Потерянная категория не фатальна: ког создаст комнаты у лобби.
    """
    issues = []
    if not cfg.get('enabled'):
        issues.append('система выключена')
    if not cfg.get('lobby_id'):
        issues.append('лобби не задан (0)')
    if lobby_state is False:
        issues.append('лобби не найден у бота — задайте заново')
    if category_state is False:
        issues.append('категория потеряна — комнаты лягут к лобби')
    ready = (bool(cfg.get('enabled')) and bool(cfg.get('lobby_id'))
             and lobby_state is not False)
    return {'ready': ready, 'issues': issues}


def normalize_settings(payload):
    """Частичные правки -> (updates | None, err). Рамки команд /j2c:
    лимит 0..99 (Range у бота), шаблон [:96] и пустой -> дефолт кога,
    ID цифрами, 0/пусто — «нет».
    """
    updates = {}
    if 'enabled' in payload:
        enabled = payload.get('enabled')
        if not isinstance(enabled, bool):
            return None, 'Включение — true или false'
        updates['enabled'] = enabled
    for key, label, err in (('lobby_id', 'лобби', 'ID лобби — только цифры'),
                            ('category_id', 'категории',
                             'ID категории — только цифры')):
        if key in payload:
            value = str(payload.get(key) or '').strip()
            if value and not value.isdigit():
                return None, err
            updates[key] = int(value) if value else 0
    if 'user_limit' in payload:
        value = payload.get('user_limit')
        if isinstance(value, bool):
            return None, 'Лимит — целое число от 0 до 99'
        try:
            value = int(str(value).strip())
        except (TypeError, ValueError):
            return None, 'Лимит — целое число от 0 до 99'
        if not (0 <= value <= 99):
            return None, 'Лимит — целое число от 0 до 99'
        updates['user_limit'] = value
    if 'name_template' in payload:
        value = payload.get('name_template')
        value = ('' if value is None else str(value)).strip()
        # как /j2c template: срез [:96], пустой — дефолт кога
        updates['name_template'] = value[:96] or JC.DEFAULT_CFG['name_template']
    return updates, ''


def preview_name(cfg, sample_user=SAMPLE_USER):
    """Имя будущей комнаты — строчка _create_room кога 1:1:
    [:96] применяется к ШАБЛОНУ до подстановки {user}, поэтому длинное
    имя владельца может вывести за 96 — повторяем, не чиним."""
    template = str(cfg.get('name_template')
                   or JC.DEFAULT_CFG['name_template'])[:96]
    return template.replace('{user}', str(sample_user))


def room_rows(rooms_map, bot, gid, names=None):
    """Реестр с состояниями: True жив (у бота на месте), False — сирота,
    None — бот офлайн. Живые первыми, число людей — если бот онлайн."""
    names = names or {}
    guild = _guild(bot, gid)
    rows = []
    for cid, oid in (rooms_map or {}).items():
        live = None
        members = None
        if guild is not None:
            try:
                channel = guild.get_channel(int(cid))
                live = channel is not None
                if channel is not None:
                    members = len(getattr(channel, 'members', []) or [])
            except Exception as _ex:
                _log.debug('j2c: канал %s: %s', cid, _ex)
        rows.append({
            'channel_id': str(cid),
            'owner_id': str(oid),
            'owner_name': str(names.get(str(oid)) or ''),
            'live': live,
            'members': members,
        })
    rows.sort(key=lambda r: (r['live'] is not True, r['channel_id']))
    return rows


def apply_settings(bot, gid, updates):
    """Правки: живому боту — через set_cfg кога (память + диск),
    офлайну — прямая запись файла. Возвращает True, если писали в живого."""
    cog = _cog(bot)
    if cog is not None:
        for key, value in updates.items():
            cog.set_cfg(int(gid), key, value)
        return True
    data = JC._load(JC.CFG_PATH, {})
    if not isinstance(data, dict):
        data = {}
    rec = data.setdefault(str(gid), {})
    rec.update(updates)
    JC._save(JC.CFG_PATH, data)
    return False


def prune_orphans(bot, gid):
    """Убрать из реестра мёртвые комнаты (как reconcile кога, но без
    удаления живых пустых каналов — не наше дело). -> (removed | None):
    None — бот/сервер недоступен, чистить не по чему."""
    cog = _cog(bot)
    guild = _guild(bot, gid)
    if guild is None:
        return None
    rooms, _live = read_rooms(bot, gid)
    removed = 0
    for cid in list(rooms):
        try:
            missing = guild.get_channel(int(cid)) is None
        except Exception as _ex:
            _log.debug('j2c: prune канал %s: %s', cid, _ex)
            missing = False
        if not missing:
            continue
        if cog is not None:
            try:
                cog._del_room(int(gid), int(cid))
            except Exception as _ex:
                _log.debug('j2c: _del_room %s: %s', cid, _ex)
        else:
            data = JC._load(JC.ROOMS_PATH, {})
            if isinstance(data, dict) and isinstance(data.get(str(gid)), dict):
                if data[str(gid)].pop(str(cid), None) is not None:
                    JC._save(JC.ROOMS_PATH, data)
        removed += 1
    return removed


# ─────────────────────────────────────────────────────────────────────
# Маршруты
# ─────────────────────────────────────────────────────────────────────
def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _notify(title):
        from web.routes._common import _fire_panel_notification
        try:
            _fire_panel_notification(
                'j2c', title,
                f'Через панель ({session.get("username", "?")})')
        except Exception as _ex:
            _log.debug('j2c: уведомление не ушло: %s', _ex)

    @app.route('/join-to-create')
    @login_required
    @role_required('mod')
    def j2c_page():
        return render_template('j2c.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/j2c/overview')
    @login_required
    @role_required('mod')
    def api_j2c_overview(gid):
        import web.app as appmod
        bot = appmod.bot_instance
        cfg, live_cfg = read_cfg(bot, gid)
        guild = _guild(bot, gid)
        lobby_state = None
        if guild is not None and cfg.get('lobby_id'):
            try:
                lobby_state = guild.get_channel(int(cfg['lobby_id'])) is not None
            except Exception as _ex:
                _log.debug('j2c: лобби: %s', _ex)
        category_state = None
        if guild is not None and cfg.get('category_id'):
            try:
                category_state = guild.get_channel(
                    int(cfg['category_id'])) is not None
            except Exception as _ex:
                _log.debug('j2c: категория: %s', _ex)
        rooms, _ = read_rooms(bot, gid)
        rows = room_rows(rooms, bot, gid, names=names_from_audit(gid))
        return jsonify({
            'success': True,
            'config': cfg,
            'live': live_cfg,
            'bot_online': guild is not None,
            'readiness': readiness(cfg, lobby_state, category_state),
            'rooms': rows,
            'rooms_total': len(rows),
            'rooms_live': sum(1 for r in rows if r['live'] is True),
            'preview': preview_name(cfg),
            'can_edit': session.get('role') in ('admin', 'owner'),
        })

    @app.route('/api/guild/<gid>/j2c/settings', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_j2c_settings(gid):
        import web.app as appmod
        data = request.get_json(silent=True) or {}
        updates, err = normalize_settings(data)
        if updates is None:
            return jsonify({'success': False, 'error': err}), 400
        if not updates:
            return jsonify({'success': True, 'changed': 0})
        live = apply_settings(appmod.bot_instance, gid, updates)
        _notify('Комнаты J2C: настройки обновлены '
                f'({", ".join(sorted(updates))})')
        cfg, _ = read_cfg(appmod.bot_instance, gid)
        return jsonify({'success': True, 'changed': len(updates),
                        'live': live, 'config': cfg,
                        'preview': preview_name(cfg)})

    @app.route('/api/guild/<gid>/j2c/rooms/prune', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_j2c_prune(gid):
        import web.app as appmod
        removed = prune_orphans(appmod.bot_instance, gid)
        if removed is None:
            return jsonify({'success': False,
                            'error': 'Бот офлайн — сироты не проверить'}), 409
        if removed:
            _notify(f'Комнаты J2C: вычищено сирот — {removed}')
        return jsonify({'success': True, 'removed': removed})
