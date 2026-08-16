# -*- coding: utf-8 -*-
"""Мод-анализ (идеи #38-40): досье участника, эффективность наказаний,
чек-лист готовности модерации.

Всё поверх уже существующих данных бота, без своих дублей хранилищ:
- data/warnings.json и data/warn_config_<gid>.json — варны и пороги
  (читаем через функции mod_control, ключи 1:1 с cogs/warnings.py);
- data/audit_log.json — наказания (категория 'mod'; единственные кары,
  которые пишет бот: Мут/Кик/Бан + снятия);
- data/temp_*.json — активные временные статусы (cogs/temp_moderation.py);
- data/mod_amnesty_<gid>.json — журнал амнистий (Мод-контроль, #36);
- data/member_notes.json — заметки модераторов (страница «Заметки»);
- data/autofilter_<gid>.json / data/antiraid_<gid>.json — конфиги защит.

Чтение — mod+ (как весь раздел «Модерация»). Своих мутаций нет.
"""
import time
from collections import Counter
from datetime import datetime, timedelta

from web.routes._common import (
    _log,
    render_template, session, request, jsonify,
)

from web.routes.analytics_plus import _parse_ts, _read_audit
from web.routes.mod_control import (
    _gid_str, _load_json, validate_user_id,
    names_from_audit, load_warns_map, load_warn_steps, at_risk_users,
    load_temp_actions, load_amnesty_log, public_amnesty, load_reasons,
)

# Единственные карательные действия, которые cogs/logs.py пишет в аудит;
# снятия («Мут снят»/«Бан снят») идут отдельным типом событий таймлайна.
PUNISH_ACTIONS = ('Мут', 'Кик', 'Бан')
LIFT_ACTIONS = ('Мут снят', 'Бан снят')

SUBJECTS_LIMIT = 30
DOSSIER_TIMELINE_LIMIT = 20
DOSSIER_NOTES_LIMIT = 5
DOSSIER_WARNS_LIMIT = 3

EFFECT_MIN_SAMPLE = 5
EFFECT_DEFAULT_DAYS = 90

CHECK_AUDIT_FRESH_DAYS = 14

ANTIRAID_TOGGLES = ('join_raid', 'bot_protection', 'webhook_protection',
                    'delete_protection', 'age_filter')
ANTIRAID_LABELS = {'join_raid': 'рейды заходов', 'bot_protection': 'боты',
                   'webhook_protection': 'вебхуки', 'delete_protection': 'удаления',
                   'age_filter': 'молодые аккаунты'}


def _norm_days(value, default):
    """Окно в днях из параметра/вызова: целое в пределах 7..365."""
    try:
        days = int(value)
    except (TypeError, ValueError):
        days = default
    return min(365, max(7, days))


def mod_events(gid):
    """(dt, action, user_id, ev) mod-события аудита, по возрастанию времени."""
    out = []
    for ev in _read_audit(gid):
        if ev.get('category') != 'mod':
            continue
        dt = _parse_ts(ev.get('timestamp'))
        if dt is None:
            continue
        out.append((dt, str(ev.get('action') or ''),
                    str(ev.get('user_id') or '').strip(), ev))
    out.sort(key=lambda t: (t[0], t[2]))
    return out


# ─────────────────────────────────────────────────────────────────────
# #38: Кто чаще наказывается (список для выбора досье)
# ─────────────────────────────────────────────────────────────────────
def subjects(gid, limit=SUBJECTS_LIMIT):
    """Люди со варнами/наказаниями: вес = варны + кары, сортировка по нему."""
    warns_map = load_warns_map(gid)
    names = names_from_audit(gid)
    punish = Counter()
    last_at = {}
    for dt, action, uid, _ev in mod_events(gid):
        if not uid or action not in PUNISH_ACTIONS:
            continue
        punish[uid] += 1
        last_at[uid] = dt
    rows = []
    for uid in set(warns_map) | set(punish):
        warns = len(warns_map.get(uid, []))
        rows.append({
            'user_id': uid,
            'name': str(names.get(uid) or ''),
            'warns': warns,
            'punishments': punish.get(uid, 0),
            'weight': warns + punish.get(uid, 0),
            'last_at': last_at[uid].isoformat(timespec='minutes') if uid in last_at else None,
        })
    rows.sort(key=lambda r: (-r['weight'], -r['punishments'], r['user_id']))
    try:
        lim = int(limit)
    except (TypeError, ValueError) as _ex:
        _log.debug("mod_insights: битый лимит subjects: %s", _ex)
        lim = SUBJECTS_LIMIT
    return {
        'items': rows[:max(1, lim)],
        'total': len(rows),
        'warns_open': sum(len(v) for v in warns_map.values()),
    }


