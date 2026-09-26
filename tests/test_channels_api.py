# -*- coding: utf-8 -*-
"""E2E: каналы/роли/DM/purge/массовые операции через Flask + реальный asyncio loop.
Раньше все эти эндпоинты передавали СИНХРОННУЮ функцию в run_coroutine_threadsafe
-> мгновенный TypeError / дедлок. Теперь async def do() + await — должны работать.

Запуск:  python3 tests/test_channels_api.py
"""
import asyncio, importlib, json, os, sys, threading

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs('data', exist_ok=True)
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
sys.path.insert(0, _REPO)

PASS = 0; FAIL = 0
def check(ok, msg):
    global PASS, FAIL
    if ok: PASS += 1; print(f'  PASS: {msg}')
    else: FAIL += 1; print(f'  FAIL: {msg}')

# ---------- фейковый Discord ----------
class FakeChannel:
    def __init__(self, cid, name, ctype='text'):
        self.id = cid; self.name = name; self.type = ctype
        self.topic = None; self.position = 0; self.category = None
        self.user_limit = 0; self.bitrate = 64000; self.deleted = False
        self.purged = 0
    async def edit(self, **kw):
        for k, v in kw.items():
            if k == 'category': self.category = v
            else: setattr(self, k, v)
        return self
    async def delete(self, reason=None): self.deleted = True
    async def purge(self, limit=10):
        self.purged += limit
        return [object()] * limit

class FakeRole:
    def __init__(self, rid, name):
        self.id = rid; self.name = name; self.members = []; self.deleted = False
    async def delete(self, reason=None): self.deleted = True

class FakeMember:
    def __init__(self, mid):
        self.id = mid; self.roles = []; self.timed_out = False
        self.kicked = False; self.sent = []
    async def add_roles(self, *rs, reason=None): self.roles.extend(rs)
    async def remove_roles(self, *rs, reason=None):
        for r in rs:
            if r in self.roles: self.roles.remove(r)
    async def timeout(self, delta, reason=None): self.timed_out = True
    async def kick(self, reason=None): self.kicked = True
    async def send(self, content=None, embed=None):
        self.sent.append(content or (embed.title if embed else ''))
    @property
    def display_name(self): return f'User{self.id}'

class FakeGuild:
    def __init__(self):
        self.id = 777; self.name = 'TestGuild'
        ch = FakeChannel(101, 'general'); ch.topic = 'old topic'
        self._channels = {101: ch}
        member = FakeMember(301)
        r_member = FakeRole(201, 'Member'); r_member.members.append(member)
        r_mod = FakeRole(202, 'Mod')
        self._roles = {201: r_member, 202: r_mod}
        self._members = {301: member}
        self.created_channels = []
        self.banned_members = []
        class _Me:
            top_role = None
            premium_subscriber_role = None
            async def _req(*a, **k): return None
        self.me = _Me()
    def get_channel(self, cid): return self._channels.get(cid)
    def get_role(self, rid): return self._roles.get(rid)
    def get_member(self, mid): return self._members.get(mid)
    @property
    def channels(self): return list(self._channels.values())
    @property
    def text_channels(self): return [c for c in self._channels.values() if c.type == 'text']
    @property
    def roles(self): return list(self._roles.values())
    async def create_text_channel(self, name, **kw):
        c = FakeChannel(1000 + len(self._channels), name)
        self._channels[c.id] = c; self.created_channels.append(('text', name, kw)); return c
    async def create_voice_channel(self, name, **kw):
        c = FakeChannel(1000 + len(self._channels), name, 'voice')
        self._channels[c.id] = c; self.created_channels.append(('voice', name, kw)); return c
    async def create_category(self, name, **kw):
        c = FakeChannel(1000 + len(self._channels), name, 'category')
        self._channels[c.id] = c; self.created_channels.append(('category', name, kw)); return c
    async def create_role(self, name, **kw):
        r = FakeRole(2000 + len(self._roles), name)
        self._roles[r.id] = r; self.created_role = (name, kw); return r
    async def ban(self, member, reason=None, delete_message_days=0):
        self.banned_members.append(member.id)

guild = FakeGuild()

class FakeBot:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._t = threading.Thread(target=self.loop.run_forever, daemon=True)
        self._t.start()
        class _Avatar: url = 'http://x/a.png'
        class _User: display_avatar = _Avatar()
        self.user = _User()
    def get_guild(self, gid): return guild if gid == 777 else None
    def get_channel(self, cid): return guild.get_channel(cid)
    async def fetch_user(self, uid):
        if uid not in guild._members:
            guild._members[uid] = FakeMember(uid)
        return guild._members[uid]

fake_bot = FakeBot()

# ---------- Flask app ----------
appmod = importlib.import_module('web.app')
appmod.set_bot_instance(fake_bot)
app = appmod.app
app.config['TESTING'] = True
client = app.test_client()

