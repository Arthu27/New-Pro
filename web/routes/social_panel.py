# -*- coding: utf-8 -*-
"""Панель «События и поиск игроков» (идеи #61-65): афиша событий с
составами, доска матчмейкинга, выгрузка участников, уборка старья.

Хранилище — файлы кога cogs/social.py (через тот же json_store):
    data/events_{gid}.json       {eid: {title, description, date (iso, UTC),
                                        max_participants (0 — без лимита),
                                        participants [uid], created_by,
                                        channel_id, message_id, reminded}}
    data/matchmaking_{gid}.json  {mid: {game, max_players (2..20), players [uid],
                                        note, created_by, created_at (iso)}}
Правила повторяют кога 1:1: предстоящие события по дате (как
/activity-list), активный поиск = моложе двух часов и состав не полон
(как /game-list).

Создание намеренно остаётся за Discord (/activity, /game-find): там запись
сразу получает эмбед с кнопкой «Участвую». Панель — витрина и уборка.

Чтение и выгрузка — mod+, удаление событий и поисков — admin+.
"""
import os
from datetime import datetime, timezone

from web.routes._common import (
    _log,
    render_template, session, request, jsonify, Response,
)

from web.routes.mod_control import names_from_audit

from json_store import load_json as _js_load, save_json as _js_save

MATCH_ACTIVE_S = 7200   # как в /game-list кога: поиск живёт два часа


def _events_path(gid):
    return f'data/events_{gid}.json'


def _matches_path(gid):
    return f'data/matchmaking_{gid}.json'


def load_map(gid, kind):
    """Тот же файл, что читает ког; не-словарь отбраковываем."""
    path = _events_path(gid) if kind == 'events' else _matches_path(gid)
    data = _js_load(path, {}, log=_log)
    if not isinstance(data, dict):
        return {}
    return data


def save_map(gid, kind, data):
    path = _events_path(gid) if kind == 'events' else _matches_path(gid)
    os.makedirs('data', exist_ok=True)
    _js_save(path, data, log=_log)


def _parse_dt(value):
    """fromisoformat кога; наивную дату считаем UTC, битую — пропускаем."""
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as ex:
        _log.debug('social_panel: дата %r не читается: %s', value, ex)
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _as_count(value):
    """Лимит мест числом; кривое значение — без лимита (0), как пустое."""
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError) as ex:
        _log.debug('social_panel: лимит %r не число: %s', value, ex)
        return 0


