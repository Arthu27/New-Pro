# -*- coding: utf-8 -*-
"""Разовый «чистый старт» по заказу владельца (2026-08).

Сценарий: хозяин попросил (а) стереть данные бота о логах и историях
серверов и (б) ГАРАНТИРОВАННО выключить всю защиту — «скоро сами будем
настройки включать», чтобы больше не было «почему он за спам отлетел».

Проблема: opt-in дефолты (b8e2c5a) помогают только НОВЫМ конфигам, а
старые файлы защиты на диске могли остаться со времён эпохи «всё включено
из коробки» — с enabled: true. Кнопка «Выключить всё» в центре
безопасности это чинит, но её надо нажать. Эта миграция делает то же
самое АВТОМАТИЧЕСКИ, один раз, при запуске бота.

Что делает (маркер data/.freshstart_v1.json защищает от повтора):
  1) Гасит флаги enabled во ВСЕХ найденных сторах защиты — файловых
     (security/antifake/autofilter/guardian/ai_moderation/antiraid)
     и в базе (GuildData 'anti_alt'). Пороги и белые списки НЕ трогаем:
     хозяин включит систему — и она заработает с прежними настройками.
  2) Удаляет логи/истории (audit/dm/login/panel-логи, кейсы модерации,
     варны, страйки, message_logs, night_summary и т.п.).
  3) Пишет маркер со сводкой. Всё, что хозяин включит ПОСЛЕ этого,
     миграция уже никогда не трогает (маркер есть — выход сразу).
"""
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone

_log = logging.getLogger(__name__)

MARKER = '.freshstart_v1.json'

# --- Логи и истории: сносим целиком, файлы пересоздадутся пустыми ------
WIPE_FILES = (
    'audit_log.json',            # журнал действий сервера
    'audit_log_backup.json',
    'dm_log.json',               # логи ЛС
    'login_log.json',            # входы в панель
    'panel_logs.json',           # журнал панели
    'mod_data.json',             # история кейсов модерации
    'mod_advanced_data.json',
    'warnings.json',             # история предупреждений
    'night_summary.json',
    'notification_history.json', # история уведомлений
    'antifake_strikes.json',     # страйки анти-фейка
    'anticrash_stats.json',      # статистика крашей
)
# Файловые префиксы (за ними идёт <gid>.json): протоколы наказаний и логи сообщений
WIPE_PREFIXES = ('modproof_', 'message_logs')

# --- Никогда не трогаем: иначе владелец потеряет доступ к панели -------
KEEP_FILES = (
    'panel_credentials.json', 'panel_credentials.txt',
    'flask_secret.key', 'tunnel_url.txt',
    MARKER,
    # bot.db и настройки уведомлений — не логи, оставляем
)

# --- Сторы защиты: гасим только флаги ----------------------------------
SECURITY_FEATURE_KEYS = ('ai_spam', 'fake_account', 'link_scanner')
AUTOFILTER_SECTIONS = ('words', 'links', 'caps', 'flood')
ANTIRAID_FLAGS = ('join_raid', 'bot_protection', 'webhook_protection',
                  'delete_protection', 'age_filter')


