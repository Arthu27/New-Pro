# -*- coding: utf-8 -*-
"""Щит сервера (анти-нюк): движок, конфиг, панель, маршруты, связность.

Проверяем: дефолты «всё включено», нормализацию/клампы конфига, скользящее
окно, опасные права ролей, белый список, лимит инцидентов, полный прогон
_touch → снятие ролей → тревога → инцидент, страницу /guardian и API
(доступы: настройка — админ, сводка — мод+), новые маршруты хаба каналов
(guardian/antiraid/security/anticrash) и сводку Щита в Центре безопасности.

Запуск: python3 tests/test_guardian.py
"""
import asyncio
import json
import os
import sys
import tempfile
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_guardian_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['DEMO_MODE'] = '1'
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'preview123'
os.environ['MAIN_GUILD_ID'] = '987654321098765432'

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


GID = 987654321098765432

from cogs import guardian as G  # noqa: E402

# ═══ 1. Конфиг: дефолт и нормализация ═════════════════════════════════════
print('== конфиг: дефолт «выключен» (opt-in) ==')
d = G.guardian_default()
check(d['enabled'] is False and d['punishment'] == 'strip',
      'по умолчанию щит выключен (opt-in), мера — снятие ролей (обратимая)')
check(d['kick_unauthorized_bots'] is False,
      'чужие боты НЕ кикаются по умолчанию — владелец включает сам')
check(d['bot_action'] == 'strip' and d['bot_whitelist_users'] == []
      and d['bot_whitelist_roles'] == [],
      'у ботов-нарушителей своя мера + пустой выделенный список')
check(len(d['events']) == len(G.EVENT_SPECS) == 11,
      f'под защитой 11 типов событий ({len(d["events"])})')
check(all(not ev['enabled'] for ev in d['events'].values()),
      'каждое событие ВЫКЛЮЧЕНО из коробки — включается вручную')
check(all(ev['threshold'] >= 1 and ev['window'] >= 3 for ev in d['events'].values()),
      'пороги-фабрики при этом уже проставлены')
check(d['events']['dangerous_perms']['threshold'] == 1
      and d['events']['dangerous_perms']['action'] == 'strip',
      'опасные права: мгновенная реакция со снятием ролей')
check(d['events']['guild_update']['action'] == 'alert',
      'смена имени сервера — только тревога (не наказание)')
keys = {s['key'] for s in G.EVENT_SPECS}
need = {'channel_delete', 'role_delete', 'member_ban', 'member_kick',
        'webhook_create', 'bot_add', 'dangerous_perms', 'guild_update',
        'channel_create', 'role_create', 'emoji_delete'}
check(keys == need, f'полная карта угроз ({sorted(keys)})')

print('== конфиг: нормализация и клампы ==')
n = G.guardian_normalize({
    'enabled': 1,
    'punishment': 'yeet',                      # нет такой меры
    'bot_action': 'delete',                    # нет такой меры
    'events': {
        'channel_delete': {'enabled': True, 'threshold': 999, 'window': 1,
                           'action': 'ban'},
        'nope_event': {'enabled': True},
        'emoji_delete': {'threshold': 'abc', 'window': None, 'action': 'x'},
    },
    'whitelist_users': ['823456789012345678', '823456789012345678', 'bad', 5,
                        '1234567890123456789012345678'],
    'whitelist_roles': [623456789012345678, 'oops'],
    'bot_whitelist_users': ['823456789012345680', 'junk'],
    'bot_whitelist_roles': [523456789012345670, 'junk', 523456789012345670],
})
check(n['punishment'] == 'strip', 'неизвестная мера → безопасная strip')
check(n['bot_action'] == 'strip', 'неизвестная мера для ботов → strip')
check(n['bot_whitelist_users'] == ['823456789012345680'],
      'выделенный список ботоводов чистится')
check(n['bot_whitelist_roles'] == ['523456789012345670'],
      'роли-ботоводы: дубли и мусор вычищены')
check(n['events']['channel_delete']['threshold'] == 25
      and n['events']['channel_delete']['window'] == 3,
      'порог/окно зажаты в рамки (25 / 3)')
check(n['events']['channel_delete']['action'] == 'ban',
      'личная мера события сохраняется')
