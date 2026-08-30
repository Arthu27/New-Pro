# -*- coding: utf-8 -*-
"""Мод-контроль (идеи #34-37): быстрые причины, «на грани» авто-наказания,
амнистия по варнам, радар истечений временных наказаний.

Всё поверх существующих файлов бота:
- data/warnings.json — зеркало варнов (пишет cogs/warnings.py);
- data/warn_config_<gid>.json — пороги авто-наказаний (страница /warn-config;
  бот читает ключи 'steps'/'thresholds' — принимаем оба 1:1);
- data/temp_mutes|temp_bans|temp_vmutes|temp_kicks.json — временные наказания
  (cogs/temp_moderation.py, формат {gid: {uid: {until, reason, mod_id}}});
- data/mod_reasons_<gid>.json и data/mod_amnesty_<gid>.json — новые, только
  панель: ког их не читает, лишний файл его не ломает.

Имена участников берём из журнала аудита (mod-события ведутся с парой
user_id/user_name). Чтение — mod+ (как раздел «Модерация»).
Мутации (причины, амнистия) — admin+.
"""
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone

from web.routes._common import (
    _log,
    render_template, session, request, jsonify,
)

from web.routes.analytics_plus import _read_audit

REASON_KINDS = ('warn', 'mute', 'kick', 'ban')
REASON_KIND_LABELS = {'warn': 'Варн', 'mute': 'Мут', 'kick': 'Кик', 'ban': 'Бан'}
REASON_TEXT_MAX = 120
REASONS_PER_KIND = 20

WARN_ACTION_LABELS = {'mute': 'Мут', 'timeout': 'Мут', 'kick': 'Кик', 'ban': 'Бан'}
AT_RISK_LIMIT = 25

AMNESTY_LOG_KEEP = 50

TEMP_KIND_FILES = (
    ('mute', 'Мут', 'temp_mutes.json'),
    ('ban', 'Бан', 'temp_bans.json'),
    ('vmute', 'Войс-мут', 'temp_vmutes.json'),
    ('kick', 'Кик', 'temp_kicks.json'),
)
RADAR_SOON_S = 24 * 3600
RADAR_WEEK_S = 3 * 86400

_USER_REF_RE = re.compile(r'^(?:<@!?(\d{1,20})>|(\d{1,20}))$')


def _gid_str(gid):
    try:
        return str(int(gid))
    except (TypeError, ValueError):
        return str(gid or '')


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as _ex:
        _log.debug("mod_control: %s не прочитан: %s", path, _ex)
        return default


def _save_json(path, data):
    """Атомарная запись (временный файл + замена) — как save_tickets в tickets_ops."""
    folder = os.path.dirname(path) or '.'
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.modctl_', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError as _ex:
            _log.debug("mod_control: временный файл не удалён: %s", _ex)
        raise


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def validate_user_id(value):
    """Принимаем чистый ID или упоминание вида <@123> / <@!123> (как в Discord)."""
    m = _USER_REF_RE.match(str(value or '').strip())
    if not m:
        return False, 'Некорректный ID пользователя', ''
    return True, '', m.group(1) or m.group(2)


def names_from_audit(gid):
    """user_id -> user_name: журнал аудита + общая карта имён (файл/демо/бот).

    Единый источник для рисков, радара, субъектов и амнистии — голые ID
    в панели больше не показываются, если имя известно.
    """
    out = {}
    for ev in _read_audit(gid):
        uid = str(ev.get('user_id') or '').strip()
        name = str(ev.get('user_name') or '').strip()
        if uid and name:
            out.setdefault(uid, name)
    try:
        from web.routes._common import name_map_for
        nm = name_map_for(gid)
        for uid, name in nm.items():
            out.setdefault(str(uid), str(name))
    except Exception as _ex:
        _log.debug("names_from_audit(%s): карта имён: %s", gid, _ex)
    return out


# ─────────────────────────────────────────────────────────────────────
# #34: Быстрые причины
# ─────────────────────────────────────────────────────────────────────
def empty_reasons():
    return {k: [] for k in REASON_KINDS}


def _reasons_path(gid):
    return 'data/mod_reasons_%s.json' % _gid_str(gid)


def load_reasons(gid):
    raw = _load_json(_reasons_path(gid), {})
    out = empty_reasons()
    if not isinstance(raw, dict):
        return out
    for kind in REASON_KINDS:
        items = raw.get(kind)
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            text = str(it.get('text') or '').strip()
            if not text:
                continue
            out[kind].append({
                'id': it.get('id'),
                'text': text[:REASON_TEXT_MAX],
                'by': str(it.get('by') or ''),
                'at': str(it.get('at') or ''),
            })
    return out


