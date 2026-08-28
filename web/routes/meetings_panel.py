# -*- coding: utf-8 -*-
"""Собрания (идеи #141-145): управление /sobranie из браузера.

Конфиг и переходы состояний — через функции кога 1:1:
- _load_cfg/_save_cfg (включая подмешивание staff_roles из
  mod_report_config_<gid>.json, когда своих нет);
- старт: его _save_voice_snapshot + active/meeting_start, как в модалке;
  своя дата парсится тем же '%d.%m.%Y %H:%M' с текстом ошибки кнопки;
- завершение или «нет активного собрания», или окно since по той же
  цепочке meeting_start -> last_meeting -> now-7d и тот же сброс полей.

Очки отчёта — его формула: сообщения×1 + минуты войса×2 + инвайты×5.
Предпросмотр считает то, что доступно без Discord: голос против снимка
(живой _scan_voice кога через asyncio.run — там нет await) и инвайты через
его _load_invites; сообщения между собраниями читает только живой бот —
в интерфейсе это подписано честно.

Чтение — mod+; старт/стоп и роли отчёта — admin+ (в боте это права
administrator на кнопках).
"""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from web.routes._common import (
    _log, _run_async,
    render_template, session, request, jsonify, Response,
)

from cogs import meeting as MT

UTC = timezone.utc

# Слова сообщений кнопок/модалки кога — без эмодзи, как требует стиль панели
ERR_ALREADY = 'Собрание уже активно!'
ERR_NOT_ACTIVE = 'Нет активного собрания.'
ERR_FORMAT = 'Format неверно! Напр.: 12.04.2026 22:00'
TEXT_NEVER = 'Собрание еще не проводилось.'
ERR_NO_ROLES = 'Добавленные роли отсутствуют.'
ERR_ROLE_ID = 'Некорректный ID роли'
ERR_ROLE_MISSING = 'Этой роли нет в списке отчёта.'
FORMULA_TEXT = 'Очки: Сообщение×1 + Звук мин×2 + Приглашение×5'
PREVIEW_NOTE = ('Сообщения между собраниями считает живой скан Discord — '
                'здесь голос против снимка начала и инвайты.')

PREVIEW_LIMIT = 20


def _gid(gid):
    return int(gid)


def load_cfg(gid):
    """Конфиг сервера через загрузчик кога (со склейкой staff_roles)."""
    return MT._load_cfg(_gid(gid))


def _save(gid, cfg):
    MT._save_cfg(_gid(gid), cfg)


def _parse_ts(raw):
    """iso -> aware datetime (метки без TZ считаем UTC, как кнопка отчёта)."""
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts


