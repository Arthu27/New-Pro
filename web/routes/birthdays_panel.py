# -*- coding: utf-8 -*-
"""Панель «Дни рождения» (идеи #56-60): календарь ближайших дат, запись
и удаление дат, настройки поздравлений, превью эмбеда, выгрузка в CSV.

Хранилище — файлы кога cogs/birthday.py:
    data/birthdays_<gid>.json          {uid: {'date': 'MM-DD', 'name': str,
                                             'year': int?, 'celebrated': 'YYYY'?}}
    data/birthday_settings_<gid>.json  {'channel_id', 'role_id', 'message',
                                        'gift_coins'?}
Порядок «ближайших» (num = месяц*100 + день, перенос года +1200) и
валидация даты повторяют команды бота /birthdays и /birthday 1:1 —
панель показывает ровно то, что увидят в Discord. Тексты ошибок — как
у бота, без эмодзи (политика панели).

Чтение, превью и выгрузка — mod+, запись дат и настройки — admin+.
"""
import json
import os
from datetime import datetime, timezone

from web.routes._common import (
    _log,
    render_template, session, request, jsonify, Response,
)

from web.routes.mod_control import validate_user_id, names_from_audit

# Дефолт ровно как в cogs/birthday.py get_settings (эмодзи — эскейпами,
# чтобы исходник панели оставался чистым).
DEFAULT_MESSAGE = ('\U0001F382 Сегодня день рождения у {user}! '
                   'Поздравляем! \U0001F389')
DEFAULT_SETTINGS = {'channel_id': None, 'role_id': None,
                    'message': DEFAULT_MESSAGE}

YEAR_MIN = 1900
MAX_MESSAGE = 200
MAX_GIFT = 100000
SAMPLE_USER = '@Мария'   # пример участника для превью


class _SafeDict(dict):
    """format_map без падения на неизвестных плейсхолдерах (как welcome_pro)."""

    def __missing__(self, key):
        return '{' + key + '}'


def _as_int(value):
    """Строгое целое: bool и дробные с хвостом отбраковываем."""
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _data_path(gid):
    return f'data/birthdays_{gid}.json'


def _settings_path(gid):
    return f'data/birthday_settings_{gid}.json'


def load_birthdays(gid):
    """Тот же файл, что читает ког: {uid: {date, name, year?, celebrated?}}."""
    path = _data_path(gid)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
    except Exception as ex:
        _log.debug('load_birthdays(%s): %s', gid, ex)
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_birthdays(gid, data):
    os.makedirs('data', exist_ok=True)
    with open(_data_path(gid), 'w', encoding='utf-8') as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)


def load_settings_stored(gid):
    """Как get_settings кога: нет файла — дефолты, есть — его содержимое."""
    path = _settings_path(gid)
    if not os.path.exists(path):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(path, 'r', encoding='utf-8') as fp:
            stored = json.load(fp)
    except Exception as ex:
        _log.debug('load_settings_stored(%s): %s', gid, ex)
        return dict(DEFAULT_SETTINGS)
    if not isinstance(stored, dict):
        return dict(DEFAULT_SETTINGS)
    return stored


def save_settings(gid, settings):
    os.makedirs('data', exist_ok=True)
    with open(_settings_path(gid), 'w', encoding='utf-8') as fp:
        json.dump(settings, fp, indent=2, ensure_ascii=False)


def public_settings(stored):
    """Вид настроек для панели: дефолты + файл, gift_coins по умолчанию 0.

    Неизвестные ключи файла сохраняются (ког и будущие версии ими владеют).
    """
    merged = dict(DEFAULT_SETTINGS)
    if isinstance(stored, dict):
        merged.update(stored)
    gift = merged.get('gift_coins', 0)
    gift = _as_int(gift)
    merged['gift_coins'] = gift if gift is not None and gift >= 0 else 0
    merged['channel_set'] = bool(merged.get('channel_id'))
    merged['role_set'] = bool(merged.get('role_id'))
    return merged