def event_rows(data, now=None):
    """Афиша: предстоящие по дате (как /activity-list), минувшие — следом,
    свежие первыми. Битые записи ког ронял бы список — панель пропускает."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for eid, ev in (data or {}).items():
        if not isinstance(ev, dict):
            continue
        dt = _parse_dt(ev.get('date'))
        if dt is None:
            continue
        participants = [str(u) for u in (ev.get('participants') or [])]
        max_p = _as_count(ev.get('max_participants'))
        rows.append({
            'id': str(eid),
            'title': str(ev.get('title') or 'Без названия'),
            'description': str(ev.get('description') or ''),
            'date': dt.isoformat(timespec='minutes'),
            'past': dt <= now,
            'participants': participants,
            'count': len(participants),
            'max_participants': max_p,
            'spots_left': (max_p - len(participants)) if max_p > 0 else None,
            'full': max_p > 0 and len(participants) >= max_p,
            'reminded': bool(ev.get('reminded')),
            'created_by': str(ev.get('created_by') or ''),
            'channel_id': str(ev.get('channel_id') or ''),
        })
    upcoming = sorted((r for r in rows if not r['past']), key=lambda r: r['date'])
    past = sorted((r for r in rows if r['past']),
                  key=lambda r: r['date'], reverse=True)
    return upcoming + past


def match_rows(data, now=None):
    """Доска поисков: активность 1:1 с /game-list (моложе MATCH_ACTIVE_S
    и состав не полон). Активные первыми, внутри — свежие сверху."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for mid, m in (data or {}).items():
        if not isinstance(m, dict):
            continue
        created = _parse_dt(m.get('created_at'))
        if created is None:
            continue
        players = [str(u) for u in (m.get('players') or [])]
        max_p = _as_count(m.get('max_players'))
        age_s = (now - created).total_seconds()
        rows.append({
            'id': str(mid),
            'game': str(m.get('game') or 'Игра'),
            'players': players,
            'count': len(players),
            'max_players': max_p,
            'note': str(m.get('note') or ''),
            'created_by': str(m.get('created_by') or ''),
            'created_at': created.isoformat(timespec='minutes'),
            'age_min': int(age_s // 60),
            'full': max_p > 0 and len(players) >= max_p,
            'active': age_s < MATCH_ACTIVE_S and len(players) < max_p,
        })
    active = sorted((r for r in rows if r['active']),
                    key=lambda r: r['created_at'], reverse=True)
    rest = sorted((r for r in rows if not r['active']),
                  key=lambda r: r['created_at'], reverse=True)
    return active + rest


def board_stats(events, matches):
    """Чипы сводки: предстоит событий, записано участников, живых поисков,
    ищут игроков (в активных поисках)."""
    upcoming = [e for e in events if not e['past']]
    live = [m for m in matches if m['active']]
    return {
        'events_total': len(events),
        'events_upcoming': len(upcoming),
        'participants': sum(e['count'] for e in upcoming),
        'matches_active': len(live),
        'seekers': sum(m['count'] for m in live),
    }


# ─────────────────────────────────────────────────────────────────────
# Маршруты
# ─────────────────────────────────────────────────────────────────────
def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _notify(title):
        from web.routes._common import _fire_panel_notification
        try:
            _fire_panel_notification(
                'social', title,
                f'Через панель ({session.get("username", "?")})')
        except Exception as _ex:
            _log.debug('social: уведомление не ушло: %s', _ex)

    @app.route('/social')
    @login_required
    @role_required('mod')
    def social_page():
        return render_template('social.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/social/overview')
    @login_required
    @role_required('mod')
    def api_social_overview(gid):
        names = names_from_audit(gid)
        events = event_rows(load_map(gid, 'events'))
        matches = match_rows(load_map(gid, 'matchmaking'))
        for e in events:
            e['created_by_name'] = str(names.get(e['created_by']) or '')
        for m in matches:
            m['players_named'] = [
                {'user_id': uid, 'name': str(names.get(uid) or '')}
                for uid in m['players']]
            m['created_by_name'] = str(names.get(m['created_by']) or '')
        return jsonify({
            'success': True,
            'events': events,
            'matches': matches,
            'stats': board_stats(events, matches),
            'can_edit': session.get('role') in ('admin', 'owner'),
        })

    @app.route('/api/guild/<gid>/social/events/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_social_event_delete(gid):
        data = request.get_json(silent=True) or {}
        event_id = str(data.get('event_id') or '').strip()
        store = load_map(gid, 'events')
        if not event_id or event_id not in store:
            return jsonify({'success': False,
                            'error': 'Событие не найдено.'}), 404
        removed = store.pop(event_id)
        save_map(gid, 'events', store)
        _notify(f'Событие «{removed.get("title") or event_id}» удалено')
        return jsonify({'success': True, 'event_id': event_id,
                        'removed': {'title': removed.get('title'),
                                    'date': removed.get('date')}})

    @app.route('/api/guild/<gid>/social/matches/close', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_social_match_close(gid):
        data = request.get_json(silent=True) or {}
        match_id = str(data.get('match_id') or '').strip()
        store = load_map(gid, 'matchmaking')
        if not match_id or match_id not in store:
            return jsonify({'success': False,
                            'error': 'Поиск не найден.'}), 404
        removed = store.pop(match_id)
        save_map(gid, 'matchmaking', store)
        _notify(f'Поиск игроков «{removed.get("game") or match_id}» закрыт')
        return jsonify({'success': True, 'match_id': match_id,
                        'removed': {'game': removed.get('game')}})

    @app.route('/api/guild/<gid>/social/events/<event_id>/participants.csv')
    @login_required
    @role_required('mod')
    def api_social_event_csv(gid, event_id):
        store = load_map(gid, 'events')
        event = store.get(event_id)
        if not isinstance(event, dict):
            return jsonify({'success': False,
                            'error': 'Событие не найдено.'}), 404
        names = names_from_audit(gid)
        lines = ['user_id;name']
        for uid in (event.get('participants') or []):
            uid = str(uid)
            name = str(names.get(uid) or uid).replace(';', ',')
            lines.append(f'{uid};{name}')
        body = '\ufeff' + '\n'.join(lines) + '\n'
        return Response(
            body, mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition':
                     'attachment; filename="event_%s_%s.csv"' % (event_id, gid)})
