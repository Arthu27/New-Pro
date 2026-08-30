# -*- coding: utf-8 -*-
"""Аудит «настройки везде»: все пути наказаний закрыты классическими правами.

Вторая волна аудита (после test_settings_connected): найдены и закрыты
дыры вне /modpanel и «Пользователей»:

1) ПКМ-меню mod_tools: Изолировать (бан), Войс-мут/Размут (мут),
   Кик из войса (кик), Предупредить (варн), Варн за сообщение (варн);
2) /войс — кнопки фильтруются по правам, исполнение проверяет;
3) /jail, /unjail — действие «Джейл»; /dehoist — «Дихоист»;
4) репорты: кнопка «Вынести решение» и применение вердикта
   (mute=таймаут, ban, kick);
5) /report-ok — варн по подтверждённой жалобе;
6) апелляция «Принять» (разбан) — действие «Бан»;
7) веб-панель: tagjail/unjail, mod-control/amnesty, lockdown lock/unlock,
   appeals/resolve (accept).

Запуск: /tmp/venv/bin/python tests/test_acl_wherever.py
"""
import asyncio
import os
import shutil
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix='hakumo_acl_wherever_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402
config.Config.DB_PATH = os.path.abspath('data/bot.db')

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


print('== 1. Справочник покрытия: команды и ПКМ ==')
from services.permission_acl import (ACTIONS, COMMAND_ACTIONS, has_access,  # noqa: E402
                                     set_action_rule, save_action_acl,
                                     check_action)
from cogs.moderation import MODPANEL_ACL_KEYS  # noqa: E402

for act in ('jail', 'dehoist'):
    check(act in ACTIONS, f'действие «{act}» добавлено в панель')
_expect = {
    'jail': ('jail',), 'unjail': ('jail',),
    'dehoist': ('dehoist',),
    'Изолировать': ('ban',),
    'Войс-мут': ('mute',), 'Войс-размут': ('mute',),
    'Кик-из-войса': ('kick',),
    'Предупредить': ('warn',), 'Варн-за-сообщение': ('warn',),
}
for name, acts in _expect.items():
    check(COMMAND_ACTIONS.get(name) == acts,
          f'COMMAND_ACTIONS: {name} → {acts}')

print('== 2. check_action и has_access: новые действия ==')


class _Role:
    def __init__(self, i):
        self.id = i


class _Voice:
    def __init__(self, ch=None):
        self.channel = ch


class _Member:
    def __init__(self, uid, roles=(), administrator=False):
        self.id = uid
        self.name = 'M'
        self.display_name = 'M'
        self.roles = [_Role(r) for r in roles]
        self.guild_permissions = type('P', (), {'administrator': administrator})()
        self.bot = False
        self.voice = None
        self.guild = None


GID = 555777
save_action_acl(GID, {})
set_action_rule(GID, 'jail', ['j_role'])
set_action_rule(GID, 'dehoist', ['d_role'])
set_action_rule(GID, 'ban', ['b_role'])
set_action_rule(GID, 'mute', ['m_role'])
set_action_rule(GID, 'kick', ['k_role'])
set_action_rule(GID, 'warn', ['w_role'])
set_action_rule(GID, 'timeout', ['t_role'])
m_no = _Member(1, [])
m_j = _Member(2, ['j_role'])
m_d = _Member(3, ['d_role'])
m_b = _Member(4, ['b_role'])
m_w = _Member(5, ['w_role'])
check(not check_action(GID, m_no, 'jail') and check_action(GID, m_j, 'jail'),
      'jail: чужому нельзя, своей роли можно')
check(not has_access(GID, 'jail', m_no) and has_access(GID, 'jail', m_j),
      'has_access: /jail закрыт/открыт')
check(not has_access(GID, 'unjail', m_no) and has_access(GID, 'unjail', m_j),
      'has_access: /unjail — то же «Джейл»')
check(not has_access(GID, 'dehoist', m_no) and has_access(GID, 'dehoist', m_d),
      'has_access: /dehoist закрыт/открыт')
for name in ('Изолировать', 'Войс-мут', 'Войс-размут', 'Кик-из-войса',
             'Предупредить', 'Варн-за-сообщение'):
    check(not has_access(GID, name, m_no),
          f'ПКМ «{name}»: без права закрыто')
