# -*- coding: utf-8 -*-
"""Классические разрешения (Action ACL): бан/кик/мут/таймаут не зависят от команды.

Идея: сколько бы команд ни умели банить (ban, tempban, unban, /moderate
action=ban), правило «ban» блокирует действие целиком. Проверяем:
1. Справочники ACTIONS / COMMAND_ACTIONS / ACTION_VALUES.
2. check_action (по умолчанию можно, правило закрывает, админ/бот обходят).
3. has_access — слой действий поверх командно-категорийного ACL.
4. Панельный API: GET отдаёт действия, action/set и actions/clear.
5. Интеграция main.py: slash-команда с опцией action=ban блокируется.

Запуск: python3 tests/test_action_permissions.py
"""
import asyncio, importlib, json, os, sys, types, importlib.util

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.makedirs('data', exist_ok=True)

import config
config.Config.DB_PATH = os.path.abspath('data/bot.db')  # изолированная sqlite

from services.permission_acl import (check_action, has_access, set_action_rule,
                                     clear_action_rules, load_action_acl, save_action_acl,
                                     set_rule, save_acl,
                                     ACTIONS, COMMAND_ACTIONS, ACTION_VALUES)

PASS = 0; FAIL = 0
def check(ok, msg):
    global PASS, FAIL
    if ok: PASS += 1; print(f'  PASS: {msg}')
    else: FAIL += 1; print(f'  FAIL: {msg}')

# ── фейки ──
class Role:
    def __init__(self, rid): self.id = rid
class Perms:
    def __init__(self, administrator=False): self.administrator = administrator
class Member:
    def __init__(self, roles=(), administrator=False, bot=False):
        self.roles = [Role(r) for r in roles]
        self.guild_permissions = Perms(administrator)
        self.bot = bot

GID = 777
save_acl(GID, {})
save_action_acl(GID, {})

print('== справочники действий ==')
for act in ('ban', 'kick', 'mute', 'timeout', 'warn'):
    check(act in ACTIONS, f'действие {act} есть')
check(COMMAND_ACTIONS.get('ban') == ('ban',), 'ban -> действие ban')
check(COMMAND_ACTIONS.get('tempban') == ('ban',), 'tempban -> действие ban')
check(COMMAND_ACTIONS.get('unban') == ('ban',), 'unban -> действие ban')
check(COMMAND_ACTIONS.get('mute') == ('mute',), 'mute -> действие mute')
check(COMMAND_ACTIONS.get('vmute') == ('mute',), 'vmute -> действие mute')
check(COMMAND_ACTIONS.get('kick') == ('kick',), 'kick -> действие kick')
check(COMMAND_ACTIONS.get('warn') == ('warn',), 'warn -> действие warn')
check(ACTION_VALUES.get('ban') == 'ban' and ACTION_VALUES.get('timeout') == 'timeout'
      and ACTION_VALUES.get('clear') == 'purge',
      'значения опции action маппятся (ban/timeout/clear)')

print('== check_action ==')
check(check_action(GID, Member(roles=[1]), 'ban'), 'нет правила действия -> можно')
set_action_rule(GID, 'ban', ['555'])
check(not check_action(GID, Member(roles=[1]), 'ban'), 'правило ban -> чужому нельзя')
check(check_action(GID, Member(roles=[555]), 'ban'), 'роль 555 может банить')
check(check_action(GID, Member(roles=[1], administrator=True), 'ban'), 'админ обходит правило')
check(check_action(GID, Member(bot=True), 'ban'), 'боты пропускаются')
check(check_action(GID, Member(roles=[1]), 'kick'), 'другое действие не затронуто')
set_action_rule(GID, 'ban', [])
check(check_action(GID, Member(roles=[1]), 'ban'), 'сняли правило -> снова можно')

print('== has_access: слой действий поверх командного ACL ==')
set_action_rule(GID, 'ban', ['555'])
check(not has_access(GID, 'ban', Member(roles=[1])), 'действие ban блокирует команду ban')
check(not has_access(GID, 'tempban', Member(roles=[1])), 'tempban тоже банит -> блокируется')
check(has_access(GID, 'ban', Member(roles=[555])), 'роль 555 может')
check(has_access(GID, 'warn', Member(roles=[1])), 'warn не затронут правилом ban')
set_action_rule(GID, 'ban', [])

# действие + категория: AND-семантика
set_rule(GID, 'Модерация', ['10'])
set_action_rule(GID, 'ban', ['20'])
check(not has_access(GID, 'ban', Member(roles=[10])), 'есть категория, нет действия -> нельзя')
check(not has_access(GID, 'ban', Member(roles=[20])), 'есть действие, нет категории -> нельзя')
check(has_access(GID, 'ban', Member(roles=[10, 20])), 'обе роли -> можно')
save_acl(GID, {})
set_action_rule(GID, 'ban', [])

print('== панельный API действий ==')
os.environ['PANEL_USER'] = 'admin'; os.environ['PANEL_PASSWORD'] = 'test123'
appmod = importlib.import_module('web.app')
app = appmod.app; app.config['TESTING'] = True
client = app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True; s['username'] = 'admin'; s['role'] = 'owner'

