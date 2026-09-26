# -*- coding: utf-8 -*-
"""«Роли наказаний» при панели ОТДЕЛЬНЫМ процессом от бота.

Сценарий (жалоба владельца: «бот онлайн, а панель пишет Бот офлайн»):
start_panel / gunicorn / панель на VDS живут без bot_instance в памяти —
раньше страница всегда отвечала «Бот офлайн», даже когда бот работал.
Теперь бот пишет пульс data/bot_state.json + снимок ролей
data/bot_roles_<gid>.json (services.bot_bridge), и панель:

1. видит «бот онлайн» по свежему пульсу (bot_online=true);
2. показывает роли из дискового снимка (roles_source=disk), отфильтровав
   @everyone и управляемые роли — селекты живые, как при боте в процессе;
3. даёт сохранить выбор (валидация по снимку) — бот применит из файла;
4. протух пульс (>TTL) или бот его не видит — снова честный «офлайн»,
   сохранять нельзя, чужой/старый список не показываем.

Запуск: python3 tests/test_role_settings_remote.py
"""
import importlib
import os
import shutil
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix='hakumo_rset_remote_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'
# DEMO_MODE не ставим: проверяем БОЕВОЙ режим без бота в процессе.

PASS = 0
FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


from services import bot_bridge as BR  # noqa: E402
from services import punish_roles as PR  # noqa: E402

appmod = importlib.import_module('web.app')
appmod.set_bot_instance(None)      # панель без бота в процессе
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


class _Role:
    def __init__(self, rid, name, pos=1, managed=False):
        self.id = rid
        self.name = name
        self.position = pos
        self.managed = managed
        self.color = None


class _Channel:
    def __init__(self, cid, name, ctype='text', pos=0, cat=None):
        self.id = cid
        self.name = name
        self.type = ctype
        self.position = pos
        self.category = cat
        self.created_at = None
        self.mention = f'#{name}'
        self.topic = None
        self.nsfw = False
        self.slowmode_delay = 0
        self.bitrate = 0
        self.user_limit = 0


class _Category:
    def __init__(self, cid, name, pos=0):
        self.id = cid
        self.name = name
        self.position = pos


def seed_bridge(gid=777, status='online', age=0.0, guild_ids=None):
    """Свежий пульс + снимки ролей/каналов, как пишет процесс бота (main.py)."""
    BR.write_state(status, latency_ms=12.5,
                   guilds=[{'id': str(g), 'name': f'G{g}',
                            'member_count': 1234}
                           for g in (guild_ids or [gid])],
                   force=True)
    if status == 'online':
        BR.write_roles(gid, [
            _Role(555001, 'Уровень 1', 5),
            _Role(555010, 'Изолирован', 12),
            _Role(gid, '@everyone', 0),          # не роль выбора
            _Role(555020, 'запрещён-бот-роль', 9, managed=True),
        ])
        _cat = _Category(7010, 'Служебные', 0)
        BR.write_channels(gid, [
            _Channel(7001, 'общий', 'text', 0),
            _Channel(7002, 'апелляции', 'text', 1),
            _Channel(7003, 'войс', 'voice', 2),
            _Channel(7004, 'служебный', 'text', 0, _cat),
            _Channel(7010, 'Служебные', 'category', 0),
        ])
    if age:
        # искусственно состарим пульс (переживем TTL) — как будто бот умер
        import json as _json
        st = BR.read_state() or {}
        st['ts'] = time.time() - age
        with open(BR.STATE_FILE, 'w', encoding='utf-8') as fp:
            _json.dump(st, fp, ensure_ascii=False)


print('== 1. панель без бота в процессе, но бот жив (пульс свежий) ==')
login('owner')
seed_bridge(777, 'online')
d = client.get('/api/guild/777/role-settings').get_json()
check(d.get('success') and d.get('bot_online') is True,
      f'бот онлайн по свежему пульсу (bot_state={d.get("bot_state")})')
check(d.get('roles_source') == 'disk', f'роли пришли из снимка бота ({d.get("roles_source")})')
rid = {r['id'] for r in d.get('roles') or []}
check('555001' in rid and '555010' in rid, 'роли сервера на месте')
check('555020' not in rid, 'управляемые роли не предлагаем (как в живом списке)')
check('777' not in rid and '@everyone' not in [r['name'] for r in d.get('roles') or []],
      '@everyone не в списке')
check(d.get('unknown_roles') == 0, 'нет «удалённых» ролей — выбор цел')

print('== 2. сохранение по снимку (как при боте в процессе) ==')
r = client.post('/api/guild/777/role-settings', json={'mapping': {
    'mute': '555010', 'warn_1': '555001', 'ban': '0'}})
