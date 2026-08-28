# -*- coding: utf-8 -*-
"""П.1: моментальное обновление статистики.

1. bot_stats.html: CPU/RAM/пинг/аптайм обновляются КАЖДЫЙ тик (старый guard
   renderIfChanged глушил тик, если не менялись серверы/юзеры — удалён).
2. Карточки KPI обновляются точечно (id-ячейки sv*), сетка собирается один
   раз — нет перерисовки (мерцания/белого экрана); location.reload нет.
3. Интервалы опроса: bot_stats ≤1.5с, bot_diagnostics health ≤2с/ошибки ≤10с,
   dashboard индекс здоровья ≤5с (всё через setLiveRefresh с fallback).
4. /api/bot-stats: 200, все поля на месте; повторный запрос — тоже 200
   (промо стабильности опроса).
5. Без сетевых подвисаний: fetch с коротким таймаутом не валит страницу
   (loadStats ловит ошибки json()).
"""
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp(prefix='p1_live_')
os.chdir(_TMP)
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


def read(p):
    with open(os.path.join(ROOT, p), encoding='utf-8') as f:
        return f.read()


print('== bot_stats.html: мгновенное и точечное обновление ==')
bs = read('web/templates/bot_stats.html')
check("renderIfChanged('bot-stats'" not in bs,
      'guard «рисовать только при смене серверов» удалён — CPU/RAM обновляют каждый тик')
for vid in ('svGuilds', 'svUsers', 'svLat', 'svUptime', 'svCpu', 'svRam'):
    check(f'id="{vid}"' in bs and f"setV('{vid}'" in bs,
          f'KPI-ячейка {vid} обновляется точечно')
check("grid.dataset.built" in bs and bs.count("grid.innerHTML") == 1,
      'сетка KPI собирается один раз (нет перерисовки = нет мерцания)')
check('location.reload' not in bs, 'нет перезагрузки страницы')
m = re.search(r'setLiveRefresh\(loadStats, (\d+)\)', bs)
check(bool(m) and int(m.group(1)) <= 1500,
      f'опрос bot_stats ≤1.5с ({m.group(1) if m else "?"}мс)')
check('catch (e) { return; }' in bs, 'обрыв ответа тихо пропускает тик (без белого экрана/ошибок)')


print('== bot_diagnostics.html: здоровье живое ==')
bd = read('web/templates/bot_diagnostics.html')
m1 = re.search(r'setLiveRefresh\(load, (\d+)\)', bd)
m2 = re.search(r'setLiveRefresh\(loadErrors, (\d+)\)', bd)
check(bool(m1) and int(m1.group(1)) <= 2000, f'здоровье ≤2с ({m1.group(1) if m1 else "?"}мс)')
check(bool(m2) and int(m2.group(1)) <= 10000, f'ошибки ≤10с ({m2.group(1) if m2 else "?"}мс)')


print('== dashboard.html: индекс здоровья не отстаёт ==')
dh = read('web/templates/dashboard.html')
m3 = re.search(r'setLiveRefresh\(loadServerHealth, (\d+)\)', dh)
check(bool(m3) and int(m3.group(1)) <= 5000, f'индекс здоровья ≤5с ({m3.group(1) if m3 else "?"}мс)')
check("setLiveRefresh(function () { loadStats();" in dh,
      'основные счётчики дашборда живут на лайв-шине (1.5с)')


print('== /api/bot-stats: форма и повторяемость ==')
import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'owner'
    s['selected_guild'] = '777'

r1 = client.get('/api/bot-stats')
r2 = client.get('/api/bot-stats')
d1 = r1.get_json() or {}
check(r1.status_code == 200 and r2.status_code == 200, 'два тика подряд — 200')
# с живым (тестовым) ботом отдаёт все поля
from types import SimpleNamespace  # noqa: E402

_prev = appmod.bot_instance
try:
    g = SimpleNamespace(id=777, name='Главный', member_count=128)
    appmod.bot_instance = SimpleNamespace(
        guilds=[g], get_guild=lambda i: g if int(i) == 777 else None,
        latency=0.042, is_closed=lambda: False,
        user=SimpleNamespace(id=1, display_name='Hakumo'))
    r3 = client.get('/api/bot-stats')
    d3 = r3.get_json() or {}
finally:
    appmod.bot_instance = _prev
need = ('guilds', 'users', 'latency', 'uptime', 'cpu', 'ram', 'history', 'guild_list')
check(all(k in d3 for k in need), 'все поля статистики в ответе с ботом', str(sorted(d3.keys())))
check(isinstance(d3.get('history'), list) and isinstance(d3.get('guild_list'), list),
      'история и список серверов — списки (для истории сессии)')
check(d3.get('guilds') == 1 and d3.get('users') == 128 and d3.get('latency') == 42,
      'счётчики живые: серверы/юзеры/пинг посчитаны из бота',
      str({k: d3.get(k) for k in ('guilds', 'users', 'latency')}))


print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
