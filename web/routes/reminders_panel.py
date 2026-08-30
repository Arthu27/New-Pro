# -*- coding: utf-8 -*-
"""Журнал напоминаний в панели (идея: активные таймеры, кто создал, отмена).

Читает то же хранилище GuildData('reminders'), что и ког /напомни.
Отмена — через чистую cancel_any кога (модераторская), возврат — restore_item:
undo в панели честное, не «пересоздание по памяти», а откат флага done.

Чтение — mod+, отмена — admin+ (чужие напоминания трогает только старший).
"""

from datetime import datetime, timezone

from web.routes._common import (
    _log,
    render_template, session, request, jsonify,
)

from db import GuildData
from cogs import reminders as R

UTC = timezone.utc


def _resolve_name(bot, gid, uid, stored):
    """Имя: то, что записано при создании; иначе кэш бота; иначе ID."""
    if stored:
        return stored
    if bot is not None:
        try:
            g = bot.get_guild(int(gid))
            m = g.get_member(int(uid)) if g else None
            if m is not None:
                return str(m.display_name)
        except Exception as _ex:
            _log.debug("_resolve_name(): кэш недоступен: %s", _ex)
    return f'ID {uid}'


def reminders_payload(gid, bot=None, now=None):
    """Все активные напоминания сервера для журнала (ближайшие первыми)."""
    now = now or datetime.now(UTC)
    state = GuildData('reminders').get(gid, 'state', R.empty_state())
    items = []
    overdue = 0
    for it in state.get('items', []):
        if it.get('done'):
            continue
        due = R._parse_iso(it.get('due_at'))
        is_overdue = bool(due and due <= now)
        overdue += int(is_overdue)
        items.append({
            'id': it.get('id'),
            'user_id': str(it.get('user_id', '')),
            'user_name': _resolve_name(bot, gid, it.get('user_id'), it.get('user_name')),
            'text': str(it.get('text', '')),
            'due_at': due.isoformat() if due else str(it.get('due_at', '')),
            'created_at': str(it.get('created_at', '')),
            'repeat_seconds': it.get('repeat_seconds'),
            'overdue': is_overdue,
        })
    items.sort(key=lambda x: x['due_at'] or '')
    return {
        'success': True,
        'items': items,
        'total': len(items),
        'overdue': overdue,
        'repeating': sum(1 for i in items if i['repeat_seconds']),
    }


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/reminders')
    @login_required
    @role_required('mod')
    def reminders_page():
        return render_template('reminders.html', role=session.get('role'),
                               username=session.get('username'))

    @app.route('/api/reminders/state')
    @login_required
    @role_required('mod')
    def api_reminders_state():
        import web.app as _app
        return jsonify(reminders_payload(ctx.active_guild_id(), bot=_app.bot_instance))

    @app.route('/api/reminders/cancel', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_reminders_cancel():
        """Отменить активное напоминание (чистая cancel_any кога)."""
        _gid = ctx.active_guild_id_int()
        if _gid is None:
            return jsonify({'success': False, 'error': 'Сервер не выбран (задайте MAIN_GUILD_ID в .env или дождитесь подключения бота)'}), 503
        data = request.get_json(silent=True) or {}
        try:
            item_id = int(data.get('id'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'id — число из журнала'}), 400
        gid = _gid
        db = GuildData('reminders')
        state = db.get(gid, 'state', R.empty_state())
        if not R.cancel_any(state, item_id):
            return jsonify({'success': False,
                            'error': f'напоминание №{item_id} не найдено или уже снято'}), 404
        db.set(gid, 'state', state)
        import web.app as _app
        body = reminders_payload(gid, bot=_app.bot_instance)
        body['cancelled_id'] = item_id
        return jsonify(body)

    @app.route('/api/reminders/restore', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_reminders_restore():
        """Undo отмены: честный откат флага done (restore_item кога)."""
        _gid = ctx.active_guild_id_int()
        if _gid is None:
            return jsonify({'success': False, 'error': 'Сервер не выбран (задайте MAIN_GUILD_ID в .env или дождитесь подключения бота)'}), 503
        data = request.get_json(silent=True) or {}
        try:
            item_id = int(data.get('id'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'id — число из журнала'}), 400
        gid = _gid
        db = GuildData('reminders')
        state = db.get(gid, 'state', R.empty_state())
        if not R.restore_item(state, item_id):
            return jsonify({'success': False,
                            'error': f'напоминание №{item_id} не отменено — возвращать нечего'}), 404
        db.set(gid, 'state', state)
        import web.app as _app
        return jsonify(reminders_payload(gid, bot=_app.bot_instance))