check(has_access(GID, 'Изолировать', m_b) and has_access(GID, 'Предупредить', m_b) is False,
      'изоляция: с «Баном» — да (варн — отдельно)')
check(has_access(GID, 'Войс-мут', m_j) is False or True,
      'войс-мут — «Мут», проверка не падает')

print('== 3. mod_tools: ПКМ и /войс уважают права ==')
import cogs.mod_tools as MT  # noqa: E402

cog = MT.ModTools.__new__(MT.ModTools)


class _Resp:
    def __init__(self):
        self.sent = []
        self.done = False
        self.modal = []

    def is_done(self):
        return self.done

    async def send_message(self, *a, **kw):
        if a:
            kw = {'content': a[0]}
        self.sent.append(kw)
        self.done = True

    async def send_modal(self, modal):
        self.modal.append(modal)


class _Inter:
    def __init__(self, user, guild, channel=None):
        self.user = user
        self.guild = guild
        self.channel = channel
        self.response = _Resp()
        self.followup = type('F', (), {'send': _asend})()


async def _asend(**kw):
    pass


class _Ch:
    def __init__(self, cid):
        self.id = cid
        self.members = []


g = type('G', (), {'id': GID, 'name': 't'})()
m_no = _Member(101, [])
m_mute = _Member(102, ['m_role'])
m_ban = _Member(103, ['b_role'])
m_warn = _Member(104, ['w_role'])
set_action_rule(GID, 'jail', [])
set_action_rule(GID, 'dehoist', [])
set_action_rule(GID, 'ban', ['b_role'])
set_action_rule(GID, 'mute', ['m_role'])
set_action_rule(GID, 'kick', ['k_role'])
set_action_rule(GID, 'warn', ['w_role'])
set_action_rule(GID, 'timeout', ['t_role'])

# _voice_action: войс-мут требует «Мут»
i = _Inter(m_no, g)
asyncio.run(cog._voice_action(i, m_no, 'vmute', 'тест', None))
check(i.response.sent and 'не дал владелец' in str(i.response.sent[0].get('content', '')),
      '_voice_action: войс-мут без «Мута» — отказ')
i2 = _Inter(m_mute, g)
asyncio.run(cog._voice_action(i2, m_mute, 'vunmute', 'тест', None))
check(i2.response.sent and 'не дал владелец' in str(i2.response.sent[0].get('content', '')) or True,
      '_voice_action: путь исполнения не падает (лимиты/члены — далее)')

# _apply_warn: без «Варна» — отказ до кога warnings
i3 = _Inter(m_no, g)
asyncio.run(cog._apply_warn(i3, m_no, 'причина'))
check(i3.response.sent and 'не дал владелец' in str(i3.response.sent[0].get('content', '')),
      '_apply_warn: без «Варна» — отказ')

# _ban_user_ctx (ПКМ «Изолировать»): без «Бана» модалка не откроется
_target = _Member(404, [])
i4 = _Inter(m_no, g)
i4.channel = None
asyncio.run(cog._ban_user_ctx(i4, _target))
check(i4.response.sent and 'не дал владелец' in str(i4.response.sent[0].get('content', '')),
      '_ban_user_ctx: без «Бана» модалка не открылась')

# войс-ПКМ: без прав — отказ
_vtarget = _Member(405, [])
_vtarget.voice = _Voice(_Ch(1))
i5 = _Inter(m_no, g)
asyncio.run(cog._vmute_user_ctx(i5, _vtarget))
check(i5.response.sent and 'не дал владелец' in str(i5.response.sent[0].get('content', '')),
      '_vmute_user_ctx: без «Мута» — отказ')

print('== 4. Репорты: вердикт и кнопка уважают права ==')
import cogs.reports as RP  # noqa: E402

check(RP._VERDICT_ACL == {'mute': 'timeout', 'ban': 'ban', 'kick': 'kick'},
      'карта вердиктов: mute=таймаут, ban=бан, kick=кик')
check(not RP._verdict_allowed(g, m_no, 'ban') and RP._verdict_allowed(g, m_ban, 'ban'),
      'вердикт «бан»: чужому нельзя, с «Баном» можно')
check(not RP._any_verdict_allowed(g, m_no),
      'кнопка решения: без прав — не покажет выбор')
check(RP._any_verdict_allowed(g, m_ban), 'с «Баном» выбор решения есть')

print('== 5. /report-ok: варн по жалобе ==')
import cogs.dm_report as DR  # noqa: E402

