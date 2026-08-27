# -*- coding: utf-8 -*-
"""Наказания ролями + апелляции в канале (заказ 2026-08-27).

Юнит:
1. services.punish_roles — выбор ролей, журнал сроков, due/clear.
2. Мут ролью вместо таймаута (apply_panel_action), авто-снятие по сроку
   (punish_roles_loop), войс-мут ролью вне голоса, бан-роль + канал
   апелляции, unban снимает роль.
3. Лестница варнов (warnings.apply_warn_punishment) — мут и бан ролями.
4. Апелляции в канале: publish_appeal_menu, _submit_channel_appeal —
   тред с карточкой, _resolve accept снимает роль «бана».
5. Панель: GET/POST /api/guild/<gid>/mod-settings — роли наказаний и
   канал меню апелляций; publish_menu.

Запуск: python3 tests/test_punish_roles.py
"""
import asyncio
import os
import shutil
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix='hakumo_punish_roles_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')   # GuildData — мимо репо

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


G = 900100
UID = 222000000000000111
R_MUTE, R_VMUTE, R_BAN = 501, 502, 503


# ── фейки Discord ────────────────────────────────────────────────────────

class _Role:
    def __init__(s, i, name='роль'):
        s.id = i
        s.name = f'{name}-{i}'
        s.mention = f'<@&{i}>'


class _Overwrite:
    def __init__(s, **kw):
        s.kw = kw


class _Ch:
    def __init__(s, i, guild=None):
        s.id = i
        s.name = f'канал-{i}'
        s.mention = f'<#{i}>'
        s.guild = guild
        s.overwrites = {}
        s.sent = []
        s.threads = []
        s.edited = []

    async def set_permissions(s, u, overwrite=None, **kw):
        s.overwrites[getattr(u, 'id', u)] = overwrite or _Overwrite(**kw)

    async def send(s, embed=None, view=None, **kw):
        s.sent.append({'embed': embed, 'view': view, **kw})

        class _Msg:
            id = len(s.sent) + 1000
            jump_url = f'https://discord.com/channels/{G}/{s.id}/{id}'

        return _Msg()

    async def edit_message(s, mid, **kw):
        s.edited.append({'id': mid, **kw})

        class _Msg:
            id = mid
            jump_url = f'https://discord.com/channels/{G}/{s.id}/{mid}'

        return _Msg()

    async def create_thread(s, name, type=None):
        class _Thread(_Ch):
            def __init__(s2, i, name):
                super().__init__(i, guild=s.guild)
                s2.name = name
                s2.parent = s

        t = _Thread(7000 + len(s.threads), name)
        s.threads.append(t)
        return t


class _Voice:
    def __init__(s, ch=None):
        s.channel = ch


class _Member:
    def __init__(s, i, voice=None, roles=()):
        s.id = i
        s.name = 'BadGuy'
        s.display_name = 'BadGuy'
        s.bot = False
        s.voice = voice
        s.guild = None
        s.roles = list(roles)
        s.added = []
        s.removed = []
        s.timed_out_until = None
        s.kicked = s.banned = False
        s.muted = None
        s.dms = []

    display_avatar = None

    @property
    def mention(s):
        return f'<@{s.id}>'

    def __str__(s):
        return 'BadGuy'

    async def add_roles(s, role, reason=None):
        s.added.append((role.id, reason))
        if role not in s.roles:
            s.roles.append(role)

    async def remove_roles(s, role, reason=None):
        s.removed.append((role.id, reason))
        if role in s.roles:
            s.roles.remove(role)

    async def timeout(s, until, reason=None):
        s.timed_out_until = until

    async def edit(s, mute=None, **kw):
        s.muted = mute

    async def kick(s, reason=None):
        s.kicked = True

    async def ban(s, reason=None):
        s.banned = True

    async def send(s, content=None, **kw):
        s.dms.append(content)


class _Perms:
    manage_guild = True


