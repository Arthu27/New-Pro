# -*- coding: utf-8 -*-
"""Расписание наказаний: календарь истечений + отложенные действия.

Данные — те самые файлы бота:
- data/temp_mutes.json, temp_bans.json, temp_vmutes.json, temp_kicks.json —
  активные временные наказания ({gid: {uid: {until, reason, mod_id}}}),
  их истечения рисуются точками на календаре (cogs/temp_moderation.py
  сам снимает наказание, когда время вышло);
- data/temp_scheduled.json — отложенные действия. Панель добавляет и
  отменяет записи; планировщик бота перечитывает файл каждые 30 секунд
  (см. run_scheduler — смерджит и исполнит), так что перезапуск не нужен.

Имена участников — names_from_audit (общий источник «ID → имя»).
Создание и отмена — mod+, журналируются авто-логом панели.
"""
import json
import os
import tempfile
import time

from web.routes._common import (
    _safe_json_obj,
    _log,
    render_template, session, request, jsonify,
)

SCHEDULED_FILE = 'data/temp_scheduled.json'
TEMP_FILES = (('mute', 'data/temp_mutes.json', 'Мьют чата'),
              ('vmute', 'data/temp_vmutes.json', 'Мьют войса'),
              ('ban', 'data/temp_bans.json', 'Бан'),
              ('kick', 'data/temp_kicks.json', 'Кик'))

ACTIONS = {'mute': 'Мьют', 'ban': 'Бан', 'kick': 'Кик'}
MAX_DELAY_SEC = 60 * 86400        # откладывать не дальше двух месяцев
MAX_DURATION_SEC = 90 * 86400     # длительность наказания — до 90 дней
DONE_KEEP_SEC = 7 * 86400         # исполненные/отменённые чистим через неделю


def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (json.JSONDecodeError, ValueError, OSError) as _ex:
        _log.debug('mod_schedule: чтение %s: %s', path, _ex)
        return default


def _write_json(path, data):
    """Атомарно: tmp + rename — перечитывающий бот не увидит полфайла."""
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.msch_', dir=os.path.dirname(path) or '.')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except OSError as _ex:
        _log.debug('mod_schedule: запись %s: %s', path, _ex)
        return False


def load_schedule():
    """Список записей с вычищенными старыми хвостами (done старше недели)."""
    entries = _read_json(SCHEDULED_FILE, [])
    now = time.time()
    kept = [e for e in entries if isinstance(e, dict) and (
        e.get('status') == 'pending'
        or float(e.get('run_at') or 0) > now - DONE_KEEP_SEC)]
    if len(kept) != len(entries):
        _write_json(SCHEDULED_FILE, kept)
    return kept


def _guild_expirations(gid, names):
    """Активные временные наказания сервера с датами истечения."""
    now = time.time()
    out = []
    for kind, path, label in TEMP_FILES:
        data = _read_json(path, {})
        for uid, rec in (data.get(str(gid)) or {}).items():
            if not isinstance(rec, dict):
                continue
            until = float(rec.get('until') or 0)
            if until <= now:        # уже истекло — бот вот-вот снимет
                continue
            out.append({'kind': kind, 'label': label,
                        'user_id': str(uid),
                        'user_name': (str(rec.get('user_name') or '').strip()
                                      or names.get(str(uid), '')),
                        'until': until,
                        'reason': str(rec.get('reason') or ''),
                        'mod_id': str(rec.get('mod_id') or '')})
    out.sort(key=lambda r: r['until'])
    return out


def _guild_scheduled(gid, names):
    out = []
    for e in load_schedule():
        if str(e.get('guild_id')) != str(gid):
            continue
        uid = str(e.get('user_id') or '')
        out.append({'id': str(e.get('id') or ''),
                    'action': e.get('action'),
                    'action_label': ACTIONS.get(e.get('action'), '?'),
                    'user_id': uid,
                    'user_name': str(e.get('user_name') or '').strip()
                                 or names.get(uid, ''),
                    'run_at': float(e.get('run_at') or 0),
                    'duration': int(e.get('duration') or 0),
                    'reason': str(e.get('reason') or ''),
                    'mod_id': str(e.get('mod_id') or ''),
                    'status': str(e.get('status') or 'pending'),
                    'source': str(e.get('source') or 'bot')})
    out.sort(key=lambda r: r['run_at'])
    return out


def schedule_payload(gid, names=None):
    """Сводка для API: KPI + истечения + отложенные (тестируется без Flask)."""
    if names is None:
        try:
            from web.routes.mod_control import names_from_audit
            names = names_from_audit(gid)
        except Exception as _ex:
            _log.debug('mod_schedule: имена: %s', _ex)
            names = {}
    expirations = _guild_expirations(gid, names)
    scheduled = _guild_scheduled(gid, names)
    now = time.time()
    day_end = now - (now % 86400) + 86400   # грубые сутки для «сегодня истекает»
    pending = [e for e in scheduled if e['status'] == 'pending']
    return {
        'expirations': expirations,
        'scheduled': scheduled,
        'stats': {
            'active': len(expirations),
            'pending': len(pending),
            'today': sum(1 for e in expirations if e['until'] <= day_end),
            'nearest': min((e['until'] for e in expirations), default=None),
        },
        'now': now,
    }