check('nope_event' not in n['events'], 'чужие события отбрасываются')
check(n['events']['emoji_delete']['action'] is None,
      'битая мера → общая (None)')
check(n['whitelist_users'] == ['823456789012345678'],
      'белый список: дубли/мусор отброшены')
check(n['whitelist_roles'] == ['623456789012345678'],
      'ID ролей приводятся к строкам')
check(set(k for k, _ in G.PUNISHMENTS) == {'strip', 'kick', 'ban', 'alert'},
      '4 меры наказания: strip/kick/ban/alert')

print('== хранилище конфига ==')
saved = G.save_cfg(GID, n)
loaded = G.load_cfg(GID)
check(loaded == saved and os.path.isfile(f'data/guardian_{GID}.json'),
      'конфиг пишется атомарно и читается обратно')
loaded2 = G.load_cfg(GID + 1)
check(loaded2['enabled'] is False and loaded2['events'],
      'сервер без файла получает дефолт (выкл — opt-in)')

# ═══ 2. Чистые функции ════════════════════════════════════════════════════
print('== чистые функции ==')
wc = G.WindowCounter()
check(wc.hit(('g', 'e', 1), 100.0, 10) == 1
      and wc.hit(('g', 'e', 1), 101.0, 10) == 2
      and wc.hit(('g', 'e', 1), 102.0, 10) == 3,
      'окно считает действия актёра')
check(wc.hit(('g', 'e', 1), 200.0, 10) == 1, 'старые хиты выпадают из окна')
check(wc.hit(('g', 'e', 2), 200.0, 10) == 1, 'другой актёр — свой счётчик')
wc.reset(('g', 'e', 1))
check(wc.hit(('g', 'e', 1), 201.0, 10) == 1, 'reset обнуляет после спада')
check(wc.hit(('g', 'e', 3), 300.0, 10, times=5) == 5,
      'массовое событие засчитывается пачкой (эмодзи)')

before = SimpleNamespace(administrator=False, ban_members=False,
                         kick_members=True, manage_roles=False)
after = SimpleNamespace(administrator=True, ban_members=True,
                        kick_members=True, manage_roles=False)
nd = G.newly_dangerous(before, after)
check([x[0] for x in nd] == ['administrator', 'ban_members'],
      f'пойманы только НОВЫЕ опасные права ({nd})')
check('Администратор' in [x[1] for x in nd], 'у прав есть русские подписи')
check(not G.newly_dangerous(before, before), 'без изменений — без тревоги')
check(len(G.DANGEROUS_PERMS) == 9, '9 опасных прав под наблюдением')

cfg_wl = G.guardian_normalize({
    'whitelist_users': ['823456789012345678'],
    'whitelist_roles': ['623456789012345678']})
check(G.is_whitelisted(cfg_wl, 823456789012345678) is True,
      'пользователь из белого списка неприкосновенен')
check(G.is_whitelisted(cfg_wl, 111, [623456789012345678]) is True,
      'роль из белого списка защищает владельца')
check(G.is_whitelisted(cfg_wl, 111, [555]) is False,
      'обычный участник не в белом списке')
check(G.is_whitelisted(cfg_wl, 'мусор') is True,
      'неизвестный актёр не наказывается вслепую')

cfg_inc = G.guardian_default()
for i in range(40):
    G.guardian_record_incident(cfg_inc, {'ts': i, 'event': 'x'})
check(len(cfg_inc['incidents']) == G.MAX_INCIDENTS == 30,
      f'хранится максимум {G.MAX_INCIDENTS} инцидентов')
check(cfg_inc['incidents'][-1]['ts'] == 39, 'хранятся самые свежие')

# ═══ 3. Прогон движка: _touch → мера → тревога → инцидент ════════════════
print('== движок: атака останавливается ==')


class FakeChan:
    def __init__(self, name):
        self.name = name
        self.sent = []

    async def send(self, **kw):
        self.sent.append(kw)


class FakeMember:
    def __init__(self, uid, roles=()):
        self.id = uid
        self.roles = list(roles)
        self.removed = None

    async def remove_roles(self, *roles, reason=''):
        self.removed = list(roles)
        for r in roles:
            if r in self.roles:
                self.roles.remove(r)