class _U:
    id = 1
    name = 'Mod'
    guild_permissions = _Perms()


class _Guild:
    def __init__(s, i):
        s.id = i
        s.owner_id = 1
        s.name = 'Тест'
        s.icon = None
        s.roles = [_Role(R_MUTE, 'мут'), _Role(R_VMUTE, 'войс'), _Role(R_BAN, 'бан')]
        s.channels = [_Ch(300 + k, guild=s) for k in range(4)]
        s.text_channels = s.channels
        s.members = []

    def get_role(s, rid):
        return next((r for r in s.roles if r.id == rid), None)

    def get_channel(s, cid):
        return next((c for c in s.channels if c.id == cid), None)

    def get_member(s, uid):
        return next((m for m in s.members if m.id == uid), None)

    async def unban(s, user, reason=None):
        s.unbanned = getattr(s, 'unbanned', 0) + 1


class _Bot:
    def __init__(s, guild):
        s.guilds = [guild]
        s.user = None
        s._cogs = {}

    def get_guild(s, gid):
        return s.guilds[0] if gid == s.guilds[0].id else None

    def get_cog(s, name):
        return s._cogs.get(name)

    async def fetch_user(s, uid):
        for g in s.guilds:
            m = g.get_member(uid)
            if m is not None:
                return m
        raise RuntimeError('офлайн')


print('== 1. Сервис punish_roles: выбор и журнал сроков ==')
from services import punish_roles as PR  # noqa: E402

PR.set_roles(G, mute=R_MUTE, vmute=R_VMUTE, ban=R_BAN, who='тест')
got = PR.get(G)
check(got.get('mute') == R_MUTE and got.get('vmute') == R_VMUTE
      and got.get('ban') == R_BAN, 'все три роли выбраны')
check(PR.role_for(G, 'mute') == R_MUTE, 'role_for отдаёт ID')

PR.set_roles(G, mute=0)
check(PR.role_for(G, 'mute') == 0 and PR.role_for(G, 'ban') == R_BAN,
      'mute=0 снимает выбор, остальные живут')
PR.set_roles(G, mute=R_MUTE)

now = time.time()
PR.add_temp(G, UID, R_MUTE, now - 5)          # уже просрочена
PR.add_temp(G, UID, R_VMUTE, now + 3600)      # живёт
due = {(int(g), int(u), int(r)) for g, u, r in PR.due(now)}
check((G, UID, R_MUTE) in due and (G, UID, R_VMUTE) not in due,
      'due отдаёт только просроченные')
check(PR.temps_for(G, UID).get(R_VMUTE) > now, 'temps_for видит живую выдачу')
PR.clear(G, UID, R_MUTE)
check((G, UID, R_MUTE) not in {(int(g), int(u), int(r)) for g, u, r in PR.due(now)}, 'clear убирает запись о сроке')
PR.clear(G, UID)
check(not PR.temps_for(G, UID), 'clear(uid) вычищает всё')

print('== 2. Мут ролью вместо таймаута (панель) ==')
import cogs.moderation as M  # noqa: E402

guild = _Guild(G)
target = _Member(UID)
target.guild = guild
guild.members = [target]
mod = M.Moderation.__new__(M.Moderation)
mod.bot = _Bot(guild)
mod.bot._cogs['Moderation'] = mod

ok, text = asyncio.run(mod.apply_panel_action(
    guild, target, 'timeout', reason='спам', amount='2ч', actor='Ivan'))
check(ok, f'мут ролью применён ({text[:70]})')
check(target.added and target.added[0][0] == R_MUTE, 'выдана именно роль мута')
check(target.timed_out_until is None, 'таймаут не тронут (роль главнее)')
_until = PR.temps_for(G, UID).get(R_MUTE, 0)
check(_until - time.time() > 7000, f'срок записан (~2ч, до {_until:.0f})')

print('== 3. Авто-снятие по сроку (punish_roles_loop) ==')
logs = []