def schedule(data, now=None):
    """Ближайшие дни рождения — тот же алгоритм, что у /birthdays бота.

    num = месяц*100 + день; diff = num - сегодня; ушедшим в минус +1200
    (грубый перенос года кога — повторяем, чтобы числа совпали с Discord).
    Битые записи ког тихо пропускает — панель тоже, но с подписью в лог.
    """
    now = now or datetime.now(timezone.utc)
    today_num = now.month * 100 + now.day
    entries = []
    for uid, info in (data or {}).items():
        if not isinstance(info, dict):
            continue
        try:
            month, day = map(int, str(info.get('date') or '').split('-'))
            num = month * 100 + day
            diff = num - today_num
            if diff < 0:
                diff += 1200
        except (TypeError, ValueError, AttributeError) as ex:
            _log.debug('schedule(%s): %s', uid, ex)
            continue
        raw_year = info.get('year')
        age = None
        if isinstance(raw_year, int) and not isinstance(raw_year, bool):
            age = now.year - raw_year
        entries.append({
            'user_id': str(uid),
            'name': str(info.get('name') or uid),
            'date': str(info.get('date') or ''),
            'day': day,
            'month': month,
            'year': raw_year if age is not None else None,
            'age': age,
            'days_until': diff,
            'today': diff == 0,
            'celebrated': str(info.get('celebrated') or ''),
            'celebrated_this_year': info.get('celebrated') == str(now.year),
        })
    entries.sort(key=lambda e: (e['days_until'], e['day'], e['month'],
                                e['name'], e['user_id']))
    return entries


def calendar_stats(entries):
    """Сводка календаря для чипов: всего, сегодня, на неделе, поздравлено."""
    return {
        'total': len(entries),
        'today': sum(1 for e in entries if e['today']),
        'week': sum(1 for e in entries if 0 < e['days_until'] <= 7),
        'celebrated_year': sum(1 for e in entries if e['celebrated_this_year']),
        'next': entries[0] if entries else None,
    }


def validate_entry(day, month, year, now=None):
    """Правило /birthday бота: 1<=день<=31 и 1<=месяц<=12, иначе
    'Неверная дата!'. Год у бота свободный int — панель сужает до
    осмысленного [YEAR_MIN; текущий] (иначе возраст выйдет отрицательным).
    -> (updates | None, err)
    """
    now = now or datetime.now(timezone.utc)
    d = _as_int(day)
    m = _as_int(month)
    if d is None or m is None or not (1 <= d <= 31 and 1 <= m <= 12):
        return None, 'Неверная дата!'
    y = None
    if year not in (None, ''):
        y = _as_int(year)
        if y is None or not (YEAR_MIN <= y <= now.year):
            return None, f'Год — от {YEAR_MIN} до {now.year}'
    return {'day': d, 'month': m, 'year': y}, ''


def build_entry(valid, name):
    """Запись формата кога set_birthday: год хранится, только если задан."""
    entry = {'date': f"{valid['month']:02d}-{valid['day']:02d}",
             'name': str(name)}
    if valid.get('year') is not None:
        entry['year'] = valid['year']
    return entry