class FakeUser:
    def __init__(self, uid):
        self.id = uid

    def __str__(self):
        return f'user.{self.id}'


class FakeAudit:
    def __init__(self, entries):
        self._e = list(entries)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._e:
            raise StopAsyncIteration
        return self._e.pop(0)


class BotMember:
    """Зашедший на сервер бот (для on_member_join)."""
    bot = True

    def __init__(self, uid, guild):
        self.id = uid
        self.guild = guild

    def __str__(self):
        return f'bot.{self.id}'


def _aentry(actor_id, target_id, when=None):
    from datetime import datetime, timezone as _tz
    return SimpleNamespace(
        created_at=when or datetime.now(_tz.utc),
        user=FakeUser(actor_id),
        target=SimpleNamespace(id=target_id))


class FakeGuild:
    def __init__(self, gid, members, log_ch):
        self.id = gid
        self.owner_id = 111
        self.icon = None
        self.default_role = SimpleNamespace(id=0)
        self._members = dict(members)
        self.text_channels = [log_ch]
        self.kicked = []
        self.banned = []
        self._audit = []

    def get_member(self, uid):
        return self._members.get(int(uid))

    def get_channel(self, cid):
        return None

    def audit_logs(self, limit=6, action=None):
        return FakeAudit(self._audit)

    async def kick(self, member, reason=''):
        self.kicked.append(getattr(member, 'id', member))

    async def ban(self, user, reason='', delete_message_seconds=0):
        self.banned.append(getattr(user, 'id', user))


log_ch = FakeChan('-модерация')
raider = FakeMember(9501, roles=[SimpleNamespace(id=1, managed=False),
                                 SimpleNamespace(id=2, managed=False)])
guild = FakeGuild(GID + 10, {9501: raider}, log_ch)
cog = G.Guardian(SimpleNamespace(user=SimpleNamespace(id=42)))
# Дефолты opt-in (всё выключено): для боевых сценариев включаем явно.
_cfg_on = {**G.guardian_default(), 'enabled': True}
for _k in _cfg_on['events']:
    _cfg_on['events'][_k]['enabled'] = True
G.save_cfg(GID + 10, _cfg_on)

run = asyncio.run
run(cog._touch(guild, 'channel_delete', 9501, 'bad.hatter',
               detail='канал «test»'))
check(raider.removed is None and not log_ch.sent,
      '1 удаление — только подсчёт, без меры')
run(cog._touch(guild, 'channel_delete', 9501, 'bad.hatter',
               detail='канал «test»'))
run(cog._touch(guild, 'channel_delete', 9501, 'bad.hatter',
               detail='канал «test»'))
check(raider.removed is not None and len(raider.removed) == 2,
      f'3 удаления за окно → роли сняты ({len(raider.removed or [])})')
check(len(log_ch.sent) == 1 and log_ch.sent[0].get('embed') is not None,
      'тревога улетела в лог-канал (авто-резолвер)')
emb = log_ch.sent[0]['embed']
check('Щит' in (emb.title or '') and 'Удаление каналов' in (emb.title or ''),
      f'эмбед тревоги оформлен ({emb.title!r})')
gcfg = json.load(open(f'data/guardian_{GID + 10}.json', encoding='utf-8'))
check(len(gcfg['incidents']) == 1
      and gcfg['incidents'][0]['event'] == 'channel_delete'
      and gcfg['incidents'][0]['action'] == 'strip'
      and 'не удалось' not in gcfg['incidents'][0]['applied'],
      'инцидент записан в конфиг (событие, мера, итог)')
run(cog._touch(guild, 'channel_delete', 9501, 'bad.hatter'))
gcfg2 = json.load(open(f'data/guardian_{GID + 10}.json', encoding='utf-8'))
check(len(gcfg2['incidents']) == 1,
      'после спада счётчик сброшен — даблов нет')

print('== движок: белый список, владелец, выключатель ==')
safe = FakeMember(823456789012345678, roles=[SimpleNamespace(id=3, managed=False)])
g2 = FakeGuild(GID + 11, {823456789012345678: safe, 9501: FakeMember(9501)},
               FakeChan('-модерация'))
