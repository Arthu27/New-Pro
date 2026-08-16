# -*- coding: utf-8 -*-
"""Панель «Смены персонала» (идеи #126-130): недельное расписание дежурств.

Хранилище одно на двоих с ботом: GuildData('staff_shifts'), ключи
'shifts' (вечное расписание), 'settings' (канал напоминаний, пояс),
'_marks' (служебные метки напоминаний), пишет cogs/staff_shifts.py.

Всё поведение — его чистые функции: parse_weekday/parse_time_range,
try_add_shift (и его тексты ошибок), active_shift/next_shift («кто»),
week_table; снятие — как команда: удаление смены + чистка её меток.
Пояс — правило -12..14 с текстом кога, канал None — молчаливый режим.

«Сейчас/следующая» считаем по UTC как бот (tz_offset из настроек).
Чтение и CSV — mod+, назначения и настройки — admin+ (manage_guild).
"""
from datetime import datetime, timezone

from web.routes._common import (
    _log,
    render_template, session, request, jsonify, Response,
)
from web.routes.mod_control import validate_user_id, names_from_audit

from cogs import staff_shifts as SH

from db import GuildData

UTC = timezone.utc

_UNSET = object()  # «не трогать» в update_settings
DAYS = SH.WEEKDAYS_RU


def _db():
    return GuildData('staff_shifts')


def _shifts(gid):
    return _db().get(gid, 'shifts', {}) or {}


def _save_shifts(gid, shifts):
    _db().set(gid, 'shifts', shifts)


def _settings(gid):
    raw = _db().get(gid, 'settings', {}) or {}
    return {'channel_id': raw.get('channel_id'),
            'tz_offset': int(raw.get('tz_offset', SH.DEFAULT_TZ))}


def _save_settings(gid, settings):
    _db().set(gid, 'settings', settings)


def _marks(gid):
    return _db().get(gid, '_marks', {}) or {}


def _shift_len_minutes(shift):
    """Длительность с учётом переноса через полночь (как _shift_window)."""
    rng = SH.parse_time_range(f"{shift.get('start', '')}-{shift.get('end', '')}")
    if rng is None:
        return 0
    start, end = rng
    return end - start if end > start else end + 1440 - start


# ─────────────────────────────────────────────────────────────────────
# #126: таблица недели
# ─────────────────────────────────────────────────────────────────────
def shift_row(sid, shift, names=None):
    names = names or {}
    uid = str(shift.get('user_id') or '')
    wd = shift.get('weekday')
    return {
        'id': str(sid),
        'user_id': uid,
        'name': str(names.get(uid) or ''),
        'weekday': wd,
        'wd_label': DAYS[wd] if isinstance(wd, int) and 0 <= wd <= 6 else '?',
        'start': str(shift.get('start') or ''),
        'end': str(shift.get('end') or ''),
        'minutes': _shift_len_minutes(shift),
        'added_by': str(shift.get('added_by') or ''),
        'added_at': str(shift.get('added_at') or '')[:10],
    }


def week_rows(shifts, names=None):
    """7 слотов-строк; внутри дня сорт (start, end) — как в week_table кога."""
    by_day = {i: [] for i in range(7)}
    for sid, shift in (shifts or {}).items():
        wd = shift.get('weekday')
        if isinstance(wd, int) and 0 <= wd <= 6:
            row = shift_row(sid, shift, names)
            row['_sort'] = (row['start'], row['end'])
            by_day[wd].append(row)
    days = []
    for i in range(7):
        slots = sorted(by_day[i], key=lambda r: r['_sort'])
        for r in slots:
            r.pop('_sort', None)
        days.append({'weekday': i, 'label': DAYS[i], 'slots': slots})
    return days


