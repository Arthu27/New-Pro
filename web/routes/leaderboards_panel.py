# -*- coding: utf-8 -*-
"""Рейтинги (идеи #146-150): /leaderboard из браузера.

Данные и оформление — строго из кога:
- таблица топ-7 — его _get_lb_data (те же места, тексты значений
  «1 850 СООБЩЕНИЙ» / «52ч 40м В ВОЙСЕ» / «500 000 МОНЕТ» и демо-строки,
  когда данных нет — панель помечает такое честно);
- PNG-карточка — его generate_leaderboard_bytes (Pillow, офлайн тоже
  рисует: гильдия-заглушка с его же фолбэком имени «Hakumo Community»);
- сырые списки для ранга и CSV читаются из тех же файлов и сортируются
  так же (сообщения int, войс total_seconds, баланс balance+bank);
- отправка в канал — как команда: тот же файл + LeaderboardView.

Некорректная категория молча сводится к messages — правило команды.
Чтение — mod+; отправка карточки в канал — admin+.
"""
import os
from types import SimpleNamespace

from web.routes._common import (
    _log, _run_async,
    render_template, session, request, jsonify, Response, discord,
)
from web.routes.mod_control import validate_user_id
from json_store import load_json

from cogs import leaderboard as LB
from cogs.voice_tracker import voice_view, fmt_duration

CATS = ('messages', 'voice', 'balance')
CAT_META = {
    'messages': {'title': 'ТОП ПО СООБЩЕНИЯМ', 'unit': 'сообщений'},
    'voice': {'title': 'ТОП ПО ГОЛОСУ', 'unit': 'сек в войсе'},
    'balance': {'title': 'ТОП ПО БАЛАНСУ МОНЕТ', 'unit': 'монет'},
}
ERR_CHANNEL = 'Некорректный ID канала'
ERR_NO_CHANNEL = 'Канал не найден на сервере.'
ERR_OFFLINE = ('Бот офлайн — карточку можно скачать, но отправить в '
               'Discord может только живой бот.')


def clamp_cat(raw):
    """Правило команды: неизвестная категория -> messages."""
    cat = str(raw or 'messages').lower()
    return cat if cat in CATS else 'messages'


def raw_rows(gid, cat):
    """Сырой рейтинг [(uid, значение)] — те же файлы и та же сортировка.

    Ког хранит лидерборды по абсолютному DATA_DIR (корень проекта), а не
    от cwd — поэтому читаем через его же константу LB.DATA_DIR.
    """
    gid = int(gid)
    rows = []
    if cat == 'messages':
        data = load_json(os.path.join(LB.DATA_DIR, f'leaderboard_{gid}.json'),
                         {}, log=_log)
        msgs = data.get('messages', {}) if isinstance(data, dict) else {}
        rows = [(str(u), int(c)) for u, c in msgs.items()]
    elif cat == 'voice':
        for uid, d in voice_view(gid).get('users', {}).items():
            secs = d.get('total_seconds', 0) if isinstance(d, dict) else int(d)
            rows.append((str(uid), int(secs)))
    elif cat == 'balance':
        data = load_json(os.path.join(LB.DATA_DIR, f'economy_{gid}.json'),
                         {}, log=_log)
        rows = [(str(u), int(d.get('balance', 0) + d.get('bank', 0)))
                for u, d in data.items() if isinstance(d, dict)]
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows


def _demo_names():
    """uid → {'name','avatar'} для офлайн-рендера.

    Реальные имена — из сохранённой карты имён (то, что реально видел бот).
    Демо-участники добавляются только в режиме предпросмотра (name_map_for
    сам их инжектит при DEMO_MODE) — в бою выдуманных людей не показываем.
    """
    out = {}
    try:
        from web.routes._common import name_map_for
        nm = name_map_for(None)
        for uid, name in nm.items():
            out.setdefault(str(uid), {'name': str(name), 'avatar': ''})
    except Exception as _ex:
        _log.debug('_demo_names(): подавлено: %s', _ex)
    return out