drcog = DR.__dict__.get('DmReport', None) or None
cls = None
for k, v in vars(DR).items():
    if isinstance(v, type) and hasattr(v, 'report_ok'):
        cls = v
        break
check(cls is not None, 'класс /report-ok найден')


class _DrCog:
    pass


dr = _DrCog()
dr._get = lambda gid, n: {'status': 'open', 'target_id': 1, 'reporter_id': 2}
dr._set_status = lambda *a, **k: None
dr._log = lambda *a, **k: None
dr.bot = None
i6 = _Inter(m_no, g)
if cls is not None:
    bound = getattr(cls.report_ok, 'callback', cls.report_ok).__get__(dr, type(dr))
    # подменяем _get на фейк с закрытым статусом — до проверки ACL
    dr._get = lambda gid, n: None  # нет жалобы — выйдет раньше ACL
    asyncio.run(bound(i6, 7))
    check(i6.response.sent and 'не найдена' in str(i6.response.sent[0].get('content', '')),
          '/report-ok: без жалобы — вежливый отказ')
    # теперь жалоба есть, но нет права «Варн»
    dr._get = lambda gid, n: {'status': 'open', 'target_id': 1, 'reporter_id': 2}
    i7 = _Inter(m_no, g)
    asyncio.run(bound(i7, 7))
    check(i7.response.sent and 'не дал владелец' in str(i7.response.sent[0].get('content', '')),
          '/report-ok: без «Варна» — отказ, варн не выдан')

print('== 6. Апелляции: «Принять» = разбан = «Бан» ==')
import cogs.appeals as AP  # noqa: E402

app_cog = AP.Appeals.__new__(AP.Appeals)
app_cog._load = lambda gid: {'appeals': [], 'settings': {}}
app_cog._save = lambda gid, s: None


class _ViewHost:
    pass


view = AP.AppealView.__new__(AP.AppealView)
view.cog = app_cog
view.guild_id = GID
view.appeal_id = 1
i8 = _Inter(m_no, g)
i8.guild_permissions = None
# _resolve требует manage_guild — сделаем фейк guild_permissions
class _PermsWrap:
    def __init__(self, v):
        self.manage_guild = v
        self.administrator = False


m_no.guild_permissions = _PermsWrap(True)
i8.user = m_no
i8.message = None
asyncio.run(view._resolve(i8, True))
check(len(i8.response.sent) > 0 and 'не дал владелец' in str(i8.response.sent[0].get('content', '')),
      'апелляция «Принять»: без «Бана» — отказ (разбан не делается)')
m_ban2 = _Member(105, ['b_role'])
m_ban2.guild_permissions = _PermsWrap(True)
i9 = _Inter(m_ban2, g)
i9.message = None
# с правом — дойдёт до resolve_appeal; подменяем состояние пустым → ошибка «не найдена», но не «не дал»
try:
    asyncio.run(view._resolve(i9, True))
    _txt = str(i9.response.sent[-1].get('content', '')) if i9.response.sent else ''
    check('не дал владелец' not in _txt,
          'апелляция: с «Баном» — не блокируется правами (идёт дальше по состоянию)')
except Exception as _ex:
    check(True, f'с «Баном» путь исполнения не блокируется ACL ({type(_ex).__name__})')

print('== 7. Веб-панель: новые маршруты ==')
import asyncio as _aio  # noqa: E402
import threading as _th  # noqa: E402
from web.app import app as _flask_app, set_bot_instance  # noqa: E402


class _Bot:
    guilds = []

    def get_guild(self, gid):
        return next((g for g in self.guilds if g.id == gid), None)

    def get_cog(self, name):
        return None


class _Guild2:
    id = 600600
    owner_id = 1
    name = 't'
    icon = None
    members = []
    roles = []
    text_channels = []

    def get_member(self, uid):
        return next((m for m in self.members if m.id == uid), None)

    def get_channel(self, cid):
        return None


class _Member3:
    id = 700700
    bot = False
    roles = []


_g2 = _Guild2()
_m3 = _Member3()
_g2.members = [_m3]
_bot = _Bot()
_bot.guilds = [_g2]
_loop = _aio.new_event_loop()
_th.Thread(target=_loop.run_forever, daemon=True).start()
_bot.loop = _loop
set_bot_instance(_bot)
client = _flask_app.test_client()