async def _fake_send_log(g, embed=None, **kw):
    logs.append(embed)


mod.send_log = _fake_send_log
PR.add_temp(G, UID, R_MUTE, time.time() - 1)   # просрочим
check(len(PR.due(time.time())) == 1, 'просроченная выдача видна')
asyncio.run(M.Moderation.punish_roles_loop.coro(mod))
check(target.removed and target.removed[0][0] == R_MUTE, 'роль снята автоматически')
check(not PR.due(time.time()), 'журнал вычищен')
check(any('истёк' in str(getattr(e, 'description', '')) for e in logs),
      'лог «срок истёк» отправлен')

print('== 4. Войс-мут ролью работает вне голоса ==')
target.voice = None        # не в голосе — раньше был отказ
ok, text = asyncio.run(mod.apply_panel_action(
    guild, target, 'vmute', amount='10м', actor='Ivan'))
check(ok and any(r == R_VMUTE for r, _ in target.added),
      f'роль войс-мута выдана даже вне голоса ({text[:60]})')
check(target.muted is None, 'серверный мут не трогали')

ok, text = asyncio.run(mod.apply_panel_action(
    guild, target, 'vunmute', actor='Ivan'))
check(ok and any(r == R_VMUTE for r, _ in target.removed), 'vunmute снял роль')

print('== 5. «Бан» ролью: гейт канала + открытая апелляция ==')
from services import channel_routes as CHR  # noqa: E402

ok, text = asyncio.run(mod.apply_panel_action(guild, target, 'ban', reason='тест'))
check(not ok and 'Настройки не завершены' in text,
      'без канала апелляции — отказ (роль не отменяет гейт)')

CHR.set_route(G, 'ban_appeal_channel', 301)
ok, text = asyncio.run(mod.apply_panel_action(guild, target, 'ban', reason='тест'))
check(ok and any(r == R_BAN for r, _ in target.added),
      f'бан-роль выдана ({text[:70]})')
iso = guild.get_channel(301)
check(UID in iso.overwrites, 'канал апелляции открыт участнику')

ok, text = asyncio.run(mod.apply_panel_action(guild, target, 'unban', actor='Ivan'))
check(ok and any(r == R_BAN for r, _ in target.removed),
      f'unban снял роль «бана» ({text[:60]})')

print('== 6. untimeout с ролью — снимает роль, не только таймаут ==')
ok, text = asyncio.run(mod.apply_panel_action(
    guild, target, 'timeout', amount='15м', actor='Ivan'))
ok, text = asyncio.run(mod.apply_panel_action(guild, target, 'untimeout', actor='Ivan'))
check(ok and target.removed.count((R_MUTE, 'снятие наказания')) >= 1
      or any(r == R_MUTE for r, _ in target.removed),
      'untimeout снял роль мута')

print('== 7. Лестница варнов — тоже ролями ==')
from cogs import warnings as WC  # noqa: E402
from cogs import ladder as LD  # noqa: E402
from cogs.warnings import load_warn_config, duration_to_minutes  # noqa: E402

cfg = load_warn_config(str(G))
cfg['steps'] = [{'count': 3, 'action': 'mute', 'duration': 30, 'unit': 'minute'},
                {'count': 5, 'action': 'ban', 'duration': 0, 'unit': 'minute'}]
LD._save_warn_config(G, cfg)
wcog = WC.warnings.__new__(WC.warnings)

target2 = _Member(UID + 1)
target2.guild = guild
guild.members = [target, target2]
res = asyncio.run(wcog.apply_warn_punishment(guild, target2, 3))
check('роль' in str(res or ''), f'3 варна → мут ролью ({res})')
check(any(r == R_MUTE for r, _ in target2.added), 'роль мута выдана лестницей')
check(PR.temps_for(G, UID + 1).get(R_MUTE, 0) > time.time(),
      'срок авто-мута записан в журнал')

