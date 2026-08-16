# -*- coding: utf-8 -*-
"""Панель «Апелляции» (идеи #116-120): очередь, разбор, история, канал.

Хранилище одно на двоих с ботом: GuildData('appeals'), ключ 'state',
пишет cogs/appeals.py. Все решения — его чистые функции:
create_appeal/resolve_appeal (и его же тексты ошибок), pending_items,
fmt_card_text (строчка карточки в очереди — как в /апелляции список).

Разбор из панели повторяет кнопку кога: сначала запись решения в state,
потом побочка при живом боте — разбан (NotFound = уже разбанен руками,
тоже успех) и ЛС тем самым методом Appeals._notify_user через цикл бота.
Бот офлайн — решение честно фиксируется, побочка подписана как не сделанная.

Чтение и выгрузка — mod+, решения и канал — admin+ (у кнопки в Discord
проверка «Управление сервером» — админский уровень).
"""
from datetime import datetime, timezone

from web.routes._common import (
    _log, _run_async,
    render_template, session, request, jsonify, Response,
    discord,
)

from cogs import appeals as AP

from db import GuildData

UTC = timezone.utc

HISTORY_LIMIT = 25
STATUS_LABELS = {'pending': 'ожидает', 'accepted': 'принята', 'rejected': 'отклонена'}


def _db():
    return GuildData('appeals')


def _state(gid):
    return _db().get(gid, 'state', AP.empty_state()) or AP.empty_state()


def _save(gid, state):
    _db().set(gid, 'state', state)


# ─────────────────────────────────────────────────────────────────────
# #116: очередь и сводка
# ─────────────────────────────────────────────────────────────────────
def overview_stats(state):
    """Счётчики очереди + последнее решение (кто и когда)."""
    items = (state or {}).get('items', [])
    by = {'pending': 0, 'accepted': 0, 'rejected': 0}
    for item in items:
        if item.get('status') in by:
            by[item['status']] += 1
    resolved = [i for i in items if i.get('reviewed_at')]
    resolved.sort(key=lambda i: str(i['reviewed_at']))
    last = None
    if resolved:
        it = resolved[-1]
        last = {'id': it.get('id'), 'status': it.get('status'),
                'status_label': STATUS_LABELS.get(it.get('status'), '?'),
                'reviewed_by': str(it.get('reviewed_by') or ''),
                'reviewed_at': str(it.get('reviewed_at') or '')[:16].replace('T', ' ')}
    return {'total': len(items), **by, 'last_resolved': last}


def pending_view(state):
    """Ожидающие, как в /апелляции список: порядок подачи + текст карточки."""
    rows = []
    for item in AP.pending_items(state or {'items': []}):
        rows.append({
            'id': item.get('id'),
            'user_id': str(item.get('user_id') or ''),
            'user_name': str(item.get('user_name') or ''),
            'text': str(item.get('text') or ''),
            'created_at': str(item.get('created_at') or '')[:16].replace('T', ' '),
            'card_text': AP.fmt_card_text(item),
        })
    return rows


def channel_readiness(bot, gid, state):
    """Куда упадёт карточка: свой канал или системный — логика _log_channel кога."""
    cid = int(state.get('log_channel_id') or 0)
    ready = {'log_channel_id': cid, 'channel_name': '', 'falls_to': ''}
    guild = None
    if bot:
        try:
            guild = bot.get_guild(int(gid))
        except Exception as _ex:
            _log.debug('appeals: guild %s: %s', gid, _ex)
    if guild is not None:
        own = guild.get_channel(cid) if cid else None
        target = own or getattr(guild, 'system_channel', None)
        if target is not None:
            ready['channel_name'] = str(getattr(target, 'name', ''))
            ready['falls_to'] = 'own' if own is not None else 'system'
    return ready


# ─────────────────────────────────────────────────────────────────────
# #117: разбор — state + побочка кнопки кога
# ─────────────────────────────────────────────────────────────────────
def _unban(guild, user_id, appeal_id):
    """Разбан семантикой кнопки: NotFound (уже разбанен руками) — тоже успех."""
    async def _do():
        try:
            await guild.unban(discord.Object(id=int(user_id)),
                              reason=f'Апелляция #{appeal_id} принята')
            return True
        except discord.NotFound:
            return True
        except (discord.Forbidden, discord.HTTPException) as _ex:
            _log.error('appeals: unban %s не удался: %s', user_id, _ex)
            return False
    try:
        return bool(_run_async(_do(), timeout=15))
    except Exception as _ex:
        _log.debug('appeals: цикл бота на разбане: %s', _ex)
        return False