def _write_atomic(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _read_json(path, default):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except Exception as _ex:
        _log.debug('fresh_start: не прочитал %s: %s', path, _ex)
        return default


def _disable_file_stores(data_dir, flipped):
    """enabled: False во всех конфигах защиты, что найдутся в data/."""
    try:
        names = os.listdir(data_dir)
    except Exception:
        return

    def seen(name):
        if name not in flipped:
            flipped.append(name)

    for fn in names:
        path = os.path.join(data_dir, fn)
        if not fn.endswith('.json') or not os.path.isfile(path):
            continue

        # security_<gid>.json — центр безопасности (3 флага)
        if fn.startswith('security_'):
            cfg = _read_json(path, None)
            if isinstance(cfg, dict):
                changed = False
                for key in SECURITY_FEATURE_KEYS:
                    if cfg.get(key):
                        cfg[key] = False
                        changed = True
                if changed:
                    _write_atomic(path, cfg)
                    seen('security')

        # antifake.json — анти-фейк + имперсонация, формат {gid: cfg}
        elif fn == 'antifake.json':
            data = _read_json(path, None)
            if isinstance(data, dict) and data:
                changed = False
                for gid, cfg in data.items():
                    if isinstance(cfg, dict) and cfg.get('enabled'):
                        cfg['enabled'] = False
                        changed = True
                if changed:
                    _write_atomic(path, data)
                    seen('antifake')

        # autofilter_<gid>.json — корень + секции words/links/caps/flood
        elif fn.startswith('autofilter_'):
            cfg = _read_json(path, None)
            if isinstance(cfg, dict):
                changed = False
                if cfg.get('enabled'):
                    cfg['enabled'] = False
                    changed = True
                for sect in AUTOFILTER_SECTIONS:
                    sub = cfg.get(sect)
                    if isinstance(sub, dict) and sub.get('enabled'):
                        sub['enabled'] = False
                        changed = True
                if changed:
                    _write_atomic(path, cfg)
                    seen('auto_filter')

        # guardian_<gid>.json — щит от нюка (глобальный enabled)
        elif fn.startswith('guardian_'):
            cfg = _read_json(path, None)
            if isinstance(cfg, dict) and cfg.get('enabled'):
                cfg['enabled'] = False
                _write_atomic(path, cfg)
                seen('guardian')

        # ai_mod_config_<gid>.json — AI-модерация
        elif fn.startswith('ai_mod_config_'):
            cfg = _read_json(path, None)
            if isinstance(cfg, dict) and cfg.get('enabled'):
                cfg['enabled'] = False
                _write_atomic(path, cfg)
                seen('ai_moderation')

        # antiraid_<gid>.json — наблюдатель: гасим все триггеры
        elif fn.startswith('antiraid_'):
            cfg = _read_json(path, None)
            if isinstance(cfg, dict):
                changed = False
                for key in ANTIRAID_FLAGS:
                    if cfg.get(key):
                        cfg[key] = False
                        changed = True
                if changed:
                    _write_atomic(path, cfg)
                    seen('antiraid')


def _disable_anti_alt(flipped):
    """GuildData('anti_alt') в sqlite: settings.enabled -> False."""
    try:
        from config import Config
        db_path = Config.DB_PATH
        if not os.path.isfile(db_path):
            return
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT guild_id, value FROM guild_data "
                "WHERE namespace='anti_alt' AND key='settings'"
            ).fetchall()
            changed = False
            for gid, raw in rows:
                try:
                    cfg = json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    continue
                if isinstance(cfg, dict) and cfg.get('enabled'):
                    cfg['enabled'] = False
                    conn.execute(
                        "UPDATE guild_data SET value=?, updated_at=CURRENT_TIMESTAMP "
                        "WHERE namespace='anti_alt' AND guild_id=? AND key='settings'",
                        (json.dumps(cfg, ensure_ascii=False), gid))
                    changed = True
            if changed:
                conn.commit()
                flipped.append('anti_alt(db)')
        finally:
            conn.close()
    except Exception as _ex:
        _log.debug('fresh_start: anti_alt в базе пропущен: %s', _ex)


def _wipe_logs(data_dir):
    wiped = []
    try:
        names = os.listdir(data_dir)
    except Exception:
        return wiped
    for fn in names:
        if fn in KEEP_FILES:
            continue
        path = os.path.join(data_dir, fn)
        if not os.path.isfile(path):
            continue
        is_wipe = fn in WIPE_FILES
        if not is_wipe and fn.endswith('.json'):
            stem = fn[:-5]
            is_wipe = any(stem.startswith(p) for p in WIPE_PREFIXES)
        if is_wipe:
            try:
                os.remove(path)
                wiped.append(fn)
            except Exception as _ex:
                _log.debug('fresh_start: не удалил %s: %s', fn, _ex)
    return wiped


def run_once(root):
    """Выполняется при старте бота. Возвращает сводку или None (уже сделано)."""
    data_dir = os.path.join(root, 'data')
    marker = os.path.join(data_dir, MARKER)
    if os.path.isfile(marker):
        return None

    os.makedirs(data_dir, exist_ok=True)

    flipped = []   # какие сторы защиты погашены
    _disable_file_stores(data_dir, flipped)
    _disable_anti_alt(flipped)

    wiped = _wipe_logs(data_dir)

    report = {
        'at': datetime.now(timezone.utc).isoformat(),
        'disabled': flipped,
        'wiped_files': wiped,
        'note': 'Разовый чистый старт: защита выключена, логи стёрты. '
                'Дальше владелец включает всё сам — миграция больше не сработает.',
    }
    try:
        _write_atomic(marker, report)
    except Exception as _ex:
        _log.warning('fresh_start: маркер не записан (%s) — миграция '
                     'повторится при следующем запуске!', _ex)

    _log.info('ЧИСТЫЙ СТАРТ: защита выключена (%s), логи стёрты (%d шт.)',
              ', '.join(flipped) or 'уже была выключена', len(wiped))
    return report
