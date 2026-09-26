# -*- coding: utf-8 -*-
"""ПОЛНАЯ очистка слеш-команд бота в Discord (ручной гарант против дублей).

Что делает (напрямую через REST API, независимо от работающего бота):
  1) читает TOKEN из .env рядом со скриптом;
  2) печатает, сколько команд сейчас зарегистрировано глобально и на каждом
     сервере, где состоит бот;
  3) СТИРАЕТ все регистрации (bulk-overwrite пустым списком): и глобальные,
     и все гильдовые — дубли умирают физически, а не «со временем»;
  4) НИЧЕГО не регистрирует обратно: запустите бота — fresh-синк при старте
     сам запишет боевое меню (modpanel/afk + апелляция,
     + update в ЛС; музыка /play удалена; сетап-команды убраны в панель).

Запуск:
  python scripts/clean_commands.py --yes

Без --yes скрипт только ПОКАЖЕТ текущее состояние (dry-run) и спросит
подтверждение. Требуется библиотека requests (она и так нужна боту).
"""
import argparse
import json
import os
import sys

API = 'https://discord.com/api/v10'


def _read_env(path):
    vals = {}
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                # их ТОКЕН бывает и кириллицей — страхуемся
                vals[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return vals


def _fail(msg):
    print(f'[ОШИБКА] {msg}')
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description='Очистка регистраций команд бота')
    ap.add_argument('--yes', action='store_true', help='не спрашивать подтверждение')
    args = ap.parse_args()

    try:
        import requests
    except ImportError:
        _fail('нет requests: pip install requests')

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = _read_env(os.path.join(here, '.env'))
    token = (env.get('TOKEN') or env.get('TOKEN_CYR') or env.get('TОKEN') or '')
    if not token or 'YOUR' in token.upper():
        _fail('TOKEN не найден в .env (рядом с папкой scripts/)')

    headers = {'Authorization': f'Bot {token}'}

    r = requests.get(f'{API}/users/@me', headers=headers, timeout=15)
    if r.status_code != 200:
        _fail(f'Токен не принят Discord (HTTP {r.status_code}) — проверьте TOKEN')
    app_id = r.json()['id']
    print(f'Бот: {r.json().get("username")}#{r.json().get("discriminator", "0")} '
          f'(application id {app_id})')

    # Текущее состояние
    g = requests.get(f'{API}/applications/{app_id}/commands',
                     headers=headers, timeout=15)
    glob = g.json() if g.status_code == 200 else []
    print(f'\nГлобально зарегистрировано: {len(glob)} шт: '
          + ', '.join(sorted(c['name'] for c in glob)))

    guilds = []
    try:
        r = requests.get(f'{API}/users/@me/guilds?limit=200',
                         headers=headers, timeout=15)
        if r.status_code == 200:
            guilds = r.json()
    except Exception:
        pass
    per_guild = {}
    for gd in guilds:
        gid = int(gd['id'])
        r = requests.get(
            f'{API}/applications/{app_id}/guilds/{gid}/commands',
            headers=headers, timeout=15)
        names = [c['name'] for c in r.json()] if r.status_code == 200 else []
        per_guild[gid] = (gd.get('name') or '?', names)
        print(f'Сервер {gd.get("name")} ({gid}): {len(names)} шт: '
              + ', '.join(sorted(names)))

    print('\nПосле очистки бот при старте зарегистрирует боевое меню заново:\n'
          '  серверы: modpanel, afk, report, my-violations\n'
          '  глобально: апелляция, update (только ЛС владельца)')

    if not args.yes:
        answer = input('\nСтереть ВСЕ регистрации команд? (напишите YES): ')
        if answer.strip() != 'YES':
            print('Отменено — ничего не трогал.')
            return

    # Чистим глобальные
    r = requests.put(f'{API}/applications/{app_id}/commands',
                     headers={**headers, 'Content-Type': 'application/json'},
                     data=json.dumps([]), timeout=20)
    if r.status_code != 200:
        _fail(f'Глобальная очистка не прошла (HTTP {r.status_code}): {r.text[:300]}')
    print('\n✓ Глобальные команды стёрты')

    # Чистим каждую гильдию
    for gid, (gname, _names) in per_guild.items():
        r = requests.put(
            f'{API}/applications/{app_id}/guilds/{gid}/commands',
            headers={**headers, 'Content-Type': 'application/json'},
            data=json.dumps([]), timeout=20)
        if r.status_code == 200:
            print(f'✓ Сервер {gname} ({gid}) очищен')
        else:
            print(f'! Сервер {gname} ({gid}): HTTP {r.status_code} — {r.text[:200]}')

    print('\nГотово. Теперь ПЕРЕЗАПУСТИТЕ бота: он зарегистрирует меню с нуля.\n'
          'Артефакты старого меню у клиента Discord проходят Ctrl+R '
          '(а глобальные команды Discord разносит до ~часа — это их кэш).')


if __name__ == '__main__':
    main()
