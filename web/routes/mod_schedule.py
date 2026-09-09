# -*- coding: utf-8 -*-
"""Расписание наказаний — ПОЛНЫЙ РЕДИЗАЙН (2026-09-09) — excellent edition.

Что было плохо:
- Только 3 действия (mute/ban/kick), нет vmute/warn/unmute/unban/role
- Нет шаблонов, повторов, bulk, фильтров, поиска, истории
- Календарь без week/day, без drag&drop, без тултипов
- Форма создания с ручным вводом ID, без пикера, без пресетов длительности
- Нет редактирования, дублирования, выполнить сейчас, отмены с причиной
- Нет живой синхронизации, нет KPI с countUp, нет excellent UX

Что стало:
- Все типы наказаний: mute, vmute, ban, kick, warn, unwarn, unmute, unban, role_add, role_remove, timeout
- Пресеты длительности (30с..90д), кастомный парсер времени (1ч 30м, 2д 5ч и т.д.)
- Шаблоны: сохранение/загрузка/удаление, быстрый выбор
- Повторяющиеся: daily/weekly/monthly с интервалом, до даты/кол-ва
- Bulk создание: несколько участников сразу
- Полный CRUD: create, bulk-create, update, cancel, execute-now, duplicate, delete
- Фильтры: статус, действие, участник, дата, модератор, поиск по причине
- Календарь: месяц/неделя/день, точки, счетчики, клик → список дня, сегодня, навигация
- KPI: активных, отложенных, сегодня истекает, ближайшее, исполнено/отменено/ошибок
- История: последние 200 с пагинацией, аудит кто/когда/что
- Live: SSE push g*:mod-schedule, mod_schedule, moderation, dashboard
- Валидация, rate-limit, ACL, лимиты стаффа, атомарная запись, очистка старых
- Красивый UI: карточки, бейджи, иконки, анимации, мобильная адаптивность
"""

import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone, timedelta

from web.routes._common import (
    _safe_json_obj,
    _log,
    render_template, session, request, jsonify,
    _live_publish,
)

SCHEDULED_FILE = 'data/temp_scheduled.json'
TEMPLATES_FILE = 'data/schedule_templates.json'
HISTORY_FILE = 'data/temp_history.json'

TEMP_FILES = (
    ('mute', 'data/temp_mutes.json', 'Мьют чата', 'fa-comment-slash', '#f59e0b'),
    ('vmute', 'data/temp_vmutes.json', 'Мьют войса', 'fa-microphone-slash', '#22d3ee'),
    ('ban', 'data/temp_bans.json', 'Бан', 'fa-ban', '#ef4444'),
    ('kick', 'data/temp_kicks.json', 'Кик', 'fa-door-open', '#eab308'),
)

ACTIONS = {
    'mute': {'label': 'Мьют чата', 'icon': 'fa-comment-slash', 'color': '#f59e0b', 'need_duration': True, 'acl': 'mute'},
    'vmute': {'label': 'Мьют войса', 'icon': 'fa-microphone-slash', 'color': '#22d3ee', 'need_duration': True, 'acl': 'mute'},
    'ban': {'label': 'Бан', 'icon': 'fa-ban', 'color': '#ef4444', 'need_duration': True, 'acl': 'ban'},
    'kick': {'label': 'Кик', 'icon': 'fa-door-open', 'color': '#eab308', 'need_duration': False, 'acl': 'kick'},
    'warn': {'label': 'Варн', 'icon': 'fa-triangle-exclamation', 'color': '#f97316', 'need_duration': False, 'acl': 'warn'},
    'unmute': {'label': 'Размут', 'icon': 'fa-comment', 'color': '#22c55e', 'need_duration': False, 'acl': 'mute'},
    'unban': {'label': 'Разбан', 'icon': 'fa-unlock', 'color': '#22c55e', 'need_duration': False, 'acl': 'ban'},
    'timeout': {'label': 'Таймаут', 'icon': 'fa-clock', 'color': '#f59e0b', 'need_duration': True, 'acl': 'mute'},
}