def load_member_notes(user_id):
    """Заметки модераторов из member_notes.json (глобальный по member_id)."""
    raw = _load_json('data/member_notes.json', {})
    if not isinstance(raw, dict):
        return []
    entry = raw.get(str(user_id))
    if not isinstance(entry, dict):
        return []
    out = []
    for n in (entry.get('notes') or []):
        if not isinstance(n, dict):
            continue
        text = str(n.get('note') or n.get('text') or '').strip()
        if not text:
            continue
        out.append({
            'note': text,
            'at': str(n.get('timestamp') or n.get('at') or n.get('date') or '')[:10],
            'mod': str(n.get('mod') or n.get('by') or n.get('author') or ''),
        })
    out.reverse()
    return out[:DOSSIER_NOTES_LIMIT]


def dossier(gid, user_id, now=None, now_ts=None):
    """Досье участника: варны, до-порога, кары таймлайном, активные статусы.

    now — datetime для «дней с последнего»; now_ts — unix-время для
    сравнения со сроками temp-файлов (раздельно ради детерминизма тестов).
    """
    ok, err, uid = validate_user_id(user_id)
    if not ok:
        return False, err, None
    gid = _gid_str(gid)
    now = now or datetime.now()
    if now_ts is None:
        now_ts = time.time()

    warns_map = load_warns_map(gid)
    warns = warns_map.get(uid, [])
    risk = at_risk_users({uid: warns}, load_warn_steps(gid), limit=1)
    names = names_from_audit(gid)

    timeline = []
    punish = 0
    lifts = 0
    last_dt = None
    for dt, action, euid, ev in mod_events(gid):
        if euid != uid:
            continue
        if action in PUNISH_ACTIONS:
            kind = 'punish'
            punish += 1
        elif action in LIFT_ACTIONS:
            kind = 'lift'
            lifts += 1
        else:
            continue
        last_dt = dt
        timeline.append({
            'action': action,
            'kind': kind,
            'reason': str(ev.get('reason') or '').strip(),
            'mod_name': str(ev.get('mod_name') or '').strip(),
            'at': dt.isoformat(timespec='minutes'),
        })
    timeline.reverse()
    timeline = timeline[:DOSSIER_TIMELINE_LIMIT]

    temp_active = []
    for r in load_temp_actions(gid):
        if r['user_id'] != uid or r['until'] <= now_ts:
            continue
        row = dict(r)
        row['remaining_s'] = int(r['until'] - now_ts)
        temp_active.append(row)
    temp_active.sort(key=lambda r: r['until'])

    amnesty = [public_amnesty(a) for a in reversed(load_amnesty_log(gid))
               if str(a.get('user_id') or '') == uid]
    notes = load_member_notes(uid)
    warn_items = [{
        'reason': str(w.get('reason') or '').strip() or 'Без причины',
        'at': str(w.get('timestamp') or '')[:10],
        'mod': str(w.get('mod') or ''),
    } for w in warns[-DOSSIER_WARNS_LIMIT:][::-1]]

    return True, '', {
        'user_id': uid,
        'name': str(names.get(uid) or ''),
        'known': bool(warns or timeline or temp_active or amnesty or notes),
        'warns': {
            'count': len(warns),
            'items': warn_items,
            'gap': risk[0]['gap'] if risk else None,
            'next_count': risk[0]['next_count'] if risk else None,
            'action_name': risk[0]['action_name'] if risk else None,
        },
        'temp_active': temp_active,
        'timeline': timeline,
        'timeline_total': punish + lifts,
        'amnesty': amnesty,
        'notes': notes,
        'stats': {
            'punishments': punish,
            'lifts': lifts,
            'warns': len(warns),
            'last_at': last_dt.isoformat(timespec='minutes') if last_dt else None,
            'days_since': max(0, (now.date() - last_dt.date()).days) if last_dt else None,
        },
    }


