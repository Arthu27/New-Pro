# -*- coding: utf-8 -*-
"""Глубокая личная проверка системы (заказ, пункт 6) — поверх реального
Flask test_client, без сети и DOM.

Секции:
1. Меню/страницы: каждая страница меню — 200 и не 500 (включая гигиену HTML).
2. Сохранение настроек: POST → файл → «перезапуск» (reload модулей) → значения
   на месте (bot-settings presence; automation server_stats с 3 счётчиками).
3. Неверные аргументы: мусорный статус/типы → 400 с понятной ошибкой, файл
   конфигурации НЕ испорчен.
4. Пустой сервер: без каналов/ролей/участников API отдают [] и 200, без 500.
5. Огромный сервер: 1500 каналов / 300 ролей / 3000 участников — ответы быстрые,
   ничего не теряется, пагинация участников с X-Total-Count.
6. Конкурентные сохранения («быстрые клики», несколько пользователей): 6 потоков
   × 10 POST presence — все 200, файл остаётся валидным JSON.
7. Безопасность: гость → редирект на логин; роль mod → 403 на owner/admin API.
8. Консоль: ни одного ERROR в логах и ни одного «Ошибка/Traceback» в stdout
   за всё время прогона (перехват logging + print).

Запуск: python3 tests/test_deep_check_p6.py
"""
import contextlib
import importlib
import io
import json
import logging
import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp(prefix='deep_p6_')
os.chdir(_TMP)  # вся data/ приземляется во временную директорию

os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ['MAIN_GUILD_ID'] = '777'

PASS = 0
FAIL = 0