def overview_stats(shifts, tz_offset, now=None):
    """Сводка: всего смен, часов в неделю, уникальных дежурных."""
    now = now or datetime.now(UTC)
    total_min = sum(_shift_len_minutes(s) for s in (shifts or {}).values())
    return {
        'shifts_total': len(shifts or {}),
        'minutes_week': total_min,
        'people': len({str(s.get('user_id')) for s in (shifts or {}).values()}),
        'tz_offset': tz_offset,
    }


# ─────────────────────────────────────────────────────────────────────
# #127: «кто сейчас» — /дежурства кто
# ─────────────────────────────────────────────────────────────────────
def duty_now(shifts, tz_offset, names=None, now=None):
    """Активная и ближайшая — те же active_shift/next_shift кога."""
    now = now or datetime.now(UTC)
    names = names or {}
    shift_list = list((shifts or {}).values())
    active = SH.active_shift(shift_list, now, tz_offset)
    nxt = SH.next_shift(shift_list, now, tz_offset)
    out = {'active': None, 'next': None, 'tz_offset': tz_offset}
    if active:
        shift, start, end = active
        row = shift_row('' , shift, names)
        row['left_s'] = max(0, int((end - now).total_seconds()))
        out['active'] = row
    if nxt:
        shift, start = nxt
        row = shift_row('', shift, names)
        row['wait_s'] = max(0, int((start - now).total_seconds()))
        out['next'] = row
    return out


# ─────────────────────────────────────────────────────────────────────
# #128: назначить / снять
# ─────────────────────────────────────────────────────────────────────
def add_shift(gid, user_ref, weekday_text, time_range, added_by):
    """Назначить смену 1:1 с /дежурства назначить (тексты ошибок те же)."""
    ok, err, uid = validate_user_id(user_ref)
    if not ok:
        return False, err, None
    wd = SH.parse_weekday(weekday_text)
    if wd is None:
        days = ', '.join(DAYS)
        return False, f'Не понял день «{weekday_text}». Пиши: {days} (или полностью).', None
    shifts = _shifts(gid)
    sid, err = SH.try_add_shift(shifts, int(uid), wd, str(time_range or ''),
                                added_by=added_by)
    if err:
        return False, err, None
    _save_shifts(gid, shifts)
    sh = shifts[sid]
    return True, '', {
        'id': sid, 'row': shift_row(sid, sh),
        'message': f"Смена добавлена: {DAYS[wd]} {sh['start']}–{sh['end']} (id {sid}).",
    }


def remove_shift(gid, shift_id):
    """Снять смену как /дежурства снять: запись и её напоминательные метки."""
    shifts = _shifts(gid)
    sid = str(shift_id or '').strip()
    shift = shifts.pop(sid, None)
    if not shift:
        return False, (f'Смена `{sid}` не найдена. Список id — в '
                       f'`/дежурства` (таблица недели).'), None
    _save_shifts(gid, shifts)
    marks = _marks(gid)
    if sid in marks:
        marks.pop(sid, None)
        _db().set(gid, '_marks', marks)
    return True, '', {
        'message': f"Смена снята: {DAYS[shift['weekday']]} "
                   f"{shift['start']}–{shift['end']} (id {sid}).",
    }


# ─────────────────────────────────────────────────────────────────────
# #129: настройки
# ─────────────────────────────────────────────────────────────────────
def update_settings(gid, channel_id=_UNSET, tz_offset=_UNSET):
    """Канал/пояс напоминаний. Пояс -12..14 словами кога."""
    raw = _db().get(gid, 'settings', {}) or {}
    if channel_id is not _UNSET:
        if channel_id in (None, '', 'null'):
            raw['channel_id'] = None
        else:
            try:
                raw['channel_id'] = int(str(channel_id).strip())
            except (TypeError, ValueError):
                return False, 'Некорректный ID канала', None
    if tz_offset is not _UNSET:
        try:
            offset = int(str(tz_offset).strip())
        except (TypeError, ValueError):
            return False, 'Пояс: от -12 до +14 (МСК = 3).', None
        if not (-12 <= offset <= 14):
            return False, 'Пояс: от -12 до +14 (МСК = 3).', None
        raw['tz_offset'] = offset
    _save_settings(gid, raw)
    return True, '', _settings(gid)