def _save_reasons(gid, data):
    _save_json(_reasons_path(gid), {k: data.get(k, []) for k in REASON_KINDS})


def validate_reason_kind(kind):
    if kind in REASON_KINDS:
        return True, ''
    return False, 'Неизвестный тип причины'


def validate_reason_text(text):
    norm = ' '.join(str(text or '').split())
    if not norm:
        return False, 'Укажите текст причины', ''
    if len(norm) > REASON_TEXT_MAX:
        return False, f'Причина длиннее {REASON_TEXT_MAX} символов', ''
    return True, '', norm


def _next_id(items):
    ids = [i for i in (it.get('id') for it in items) if isinstance(i, int)]
    return (max(ids) if ids else 0) + 1


def add_reason(gid, kind, text, by=''):
    ok, err = validate_reason_kind(kind)
    if not ok:
        return False, err, None
    ok, err, norm = validate_reason_text(text)
    if not ok:
        return False, err, None
    data = load_reasons(gid)
    items = data[kind]
    if any(it['text'].lower() == norm.lower() for it in items):
        return False, 'Такая причина уже есть', None
    if len(items) >= REASONS_PER_KIND:
        return False, f'Лимит: {REASONS_PER_KIND} причин на «{REASON_KIND_LABELS[kind]}»', None
    item = {'id': _next_id(items), 'text': norm, 'by': str(by or ''), 'at': _now_iso()}
    items.append(item)
    _save_reasons(gid, data)
    return True, '', item


def remove_reason(gid, kind, item_id):
    ok, err = validate_reason_kind(kind)
    if not ok:
        return False, err, None
    data = load_reasons(gid)
    items = data[kind]
    for idx, it in enumerate(items):
        if it.get('id') == item_id:
            removed = items.pop(idx)
            _save_reasons(gid, data)
            return True, '', removed
    return False, 'Причина не найдена', None


# ─────────────────────────────────────────────────────────────────────
# #35: «На грани» — в одном варне от авто-наказания
# ─────────────────────────────────────────────────────────────────────
def load_warns_map(gid):
    """{uid: [варны]} из зеркала data/warnings.json (только списки словарей)."""
    raw = _load_json('data/warnings.json', {})
    gmap = raw.get(_gid_str(gid)) if isinstance(raw, dict) else None
    if not isinstance(gmap, dict):
        return {}
    out = {}
    for uid, warns in gmap.items():
        if not isinstance(warns, list):
            continue
        items = [w for w in warns if isinstance(w, dict)]
        if items:
            out[str(uid)] = items
    return out


def load_warn_steps(gid):
    """Пороги авто-наказаний: ключи 'steps'/'thresholds' 1:1 с cogs/warnings.py."""
    raw = _load_json('data/warn_config_%s.json' % _gid_str(gid), {})
    if not isinstance(raw, dict):
        return []
    # 1:1 с cogs/warnings.py: панель пишет 'thresholds', старые данные — 'steps'
    steps = raw.get('steps') or raw.get('thresholds') or []
    if not isinstance(steps, list):
        return []
    out = []
    for st in steps:
        if not isinstance(st, dict):
            continue
        try:
            count = int(st.get('count'))
        except (TypeError, ValueError) as _ex:
            _log.debug("mod_control: битый порог варнов: %s", _ex)
            continue
        if count <= 0:
            continue
        action = str(st.get('action') or 'mute')
        out.append({'count': count, 'action': action,
                    'action_name': WARN_ACTION_LABELS.get(action, action)})
    out.sort(key=lambda s: s['count'])
    # Дубли порога: бот выберет последний подходящий — оставляем первый, чтобы
    # «следующий шаг» был детерминированным.
    seen = set()
    uniq = []
    for st in out:
        if st['count'] in seen:
            continue
        seen.add(st['count'])
        uniq.append(st)
    return uniq


def at_risk_users(warns_map, steps, names=None, limit=AT_RISK_LIMIT):
    """Участники с варнами, до следующего авто-наказания которых gap >= 1.

    Бот (cogs/warnings.py) наказывает при warns >= step.count, поэтому
    «следующий шаг» — минимальный порог строго выше текущего счётчика.
    """
    rows = []
    names = names or {}
    for uid, warns in (warns_map or {}).items():
        count = len(warns)
        if count <= 0:
            continue
        nxt = None
        for st in steps or []:
            if st['count'] > count:
                nxt = st
                break
        if nxt is None:
            continue
        rows.append({
            'user_id': uid,
            'name': str(names.get(uid) or ''),
            'warns': count,
            'gap': nxt['count'] - count,
            'next_count': nxt['count'],
            'action': nxt['action'],
            'action_name': nxt.get('action_name') or nxt['action'],
        })
    rows.sort(key=lambda r: (r['gap'], -r['warns'], r['user_id']))
    try:
        lim = int(limit)
    except (TypeError, ValueError) as _ex:
        _log.debug("mod_control: битый лимит at_risk: %s", _ex)
        lim = AT_RISK_LIMIT
    return rows[:max(1, lim)]


