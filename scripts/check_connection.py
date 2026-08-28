# -*- coding: utf-8 -*-
"""Проверка соединения «бот ↔ веб-панель» и каналов.

Запуск:  python3 scripts/check_connection.py

Что проверяет (и что чинить, если FAIL):
1. .env — TOKEN, MAIN_GUILD_ID, PANEL_PORT заданы (панель и бот видят
   один сервер, порт совпадает с PANEL_PORT).
2. Панель отвечает на /health — и главное: `bot: ready` (панель ВИДИТ бота).
   Если `bot: demo`/иной статус — панель запущена не через main.py
   (см. PANEL_PROCESS=embedded / запускай main.py).
3. WebSocket-порт 8765 слушает (live-обновления панели).
4. Общие файлы-мосты между панелью и ботом:
   data/channel_routes.json (каналы), data/command_switches.json (команды),
   data/bot_config.json (present-статус).
5. Зависимости музыки (связка с /play): ffmpeg в PATH, yt-dlp установлен.
6. Маршруты каналов из панели (channel_routes) — ключи и номера каналов.

Скрипт НЕ запускает бота и ничего не меняет — только читает и проверяет.
"""
import json
import os
import socket
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

OK = 0
FAIL = 0


def check(ok, msg, fix=''):
    global OK, FAIL
    if ok:
        OK += 1
        print(f'  [OK]   {msg}')
    else:
        FAIL += 1
        print(f'  [FAIL] {msg}')
        if fix:
            print(f'         → {fix}')


def _env_value(key):
    """Значение из .env (свой мини-парсер, без изменений окружения)."""
    env_path = os.path.join(ROOT, '.env')
    try:
        with open(env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
    except OSError:
        return None
    return os.environ.get(key, '')


def _port_open(host, port, timeout=1.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main():
    print('=' * 62)
    print('  HAKUMO — проверка соединения бот ↔ панель')
    print('=' * 62)

    print('\n== 1. Конфигурация (.env) ==')
    token = _env_value('TOKEN') or _env_value('TОКEN')
    main_guild = _env_value('MAIN_GUILD_ID')
    panel_port = int(_env_value('PANEL_PORT') or 0) or 5001
    panel_user = _env_value('PANEL_USER') or 'owner'
    check(bool(token), 'TOKEN задан (бот входит в Discord)', )
    check(bool(main_guild), 'MAIN_GUILD_ID задан (панель и бот на одном сервере)',
          'укажи MAIN_GUILD_ID=<id сервера> в .env')
    check(panel_user, 'PANEL_USER задан (логин панели)')

    print(f'\n== 2. Панель: http://127.0.0.1:{panel_port} ==')
    if not _port_open('127.0.0.1', panel_port):
        check(False, 'панель не отвечает на порту %d' % panel_port,
              'запусти бота: python main.py (панель поднимется с ним)')
    else:
        check(True, 'порт %d открыт — панель слушает' % panel_port)
        try:
            import requests
            r = requests.get(f'http://127.0.0.1:{panel_port}/health',
                             timeout=3)
            data = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
            status = data.get('bot', '?')
            if status == 'ready':
                check(True,
                      f'панель ВИДИТ бота (bot=ready, серверов: {data.get("guilds")})')
            elif status == 'demo':
                check(False, 'панель в демо/без бота (bot=demo)',
                      'панель запущена отдельно или без main.py — '
                      'запусти python main.py; PANEL_PROCESS не должен быть gunicorn')
            else:
                check(False, f'панель отвечает, но статус бота неизвестен ({status!r})',
                      'проверь логи main.py — бот мог не войти в Discord')
        except Exception as e:
            check(False, f'/health не прочитался: {e}')

    print('\n== 3. WebSocket (live-обновления панели) ==')
    ws_port = int(_env_value('WS_PORT') or 0) or 8765
    if _port_open('127.0.0.1', ws_port):
        check(True, f'WebSocket слушает порт {ws_port} (live-канал работает локально)')
    else:
        check(False, f'WebSocket-порт {ws_port} не слушает',
              'бот должен поднять WS: проверь, что запущен main.py и библиотека websockets установлена')

    print('\n== 4. Общие файлы-мосты (панель ↔ бот) ==')
    bridges = [
        ('data/channel_routes.json', 'каналы-маршруты (апелляции, доказательства, тикеты...)'),
        ('data/command_switches.json', 'вкл/выкл команд из панели'),
        ('data/bot_config.json', 'статус/активность бота'),
    ]
    for path, what in bridges:
        exists = os.path.isfile(path)
        if exists:
            try:
                with open(path, encoding='utf-8') as f:
                    json.load(f)
                check(True, f'{path} — {what} (читается)')
            except Exception as e:
                check(False, f'{path} — {what} (битый JSON: {e})')
        else:
            check(False, f'{path} — {what} (файла ещё нет)',
                  'создастся при первом сохранении в панели — не критично')

    print('\n== 5. Маршруты каналов (что заполнено в панели) ==')
    routes = {}
    if os.path.isfile('data/channel_routes.json'):
        try:
            with open('data/channel_routes.json', encoding='utf-8') as f:
                routes = json.load(f)
        except Exception:
            routes = {}
    if routes:
        for gid, cfg in list(routes.items())[:1]:
            filled = {k: v for k, v in (cfg or {}).items() if v}
            check(bool(filled),
                  f'сервер {gid}: заполнено маршрутов — {len(filled)} '
                  f'({", ".join(filled) or "нет"})')
    else:
        check(False, 'маршруты каналов не заполнены',
              'панель → «Каналы и маршруты»: выбери каналы '
              '(апелляция/доказательства/приветствия и т.д.)')

    print('\n== 6. Музыка (/play) ==')
    check(shutil.which('ffmpeg') is not None,
          'ffmpeg найден в PATH (без него музыка не играет)',
          'установи ffmpeg или укажи FFMPEG_BINARY в .env')
    try:
        import yt_dlp  # noqa: F401
        check(True, 'yt-dlp установлен (ссылки/названия для /play)')
    except ImportError:
        check(False, 'yt-dlp не установлен',
              'выполни: .venv/bin/pip install -r requirements.txt && перезапусти бота')

    print('\n' + '=' * 62)
    print(f'  ИТОГ: ОК — {OK} · ПРОБЛЕМ — {FAIL}')
    print('=' * 62)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
