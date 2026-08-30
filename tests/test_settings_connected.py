# -*- coding: utf-8 -*-
"""Настройки доступа связаны везде: /modpanel, команды, веб-панель.

Заказ владельца: «такие настройки должны быть везде и в панеле тоже —
проверь соединение настроек между друг с другом».

Классические разрешения (панель → Доступ → Права команд: Бан/Мут/Таймаут/
Варн/Очистка/…) должны закрывать КАЖДЫЙ путь наказания:
1) /modpanel — пункты и исполнение (cogs/moderation.MODPANEL_ACL_KEYS);
2) команды бота — COMMAND_ACTIONS/ACTION_VALUES (main.py tree.check);
3) веб-панель «Пользователи» — punish/options + punish POST;
4) веб-панель «Расписание» — mod-schedule/create;
5) веб-панель «Лестница» — ladder/add и mod-settings POST (ступени);
и все карты действия согласованы между собой (одни и те же ключи ACTIONS).

Запуск: /tmp/venv/bin/python tests/test_settings_connected.py
"""
import os
import shutil
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix='hakumo_settings_connected_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402
config.Config.DB_PATH = os.path.abspath('data/bot.db')  # изолированный sqlite

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


print('== 1. Карты действий согласованы между модулями ==')
from services import permission_acl as PACL  # noqa: E402
from cogs.moderation import MODPANEL_ACL_KEYS, MODPANEL_ACTIONS  # noqa: E402

for act in MODPANEL_ACTIONS:
    key = MODPANEL_ACL_KEYS.get(act[0])
    check(key in PACL.ACTIONS, f'{act[0]} → ключ «{key}» есть в ACTIONS панели')

import web.routes.panel_punish as PP  # noqa: E402
_mismatch = {k: (PP._ACTION_ACL.get(k), MODPANEL_ACL_KEYS.get(k))
             for k in PP._ACTION_ACL if PP._ACTION_ACL.get(k) != MODPANEL_ACL_KEYS.get(k)}
check(not _mismatch,
      f'панель «Пользователи» использует ту же карту, что /modpanel (разн: {_mismatch})')
for v in PP._ACTION_ACL.values():
    check(v in PACL.ACTIONS, f'«Пользователи»: ключ «{v}» есть в ACTIONS')

import web.routes.mod_schedule as MS  # noqa: E402
import web.routes.ladder_panel as LD  # noqa: E402
import web.routes.mod_settings as MST  # noqa: E402
for name, acts in (('Расписание', MS.ACTIONS),
                   ('Лестница', LD.ACTIONS),
                   ('Настройки модерации', MST.ACTIONS)):
    for a in acts:
        check(a in PACL.ACTIONS, f'{name}: действие «{a}» — ключ классических разрешений')

print('== 2. Команды-наказания закрыты классическими разрешениями ==')
_punish_names = {
    'ban', 'tempban', 'unban', 'temp-unban', 'softban',          # бан
    'kick', 'tempkick',                                          # кик
    'mute', 'unmute', 'temp-mute', 'temp-unmute',
    'vmute', 'vunmute', 'ghostmute', 'ghostunmute',              # муты
    'timeout', 'untimeout',                                      # таймаут
    'warn', 'unwarn', 'clearwarns', 'pw',                        # варн
    'clear', 'purge', 'nuke',                                    # очистка
    'lock', 'unlock', 'lockdown',                                # локдаун
    'role', 'massrole', 'reactionrole', 'removereactionrole',    # роли
    'raidcleanup',                                               # массовое (kick+ban)
}
_covered = set(PACL.COMMAND_ACTIONS)
_missing = sorted(_punish_names - _covered)
check(not _missing, f'все команды-наказания в COMMAND_ACTIONS (нет: {_missing})')
check(PACL.COMMAND_ACTIONS.get('ghostmute') == ('mute',)
      and PACL.COMMAND_ACTIONS.get('ghostunmute') == ('mute',),
      'тихие муты = действие «Мут»')
check(PACL.COMMAND_ACTIONS.get('nuke') == ('purge',),
      'пересоздание канала = действие «Очистка»')
check(PACL.COMMAND_ACTIONS.get('raidcleanup') == ('kick', 'ban'),
      'raid-cleanup требует и «Кик», и «Бан»')
# команды с параметром action (ladder-add, security-newaccount, moderate…)
# ловятся main._find_action_value + ACTION_VALUES — проверим, что механизм
# на месте и значения действий в справочнике, а у команд есть параметр.
_main_src = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
for name in ('moderate', 'utility', 'ladder-add', 'security-newaccount'):
    check('_find_action_value' in _main_src and 'ACTION_VALUES' in _main_src,
          f'{name}: механизм action-параметра в main.py на месте')