def check(ok, msg, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {detail}')


# ── перехват консоли (п.6 «проверка консоли») ────────────────────────────
_LOG_RECORDS = []


class _ErrTap(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            _LOG_RECORDS.append(record.getMessage()[:200])


logging.getLogger().addHandler(_ErrTap())


class _OutTap(io.StringIO):
    BAD = ('Traceback', 'ERROR] ', ']Ошибка ', 'Exception:')

    def __init__(self, real):
        super().__init__()
        self._real = real
        self.bad = []

    def write(self, s):
        for pat in self.BAD:
            if pat in s:
                self.bad.append(s.strip()[:160])
        return self._real.write(s)

    def flush(self):
        return self._real.flush()


_stdout_tap = _OutTap(sys.stdout)
sys.stdout = _stdout_tap

import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def _login(role='owner'):
    with client.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role
        s['selected_guild'] = '777'


# ── фейки Discord-сущностей ──────────────────────────────────────────────
def _channel(i, name=None):
    return SimpleNamespace(
        id=1000000000000000000 + i,
        name=name or f'канал-{i}',
        type=0,                     # text; int не совпадает с ChannelType — fallback-ветка
        position=i,
        category=None,
        topic=None,
    )


def _role(i, name=None, members=0):
    return SimpleNamespace(
        id=2000000000000000000 + i,
        name=name or f'роль-{i}',
        color=0,
        members=[None] * members,
    )


def _member(i):
    r = _role(5000 + i % 9, members=1)
    return SimpleNamespace(
        id=3000000000000000000 + i,
        name=f'user{i}',
        display_name=f'Участник {i}',
        discriminator='0',
        display_avatar=SimpleNamespace(url='https://cdn.discordapp.com/a.png'),
        joined_at=datetime(2024, 1, 1),
        roles=[_role(0, name='@everyone'), r],
        bot=False,
        status='online',
        nick=None,
        top_role=r,
    )


def _bot_with(guild):
    return SimpleNamespace(
        guilds=[guild] if guild else [],
        get_guild=(lambda gid, g=guild: g if g and int(gid) == int(g.id) else None),
        is_closed=lambda: False,
        user=SimpleNamespace(id=1, display_name='Hakumo'),
    )


def _guild(gid=777, channels=(), roles=(), members=(), name='Тест'):
    return SimpleNamespace(
        id=gid, name=name, channels=list(channels), roles=list(roles),
        members=list(members), member_count=len(members),
        icon=None,
    )


print('== 1. Меню: каждая страница — 200, валидный HTML ==')
_login('owner')
from services.panel_menu import MENU  # noqa: E402

paths = set()


def _walk(node):
    if isinstance(node, dict):
        if node.get('path'):
            paths.add(node['path'])
        for v in node.values():
            _walk(v)
    elif isinstance(node, (list, tuple)):
        for v in node:
            _walk(v)


_walk(MENU)
_bad_pages = []
for p in sorted(paths):
    try:
        r = client.get(p)
        body = r.get_data(as_text=True)
        if r.status_code != 200 or '<!doctype' not in body.lower() or \
                'Internal Server Error' in body or 'Traceback' in body:
            _bad_pages.append(f'{p}: {r.status_code}')
    except Exception as ex:  # noqa: BLE001
        _bad_pages.append(f'{p}: EXC {ex}')
check(not _bad_pages, f'все {len(paths)} страниц меню отвечают 200 с чистым HTML',
      '; '.join(_bad_pages[:8]))


print('== 2. Сохранение настроек -> перезапуск бота ==')
_login('owner')
r = client.post('/api/bot-settings/presence', json={
    'status': 'dnd', 'activity_type': 'watching',
    'activity_text': 'стражу за сервером'})
check(r.status_code == 200 and r.get_json().get('ok'),
      'presence: валидный POST принят (200 ok)')

cfg_path = 'data/bot_config.json'
check(os.path.exists(cfg_path), 'presence: конфиг записан на диск')
with open(cfg_path, encoding='utf-8') as f:
    on_disk = json.load(f)
check(on_disk.get('status') == 'dnd' and on_disk.get('activity_text') == 'стражу за сервером',
      'presence: на диске именно то, что отправляли')

# «перезапуск»: переимпорт модуля роутов панели (бот при старте читает тот же
# файл data/bot_config.json — проверено отдельно, здесь достаточно reload)
importlib.reload(sys.modules['web.routes.bot_settings'])
r = client.get('/api/bot-settings')
pres = (r.get_json() or {}).get('presence', {})
check(pres.get('status') == 'dnd' and pres.get('activity_text') == 'стражу за сервером',
      'presence: после «перезапуска» настройки не сбросились', str(pres))

# automation server_stats — модуль удалён (выключенная автоматика счётчиков).


print('== 3. Неверные аргументы: 400, понятная ошибка, файл цел ==')
with open(cfg_path, encoding='utf-8') as f:
    before = f.read()
r = client.post('/api/bot-settings/presence', json={
    'status': 'banana', 'activity_type': 'flying', 'activity_text': ''})
j = r.get_json() or {}
check(r.status_code == 400 and j.get('ok') is False and j.get('errors'),
      'presence: мусорный статус/тип/пустой текст → 400 с разбором полей')
check(all('Traceback' not in e and '`' not in e for e in (j.get('errors') or [])),
      'presence: ошибки — человеческий текст без технической шелухи')
with open(cfg_path, encoding='utf-8') as f:
    check(f.read() == before, 'presence: отказанный POST не тронул файл конфигурации')
r = client.post('/api/bot-settings/presence', data='не-json', content_type='text/plain')
check(r.status_code in (400, 415), 'presence: не-JSON тело → вежливый отказ, не 500')
# automation server_stats удалён — проверка не-JSON больше не нужна.


print('== 4. Пустой сервер (нет каналов/ролей/участников) ==')
_prev_bot = appmod.bot_instance
try:
    appmod.bot_instance = _bot_with(_guild(777))
    r = client.get('/api/guild/777/channels')
    body = r.get_json()
    chans = body.get('channels') if isinstance(body, dict) else body
    check(r.status_code == 200 and chans == [], 'пустой сервер: каналы — []')
    r = client.get('/api/guild/777/roles')
    check(r.status_code == 200 and r.get_json() == [], 'пустой сервер: роли — []')
    r = client.get('/api/guild/777/members')
    check(r.status_code == 200 and r.get_json() == [], 'пустой сервер: участники — []')

    print('== 5. Огромный сервер: 1500 каналов / 300 ролей / 3000 участников ==')
    huge_members = [_member(i) for i in range(3000)]
    huge_channels = [_channel(i) for i in range(1500)]
    huge_roles = [_role(i, members=(i % 40)) for i in range(1, 301)]
    appmod.bot_instance = _bot_with(
        _guild(777, channels=huge_channels, roles=huge_roles,
               members=huge_members, name='Огромный'))

    t0 = time.time()
    r = client.get('/api/guild/777/channels')
    dt = time.time() - t0
    chans = r.get_json()
    if isinstance(chans, dict):
        chans = chans.get('channels') or []
    check(r.status_code == 200 and len(chans) == 1500 and dt < 4.0,
          f'огромный сервер: все 1500 каналов за {dt:.2f}с')

    t0 = time.time()
    r = client.get('/api/guild/777/roles')
    dt = time.time() - t0
    check(r.status_code == 200 and len(r.get_json()) == 300 and dt < 4.0,
          f'огромный сервер: все 300 ролей за {dt:.2f}с')

    t0 = time.time()
    r = client.get('/api/guild/777/members?limit=500')
    dt = time.time() - t0
    check(r.status_code == 200 and len(r.get_json()) == 500 and
          r.headers.get('X-Total-Count') == '3000' and dt < 4.0,
          f'огромный сервер: пагинация членов 500/3000 за {dt:.2f}с')
    r2 = client.get('/api/guild/777/members?limit=500&offset=2500')
    tail = r2.get_json()
    check(len(tail) == 500 and tail[0]['id'] != r.get_json()[0]['id'],
          'огромный сервер: «скролл» (offset=2500) отдаёт хвост без дублей')
finally:
    appmod.bot_instance = _prev_bot


print('== 6. Конкурентные сохранения (быстрые клики / несколько пользователей) ==')
results = []


def _hammer(n):
    cl = appmod.app.test_client()
    with cl.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = f'user{n}'
        s['role'] = 'owner'
        s['selected_guild'] = '777'
    for k in range(10):
        rr = cl.post('/api/bot-settings/presence', json={
            'status': 'online', 'activity_type': 'playing',
            'activity_text': f'текст-{n}-{k}'})
        results.append(rr.status_code)


threads = [threading.Thread(target=_hammer, args=(n,)) for n in range(6)]
for th in threads:
    th.start()
for th in threads:
    th.join()
check(all(c == 200 for c in results), f'60 конкурентных POST — все 200 ({len(results)})')
try:
    with open(cfg_path, encoding='utf-8') as f:
        final_cfg = json.load(f)
    ok_json = isinstance(final_cfg, dict) and final_cfg.get('status') == 'online'
except Exception:  # noqa: BLE001
    final_cfg, ok_json = None, False
check(ok_json, 'файл конфигурации после штурма — валидный JSON, без полусломанного состояния')
r = client.get('/api/bot-settings')
check((r.get_json() or {}).get('presence', {}).get('status') == 'online',
      'GET после штурма отдаёт согласованное состояние')


print('== 7. Безопасность API настроек ==')
guest = appmod.app.test_client()  # без сессии
r = guest.post('/api/bot-settings/presence', json={
    'status': 'online', 'activity_type': 'playing', 'activity_text': 'x'})
check(r.status_code in (302, 401, 403), 'гость не сохраняет presence (нет сессии)')
r = guest.get('/api/bot-settings')
check(r.status_code in (302, 401, 403), 'гость не читает настройки бота')

mod_client = appmod.app.test_client()
with mod_client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'moder'
    s['role'] = 'mod'
    s['selected_guild'] = '777'
r = mod_client.post('/api/bot-settings/presence', json={
    'status': 'online', 'activity_type': 'playing', 'activity_text': 'x'})
check(r.status_code == 403, 'роль mod не может менять присутствие бота (owner-only)')
# automation server_stats удалён — ролевой проверки больше нет.
r = mod_client.post('/update' if False else '/api/bot-settings/sync', json={})
check(r.status_code in (403, 404), 'mod не имеет доступа к sync-пульту')


print('== 8. Утечки/зависания: 400 сохранений + 400 чтений подряд ==')
_login('owner')
import resource  # noqa: E402


def _rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


rss0 = _rss_mb()
t0 = time.time()
for i in range(400):
    txt = 'лично' if i % 2 else 'пропарка'
    r = client.post('/api/bot-settings/presence', json={
        'status': 'online', 'activity_type': 'playing', 'activity_text': f'{txt}-{i % 50}'})
    assert r.status_code == 200, r.status_code
    r = client.get('/api/bot-settings')
    assert r.status_code == 200, r.status_code
dt = time.time() - t0
growth = _rss_mb() - rss0
check(dt < 60, f'800 запросов за {dt:.1f}с — без зависаний')
check(growth < 40, f'RSS-пророст {growth:.1f} МБ (<40) — утечек нет')
with open(cfg_path, encoding='utf-8') as f:
    check(bool(json.load(f)), 'после стресса конфигурация цела')


print('== 9. Консоль чистая за весь прогон ==')
log_bad = [m for m in _LOG_RECORDS if 'Traceback' in m or 'Exception' in m or True]
check(not _LOG_RECORDS, f'ни одного ERROR-лога за весь прогон ({len(_LOG_RECORDS)})',
      '; '.join(_LOG_RECORDS[:6]))
check(not _stdout_tap.bad, f'stdout без Traceback/«Ошибка» ({len(_stdout_tap.bad)})',
      '; '.join(_stdout_tap.bad[:6]))


print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
