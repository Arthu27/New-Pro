# -*- coding: utf-8 -*-
"""Комната счёта в панели (идея #3): текущее число, рекорд, падения, канал.

Читает/пишет то же хранилище GuildData('counting'), что и ког /счёт.
Строки статуса — прямо из status_lines кога (1:1 с «/счёт статус»).
Включение канала дублирует поведение «/счёт канал» (свежий стейт),
выключение — «/счёт выкл» (рекорд сохраняется).

Чтение — mod+, включение/выключение — admin+ (manage_guild у кога).
"""

from datetime import datetime, timezone

from web.routes._common import (
    _log,
    render_template, session, request, jsonify,
)

from db import GuildData
from cogs import counting as C

UTC = timezone.utc


def _channel(bot, gid, channel_id):
    """Канал из кэша бота (объект) или None."""
    if bot is None or not channel_id:
        return None
    try:
        g = bot.get_guild(int(gid))
        return g.get_channel(int(channel_id)) if g else None
    except Exception as _ex:
        _log.debug("_channel(): кэш недоступен: %s", _ex)
        return None


def counting_payload(gid, bot=None):
    """Единая картина считалки для панели: и GET, и ответы мутаций."""
    state = GuildData('counting').get(gid, 'state', C.empty_state()) or C.empty_state()
    ch = _channel(bot, gid, state.get('channel_id'))
    nxt = int(state.get('next', 1) or 1)
    return {
        'success': True,
        'active': bool(state.get('channel_id')),
        'channel_id': str(state.get('channel_id') or ''),
        'channel_name': str(getattr(ch, 'name', '') or ''),
        'current': max(0, nxt - 1),
        'next': nxt,
        'best': int(state.get('best', 0) or 0),
        'fails': int(state.get('fails', 0) or 0),
        'last_user_name': str(state.get('last_user_name') or ''),
        'fail_reason': str(state.get('fail_reason') or ''),
        'fail_expected': state.get('fail_expected'),
        'fail_got': state.get('fail_got'),
        'updated_at': str(state.get('updated_at') or ''),
        # те самые строки, что показывает «/счёт статус» в Discord
        'status_lines': C.status_lines(state),
    }


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/counting')
    @login_required
    @role_required('mod')
    def counting_page():
        return render_template('counting.html', role=session.get('role'),
                               username=session.get('username'))

    @app.route('/api/counting/state')
    @login_required
    @role_required('mod')
    def api_counting_state():
        import web.app as _app
        return jsonify(counting_payload(ctx.active_guild_id(), bot=_app.bot_instance))

    @app.route('/api/counting/channel', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_counting_channel():
        """Включить считалку в канале — зеркало «/счёт канал» (свежий стейт)."""
        _gid = ctx.active_guild_id_int()
        if _gid is None:
            return jsonify({'success': False, 'error': 'Сервер не выбран (задайте MAIN_GUILD_ID в .env или дождитесь подключения бота)'}), 503
        import web.app as _app
        bot = _app.bot_instance
        if bot is None:
            return jsonify({'success': False,
                            'error': 'Бот офлайн — канал проверить не могу'}), 503
        data = request.get_json(silent=True) or {}
        gid = _gid
        try:
            ch_id = int(data.get('channel_id'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'channel_id — число'}), 400
        ch = _channel(bot, gid, ch_id)
        if ch is None or not hasattr(ch, 'name'):
            return jsonify({'success': False,
                            'error': f'в кэше нет текстового канала {ch_id}'}), 404
        state = C.empty_state(ch_id)
        state['updated_at'] = datetime.now(UTC).isoformat()
        GuildData('counting').set(gid, 'state', state)
        return jsonify(counting_payload(gid, bot=bot))

    @app.route('/api/counting/off', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_counting_off():
        """Выключить — зеркало «/счёт выкл» (рекорд и статистика сохраняются)."""
        _gid = ctx.active_guild_id_int()
        if _gid is None:
            return jsonify({'success': False, 'error': 'Сервер не выбран (задайте MAIN_GUILD_ID в .env или дождитесь подключения бота)'}), 503
        import web.app as _app
        gid = _gid
        db = GuildData('counting')
        state = db.get(gid, 'state', C.empty_state()) or C.empty_state()
        state['channel_id'] = 0
        db.set(gid, 'state', state)
        return jsonify(counting_payload(gid, bot=_app.bot_instance))