for val in ('ban', 'kick', 'mute', 'timeout', 'warn', 'clear'):
    check(val in PACL.ACTION_VALUES, f'ACTION_VALUES покрывает «{val}»')
_cogs_src = ''.join(open(os.path.join(ROOT, 'cogs', f), encoding='utf-8').read()
                    for f in os.listdir(os.path.join(ROOT, 'cogs'))
                    if f.endswith('.py') and f != '__init__.py')
import re as _re  # noqa: E402
for name in ('ladder-add', 'security-newaccount', 'raidcleanup'):
    _found = _re.search(r"name\s*=\s*['\"]" + _re.escape(name) + r"['\"]", _cogs_src)
    check(bool(_found), f'{name} существует в когах')

print('== 3. has_access: новые команды реально режутся ==')
from services.permission_acl import (has_access, set_action_rule,  # noqa: E402
                                     save_action_acl)


class _Role:
    def __init__(self, rid):
        self.id = rid


class _Perms:
    def __init__(self):
        self.administrator = False


class _Member:
    def __init__(self, uid, roles=()):
        self.id = uid
        self.roles = [_Role(r) for r in roles]
        self.guild_permissions = _Perms()


GID = 909090
save_action_acl(GID, {})
# у каждого действия — своя разрешённая роль, чтобы проверять комбинации
set_action_rule(GID, 'mute', ['mute_role'])
set_action_rule(GID, 'purge', ['purge_role'])
set_action_rule(GID, 'ban', ['ban_role'])
set_action_rule(GID, 'kick', ['kick_role'])
m_other = _Member(501, ['none'])
m_mute_purge = _Member(502, ['mute_role', 'purge_role'])
m_ban_only = _Member(503, ['ban_role'])
m_full = _Member(504, ['mute_role', 'ban_role', 'kick_role'])
check(not has_access(GID, 'ghostmute', m_other), 'без «Мута» /ghostmute закрыт')
check(has_access(GID, 'ghostmute', m_mute_purge), 'с «Мутом» /ghostmute открыт')
check(not has_access(GID, 'nuke', m_ban_only), 'без «Очистки» /nuke закрыт')
check(has_access(GID, 'nuke', m_mute_purge), 'с «Очисткой» /nuke открыт')
check(not has_access(GID, 'raidcleanup', m_mute_purge),
      'raid-cleanup: мут+очистка без «Кика»/«Бана» → закрыт')
check(not has_access(GID, 'raidcleanup', m_ban_only),
      'raid-cleanup: «Бан» без «Кика» → закрыт')
check(has_access(GID, 'raidcleanup', m_full),
      'с «Киком» и «Баном» raid-cleanup открыт')
save_action_acl(GID, {})

print('== 4. Панель: Расписание/Лестница/Настройки не обходят ACL ==')
import asyncio as _aio  # noqa: E402
import threading as _th  # noqa: E402
from web.app import app as _flask_app, set_bot_instance  # noqa: E402


class _Ch:
    def __init__(self, i):
        self.id = i
        self.mention = f'<#{i}>'


class _Member2:
    id = 777001
    bot = False
    display_name = 'LinkedMod'
    name = 'LinkedMod'
    mention = '<@777001>'
    roles = []


class _Guild:
    id = 777002
    owner_id = 1
    name = 'Тест'
    icon = None
    members = []
    roles = []
    text_channels = []

    def get_member(self, uid):
        m = next((m for m in self.members if m.id == uid), None)
        return m

    def get_channel(self, cid):
        return None


class _Bot:
    guilds = []

    def get_guild(self, gid):
        return self.guilds[0] if gid == self.guilds[0].id else None

    def get_cog(self, name):
        return None


_bot = _Bot()
_guild = _Guild()
_member = _Member2()
_member.roles = []                       # без разрешённых ролей (по умолчанию)
_guild.members = [_member]
_bot.guilds = [_guild]
_loop = _aio.new_event_loop()
_th.Thread(target=_loop.run_forever, daemon=True).start()
_bot.loop = _loop
set_bot_instance(_bot)

client = _flask_app.test_client()


def _login(role='mod', discord_id=str(_member.id)):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'LinkedMod'
        sess['role'] = role
        sess['discord_id'] = discord_id
        sess['selected_guild'] = str(_guild.id)
        sess['_role_checked'] = time.time()


# Расписание: бан без права «Бан» → 403
_member.roles = []
set_action_rule(_guild.id, 'ban', ['900'])
_login()
r = client.post(f'/api/guild/{_guild.id}/mod-schedule/create', json={
    'action': 'ban', 'user_id': str(777002), 'run_at': time.time() + 3600,
    'duration': 10, 'reason': 'тест'})