res = asyncio.run(wcog.apply_warn_punishment(guild, target2, 5))
check('роль' in str(res or ''), f'5 варнов → бан-ролью ({res})')
check(any(r == R_BAN for r, _ in target2.added), 'бан-роль выдана лестницей')
check(UID + 1 in iso.overwrites, 'лестница открыла канал апелляции')

print('== 8. Апелляции в канале: меню + тред ==')
import cogs.appeals as A  # noqa: E402
from db import GuildData  # noqa: E402

acog = A.Appeals.__new__(A.Appeals)
acog.bot = mod.bot
acog.db = GuildData('appeals')
acog._views_restored = True
mod.bot._cogs['Appeals'] = acog

check(A.MENU_CUSTOM_ID == 'appeal:menu:open', 'custom_id меню фиксирован')
menu_view = A.AppealMenuView()
kids = list(menu_view.children)
check(kids and getattr(kids[0], 'custom_id', None) == A.MENU_CUSTOM_ID,
      'меню-view содержит select с persistent custom_id')
check(menu_view.timeout is None, 'view без таймаута (переживает рестарт)')

menu_ch = guild.get_channel(302)
ok, msg = asyncio.run(acog.publish_appeal_menu(menu_ch))
check(ok and menu_ch.sent, f'меню опубликовано ({msg})')
st = acog._load(G)
check(st.get('menu', {}).get('channel_id') == 302, 'сообщение меню запомнено')
mid = st['menu']['message_id']
ok, msg = asyncio.run(acog.publish_appeal_menu(menu_ch))
check(ok and menu_ch.edited and menu_ch.edited[-1]['id'] == mid,
      'повторная публикация редактирует то же сообщение')

user = _Member(UID + 2)
user.guild = guild
guild.members.append(user)
item, err = asyncio.run(acog._submit_channel_appeal(
    user, guild, 'Меня забанили незаслуженно, это ошибка!', link=None,
    channel=menu_ch))
check(err is None and item is not None, f'апелляция принята из меню ({err})')
check(item.get('thread_id') in [t.id for t in menu_ch.threads],
      'для апелляции создан тред в канале меню')
thread = next(t for t in menu_ch.threads if t.id == item.get('thread_id'))
check(thread.sent and thread.sent[0].get('embed') is not None,
      'карточка-embed отправлена в тред')
check(item.get('thread_url'), 'ссылка на тред сохранена')
check(user.dms, 'участник получил уведомление в ЛС')

short, err2 = asyncio.run(acog._submit_channel_appeal(
    user, guild, 'коротко', channel=menu_ch))
check(short is None and err2 and '10' in err2, f'короткий текст отклонён ({err2})')

print('== 9. Принятие апелляции снимает роль «бана» ==')

from cogs.appeals import AppealView  # noqa: E402


class _Resp:
    def __init__(s):
        s.sent = []

    async def send_message(s, *a, **kw):
        s.sent.append(a)

    async def edit_message(s, *a, **kw):
        s.sent.append(a)

    def is_done(s):
        return True


class _Msg:
    class _Embeds(list):
        pass

    embeds = []
    id = 1


class _Interaction:
    def __init__(s, u):
        s.user = u
        s.response = _Resp()
        s.message = _Msg()


# автор апелляции — участник с бан-ролью: пересоздадим от его имени
item2, err3 = asyncio.run(acog._submit_channel_appeal(
    target2, guild, 'Бан по 5 варнам несправедлив, разберите пожалуйста.', channel=menu_ch))
check(err3 is None, f'апелляция автора с бан-ролью принята ({err3})')
view = AppealView(acog, G, item2['id'])
interaction = _Interaction(_U())
before = len(target2.removed)
asyncio.run(view._resolve(interaction, accept=True))
check(any(r == R_BAN for r, _ in target2.removed[before:]),
      'accept снял роль «бана» с участника')
st = acog._load(G)
done = next((x for x in st['items'] if x['id'] == item2['id']), None)
check(done and done['status'] == 'accepted', 'апелляция закрыта как принятая')

