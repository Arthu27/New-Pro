# -*- coding: utf-8 -*-
"""Активность персонала (идеи #196-200): таблица /staff-stats в браузере.

Логика 1:1 cogs/staff_stats.py — те самые collect_actions (mod_data.json +
temp_history.json + варны из sqlite), summarize (период в днях) и
_breakdown (подписи действий из ACTION_LABEL кога). Период зажат в 1..365
ровно как в команде, дефолт 30. Карточка модератора — как в эмбеде: всего,
последнее действие, разбивка и «Последние 5 действий» тем же отбором
(desc по времени, те же подписи).

Имена берутся из кэша гильдии, когда бот жив; без него — честный запасной
вариант самой команды «ID {mod_id}», данные ведь лежат в файлах и базе.
Ничего не меняется, поэтому всё — mod+ (у команды moderate_members).
"""
import time
from datetime import datetime, timezone

from web.routes._common import (
    render_template, session, request, jsonify, Response,
)

from cogs import staff_stats as SS

UTC = timezone.utc

ERR_DAYS = 'Дни — целое число'
ERR_NUMBER = 'ID — число'
SOURCES_NOTE = ('Читаются: mod_data.json, temp_history.json, '
                'варны из базы')   # подпись пустого эмбеда команды


def _guild(bot_lookup, gid):
    """Гильдия из кэша или None — тогда имена идут запасным «ID x»."""
    bot = bot_lookup()
    if bot is None:
        return None
    return bot.get_guild(int(gid))


def _clamp_days(raw):
    """Период 1:1 команде: целое, зажатое в 1..365."""
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return None
    return max(1, min(days, 365))


def _name_of(guild, mod_id):
    """Имя из кэша или запасной вариант команды «ID {mod_id}»."""
    member = guild.get_member(int(mod_id)) if guild and str(mod_id).isdigit() else None
    return str(member.display_name) if member else f'ID {mod_id}'


def _row(guild, mod_id, ent):
    return {
        'mod_id': str(mod_id),
        'name': _name_of(guild, mod_id),
        'total': int(ent['total']),
        'by': dict(ent['by']),
        'breakdown': SS._breakdown(ent['by']),
        'last_ts': int(ent.get('last_ts') or 0),
        'last_at': (datetime.fromtimestamp(ent['last_ts'], UTC)
                    .strftime('%Y-%m-%d %H:%M') if ent.get('last_ts') else ''),
    }


def table_flow(bot_lookup, gid, days_raw):
    """Витрина топа 1:1 эмбеду: сортировка по total desc, сумма периода."""
    days = _clamp_days(days_raw)
    if days is None:
        return False, ERR_DAYS, 400, None
    guild = _guild(bot_lookup, gid)
    actions = SS.collect_actions(int(gid))
    per = SS.summarize(actions, days)
    rows = [_row(guild, mod_id, ent) for mod_id, ent in
            sorted(per.items(), key=lambda x: -x[1]['total'])]
    return True, '', 200, {
        'days': days,
        'grand_total': sum(e['total'] for e in per.values()),
        'mods_total': len(per),
        'sources': SOURCES_NOTE,
        'live_names': guild is not None,
        'rows': rows,
    }


def card_flow(bot_lookup, gid, user_id, days_raw):
    """Карточка 1:1 эмбеду: всего/разбивка/последнее + последние 5."""
    days = _clamp_days(days_raw)
    if days is None:
        return False, ERR_DAYS, 400, None
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False, ERR_NUMBER, 400, None
    guild = _guild(bot_lookup, gid)
    actions = SS.collect_actions(int(gid))
    per = SS.summarize(actions, days)
    ent = per.get(str(uid), {'total': 0, 'by': {}, 'last_ts': 0})
    mine = [a for a in actions if a[0] == str(uid)]
    mine.sort(key=lambda a: -a[2])
    recent = [{
        'action': act,
        'label': SS.ACTION_LABEL.get(act, f'▪ {act}'),
        'ts': int(ts),
        'at': datetime.fromtimestamp(ts, UTC).strftime('%Y-%m-%d %H:%M'),
    } for _mid, act, ts in mine[:5]]
    return True, '', 200, {
        'mod_id': str(uid),
        'name': _name_of(guild, uid),
        'days': days,
        'total': int(ent['total']),
        'breakdown': SS._breakdown(ent['by']),
        'by': dict(ent['by']),
        'last_ts': int(ent.get('last_ts') or 0),
        'last_at': (datetime.fromtimestamp(ent['last_ts'], UTC)
                    .strftime('%Y-%m-%d %H:%M') if ent.get('last_ts') else ''),
        'recent': recent,
    }


def _csv_cell(text):
    return str(text).replace(';', ',').replace('\r', ' ').replace('\n', ' ')


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _bot():
        import web.app as appmod
        return appmod.bot_instance

    def _json():
        return request.get_json(silent=True) or {}

    def _reply(result):
        ok, err, code, payload = result
        if not ok:
            return jsonify({'success': False, 'error': err}), code
        return jsonify({'success': True, **payload})

    @app.route('/staff-stats')
    @login_required
    @role_required('mod')
    def staff_stats_page():
        return render_template('staff_stats.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/staff-stats/table')
    @login_required
    @role_required('mod')
    def api_staff_stats_table(gid):
        return _reply(table_flow(_bot, gid, request.args.get('days', 30)))

    @app.route('/api/guild/<gid>/staff-stats/card', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_staff_stats_card(gid):
        data = _json()
        return _reply(card_flow(_bot, gid, data.get('user_id'),
                                data.get('days', 30)))

    @app.route('/api/guild/<gid>/staff-stats/export.csv')
    @login_required
    @role_required('mod')
    def api_staff_stats_csv(gid):
        ok, err, code, payload = table_flow(_bot, gid,
                                            request.args.get('days', 30))
        if not ok:
            return jsonify({'success': False, 'error': err}), code
        body = '\ufeff' + 'mod_id;name;total;last_at;breakdown\n'
        body += '\n'.join(';'.join(_csv_cell(c) for c in (
            r['mod_id'], r['name'], r['total'], r['last_at'],
            r['breakdown'])) for r in payload['rows'])
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=staff_stats_{gid}.csv')
        return resp