def _shim_guild(gid):
    """Гильдия-заглушка для офлайн-рендера: имена участников из демо-данных —
    никаких «HAKUMO_LEADER», таблица показывает реальных людей."""
    names = _demo_names()

    def get_member(uid):
        rec = names.get(str(uid))
        if not rec:
            return None
        return SimpleNamespace(id=int(uid), display_name=rec['name'],
                               name=rec['name'])

    return SimpleNamespace(id=int(gid), name='Hakumo Community',
                           get_member=get_member)


def _guild(bot, gid):
    if bot is None:
        return _shim_guild(gid)
    return bot.get_guild(int(gid)) or _shim_guild(gid)


def _pretty_value(cat, raw):
    """Значение словами панели (русские единицы, пробелы разрядов)."""
    if cat == 'voice':
        return fmt_duration(raw)
    num = f'{int(raw):,}'.replace(',', ' ')
    unit = {'messages': 'сообщений', 'voice': 'в войсе', 'balance': 'монет'}[cat]
    return f'{num} {unit}'


def table_view(bot, gid, cat, limit=20):
    """Топ рейтинга: живые данные и реальные имена (без фейковых заглушек).

    С ботом — словами кога. Офлайн (демо) — из тех же файлов, что читает
    ког, с именами из демо-участников и карты имён. Строки «HAKUMO_LEADER»
    больше не появляются: если данных нет вообще, отдаём пустой список.
    """
    if bot is not None:
        top = LB._get_lb_data(_guild(bot, gid), cat)
        rows = [{'rank': i + 1, 'name': n, 'value': v}
                for i, (n, v) in enumerate(top)]
        rows = rows[:limit]
    else:
        names = _demo_names()
        if cat == 'voice':
            # имена из голосовой статистики (там же, где секунды)
            for uid, d in voice_view(int(gid)).get('users', {}).items():
                if isinstance(d, dict) and d.get('name'):
                    names.setdefault(str(uid), {'name': str(d['name']), 'avatar': str(d.get('avatar') or '')})
        raw = raw_rows(gid, cat)[:limit]
        rows = [{'rank': i + 1,
                 'name': (names.get(uid) or {}).get('name') or f'ID {uid}',
                 'uid': uid,
                 'raw': val,
                 'value': _pretty_value(cat, val)}
                for i, (uid, val) in enumerate(raw)]
        # аватар из демо-участников — в клиентскую строку
        for row in rows:
            rec = names.get(row.get('uid') or '')
            if rec and rec.get('avatar'):
                row['avatar'] = rec['avatar']
    return {'rows': rows,
            'demo': False,
            'title': CAT_META[cat]['title'],
            'cat': cat,
            'unit': CAT_META[cat]['unit']}


def rank_view(gid, uid_raw):
    """Позиция участника в каждом из трёх рейтингов (по сырым спискам)."""
    ok, err, uid = validate_user_id(uid_raw)
    if not ok:
        return False, err, None
    uid = str(uid)
    out = []
    for cat in CATS:
        rows = raw_rows(gid, cat)
        rank = None
        value = 0
        for i, (u, v) in enumerate(rows):
            if u == uid:
                rank, value = i + 1, v
                break
        out.append({'cat': cat, 'title': CAT_META[cat]['title'],
                    'rank': rank, 'total': len(rows), 'raw': value})
    return True, '', out


def rank_pretty(cat, raw):
    """Сырое значение в читаемое (для войса — его fmt_duration)."""
    if cat == 'voice':
        return fmt_duration(raw)
    return f'{raw:,}'.replace(',', ' ') + ' ' + CAT_META[cat]['unit']


def csv_rows(bot, gid, cat):
    """Весь рейтинг: rank;uid;name;value — имена живые, если бот в сети."""
    voice_names = {}
    if cat == 'voice':
        voice_names = {uid: d.get('name') for uid, d in
                       voice_view(int(gid)).get('users', {}).items()
                       if isinstance(d, dict)}
    guild = _guild(bot, gid)
    demo_names = _demo_names()
    out = []
    for i, (uid, val) in enumerate(raw_rows(gid, cat)):
        member = guild.get_member(int(uid)) if uid.isdigit() else None
        name = (member.display_name if member
                else voice_names.get(uid)
                or (demo_names.get(uid) or {}).get('name')
                or f'ID {uid[:6]}')
        out.append((i + 1, uid, name, val))
    return out


