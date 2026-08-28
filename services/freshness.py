# -*- coding: utf-8 -*-
"""Авто-остывание статуса нарушителя («свежесть»).

Идея: прошло N дней без нарушений — «горячий» статус сам теплеет, потом
остывает. Ничего не удаляем и не переписываем: это вычисляемое представление
поверх тех же варнов (data/warnings.json) и аудита (data/audit_log.json).

Пороги — отдельный панельный файл data/freshness_config_<gid>.json
(свой, потому что warn_config_<gid>.json целиком пересобирается страницей
лестницы — там наши ключи потерялись бы):
- warm_days (по умолчанию 14) — после стольких чистых дней статус «тёплый»
- cold_days (по умолчанию 45) — после стольких «холодный — скорее всего, исправился»

Показывается в карточке 360° (Пользователи) полоской остывания.
"""
import json
import os

from logger import get_logger

_log = get_logger('freshness')

DEFAULT_WARM_DAYS = 14
DEFAULT_COLD_DAYS = 45
MAX_DAYS = 365

LEVELS = {
    'hot': ('Горячий', 'tone-warning'),
    'warm': ('Тёплый', 'tone-info'),
    'cold': ('Холодный', 'tone-ok'),
    'clean': ('Чистый', 'ok'),
}


def _clamp(raw, default, lo, hi):
    if raw is None:
        return default
    try:
        return max(lo, min(int(raw), hi))
    except (TypeError, ValueError):
        return default


def config_path(gid):
    return f'data/freshness_config_{gid}.json'


def cooldown_config(gid):
    """{'warm_days', 'cold_days'} — cold всегда строго больше warm."""
    cfg = {}
    path = config_path(gid)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg = data
        except (json.JSONDecodeError, OSError) as _ex:
            _log.debug('freshness: конфиг %s: %s', path, _ex)
    warm = _clamp(cfg.get('warm_days'), DEFAULT_WARM_DAYS, 1, MAX_DAYS - 1)
    cold = _clamp(cfg.get('cold_days'), DEFAULT_COLD_DAYS, 2, MAX_DAYS)
    if cold <= warm:
        cold = min(warm + 1, MAX_DAYS)
    return {'warm_days': warm, 'cold_days': cold}


def save_cooldown_config(gid, warm_days, cold_days):
    """Сохранить пороги; вернуть (конфиг, ошибка)."""
    warm = _clamp(warm_days, DEFAULT_WARM_DAYS, 1, MAX_DAYS - 1)
    cold = _clamp(cold_days, DEFAULT_COLD_DAYS, 2, MAX_DAYS)
    if cold <= warm:
        return None, '«Холодный» должен наступать позже «тёплого»'
    cfg = {'warm_days': warm, 'cold_days': cold}
    try:
        os.makedirs('data', exist_ok=True)
        with open(config_path(gid), 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False)
    except OSError as _ex:
        _log.debug('freshness: запись конфига: %s', _ex)
        return None, 'Не удалось записать настройки'
    return cfg, None


def _ts_of(value):
    """ISO-строка/epoch → naive local datetime или None."""
    if not value:
        return None
    try:
        from web.routes.analytics_plus import _parse_ts
        return _parse_ts(value)
    except Exception:
        return None


def last_violation_dt(gid, uid):
    """Свежайшее нарушение: максимум меток из варнов и мод-аудита."""
    uid = str(uid)
    latest = None

    def bump(dt):
        nonlocal latest
        if dt is not None and (latest is None or dt > latest):
            latest = dt

    try:
        from web.routes.mod_control import load_warns_map
        for w in load_warns_map(gid).get(uid, []):
            bump(_ts_of(w.get('timestamp') or w.get('ts') or w.get('at')))
    except Exception as _ex:
        _log.debug('freshness: варны: %s', _ex)
    try:
        from web.routes.analytics_plus import _read_audit
        for ev in _read_audit(gid):
            if (ev.get('category') or '').lower() != 'mod':
                continue
            if str(ev.get('user_id') or '') != uid:
                continue
            bump(_ts_of(ev.get('timestamp')))
    except Exception as _ex:
        _log.debug('freshness: аудит: %s', _ex)
    return latest


def freshness_of(gid, uid, now=None):
    """Уровень остывания участника + прогресс до следующего уровня.

    Возвращает {'level', 'label', 'tone', 'days_without', 'progress',
    'to_next', 'cooldown_days'}; у чистого — days_without=None.
    """
    from datetime import datetime
    cfg = cooldown_config(gid)
    last = last_violation_dt(gid, uid)
    if last is None:
        label, tone = LEVELS['clean']
        return {'level': 'clean', 'label': label, 'tone': tone,
                'days_without': None, 'progress': 100, 'to_next': None,
                'cooldown_days': cfg['cold_days']}
    now = now or datetime.now()   # naive local — как метки в файлах
    days = max(0, (now - last).days)
    warm, cold = cfg['warm_days'], cfg['cold_days']
    if days < warm:
        level = 'hot'
        progress = round(100 * days / warm)
        to_next = f'до «тёплого» — {warm - days} дн.'
    elif days < cold:
        level = 'warm'
        progress = round(100 * (days - warm) / max(1, cold - warm))
        to_next = f'до «холодного» — {cold - days} дн.'
    else:
        level = 'cold'
        progress = 100
        to_next = 'статус остыл полностью'
    label, tone = LEVELS[level]
    return {'level': level, 'label': label, 'tone': tone,
            'days_without': days, 'progress': progress,
            'to_next': to_next, 'cooldown_days': cfg['cold_days']}