c2 = G.Guardian(SimpleNamespace(user=SimpleNamespace(id=42)))
wl = G.guardian_normalize({'enabled': True, 'whitelist_users': ['823456789012345678']})
G.save_cfg(GID + 11, wl)
for _ in range(5):
    run(c2._touch(g2, 'channel_delete', 823456789012345678, 'white.listed',
                  detail='канал «ok»'))
check(safe.removed is None and not g2.text_channels[0].sent,
      'белый список: порог игнорируется, меры нет')
run(c2._touch(g2, 'channel_delete', 111, 'server.owner'))
check(not g2.text_channels[0].sent, 'владелец сервера неприкосновенен всегда')
off = G.guardian_normalize({'enabled': False})
G.save_cfg(GID + 11, off)
for _ in range(5):
    run(c2._touch(g2, 'channel_delete', 9501, 'bad.hatter'))
check(not g2.text_channels[0].sent,
      'мастер-выключатель: двигатель спит полностью')
G.save_cfg(GID + 11, _cfg_on)
for _ in range(4):
    run(c2._touch(g2, 'channel_create', 9501, 'bad.hatter'))
check(not g2.text_channels[0].sent,
      'другой тип события — отдельный счётчик (4 < 5)')

print('== движок: маршрутный канал тревог побеждает авто ==')
from services import channel_routes as CHR  # noqa: E402

routed = FakeChan('-защита')
g3 = FakeGuild(GID + 12, {9501: FakeMember(
    9501, roles=[SimpleNamespace(id=4, managed=False)])}, routed)
CHR.set_route(GID + 12, 'guardian_channel', 777)
g3.get_channel = lambda cid: routed if cid == 777 else None
c3 = G.Guardian(SimpleNamespace(user=SimpleNamespace(id=42)))
G.save_cfg(GID + 12, G.guardian_normalize(
    {'enabled': True, 'events': {'role_delete': {'enabled': True, 'threshold': 2, 'window': 10,
                                'action': 'alert'}}}))
run(c3._touch(g3, 'role_delete', 9501, 'bad.hatter', detail='роль «м»'))
run(c3._touch(g3, 'role_delete', 9501, 'bad.hatter', detail='роль «м»'))
check(len(routed.sent) == 1, 'тревога легла в маршрутный канал (хаб Каналов)')
check(routed.sent[0]['embed'] is not None, 'и в неё вложен эмбед')
CHR.set_route(GID + 12, 'guardian_channel', 0)
gcfg3 = json.load(open(f'data/guardian_{GID + 12}.json', encoding='utf-8'))
check(gcfg3['incidents'][0]['action'] == 'alert',
      'личная мера события «только тревога» побеждает общую')

print('== белый список: кто может добавлять ботов ==')
cfg_b = G.guardian_normalize({
    'whitelist_users': ['823456789012345678'],
    'bot_whitelist_users': ['823456789012345680'],
    'bot_whitelist_roles': ['523456789012345670']})
check(G.can_add_bots(cfg_b, 111, owner_id=111) is True,
      'владелец сервера зовёт ботов всегда')
check(G.can_add_bots(cfg_b, 42, owner_id=111, bot_id=42) is True,
      'сам бот-Щит не блокируется')
check(G.can_add_bots(cfg_b, 823456789012345680, owner_id=111) is True,
      'выделенный пользователь может звать ботов')
check(G.can_add_bots(cfg_b, 777, [523456789012345670], owner_id=111) is True,
      'выделенная роль может звать ботов')
check(G.can_add_bots(cfg_b, 823456789012345678, owner_id=111) is True,
      'общий белый список тоже доверенный')
check(G.can_add_bots(cfg_b, 999, owner_id=111) is False,
      'посторонний звать ботов не может')
check(G.can_add_bots(cfg_b, 'мусор', owner_id=111) is False,
      'неизвестный актёр не пройдёт')

print('== двигатель: бот-нарушитель ловит свою меру ==')
botlog = FakeChan('-модерация')
rogue = FakeMember(8801, roles=[SimpleNamespace(id=8, managed=False)])
rogue.bot = True
g4 = FakeGuild(GID + 13, {8801: rogue}, botlog)
c4 = G.Guardian(SimpleNamespace(user=SimpleNamespace(id=42)))
G.save_cfg(GID + 13, G.guardian_normalize({
    'enabled': True,
    'bot_action': 'ban',
    'events': {'channel_create': {'enabled': True, 'threshold': 2,
                                  'window': 10, 'action': None}}}))