def _notify_user(bot, item, accept, unbanned):
    """ЛС решением — тот самый метод кога, через его цикл."""
    try:
        cog = bot.get_cog('Appeals')
    except Exception as _ex:
        _log.debug('appeals: get_cog: %s', _ex)
        cog = None
    if cog is None:
        return False
    try:
        _run_async(cog._notify_user(item, accept, unbanned), timeout=10)
        return True
    except Exception as _ex:
        _log.debug('appeals: ЛС решением: %s', _ex)
        return False


def apply_side_effects(bot, gid, item, accept):
    """Разбан (только при принятии) + ЛС — как в AppealView._resolve."""
    if not bot:
        return {'offline': True, 'unbanned': None, 'dm_attempted': False}
    unbanned = None
    if accept:
        guild = None
        try:
            guild = bot.get_guild(int(gid))
        except Exception as _ex:
            _log.debug('appeals: guild на разбане: %s', _ex)
        if guild is not None:
            unbanned = _unban(guild, item['user_id'], item['id'])
    dm = _notify_user(bot, item, accept, bool(unbanned))
    return {'offline': False, 'unbanned': unbanned, 'dm_attempted': dm}


def resolve_panel(bot, gid, appeal_id, accept, reviewer, reply=None, now=None):
    """Решение по апелляции. (ok, err, http_code, payload)."""
    state = _state(gid)
    item, err = AP.resolve_appeal(state, int(appeal_id), bool(accept), reviewer,
                                  now or datetime.now(UTC), reply=reply)
    if err:
        return False, err, (404 if 'не найдена' in err else 409), None
    _save(gid, state)
    effects = apply_side_effects(bot, gid, item, bool(accept))
    status_text = ('принята (разбанен)' if (accept and effects.get('unbanned'))
                   else ('принята' if accept else 'отклонена'))
    return True, '', 200, {'item': item, 'effects': effects,
                           'status_text': status_text}


# ─────────────────────────────────────────────────────────────────────
# #118: история решений
# ─────────────────────────────────────────────────────────────────────
def history_view(state, status=None, query=None, limit=HISTORY_LIMIT):
    """Журнал апелляций: свежие сверху, фильтры по статусу и строке."""
    items = list((state or {}).get('items', []))
    if status in STATUS_LABELS:
        items = [i for i in items if i.get('status') == status]
    q = str(query or '').strip().lower()
    if q:
        items = [i for i in items
                 if q in str(i.get('user_name') or '').lower()
                 or q in str(i.get('text') or '').lower()
                 or q in str(i.get('reply') or '').lower()
                 or q in str(i.get('user_id') or '')]
    items.sort(key=lambda i: str(i.get('created_at') or ''), reverse=True)
    out = []
    for item in items[:limit]:
        out.append({
            'id': item.get('id'),
            'user_id': str(item.get('user_id') or ''),
            'user_name': str(item.get('user_name') or ''),
            'text': str(item.get('text') or ''),
            'status': item.get('status'),
            'status_label': STATUS_LABELS.get(item.get('status'), '?'),
            'created_at': str(item.get('created_at') or '')[:16].replace('T', ' '),
            'reviewed_by': str(item.get('reviewed_by') or ''),
            'reviewed_at': str(item.get('reviewed_at') or '')[:16].replace('T', ' '),
            'reply': str(item.get('reply') or ''),
        })
    return out


# ─────────────────────────────────────────────────────────────────────
# #119: канал карточек
# ─────────────────────────────────────────────────────────────────────
def set_log_channel(state, channel_id):
    """Целочисленный ID канала, как сохраняет /апелляции канал."""
    try:
        cid = int(str(channel_id or '').strip())
    except (TypeError, ValueError):
        return False, 'Некорректный ID канала', 0
    if cid < 0:
        return False, 'Некорректный ID канала', 0
    state['log_channel_id'] = cid
    return True, '', cid