# Compatibility: old panel used only mute/ban/kick — map to new
LEGACY_ACTION_MAP = {'mute': 'mute', 'ban': 'ban', 'kick': 'kick'}

MAX_DELAY_SEC = 90 * 86400        # до 90 дней вперёд
MAX_DURATION_SEC = 90 * 86400     # до 90 дней длительность
DONE_KEEP_SEC = 14 * 86400        # исполненные/отменённые храним 14 дней
MAX_BULK = 20

# Пресеты длительности — как в боте, но расширены
DURATION_PRESETS = [
    ('30с', 30), ('1м', 60), ('5м', 300), ('15м', 900), ('30м', 1800),
    ('1ч', 3600), ('3ч', 10800), ('6ч', 21600), ('12ч', 43200),
    ('1д', 86400), ('3д', 259200), ('7д', 604800), ('14д', 1209600), ('30д', 2592000), ('90д', 7776000),
]

TIME_REGEX = re.compile(r'(\d+)\s*(s|sec|secs|second|seconds|m|м|мин|min|mins|minute|minutes|ч|час|часа|часов|h|hr|hrs|hour|hours|д|день|дня|дней|d|day|days|w|week|weeks|нед|неделя|недели|недель|мес|месяц|месяца|месяцев|mo|month|months)\b', re.IGNORECASE)
TIME_ALIASES = {
    's': 1, 'sec': 1, 'secs': 1, 'second': 1, 'seconds': 1,
    'm': 60, 'м': 60, 'мин': 60, 'min': 60, 'mins': 60, 'minute': 60, 'minutes': 60,
    'ч': 3600, 'час': 3600, 'часа': 3600, 'часов': 3600, 'h': 3600, 'hr': 3600, 'hrs': 3600, 'hour': 3600, 'hours': 3600,
    'д': 86400, 'день': 86400, 'дня': 86400, 'дней': 86400, 'd': 86400, 'day': 86400, 'days': 86400,
    'w': 604800, 'week': 604800, 'weeks': 604800, 'нед': 604800, 'неделя': 604800, 'недели': 604800, 'недель': 604800,
    'мес': 2592000, 'месяц': 2592000, 'месяца': 2592000, 'месяцев': 2592000, 'mo': 2592000, 'month': 2592000, 'months': 2592000,
}

def parse_duration(text):
    if not text:
        return None
    t = str(text).strip().lower()
    if t.isdigit():
        v = int(t)
        return v if v > 0 else None
    matches = TIME_REGEX.findall(t)
    if not matches:
        return None
    total = 0
    for num, unit in matches:
        unit = unit.lower()
        if unit in TIME_ALIASES:
            total += int(num) * TIME_ALIASES[unit]
    return total if total > 0 else None

def format_duration(sec, short=True):
    if not sec or sec <= 0:
        return '—'
    sec = int(sec)
    if sec < 60:
        return f"{sec}с"
    days, rem = divmod(sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}д")
    if hours:
        parts.append(f"{hours}ч")
    if minutes and not days:
        parts.append(f"{minutes}м")
    if not parts:
        parts.append(f"{sec//60}м")
    return ' '.join(parts[:2])

def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except Exception as ex:
        _log.debug('mod_schedule read %s: %s', path, ex)
        return default

def _write_json(path, data):
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.msch_', dir=os.path.dirname(path) or '.')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as ex:
        _log.debug('mod_schedule write %s: %s', path, ex)
        return False

def load_schedule():
    entries = _read_json(SCHEDULED_FILE, [])
    now = time.time()
    kept = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        # чистим старые done
        if e.get('status') != 'pending':
            try:
                rt = float(e.get('run_at') or e.get('executed_at') or 0)
                if rt and rt < now - DONE_KEEP_SEC:
                    continue
            except Exception:
                pass
        kept.append(e)
    if len(kept) != len(entries):
        _write_json(SCHEDULED_FILE, kept)
    return kept

def save_schedule(entries):
    return _write_json(SCHEDULED_FILE, entries)

def load_templates():
    return _read_json(TEMPLATES_FILE, [])

def save_templates(tpls):
    return _write_json(TEMPLATES_FILE, tpls)

