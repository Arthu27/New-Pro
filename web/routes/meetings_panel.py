# -*- coding: utf-8 -*-
"""Панель собраний стаффа — создание, явка, уважительные причины.

Хранилище: GuildData('meetings'), пишет cogs/meetings.py
"""

from datetime import datetime, timezone
from db import GuildData
from cogs import meetings as MT
from web.routes._common import _safe_json_obj, _log, _run_async, _live_publish, render_template, session, request, jsonify, Response

UTC = timezone.utc

def _db():
    return GuildData('meetings')

def _state(gid):
    return _db().get(gid, 'state', MT.empty_state()) or MT.empty_state()

def _save(gid, state):
    _db().set(gid, 'state', state)
    # live-пуш: собрания обновились — панель обновится без F5
    try:
        _live_publish(gid, 'meetings')
    except Exception as _ex:
        _log.debug('meetings live_publish: %s', _ex)


def overview_stats(state):
    items = (state or {}).get('items', [])
    total = len(items)
    scheduled = sum(1 for i in items if i.get('status') == 'scheduled')
    finished = sum(1 for i in items if i.get('status') == 'finished')
    cancelled = sum(1 for i in items if i.get('status') == 'cancelled')
    # явка
    total_yes = total_no = total_maybe = 0
    total_excuses = 0
    for it in items:
        s = MT.meeting_stats(it)
        total_yes += s['yes']
        total_no += s['no']
        total_maybe += s['maybe']
        total_excuses += s['excuses']
    return {
        'total': total,
        'scheduled': scheduled,
        'finished': finished,
        'cancelled': cancelled,
        'yes': total_yes,
        'no': total_no,
        'maybe': total_maybe,
        'excuses': total_excuses,
    }


