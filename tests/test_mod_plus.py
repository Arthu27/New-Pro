# -*- coding: utf-8 -*-
"""Тесты cogs/mod_plus.py — snipe / sticky / panic-lockdown.

Запуск: python3 tests/test_mod_plus.py
"""
import asyncio
import json
import os
import sys
import tempfile
import time

# временная рабочая директория — data/* не мусорит в репо
_TMP = tempfile.mkdtemp(prefix='aether_modplus_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord

from cogs.mod_plus import ModPlus, _sticky_path, _panic_path, STICKY_REPOST_COOLDOWN

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


# ─── фейки ─────────────────────────────────────────────────────────────
class FakeAvatar:
    url = 'http://x/av.png'


class FakeRole:
    def __init__(self, rid, name='@everyone'):
        self.id = rid
        self.name = name
        self.mention = f'<@&{rid}>'


class FakeMessage:
    _next = 5000

    def __init__(self, mid=None, content='', author=None, channel=None, guild=None,
                 attachments=()):
        FakeMessage._next += 1
        self.id = mid or FakeMessage._next
        self.content = content
        self.author = author
        self.channel = channel
        self.guild = guild
        self.attachments = list(attachments)
        self.jump_url = f'http://jump/{self.id}'
        self.deleted = False

    async def delete(self):
        self.deleted = True


class FakeTextChannel:
    def __init__(self, cid, name, guild=None):
        self.id = cid
        self.name = name
        self.mention = f'<#{cid}>'
        self.guild = guild
        self.overwrites = {}          # role -> discord.PermissionOverwrite
        self.sent = []                # отправленные сообщения
        self.perm_calls = []          # вызовы set_permissions для проверок

    def overwrites_for(self, role):
        return self.overwrites.get(role, discord.PermissionOverwrite())

    async def set_permissions(self, target, reason=None, **perms):
        ow = self.overwrites.setdefault(target, discord.PermissionOverwrite())
        for k, v in perms.items():
            setattr(ow, k, v)
        self.perm_calls.append((target.id, dict(perms)))

    async def send(self, embed=None, content=None, **kw):
        m = FakeMessage(content=content or (embed.description if embed else ''),
                        channel=self, guild=self.guild)
        self.sent.append(m)
        return m

    async def fetch_message(self, mid):
        for m in self.sent:
            if m.id == mid:
                return m
        raise discord.NotFound(None, 'not found')


class FakeUser:
    def __init__(self, uid, name, bot=False):
        self.id = uid
        self.display_name = name
        self.name = name
        self.bot = bot
        self.mention = f'<@{uid}>'
        self.display_avatar = FakeAvatar()

    def __str__(self):
        return f'{self.name}#{self.id % 10000:04d}'


class FakeGuild:
    def __init__(self):
        self.id = 555
        self.name = 'TestGuild'
        self.default_role = FakeRole(1)
        self.text_channels = [FakeTextChannel(100, 'общий', self),
                              FakeTextChannel(101, 'правила', self),
                              FakeTextChannel(102, 'флуд', self)]
        self.verification_level = discord.VerificationLevel.none
        self.edit_calls = []

    def get_channel(self, cid):
        return next((c for c in self.text_channels if c.id == cid), None)

    async def edit(self, reason=None, **kw):
        if 'verification_level' in kw:
            self.verification_level = kw['verification_level']
        self.edit_calls.append(kw)


class FakeResp:
    def __init__(self):
        self.sent = None
        self.deferred = False

    async def send_message(self, content=None, embed=None, ephemeral=False, **kw):
        self.sent = (content, embed, ephemeral)

    async def defer(self, ephemeral=False):
        self.deferred = True


class FakeFollowup:
    def __init__(self):
        self.sent = None

    async def send(self, content=None, embed=None, ephemeral=False, **kw):
        self.sent = (content, embed, ephemeral)


class FakeInter:
    def __init__(self, guild, user, channel=None):
        self.guild = guild
        self.user = user
        self.channel = channel or guild.text_channels[0]
        self.response = FakeResp()
        self.followup = FakeFollowup()


cog = ModPlus(bot=None)
loop = asyncio.new_event_loop()
run = loop.run_until_complete
guild = FakeGuild()
mod = FakeUser(50, 'Mod')

# ═══ snipe ═════════════════════════════════════════════════════════════
print('== snipe: удалённые и правки ==')
ch = guild.text_channels[0]
u = FakeUser(77, 'Hooligan')
m1 = FakeMessage(content='токсичное сообщение', author=u, channel=ch, guild=guild)
cog._snipe_deleted.clear()
run(cog.on_message_delete(m1))
inter = FakeInter(guild, mod, ch)
run(ModPlus.snipe.callback(cog, inter))
e = inter.response.sent[1]
check(e and 'токсичное сообщение' in (e.description or ''), 'snipe показывает стёртый текст')
check('Последнее удалённое сообщение' in (e.author.name or ''), 'snipe: заголовок на месте')

m2 = FakeMessage(content='а', author=u, channel=ch, guild=guild)
run(cog.on_message_edit(m2, m2))  # содержимое не изменилось — правка мимо буфера
# настоящая правка
before = FakeMessage(content='было: всё ОК', author=u, channel=ch, guild=guild)
after = FakeMessage(content='стало: ничего не было', author=u, channel=ch, guild=guild)
check(len(cog._snipe_edited.get(ch.id, {}) or {}) == 0, 'правка без изменений игнорируется')
run(cog.on_message_edit(before, after))
inter2 = FakeInter(guild, mod, ch)
run(ModPlus.editsnipe.callback(cog, inter2))
e2 = inter2.response.sent[1]
check(e2 and any('было: всё ОК' in (f.value or '') for f in e2.fields), 'editsnipe: версия «было» видна')

# бот не засчитывается
bot_msg = FakeMessage(content='bot text', author=FakeUser(9, 'Botty', bot=True), channel=ch, guild=guild)
before_len = len(cog._snipe_deleted)
run(cog.on_message_delete(bot_msg))
check(len(cog._snipe_deleted) == before_len, 'удаление сообщения бота не пишется в буфер')

# пустой канал буфера → ответ «пусто»
inter3 = FakeInter(guild, mod, guild.text_channels[2])
run(ModPlus.snipe.callback(cog, inter3))
check(inter3.response.sent[0] and 'пуст' in inter3.response.sent[0].lower(), 'snipe по пустому каналу — вежливый отказ')

# ═══ sticky ═════════════════════════════════════════════════════════════
print('== sticky: закрепление, репост, анти-баунс ==')
run(ModPlus.stick.callback(cog, FakeInter(guild, mod, ch), text='Соблюдайте правила!', channel=ch))
data = json.load(open(_sticky_path(guild.id), encoding='utf-8'))
check(str(ch.id) in data and data[str(ch.id)]['text'] == 'Соблюдайте правила!',
      'stick: запись сохранена в json')
check(ch.sent and '📌' in (ch.sent[-1].content or ''), 'stick: липкое сразу отправлено в канал')
sticky_id = data[str(ch.id)]['msg_id']
check(sticky_id, 'stick: msg_id сохранён для будущей замены')

# человек написал → липкое перелетает вниз (старое удаляется)
run(cog.on_message(FakeMessage(content='привет', author=u, channel=ch, guild=guild)))
check(ch.sent[-1].id != sticky_id and ch.sent[-2].deleted is True,
      'репост: старое липкое удалено, новое — сверху')

# анти-баунс: мгновенное второе сообщение — НЕ репостится
n_sent = len(ch.sent)
run(cog.on_message(FakeMessage(content='и снова привет', author=u, channel=ch, guild=guild)))
check(len(ch.sent) == n_sent, 'анти-баунс: повторный репост не чаще cooldown')

# после истечения cooldown — репостится снова
cog._last_sticky_repost[ch.id] = time.monotonic() - STICKY_REPOST_COOLDOWN - 1
run(cog.on_message(FakeMessage(content='ещё сообщение', author=u, channel=ch, guild=guild)))
check(len(ch.sent) == n_sent + 1, 'после cooldown липкое снова пересылается')

# сообщение бота не триггерит
n_sent = len(ch.sent)
cog._last_sticky_repost[ch.id] = time.monotonic() - STICKY_REPOST_COOLDOWN - 1
run(cog.on_message(FakeMessage(content='бот', author=FakeUser(9, 'Botty', bot=True), channel=ch, guild=guild)))
check(len(ch.sent) == n_sent, 'сообщение бота липкое не двигает')

# unstick
run(ModPlus.unstick.callback(cog, FakeInter(guild, mod, ch), channel=ch))
data = json.load(open(_sticky_path(guild.id), encoding='utf-8'))
check(str(ch.id) not in data, 'unstick: запись удалена')
inter_l = FakeInter(guild, mod, ch)
run(ModPlus.sticklist.callback(cog, inter_l))
check(inter_l.response.sent[0] and 'нет' in inter_l.response.sent[0].lower(), 'sticklist: пустой список сообщается')

# ═══ panic ═══════════════════════════════════════════════════════════════
print('== panic: локдаун и точный откат ==')
# заранее смешанные права: в «правилах» @everyone и так запрещено писать
guild.text_channels[1].overwrites.setdefault(guild.default_role,
                                             discord.PermissionOverwrite()).send_messages = False

# без confirm — только предупреждение
inter_p = FakeInter(guild, mod, ch)
run(ModPlus.panic_on.callback(cog, inter_p, reason='рейдят', confirm=False, boost_verification=True))
check(inter_p.response.sent and not os.path.exists(_panic_path(guild.id)),
      'panic без confirm=True не запускается')

# заглушим запись в лог-канал (в тесте нет настоящих каналов логов)
async def _fake_notify(self, guild_, embed_):
    guild_.notified = embed_
ModPlus._notify_mod_log = _fake_notify

inter_p2 = FakeInter(guild, mod, ch)
run(ModPlus.panic_on.callback(cog, inter_p2, reason='рейдят', confirm=True, boost_verification=True))
check(os.path.exists(_panic_path(guild.id)), 'panic on: state-файл создан')
check(all(c.overwrites_for(guild.default_role).send_messages is False
          for c in guild.text_channels), 'panic on: все каналы закрыты для @everyone')
state = json.load(open(_panic_path(guild.id), encoding='utf-8'))
check(state['channels']['100']['send_messages'] is None, 'panic: прежнее «наследуется» (None) записано')
check(state['channels']['101']['send_messages'] is False, 'panic: прежнее «запрещено» записано')
check(guild.verification_level == discord.VerificationLevel.high, 'panic: проверка сервера поднята до High')
check(state.get('verification') == 0, 'panic: прежний уровень проверки сохранён')

# повторный запуск при активном локдауне
inter_p3 = FakeInter(guild, mod, ch)
run(ModPlus.panic_on.callback(cog, inter_p3, confirm=True))
check(inter_p3.response.sent and 'уже активен' in inter_p3.response.sent[0],
      'panic: повторный on отклонён вежливо')

# status
inter_s = FakeInter(guild, mod, ch)
run(ModPlus.panic_status.callback(cog, inter_s))
check(inter_s.response.sent and 'АКТИВЕН' in (inter_s.response.sent[1].title or ''),
      'panic status показывает активный локдаун')

# off — восстановление ТОЧНО прежних значений
inter_off = FakeInter(guild, mod, ch)
run(ModPlus.panic_off.callback(cog, inter_off))
check(not os.path.exists(_panic_path(guild.id)), 'panic off: state-файл удалён')
ovw = guild.text_channels[0].overwrites_for(guild.default_role).send_messages
check(ovw is None, 'panic off: канал с None вернулся к наследованию')
ovw2 = guild.text_channels[1].overwrites_for(guild.default_role).send_messages
check(ovw2 is False, 'panic off: канал с запретом остался запрещён')
check(guild.verification_level == discord.VerificationLevel.none, 'panic off: проверка сервера возвращена')

# off без активного — аккуратный отказ
inter_off2 = FakeInter(guild, mod, ch)
run(ModPlus.panic_off.callback(cog, inter_off2))
check(inter_off2.followup.sent and 'не активен' in inter_off2.followup.sent[0].lower(),
      'panic off без локдауна — вежливый отказ')

# ═══ веб-панель: API липких и паники ═════════════════════════════════════
print('== панель: /api/sticky и /api/panic ==')
import threading as _threading


class FakeBotPanel:
    """Бот для панели: живой loop в потоке + наш ког."""

    def __init__(self, g):
        self.guilds = [g]
        self.loop = asyncio.new_event_loop()
        _threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self._cog = ModPlus(bot=self)

    def get_cog(self, name):
        return self._cog if name == 'ModPlus' else None

    def get_guild(self, gid):
        return self.guilds[0] if gid == self.guilds[0].id else None


bot_panel = FakeBotPanel(guild)
from web.app import app as _flask_app, set_bot_instance  # noqa: E402
set_bot_instance(bot_panel)
client = _flask_app.test_client()

# без логина — редирект/отказ
r = client.get('/api/sticky')
check(r.status_code in (302, 401, 403), f'API без логина закрыто ({r.status_code})')


def login_as(role):
    # discord_id специально НЕ ставим: login_required раз в 5 минут перечитывает
    # роль из Discord по discord_id и понизил бы тестовую роль до 'uye'.
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'PanelMod'
        s['role'] = role


login_as('mod')
r = client.get('/api/sticky')
check(r.status_code == 200 and r.get_json().get('items') == [], 'sticky list: пусто')

r = client.post('/api/sticky', json={'channel_id': '100', 'text': 'Правила читать обязательно!'})
d = r.get_json()
check(d.get('success') is True and d.get('reposted') is True,
      'sticky POST: создано и СРАЗУ репостнуто через бота')
sdata = json.load(open(_sticky_path(guild.id), encoding='utf-8'))
check(sdata.get('100', {}).get('text', '').startswith('Правила'), 'sticky: запись в json от панели')
check(ch.sent and 'Правила' in (ch.sent[-1].content or ''), 'sticky: бот отправил её в канал')

r = client.post('/api/sticky', json={'channel_id': '100', 'text': ''})
check(r.status_code == 400, 'sticky POST: пустой текст отклонён (400)')
r = client.post('/api/sticky', json={'channel_id': '999999', 'text': 'тест'})
check(r.status_code == 404, 'sticky POST: несуществующий канал (404)')

r = client.delete('/api/sticky', json={'channel_id': '100'})
check(r.get_json().get('success') is True, 'sticky DELETE: отклеено')
check(json.load(open(_sticky_path(guild.id), encoding='utf-8')).get('100') is None,
      'sticky: запись удалена из json')

# panic: mod роли мало — нужна admin+
r = client.post('/api/panic', json={'action': 'on', 'reason': 'тест-рейд'})
check(r.status_code == 403, f'panic POST для mod запрещён ({r.status_code})')
login_as('admin')
r = client.post('/api/panic', json={'action': 'on', 'reason': 'тест-рейд', 'boost_verification': True})
d = r.get_json()
check(d.get('success') is True and d.get('done') == 3, 'panic из панели: включён, 3 канала')
check(all(c.overwrites_for(guild.default_role).send_messages is False
          for c in guild.text_channels), 'panic из панели: каналы реально закрыты')
r = client.get('/api/panic')
check(r.get_json().get('active') is True, 'panic status из панели: активен')
check(r.get_json()['state'].get('by') == 'панель:PanelMod', 'panic: виновник записан (панель:…)')

r = client.post('/api/panic', json={'action': 'on'})
check(r.status_code == 409, 'panic: повторный on → 409 уже активен')
r = client.post('/api/panic', json={'action': 'nope'})
check(r.status_code == 400, 'panic: неизвестный action → 400')

r = client.post('/api/panic', json={'action': 'off'})
d = r.get_json()
check(d.get('success') is True and d.get('done') == 3, 'panic из панели: снят, 3 канала')
check(not os.path.exists(_panic_path(guild.id)), 'panic из панели: state-файл подчищен')

# страница рендерится
r = client.get('/mod-tools')
check(r.status_code == 200 and 'sticky' in r.get_data(as_text=True).lower()
      and 'panic' in r.get_data(as_text=True).lower(), 'страница /mod-tools рендерится')

login_as('uye')
r = client.get('/mod-tools')
check(r.status_code in (302, 403), f'uye на /mod-tools не пускают ({r.status_code})')

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
loop.close()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