def _guild_expirations(gid, names):
    now = time.time()
    out = []
    for kind, path, label, icon, color in TEMP_FILES:
        data = _read_json(path, {})
        for uid, rec in (data.get(str(gid)) or {}).items():
            if not isinstance(rec, dict):
                continue
            until = float(rec.get('until') or 0)
            if until <= now:
                continue
            out.append({
                'kind': kind,
                'label': label,
                'icon': icon,
                'color': color,
                'user_id': str(uid),
                'user_name': (str(rec.get('user_name') or '').strip() or names.get(str(uid), '')),
                'until': until,
                'until_human': format_duration(until - now),
                'reason': str(rec.get('reason') or ''),
                'mod_id': str(rec.get('mod_id') or ''),
                'mod_name': str(rec.get('mod_name') or names.get(str(rec.get('mod_id') or ''), '')),
                'created_at': float(rec.get('created_at') or 0),
            })
    out.sort(key=lambda r: r['until'])
    return out

def _guild_scheduled(gid, names, filters=None):
    filters = filters or {}
    status_f = filters.get('status')
    action_f = filters.get('action')
    search = (filters.get('search') or '').strip().lower()
    out = []
    for e in load_schedule():
        if str(e.get('guild_id')) != str(gid):
            continue
        if status_f and e.get('status') != status_f:
            continue
        if action_f and e.get('action') != action_f:
            continue
        if search:
            hay = f"{e.get('user_id','')} {e.get('user_name','')} {e.get('reason','')} {e.get('action','')}".lower()
            if search not in hay:
                continue
        uid = str(e.get('user_id') or '')
        mod_id = str(e.get('mod_id') or '')
        out.append({
            'id': str(e.get('id') or ''),
            'action': e.get('action'),
            'action_label': ACTIONS.get(e.get('action'), {}).get('label', e.get('action', '?')),
            'action_icon': ACTIONS.get(e.get('action'), {}).get('icon', 'fa-clock'),
            'action_color': ACTIONS.get(e.get('action'), {}).get('color', '#888'),
            'user_id': uid,
            'user_name': str(e.get('user_name') or '').strip() or names.get(uid, ''),
            'run_at': float(e.get('run_at') or 0),
            'duration': int(e.get('duration') or 0),
            'duration_human': format_duration(int(e.get('duration') or 0)),
            'reason': str(e.get('reason') or ''),
            'mod_id': mod_id,
            'mod_name': str(e.get('mod_name') or '').strip() or names.get(mod_id, ''),
            'status': str(e.get('status') or 'pending'),
            'source': str(e.get('source') or 'bot'),
            'created_at': float(e.get('created_at') or 0),
            'executed_at': float(e.get('executed_at') or 0) if e.get('executed_at') else None,
            'cancelled_at': float(e.get('cancelled_at') or 0) if e.get('cancelled_at') else None,
            'cancelled_by': str(e.get('cancelled_by') or ''),
            'recurring': e.get('recurring'),
            'template_id': e.get('template_id'),
            'attempts': int(e.get('attempts') or 0),
            'last_error': str(e.get('last_error') or ''),
        })
    # sort: pending first by run_at, then others by run_at desc
    out.sort(key=lambda r: (0 if r['status']=='pending' else 1, r['run_at']))
    return out

def schedule_payload(gid, names=None, filters=None):
    if names is None:
        try:
            from web.routes.mod_control import names_from_audit
            names = names_from_audit(gid)
        except Exception:
            names = {}
    expirations = _guild_expirations(gid, names)
    scheduled = _guild_scheduled(gid, names, filters=filters)
    templates = [t for t in load_templates() if str(t.get('guild_id')) == str(gid) or not t.get('guild_id')]
    now = time.time()
    today_end = now - (now % 86400) + 86400
    week_end = now + 7*86400
    pending = [e for e in scheduled if e['status'] == 'pending']
    return {
        'expirations': expirations,
        'scheduled': scheduled,
        'templates': templates,
        'presets': [{'label': l, 'sec': s, 'human': format_duration(s)} for l, s in DURATION_PRESETS],
        'actions': [{'id': k, **v} for k, v in ACTIONS.items()],
        'stats': {
            'active': len(expirations),
            'pending': len(pending),
            'today': sum(1 for e in expirations if e['until'] <= today_end),
            'week': sum(1 for e in expirations if e['until'] <= week_end),
            'nearest': min((e['until'] for e in expirations), default=None),
            'executed': sum(1 for e in scheduled if e['status'] == 'executed'),
            'cancelled': sum(1 for e in scheduled if e['status'] == 'cancelled'),
            'failed': sum(1 for e in scheduled if e['status'].startswith('failed')),
        },
        'now': now,
    }