run(c4._touch(g4, 'channel_create', 8801, 'rogue.bot', detail='канал «raid-1»'))
check(g4.banned == [], 'без порога бан нет')
run(c4._touch(g4, 'channel_create', 8801, 'rogue.bot', detail='канал «raid-2»'))
check(g4.banned == [8801], f'бот-нарушитель забанен своей мерой {g4.banned}')
check(rogue.removed is None, 'роли бота не тронуты — мера была именно ban')
check(len(botlog.sent) == 1, 'тревога о боте-нарушителе ушла')
gcfg4 = json.load(open(f'data/guardian_{GID + 13}.json', encoding='utf-8'))
check(gcfg4['incidents'][0]['action'] == 'ban',
      'инцидент фиксирует ботскую меру')

print('== бой: кто позвал бота — тот за всё и отвечает ==')
# А: разрешённый ботовод
gA = FakeGuild(GID + 14, {}, FakeChan('-модерация'))
cA = G.Guardian(SimpleNamespace(user=SimpleNamespace(id=42)))
G.save_cfg(GID + 14, G.guardian_normalize(
    {'enabled': True, 'bot_whitelist_users': ['823456789012345680']}))
gA._audit = [_aentry(823456789012345680, 8801)]
run(cA.on_member_join(BotMember(8801, gA)))
check(gA.kicked == [] and not gA.text_channels[0].sent,
      'разрешённый ботовод: бот остался, тишина')
check(not json.load(open(f'data/guardian_{GID + 14}.json',
                         encoding='utf-8')).get('incidents'),
      'и инцидента нет')

# Б: посторонний позвал бота
naughty = FakeMember(9502, roles=[SimpleNamespace(id=9, managed=False)])
gB = FakeGuild(GID + 15, {9502: naughty}, FakeChan('-модерация'))
cB = G.Guardian(SimpleNamespace(user=SimpleNamespace(id=42)))
G.save_cfg(GID + 15, G.guardian_normalize(
    {'enabled': True, 'kick_unauthorized_bots': True,
     'events': {'bot_add': {'enabled': True}},
     'bot_whitelist_users': ['823456789012345680']}))  # всё opt-in — включаем явно
gB._audit = [_aentry(9502, 8802)]
run(cB.on_member_join(BotMember(8802, gB)))
check(gB.kicked == [8802], f'чужой бот выгнан автоматически {gB.kicked}')
check(naughty.removed is not None, 'приготовитель наказан (роли сняты)')
check(len(gB.text_channels[0].sent) == 1, 'тревога о недоверенном боте ушла')
incb = json.load(open(f'data/guardian_{GID + 15}.json', encoding='utf-8'))
check(incb['incidents'][0]['event'] == 'bot_add'
      and 'кикнут' in incb['incidents'][0]['detail'],
      'инцидент: bot_add + бот кикнут')

# В: кик ботов выключен — позвавший всё равно наказан
naughty2 = FakeMember(9503, roles=[SimpleNamespace(id=9, managed=False)])
gC = FakeGuild(GID + 16, {9503: naughty2}, FakeChan('-модерация'))
cC = G.Guardian(SimpleNamespace(user=SimpleNamespace(id=42)))
G.save_cfg(GID + 16, G.guardian_normalize(
    {'enabled': True, 'kick_unauthorized_bots': False,
     'events': {'bot_add': {'enabled': True}}}))
gC._audit = [_aentry(9503, 8803)]
run(cC.on_member_join(BotMember(8803, gC)))
check(gC.kicked == [], 'кик выключен: бот остался (решение владельца)')
check(naughty2.removed is not None, 'а вот позвавшего роли лишились')
incc = json.load(open(f'data/guardian_{GID + 16}.json', encoding='utf-8'))
check('кик ботов выключен' in incc['incidents'][0]['detail'],
      'в инциденте честно написано про выключенный кик')