# ─────────────────────────────────────────────────────────────────────
# #130: нагрузка и выгрузка
# ─────────────────────────────────────────────────────────────────────
def workload(shifts, names=None):
    """Часов в неделю на дежурного — честно посчитано из данных кога."""
    acc = {}
    for shift in (shifts or {}).values():
        uid = str(shift.get('user_id') or '')
        slot = acc.setdefault(uid, {'user_id': uid, 'shifts': 0, 'minutes': 0})
        slot['shifts'] += 1
        slot['minutes'] += _shift_len_minutes(shift)
    names = names or {}
    rows = list(acc.values())
    for row in rows:
        row['name'] = str(names.get(row['user_id']) or '')
        row['hours'] = round(row['minutes'] / 60, 1)
    rows.sort(key=lambda r: (-r['minutes'], r['user_id']))
    return rows


def shifts_csv_rows(shifts, names=None):
    rows = []
    for day in week_rows(shifts, names):
        for slot in day['slots']:
            rows.append((day['label'], slot['start'], slot['end'], slot['user_id'],
                         slot['name'] or '—', f"{slot['minutes'] / 60:.1f}".replace('.', ','),
                         slot['id'], slot['added_by']))
    return rows


CSV_HEADER = 'day;start;end;user_id;name;hours;shift_id;added_by'


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
            _log.debug('shifts: уведомление не ушло: %s', _ex)

    @app.route('/staff-shifts')
    @login_required
    @role_required('mod')
    def shifts_page():
        return render_template('staff_shifts.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id(),
                               can_edit=session.get('role') in ('admin', 'owner'),
                               days=DAYS)

    @app.route('/api/guild/<gid>/shiftboard/overview')
    @login_required
    @role_required('mod')
    def api_shifts_overview(gid):
        shifts = _shifts(gid)
        settings = _settings(gid)
        names = names_from_audit(gid)
        return jsonify({
            'success': True,
            'stats': overview_stats(shifts, settings['tz_offset']),
            'week': week_rows(shifts, names),
            'duty': duty_now(shifts, settings['tz_offset'], names),
            'workload': workload(shifts, names),
            'settings': settings,
            'week_table_text': SH.week_table(list(shifts.values())),
            'can_edit': session.get('role') in ('admin', 'owner'),
        })

    @app.route('/api/guild/<gid>/shiftboard/add', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_shifts_add(gid):
        data = request.get_json(silent=True) or {}
        ok, err, payload = add_shift(gid, data.get('user_id'), data.get('weekday'),
                                     data.get('time'),
                                     f"panel:{session.get('username', '?')}")
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        _notify(f"Смена добавлена ({payload['id']})")
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/shiftboard/remove', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_shifts_remove(gid):
        data = request.get_json(silent=True) or {}
        ok, err, payload = remove_shift(gid, data.get('shift_id'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 404
        _notify('Смена снята')
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/shiftboard/settings', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_shifts_settings(gid):
        data = request.get_json(silent=True) or {}
        kwargs = {}
        if 'channel_id' in data:
            kwargs['channel_id'] = data['channel_id']
        if 'tz_offset' in data:
            kwargs['tz_offset'] = data['tz_offset']
        ok, err, settings = update_settings(gid, **kwargs)
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        _notify('Смены: настройки обновлены')
        return jsonify({'success': True, 'settings': settings})

    @app.route('/api/guild/<gid>/shiftboard/export.csv')
    @login_required
    @role_required('mod')
    def api_shifts_export(gid):
        names = names_from_audit(gid)
        rows = shifts_csv_rows(_shifts(gid), names)
        body = '\ufeff' + CSV_HEADER + '\n'
        body += '\n'.join(';'.join(_csv_cell(c) for c in row) for row in rows) + '\n'
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=staff_shifts_{gid}.csv')
        return resp