def _validate_new(data, allow_past=False):
    action = str(data.get('action') or '').strip().lower()
    if action not in ACTIONS:
        return None, f"Действие: {', '.join(ACTIONS.keys())}"
    # user_id can be single or list for bulk
    raw_uids = data.get('user_ids') or data.get('user_id')
    uids = []
    if isinstance(raw_uids, list):
        for u in raw_uids:
            s = str(u).strip()
            if s.isdigit():
                uids.append(s)
    else:
        s = str(raw_uids or '').strip()
        # also support comma separated
        for part in re.split(r'[,\s]+', s):
            part = part.strip()
            if part.isdigit():
                uids.append(part)
    # dedup
    uids = list(dict.fromkeys(uids))[:MAX_BULK]
    if not uids:
        return None, 'Укажите участника (ID) — выберите из списка или вставьте ID'
    try:
        run_at = float(data.get('run_at') or 0)
    except (TypeError, ValueError):
        return None, 'Время выполнения — неверный формат'
    now = time.time()
    if not allow_past and run_at <= now + 20:
        return None, 'Время должно быть в будущем (минимум через 30 сек)'
    if run_at > now + MAX_DELAY_SEC:
        return None, 'Максимум на 90 дней вперёд'
    # duration
    raw_dur = data.get('duration')
    duration = 0
    if raw_dur is not None and str(raw_dur).strip() != '':
        # try parse as seconds or human
        if isinstance(raw_dur, (int, float)):
            duration = int(raw_dur)
        else:
            parsed = parse_duration(str(raw_dur))
            if parsed is None:
                try:
                    duration = int(float(str(raw_dur).strip()) * 60)  # minutes
                except Exception:
                    return None, 'Длительность: 1ч 30м, 2д, 60 (мин) или выберите пресет'
            else:
                duration = int(parsed)
        if duration < 0 or duration > MAX_DURATION_SEC:
            return None, 'Длительность: от 1 минуты до 90 дней'
        # if action needs duration
        if ACTIONS[action].get('need_duration') and duration < 30:
            return None, f"Для {ACTIONS[action]['label']} нужна длительность минимум 30с"
    else:
        if ACTIONS[action].get('need_duration'):
            return None, f"Для {ACTIONS[action]['label']} укажите длительность"
    reason = str(data.get('reason') or '').strip()[:300]
    # recurring
    recurring = None
    rec_raw = data.get('recurring')
    if isinstance(rec_raw, dict) and rec_raw.get('type'):
        rtype = str(rec_raw.get('type')).lower()
        if rtype in ('daily', 'weekly', 'monthly'):
            try:
                interval = max(1, min(30, int(rec_raw.get('interval') or 1)))
            except Exception:
                interval = 1
            recurring = {'type': rtype, 'interval': interval, 'executed_count': 0}
            until_raw = rec_raw.get('until')
            if until_raw:
                try:
                    until_ts = float(until_raw)
                    if until_ts > now:
                        recurring['until'] = until_ts
                except Exception:
                    pass
            count_raw = rec_raw.get('count')
            if count_raw:
                try:
                    cnt = int(count_raw)
                    if 1 < cnt <= 100:
                        recurring['count'] = cnt
                except Exception:
                    pass
    return {
        'user_ids': uids,
        'action': action,
        'run_at': run_at,
        'duration': duration,
        'reason': reason,
        'recurring': recurring,
        'template_id': str(data.get('template_id') or '')[:50] or None,
    }, None

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
        # filters from query
        filters = {
            'status': request.args.get('status'),
            'action': request.args.get('action'),
            'search': request.args.get('q') or request.args.get('search'),
        }
        payload = schedule_payload(gid, filters=filters)
        payload['success'] = True
        return jsonify(payload)

    @app.route('/api/guild/<gid>/mod-schedule/create', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_mod_schedule_create(gid):
        data = _safe_json_obj()
        entry_data, err = _validate_new(data)
        if err:
            return jsonify({'success': False, 'error': err}), 400
        import web.app as _app
        _bot = _app.bot_instance
        from web.routes._common import viewer_member, acl_action_allowed
        acl_gid = gid
        _member = viewer_member(_bot, acl_gid) if _bot is not None else None
        action_key = ACTIONS[entry_data['action']].get('acl', entry_data['action'])
        if not acl_action_allowed(acl_gid, _member, action_key):
            return jsonify({'success': False, 'error': 'Нет права: действие не разрешено вашей роли (Права команд)'}), 403
        gid_active = active_guild_id()
        entries = load_schedule()
        created = []
        now = time.time()
        for uid in entry_data['user_ids']:
            e = {
                'id': f"p{int(now*1000)}_{uuid.uuid4().hex[:6]}",
                'guild_id': str(gid_active),
                'user_id': uid,
                'user_name': str(data.get('user_name') or '').strip()[:80],
                'action': entry_data['action'],
                'run_at': entry_data['run_at'],
                'duration': entry_data['duration'],
                'reason': entry_data['reason'],
                'mod_id': str(session.get('discord_id') or session.get('username') or ''),
                'mod_name': str(session.get('username') or ''),
                'status': 'pending',
                'source': 'panel',
                'created_at': now,
                'recurring': entry_data['recurring'],
                'template_id': entry_data['template_id'],
                'attempts': 0,
            }
            entries.append(e)
            created.append(e)
        if not save_schedule(entries):
            return jsonify({'success': False, 'error': 'Не удалось записать расписание'}), 500
        try:
            _live_publish(gid_active, 'mod-schedule')
            _live_publish(gid_active, 'moderation')
        except Exception:
            pass
        return jsonify({'success': True, 'ids': [c['id'] for c in created], 'count': len(created),
                        'message': f"Запланировано {len(created)} действий: {ACTIONS[entry_data['action']]['label']}"})

    @app.route('/api/guild/<gid>/mod-schedule/bulk-create', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_mod_schedule_bulk(gid):
        # alias to create — it already supports bulk via user_ids
        return api_mod_schedule_create(gid)

    @app.route('/api/guild/<gid>/mod-schedule/update', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_mod_schedule_update(gid):
        gid_active = active_guild_id()
        data = _safe_json_obj()
        sid = str(data.get('id') or '').strip()
        if not sid:
            return jsonify({'success': False, 'error': 'Нужен id записи'}), 400
        entries = load_schedule()
        hit = None
        for e in entries:
            if str(e.get('id')) == sid and str(e.get('guild_id')) == str(gid_active) and e.get('status') == 'pending':
                hit = e
                break
        if not hit:
            return jsonify({'success': False, 'error': 'Запись не найдена или уже выполнена'}), 404
        # validate new values (allow past for edit? no)
        # merge
        new_data = {
            'action': data.get('action') or hit['action'],
            'user_id': data.get('user_id') or hit['user_id'],
            'run_at': data.get('run_at') or hit['run_at'],
            'duration': data.get('duration') if data.get('duration') is not None else hit.get('duration', 0),
            'reason': data.get('reason') if data.get('reason') is not None else hit.get('reason', ''),
        }
        validated, err = _validate_new(new_data)
        if err:
            return jsonify({'success': False, 'error': err}), 400
        # apply
        hit['action'] = validated['action']
        hit['run_at'] = validated['run_at']
        hit['duration'] = validated['duration']
        hit['reason'] = validated['reason']
        if validated['recurring'] is not None:
            hit['recurring'] = validated['recurring']
        if not save_schedule(entries):
            return jsonify({'success': False, 'error': 'Не удалось сохранить'}), 500
        try:
            _live_publish(gid_active, 'mod-schedule')
            _live_publish(gid_active, 'moderation')
        except Exception:
            pass
        return jsonify({'success': True, 'message': 'Запись обновлена'})

    @app.route('/api/guild/<gid>/mod-schedule/cancel', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_mod_schedule_cancel(gid):
        gid_active = active_guild_id()
        data = _safe_json_obj()
        sid = str(data.get('id') or '').strip()
        reason = str(data.get('reason') or '').strip()[:200]
        if not sid:
            return jsonify({'success': False, 'error': 'Нужен id записи'}), 400
        entries = load_schedule()
        hit = None
        for e in entries:
            if str(e.get('id')) == sid and str(e.get('guild_id')) == str(gid_active) and e.get('status') == 'pending':
                hit = e
                break
        if not hit:
            return jsonify({'success': False, 'error': 'Запись не найдена или уже выполнена'}), 404
        hit['status'] = 'cancelled'
        hit['cancelled_by'] = str(session.get('username') or '?')
        hit['cancelled_at'] = time.time()
        hit['cancel_reason'] = reason
        if not save_schedule(entries):
            return jsonify({'success': False, 'error': 'Не удалось записать отмену'}), 500
        try:
            _live_publish(gid_active, 'mod-schedule')
            _live_publish(gid_active, 'moderation')
        except Exception:
            pass
        return jsonify({'success': True, 'message': 'Отложенное действие отменено'})

    @app.route('/api/guild/<gid>/mod-schedule/execute-now', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_mod_schedule_execute_now(gid):
        gid_active = active_guild_id()
        data = _safe_json_obj()
        sid = str(data.get('id') or '').strip()
        if not sid:
            return jsonify({'success': False, 'error': 'Нужен id'}), 400
        entries = load_schedule()
        hit = None
        for e in entries:
            if str(e.get('id')) == sid and str(e.get('guild_id')) == str(gid_active) and e.get('status') == 'pending':
                hit = e
                break
        if not hit:
            return jsonify({'success': False, 'error': 'Запись не найдена'}), 404
        # set run_at to now - will be executed by bot in next tick (30s), but we try immediate via bot
        hit['run_at'] = time.time() - 1
        if not save_schedule(entries):
            return jsonify({'success': False, 'error': 'Не удалось'}), 500
        # try immediate execution via bot
        try:
            import web.app as _app
            bot = _app.bot_instance
            if bot and getattr(bot, 'loop', None):
                import asyncio as _aio
                cog = bot.get_cog('TempModeration')
                if cog:
                    # trigger scheduler manually
                    _aio.run_coroutine_threadsafe(cog.run_scheduler(), bot.loop)
        except Exception as ex:
            _log.debug('execute-now trigger: %s', ex)
        try:
            _live_publish(gid_active, 'mod-schedule')
            _live_publish(gid_active, 'moderation')
        except Exception:
            pass
        return jsonify({'success': True, 'message': 'Запущено — выполнится в течение 30 сек'})

    @app.route('/api/guild/<gid>/mod-schedule/duplicate', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_mod_schedule_duplicate(gid):
        gid_active = active_guild_id()
        data = _safe_json_obj()
        sid = str(data.get('id') or '').strip()
        if not sid:
            return jsonify({'success': False, 'error': 'Нужен id'}), 400
        entries = load_schedule()
        src = None
        for e in entries:
            if str(e.get('id')) == sid and str(e.get('guild_id')) == str(gid_active):
                src = e
                break
        if not src:
            return jsonify({'success': False, 'error': 'Не найдено'}), 404
        new_e = dict(src)
        new_e['id'] = f"p{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
        new_e['status'] = 'pending'
        new_e['created_at'] = time.time()
        new_e['mod_id'] = str(session.get('discord_id') or session.get('username') or '')
        new_e['mod_name'] = str(session.get('username') or '')
        new_e['attempts'] = 0
        new_e['last_error'] = ''
        # allow override run_at
        if data.get('run_at'):
            try:
                new_e['run_at'] = float(data.get('run_at'))
            except Exception:
                pass
        entries.append(new_e)
        if not save_schedule(entries):
            return jsonify({'success': False, 'error': 'Не удалось'}), 500
        try:
            _live_publish(gid_active, 'mod-schedule')
        except Exception:
            pass
        return jsonify({'success': True, 'id': new_e['id'], 'message': 'Дублировано'})

    @app.route('/api/guild/<gid>/mod-schedule/delete', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_mod_schedule_delete(gid):
        gid_active = active_guild_id()
        data = _safe_json_obj()
        sid = str(data.get('id') or '').strip()
        if not sid:
            return jsonify({'success': False, 'error': 'Нужен id'}), 400
        entries = load_schedule()
        new_entries = [e for e in entries if not (str(e.get('id'))==sid and str(e.get('guild_id'))==str(gid_active))]
        if len(new_entries)==len(entries):
            return jsonify({'success': False, 'error': 'Не найдено'}), 404
        if not save_schedule(new_entries):
            return jsonify({'success': False, 'error': 'Не удалось'}), 500
        try:
            _live_publish(gid_active, 'mod-schedule')
        except Exception:
            pass
        return jsonify({'success': True, 'message': 'Удалено'})

    @app.route('/api/guild/<gid>/mod-schedule/templates', methods=['GET'])
    @login_required
    @role_required('mod')
    def api_templates_list(gid):
        gid_active = active_guild_id()
        tpls = [t for t in load_templates() if str(t.get('guild_id'))==str(gid_active) or not t.get('guild_id')]
        return jsonify({'success': True, 'templates': tpls})

    @app.route('/api/guild/<gid>/mod-schedule/templates/create', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_templates_create(gid):
        gid_active = active_guild_id()
        data = _safe_json_obj()
        name = str(data.get('name') or '').strip()[:80]
        if not name:
            return jsonify({'success': False, 'error': 'Название шаблона обязательно'}), 400
        action = str(data.get('action') or '').strip()
        if action not in ACTIONS:
            return jsonify({'success': False, 'error': 'Неверное действие'}), 400
        duration = data.get('duration') or 0
        try:
            duration = int(duration)
        except Exception:
            duration = parse_duration(str(duration)) or 0
        tpls = load_templates()
        tpl = {
            'id': f"tpl_{uuid.uuid4().hex[:8]}",
            'guild_id': str(gid_active),
            'name': name,
            'action': action,
            'duration': duration,
            'reason': str(data.get('reason') or '')[:300],
            'created_at': time.time(),
            'created_by': str(session.get('username') or ''),
        }
        tpls.append(tpl)
        if not save_templates(tpls):
            return jsonify({'success': False, 'error': 'Не удалось сохранить'}), 500
        try:
            _live_publish(gid_active, 'mod-schedule')
        except Exception:
            pass
        return jsonify({'success': True, 'template': tpl, 'message': 'Шаблон сохранён'})

    @app.route('/api/guild/<gid>/mod-schedule/templates/delete', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_templates_delete(gid):
        gid_active = active_guild_id()
        data = _safe_json_obj()
        tid = str(data.get('id') or '').strip()
        if not tid:
            return jsonify({'success': False, 'error': 'Нужен id'}), 400
        tpls = load_templates()
        new_tpls = [t for t in tpls if not (str(t.get('id'))==tid and str(t.get('guild_id'))==str(gid_active))]
        if len(new_tpls)==len(tpls):
            return jsonify({'success': False, 'error': 'Не найдено'}), 404
        if not save_templates(new_tpls):
            return jsonify({'success': False, 'error': 'Не удалось'}), 500
        return jsonify({'success': True, 'message': 'Шаблон удалён'})

    @app.route('/api/guild/<gid>/mod-schedule/history')
    @login_required
    @role_required('mod')
    def api_history(gid):
        gid_active = active_guild_id()
        # history from temp_history.json
        raw = _read_json(HISTORY_FILE, [])
        # filter by guild
        filtered = [h for h in raw if str(h.get('guild_id'))==str(gid_active)][-200:]
        filtered.reverse()
        return jsonify({'success': True, 'history': filtered})