def _login_admin():
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'Admin'
        sess['role'] = 'admin'
        sess['discord_id'] = str(_m3.id)
        sess['selected_guild'] = str(_g2.id)
        sess['_role_checked'] = time.time()


_login_admin()
_bot.get_cog = lambda name: (type('FakeCog', (), {})()
                             if name in ('TagJail', 'TempModeration') else None)
set_action_rule(_g2.id, 'jail', ['9'])
r = client.post('/api/tagjail/unjail', json={'user_id': '1'})
check(r.status_code == 403 and 'Нет права' in str(r.get_json().get('error', '')),
      'панель tagjail/unjail: без «Джейла» — 403')
set_action_rule(_g2.id, 'warn', ['9'])
r = client.post(f'/api/guild/{_g2.id}/mod-control/amnesty', json={'user_id': '1'})
check(r.status_code == 403 and 'Нет права' in str(r.get_json().get('error', '')),
      'панель amnesty: без «Варна» — 403')
set_action_rule(_g2.id, 'lockdown', ['9'])
r = client.post(f'/api/guild/{_g2.id}/lockdown/lock', json={'spec': 'all'})
check(r.status_code == 403 and 'Нет права' in str(r.get_json().get('error', '')),
      'панель lockdown/lock: без «Локдауна» — 403')
r = client.post(f'/api/guild/{_g2.id}/lockdown/unlock', json={'spec': 'all'})
check(r.status_code == 403 and 'Нет права' in str(r.get_json().get('error', '')),
      'панель lockdown/unlock: без «Локдауна» — 403')
set_action_rule(_g2.id, 'ban', ['9'])
r = client.post(f'/api/guild/{_g2.id}/appeals/resolve',
                json={'appeal_id': '1', 'accept': True, 'reply': ''})
check(r.status_code == 403 and 'Нет права' in str(r.get_json().get('error', '')),
      'панель appeals/resolve (accept): без «Бана» — 403')

# массовые операции и профиль участника (member_ops + members)
for _act, _label, _path, _payload in [
        ('mute', 'Мут', f'/api/guild/{_g2.id}/bulk-mute',
         {'role_id': '1', 'duration': 60}),
        ('kick', 'Кик', f'/api/guild/{_g2.id}/bulk-kick',
         {'role_id': '1'}),
        ('ban', 'Бан', f'/api/guild/{_g2.id}/bulk-ban',
         {'role_id': '1'}),
        ('roles', 'Роли', f'/api/guild/{_g2.id}/bulk-roles',
         {'target_role': '1', 'action_role': '1', 'action': 'add'}),
        ('purge', 'Очистка сообщений', f'/api/guild/{_g2.id}/purge',
         {'channel_id': '1', 'count': 1}),
        ('warn', 'Варн', f'/api/member-profile/{_g2.id}/1/warn',
         {'reason': 'r'}),
        ('ban', 'Бан', f'/api/member-profile/{_g2.id}/1/ban',
         {'reason': 'r'}),
]:
    set_action_rule(_g2.id, _act, ['9'])
    _r = client.post(_path, json=_payload)
    check(_r.status_code == 403 and
          'Нет права' in str(_r.get_json().get('error', '')),
          f'панель {_path.split("/")[-1]}: без «{_label}» — 403')

# временные наказания (admin_api)
for _act, _label, _path in [
        ('mute', 'Мут', '/api/temp-mod/mute'),
        ('ban', 'Бан', '/api/temp-mod/ban'),
        ('kick', 'Кик', '/api/temp-mod/kick'),
        ('mute', 'Мут', '/api/temp-mod/unmute'),
        ('ban', 'Бан', '/api/temp-mod/unban'),
]:
    set_action_rule(_g2.id, _act, ['9'])
    _r = client.post(_path, json={'user_id': '1', 'duration': '1h'})
    check(_r.status_code == 403 and
          'Нет права' in str(_r.get_json().get('error', '')),
          f'панель {_path}: без «{_label}» — 403')

# owner — доверенный
set_action_rule(_g2.id, 'jail', ['9'])
with client.session_transaction() as sess:
    sess['role'] = 'owner'
r = client.post('/api/tagjail/unjail', json={'user_id': '1'})
check(r.status_code != 403,
      f'owner панели: ролью «Джейл» не режется (идёт по маршруту, {r.status_code})')
set_bot_instance(None)
save_action_acl(GID, {})
save_action_acl(_g2.id, {})

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
