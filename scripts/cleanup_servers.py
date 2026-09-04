# -*- coding: utf-8 -*-
"""Чистка данных о «лишних» серверах: остаётся только MAIN_GUILD_ID.

Бот хранит настройки по серверам: data/<имя>_<ID>.json, журналы с ключом
по серверу и строки в базе. Если бот побывал на тестовых серверах —
от них остаются файлы. Этот скрипт убирает всё, что не про главный
сервер, и перед этим делает резервную копию data/.

Посмотреть, что будет удалено (ничего не меняет):
    python scripts/cleanup_servers.py
Удалить:
    python scripts/cleanup_servers.py --apply

Главный сервер берётся из .env (MAIN_GUILD_ID).
"""
import argparse
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')

# data/<имя>_<ID_сервера>(_что-угодно).(.json|.db) — хранится по серверам
# (message_logs_777.json, proof_config_888.json, modproof_424242_1.json …).
# Универсальный шаблон: новые файлы настроек подхватятся сами.
GUILD_FILE_RE = re.compile(r'^[a-z][a-z0-9_]*_(\d+).*\.(?:json|db)$')

# журналы-словари: {ID_сервера: [...]}  — сырой список ключей верхнего уровня
DICT_KEYED = ('audit_log.json', 'audit_log_backup.json', 'join_log.json',
              # кэш аудита Discord и курсор синка — главный источник «чужих»
              # записей в Журнале модерации до фикса изоляции сервера
              'discord_audit_cache.json', 'audit_seen.json',
              'warnings.json', 'night_summary.json', 'channel_routes.json',
              'tag_jail.json')

# справочники записей с полем сервера: {ключ: {'guild_id': ID, ...}}
VALUE_FIELD_KEYED = {'staff_apps.json': 'guild_id'}

DB_TABLE = 'guild_data'


def keep_gid() -> str:
    """ID главного сервера: .env → config (может не быть — тогда пусто)."""
    mid = (os.getenv('MAIN_GUILD_ID') or '').strip()
    if not mid:
        try:
            sys.path.insert(0, ROOT)
            from config import Config
            mid = str(Config.MAIN_GUILD_ID or '').strip()
        except Exception:
            pass
    return mid


def plan(keep: str) -> list:
    """Список (тип, цель, описание) лишних данных. Ничего не меняет."""
    actions = []
    if not os.path.isdir(DATA):
        return actions
    for name in sorted(os.listdir(DATA)):
        path = os.path.join(DATA, name)
        if not os.path.isfile(path):
            continue
        m = GUILD_FILE_RE.match(name)
        if m and m.group(1) != keep:
            actions.append(('file', path, f'файл сервера {m.group(1)}: {name}'))
            continue
        if name in DICT_KEYED:
            try:
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                continue
            if isinstance(data, dict):
                for gid in sorted(k for k in data if k.isdigit() and k != keep):
                    n = len(data[gid]) if hasattr(data[gid], '__len__') else 1
                    actions.append(('json_key', (path, gid),
                                    f'журнал {name}: сервер {gid} ({n} записей)'))
            continue
        # mod_data.json: журналы дел живут в ДВУХ ключах сразу ('cases' —
        # актуальный, 'case' — легаси); прогон по обоим, иначе записи
        # выселённого сервера остаются в другом ключе.
        if name == 'mod_data.json':
            try:
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            for section in ('cases', 'case'):
                nested = data.get(section)
                if not isinstance(nested, dict):
                    continue
                for gid in sorted(k for k in nested if str(k).isdigit() and str(k) != keep):
                    n = len(nested[gid]) if hasattr(nested[gid], '__len__') else 1
                    actions.append(('json_nested_key', (path, section, str(gid)),
                                    f'журнал {name}/{section}: сервер {gid} ({n} записей)'))
            continue
        if name in VALUE_FIELD_KEYED:
            field = VALUE_FIELD_KEYED[name]
            try:
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                continue
            if isinstance(data, dict):
                for rec_key in sorted(data):
                    rec = data[rec_key]
                    rec_gid = str(rec.get(field)) if isinstance(rec, dict) else ''
                    if rec_gid.isdigit() and rec_gid != keep:
                        actions.append(('json_value_field', (path, field, rec_gid, rec_key),
                                        f'{name}: запись {rec_key} (сервер {rec_gid})'))
    db = os.path.join(DATA, 'bot.db')
    if os.path.exists(db):
        try:
            con = sqlite3.connect(db)
            cols = [r[1] for r in con.execute(f'PRAGMA table_info({DB_TABLE})')]
            if 'guild_id' in cols:
                for (gid,) in con.execute(f'SELECT DISTINCT guild_id FROM {DB_TABLE}'):
                    if str(gid) != keep:
                        actions.append(('db_row', (db, str(gid)),
                                        f'база, {DB_TABLE}: сервер {gid}'))
            con.close()
        except Exception as e:
            print(f'[предупреждение] база не прочитана: {e}')
    return actions


