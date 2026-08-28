# -*- coding: utf-8 -*-
"""Индекс здоровья сервера (0–100) для дашборда.

Шесть факторов с прозрачными весами (в сумме 100) — каждый показывается
отдельной полосой, так что цифра объяснима, а не магическая:

1. Очередь апелляций          20  просроченные дела (stale) съедают вес
2. Оценки рассмотрения        15  % положительных оценок апелляций
3. Нагрузка наказаний         20  активные временные мьют/бан/кик
4. Открытые репорты           15  незакрытые тикеты из /report
5. Активность модерации       15  действия команды за 7 дней (аудит)
6. Оценки команды             15  средний балл /оценить (staff_rating)

Факторы 2 и 6 без данных честно нейтральны (половина веса), а не ноль —
иначе молодой сервер выглядел бы больным. Всё fail-safe: пустые файлы =
зелёные факторы, ошибка чтения = нейтральная половина с пометкой.
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone

from logger import get_logger

_log = get_logger('health_index')

UTC = timezone.utc
TEMP_FILES = ('data/temp_mutes.json', 'data/temp_bans.json',
              'data/temp_vmutes.json', 'data/temp_kicks.json')

W = {'appeals': 20, 'ratings': 15, 'punishments': 20,
     'reports': 15, 'activity': 15, 'staff': 15}


def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (json.JSONDecodeError, ValueError, OSError) as _ex:
        _log.debug('health: чтение %s: %s', path, _ex)
        return default


def _factor(key, label, icon, points, detail, max_pts=None):
    max_pts = max_pts if max_pts is not None else W[key]
    return {'key': key, 'label': label, 'icon': icon,
            'points': round(points, 1), 'max': max_pts,
            'pct': round(100 * points / max_pts) if max_pts else 0,
            'detail': detail}


def _appeals_factor(gid, now):
    try:
        from db import GuildData
        from cogs import appeals as AP
        state = GuildData('appeals').get(gid, 'state', AP.empty_state()) \
            or AP.empty_state()
        settings = AP.settings_of(state)
        pend = AP.pending_items(state)
        edge = now - timedelta(hours=settings['stale_hours'])
        stale = sum(1 for it in pend
                    if (AP._parse_ts(it.get('created_at')) or now) <= edge)
        if not pend:
            pts, detail = W['appeals'], 'очередь чиста'
        else:
            pts = max(0.0, 1 - stale / len(pend)) * W['appeals']
            detail = f'{len(pend)} ждут · просрочено {stale}'
        up = sum(1 for i in state.get('items', []) if i.get('rating') == 'up')
        down = sum(1 for i in state.get('items', [])
                   if i.get('rating') == 'down')
        votes = up + down
        if votes:
            pts_r = W['ratings'] * up / votes
            detail_r = f'{up} за · {down} против'
        else:
            pts_r, detail_r = W['ratings'] / 2, 'оценок пока нет'
        return (_factor('appeals', 'Очередь апелляций', 'fa-scale-balanced',
                        pts, detail),
                _factor('ratings', 'Оценки рассмотрения', 'fa-face-smile',
                        pts_r, detail_r))
    except Exception as _ex:
        _log.debug('health: апелляции: %s', _ex)
        half_a, half_r = W['appeals'] / 2, W['ratings'] / 2
        return (_factor('appeals', 'Очередь апелляций', 'fa-scale-balanced',
                        half_a, 'данные недоступны'),
                _factor('ratings', 'Оценки рассмотрения', 'fa-face-smile',
                        half_r, 'данные недоступны'))


def _punishments_factor(gid, now_ts):
    try:
        active = 0
        for path in TEMP_FILES:
            data = _read_json(path, {})
            now_f = time.time() if now_ts is None else now_ts
            for rec in (data.get(gid) or {}).values():
                try:
                    if isinstance(rec, dict) and float(rec.get('until') or 0) > now_f:
                        active += 1
                except (TypeError, ValueError):
                    continue
        pts = max(0.0, W['punishments'] - 2 * active)
        detail = 'нет активных наказаний' if not active \
            else f'активных: {active}'
        return _factor('punishments', 'Нагрузка наказаний', 'fa-gavel',
                       pts, detail)
    except Exception as _ex:
        _log.debug('health: наказания: %s', _ex)
        return _factor('punishments', 'Нагрузка наказаний', 'fa-gavel',
                       W['punishments'] / 2, 'данные недоступны')


def _reports_factor(gid):
    try:
        from services import reports_core as RC
        open_n = RC.ticket_stats(gid).get('open', 0)
        pts = max(0.0, W['reports'] - 5 * open_n)
        detail = 'репортов в очереди нет' if not open_n \
            else f'открыто: {open_n}'
        return _factor('reports', 'Открытые репорты', 'fa-flag', pts, detail)
    except Exception as _ex:
        _log.debug('health: репорты: %s', _ex)
        return _factor('reports', 'Открытые репорты', 'fa-flag',
                       W['reports'] / 2, 'данные недоступны')


def _activity_factor(gid, now):
    try:
        from web.routes.analytics_plus import _read_audit, _parse_ts, _AUDIT_FILE
        if not os.path.exists(_AUDIT_FILE):
            # аудита ещё нет — судить об активности рано, честная половина
            return _factor('activity', 'Активность модерации', 'fa-bolt',
                           W['activity'] / 2, 'нет данных аудита')
        # _parse_ts отдаёт naive local — окно считаем в той же конвенции
        week_ago = datetime.now() - timedelta(days=7)
        n = 0
        for ev in _read_audit(gid):
            if (ev.get('category') or '').lower() != 'mod':
                continue
            ts = _parse_ts(ev.get('timestamp'))
            if ts is not None and ts >= week_ago:
                n += 1
        pts = min(1.0, n / 10) * W['activity']
        detail = f'{n} действий за 7 дней' if n else 'тишина за 7 дней'
        return _factor('activity', 'Активность модерации', 'fa-bolt',
                       pts, detail)
    except Exception as _ex:
        _log.debug('health: активность: %s', _ex)
        return _factor('activity', 'Активность модерации', 'fa-bolt',
                       W['activity'] / 2, 'данные недоступны')


def _staff_factor(gid):
    try:
        from db import GuildData
        from cogs import staff_rating as SR
        state = GuildData('staff_rating').get(gid, 'state', {}) or {}
        rows = SR.rating_rows(state, limit=50)
        if rows:
            votes = sum(r[2] for r in rows)
            avg = sum(r[1] * r[2] for r in rows) / votes
            pts = W['staff'] * avg / 5
            detail = f'{round(avg, 2)} из 5 · голосов {votes}'
        else:
            pts, detail = W['staff'] / 2, 'голосов за команду нет'
        return _factor('staff', 'Оценки команды', 'fa-star', pts, detail)
    except Exception as _ex:
        _log.debug('health: команда: %s', _ex)
        return _factor('staff', 'Оценки команды', 'fa-star',
                       W['staff'] / 2, 'данные недоступны')


def compute_health(gid, now=None):
    """Итоговый индекс: score, тон, ярлык и разложение по факторам."""
    gid = str(gid)
    now = now or datetime.now(UTC)
    now_ts = time.time()
    f_appeals, f_ratings = _appeals_factor(gid, now)
    factors = [f_appeals, f_ratings,
               _punishments_factor(gid, now_ts),
               _reports_factor(gid),
               _activity_factor(gid, now),
               _staff_factor(gid)]
    score = max(0, min(100, round(sum(f['points'] for f in factors))))
    if score >= 80:
        label, tone = 'Отличное здоровье', 'ok'
    elif score >= 60:
        label, tone = 'Стабильное', 'info'
    elif score >= 40:
        label, tone = 'Есть над чем работать', 'warn'
    else:
        label, tone = 'Требует внимания', 'err'
    return {'score': score, 'label': label, 'tone': tone,
            'factors': factors,
            'hint': _hint_for(factors)}


def _hint_for(factors):
    """Главная болячка одной строкой — куда смотреть в первую очередь."""
    worst = min(factors, key=lambda f: f['pct'])
    tips = {
        'appeals': 'Разберите просроченные апелляции в очереди «Апелляций».',
        'ratings': 'Люди недовольны рассмотрением — проверьте ответы модерации.',
        'punishments': 'Много активных наказаний — загляните в «Расписание».',
        'reports': 'Незакрытые репорты ждут решения в разделе «Репорты».',
        'activity': 'Команда молчит неделю — проверьте смены модераторов.',
        'staff': 'Попросите участников оценить работу команды (/оценить).',
    }
    if worst['pct'] >= 70:
        return 'Всё под контролем — держите темп.'
    return tips.get(worst['key'], '')
