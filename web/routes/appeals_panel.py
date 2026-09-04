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

Поверх:
- «Контекст модератора» в очереди — наказания и прошлые апелляции юзера
  (services/appeal_context);
- «Правила подачи» (state['settings']): кулдаун после отказа, порог
  напоминаний о висящих, обязательный комментарий при отказе, шаблоны отказов;
- статус auto_closed (разбанили вручную в Discord) — история и CSV;
- все API-роуты замкнуты на active_guild_id() — панель живёт одним сервером
  (MAIN_GUILD_ID), gid из адресной строки не имеет значения.

Чтение и выгрузка — mod+, решения и канал — admin+ (у кнопки в Discord
проверка «Управление сервером» — админский уровень).
"""
from datetime import datetime, timezone

from web.routes._common import (
    _safe_json_obj,
    _log, _run_async,
    render_template, session, request, jsonify, Response,
    discord,
)

from cogs import appeals as AP
from services import appeal_card as ABC

from db import GuildData

UTC = timezone.utc

HISTORY_LIMIT = 25
STATUS_LABELS = {'pending': 'ожидает', 'accepted': 'принята', 'rejected': 'отклонена',
                 'auto_closed': 'закрыта (авто)'}


def _db():
    return GuildData('appeals')


def _state(gid):
    return _db().get(gid, 'state', AP.empty_state()) or AP.empty_state()


def _save(gid, state):
    _db().set(gid, 'state', state)


# ─────────────────────────────────────────────────────────────────────
# #116: очередь и сводка
# ─────────────────────────────────────────────────────────────────────
def overview_stats(state, now=None, stale_hours=None):
    """Счётчики очереди + висящие (ждут дольше stale_hours) + последнее решение."""
    items = (state or {}).get('items', [])
    by = {'pending': 0, 'accepted': 0, 'rejected': 0, 'auto_closed': 0}
    for item in items:
        if item.get('status') in by:
            by[item['status']] += 1
    try:
        from datetime import timedelta
        hours = stale_hours if stale_hours is not None \
            else AP.settings_of(state)['stale_hours']
        edge = (now or datetime.now(UTC)) - timedelta(hours=hours)
        stale = 0
        for item in AP.pending_items(state or {'items': []}):
            created = AP._parse_ts(item.get('created_at'))
            if created is not None and created <= edge:
                stale += 1
    except Exception as _ex:
        _log.debug('appeals: stale-stats: %s', _ex)
        stale = 0
    resolved = [i for i in items if i.get('reviewed_at')]
    resolved.sort(key=lambda i: str(i['reviewed_at']))
    last = None
    if resolved:
        it = resolved[-1]
        last = {'id': it.get('id'), 'status': it.get('status'),
                'status_label': STATUS_LABELS.get(it.get('status'), '?'),
                'reviewed_by': str(it.get('reviewed_by') or ''),
                'reviewed_at': str(it.get('reviewed_at') or '')[:16].replace('T', ' ')}
    up = down = 0
    for item in items:
        if item.get('rating') == 'up':
            up += 1
        elif item.get('rating') == 'down':
            down += 1
    total_votes = up + down
    # последние комментарии «почему так» — самая ценная обратная связь
    comments = []
    for item in items:
        cm = str(item.get('rating_comment') or '').strip()
        if cm:
            comments.append({'id': item.get('id'),
                             'rating': item.get('rating'),
                             'comment': cm[:300]})
    comments = comments[-3:][::-1]
    ratings = {'up': up, 'down': down,
               'pct': round(100 * up / total_votes) if total_votes else None,
               'comments': comments}
    return {'total': len(items), **by, 'stale': stale,
            'ratings': ratings, 'last_resolved': last}


def pending_view(state, gid=None):
    """Ожидающие, как в /апелляции список: порядок подачи + текст карточки.

    context — строка «наказания и прошлые апелляции юзера»
    (services/appeal_context); без gid не считаем (тесты без диска).
    """
    rows = []
    for item in AP.pending_items(state or {'items': []}):
        context = ''
        if gid is not None:
            try:
                from services.appeal_context import build_context
                context = build_context(state, gid, item.get('user_id'))['line']
            except Exception as _ex:
                _log.debug('appeals: контекст очереди: %s', _ex)
        claim = item.get('claimed_by') or None
        rows.append({
            'id': item.get('id'),
            'user_id': str(item.get('user_id') or ''),
            'user_name': str(item.get('user_name') or ''),
            'text': str(item.get('text') or ''),
            'created_at': str(item.get('created_at') or '')[:16].replace('T', ' '),
            'link': str(item.get('link') or ''),
            'context': context,
            'card_text': AP.fmt_card_text(item),
            'claimed_by': (str(claim.get('name') or '') if claim else ''),
            'escalated': bool(item.get('escalated_at')),
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


def _notify_user(bot, gid, item, accept, unbanned, member_present=False):
    """ЛС решением — тот самый метод кога, через его цикл.

    member_present — человек на сервере (изоляция): ЛС скажет «доступ
    восстановлен», а для реального Discord-бана — текст про возврат
    (плюс разовая ссылка, если владелец включил в «Правилах подачи»).
    """
    try:
        cog = bot.get_cog('Appeals')
    except Exception as _ex:
        _log.debug('appeals: get_cog: %s', _ex)
        cog = None
    if cog is None:
        return False
    try:
        settings = AP.settings_of(_state(gid))
        guild = None
        try:
            guild = bot.get_guild(int(gid))
        except Exception as _ex:
            _log.debug('appeals: guild на ЛС: %s', _ex)
        invite_url = None
        if accept and unbanned and not member_present and guild is not None:
            try:
                invite_url = _run_async(
                    cog._make_return_invite(guild, settings), timeout=10)
            except Exception as _ex:
                _log.debug('appeals: инвайт возврата из панели: %s', _ex)
        _run_async(cog._notify_user(
            item, accept, unbanned,
            cooldown_hours=settings['cooldown_hours'],
            guild_name=str(getattr(guild, 'name', '') or ''),
            member_present=member_present, invite_url=invite_url,
            guild_id=int(gid)), timeout=10)
        return True
    except Exception as _ex:
        _log.debug('appeals: ЛС решением: %s', _ex)
        return False


def apply_side_effects(bot, gid, item, accept):
    """Разбан/снятие изоляции (при принятии) + ЛС — как в AppealView._resolve."""
    if not bot:
        return {'offline': True, 'unbanned': None, 'dm_attempted': False}
    unbanned = None
    member_present = False
    if accept:
        guild = None
        try:
            guild = bot.get_guild(int(gid))
        except Exception as _ex:
            _log.debug('appeals: guild на разбане: %s', _ex)
        if guild is not None:
            member = None
            try:
                member = guild.get_member(int(item['user_id']))
            except Exception as _ex:
                _log.debug('appeals: member presence: %s', _ex)
            member_present = member is not None
            # панель повторяет кнопку кога: мягкое возвращение из изоляции —
            # роль-бан, доступ к каналам, голосовой таймаут
            if member is not None:
                async def _soft_return():
                    from services import punish_roles as PR
                    rid = PR.role_for(int(gid), 'ban')
                    role = guild.get_role(rid) if rid else None
                    if role is not None and role in getattr(member, 'roles', []):
                        await member.remove_roles(
                            role, reason=f'Апелляция #{item["id"]} принята')
                        PR.clear(int(gid), member.id, rid)
                    mod = bot.get_cog('Moderation')
                    if mod is not None:
                        await mod._unisolate_member(guild, member)
                        try:
                            await member.timeout(None)
                        except (discord.Forbidden, discord.HTTPException) as _e:
                            _log.debug('appeals: таймаут при возврате: %s', _e)
                try:
                    _run_async(_soft_return(), timeout=15)
                except Exception as _ex:
                    _log.debug('appeals: снятие изоляции из панели: %s', _ex)
            unbanned = _unban(guild, item['user_id'], item['id'])
    dm = _notify_user(bot, gid, item, accept, bool(unbanned), member_present)
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
            'link': str(item.get('link') or ''),
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
        gid = active_guild_id()   # панель живёт одним сервером (MAIN_GUILD_ID)
        state = _state(gid)
        settings = AP.settings_of(state)
        return jsonify({
            'success': True,
            'stats': overview_stats(state),
            'pending': pending_view(state, gid=gid),
            'readiness': channel_readiness(appmod.bot_instance, gid, state),
            'can_edit': session.get('role') in ('admin', 'owner'),
            'appearance': ABC.normalize_appearance(state.get('appearance')),
            'themes': [{'id': t, 'label': t} for t in ABC.APPEAL_THEME_ORDER],
            'settings': settings,
        })

    @app.route('/api/guild/<gid>/appeals/appearance', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_appeals_appearance(gid):
        """Оформление карточки апелляции: авто-картинка (тема), свой URL или off."""
        gid = active_guild_id()
        data = _safe_json_obj()
        ap = ABC.normalize_appearance(data)
        url = ap['url']
        if ap['mode'] == 'url' and url:
            low = url.lower()
            if not low.startswith('https://'):
                return jsonify({'success': False,
                                'error': 'Картинка по URL — только по https:// (Discord не покажет http)'}), 400
            if any(bad in low for bad in ('localhost', '127.0.0.1', '0.0.0.0')):
                return jsonify({'success': False,
                                'error': 'Адрес картинки должен быть публичным'}), 400
        state = _state(gid)
        state['appearance'] = ap
        _save(gid, state)
        _notify(f'Оформление апелляций: {ABC.APPEAL_MODE_LABELS[ap["mode"]]}'
                + (f' ({ap["theme"]})' if ap['mode'] == 'auto' else ''))
        return jsonify({'success': True, 'appearance': ap,
                        'message': 'Оформление сохранено: ' +
                                   ABC.APPEAL_MODE_LABELS[ap['mode']] +
                                   (f' · тема «{ap["theme"]}»' if ap['mode'] == 'auto' else '')})

    @app.route('/api/guild/<gid>/appeals/settings', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_appeals_settings(gid):
        """«Правила подачи»: кулдаун после отказа, порог напоминаний о висящих,
        обязательный комментарий при отказе, шаблоны причин отказа."""
        gid = active_guild_id()
        data = _safe_json_obj()

        def _clamp_hours(value, lo, hi, fallback):
            try:
                return max(lo, min(int(value), hi))
            except (TypeError, ValueError):
                return fallback

        state = _state(gid)
        cur = AP.settings_of(state)
        tpl_in = data.get('reject_templates')
        templates = cur['reject_templates']
        if isinstance(tpl_in, list):
            templates = [str(t).strip()[:100] for t in tpl_in]
            templates = [t for t in templates if t][:AP.MAX_TEMPLATES]
            if not templates:
                return jsonify({'success': False,
                                'error': 'Нужен хотя бы один шаблон отказа'}), 400
        # канал для разовых ссылок-возвратов (0 = выключено)
        invite_channel_id = cur['invite_channel_id']
        if 'invite_channel_id' in data:
            try:
                invite_channel_id = max(0, int(data.get('invite_channel_id') or 0))
            except (TypeError, ValueError):
                return jsonify({'success': False,
                                'error': 'Канал для ссылок: число'}), 400
        invite_on_unban = bool(data.get('invite_on_unban',
                                        cur['invite_on_unban']))
        if invite_on_unban and not invite_channel_id:
            return jsonify({'success': False,
                            'error': 'Разовые ссылки: сначала выберите канал'}), 400
        settings = {
            'cooldown_hours': _clamp_hours(data.get('cooldown_hours'), 0, 720,
                                           cur['cooldown_hours']),
            'stale_hours': _clamp_hours(data.get('stale_hours'), 1, 336,
                                        cur['stale_hours']),
            # флаг не передали — оставляем как было, не сбрасываем молча
            'require_reply_on_reject': bool(data.get('require_reply_on_reject',
                                                     cur['require_reply_on_reject'])),
            'reject_templates': templates,
            'invite_on_unban': invite_on_unban,
            'invite_channel_id': invite_channel_id,
            'ping_role_id': _clamp_hours(data.get('ping_role_id'), 0, 10 ** 25,
                                         cur['ping_role_id']),
            'block_after_rejects': _clamp_hours(data.get('block_after_rejects'),
                                                0, 10,
                                                cur['block_after_rejects']),
            # эскалация старшей роли: 0 часов — выключена
            'escalate_hours': _clamp_hours(data.get('escalate_hours'), 0, 336,
                                           cur['escalate_hours']),
            'escalate_role_id': _clamp_hours(data.get('escalate_role_id'), 0,
                                             10 ** 25,
                                             cur['escalate_role_id']),
        }
        state['settings'] = settings
        _save(gid, state)
        _notify('Апелляции: правила подачи обновлены')
        return jsonify({'success': True, 'settings': settings,
                        'message': 'Правила подачи сохранены'})

    @app.route('/api/guild/<gid>/appeals/card-preview.png')
    @login_required
    @role_required('mod')
    def api_appeals_card_preview(gid):
        """Живой предпросмотр авто-карточки апелляции в выбранной теме."""
        theme = request.args.get('theme')
        text = (request.args.get('text') or
                'Бан за ссылки — это был не спам, а ссылка на общий документ '
                'с гайдом по ивенту. Прикладываю скрин переписки с согласованием.'
                )[:400]
        link = request.args.get('link') or 'https://i.imgur.com/demo-appeal-proof.png'
        png = ABC.render_appeal_card(
            appeal_id=7, user_name='Кипарис', text=text,
            link=link, theme=theme or ABC.DEFAULT_APPEAL_THEME)
        if not png:
            return jsonify({'success': False, 'error': 'Не удалось отрисовать пример'}), 500
        resp = Response(png, mimetype='image/png')
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    @app.route('/api/guild/<gid>/appeals/user/<uid>')
    @login_required
    @role_required('mod')
    def api_appeals_user(gid, uid):
        """Апелляции конкретного участника — мини-блок в карточке 360°."""
        gid = active_guild_id()
        state = _state(gid)
        items = [i for i in (state or {}).get('items', [])
                 if str(i.get('user_id')) == str(uid)]
        items.sort(key=lambda i: str(i.get('created_at') or ''), reverse=True)
        return jsonify({'success': True, 'total': len(items), 'items': [{
            'id': i.get('id'),
            'status': i.get('status'),
            'status_label': STATUS_LABELS.get(i.get('status'), '?'),
            'created_at': str(i.get('created_at') or '')[:16].replace('T', ' '),
            'reviewed_at': str(i.get('reviewed_at') or '')[:16].replace('T', ' '),
            'reply': str(i.get('reply') or ''),
            'text': str(i.get('text') or '')[:120],
        } for i in items[:5]]})

    @app.route('/api/guild/<gid>/appeals/history')
    @login_required
    @role_required('mod')
    def api_appeals_history(gid):
        gid = active_guild_id()
        return jsonify({'success': True,
                        'items': history_view(_state(gid),
                                              status=request.args.get('status'),
                                              query=request.args.get('q'))})

    @app.route('/api/guild/<gid>/appeals/resolve', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_appeals_resolve(gid):
        import web.app as appmod
        gid = active_guild_id()
        data = _safe_json_obj()
        raw_id = str(data.get('appeal_id') or '').strip()
        if not raw_id.isdigit():
            return jsonify({'success': False,
                            'error': 'Некорректный номер апелляции'}), 400
        accept = data.get('accept')
        if accept not in (True, False):
            return jsonify({'success': False,
                            'error': 'Решение должно быть true или false'}), 400
        # настройка «комментарий обязателен при отказе» — из «Правил подачи»
        reply = str(data.get('reply') or '')
        if accept is False:
            settings = AP.settings_of(_state(gid))
            if settings['require_reply_on_reject'] and not reply.strip():
                return jsonify({'success': False,
                                'error': 'При отказе комментарий обязателен — '
                                         'выберите шаблон или напишите свой'}), 400
        # Принятие = разбан/снятие изоляции — то же действие «Бан», что у
        # /unban: настройки «Права команд» действуют и в панели.
        if accept:
            from web.routes._common import viewer_member, acl_action_allowed
            _member = viewer_member(appmod.bot_instance, gid)
            if not acl_action_allowed(gid, _member, 'ban'):
                return jsonify({'success': False,
                                'error': 'Нет права: «Бан» не разрешено вашей '
                                         'роли (настройка — «Права команд»)'}), 403
        ok, err, code, payload = resolve_panel(
            appmod.bot_instance, gid, int(raw_id), accept,
            session.get('username', '?'), reply=reply)
        if not ok:
            return jsonify({'success': False, 'error': err}), code
        payload['success'] = True
        _notify(f'Апелляция #{raw_id}: {payload["status_text"]}')
        return jsonify(payload)

    @app.route('/api/guild/<gid>/appeals/claim', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_appeals_claim(gid):
        """Взять апелляцию в работу из панели / снять с себя (повтор)."""
        gid = active_guild_id()
        data = _safe_json_obj()
        raw_id = str(data.get('appeal_id') or '').strip()
        if not raw_id.isdigit():
            return jsonify({'success': False,
                            'error': 'Некорректный номер апелляции'}), 400
        state = _state(gid)
        item = AP.get_appeal(state, int(raw_id))
        if item is None or item.get('status') != 'pending':
            return jsonify({'success': False,
                            'error': 'Апелляция уже решена или не найдена'}), 404
        uid = str(session.get('discord_id') or session.get('username') or '?')
        uname = str(session.get('username') or uid)
        claim = item.get('claimed_by') or None
        if claim and str(claim.get('id')) != uid:
            return jsonify({'success': False,
                            'error': f'Уже в работе у {claim.get("name")}'}), 409
        if claim:
            item['claimed_by'] = None
            claimed_by = ''
        else:
            item['claimed_by'] = {'id': uid, 'name': uname,
                                  'at': datetime.now(UTC).isoformat()}
            claimed_by = uname
        _save(gid, state)
        _notify(f'Апелляция #{raw_id}: ' +
                ('в работе у ' + uname if claimed_by else 'снята с работы'))
        return jsonify({'success': True, 'claimed': bool(claimed_by),
                        'claimed_by': claimed_by})

    @app.route('/api/guild/<gid>/appeals/channel', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_appeals_channel(gid):
        import web.app as appmod
        gid = active_guild_id()
        data = _safe_json_obj()
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
        gid = active_guild_id()
        rows = appeals_csv_rows(_state(gid))
        body = '\ufeff' + CSV_HEADER + '\n'
        body += '\n'.join(';'.join(_csv_cell(c) for c in row) for row in rows) + '\n'
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=appeals_{gid}.csv')
        return resp
