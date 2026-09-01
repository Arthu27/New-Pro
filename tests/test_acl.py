# -*- coding: utf-8 -*-
"""E2E: ролевой доступ к командам (Command ACL).
Ключевой баг: правила панели на группы команд ("j2c", "tagjail"...) не
срабатывали, т.к. в рантайме проверялось лишь имя сабкоманды ("lobby").
Теперь проверяется цепочка кандидатов: "j2c-lobby" -> "j2c".

Запуск:  python3 tests/test_acl.py
"""
import asyncio, importlib, json, os, sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.makedirs('data', exist_ok=True)

import config
config.Config.DB_PATH = os.path.abspath('data/bot.db')  # изолированная sqlite

from services.permission_acl import (_candidates, has_access, roles_for_command,
                                     set_rule, clear_rule, load_acl, save_acl,
                                     COMMAND_CATEGORIES)

PASS = 0; FAIL = 0
def check(ok, msg):
    global PASS, FAIL
    if ok: PASS += 1; print(f'  PASS: {msg}')
    else: FAIL += 1; print(f'  FAIL: {msg}')

# ---------- фейки ----------
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
save_acl(GID, {})  # чистый лист

print('== резолвер имён ==')
check(_candidates('ban') == ['ban'], 'одиночная команда -> [ban]')
check(_candidates('temp-mute') == ['temp-mute'], 'одиночная с дефисом -> только она')
check(_candidates('j2c lobby') == ['j2c-lobby', 'j2c'], 'сабкоманда -> [j2c-lobby, j2c]')
check(_candidates('ticket sla create') == ['ticket-sla-create', 'ticket-sla', 'ticket'],
      'три уровня -> цепочка предков')

print('== has_access: база ==')
check(has_access(GID, 'ban', Member(roles=[1])), 'нет правил -> всем можно')
set_rule(GID, 'ban', ['555'])
check(not has_access(GID, 'ban', Member(roles=[1])), 'правило ban -> чужому нельзя')
check(has_access(GID, 'ban', Member(roles=[555])), 'правило ban -> роли 555 можно')
check(has_access(GID, 'ban', Member(roles=[1], administrator=True)), 'админ обходит правило')
check(has_access(GID, 'ban', Member(bot=True)), 'боты пропускаются')
clear_rule(GID, 'ban')
check(has_access(GID, 'ban', Member(roles=[1])), 'clear_rule -> снова всем можно')

print('== правило на категорию ==')
set_rule(GID, 'Модерация', ['777'])
check(not has_access(GID, 'kick', Member(roles=[1])), 'категория Модерация закрыта (kick)')
check(has_access(GID, 'kick', Member(roles=[777])), 'роль 777 может (kick)')
check(has_access(GID, '8ball', Member(roles=[1])), 'другая категория не затронута (8ball)')
save_acl(GID, {})

print('== КЛЮЧЕВОЙ БАГ: сабкоманды групп ==')
set_rule(GID, 'j2c', ['900'])
check(not has_access(GID, 'j2c lobby', Member(roles=[1])),
      'правило на группу j2c блокирует /j2c lobby (раньше НЕ работало)')
check(has_access(GID, 'j2c-limit', Member(roles=[1])),
      'одиночное имя j2c-limit изолировано (правило j2c ловит через qualified "j2c limit")')
check(not has_access(GID, 'j2c limit', Member(roles=[1])),
      'qualified "j2c limit" -> правило j2c блокирует (реальный рантайм slash)')
check(has_access(GID, 'j2c lobby', Member(roles=[900])), 'роль 900 может /j2c lobby')
save_acl(GID, {})
set_rule(GID, 'j2c-lobby', ['901'])
check(not has_access(GID, 'j2c lobby', Member(roles=[900])),
      'правило на сабкоманду: у чужого (есть 900, но не 901) нельзя')
check(has_access(GID, 'j2c lobby', Member(roles=[901])), 'роль 901 может /j2c lobby')
check(has_access(GID, 'j2c limit', Member(roles=[900])),
      'правило j2c-lobby не трогает другую сабкоманду')
save_acl(GID, {})

print('== изоляция имён с дефисом ==')
set_rule(GID, 'report', ['333'])
check(not has_access(GID, 'report', Member(roles=[1])), 'report закрыт')
check(has_access(GID, 'report-role-add', Member(roles=[1])),
      'правило report НЕ перетекает на report-role-add')
check(not has_access(GID, 'report stats', Member(roles=[1])),
      'но сабкоманда "report stats" ловит правило родителя report')
save_acl(GID, {})

print('== несколько правил сразу (AND-семантика) ==')
set_rule(GID, 'Модерация', ['10'])
set_rule(GID, 'ban', ['20'])
check(not has_access(GID, 'ban', Member(roles=[10])), 'есть роль категории, нет роли команды -> нельзя')
check(not has_access(GID, 'ban', Member(roles=[20])), 'есть роль команды, нет роли категории -> нельзя')
check(has_access(GID, 'ban', Member(roles=[10, 20])), 'обе роли -> можно')
check(has_access(GID, 'ban', Member(roles=[10, 20, 99])), 'обе роли + лишняя -> можно')
save_acl(GID, {})

print('== roles_for_command ==')
set_rule(GID, 'j2c', ['900'])
check(roles_for_command(GID, 'j2c lobby') == ['900'], 'сабкоманда получает роли группы')
set_rule(GID, 'j2c-lobby', ['901'])
check(roles_for_command(GID, 'j2c lobby') == ['901'], 'прямое правило важнее группового')
save_acl(GID, {})

