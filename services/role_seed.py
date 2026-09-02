# -*- coding: utf-8 -*-
"""Одноразовое применение стартовых ролей из config/role_seed.json.

Зачем: владелец задал роли персонала и роль бана ДО выкатки на сервер.
Файлы data/role_map.json и data/punish_roles.json — рантайм и в git не
попадают, поэтому настройка едет в отслеживаемом config/role_seed.json и
применяется при старте бота/панели.

Правила:
  • применяется ТОЛЬКО если config/role_seed.json существует;
  • НЕ перезатирает уже заданное: в role_map дописываются только
    отсутствующие роли, роль бана ставится только если её ещё нет;
  • идемпотентно по версии сида: маркер data/.role_seed.v<N> ставится
    после успешного прогона — повторно не сыпем, ручные правки в панели
    живут дальше (новые роли добавляются в сид с бампом version);
  • в демо/превью-панели без боевого MAIN_GUILD_ID ничего не пишем
    (иначе сид бы осел в демо-данных).
"""
import json
import os

from logger import get_logger

_log = get_logger('role_seed')

SEED_PATH = os.path.join('config', 'role_seed.json')
ROLE_MAP_PATH = os.path.join('data', 'role_map.json')
PUNISH_PATH = os.path.join('data', 'punish_roles.json')
MARKER_FMT = os.path.join('data', '.role_seed.v{version}')


def _read_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _main_guild_id():
    """Боевой MAIN_GUILD_ID из окружения (0/демо-фейк → None)."""
    try:
        from config import Config
        gid = int(getattr(Config, 'MAIN_GUILD_ID', 0) or 0)
        # демо-витрина использует заведомо фейковый id — не сеем туда
        if gid and gid != 987654321098765432:
            return gid
    except Exception as _ex:
        _log.debug('main_guild_id: %s', _ex)
    return None


def apply_role_seed(force=False):
    """Применить сид. Возвращает короткий отчёт-словарь (для логов/тестов).

    force=True — игнорировать маркер версии (для тестов/ручного прогона).
    Никогда не бросает исключение наружу: сид не должен ронять старт.
    """
    report = {'applied': False, 'role_map_added': [], 'ban_role': False,
              'reason': ''}
    try:
        # Демо/превью/тесты — не сеем (иначе боевые роли осели бы в фейковых
        # данных витрины и тестовых временных каталогах).
        if str(os.environ.get('DEMO_MODE', '')).strip() in ('1', 'true', 'yes', 'on'):
            report['reason'] = 'demo mode'
            return report
        if not os.path.exists(SEED_PATH):
            report['reason'] = 'no seed file'
            return report

        seed = _read_json(SEED_PATH, {})
        try:
            version = int(seed.get('version') or 1)
        except (TypeError, ValueError):
            version = 1
        marker = MARKER_FMT.format(version=version)
        if not force and os.path.exists(marker):
            report['reason'] = f'already applied (v{version})'
            return report

        # 1) role_map: дописываем только отсутствующие роли.
        seed_map = seed.get('role_map') or {}
        role_map = _read_json(ROLE_MAP_PATH, {})
        if not isinstance(role_map, dict):
            role_map = {}
        for rid, tier in seed_map.items():
            rid = str(rid).strip()
            tier = str(tier).strip()
            if rid and tier in ('mod', 'curator', 'admin', 'owner') \
                    and rid not in role_map:
                role_map[rid] = tier
                report['role_map_added'].append(f'{rid}={tier}')
        if report['role_map_added']:
            _write_json(ROLE_MAP_PATH, role_map)

        # 2) punish_roles: роль бана для главного сервера (если не задана).
        ban_role = int((seed.get('punish_roles') or {}).get('ban') or 0)
        gid = _main_guild_id()
        if ban_role and gid:
            punish = _read_json(PUNISH_PATH, {})
            if not isinstance(punish, dict):
                punish = {}
            row = punish.get(str(gid))
            if not isinstance(row, dict):
                row = {}
            roles = row.get('roles')
            if not isinstance(roles, dict):
                roles = {}
            if not int(roles.get('ban') or 0):
                roles['ban'] = ban_role
                row['roles'] = roles
                punish[str(gid)] = row
                _write_json(PUNISH_PATH, punish)
                report['ban_role'] = True
        elif ban_role and not gid:
            _log.debug('punish ban-role пропущен: боевой MAIN_GUILD_ID не задан')

        # маркер версии — прогон сделан
        try:
            os.makedirs('data', exist_ok=True)
            with open(marker, 'w', encoding='utf-8') as fh:
                fh.write('ok')
        except OSError as _ex:
            _log.debug('marker: %s', _ex)

        report['applied'] = True
        report['reason'] = 'ok'
        _log.info('role_seed v%s применён: role_map +%s, ban_role=%s',
                  version, report['role_map_added'], report['ban_role'])
    except Exception as _ex:
        report['reason'] = f'error: {_ex}'
        _log.warning('apply_role_seed: %s', _ex)
    return report
