# -*- coding: utf-8 -*-
"""Наказания из карточки участника («Пользователи») — как в /modpanel.

POST /api/guild/<gid>/punish — выдать наказание (варн, муты, бан-апелляция,
снятия). Исполняет тот же код, что и /modpanel: длительности «60, 1ч, 3ч, 1д»,
«бан» не выкидывает с сервера (изоляция + канал апелляции), без настроенного
канала — «настройки не завершены», доказательство — если в панели включено
требование.

GET /api/guild/<gid>/punish/options — что доступно сейчас: состояние
тумблера доказательств, готовность «бана» (канал апелляции), бот онлайн.
Доступ — mod+ (панель — доверенный вход, действия пишутся от «Панель: логин»).
"""
from web.routes._common import (
    _log, _run_async, _fire_panel_notification,
    render_template, session, request, jsonify,
    os, json,
)

# (value, label, нужна_длительность, нужно_доказательство_если_тумблер)
PANEL_ACTIONS = [
    ('warn', 'Варн', False, False),
    ('timeout', 'Мут (чат + войс)', True, True),
    ('mute_chat', 'Мут чата', True, True),
    ('vmute', 'Войс-мут', True, True),
    ('ban', 'Бан (апелляция)', False, True),
    ('unban', 'Снять апелляцию / разбан', False, False),
    ('untimeout', 'Снять мут', False, False),
    ('vunmute', 'Снять войс-мут', False, False),
]
_VALUE_SET = {a[0] for a in PANEL_ACTIONS}


def _punish_cog(bot):
    return bot.get_cog('Moderation') if bot else None


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/api/guild/<gid>/punish/options')
    @login_required
    @role_required('mod')
    def api_punish_options(gid):
        import web.app as _app
        bot = _app.bot_instance
        proof_required = False
        try:
            if bot is not None:
                from cogs.proof_cog import proof_is_required
                g = bot.get_guild(int(gid))
                if g is not None:
                    proof_required = bool(proof_is_required(g.id))
        except Exception as _ex:
            _log.debug('punish/options proof: %s', _ex)
        ban_ready = False
        try:
            from services.channel_routes import get_route
            ban_ready = int(get_route(gid, 'ban_appeal_channel') or 0) > 0
        except Exception as _ex:
            _log.debug('punish/options ban: %s', _ex)
        return jsonify({
            'success': True,
            'bot_online': bot is not None,
            'proof_required': proof_required,
            'ban_ready': ban_ready,
            'actions': [
                {'value': v, 'label': lbl, 'duration': dur, 'proof': prf}
                for v, lbl, dur, prf in PANEL_ACTIONS
            ],
        })

    @app.route('/api/guild/<gid>/punish', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_punish(gid):
        import web.app as _app
        bot = _app.bot_instance
        if bot is None:
            return jsonify({'success': False,
                            'error': 'Бот офлайн — наказание не выдать'}), 503
        cog = _punish_cog(bot)
        if cog is None:
            return jsonify({'success': False,
                            'error': 'Модуль модерации не загружен'}), 404
        d = request.get_json(silent=True) or {}
        action = str(d.get('action') or '').strip()
        if action not in _VALUE_SET:
            return jsonify({'success': False, 'error': 'Неизвестное действие'}), 400
        guild = bot.get_guild(int(gid))
        if guild is None:
            return jsonify({'success': False, 'error': 'Сервер не найден'}), 404

        raw_uid = str(d.get('user_id') or '').strip().strip('<@!>')
        if not raw_uid.isdigit():
            return jsonify({'success': False,
                            'error': 'ID участника — число'}), 400
        member = guild.get_member(int(raw_uid))
        target = member if member is not None else raw_uid
        if member is not None and getattr(member, 'bot', False):
            return jsonify({'success': False,
                            'error': 'Ботов наказывать нельзя'}), 400
        if member is not None and member.id == guild.owner_id:
            return jsonify({'success': False,
                            'error': 'Владельца сервера наказать нельзя'}), 400

        reason = str(d.get('reason') or '').strip()[:500]
        duration = str(d.get('duration') or '').strip()[:40] or None
        proof = str(d.get('proof') or '').strip()[:500] or None
        actor = str(session.get('username') or 'Панель')

        try:
            ok, text = _run_async(cog.apply_panel_action(
                guild, target, action, reason=reason,
                amount=duration, proof_link=proof, actor=actor))
        except Exception as _ex:
            _log.warning('punish: %s', _ex)
            return jsonify({'success': False,
                            'error': f'Не получилось: {_ex}'}), 200
        if not text:
            text = 'Готово' if ok else 'Не получилось'
        try:
            _fire_panel_notification(
                'mod_action' if ok else 'mod_action_failed',
                f"Наказание из панели: {action}",
                f"{actor} → {raw_uid} · {text[:200]}")
        except Exception as _ex:
            _log.debug("punish/options: подавлено: {_ex}", _ex)
            pass
        return jsonify({'success': bool(ok), 'message' if ok else 'error': text})