# ─────────────────────────────────────────────────────────────────────
# #39: Эффективность наказаний — помогает ли кара
# ─────────────────────────────────────────────────────────────────────
def punishment_effectiveness(events, now=None, days=EFFECT_DEFAULT_DAYS):
    """Доля рецидива после первого наказания участника за окно.

    «Рецидив» — второе наказание ЛЮБОГО типа: после мута смотрим, получил
    ли человек ещё кару за 7/30 дней. Выборка < EFFECT_MIN_SAMPLE помечается
    thin, чтобы панель показала «мало данных» вместо громких процентов.
    """
    days = _norm_days(days, EFFECT_DEFAULT_DAYS)
    now = now or datetime.now()
    cutoff = now - timedelta(days=days)
    seq = [(dt, action, uid) for dt, action, uid, _ev in (events or [])
           if action in PUNISH_ACTIONS and uid and dt >= cutoff]
    seq.sort(key=lambda t: (t[0], t[2]))

    firsts = {}
    for dt, action, uid in seq:
        rec = firsts.get(uid)
        if rec is None:
            firsts[uid] = (dt, action, None)
        elif rec[2] is None:
            firsts[uid] = (rec[0], rec[1], dt)

    rows = {a: {'count': 0, 'rep7': 0, 'rep30': 0, 'deltas': []} for a in PUNISH_ACTIONS}
    overall = {'count': 0, 'rep7': 0, 'rep30': 0, 'deltas': []}
    for _uid, (first_dt, first_act, second_dt) in firsts.items():
        buckets = (rows[first_act], overall)
        for b in buckets:
            b['count'] += 1
        if second_dt is None:
            continue
        delta = (second_dt - first_dt).total_seconds() / 86400.0
        for b in buckets:
            b['deltas'].append(delta)
            if delta <= 7:
                b['rep7'] += 1
            if delta <= 30:
                b['rep30'] += 1

    def _finalize(action, b):
        count = b['count']
        deltas = sorted(b['deltas'])
        median = None
        if deltas:
            mid = len(deltas) // 2
            median = deltas[mid] if len(deltas) % 2 else (deltas[mid - 1] + deltas[mid]) / 2
            median = round(median, 1)
        return {
            'action': action,
            'count': count,
            'repeats': len(deltas),
            'repeat7': round(100 * b['rep7'] / count) if count else None,
            'repeat30': round(100 * b['rep30'] / count) if count else None,
            'median_days': median,
            'thin': count < EFFECT_MIN_SAMPLE,
        }

    return {
        'days': days,
        'min_sample': EFFECT_MIN_SAMPLE,
        'types': [_finalize(a, rows[a]) for a in PUNISH_ACTIONS],
        'overall': _finalize('all', overall),
    }


# ─────────────────────────────────────────────────────────────────────
# #40: Чек-лист готовности модерации
# ─────────────────────────────────────────────────────────────────────
def _autofilter_check(gid):
    base = {'key': 'autofilter', 'title': 'Автофильтр чата',
            'link': '/autofilter', 'link_label': 'Открыть'}
    try:
        from cogs.auto_filter import cfg_path, merge_config
        path = cfg_path(gid)
    except (ImportError, TypeError, ValueError) as _ex:
        _log.debug("mod_insights: конфиг автофильтра недоступен: %s", _ex)
        return dict(base, status='missing', detail='Недоступен',
                    hint='Модуль автофильтра не загружен.')
    raw = _load_json(path, None)
    if not isinstance(raw, dict):
        return dict(base, status='warn', detail='По умолчанию',
                    hint='Работает на дефолтах — задайте собственный словарь стоп-слов.')
    cfg = merge_config(raw)
    if not cfg.get('enabled'):
        return dict(base, status='missing', detail='Выключен',
                    hint='Фильтр снят с дежурства — чат без автозащиты.')
    words = (cfg.get('words') or {}).get('list') or []
    if not words:
        return dict(base, status='warn', detail='Без словаря',
                    hint='Фильтр включён, но список стоп-слов пуст.')
    extras = sum(1 for f in ('links', 'caps', 'flood') if (cfg.get(f) or {}).get('enabled'))
    return dict(base, status='ok', detail='%d слов' % len(words),
                hint='Словарь задан; дополнительных фильтров включено: %d.' % extras)