# ─────────────────────────────────────────────────────────────────────
# #120: выгрузка
# ─────────────────────────────────────────────────────────────────────
def appeals_csv_rows(state):
    """Весь журнал — человекочитаемые статусы, решения с деталями."""
    rows = []
    for item in (state or {}).get('items', []):
        rows.append((
            str(item.get('id')),
            str(item.get('user_id') or ''),
            str(item.get('user_name') or ''),
            STATUS_LABELS.get(item.get('status'), str(item.get('status') or '')),
            str(item.get('created_at') or '')[:16].replace('T', ' '),
            str(item.get('reviewed_by') or ''),
            str(item.get('reviewed_at') or '')[:16].replace('T', ' '),
            str(item.get('reply') or ''),
            str(item.get('text') or ''),
        ))
    return rows


CSV_HEADER = 'id;user_id;user_name;status;created_at;reviewed_by;reviewed_at;reply;text'


def _csv_cell(text):
    return str(text).replace(';', ',').replace('\r', ' ').replace('\n', ' ')


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _notify(title):
        from web.routes._common import _fire_panel_notification
        try:
            _fire_panel_notification(
                'mod_action', title,
                f'Через панель ({session.get("username", "?")})')
        except Exception as _ex:
            _log.debug('appeals: уведомление не ушло: %s', _ex)

    @app.route('/appeals')
    @login_required
    @role_required('mod')
    def appeals_page():
        return render_template('appeals.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id(),
                               can_edit=session.get('role') in ('admin', 'owner'))

    @app.route('/api/guild/<gid>/appeals/overview')
    @login_required
    @role_required('mod')
    def api_appeals_overview(gid):
        import web.app as appmod
        state = _state(gid)
        return jsonify({
            'success': True,
            'stats': overview_stats(state),
            'pending': pending_view(state),
            'readiness': channel_readiness(appmod.bot_instance, gid, state),
            'can_edit': session.get('role') in ('admin', 'owner'),
        })

    @app.route('/api/guild/<gid>/appeals/history')
    @login_required
    @role_required('mod')
    def api_appeals_history(gid):
        return jsonify({'success': True,
                        'items': history_view(_state(gid),
                                              status=request.args.get('status'),
                                              query=request.args.get('q'))})

    @app.route('/api/guild/<gid>/appeals/resolve', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_appeals_resolve(gid):
        import web.app as appmod
        data = request.get_json(silent=True) or {}
        raw_id = str(data.get('appeal_id') or '').strip()
        if not raw_id.isdigit():
            return jsonify({'success': False,
                            'error': 'Некорректный номер апелляции'}), 400
        accept = data.get('accept')
        if accept not in (True, False):
            return jsonify({'success': False,
                            'error': 'Решение должно быть true или false'}), 400
        ok, err, code, payload = resolve_panel(
            appmod.bot_instance, gid, int(raw_id), accept,
            session.get('username', '?'), reply=data.get('reply'))
        if not ok:
            return jsonify({'success': False, 'error': err}), code
        payload['success'] = True
        _notify(f'Апелляция #{raw_id}: {payload["status_text"]}')
        return jsonify(payload)

    @app.route('/api/guild/<gid>/appeals/channel', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_appeals_channel(gid):
        import web.app as appmod
        data = request.get_json(silent=True) or {}
        state = _state(gid)
        ok, err, cid = set_log_channel(state, data.get('channel_id'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        bot = appmod.bot_instance
        if bot:
            guild = None
            try:
                guild = bot.get_guild(int(gid))
            except Exception as _ex:
                _log.debug('appeals: guild на смене канала: %s', _ex)
            channel = guild.get_channel(cid) if (guild and cid) else None
            if channel is None or not hasattr(channel, 'history'):
                return jsonify({'success': False,
                                'error': 'Текстовый канал не найден'}), 404
            _save(gid, state)
            _notify(f'Апелляции идут в #{channel.name}')
            return jsonify({'success': True,
                            'message': f'Апелляции идут в #{channel.name}.'})
        _save(gid, state)
        return jsonify({'success': True,
                        'message': 'Канал сохранён — бот офлайн, проверка при его старте'})

    @app.route('/api/guild/<gid>/appeals/export.csv')
    @login_required
    @role_required('mod')
    def api_appeals_export(gid):
        rows = appeals_csv_rows(_state(gid))
        body = '\ufeff' + CSV_HEADER + '\n'
        body += '\n'.join(';'.join(_csv_cell(c) for c in row) for row in rows) + '\n'
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=appeals_{gid}.csv')
        return resp