def meetings_view(state):
    from datetime import timedelta as _td
    items = list((state or {}).get('items', []))
    # свежие сверху (по ISO — уже UTC, сортировка строкой ок)
    items.sort(key=lambda i: str(i.get('scheduled_at') or ''), reverse=True)
    out = []
    for it in items[:50]:
        sched = MT._parse_dt(it.get('scheduled_at'))
        # показываем в МСК для панели
        if sched:
            msk = sched.astimezone(timezone(_td(hours=3)))
            sched_str = msk.strftime('%d.%m.%Y %H:%M МСК')
        else:
            sched_str = str(it.get('scheduled_at') or '')[:16].replace('T',' ')
        out.append({
            'id': it.get('id'),
            'type': it.get('type'),
            'type_label': MT.MEETING_TYPES.get(it.get('type'), {}).get('label', it.get('type')),
            'title': it.get('title'),
            'description': it.get('description'),
            'scheduled_at': sched_str,
            'scheduled_ts': int(sched.timestamp()) if sched else 0,
            'created_by': it.get('created_by'),
            'status': it.get('status'),
            'channel_id': it.get('channel_id'),
            'message_id': it.get('message_id'),
            'stats': MT.meeting_stats(it),
            'attendance': it.get('attendance') or {},
            'excuses': it.get('excuses') or {},
        })
    return out


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _notify(title):
        from web.routes._common import _fire_panel_notification
        try:
            _fire_panel_notification('mod_action', title, f"Через панель ({session.get('username','?')})")
        except Exception as _ex:
            _log.debug('meetings: notify: %s', _ex)

    @app.route('/meetings')
    @login_required
    @role_required('mod')
    def meetings_page():
        return render_template('meetings.html', role=session.get('role'), username=session.get('username'),
                               guild_id=active_guild_id(), can_edit=session.get('role') in ('admin','owner'))

    @app.route('/api/guild/<gid>/meetings/overview')
    @login_required
    @role_required('mod')
    def api_meetings_overview(gid):
        import web.app as appmod
        gid = active_guild_id()
        state = _state(gid)
        return jsonify({
            'success': True,
            'stats': overview_stats(state),
            'meetings': meetings_view(state),
            'types': [{'id': k, 'label': v['label'], 'emoji': v['emoji']} for k,v in MT.MEETING_TYPES.items()],
            'can_edit': session.get('role') in ('admin','owner'),
        })

    @app.route('/api/guild/<gid>/meetings/create', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_meetings_create(gid):
        import web.app as appmod
        gid = active_guild_id()
        data = _safe_json_obj()
        mtype = str(data.get('type') or 'general').strip()
        title = str(data.get('title') or '').strip()
        desc = str(data.get('description') or '').strip()
        scheduled_at = str(data.get('scheduled_at') or '').strip()
        ping_role_id = data.get('ping_role_id')

        if not title:
            return jsonify({'success': False, 'error': 'Название собрания обязательно'}), 400
        if not scheduled_at:
            return jsonify({'success': False, 'error': 'Время обязательно'}), 400

        # создаём через ког если бот онлайн — авто-отправка таблицы + ЛС
        bot = appmod.bot_instance
        if bot:
            guild = None
            try:
                guild = bot.get_guild(int(gid))
            except Exception as _ex:
                _log.debug('meetings: guild: %s', _ex)
            if guild is None:
                return jsonify({'success': False, 'error': 'Бот офлайн — собрание не создать'}), 503

            try:
                cog = bot.get_cog('Meetings')
                if cog is None:
                    return jsonify({'success': False, 'error': 'Модуль собраний не загружен'}), 500

                # парсим время: ожидаем ISO или datetime-local (YYYY-MM-DDTHH:MM) — считаем МСК
                from datetime import datetime as _dt, timedelta as _td
                try:
                    dt = _dt.fromisoformat(scheduled_at.replace('Z','+00:00'))
                    if dt.tzinfo is None:
                        # наивное из <input datetime-local> — МСК (UTC+3)
                        dt = dt.replace(tzinfo=timezone(_td(hours=3))).astimezone(timezone.utc)
                except Exception:
                    return jsonify({'success': False, 'error': 'Неверный формат времени — используйте YYYY-MM-DDTHH:MM'}), 400

                async def _do():
                    return await cog.create_and_publish(
                        guild, mtype, title, desc, dt,
                        session.get('username','?'),
                        session.get('discord_id') or 0,
                        ping_role_id=ping_role_id
                    )

                item, err = _run_async(_do(), timeout=20)
                if err:
                    return jsonify({'success': False, 'error': err}), 400

                _notify(f"Собрание #{item['id']} — {title}")
                return jsonify({'success': True, 'meeting': item, 'message': f"Собрание #{item['id']} создано — карточка в канале, ЛС разосланы"})
            except Exception as _ex:
                _log.debug('meetings create: %s', _ex)
                return jsonify({'success': False, 'error': f'Ошибка: {_ex}'}), 500
        else:
            # офлайн — просто в БД
            state = _state(gid)
            from datetime import datetime as _dt, timedelta as _td
            try:
                dt = _dt.fromisoformat(scheduled_at.replace('Z','+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone(_td(hours=3))).astimezone(timezone.utc)
            except Exception:
                return jsonify({'success': False, 'error': 'Неверный формат времени'}), 400
            item, err = MT.create_meeting(state, mtype, title, desc, dt, session.get('username','?'), session.get('discord_id') or 0, ping_role_id=ping_role_id)
            if err:
                return jsonify({'success': False, 'error': err}), 400
            _save(gid, state)
            _notify(f"Собрание #{item['id']} — {title} (бот офлайн)")
            return jsonify({'success': True, 'meeting': item, 'message': 'Собрание сохранено — бот офлайн, карточка уйдёт при старте'})

    @app.route('/api/guild/<gid>/meetings/<int:mid>/attendance', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_meetings_attendance(gid, mid):
        gid = active_guild_id()
        data = _safe_json_obj()
        status = str(data.get('status') or '').strip()
        if status not in MT.ATTENDANCE_STATUSES:
            return jsonify({'success': False, 'error': 'Неверный статус'}), 400
        state = _state(gid)
        item, err = MT.set_attendance(state, mid, session.get('discord_id') or 0, status)
        if err:
            return jsonify({'success': False, 'error': err}), 400
        _save(gid, state)
        return jsonify({'success': True, 'stats': MT.meeting_stats(item)})

    @app.route('/api/guild/<gid>/meetings/<int:mid>/excuse', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_meetings_excuse(gid, mid):
        gid = active_guild_id()
        data = _safe_json_obj()
        reason = str(data.get('reason') or '').strip()
        if len(reason) < 5:
            return jsonify({'success': False, 'error': 'Причина минимум 5 символов'}), 400
        state = _state(gid)
        item, err = MT.add_excuse(state, mid, session.get('discord_id') or 0, session.get('username','?'), reason)
        if err:
            return jsonify({'success': False, 'error': err}), 400
        _save(gid, state)
        return jsonify({'success': True, 'stats': MT.meeting_stats(item)})

    @app.route('/api/guild/<gid>/meetings/<int:mid>/cancel', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_meetings_cancel(gid, mid):
        gid = active_guild_id()
        state = _state(gid)
        item = MT.get_meeting(state, mid)
        if not item:
            return jsonify({'success': False, 'error': 'Собрание не найдено'}), 404
        item['status'] = 'cancelled'
        _save(gid, state)
        _notify(f"Собрание #{mid} отменено")
        # пробуем обновить карточку в Discord
        try:
            import web.app as appmod
            bot = appmod.bot_instance
            if bot:
                guild = bot.get_guild(int(gid))
                cog = bot.get_cog('Meetings') if bot else None
                if guild and cog:
                    async def _upd():
                        await cog.update_card(guild, mid)
                    _run_async(_upd(), timeout=10)
        except Exception as _ex:
            _log.debug('meetings cancel update: %s', _ex)
        return jsonify({'success': True})

    @app.route('/api/guild/<gid>/meetings/<int:mid>/finish', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_meetings_finish(gid, mid):
        gid = active_guild_id()
        state = _state(gid)
        item = MT.get_meeting(state, mid)
        if not item:
            return jsonify({'success': False, 'error': 'Собрание не найдено'}), 404
        item['status'] = 'finished'
        _save(gid, state)
        _notify(f"Собрание #{mid} завершено")
        try:
            import web.app as appmod
            bot = appmod.bot_instance
            if bot:
                guild = bot.get_guild(int(gid))
                cog = bot.get_cog('Meetings') if bot else None
                if guild and cog:
                    async def _upd():
                        await cog.update_card(guild, mid)
                    _run_async(_upd(), timeout=10)
        except Exception as _ex:
            _log.debug('meetings finish update: %s', _ex)
        return jsonify({'success': True})
