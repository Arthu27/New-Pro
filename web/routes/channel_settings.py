# -*- coding: utf-8 -*-
"""Каналы и маршруты: единая страница настройки «куда бот что пишет».

Маршруты (см. ROUTE_SPECS в services/channel_routes.py):
  • proof_channel     — канал доказательств (native: data/channel_routes.json,
                        бот читает через cogs/proof_cog._proof_channel);
  • appeals_channel   — карточки апелляций (GuildData('appeals').state);
  • welcome_channel   — приветствия PRO (GuildData('welcome_pro').settings);
  • tagjail_channel   — лог Tag Jail (data/tag_jail.json cfg).

Просмотр — mod+ (чтобы у команды не было вопросов «почему улетело туда»),
изменение — admin+ (остальные просто видят, как настроено).
"""
from web.routes._common import (
    _log, _fire_panel_notification,
    render_template, session, request, jsonify,
    os, json,
)

from db import GuildData
from services import channel_routes as CHR

TAGJAIL_CFG = 'data/tag_jail.json'


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


def _tagjail_load():
    try:
        with open(TAGJAIL_CFG, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _tagjail_get(gid):
    return int((_tagjail_load().get(str(gid)) or {}).get('log_channel_id') or 0)


def _tagjail_set(gid, cid):
    data = _tagjail_load()
    row = data.setdefault(str(gid), {})
    row['log_channel_id'] = int(cid)
    os.makedirs(os.path.dirname(TAGJAIL_CFG), exist_ok=True)
    tmp = TAGJAIL_CFG + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, TAGJAIL_CFG)
    return True


ADAPTERS = {
    'proof_channel': (CHR.get_route, CHR.set_route),
    'appeals_channel': (_appeals_get, _appeals_set),
    'welcome_channel': (_welcome_get, _welcome_set),
    'tagjail_channel': (_tagjail_get, _tagjail_set),
}


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/channel-settings')
    @login_required
    @role_required('mod')
    def channel_settings_page():
        return render_template('channel_settings.html',
                               role=session.get('role'),
                               username=session.get('username'))

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
        return jsonify({'success': True, 'key': key, 'channel_id': cid})