check(r.status_code == 403 and 'Нет права' in (r.get_json().get('error') or ''),
      f'планировщик: бан без «Бана» → 403 ({r.status_code})')
set_action_rule(_guild.id, 'ban', [])

# с правом «Бан» — планируется
_member.roles = [_Role(int(_member.id))]
set_action_rule(_guild.id, 'ban', [str(_member.id)])
r = client.post(f'/api/guild/{_guild.id}/mod-schedule/create', json={
    'action': 'ban', 'user_id': str(777002), 'run_at': time.time() + 3600,
    'duration': 10, 'reason': 'тест'})
check(r.status_code == 200 and (r.get_json() or {}).get('success'),
      f'с «Баном» в Правах команд — планируется ({r.status_code})')
set_action_rule(_guild.id, 'ban', [])

# Лестница: добавить ступень «бан» без права → 403; с правом — ок
# (страница лестницы открыта роли admin панели)
_member.roles = []
_set_role = 'admin'
_login(role=_set_role)
set_action_rule(_guild.id, 'ban', ['900'])
r = client.post(f'/api/guild/{_guild.id}/ladder/add', json={
    'count': 5, 'action': 'ban', 'duration': '1', 'unit': 'minute'})
check(r.status_code == 403, f'лестница: ступень «бан» без права → 403 ({r.status_code})')
_member.roles = [_Role(int(_member.id))]
_login(role=_set_role)
set_action_rule(_guild.id, 'ban', [str(_member.id)])
r = client.post(f'/api/guild/{_guild.id}/ladder/add', json={
    'count': 5, 'action': 'ban', 'duration': '1', 'unit': 'minute'})
check(r.status_code == 200, f'с «Баном» ступень сохраняется ({r.status_code})')
set_action_rule(_guild.id, 'ban', [])

# Настройки модерации: список ступеней с закрытым действием → 403
_member.roles = []
_login(role='admin')
set_action_rule(_guild.id, 'kick', ['900'])
r = client.post(f'/api/guild/{_guild.id}/mod-settings', json={
    'steps': [{'count': 3, 'action': 'kick', 'duration': 0, 'unit': 'minute'}]})
check(r.status_code == 403 and 'Нет права' in (r.get_json().get('error') or ''),
      f'настройки: ступень «кик» без «Кика» → 403 ({r.status_code})')
_member.roles = [_Role(int(_member.id))]
_login(role='admin')
set_action_rule(_guild.id, 'kick', [str(_member.id)])
r = client.post(f'/api/guild/{_guild.id}/mod-settings', json={
    'steps': [{'count': 3, 'action': 'kick', 'duration': 0, 'unit': 'minute'}]})
check(r.status_code == 200, f'с «Киком» лестница сохраняется ({r.status_code})')
set_action_rule(_guild.id, 'kick', [])

# owner панели — доверенный: правила его не режут
_member.roles = []
set_action_rule(_guild.id, 'ban', ['900'])
_login(role='owner')
r = client.post(f'/api/guild/{_guild.id}/mod-schedule/create', json={
    'action': 'ban', 'user_id': str(777002), 'run_at': time.time() + 3600,
    'duration': 10, 'reason': 'тест'})
check(r.status_code == 200, 'owner панели: планирует бан даже без роли (доверенный)')
set_action_rule(_guild.id, 'ban', [])
set_bot_instance(None)

print('== 5. Общий хелпер панели: одна точка, где сессия → мембер ==')
from web.routes._common import viewer_member, acl_action_allowed  # noqa: E402
from flask import session as _flask_session  # noqa: E402
set_bot_instance(_bot)
_member.roles = []                          # без ролей — «чужой»
with client.application.test_request_context():
    _flask_session['role'] = 'mod'
    _flask_session['discord_id'] = str(_member.id)
    mv = viewer_member(_bot, _guild.id)
    check(mv is _member, 'viewer_member: мембер по session[discord_id] найден')
    set_action_rule(_guild.id, 'ban', ['900'])
    check(not acl_action_allowed(_guild.id, mv, 'ban'), 'acl_action_allowed: чужому — нет')
    check(acl_action_allowed(_guild.id, None, 'ban'), 'acl_action_allowed: доверенный — да')
    _flask_session['role'] = 'owner'
    check(viewer_member(_bot, _guild.id) is None,
          'owner панели → доверенный (None), правила не режут')
    set_action_rule(_guild.id, 'ban', [])
set_bot_instance(None)

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
