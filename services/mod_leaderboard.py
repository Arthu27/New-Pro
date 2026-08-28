# -*- coding: utf-8 -*-
"""Эффективность модераторов: композитный рейтинг команды (0–100).

Четыре прозрачных источника, веса в сумме 100:
- активность (30)      — действия модерации из аудита за N дней (цель 30)
- скорость (30)        — среднее время до решения апелляции (0 ч = 30, 48 ч+ = 0)
- звёзды (25)          — средний балл /оценить (staff_rating), id → имя
                         через общую карту имён
- справедливость (15)  — оценки «помогли/не помогли» по апелляциям,
                         которые решал этот модератор

Метрики без данных — честная нейтральная половина (помечено «нет данных»),
а не ноль: иначе новичок команды выглядел бы провалившимся.
Имена сводятся по нижнему регистру (панель и Discord пишут одно имя).
"""
from datetime import datetime, timedelta, timezone

from logger import get_logger

_log = get_logger('mod_leaderboard')

UTC = timezone.utc
W = {'activity': 30, 'speed': 30, 'stars': 25, 'fairness': 15}
TARGET_ACTIONS = 30
SPEED_CAP_H = 48.0


def _row(rows, name):
    key = str(name or '').strip()
    if not key:
        return None
    return rows.setdefault(key.lower(), {
        'mod': key, 'actions': 0, 'decisions': 0, 'hours': [],
        'star_sum': 0.0, 'star_votes': 0, 'fair_up': 0, 'fair_down': 0})


def compute_leaderboard(gid, days=30, now=None):
    """Отсортированные строки рейтинга + модератор месяца (тестируемо)."""
    gid = str(gid)
    now = now or datetime.now(UTC)
    rows = {}

    # 1) активность: мод-действия из аудита за окно
    try:
        from web.routes.analytics_plus import _read_audit, _parse_ts
        cutoff = datetime.now() - timedelta(days=int(days))   # naive local — как _parse_ts
        for ev in _read_audit(gid):
            if (ev.get('category') or '').lower() != 'mod':
                continue
            ts = _parse_ts(ev.get('timestamp'))
            if ts is None or ts < cutoff:
                continue
            r = _row(rows, ev.get('mod_name'))
            if r is not None:
                r['actions'] += 1
    except Exception as _ex:
        _log.debug('leaderboard: аудит: %s', _ex)

    # 2) апелляции: решения, скорость, справедливость
    try:
        from db import GuildData
        from cogs import appeals as AP
        state = GuildData('appeals').get(gid, 'state', {}) or {}
        for it in state.get('items', []):
            mod = str(it.get('reviewed_by') or '').strip()
            if not mod or mod.startswith('Discord'):
                continue
            if not it.get('reviewed_at'):
                continue
            r = _row(rows, mod)
            if r is None:
                continue
            r['decisions'] += 1
            created = AP._parse_ts(it.get('created_at'))
            reviewed = AP._parse_ts(it.get('reviewed_at'))
            if created is not None and reviewed is not None:
                r['hours'].append(
                    max(0.0, (reviewed - created).total_seconds() / 3600))
            if it.get('rating') == 'up':
                r['fair_up'] += 1
            elif it.get('rating') == 'down':
                r['fair_down'] += 1
    except Exception as _ex:
        _log.debug('leaderboard: апелляции: %s', _ex)

    # 3) звёзды: staff_rating, staff_id → имя через общую карту
    try:
        from db import GuildData
        from cogs import staff_rating as SR
        from web.routes.mod_control import names_from_audit
        state = GuildData('staff_rating').get(gid, 'state', {}) or {}
        names = names_from_audit(gid)
        for uid, avg, n_votes in SR.rating_rows(state, limit=50):
            name = names.get(str(uid)) or str(uid)
            r = _row(rows, name)
            if r is not None and n_votes:
                r['star_sum'] += avg * n_votes
                r['star_votes'] += n_votes
    except Exception as _ex:
        _log.debug('leaderboard: звёзды: %s', _ex)

    out = []
    for r in rows.values():
        hours = r['hours']
        avg_h = round(sum(hours) / len(hours), 1) if hours else None
        stars = (round(r['star_sum'] / r['star_votes'], 2)
                 if r['star_votes'] else None)
        fair_votes = r['fair_up'] + r['fair_down']
        fair_pct = (round(100 * r['fair_up'] / fair_votes)
                    if fair_votes else None)

        activity_pts = min(1.0, r['actions'] / TARGET_ACTIONS) * W['activity']
        speed_pts = (W['speed'] * max(0.0, 1 - min(avg_h, SPEED_CAP_H) / SPEED_CAP_H)
                     if avg_h is not None else W['speed'] / 2)
        stars_pts = (W['stars'] * stars / 5
                     if stars is not None else W['stars'] / 2)
        fairness_pts = (W['fairness'] * fair_pct / 100
                        if fair_pct is not None else W['fairness'] / 2)
        score = round(activity_pts + speed_pts + stars_pts + fairness_pts)

        out.append({
            'mod': r['mod'],
            'actions': r['actions'],
            'decisions': r['decisions'],
            'avg_hours': avg_h,
            'stars': stars,
            'star_votes': r['star_votes'],
            'fair_pct': fair_pct,
            'score': score,
            'no_data': sum(1 for v in (avg_h, stars, fair_pct) if v is None),
        })
    out.sort(key=lambda x: (-x['score'], x['mod']))
    for i, r in enumerate(out, 1):
        r['rank'] = i

    best = None
    if out and (out[0]['actions'] > 0 or out[0]['decisions'] > 0) \
            and out[0]['score'] >= 50:
        best = out[0]['mod']
    return {'rows': out, 'days': int(days), 'mod_of_month': best,
            'total_mods': len(out)}