print('== интеграция: хуки main.py ==')
# main.py при импорте проверяет зависимости и при их отсутствии делает sys.exit(1).
# В песочнице pip недоступен (externally-managed), поэтому подкладываем
# заглушки отсутствующих модулей — самим командам они не нужны.
import types, importlib.util
class _AnyMod(types.ModuleType):
    """Модуль-заглушка: любой обычный атрибут существует (для аннотаций в коде),
    а дандеры (напр. __path__) отсутствуют — иначе ломается импорт сабмодулей."""
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
import main  # регистрирует bot.check + tree.interaction_check

class FakeCmd:
    def __init__(self, qn): self.qualified_name = qn; self.name = qn.split()[-1]
class FakeResp:
    def __init__(self): self.kw = None
    async def send_message(self, content=None, **kw): self.kw = {'content': content, **kw}
class FakeInteraction:
    def __init__(self, qn, member):
        self.command = FakeCmd(qn)
        self.user = member
        self.data = {'name': qn}
        self.response = FakeResp()
        class G: id = GID
        self.guild = G()
class FakeCtx:
    def __init__(self, qn, member):
        self.command = FakeCmd(qn)
        self.author = member
        self.sent = []
        class G: id = GID
        self.guild = G()
    async def send(self, content=None, **kw): self.sent.append(content)

set_rule(GID, 'j2c', ['900'])
inter = FakeInteraction('j2c lobby', Member(roles=[1]))
ok = asyncio.new_event_loop().run_until_complete(main._acl_slash_check(inter))
check(ok is False and inter.response.kw
      and 'Недостаточно прав' in inter.response.kw['content']
      and '/j2c' in inter.response.kw['content']
      and inter.response.kw.get('ephemeral') is True,
      'slash: /j2c lobby заблокирован для чужого (эфемерно)')
inter2 = FakeInteraction('j2c lobby', Member(roles=[900]))
ok2 = asyncio.new_event_loop().run_until_complete(main._acl_slash_check(inter2))
check(ok2 is True and inter2.response.kw is None, 'slash: своя роль проходит /j2c lobby')
inter3 = FakeInteraction('8ball', Member(roles=[1]))
ok3 = asyncio.new_event_loop().run_until_complete(main._acl_slash_check(inter3))
check(ok3 is True, 'slash: команда без правила открыта')

ctx = FakeCtx('meeting role-add', Member(roles=[1]))
set_rule(GID, 'meeting-role-add', ['700'])
okp = asyncio.new_event_loop().run_until_complete(main._acl_check(ctx))
check(okp is False and ctx.sent and 'нет доступа' in ctx.sent[0],
      'prefix: !meeting role-add заблокирован (правило meeting-role-add)')
ctx2 = FakeCtx('meeting role-add', Member(roles=[700]))
okp2 = asyncio.new_event_loop().run_until_complete(main._acl_check(ctx2))
check(okp2 is True, 'prefix: своя роль проходит !meeting role-add')
save_acl(GID, {})

# ── Владелец бота: правила команд его не проверяют ──
os.environ['OWNER_IDS'] = '555555'
set_rule(GID, 'j2c', ['900'])
class _OwnerM:
    class _P: administrator = False
    guild_permissions = _P(); bot = False
    id = 555555
    roles = []
class _StrangerM:
    class _P: administrator = False
    guild_permissions = _P(); bot = False
    id = 666666
    roles = []
check(has_access(GID, 'j2c lobby', _OwnerM()) is True,
      'владелец бота (OWNER_IDS) проходит закрытую команду без роли')
check(has_access(GID, 'j2c lobby', _StrangerM()) is False,
      'посторонний без роли — по-прежнему мимо')
os.environ.pop('OWNER_IDS', None)


print('== панельный API категорий ==')
os.environ['PANEL_USER'] = 'admin'; os.environ['PANEL_PASSWORD'] = 'test123'
appmod = importlib.import_module('web.app')
app = appmod.app; app.config['TESTING'] = True
client = app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True; s['username'] = 'admin'; s['role'] = 'owner'

r = client.get(f'/api/role-permissions/{GID}')
body = r.get_json()
check(r.status_code == 200 and body.get('success'), f'GET категории -> {r.status_code}')
cats = body.get('categories', {})
# категории = ЖИВОЙ каталог бота (не хардкод): призраков удалённых команд нет
from services import command_registry as CR
from services.permission_acl import command_categories as live_cats
live = live_cats()
check(cats == live, 'категории панели = живой каталог бота (1:1)')
check('Модерация' in cats and 'modpanel' in cats.get('Модерация', []),
      'категория Модерация содержит живую команду modpanel')
check('ban' not in cats.get('Модерация', []) and 'kick' not in cats.get('Модерация', []),
      'удалённые ban/kick НЕ показываются как призраки')
total_cmds = sum(len(v) for v in cats.values())
cat_total = CR.catalog()['total']
check(total_cmds == cat_total, f'всего команд в панели: {total_cmds} == каталогу {cat_total}')

r = client.post(f'/api/role-permissions/{GID}/set',
                data=json.dumps({'command': 'report', 'role_ids': ['900']}),
                content_type='application/json')
check(r.status_code == 200 and r.get_json().get('success'), 'POST set report -> ok')
check(load_acl(GID).get('report') == ['900'], 'правило записалось в sqlite')
r = client.post(f'/api/role-permissions/{GID}/set',
                data=json.dumps({'command': 'report', 'role_ids': []}),
                content_type='application/json')
check(r.status_code == 200 and 'report' not in load_acl(GID), 'POST set пустой -> правило снято')
r = client.post(f'/api/role-permissions/{GID}/clear', data='{}', content_type='application/json')
check(r.status_code == 200 and load_acl(GID) == {}, 'POST clear -> все правила сняты')

print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