def _antiraid_check(gid):
    base = {'key': 'antiraid', 'title': 'Анти-рейд',
            'link': '/antiraid', 'link_label': 'Открыть'}
    raw = _load_json('data/antiraid_%s.json' % gid, None)
    if not isinstance(raw, dict):
        return dict(base, status='missing', detail='Не настроен',
                    hint='Ни одна защита от рейдов не подключена.')
    on = [k for k in ANTIRAID_TOGGLES if raw.get(k)]
    if not on:
        return dict(base, status='warn', detail='Всё выключено',
                    hint='Конфиг есть, но все переключатели защиты сняты.')
    return dict(base, status='ok', detail='%d из %d' % (len(on), len(ANTIRAID_TOGGLES)),
                hint='Активно: ' + ', '.join(ANTIRAID_LABELS[k] for k in on) + '.')


def _audit_check(gid, now):
    base = {'key': 'audit_fresh', 'title': 'Журнал модерации',
            'link': '/logs', 'link_label': 'Открыть'}
    latest = None
    for ev in _read_audit(gid):
        dt = _parse_ts(ev.get('timestamp'))
        if dt is not None and (latest is None or dt > latest):
            latest = dt
    if latest is None:
        return dict(base, status='missing', detail='Пусто',
                    hint='Событий нет — проверьте, что бот на сервере и пишет логи.')
    age = max(0, (now - latest).days)
    if age > CHECK_AUDIT_FRESH_DAYS:
        return dict(base, status='warn', detail='Тихо %d дн.' % age,
                    hint='Журнал давно не пополнялся — стоит проверить связку бота.')
    detail = 'Сегодня' if age == 0 else ('Вчера' if age == 1 else '%d дн. назад' % age)
    return dict(base, status='ok', detail=detail,
                hint='Последнее событие: %s.' % latest.isoformat(timespec='minutes'))


def readiness_checklist(gid, now=None):
    """Пять проверок готовности: пороги, причины, фильтр, антирейд, журнал."""
    gid = _gid_str(gid)
    now = now or datetime.now()
    items = []

    steps = load_warn_steps(gid)
    items.append({
        'key': 'warn_steps', 'title': 'Авто-наказания за варны',
        'status': 'ok' if steps else 'missing',
        'detail': '%d пор.' % len(steps) if steps else 'Не заданы',
        'hint': 'Бот сам накажет при достижении порога варнов.',
        'link': '/warn-config', 'link_label': 'Настроить',
    })

    reasons = load_reasons(gid).get('warn') or []
    items.append({
        'key': 'warn_reasons', 'title': 'Быстрые причины',
        'status': 'ok' if reasons else 'warn',
        'detail': '%d шабл.' % len(reasons) if reasons else 'Пусто',
        'hint': 'Шаблоны причин ускоряют выдачу и делают журнал читаемым.',
        'link': '/mod-control', 'link_label': 'Добавить',
    })

    items.append(_autofilter_check(gid))
    items.append(_antiraid_check(gid))
    items.append(_audit_check(gid, now))

    counts = Counter(it['status'] for it in items)
    return {'items': items, 'ok': counts.get('ok', 0),
            'warn': counts.get('warn', 0), 'missing': counts.get('missing', 0),
            'total': len(items)}


# ─────────────────────────────────────────────────────────────────────
# Маршруты
# ─────────────────────────────────────────────────────────────────────
def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    @app.route('/mod-insights')
    @login_required
    @role_required('mod')
    def mod_insights_page():
        return render_template('mod_insights.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/mod-insights/overview')
    @login_required
    @role_required('mod')
    def api_mod_insights_overview(gid):
        days = _norm_days(request.args.get('days'), EFFECT_DEFAULT_DAYS)
        return jsonify({
            'success': True,
            'subjects': subjects(gid),
            'effectiveness': punishment_effectiveness(mod_events(gid), days=days),
            'checklist': readiness_checklist(gid),
        })

    @app.route('/api/guild/<gid>/mod-insights/dossier')
    @login_required
    @role_required('mod')
    def api_mod_insights_dossier(gid):
        ok, err, data = dossier(gid, request.args.get('user_id'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, 'dossier': data})