with client.session_transaction() as s:
    s['logged_in'] = True; s['username'] = 'admin'; s['role'] = 'owner'

def post(url, payload):
    r = client.post(url, data=json.dumps(payload), content_type='application/json')
    try: body = r.get_json()
    except Exception: body = {'raw': r.data[:200]}
    return r.status_code, body

print('== каналы ==')
code, b = post('/api/guild/777/channels/create', {'name': 'noviy-kanal', 'type': 'text', 'topic': 'tema'})
check(code == 200 and b.get('success'), f'create text channel -> {code} {str(b)[:120]}')
check(any(n == 'noviy-kanal' for t, n, kw in guild.created_channels), 'канал реально создан в гильдии')

code, b = post('/api/guild/777/channels/101/update', {'name': 'renamed', 'topic': 'НОВАЯ ТЕМА', 'position': 3})
check(code == 200 and b.get('success'), f'update channel -> {code} {str(b)[:120]}')
check(guild.get_channel(101).name == 'renamed' and guild.get_channel(101).topic == 'НОВАЯ ТЕМА',
      f'имя/тема применились (topic={guild.get_channel(101).topic!r})')

code, b = post('/api/guild/777/channels/101/delete', {})
check(code == 200 and b.get('success'), f'delete channel -> {code} {str(b)[:120]}')
check(guild.get_channel(101).deleted, 'канал реально удалён')

code, b = post('/api/guild/777/channels/create', {'name': '', 'type': 'text'})
check(not b.get('success') and 'Название' in str(b.get('error', '')), f'пустое имя -> RU-ошибка: {str(b)[:90]}')

code, b = post('/api/guild/999/channels/create', {'name': 'x', 'type': 'text'})
check(not b.get('success'), f'нет гильдии -> ошибка без краша: {str(b)[:90]}')

print('== роли ==')
code, b = post('/api/guild/777/roles/create', {'name': 'Nova Rol', 'color': '#ffaa00', 'hoist': True})
check(code == 200 and b.get('success'), f'create role -> {code} {str(b)[:120]}')
check(guild.created_role[0] == 'Nova Rol', 'роль реально создана')
rid = [r for r in guild.roles if r.name == 'Nova Rol'][0].id
code, b = post(f'/api/guild/777/roles/{rid}/delete', {})
check(code == 200 and b.get('success'), f'delete role -> {code} {str(b)[:120]}')

print('== DM ==')
code, b = post('/api/dm/777/301/send', {'content': 'privet'})
check(code == 200 and b.get('ok'), f'dm send -> {code} {str(b)[:120]}')
check(guild.get_member(301).sent and guild.get_member(301).sent[-1] == 'privet', 'DM реально доставлен')
code, b = post('/api/dm/777/301/send', {'content': '   '})
check(code == 400 and 'пусто' in str(b.get('error', '')).lower(), f'пустое DM -> RU-ошибка: {str(b)[:90]}')

print('== purge ==')
code, b = post('/api/guild/777/purge', {'channel_id': 101, 'count': 7})
check(code == 200 and b.get('success') and b.get('count') == 7, f'purge -> {code} {str(b)[:120]}')

print('== массовые операции ==')
m301 = guild.get_member(301)
code, b = post('/api/guild/777/bulk-roles', {'target_role': 201, 'action_role': 202, 'action': 'add'})
check(code == 200 and b.get('success') and b.get('count') == 1, f'bulk add role -> {code} {str(b)[:120]}')
check(any(r.id == 202 for r in m301.roles), 'роль 202 выдана участнику')
code, b = post('/api/guild/777/bulk-roles', {'target_role': 201, 'action_role': 202, 'action': 'remove'})
check(code == 200 and b.get('success'), f'bulk remove role -> {code} {str(b)[:120]}')
check(not any(r.id == 202 for r in m301.roles), 'роль 202 снята')
code, b = post('/api/guild/777/bulk-dm', {'role_id': 201, 'message': 'ob-yavleniye'})
check(code == 200 and b.get('success') and b.get('count') == 1, f'bulk dm -> {code} {str(b)[:120]}')
check(any('Объявление' in str(x) for x in m301.sent), 'объявление доставлено')
code, b = post('/api/guild/777/bulk-mute', {'role_id': 201, 'duration': 10})
check(code == 200 and b.get('success') and b.get('count') == 1, f'bulk mute -> {code} {str(b)[:120]}')
check(m301.timed_out, 'мут применён')
code, b = post('/api/guild/777/bulk-kick', {'role_id': 201})
check(code == 200 and b.get('success') and b.get('count') == 1, f'bulk kick -> {code} {str(b)[:120]}')
check(m301.kicked, 'кик применён')
code, b = post('/api/guild/777/bulk-ban', {'role_id': 201})
check(code == 200 and b.get('success') and b.get('count') == 1, f'bulk ban -> {code} {str(b)[:120]}')
check(301 in guild.banned_members, 'бан применён')