def greeting_view(stored, now=None):
    """Структура поздравления, которое реально пошлёт ког (check_birthdays):
    ansi-шапка, строка с упоминанием и возрастом, поля Дата/Возраст,
    выдача роли и подарок в экономику. Плюс сохранённый шаблон message
    (заготовка: ког пока шлёт фирменный эмбед и не читает его).
    """
    now = now or datetime.now(timezone.utc)
    merged = public_settings(stored)
    age = 20
    sample_date = f'{now.month:02d}-{now.day:02d}'
    return {
        'ready': merged['channel_set'],
        'channel_id': str(merged.get('channel_id') or ''),
        'role_set': merged['role_set'],
        'gift_coins': merged['gift_coins'],
        'header': 'С ДНЁМ РОЖДЕНИЯ!',
        'line': f'У {SAMPLE_USER} сегодня день рождения ({age} лет)!',
        'invite': 'Все ждём твоих поздравлений!',
        'fields': [{'name': 'Дата', 'value': sample_date.replace('-', '/')},
                   {'name': 'Возраст', 'value': str(age)}],
        'template': str(merged.get('message') or '').format_map(
            _SafeDict(user=SAMPLE_USER)),
        'sample': True,
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
                'birthdays', title,
                f'Через панель ({session.get("username", "?")})')
        except Exception as _ex:
            _log.debug('birthdays: уведомление не ушло: %s', _ex)

    @app.route('/birthdays')
    @login_required
    @role_required('mod')
    def birthdays_page():
        return render_template('birthdays.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/birthdays/overview')
    @login_required
    @role_required('mod')
    def api_birthdays_overview(gid):
        names = names_from_audit(gid)
        entries = schedule(load_birthdays(gid))
        for e in entries:
            e['name'] = str(names.get(e['user_id']) or e['name'])
        return jsonify({
            'success': True,
            'entries': entries,
            'stats': calendar_stats(entries),
            'settings': public_settings(load_settings_stored(gid)),
            'can_edit': session.get('role') in ('admin', 'owner'),
        })

    @app.route('/api/guild/<gid>/birthdays/set', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_birthdays_set(gid):
        data = request.get_json(silent=True) or {}
        ok, err, uid = validate_user_id(data.get('user_id'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        valid, err = validate_entry(data.get('day'), data.get('month'),
                                    data.get('year'))
        if not valid:
            return jsonify({'success': False, 'error': err}), 400
        store = load_birthdays(gid)
        name = names_from_audit(gid).get(uid) or uid
        entry = build_entry(valid, name)
        store[uid] = entry
        save_birthdays(gid, store)
        _notify(f'День рождения: {uid} записан на '
                f'{valid["day"]:02d}.{valid["month"]:02d}')
        return jsonify({'success': True, 'user_id': uid, 'entry': entry})

    @app.route('/api/guild/<gid>/birthdays/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_birthdays_delete(gid):
        data = request.get_json(silent=True) or {}
        ok, err, uid = validate_user_id(data.get('user_id'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        store = load_birthdays(gid)
        if uid not in store:
            return jsonify({'success': False,
                            'error': 'Запись о дне рождения не найдена.'}), 404
        removed = store.pop(uid)
        save_birthdays(gid, store)
        _notify(f'День рождения: запись {uid} удалена')
        return jsonify({'success': True, 'user_id': uid, 'removed': removed})

    @app.route('/api/guild/<gid>/birthdays/settings', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_birthdays_settings(gid):
        data = request.get_json(silent=True) or {}
        stored = load_settings_stored(gid)
        if 'channel_id' in data:
            value = str(data.get('channel_id') or '').strip()
            if value and not value.isdigit():
                return jsonify({'success': False,
                                'error': 'ID канала — только цифры'}), 400
            stored['channel_id'] = value or None
        if 'role_id' in data:
            value = str(data.get('role_id') or '').strip()
            if value and not value.isdigit():
                return jsonify({'success': False,
                                'error': 'ID роли — только цифры'}), 400
            stored['role_id'] = value or None
        if 'gift_coins' in data:
            gift = _as_int(data.get('gift_coins'))
            if gift is None or not (0 <= gift <= MAX_GIFT):
                return jsonify({'success': False,
                                'error': 'Подарок — целое число '
                                         f'от 0 до {MAX_GIFT}'}), 400
            stored['gift_coins'] = gift
        if 'message' in data:
            message = str(data.get('message') or '').strip()
            if not (1 <= len(message) <= MAX_MESSAGE):
                return jsonify({'success': False,
                                'error': 'Сообщение — от 1 до '
                                         f'{MAX_MESSAGE} символов'}), 400
            stored['message'] = message
        save_settings(gid, stored)
        _notify('Дни рождения: настройки поздравлений обновлены')
        return jsonify({'success': True, 'settings': public_settings(stored)})

    @app.route('/api/guild/<gid>/birthdays/preview', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_birthdays_preview(gid):
        return jsonify({'success': True,
                        'preview': greeting_view(load_settings_stored(gid))})

    @app.route('/api/guild/<gid>/birthdays/export.csv')
    @login_required
    @role_required('mod')
    def api_birthdays_export(gid):
        names = names_from_audit(gid)
        entries = schedule(load_birthdays(gid))
        lines = ['user_id;name;date;year;age;days_until;celebrated']
        for e in entries:
            name = str(names.get(e['user_id']) or e['name']).replace(';', ',')
            lines.append('{};{};{};{};{};{};{}'.format(
                e['user_id'], name, e['date'],
                e['year'] if e['year'] is not None else '',
                e['age'] if e['age'] is not None else '',
                e['days_until'], e['celebrated']))
        body = '\ufeff' + '\n'.join(lines) + '\n'
        return Response(body, mimetype='text/csv; charset=utf-8',
                        headers={'Content-Disposition':
                                 'attachment; filename="birthdays_%s.csv"' % gid})
