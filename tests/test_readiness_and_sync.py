# -*- coding: utf-8 -*-
"""Готовность систем + исчезновение выключенных команд + демки без ID.

1. «Настройки не все завершены»: /staff-panel не создаёт панель, пока
   заявки не дойдут до персонала; в сообщении ТОЛЬКО незавершённое.
2. Выключенные команды («Команды вкл/выкл») исчезают из Discord:
   guild-команды, глобальный список чистится, панели по-прежнему видят
   все команды.
3. /proofs: демка грузится с одним именем участника (без ID и подсказок),
   без участника вовсе — вежливый отказ.
4. Щит: тумблер события сохраняется одним нажатием (разметка страницы).

Запуск: python3 tests/test_readiness_and_sync.py
"""
import asyncio
import io
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_ready_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DEMO_MODE'] = '1'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['SECRET_KEY'] = 'test-secret'

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


# ═══ 1. Готовность заявок ═════════════════════════════════════════════════
print('== «Настройки не все завершены» (/staff-panel) ==')
from services.system_readiness import readiness_block, staff_apply_missing  # noqa: E402


class Chan:
    def __init__(self, i):
        self.id = i


class Role:
    def __init__(self, i, n):
        self.id = i
        self.name = n


class Guild:
    def __init__(self, roles=(), chans=()):
        self.id = 777
        self.roles = list(roles)
        self._ch = {c.id: c for c in chans}

    def get_channel(self, cid):
        return self._ch.get(cid)

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == rid), None)


g_empty = Guild()                      # ничего не настроено
missing = staff_apply_missing(g_empty)
block = readiness_block('Заявки в команду', missing)
check(block is not None and 'не все завершены' in block,
      'пустой сервер: сообщение «настройки не все завершены»')
check('канал' in block and 'роль хелпера' in block and 'роль модератора' in block,
      'перечислено только незавершённое: канал + обе роли')
check('куратор' not in block, 'куратор необязателен — не упомянут')
check(readiness_block('X', []) is None, 'всё готово — сообщения нет')

# частично настроено: канал есть, ролей нет — про канал не пишем
from services import staff_roles as SR  # noqa: E402
SR.save_setting(777, 'helper_channel', 501)
SR.save_setting(777, 'moderator_channel', 502)
g_chans = Guild(chans=[Chan(501), Chan(502)])
m2 = staff_apply_missing(g_chans)
check(len(m2) == 2 and all('роль' in x for x in m2),
      'каналы настроены — про них не упоминается, только две роли')

SR.save_setting(777, 'helper_role', 10)
SR.save_setting(777, 'moderator_role', 20)
g_full = Guild(roles=[Role(10, 'Хелпер'), Role(20, 'Модератор')],
               chans=[Chan(501), Chan(502)])
check(staff_apply_missing(g_full) == [], 'всё настроено — замечаний нет')

src_cog = open(os.path.join(ROOT, 'cogs', 'staff_apply.py'), encoding='utf-8').read()
check('readiness_block' in src_cog, '/staff-panel подключён к проверке готовности')

# ═══ 2. Выключенные команды исчезают из Discord ═══════════════════════════
print('== выключенные команды не попадают в Discord ==')
from services import sync_filtered as SF  # noqa: E402
from services import command_switches as CSW  # noqa: E402


class Cmd:
    def __init__(self, n):
        self.name = n


class Tree:
    def __init__(self):
        self.glob = [Cmd('ban'), Cmd('warn'), Cmd('staff-panel')]
        self.guilds = {}
        self.synced = []

    def get_commands(self, guild=None):
        if guild is None:
            return list(self.glob)
        return list(self.guilds.get(guild.id, []))

    def remove_command(self, name, guild=None, type=None):
        if guild is None:
            self.glob = [c for c in self.glob if c.name != name]
        else:
            self.guilds[guild.id] = [c for c in self.guilds.get(guild.id, []) if c.name != name]

    def add_command(self, c, guild=None):
        if guild is None:
            if c.name not in [x.name for x in self.glob]:
                self.glob.append(c)
        else:
            box = self.guilds.setdefault(guild.id, [])
            if c.name not in [x.name for x in box]:
                box.append(c)

    def copy_global_to(self, guild=None):
        self.guilds[guild.id] = list(self.glob)

    async def sync(self, guild=None):
        box = self.glob if guild is None else self.guilds.get(guild.id, [])
        self.synced.append(('global' if guild is None else guild.id,
                            [c.name for c in box]))
        return box


class GObj:
    def __init__(self, i):
        self.id = i


class Bot:
    def __init__(self):
        self.tree = Tree()
        self.guilds = [GObj(777)]

    def get_guild(self, i):
        return GObj(777) if i == 777 else None


CSW.set_disabled('warn', True)
b = Bot()
asyncio.new_event_loop().run_until_complete(SF.full_sync(b))
synced = dict(b.tree.synced)
check(synced.get('global') == [], 'глобальный список Discord очищен (без дублей)')
check('warn' not in synced.get(777, []) and 'ban' in synced.get(777, []),
      'на сервер синка без выключенной warn, но с ban')
check('staff-panel' in synced.get(777, []), 'остальные команды на месте')
check(any(c.name == 'warn' for c in b.tree.get_commands(guild=GObj(777))),
      'warn вернулась в локальное дерево — панель видит и может включить')

CSW.set_disabled('warn', False)        # включили обратно
b2 = Bot()
asyncio.new_event_loop().run_until_complete(SF.full_sync(b2))
synced2 = dict(b2.tree.synced)
check('warn' in synced2.get(777, []), 'включили warn — снова в Discord')

src_main = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
check('full_sync' in src_main, 'старт бота использует полный синк')
CSW.set_disabled('warn', False)

# ═══ 3. Демки: имя вместо ID ══════════════════════════════════════════════
print('== /proofs: загрузка без ID участника ==')
from web.app import app  # noqa: E402
app.config['TESTING'] = True
c = app.test_client()
with c.session_transaction() as s:
    s.update(logged_in=True, role='owner', username='t', selected_guild='777')

png = b'\x89PNG\r\n\x1a\n' + b'x' * 150
r = c.post('/api/proofs/upload', data={
    'file': (io.BytesIO(png), 'd.png'), 'user_id': '',
    'user_name': 'Вася Пупкин', 'action': 'бан', 'reason': 'тест',
}, content_type='multipart/form-data')
check(r.status_code == 200 and r.get_json().get('success'),
      'демка грузится с одним именем (без ID и подсказок)')
r2 = c.post('/api/proofs/upload', data={
    'file': (io.BytesIO(png), 'd2.png'), 'user_id': '',
    'user_name': '', 'action': 'бан', 'reason': '',
}, content_type='multipart/form-data')
d2 = r2.get_json()
check(d2.get('success') is False and 'участника' in d2.get('error', ''),
      'без участника вовсе — вежливый отказ с подсказкой')

# ═══ 4. Щит: тумблер = одно нажатие ═══════════════════════════════════════
print('== Щит: включение по одному — одним нажатием ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'guardian.html'),
           encoding='utf-8').read()
check("t.classList.contains('gd-ev-tog')" in tpl and "gdMaster" in tpl,
      'тумблер события и мастер-выключатель сохраняются сразу (одно нажатие)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