# ─────────────────────────────────────────────────────────────────────
# #36: Амнистия — обнулить варны с возможностью отката
# ─────────────────────────────────────────────────────────────────────
def _amnesty_path(gid):
    return 'data/mod_amnesty_%s.json' % _gid_str(gid)


def load_amnesty_log(gid):
    raw = _load_json(_amnesty_path(gid), [])
    if not isinstance(raw, list):
        return []
    return [a for a in raw if isinstance(a, dict)]


def public_amnesty(a, gid=None):
    row = {'id': a.get('id'), 'user_id': str(a.get('user_id') or ''),
            'count': a.get('count', 0), 'by': str(a.get('by') or ''),
            'at': str(a.get('at') or ''), 'restored_at': a.get('restored_at') or None}
    if gid is not None:
        try:
            from web.routes._common import name_map_for
            nm = name_map_for(gid)
            row['name'] = nm.get(row['user_id']) or ''
        except Exception as _ex:
            _log.debug("public_amnesty(): имена: %s", _ex)
    return row


def amnesty_user(gid, user_id, by='', at=None):
    """Забрать все варны участника в журнал амнистии и очистить зеркало."""
    ok, err, uid = validate_user_id(user_id)
    if not ok:
        return False, err, None
    gid = _gid_str(gid)
    raw = _load_json('data/warnings.json', {})
    if not isinstance(raw, dict):
        raw = {}
    gmap = raw.get(gid)
    warns = []
    if isinstance(gmap, dict):
        cur = gmap.get(uid)
        if isinstance(cur, list):
            warns = [w for w in cur if isinstance(w, dict)]
    if not warns:
        return False, 'У участника нет варнов', None
    if isinstance(gmap, dict):
        gmap.pop(uid, None)
        if not gmap:
            raw.pop(gid, None)
    _save_json('data/warnings.json', raw)

    log = load_amnesty_log(gid)
    entry = {'id': _next_id(log), 'user_id': uid, 'count': len(warns), 'warns': warns,
             'by': str(by or ''), 'at': at or _now_iso(), 'restored_at': None}
    log.append(entry)
    _save_json(_amnesty_path(gid), log[-AMNESTY_LOG_KEEP:])
    return True, '', entry


def undo_amnesty(gid, amnesty_id, at=None):
    gid = _gid_str(gid)
    log = load_amnesty_log(gid)
    entry = None
    for a in log:
        if a.get('id') == amnesty_id:
            entry = a
            break
    if entry is None:
        return False, 'Запись амнистии не найдена', 0
    if entry.get('restored_at'):
        return False, 'Амнистия уже откачена', 0
    raw = _load_json('data/warnings.json', {})
    if not isinstance(raw, dict):
        raw = {}
    try:
        gmap = raw[gid]
    except KeyError:
        gmap = {}
        raw[gid] = gmap
    if not isinstance(gmap, dict):
        gmap = {}
        raw[gid] = gmap
    cur = gmap.get(entry['user_id'])
    if isinstance(cur, list) and any(isinstance(w, dict) for w in cur):
        return False, 'После амнистии появились новые варны', 0
    gmap[entry['user_id']] = entry.get('warns') or []
    _save_json('data/warnings.json', raw)
    entry['restored_at'] = at or _now_iso()
    _save_json(_amnesty_path(gid), log)
    return True, '', len(entry.get('warns') or [])


# ─────────────────────────────────────────────────────────────────────
# #37: Радар истечений — что просрочено и что заканчивается
# ─────────────────────────────────────────────────────────────────────
def load_temp_actions(gid):
    """Активные временные наказания сервера из файлов temp_moderation-кога."""
    gid = _gid_str(gid)
    rows = []
    for kind, kind_name, fname in TEMP_KIND_FILES:
        raw = _load_json('data/%s' % fname, {})
        gmap = raw.get(gid) if isinstance(raw, dict) else None
        if not isinstance(gmap, dict):
            continue
        for uid, info in gmap.items():
            if not isinstance(info, dict):
                continue
            try:
                until = float(info.get('until'))
            except (TypeError, ValueError) as _ex:
                _log.debug("mod_control: битый until в %s: %s", fname, _ex)
                continue
            created = info.get('created_at')
            try:
                created = float(created) if created is not None else None
            except (TypeError, ValueError):
                created = None
            rows.append({
                'kind': kind,
                'kind_name': kind_name,
                'user_id': str(uid),
                'until': until,
                'created_at': created,
                'reason': str(info.get('reason') or '').strip(),
                'mod_id': str(info.get('mod_id') or ''),
            })
    return rows