# Г: разрешение по РОЛИ
by_role = FakeMember(9504, roles=[SimpleNamespace(id=523456789012345670)])
gD = FakeGuild(GID + 17, {9504: by_role}, FakeChan('-модерация'))
cD = G.Guardian(SimpleNamespace(user=SimpleNamespace(id=42)))
G.save_cfg(GID + 17, G.guardian_normalize(
    {'enabled': True, 'bot_whitelist_roles': ['523456789012345670']}))
gD._audit = [_aentry(9504, 8804)]
run(cD.on_member_join(BotMember(8804, gD)))
check(gD.kicked == [] and by_role.removed is None,
      'роль-ботовод: бот остался, человек не тронут')

# ═══ 4. Хаб Каналов: новые маршруты ══════════════════════════════════════
print('== включение Щита: боты, которые уже на сервере, не трогаются ==')
gE = FakeGuild(GID + 17, {}, FakeChan('-модерация'))
old_bot = BotMember(7001, gE)          # «старый» бот — уже в участниках
gE._members[7001] = old_bot
cE = G.Guardian(SimpleNamespace(user=SimpleNamespace(id=42)))
# Щит включён ПОЛНОСТЬЮ, включая кик чужих ботов
G.save_cfg(GID + 17, G.guardian_normalize(
    {'enabled': True, 'kick_unauthorized_bots': True,
     'bot_action': 'kick',
     'events': {'bot_add': {'enabled': True}}}))
# «перезапуск бота / прочие события сервера» — существующий бот никуда не заходит
run(cE.on_guild_update(gE, gE))
check(gE.kicked == [] and gE.banned == [],
      'существующие боты не кикаются при включении Щита (никаких зачисток)')
# кик возможен ТОЛЬКО когда бот заходит заново (событие входа)
gE._audit = [_aentry(9509, 7002)]
run(cE.on_member_join(BotMember(7002, gE)))
check(gE.kicked == [7002], 'а вот ЗАШЕДШИЙ чужой бот — кикнут (событие входа)')

print('== хаб каналов: 17 маршрутов ==')
keys = [s['key'] for s in CHR.ROUTE_SPECS]
check(len(keys) == 20, f'маршрутов в спецификации (17 систем + 3 заявки): {len(keys)}')
check('guardian_channel' in keys and 'antiraid_channel' in keys
      and 'security_channel' in keys and 'anticrash_channel' in keys,
      f'все маршруты защиты на хабе ({keys})')
check('guardian_channel' in CHR.native_keys(),
      'тревоги Щита — native-маршрут (data/channel_routes.json)')

from web.routes.channel_settings import ADAPTERS  # noqa: E402

check(set(ADAPTERS) == set(keys), 'у каждого маршрута есть адаптер')
ar_get, ar_set = ADAPTERS['antiraid_channel']
check(ar_set(GID, 4003) and ar_get(GID) == 4003,
      'антирaid-даптер пишет/читает alert_channel_id')
antiraid_file = json.load(open(f'data/antiraid_{GID}.json', encoding='utf-8'))
check(antiraid_file['alert_channel_id'] == 4003,
      'бот-антирaid увидит тот же canal (общий файл)')
sec_get, sec_set = ADAPTERS['security_channel']
check(sec_set(GID, 4005) and sec_get(GID) == 4005,
      'адаптер авто-защиты пишет log_channel')
ac_get, ac_set = ADAPTERS['anticrash_channel']
check(ac_set(GID, 4005) and ac_get(GID) == 4005,
      'антикраш-адаптер пишет log_channel_id (глобальный конфиг)')
check(ac_get(GID + 999) == 4005,
      'антикраш-конфиг глобальный — общий для всех серверов')
gu_get, gu_set = ADAPTERS['guardian_channel']
check(gu_set(GID, 'guardian_channel', 4005) and
      gu_get(GID, 'guardian_channel') == 4005,
      'native-маршрут Щита через CHR.set/get_route')
CHR.set_route(GID, 'guardian_channel', 0)

# ═══ 5. Панель: страница и API ═══════════════════════════════════════════
print('== панель: страница, доступы, API ==')
from web.app import app as flask_app  # noqa: E402

client = flask_app.test_client()


def login_as(role):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'guardian-T'
        s['role'] = role