dd = r.get_json()
check(r.status_code == 200 and dd.get('success'), f'сохранение прошло: {dd.get("error", "")}')
got = PR.get('777')
check(got.get('mute') == 555010 and got.get('warn_1') == 555001,
      'выбор лёг в data/punish_roles.json — бот применит из того же файла')
r = client.post('/api/guild/777/role-settings', json={'mapping': {
    'mute': '999999999999999999'}})
check(r.status_code == 400, 'роль не из снимка сервера — 400 (ручной ID не пройдёт)')

print('== 3. пульс протух / бот умер — честный офлайн ==')
seed_bridge(777, 'online', age=BR.TTL_SEC + 5)
d = client.get('/api/guild/777/role-settings').get_json()
check(d.get('success') and d.get('bot_online') is False,
      f'протухший пульс = офлайн (bot_state={d.get("bot_state")})')
check(d.get('roles') == [] and d.get('roles_count') == 0,
      'старый снимок ролей НЕ показываем — пустой список')
ok, err, saved = __import__('web.routes.role_settings_panel',
                            fromlist=['save_settings']).save_settings(
    777, {'mute': '555010'}, who='test')
check(not ok and err and saved is None, f'сохранять нельзя: {err}')

print('== 4. бот онлайн, но этой гильдии у него нет ==')
seed_bridge(4242, 'online')
d = client.get('/api/guild/777/role-settings').get_json()
check(d.get('bot_online') is True and d.get('bot_guild_ok') is False,
      'гильдия не у бота → bot_guild_ok=false (страница объяснит причину)')
check(d.get('roles') == [], 'роли чужой гильдии не подмешиваем')

print('== 5. старт бота (starting) — не «офлайн», а «подключается» ==')
seed_bridge(777, 'starting')
d = client.get('/api/guild/777/role-settings').get_json()
check(d.get('bot_state') == 'starting' and d.get('bot_online') is False,
      'starting отдан отдельным полем — страница скажет «подключается»')

print('== 6. статус по всей панели: /api/stats, /health, /api/status-public ==')
seed_bridge(777, 'online')
d = client.get('/api/stats').get_json()
check(d.get('status') == 'online' and d.get('latency') == 12.5
      and d.get('guilds') == 1,
      f'/api/stats: шапка/дашборд видят онлайн-бота по пульсу ({d.get("status")})')
check(d.get('users') == 1234, '/api/stats: число участников из пульса (member_count)')
r = client.get('/health')
d = r.get_json()
check(r.status_code == 200 and d.get('bot') == 'ready' and d.get('status') == 'healthy',
      f'/health: мониторинг не врёт degraded при живом удалённом боте ({r.status_code})')
d = client.get('/api/status-public').get_json()
check(d.get('ok') and d.get('online') is True and d.get('latency_ms') == 12.5,
      f'/api/status-public: публичная страница показывает онлайн ({d.get("online")})')

print('== 7. пикеры ролей и каналов по всей панели (remote) ==')
d = client.get('/api/guild/777/roles').get_json()
rid = {r['id'] for r in d}
names = [r['name'] for r in d]
check(isinstance(d, list) and '555001' in rid and '555010' in rid,
      f'/api/roles: селекты ролей по всей панели живые ({names[:2]})')
check('@everyone' not in names,
      '/api/roles: @everyone не отдаём (как в живом списке)')
d = client.get('/api/guild/777/channels').get_json()
chid = {c['id'] for c in d}
check(isinstance(d, list) and '7001' in chid and '7002' in chid,
      '/api/channels: селекты каналов по всей панели живые (снимок бота)')
check(all(c.get('type') in ('text', 'voice', 'category') for c in d),
      '/api/channels: тип канала в снимке есть — страница каналов не сломается')
from web.routes.guild_admin import guild_channels_roles as GCR
channels, roles = GCR('777')
check({c['id'] for c in channels} == {'7001', '7002', '7004'}
      and {r['id'] for r in roles} == {'555001', '555010'},
      'guild_channels_roles: текстовые каналы и роли (без voice/category/@everyone/managed)')

print('== 8. действие без бота в процессе при ЖИВОМ боте: честная подсказка ==')
seed_bridge(777, 'online')
r = client.post('/api/temp-mod/mute', json={'user_id': '123', 'duration': '1h'})
d = r.get_json(silent=True) or {}
err = d.get('error') or ''
check('панель запущена отдельным процессом' in err,
      f'после after_request: «панель отдельным процессом», а не «бот офлайн»: {err!r}')
seed_bridge(777, 'online', age=BR.TTL_SEC + 5)   # бот «умер»
r = client.post('/api/temp-mod/mute', json={'user_id': '123', 'duration': '1h'})
d = r.get_json(silent=True) or {}
err = d.get('error') or ''
check('start.bat' in err, f'бот реально офлайн — прежняя подсказка со start.bat: {err!r}')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