def expiry_radar(rows, now=None):
    """Бакеты просрочено / 24ч / 3 суток / позже + строки срочных для таблицы."""
    now = float(now if now is not None else time.time())
    out = {'counts': {'overdue': 0, 'soon': 0, 'week': 0, 'later': 0},
           'rows': [], 'active_total': 0}
    for r in rows or []:
        remaining = r['until'] - now
        out['active_total'] += 1
        if remaining <= 0:
            bucket = 'overdue'
        elif remaining <= RADAR_SOON_S:
            bucket = 'soon'
        elif remaining <= RADAR_WEEK_S:
            bucket = 'week'
        else:
            bucket = 'later'
        out['counts'][bucket] += 1
        if bucket == 'later':
            continue
        created = r.get('created_at')
        if created is not None and r['until'] > created:
            frac = (now - created) / (r['until'] - created)
            frac = max(0.0, min(1.0, frac))
        else:
            frac = None
        row = dict(r)
        row['remaining_s'] = int(remaining)
        row['frac'] = frac
        out['rows'].append(row)
    out['rows'].sort(key=lambda r: r['until'])
    return out


# ─────────────────────────────────────────────────────────────────────
# Маршруты
# ─────────────────────────────────────────────────────────────────────
def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _json():
        return request.get_json(silent=True) or {}

    @app.route('/mod-control')
    @login_required
    @role_required('mod')
    def mod_control_page():
        return render_template('mod_control.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/mod-control/overview')
    @login_required
    @role_required('mod')
    def api_mod_control_overview(gid):
        names = names_from_audit(gid)
        steps = load_warn_steps(gid)
        items = at_risk_users(load_warns_map(gid), steps, names=names)
        radar_rows = load_temp_actions(gid)
        for r in radar_rows:
            r['name'] = names.get(r['user_id'], '')
        amnesty_log = load_amnesty_log(gid)
        return jsonify({
            'success': True,
            'reason_kinds': [{'key': k, 'label': REASON_KIND_LABELS[k]} for k in REASON_KINDS],
            'reasons': load_reasons(gid),
            'risk': {
                'tuned': bool(steps),
                'steps': steps,
                'items': items,
                'edge': sum(1 for r in items if r['gap'] == 1),
            },
            'radar': expiry_radar(radar_rows),
            'amnesty': [public_amnesty(a, gid) for a in reversed(amnesty_log)][:10],
            'amnesty_total': len(amnesty_log),
            'can_edit': session.get('role') in ('admin', 'owner'),
        })

    @app.route('/api/guild/<gid>/mod-control/reasons', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_control_reason_add(gid):
        data = _json()
        ok, err, item = add_reason(gid, data.get('kind'), data.get('text'),
                                   by=session.get('username'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, 'item': item, 'reasons': load_reasons(gid)})

    @app.route('/api/guild/<gid>/mod-control/reasons/<kind>/<int:rid>/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_control_reason_delete(gid, kind, rid):
        ok, err, removed = remove_reason(gid, kind, rid)
        if not ok:
            code = 404 if err == 'Причина не найдена' else 400
            return jsonify({'success': False, 'error': err}), code
        return jsonify({'success': True, 'removed': removed, 'reasons': load_reasons(gid)})

    @app.route('/api/guild/<gid>/mod-control/amnesty', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_control_amnesty(gid):
        # Классическое разрешение: амнистия снимает ВСЕ варны — тот же
        # тумблер «Варн» (как у /unwarn и /clearwarns).
        import web.app as _app
        from web.routes._common import viewer_member, acl_action_allowed
        _bot = _app.bot_instance
        _member = viewer_member(_bot, gid) if _bot is not None else None
        if not acl_action_allowed(gid, _member, 'warn'):
            return jsonify({'success': False,
                            'error': 'Нет права: «Варн» не разрешено вашей '
                                     'роли (настройка — «Права команд»)'}), 403
        data = _json()
        ok, err, entry = amnesty_user(gid, data.get('user_id'), by=session.get('username'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, 'amnesty': public_amnesty(entry)})

    @app.route('/api/guild/<gid>/mod-control/amnesty/<int:aid>/undo', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_mod_control_amnesty_undo(gid, aid):
        ok, err, restored = undo_amnesty(gid, aid)
        if not ok:
            code = 404 if err == 'Запись амнистии не найдена' else 400
            return jsonify({'success': False, 'error': err}), code
        return jsonify({'success': True, 'restored': restored})