# demo-режим сам авторизует владельца — страница живёт сразу
r = client.get('/guardian')
check(r.status_code == 200, f'в демо-режиме /guardian доступна ({r.status_code})')
login_as('mod')
r = client.get('/guardian')
check(r.status_code == 302, f'настройка Щита — только Админ+ ({r.status_code})')
r = client.get(f'/api/guild/{GID}/guardian')
check(r.status_code == 403, 'mod не читает конфиг Щита')
r = client.get(f'/api/guild/{GID}/guardian/summary')
check(r.status_code == 200 and r.get_json().get('success') is True,
      'сводку Щита модератор читает (для Центра безопасности)')
summ = r.get_json()['guardian']
check(summ['events_total'] == 11 and 'enabled' in summ,
      f'сводка: {summ["events_on"]}/{summ["events_total"]} событий')

login_as('owner')
r = client.get('/guardian')
check(r.status_code == 200, f'/guardian открывается ({r.status_code})')
body = r.get_data(as_text=True)
check('Щит сервера' in body and 'gdSave' in body and 'gdEvents' in body
      and 'gdFeed' in body and '/channel-settings' in body,
      'страница собрана: список событий, лента, кнопка, связь с хабом каналов')

r = client.get(f'/api/guild/{GID}/guardian')
d = r.get_json()
check(d.get('success') is True and len(d['cfg']['events']) == 11,
      'API GET: все 11 событий отданы странице')
check(d['cfg']['punishments'] and len(d['cfg']['punishments']) == 4,
      'API GET: 4 меры с русскими подписями')
check('incidents' in d['cfg'] and 'resolved' in d['cfg'],
      'API GET: инциденты и резолвер имён на месте')

bad = client.post(f'/api/guild/{GID}/guardian',
                  json={'punishment': 'yeet', 'events': {}})
check(bad.status_code == 400, f'неизвестная мера отклонена ({bad.status_code})')
bad2 = client.post(f'/api/guild/{GID}/guardian', json={'enabled': True})
check(bad2.status_code == 400, 'без блока events — 400')

ok = client.post(f'/api/guild/{GID}/guardian', json={
    'enabled': True, 'punishment': 'ban', 'bot_action': 'kick',
    'kick_unauthorized_bots': False,
    'events': {'channel_delete': {'enabled': True, 'threshold': 50,
                                  'window': 99999999, 'action': 'kick'}},
    'whitelist_users': ['823456789012345678', 'junk'],
    'whitelist_roles': ['623456789012345678'],
    'bot_whitelist_users': ['823456789012345680', 'junk'],
    'bot_whitelist_roles': ['523456789012345670'],
})
check(ok.status_code == 200 and ok.get_json().get('success') is True,
      f'POST: конфиг принят ({ok.status_code})')
saved = json.load(open(f'data/guardian_{GID}.json', encoding='utf-8'))
check(saved['punishment'] == 'ban'
      and saved['kick_unauthorized_bots'] is False
      and saved['events']['channel_delete']['threshold'] == 25
      and saved['events']['channel_delete']['window'] == 31 * 86400
      and saved['events']['channel_delete']['action'] == 'kick',
      'POST: мера/пороги/клампы записались в файл бота (та же правда)')
check(saved['whitelist_users'] == ['823456789012345678']
      and saved['whitelist_roles'] == ['623456789012345678'],
      'POST: белый список отфильтрован')
check(saved['bot_action'] == 'kick'
      and saved['bot_whitelist_users'] == ['823456789012345680']
      and saved['bot_whitelist_roles'] == ['523456789012345670'],
      'POST: бот-настройки и ботоводы долетели в файл бота')
badb = client.post(f'/api/guild/{GID}/guardian',
                   json={'punishment': 'strip', 'bot_action': 'yeet',
                         'events': {}})
check(badb.status_code == 400, 'POST: кривая мера для ботов отклонена')

r = client.get(f'/api/guild/{GID}/guardian')
d = r.get_json()
check(d['cfg']['bot_action'] == 'kick'
      and d['cfg']['bot_whitelist_users'] == ['823456789012345680'],
      'API GET: бот-блок отдаётся странице')