r = client.get(f'/api/role-permissions/{GID}')
body = r.get_json()
check(r.status_code == 200 and body.get('success'), f'GET -> {r.status_code}')
check(isinstance(body.get('actions'), dict) and body.get('actions', {}).get('ban') == 'Бан (апелляция)',
      'GET отдаёт действия с русскими подписями')
check(isinstance(body.get('action_acl'), dict), 'GET отдаёт action_acl')

r = client.post(f'/api/role-permissions/{GID}/action/set',
                data=json.dumps({'action': 'ban', 'role_ids': ['900']}),
                content_type='application/json')
check(r.status_code == 200 and r.get_json().get('success'), 'POST action/set -> ok')
check(load_action_acl(GID).get('ban') == ['900'], 'правило действия записалось в sqlite')

r = client.post(f'/api/role-permissions/{GID}/action/set',
                data=json.dumps({'action': 'ban', 'role_ids': []}),
                content_type='application/json')
check(r.status_code == 200 and 'ban' not in load_action_acl(GID), 'пустой role_ids снимает правило')

r = client.post(f'/api/role-permissions/{GID}/action/set',
                data=json.dumps({'action': 'no-such-action', 'role_ids': ['1']}),
                content_type='application/json')
check(r.status_code == 400, 'неизвестное действие -> 400')

r = client.post(f'/api/role-permissions/{GID}/actions/clear', data='{}',
                content_type='application/json')
check(r.status_code == 200 and load_action_acl(GID) == {}, 'actions/clear -> все правила сняты')

print('== интеграция main.py: slash с опцией action ==')
# заглушки тяжёлых зависимостей — как в test_acl.py
class _AnyMod(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        cls = type(name, (), {'__init__': lambda self, *a, **k: None})
        setattr(self, name, cls)
        return cls
for _m in ['flask_session', 'gunicorn', 'nacl', 'psutil', 'duckduckgo_search',
           'edge_tts', 'faster_whisper', 'voice_recv', 'deep_translator', 'colorama',
           'requests', 'yt_dlp', 'websockets', 'PIL', 'Pillow', 'pyotp', 'qrcode']:
    try:
        if importlib.util.find_spec(_m) is None:
            sys.modules[_m] = _AnyMod(_m)
    except Exception:
        sys.modules[_m] = _AnyMod(_m)
import main  # noqa: E402

class FakeCmd:
    def __init__(self, qn): self.qualified_name = qn; self.name = qn.split()[-1]
class FakeResp:
    def __init__(self): self.kw = None
    async def send_message(self, content=None, **kw): self.kw = {'content': content, **kw}
class FakeInteraction:
    def __init__(self, qn, member, data=None):
        self.command = FakeCmd(qn)
        self.user = member
        self.data = data or {'name': qn}
        self.response = FakeResp()
        class G: id = GID
        self.guild = G()

# действие ban задано через «классические» разрешения: slash-команда с опцией
# action=ban блокируется (механизм общий, не зависит от имени команды).
set_action_rule(GID, 'ban', ['900'])
inter = FakeInteraction('modpanel', Member(roles=[1]),
                        {'name': 'modpanel', 'options': [{'name': 'action', 'value': 'ban', 'type': 3}]})
ok = asyncio.new_event_loop().run_until_complete(main._acl_slash_check(inter))
check(ok is False and inter.response.kw
      and 'Недостаточно прав' in inter.response.kw['content']
      and 'действие' in inter.response.kw['content']
      and inter.response.kw.get('ephemeral') is True,
      'slash: опция action=ban заблокирована для чужого')

inter2 = FakeInteraction('modpanel', Member(roles=[900]),
                         {'name': 'modpanel', 'options': [{'name': 'action', 'value': 'ban', 'type': 3}]})
ok2 = asyncio.new_event_loop().run_until_complete(main._acl_slash_check(inter2))
check(ok2 is True and inter2.response.kw is None, 'slash: своя роль проходит action=ban')

# utility: action=clear (purge) без правила — открыто
inter3 = FakeInteraction('utility', Member(roles=[1]),
                         {'name': 'utility', 'options': [{'name': 'action', 'value': 'clear', 'type': 3}]})
ok3 = asyncio.new_event_loop().run_until_complete(main._acl_slash_check(inter3))
check(ok3 is True, 'slash: action=clear без правила открыто')
set_action_rule(GID, 'ban', [])

# правило на действие purge блокирует action=clear
set_action_rule(GID, 'purge', ['900'])
inter4 = FakeInteraction('utility', Member(roles=[1]),
                         {'name': 'utility', 'options': [{'name': 'action', 'value': 'clear', 'type': 3}]})
ok4 = asyncio.new_event_loop().run_until_complete(main._acl_slash_check(inter4))
check(ok4 is False, 'slash: action=clear заблокирован правилом purge')
set_action_rule(GID, 'purge', [])

os.system('rm -rf data')
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