def _validate_new(data):
    """Проверка формы отложенного действия. Возвращает (entry, ошибка)."""
    action = str(data.get('action') or '').strip().lower()
    if action not in ACTIONS:
        return None, 'Действие: mute, ban или kick'
    uid = str(data.get('user_id') or '').strip()
    if not uid.isdigit():
        return None, 'ID участника — только цифры (включите режим разработчика в Discord)'
    name = str(data.get('user_name') or '').strip()[:80]
    try:
        run_at = float(data.get('run_at') or 0)
    except (TypeError, ValueError):
        run_at = 0
    now = time.time()
    if run_at <= now + 30:
        return None, 'Время выполнения должно быть в будущем (хотя бы через минуту)'
    if run_at > now + MAX_DELAY_SEC:
        return None, 'Откладывать можно максимум на 60 дней вперёд'
    try:
        duration = int(data.get('duration') or 0)
    except (TypeError, ValueError):
        return None, 'Длительность — число минут'
    if duration < 1 or duration * 60 > MAX_DURATION_SEC:
        return None, 'Длительность: от 1 минуты до 90 дней'
    reason = str(data.get('reason') or '').strip()[:200]
    return {'action': action, 'user_id': uid, 'user_name': name,
            'run_at': run_at, 'duration': duration * 60,
            'reason': reason}, None


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    @app.route('/mod-schedule')
    @login_required
    @role_required('mod')
    def mod_schedule_page():
        return render_template('mod_schedule.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id(),
                               can_edit=session.get('role') in ('mod', 'admin', 'owner'))

    @app.route('/api/guild/<gid>/mod-schedule')
    @login_required
    @role_required('mod')
    def api_mod_schedule(gid):
        gid = active_guild_id()
        payload = schedule_payload(gid)
        payload['success'] = True
        return jsonify(payload)

    @app.route('/api/guild/<gid>/mod-schedule/create', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_mod_schedule_create(gid):
        entry, err = _validate_new(_safe_json_obj())
        if err:
            return jsonify({'success': False, 'error': err}), 400
        # Классические разрешения (Доступ → Права команд): не дал роли
        # «Бан»/«Мут»/«Кик» — отложенный бан/мут/кик не создать, даже если
        # выполняется ботом позже (настройки действуют везде одинаково).
        # ACL проверяем по серверу из URL (на нём действует правило), а
        # данные пишем в активный сервер панели (MAIN_GUILD_ID).
        import web.app as _app
        _bot = _app.bot_instance
        from web.routes._common import viewer_member, acl_action_allowed
        # ACL — по серверу из URL (на нём действует правило); данные пишем
        # в активный сервер панели (MAIN_GUILD_ID).
        acl_gid = gid
        _member = viewer_member(_bot, acl_gid) if _bot is not None else None
        if not acl_action_allowed(acl_gid, _member, entry['action']):
            return jsonify({'success': False,
                            'error': 'Нет права: действие не разрешено вашей '
                                     'роли (настройка — «Права команд»)'}), 403
        gid = active_guild_id()
        entries = load_schedule()
        entry.update({
            'id': f'p{int(time.time() * 1000)}',
            'guild_id': str(gid),
            'mod_id': str(session.get('discord_id') or
                          session.get('username') or ''),
            'mod_name': str(session.get('username') or ''),
            'status': 'pending',
            'source': 'panel',          # бот выполнит: пометим origin честно
        })
        entries.append(entry)
        if not _write_json(SCHEDULED_FILE, entries):
            return jsonify({'success': False,
                            'error': 'Не удалось записать расписание'}), 500
        return jsonify({'success': True, 'id': entry['id'],
                        'message': f"Запланировано: {ACTIONS[entry['action']]} "
                                   f'для {entry["user_id"]}'})

    @app.route('/api/guild/<gid>/mod-schedule/cancel', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_mod_schedule_cancel(gid):
        gid = active_guild_id()
        data = _safe_json_obj()
        sid = str(data.get('id') or '').strip()
        if not sid:
            return jsonify({'success': False, 'error': 'Нужен id записи'}), 400
        entries = load_schedule()
        hit = None
        for e in entries:
            if (str(e.get('id')) == sid and str(e.get('guild_id')) == str(gid)
                    and e.get('status') == 'pending'):
                hit = e
                break
        if hit is None:
            return jsonify({'success': False,
                            'error': 'Запись не найдена или уже выполнена'}), 404
        hit['status'] = 'cancelled'
        hit['cancelled_by'] = str(session.get('username') or '?')
        if not _write_json(SCHEDULED_FILE, entries):
            return jsonify({'success': False,
                            'error': 'Не удалось записать отмену'}), 500
        return jsonify({'success': True, 'message': 'Отложенное действие отменено'})