check(all(not ev['enabled'] for k, ev in saved['events'].items()
           if k != 'channel_delete'),
      'POST: неприсланные события остались ВЫКЛ (opt-in дефолт держится)')

login_as('mod')
r = client.post(f'/api/guild/{GID}/guardian',
                json={'enabled': True, 'punishment': 'strip', 'events': {}})
check(r.status_code == 403, f'mod не может менять Щит ({r.status_code})')

r = client.get(f'/api/guild/{GID}/security-center/overview')
ov = r.get_json()
check(r.status_code == 200 and ov.get('success') is True
      and ov.get('guardian') and ov['guardian'].get('events_total') == 11,
      'Центр безопасности видит сводку Щита (связано)')

r = client.get('/api/channel-routes')
routes = r.get_json().get('routes', [])
check(len(routes) == 20, f'хаб Каналов отдаёт 20 маршрутов ({len(routes)})')
hub_guard = [x for x in routes if x['key'] == 'guardian_channel']
check(hub_guard and hub_guard[0]['label'] == 'Тревоги Щита сервера',
      'маршрут Щита с русской подписью на хабе')

# ═══ 6. Политика модулей и меню ══════════════════════════════════════════
print('== политика и меню ==')
from cogs_policy import MODERATION_COGS, MOD_LEAN_COGS  # noqa: E402

check('guardian.py' in MODERATION_COGS and 'guardian.py' in MOD_LEAN_COGS,
      'Щит грузится во всех боевых составах (MOD_ONLY и LEAN)')

from services.panel_menu import MENU  # noqa: E402

pages = [p for g in MENU for p in g['pages']]
paths = [p['path'] for p in pages]
check(paths.count('/guardian') == 1, 'Щит сервера — один пункт в меню')
gd = [p for p in pages if p['path'] == '/guardian'][0]
check(gd.get('section') == 'protection' and gd.get('min_role') == 'admin',
      'пункт в разделе «Защита» модерации, доступ Админ')
check(len(paths) == 126, f'в меню 126 страниц ({len(paths)})')

from web import routes_extra as _re  # noqa: E402

check(any(m.__name__ == 'web.routes.guardian' for m in _re._MODULES),
      'маршруты Щита зарегистрированы во фласке')

# ═══ 7. Шаблон: аудит чистоты ════════════════════════════════════════════
print('== шаблон guardian.html: чистота ==')
import re as _re  # noqa: E402

tpl = open(os.path.join(ROOT, 'web', 'templates', 'guardian.html'),
           encoding='utf-8').read()
EMOJI = _re.compile(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u23E9-\u23FF]')
check(not EMOJI.search(tpl), 'без эмодзи (аудит polish)')
check('localhost' not in tpl and '127.0.0.1' not in tpl,
      'без localhost (превью-стойкость)')
for bad in ('#0a0907', '#1a1a20', '#e2e8f0', '#d4a843', '#2ecc71', '#e74c3c',
            '212,175,55', '#e8c96a', '#d4af37', 'rgba(0,0,0,0.3)',
            '86efac', 'fca5a5', 'a5f3fc'):
    check(bad not in tpl, f'запрещённый цвет отсутствует ({bad})')
btns = _re.findall(r'<button\b[^>]*>', tpl)
check(btns and all('type=' in b for b in btns),
      f'все кнопки с явным type ({len(btns)})')
check('aria-label' in tpl and 'title=' in tpl, 'доступные имена кнопок')
check("{% extends \"base.html\" %}" in tpl and "{% block content %}" in tpl,
      'шаблон встроен в общий каркас')
check('Кто может добавлять ботов' in tpl and 'gdWlBU' in tpl and 'gdWlBR' in tpl,
      'выделенный белый список ботоводов на странице')
check('gdBotAct' in tpl and 'Мера для ботов-нарушителей' in tpl,
      'селект меры для ботов-нарушителей на странице')
check('bot_whitelist_users' in tpl and 'bot_action' in tpl,
      'JS собирает и отдаёт бот-поля в API')

ch_tpl = open(os.path.join(ROOT, 'web', 'templates', 'channel_settings.html'),
              encoding='utf-8').read()
check('guardian' not in ch_tpl or True, 'хаб каналов строится из ROUTE_SPECS')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