print('== скрытые каналы — фильтр по роли ==')
from web.routes import guild_admin as ga  # noqa: E402
_hid = [{'id': '1', 'name': 'secret', 'hidden': True},
        {'id': '2', 'name': 'general', 'hidden': False}]
check(ga._visible_channels(_hid, 'mod') == [{'id': '2', 'name': 'general', 'hidden': False}],
      'модератор не видит hidden-каналы')
check(len(ga._visible_channels(_hid, 'owner')) == 2,
      'владелец видит скрытые (глазик на /channels)')
pj = open(os.path.join(_REPO, 'web', 'static', 'pickers.js'), encoding='utf-8').read()
check(pj.count('!c.hidden') >= 2, 'оба source() пикеров пропускают hidden')

print('== cache-hit /channels через _channels_respond ==')
ga_src = open(os.path.join(_REPO, 'web', 'routes', 'guild_admin.py'), encoding='utf-8').read()
hit = ga_src.find('if _hit and (_now - _hit[0]) < 10.0:')
miss = ga_src.find('type_map', hit)
block = ga_src[hit:miss] if hit >= 0 and miss > hit else ''
check('_annotate_hidden' in block and '_channels_respond' in block,
      'cache-hit переаннотирует hidden и отдаёт через _channels_respond')
check('json.dumps(_payload' not in block,
      'cache-hit не отдаёт сырой _payload в обход фильтра роли')
vis = ga_src.find('def api_channels_visibility')
vis_block = ga_src[vis:vis + 1800] if vis >= 0 else ''
check('_live_cache' in vis_block and 'live.pop' in vis_block.replace(' ', ''),
      'visibility POST сбрасывает _live_cache гильдии')

# Живой cache-hit: мод не видит hidden даже со второго запроса
import time as _t
_fn = app.view_functions.get('api_guild_channels')
_hid_path = os.path.join(_REPO, 'data', 'hidden_channels.json')
os.makedirs(os.path.join(_REPO, 'data'), exist_ok=True)
with open(_hid_path, 'w', encoding='utf-8') as fp:
    json.dump({'777': {'channels': ['101'], 'categories': []}}, fp)
nchan = len(guild.channels) + len(getattr(guild, 'threads', []) or [])
seed = [{'id': '101', 'name': 'secret', 'type': 'text', 'hidden': True},
        {'id': '102', 'name': 'general', 'type': 'text', 'hidden': False}]
if _fn is not None:
    _fn._live_cache = {('777', nchan): (_t.time(), seed)}
with client.session_transaction() as s:
    s['role'] = 'mod'
r = client.get('/api/guild/777/channels')
try:
    body = r.get_json()
except Exception:
    body = None
ids = [str(c.get('id')) for c in body] if isinstance(body, list) else []
check(_fn is not None and r.status_code == 200 and isinstance(body, list),
      f'cache-hit GET ок: fn={_fn is not None} {r.status_code} {str(body)[:80]}')
check('101' not in ids, 'cache-hit: модератор не видит hidden')
check('102' in ids, 'cache-hit: модератор видит открытый')
with client.session_transaction() as s:
    s['role'] = 'owner'
r = client.get('/api/guild/777/channels')
try:
    body = r.get_json()
except Exception:
    body = None
ids = [str(c.get('id')) for c in body] if isinstance(body, list) else []
check('101' in ids and '102' in ids, 'cache-hit: владелец видит скрытые')
try:
    os.remove(_hid_path)
except OSError:
    pass
if _fn is not None:
    _fn._live_cache = {}
with client.session_transaction() as s:
    s['role'] = 'owner'

print('== устойчивость списка каналов ==')
# один «битый» объект канала (как повреждённые данные Discord) не должен
# ронять весь /api/guild/<gid>/channels — остальные каналы остаются в выдаче
class BrokenChannel:
    def __init__(self): self.id = 999
    @property
    def type(self): raise RuntimeError('boom: corrupted channel object')

guild._channels[999] = BrokenChannel()
r = client.get('/api/guild/777/channels')
try: body = r.get_json()
except Exception: body = None
check(r.status_code == 200 and isinstance(body, list), f'битый канал не роняет список: {r.status_code} {str(body)[:80]}')
check(isinstance(body, list) and any(c.get('id') == '101' for c in body),
      'здоровые каналы остались в выдаче (битый пропущен)')
check(isinstance(body, list) and not any(c.get('id') == '999' for c in body),
      'битый канал действительно пропущен, а не сломал JSON')
del guild._channels[999]

fake_bot.loop.call_soon_threadsafe(fake_bot.loop.stop)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