def status_view(cfg):
    """Карточка состояния для шапки страницы."""
    active = bool(cfg.get('active'))
    start = _parse_ts(cfg.get('meeting_start'))
    last = _parse_ts(cfg.get('last_meeting'))
    since = start or last
    return {
        'active': active,
        'meeting_start': start.isoformat() if start else None,
        'last_meeting': last.isoformat() if last else None,
        'since': since.isoformat() if since else None,
        'elapsed_min': (round((datetime.now(UTC) - start).total_seconds() // 60)
                        if active and start else None),
        'ever_held': since is not None,
        'note': None if since is not None else TEXT_NEVER,
        'staff_roles': [str(r) for r in (cfg.get('staff_roles') or [])],
        'panel_channel': str(cfg.get('panel_channel') or ''),
    }


def start_flow(gid, when=''):
    """Старт собрания — шаги кнопки «Запустить» + модалки времени."""
    cfg = load_cfg(gid)
    if cfg.get('active'):
        return False, ERR_ALREADY, None
    when = (when or '').strip()
    if when:
        try:
            start = datetime.strptime(when, '%d.%m.%Y %H:%M').replace(tzinfo=UTC)
        except ValueError:
            return False, ERR_FORMAT, None
    else:
        start = datetime.now(UTC)
    MT._save_voice_snapshot(_gid(gid))
    cfg['active'] = True
    cfg['meeting_start'] = start.isoformat()
    _save(gid, cfg)
    return True, '', start.isoformat()


def end_flow(gid):
    """Финиш — окно since и сброс полей по цепочке кнопки «Завершить»."""
    cfg = load_cfg(gid)
    if not cfg.get('active'):
        return False, ERR_NOT_ACTIVE, None, None
    since = _parse_ts(cfg.get('meeting_start') or cfg.get('last_meeting'))
    if since is None:
        since = datetime.now(UTC) - timedelta(days=7)
    cfg['active'] = False
    cfg['last_meeting'] = datetime.now(UTC).isoformat()
    cfg['meeting_start'] = None
    _save(gid, cfg)
    return True, '', since, cfg


def add_role_flow(gid, rid_raw, name=None):
    """Дедупликация и запись — как у команды !sobranie-rol-add."""
    rid_raw = str(rid_raw or '').strip().strip('<@&>')
    if not rid_raw.isdigit():
        return False, ERR_ROLE_ID, None
    rid = int(rid_raw)
    cfg = load_cfg(gid)
    roles = cfg.setdefault('staff_roles', [])
    if rid not in roles:
        roles.append(rid)
        _save(gid, cfg)
    label = name or rid_raw
    return True, '', f'Роль {label} добавлена в отчёт собрания.'


def remove_role_flow(gid, rid_raw, name=None):
    rid_raw = str(rid_raw or '').strip().strip('<@&>')
    if not rid_raw.isdigit():
        return False, ERR_ROLE_ID, None
    rid = int(rid_raw)
    cfg = load_cfg(gid)
    roles = cfg.get('staff_roles') or []
    if not roles:
        return False, ERR_NO_ROLES, None
    if rid not in roles:
        return False, ERR_ROLE_MISSING, None
    roles.remove(rid)
    _save(gid, cfg)
    label = name or rid_raw
    return True, '', f'Роль {label} убрана из отчёта собрания.'


def preview(gid, limit=PREVIEW_LIMIT):
    """Что соберёт отчёт прямо сейчас: голос против снимка + инвайты.

    Голосовая разница — живой _scan_voice кога (async без await, гоняем
    через asyncio.run); сообщения он читает из Discord — офлайн их нет,
    и строки честно идут с msg=0.
    """
    voice_secs = asyncio.run(MT._scan_voice(SimpleNamespace(id=_gid(gid)), None))
    invites = MT._load_invites(_gid(gid))
    voice_now = MT._vt.voice_view(_gid(gid)).get('users', {})
    names = {uid: rec.get('name') for uid, rec in voice_now.items()}

    rows = []
    for uid in set(voice_secs) | set(invites):
        secs = int(voice_secs.get(uid, 0) or 0)
        inv = int(invites.get(uid, 0) or 0)
        score = (secs // 60) * 2 + inv * 5
        if score <= 0:
            continue
        rows.append({
            'uid': uid,
            'name': names.get(uid) or uid,
            'voice_secs': secs,
            'voice_txt': MT._vt.fmt_duration(secs),
            'inv': inv,
            'score': score,
        })
    rows.sort(key=lambda r: r['score'], reverse=True)
    if limit is not None:
        rows = rows[:limit]
    totals = {
        'participants': len(rows),
        'voice_min': sum(r['voice_secs'] for r in rows) // 60,
        'invites': sum(r['inv'] for r in rows),
        'score': sum(r['score'] for r in rows),
    }
    return rows, totals


def csv_rows(rows):
    return [(r['uid'], r['name'], r['voice_secs'] // 60, r['inv'], r['score'])
            for r in rows]


def _csv_cell(text):
    return str(text).replace(';', ',').replace('\r', ' ').replace('\n', ' ')


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _role_name(bot, gid, rid):
        """Имя роли для текстов — если бот жив и роль на месте."""
        if bot is None:
            return None
        try:
            guild = bot.get_guild(int(gid))
            role = guild.get_role(int(rid)) if guild else None
        except (TypeError, ValueError) as exc:
            _log.debug('meetings _role_name: %s', exc)
            return None
        return role.name if role else None

    @app.route('/meetings')
    @login_required
    @role_required('mod')
    def meetings_page():
        return render_template('meetings.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id(),
                               can_edit=session.get('role') in ('admin', 'owner'))

    @app.route('/api/guild/<gid>/meetings/status')
    @login_required
    @role_required('mod')
    def api_meetings_status(gid):
        import web.app as appmod
        view = status_view(load_cfg(gid))
        names = {r: _role_name(appmod.bot_instance, gid, r)
                 for r in view['staff_roles']}
        view['role_names'] = names
        return jsonify({'success': True, 'status': view,
                        'formula': FORMULA_TEXT,
                        'can_edit': session.get('role') in ('admin', 'owner'),
                        'bot_online': appmod.bot_instance is not None})

    @app.route('/api/guild/<gid>/meetings/preview')
    @login_required
    @role_required('mod')
    def api_meetings_preview(gid):
        rows, totals = preview(gid)
        view = status_view(load_cfg(gid))
        return jsonify({'success': True, 'rows': rows, 'totals': totals,
                        'since': view['since'], 'active': view['active'],
                        'window': ('с начала текущего собрания' if view['active']
                                   else 'с прошлого собрания' if view['since'] else None),
                        'note': PREVIEW_NOTE, 'formula': FORMULA_TEXT})

    @app.route('/api/guild/<gid>/meetings/start', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_meetings_start(gid):
        when = (request.get_json(silent=True) or {}).get('time', '')
        ok, err, start_iso = start_flow(gid, when)
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        start = _parse_ts(start_iso)
        return jsonify({'success': True,
                        'message': (f'Собрание запущено: '
                                    f'{start.strftime("%d.%m.%Y %H:%M")} UTC. '
                                    'Голосовой снимок зафиксирован.'),
                        'status': status_view(load_cfg(gid))})

    @app.route('/api/guild/<gid>/meetings/end', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_meetings_end(gid):
        ok, err, since, cfg = end_flow(gid)
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        import web.app as appmod
        sent = False
        if appmod.bot_instance is not None and cfg.get('panel_channel'):
            guild = appmod.bot_instance.get_guild(_gid(gid))
            channel = (guild.get_channel(int(cfg['panel_channel']))
                       if guild else None)
            if channel is not None:
                try:
                    embeds = _run_async(MT._build_meeting_report(guild, since),
                                        timeout=60)

                    async def _send_report():
                        for i in range(0, len(embeds), 10):
                            await channel.send(embeds=embeds[i:i + 10])

                    _run_async(_send_report(), timeout=30)
                    sent = True
                except Exception as exc:
                    _log.debug('meetings end report: %s', exc)
        if sent:
            msg = 'Собрание завершено. Отчёт отправлен в канал панели.'
        elif appmod.bot_instance is None:
            msg = ('Собрание завершено. Бот офлайн — отчёт за это окно не '
                   'построить: историю читает только живой бот.')
        else:
            msg = ('Собрание завершено. Отчёт не ушёл: канал панели '
                   'неизвестен — отправьте !sobranie в Discord, чтобы его '
                   'зафиксировать.')
        return jsonify({'success': True, 'message': msg, 'report_sent': sent,
                        'status': status_view(load_cfg(gid))})

    @app.route('/api/guild/<gid>/meetings/roles', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_meetings_role_add(gid):
        raw = str((request.get_json(silent=True) or {}).get('role') or '')
        import web.app as appmod
        ok, err, msg = add_role_flow(gid, raw,
                                     _role_name(appmod.bot_instance, gid, raw))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, 'message': msg,
                        'status': status_view(load_cfg(gid))})

    @app.route('/api/guild/<gid>/meetings/roles/remove', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_meetings_role_remove(gid):
        raw = str((request.get_json(silent=True) or {}).get('role') or '')
        import web.app as appmod
        ok, err, msg = remove_role_flow(gid, raw,
                                        _role_name(appmod.bot_instance, gid, raw))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, 'message': msg,
                        'status': status_view(load_cfg(gid))})

    @app.route('/api/guild/<gid>/meetings/export.csv')
    @login_required
    @role_required('mod')
    def api_meetings_export(gid):
        rows, _totals = preview(gid, limit=None)
        body = '\ufeff' + 'uid;name;voice_minutes;invites;score\n'
        body += '\n'.join(';'.join(_csv_cell(c) for c in row)
                          for row in csv_rows(rows))
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=meetings_preview_{gid}.csv')
        return resp
