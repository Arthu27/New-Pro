# -*- coding: utf-8 -*-
"""Наказания из карточки участника («Пользователи») — как в /modpanel.

POST /api/guild/<gid>/punish — выдать наказание (варн, муты, бан-апелляция,
снятия). Исполняет тот же код, что и /modpanel: длительности «60, 1ч, 3ч, 1д»,
«бан» не выкидывает с сервера (изоляция + канал апелляции), без настроенного
канала — «настройки не завершены». Доказательство панель не спрашивает:
форма упрощена, поле убрано.

GET /api/guild/<gid>/punish/options — что доступно именно ЭТОМУ
пользователю панели: список действий отфильтрован по ACL «Права команд»
(services/permission_acl): если владелец ограничил действие конкретным
Discord-ролям, то входящему через Discord-аккаунт модератору без этих ролей
действие не показывается и на POST не принимается (403). Статический вход
из .env и роль owner — доверенные: им доступен весь набор. Плюс состояние
готовности «бана» (канал апелляции) и «бот онлайн».
"""
from services import staff_hierarchy as SH
from web.routes._common import (
    _safe_json_obj,
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

# Привязка действий панели к ACL «Права команд» (services/permission_acl.ACTIONS):
# действие доступно роли, только если владелец ЯВНО разрешил его в панели.
# Строгая модель (default-deny, Discord-права игнорируются) — 1:1 с ботом.
# Чат-мут и войс-мут — РАЗНЫЕ разрешения.
_ACTION_ACL = {
    'warn': 'warn',
    'unwarn': 'unwarn',
    'timeout': 'timeout',
    'mute_chat': 'mute',
    'vmute': 'vmute',
    'ban': 'ban',
    'unban': 'ban',
    'untimeout': 'timeout',
    'vunmute': 'vmute',
}

# Действие панели → ключ счётчика «Лимитов команды» (services/staff_limits):
# таймаут/чат-мут/войс-мут — ОДИН потолок «mute»; их снятия — «unmute»;
# бан и разбан — отдельные ключи (та же раскладка, что в cogs/moderation).
_PANEL_LIMIT_KEY = {
    'unwarn': 'unwarn',
    'warn': 'warn',
    'timeout': 'mute',
    'mute_chat': 'mute',
    'vmute': 'mute',
    'untimeout': 'unmute',
    'vunmute': 'unmute',
    'ban': 'ban',
    'unban': 'unban',
}

# Действия с длительностью — им проверяем ещё и «потолок мута» (Щит → Лимиты).
_DURATION_ACTIONS = ('timeout', 'mute_chat', 'vmute')


def _member_role_ids(member):
    """ID Discord-ролей модератора (без @everyone) — как в staff_limits.check_action."""
    if member is None:
        return []
    try:
        gid = getattr(member.guild, 'id', None)
        return [r.id for r in (getattr(member, 'roles', None) or [])
                if getattr(r, 'id', None) != gid]
    except Exception:
        return []


def _limit_exempt(guild, member):
    """True — лимиты не считаем: владелец сервера/бота не ограничен никогда.

    Статический вход и роль owner панели сюда не доходят: viewer_member()
    для них уже вернул None (доверенный вход).
    """
    if member is None:
        return True
    try:
        from config import Config as _Cfg
        if int(getattr(member, 'id', 0) or 0) in _Cfg.all_owner_ids():
            return True
    except Exception as _ex:
        _log.debug('limit_exempt: владелец бота не проверен: %s', _ex)
    try:
        if int(getattr(member, 'id', 0) or 0) == int(getattr(guild, 'owner_id', 0) or 0):
            return True
    except Exception as _ex:
        _log.debug('limit_exempt: владелец сервера не проверен: %s', _ex)
    return False


def _punish_cog(bot):
    return bot.get_cog('Moderation') if bot else None


def _viewer_member(bot, gid):
    """Discord-мембер, под которым вошли в панель (session['discord_id']).

    Единая реализация — web/routes/_common.viewer_member: та же логика
    используется планировщиком, лестницей и «Пользователями», чтобы нигде
    не было двух разных проверок.
    """
    from web.routes._common import viewer_member
    return viewer_member(bot, gid)


def _acl_allows(gid, member, action):
    """True, если действие не отрезано ACL «Права команд» для этого мембера."""
    key = _ACTION_ACL.get(action)
    if not key:
        return True
    from web.routes._common import acl_action_allowed
    return acl_action_allowed(gid, member, key)


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
        # ACL «Права команд»: каждому — только его действия.
        member = _viewer_member(bot, gid)
        actions_acl = [a for a in PANEL_ACTIONS if _acl_allows(gid, member, a[0])]
        hidden_by_acl = len(PANEL_ACTIONS) - len(actions_acl)
        # «Лимиты команды» (Щит сервера → Лимиты) для входа через
        # Discord-аккаунт: сколько у модератора осталось по каждому действию
        # и какие действия ему доступны (если для его ролей заданы свои
        # лимиты — видит только их, как в меню /modpanel).
        actions = actions_acl
        limits = {}
        limit_exempt = True
        if member is not None and bot is not None:
            try:
                guild = bot.get_guild(int(gid))
                if guild is not None and not _limit_exempt(guild, member):
                    from services import staff_limits as _SL
                    role_ids = _member_role_ids(member)
                    scope = _SL.role_scoped_actions(gid, role_ids)
                    if scope is not None:
                        actions = [a for a in actions_acl
                                   if _PANEL_LIMIT_KEY.get(a[0]) in scope]
                    windows = _SL.get_windows(gid)
                    for a in actions:
                        key = _PANEL_LIMIT_KEY.get(a[0])
                        if not key:
                            continue
                        _ok, used, lim = _SL.check_limit(
                            int(gid), member.id, key, 1, role_ids=role_ids)
                        if lim > 0:
                            limits[a[0]] = {
                                'limit': lim,
                                'used': used,
                                'left': max(0, lim - used),
                                'window': _SL.human_window(windows.get(key, 86400)),
                            }
                    limit_exempt = False
            except Exception as _lex:
                _log.debug('punish/options limits: %s', _lex)
        return jsonify({
            'success': True,
            'bot_online': bot is not None,
            'proof_required': proof_required,
            'ban_ready': ban_ready,
            # сколько действий скрыто правами ролей — для подсказки в форме
            'hidden_by_acl': hidden_by_acl,
            # счётные лимиты текущего модератора (если вход не доверенный)
            'limit_exempt': limit_exempt,
            'limits': limits,
            'actions': [
                {'value': v, 'label': lbl, 'duration': dur, 'proof': prf}
                for v, lbl, dur, prf in actions
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
        d = _safe_json_obj()
        action = str(d.get('action') or '').strip()
        if action not in _VALUE_SET:
            return jsonify({'success': False, 'error': 'Неизвестное действие'}), 400
        guild = bot.get_guild(int(gid))
        if guild is None:
            return jsonify({'success': False, 'error': 'Сервер не найден'}), 404

        # ACL «Права команд» — то же правило, что в options: действие,
        # отрезанное ролям этого модератора, не выполняем, даже если
        # обошли форму и шлют запрос напрямую.
        member_viewer = _viewer_member(bot, gid)
        if not _acl_allows(gid, member_viewer, action):
            return jsonify({'success': False,
                            'error': 'Нет права: действие не разрешено вашей '
                                     'роли (настройка — «Права команд»)'}), 403

        raw_uid = str(d.get('user_id') or '').strip().strip('<@!>')
        if not raw_uid.isdigit():
            return jsonify({'success': False,
                            'error': 'ID участника — число'}), 400
        member = guild.get_member(int(raw_uid))
        target = member if member is not None else raw_uid
        # ИЕРАРХИЯ ПЕРСОНАЛА (владелец 2026-09-05: «модер наказывает модера
        # и куратора — беспредел»): персонал не наказывает персонал своего
        # уровня и выше; владелец бота/сервера — вне юрисдикции.
        _h_ok, _h_deny, _a_role, _t_role = SH.check(
            guild, member_viewer, member, action,
            session_role=session.get('role'))
        if not _h_ok:
            return jsonify({'success': False, 'error': _h_deny}), 403

        reason = str(d.get('reason') or '').strip()[:500]
        duration = str(d.get('duration') or '').strip()[:40] or None
        proof = str(d.get('proof') or '').strip()[:500] or None
        actor = str(session.get('username') or 'Панель')

        # «Лимиты команды» (Щит сервера → Лимиты) применяются и в карточке
        # участника: модератор, вошедший через Discord-аккаунт, НЕ может
        # выдавать наказания бесконечно — для него действуют те же счётные
        # лимиты и потолок длительности мута, что и в командах бота.
        # Доверенный вход (владелец панели / статический логин) не режется.
        lim_key = _PANEL_LIMIT_KEY.get(action)
        quota_actor = None
        if lim_key and member_viewer is not None:
            try:
                if not _limit_exempt(guild, member_viewer):
                    quota_actor = member_viewer
            except Exception as _qex:
                _log.debug('punish quota actor: %s', _qex)
        if quota_actor is not None:
            try:
                from services import staff_limits as _SL
                role_ids = _member_role_ids(quota_actor)
                _okl, _deny = _SL.check_action(guild, quota_actor, lim_key)
                if not _okl:
                    return jsonify({'success': False,
                                    'error': _deny or 'Лимит исчерпан'}), 429
                # потолок длительности мута (0/не задан — без ограничения)
                if action in _DURATION_ACTIONS:
                    _cap = _SL.effective_max_duration(guild.id, 'mute', role_ids)
                    if _cap:
                        from cogs.moderation import parse_duration_minutes as _pd
                        from cogs.moderation import human_duration as _hd
                        _mins = _pd(duration, 5)
                        if _mins * 60 > _cap:
                            return jsonify({'success': False, 'error': (
                                'Мут дольше разрешённого: потолок для вашей '
                                f'роли — {_hd(max(1, _cap // 60))}, а вы просите '
                                f'{_hd(_mins)}. Потолок настраивается: панель → '
                                'Щит сервера → Лимиты.')}), 429
            except Exception as _slx:
                _log.debug('punish quota gate: %s', _slx)

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
        # успешное действие — в счётчик модератора (если лимиты для него есть)
        if ok and quota_actor is not None:
            try:
                from services import staff_limits as _SL2
                _SL2.record_hit(guild.id, quota_actor.id, lim_key, 1)
            except Exception as _rex:
                _log.debug('punish record_hit: %s', _rex)
        try:
            _fire_panel_notification(
                'mod_action' if ok else 'mod_action_failed',
                f"Наказание из панели: {action}",
                f"{actor} → {raw_uid} · {text[:200]}")
        except Exception as _ex:
            _log.debug("punish/options: подавлено: {_ex}", _ex)
            pass
        return jsonify({'success': bool(ok), 'message' if ok else 'error': text})