def _csv_cell(text):
    return str(text).replace(';', ',').replace('\r', ' ').replace('\n', ' ')


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    @app.route('/leaderboards')
    @login_required
    @role_required('mod')
    def leaderboards_page():
        return render_template('leaderboards.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id(),
                               can_edit=session.get('role') in ('admin', 'owner'))

    @app.route('/api/guild/<gid>/leaderboards/table')
    @login_required
    @role_required('mod')
    def api_lb_table(gid):
        import web.app as appmod
        cat = clamp_cat(request.args.get('cat'))
        return jsonify({'success': True, 'cat': cat,
                        'table': table_view(appmod.bot_instance, gid, cat),
                        'bot_online': appmod.bot_instance is not None})

    @app.route('/api/guild/<gid>/leaderboards/card.png')
    @login_required
    @role_required('mod')
    def api_lb_card(gid):
        import web.app as appmod
        cat = clamp_cat(request.args.get('cat'))
        try:
            buf = LB.generate_leaderboard_bytes(
                _guild(appmod.bot_instance, gid), cat)
        except Exception as exc:
            _log.debug('leaderboards card: %s', exc)
            return jsonify({'success': False,
                            'error': 'Не удалось отрисовать карточку.'}), 500
        resp = Response(buf.getvalue(), mimetype='image/png')
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    @app.route('/api/guild/<gid>/leaderboards/rank')
    @login_required
    @role_required('mod')
    def api_lb_rank(gid):
        ok, err, rows = rank_view(gid, request.args.get('user'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        for r in rows:
            r['pretty'] = rank_pretty(r['cat'], r['raw'])
        return jsonify({'success': True, 'rows': rows})

    @app.route('/api/guild/<gid>/leaderboards/send', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_lb_send(gid):
        import web.app as appmod
        data = request.get_json(silent=True) or {}
        cat = clamp_cat(data.get('cat'))
        cid_raw = str(data.get('channel') or '').strip().strip('<#>')
        if not cid_raw.isdigit():
            return jsonify({'success': False, 'error': ERR_CHANNEL}), 400
        if appmod.bot_instance is None:
            return jsonify({'success': False, 'error': ERR_OFFLINE}), 409
        guild = appmod.bot_instance.get_guild(int(gid))
        channel = guild.get_channel(int(cid_raw)) if guild else None
        if channel is None:
            return jsonify({'success': False, 'error': ERR_NO_CHANNEL}), 404
        try:
            buf = LB.generate_leaderboard_bytes(guild, cat)

            async def _send():
                view = LB.LeaderboardView(current_cat=cat)
                return await channel.send(
                    file=discord.File(buf, filename='leaderboard_card.png'),
                    view=view)

            msg = _run_async(_send(), timeout=30)
        except Exception as exc:
            _log.debug('leaderboards send: %s', exc)
            return jsonify({'success': False,
                            'error': 'Discord не принял карточку — '
                                     'проверьте права бота в канале.'}), 502
        return jsonify({'success': True,
                        'message': f'Карточка «{CAT_META[cat]["title"]}» '
                                   f'отправлена в #{channel.name}.',
                        'message_id': str(getattr(msg, 'id', ''))})

    @app.route('/api/guild/<gid>/leaderboards/export.csv')
    @login_required
    @role_required('mod')
    def api_lb_export(gid):
        import web.app as appmod
        cat = clamp_cat(request.args.get('cat'))
        col = {'messages': 'messages', 'voice': 'voice_seconds',
               'balance': 'coins'}[cat]
        body = '\ufeff' + f'rank;uid;name;{col}\n'
        body += '\n'.join(';'.join(_csv_cell(c) for c in row)
                          for row in csv_rows(appmod.bot_instance, gid, cat))
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=leaderboards_{cat}_{gid}.csv')
        return resp
