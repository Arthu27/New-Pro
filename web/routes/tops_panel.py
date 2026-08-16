# -*- coding: utf-8 -*-
"""Панель «Топ сервера» (идеи #81-85): три категории лидерборд-карточки
(сообщения / войс / монеты), сводка, выгрузка, диагностика источников.

Агрегации и строки отображения повторяют _get_lb_data кога
cogs/leaderboard.py 1:1:
  messages — data/leaderboard_<gid>.json {'messages': {uid: count}}
             «1 500 СООБЩЕНИЙ» (запятые → пробелы)
  voice    — voice_tracker.voice_view(gid) → total_seconds,
             «Hч Mм В ВОЙСЕ» (до часа — «Mм В ВОЙСЕ»), имя из записи
  balance  — data/economy_<gid>.json balance + bank, «1 500 МОНЕТ»
Ког рисует топ-7 на карточке; панель отдаёт топ-25 таблицей и полный CSV.
Битое значение валит категорию у кога целиком (try/except вокруг) —
панель показывает состояние 'error', а не молчаливый ноль.

Имена: участник через живого бота → аудит-журнал → «ID xxxxxx» (как ког).

Страница читаемая — mod+, мутаций нет.
"""
import json
import os
from datetime import datetime

from web.routes._common import (
    _log,
    render_template, session, request, jsonify, Response,
)

from web.routes.mod_control import names_from_audit

PANEL_LIMIT = 25        # глубина таблицы (карточка кога — 7)
STALE_DAYS = 2          # источник старше — подсвечиваем «устарел»

CATEGORIES = {
    'messages': {'label': 'Сообщения', 'icon': 'fa-message'},
    'voice': {'label': 'Войс', 'icon': 'fa-microphone'},
    'balance': {'label': 'Монеты', 'icon': 'fa-coins'},
}


def _lb_path(gid):
    return f'data/leaderboard_{gid}.json'


def _econ_path(gid):
    return f'data/economy_{gid}.json'


def _fallback_name(uid):
    return f'ID {str(uid)[:6]}'   # как у кога


def messages_rows(msgs, resolve=None, limit=PANEL_LIMIT):
    """(rows, state). Агрегация 1:1: sorted по int(count), битое значение
    валит всю категорию — как try/except кога."""
    rows = []
    try:
        ordered = sorted((msgs or {}).items(),
                         key=lambda kv: int(kv[1]), reverse=True)
        for uid, count in ordered[:max(1, int(limit))]:
            count = int(count)
            name = resolve(uid) if resolve else None
            rows.append({
                'user_id': str(uid),
                'name': str(name) if name else _fallback_name(uid),
                'value': count,
                'display': f"{count:,} СООБЩЕНИЙ".replace(',', ' '),
            })
    except (TypeError, ValueError) as ex:
        _log.debug('tops messages: %s', ex)
        return [], 'error'
    for rank, row in enumerate(rows, 1):
        row['rank'] = rank
    return rows, ('ok' if rows else 'empty')