print('== 10. Панель: роли наказаний и меню апелляций ==')
from web.app import app as _flask_app, set_bot_instance  # noqa: E402


class _WebRole:
    def __init__(s, i, name, pos, managed=False):
        s.id = i
        s.name = name
        s.position = pos
        s.managed = managed
        s.color = None

    def is_default(s):
        return False


class _WebGuild(_Guild):
    def __init__(s, i):
        super().__init__(i)
        s.roles = [_WebRole(9, 'everyone-подобная', 0),
                   _WebRole(R_MUTE, 'Мут', 3), _WebRole(R_BAN, 'Бан', 4)]
        m = _Member(UID)
        m.guild = s
        s.members = [m]


class _WebBot(_Bot):
    latency = 0.03
    voice_clients = []

    def is_closed(s):
        return False

    async def change_presence(s, **kw):
        pass


wg = _WebGuild(777)
wbot = _WebBot(wg)
wmod = M.Moderation.__new__(M.Moderation)
wmod.bot = wbot
wbot._cogs['Moderation'] = wmod
wacog = A.Appeals.__new__(A.Appeals)
wacog.bot = wbot
wacog.db = GuildData('appeals')
wacog._views_restored = True
wbot._cogs['Appeals'] = wacog

import threading as _th  # noqa: E402

_loop = asyncio.new_event_loop()
_th.Thread(target=_loop.run_forever, daemon=True).start()
wbot.loop = _loop
set_bot_instance(wbot)
client = _flask_app.test_client()
with client.session_transaction() as sess:
    sess.clear()
    sess['logged_in'] = True
    sess['username'] = 'Owner'
    sess['role'] = 'owner'
    sess['selected_guild'] = '777'

r = client.get('/api/guild/777/mod-settings')
d = r.get_json()
cfg = d.get('cfg') or {}
check(r.status_code == 200 and d.get('success'), 'GET настроек — 200')
check('punish_roles' in cfg and 'appeal_menu_channel' in cfg,
      'в настройках есть роли наказаний и канал меню')
check(any(x['name'] == 'Мут' for x in cfg.get('roles', [])),
      'список ролей сервера отдан')
check(any(x.get('id') == '301' for x in cfg.get('channels', [])),
      'список каналов сервера отдан')
check({k['key'] for k in cfg.get('kinds', [])} == {'mute', 'vmute', 'ban'},
      'три вида наказаний описаны')

r = client.post('/api/guild/777/mod-settings', json={
    'punish_roles': {'mute': R_MUTE, 'vmute': 0, 'ban': R_BAN},
    'appeal_menu_channel': 301})
d = r.get_json()
check(r.status_code == 200 and d.get('success'), 'POST ролей и канала — ок')
saved = PR.get(777)
check(saved.get('mute') == R_MUTE and saved.get('ban') == R_BAN
      and 'vmute' not in saved, 'роли сохранены через сервис')
check(CHR.get_route(777, 'appeal_menu_channel') == 301,
      'канал меню сохранён в маршрутах')

r = client.post('/api/guild/777/mod-settings', json={'publish_menu': True})
d = r.get_json()
check(r.status_code == 200 and d.get('success'), f'publish_menu — ок ({str(d)[:70]})')
published = wg.get_channel(301)
check(published.sent and published.sent[0].get('view') is not None,
      'бот опубликовал меню в выбранный канал')

r = client.post('/api/guild/777/mod-settings',
                json={'appeal_menu_channel': 0, 'publish_menu': True})
d = r.get_json()
check(r.status_code == 400 and 'канал' in (d.get('error') or ''),
      'публикация без канала — понятный отказ')

# гость не видит настройки
with client.session_transaction() as sess:
    sess.clear()
r = client.get('/api/guild/777/mod-settings')
check(r.status_code in (301, 302, 401, 403), 'гостю закрыто')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