def _make_backup() -> str or None:
    """Резервная копия data\\ перед чисткой (zip в backups/)."""
    try:
        sys.path.insert(0, ROOT)
        os.chdir(ROOT)
        from services.backup import create_backup, BACKUP_DIR_DEFAULT
        info = create_backup(backup_dir=BACKUP_DIR_DEFAULT,
                             reason='перед чисткой лишних серверов')
        return info.get('name')
    except Exception as e:
        print(f'[предупреждение] копия не создана: {e}')
        return None


def apply_plan(actions: list) -> dict:
    """Выполнить план. Возвращает отчёт {удалено, ошибки}."""
    report = {'removed': 0, 'errors': []}
    touched_json = {}  # path -> список операций удаления
    for kind, target, _desc in actions:
        try:
            if kind == 'file':
                os.remove(target)
                report['removed'] += 1
            elif kind == 'json_key':
                path, gid = target
                touched_json.setdefault(path, []).append(('key', gid))
            elif kind == 'json_nested_key':
                path, section, gid = target
                touched_json.setdefault(path, []).append(('nested', section, gid))
            elif kind == 'json_value_field':
                path, field, gid, rec_key = target
                touched_json.setdefault(path, []).append(('value_field', field, gid, rec_key))
            elif kind == 'db_row':
                db, gid = target
                con = sqlite3.connect(db)
                con.execute(f'DELETE FROM {DB_TABLE} WHERE guild_id=?', (int(gid),))
                con.commit()
                con.close()
                report['removed'] += 1
        except Exception as e:
            report['errors'].append(f'{_desc}: {e}')
    for path, ops in touched_json.items():
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            removed_here = 0
            for op in ops:
                if op[0] == 'key':
                    if data.pop(op[1], None) is not None:
                        removed_here += 1
                elif op[0] == 'nested':
                    section = data.get(op[1])
                    if isinstance(section, dict) and section.pop(op[2], None) is not None:
                        removed_here += 1
                elif op[0] == 'value_field':
                    _field, _gid, rec_key = op[1], op[2], op[3]
                    rec = data.get(rec_key)
                    if isinstance(rec, dict) and str(rec.get(_field)) == _gid:
                        del data[rec_key]
                        removed_here += 1
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
            report['removed'] += removed_here
        except Exception as e:
            report['errors'].append(f'{path}: {e}')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Убрать данные обо всех серверах, кроме MAIN_GUILD_ID')
    parser.add_argument('--apply', action='store_true',
                        help='really delete (default: только показать)')
    args = parser.parse_args()

    keep = keep_gid()
    if not keep:
        print('MAIN_GUILD_ID не задан. Впишите в .env ID главного сервера '
              'и запустите снова — я оставлю только его данные.')
        return 1

    actions = plan(keep)
    print(f'Главный сервер (остаётся): {keep}')
    if not actions:
        print('Лишних данных о других серверах не найдено — чисто.')
        return 0

    print(f'Найдено лишнего: {len(actions)}')
    for _kind, _t, desc in actions:
        print(f'  - {desc}')

    if not args.apply:
        print('\nЭто только просмотр. Чтобы удалить: '
              'python scripts/cleanup_servers.py --apply')
        return 0

    print('\nДелаю резервную копию data\\ ...')
    backup = _make_backup()
    if backup:
        print(f'  копия: backups/{backup}')

    report = apply_plan(actions)
    print(f"Удалено: {report['removed']}")
    for err in report['errors']:
        print(f'  [ошибка] {err}')
    print('Готово: данные теперь только про главный сервер.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