def voice_rows(users, limit=PANEL_LIMIT):
    """(rows, state). Имя — из записи войс-трекера (карточка так же),
    значение — секунды, экран как у кога."""
    rows = []
    try:
        ordered = sorted(
            (users or {}).items(),
            key=lambda kv: kv[1].get('total_seconds', 0)
            if isinstance(kv[1], dict) else int(kv[1]),
            reverse=True)
        for uid, rec in ordered[:max(1, int(limit))]:
            secs = (rec.get('total_seconds', 0)
                    if isinstance(rec, dict) else int(rec))
            secs = int(secs)
            name = (str(rec.get('name') or '') if isinstance(rec, dict)
                    else '') or _fallback_name(uid)
            hours, minutes = divmod(secs // 60, 60)
            rows.append({
                'user_id': str(uid),
                'name': name,
                'value': secs,
                'display': (f'{hours}ч {minutes}м В ВОЙСЕ' if hours
                            else f'{minutes}м В ВОЙСЕ'),
            })
    except (TypeError, ValueError, AttributeError) as ex:
        _log.debug('tops voice: %s', ex)
        return [], 'error'
    for rank, row in enumerate(rows, 1):
        row['rank'] = rank
    return rows, ('ok' if rows else 'empty')


def balance_rows(econ, resolve=None, limit=PANEL_LIMIT):
    """(rows, state). balance + bank, не-словари пропускаются (как у кога)."""
    rows = []
    try:
        ordered = sorted(
            [(u, d.get('balance', 0) + d.get('bank', 0))
             for u, d in (econ or {}).items() if isinstance(d, dict)],
            key=lambda kv: kv[1], reverse=True)
        for uid, coins in ordered[:max(1, int(limit))]:
            name = resolve(uid) if resolve else None
            rows.append({
                'user_id': str(uid),
                'name': str(name) if name else _fallback_name(uid),
                'value': coins,
                'display': f"{coins:,} МОНЕТ".replace(',', ' '),
            })
    except (TypeError, ValueError) as ex:
        _log.debug('tops balance: %s', ex)
        return [], 'error'
    for rank, row in enumerate(rows, 1):
        row['rank'] = rank
    return rows, ('ok' if rows else 'empty')


def load_msgs(gid):
    """{'messages': {...}} из файла кога; битый — пусто (как у кога)."""
    path = _lb_path(gid)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
    except Exception as ex:
        _log.debug('tops: %s: %s', path, ex)
        return {}
    msgs = data.get('messages', {}) if isinstance(data, dict) else {}
    return msgs if isinstance(msgs, dict) else {}


def load_econ(gid):
    path = _econ_path(gid)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
    except Exception as ex:
        _log.debug('tops: %s: %s', path, ex)
        return {}
    return data if isinstance(data, dict) else {}


def load_voice_users(gid):
    """Пользователи войс-трекера тем же voice_view, что и ког."""
    try:
        from cogs.voice_tracker import voice_view
        return voice_view(int(gid)).get('users', {}) or {}
    except Exception as ex:
        _log.debug('tops: voice_view(%s): %s', gid, ex)
        return {}


def _loose_int(value):
    """int без падения: мусор — None (вызывающий пропускает)."""
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def board_summary(msgs, users, econ):
    """Сводка для чипов: суммы по трём категориям без падения на мусоре."""
    messages_total = sum(n for n in (_loose_int(v) for v in (msgs or {}).values())
                         if n is not None)
    voice_seconds = 0
    for rec in (users or {}).values():
        n = _loose_int(rec.get('total_seconds', 0)
                       if isinstance(rec, dict) else rec)
        voice_seconds += n if n is not None else 0
    coins = 0
    for d in (econ or {}).values():
        if not isinstance(d, dict):
            continue
        balance = _loose_int(d.get('balance', 0))
        bank = _loose_int(d.get('bank', 0))
        coins += (balance or 0) + (bank or 0)
    return {
        'messages_total': messages_total,
        'voice_seconds_total': voice_seconds,
        'coins_total': coins,
        'people_messages': len(msgs or {}),
        'people_voice': len(users or {}),
        'people_balance': len([d for d in (econ or {}).values()
                               if isinstance(d, dict)]),
    }


def source_freshness(gid, now=None):
    """Возраст файлов-источников: чипы «свежо/устарело/нет файла»."""
    now = now or datetime.now()
    out = {}
    for key, path in (('messages', _lb_path(gid)), ('balance', _econ_path(gid))):
        if not os.path.exists(path):
            out[key] = {'state': 'missing', 'age_days': None}
            continue
        try:
            age = (now - datetime.fromtimestamp(os.path.getmtime(path))).days
        except OSError as ex:
            _log.debug('tops: mtime %s: %s', path, ex)
            out[key] = {'state': 'missing', 'age_days': None}
            continue
        out[key] = {'state': 'stale' if age > STALE_DAYS else 'fresh',
                    'age_days': age}
    out['voice'] = {'state': 'live', 'age_days': 0}   # SQLite, пишется живьём
    return out


def _resolver(bot, gid, names):
    """Имя: участник через бота → аудит → None (дальше fallback кога)."""
    guild = None
    if bot:
        try:
            guild = bot.get_guild(int(gid))
        except Exception as _ex:
            _log.debug('tops: get_guild(%s): %s', gid, _ex)

    def resolve(uid):
        if guild is not None:
            member = None
            try:
                member = guild.get_member(int(uid))
            except Exception as _ex:
                _log.debug('tops: get_member(%s): %s', uid, _ex)
            if member is not None:
                display = getattr(member, 'display_name', None)
                if display:
                    return str(display)
        return str(names.get(str(uid)) or '') or None

    return resolve


# ─────────────────────────────────────────────────────────────────────
# Маршруты
# ─────────────────────────────────────────────────────────────────────
def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _category_rows(gid, category, limit):
        import web.app as appmod
        names = names_from_audit(gid)
        resolve = _resolver(appmod.bot_instance, gid, names)
        if category == 'messages':
            return messages_rows(load_msgs(gid), resolve=resolve, limit=limit)
        if category == 'voice':
            return voice_rows(load_voice_users(gid), limit=limit)
        return balance_rows(load_econ(gid), resolve=resolve, limit=limit)

    @app.route('/tops')
    @login_required
    @role_required('mod')
    def tops_page():
        return render_template('tops.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/tops/overview')
    @login_required
    @role_required('mod')
    def api_tops_overview(gid):
        category = (request.args.get('category') or 'messages').strip()
        if category not in CATEGORIES:
            return jsonify({'success': False,
                            'error': 'Нет такой категории'}), 400
        msgs = load_msgs(gid)
        users = load_voice_users(gid)
        econ = load_econ(gid)
        rows, state = _category_rows(gid, category, PANEL_LIMIT)
        return jsonify({
            'success': True,
            'category': category,
            'categories': {k: v['label'] for k, v in CATEGORIES.items()},
            'rows': rows,
            'state': state,
            'summary': board_summary(msgs, users, econ),
            'freshness': source_freshness(gid),
        })

    @app.route('/api/guild/<gid>/tops/<category>.csv')
    @login_required
    @role_required('mod')
    def api_tops_csv(gid, category):
        if category not in CATEGORIES:
            return jsonify({'success': False,
                            'error': 'Нет такой категории'}), 404
        rows, _state = _category_rows(gid, category, 100000)
        lines = ['rank;user_id;name;display;value']
        for row in rows:
            name = str(row['name']).replace(';', ',')
            lines.append('{};{};{};{};{}'.format(
                row['rank'], row['user_id'], name,
                row['display'], row['value']))
        body = '﻿' + '\n'.join(lines) + '\n'
        return Response(
            body, mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition':
                     'attachment; filename="tops_%s_%s.csv"' % (category, gid)})
