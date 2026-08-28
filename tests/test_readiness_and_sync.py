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
    def __init__(self, n, ctype='chat', extras=None):
        self.name = n
        self.ctype = ctype          # 'chat' | 'user' | 'message'
        self.extras = extras or {}


class Tree:
    """Кукла discord.py CommandTree: команды — (имя, тип), глобальные
    контекстные меню копируются в гильдии (как настоящий copy_global_to).
    sync() записывает пейлоад: [(имя, тип)]."""

    def __init__(self):
        self.glob = [Cmd('ban'), Cmd('warn'), Cmd('staff-panel'),
                     Cmd('апелляция', extras={'keep_global': True}),
                     Cmd('Войс-мут', 'user'), Cmd('Варн за сообщение', 'message')]
        self.guilds = {}
        self.synced = []

    @staticmethod
    def _want(t):
        n = getattr(t, 'name', None) or t or 'chat_input'
        return 'chat' if n == 'chat_input' else n

    def get_commands(self, guild=None, type=None):
        box = self.glob if guild is None else self.guilds.get(guild.id, [])
        want = self._want(type)
        return [c for c in box if c.ctype == want]

    def remove_command(self, name, guild=None, type=None):
        box = self.glob if guild is None else self.guilds.get(guild.id, [])
        want = self._want(type)
        box2 = [c for c in box if not (c.name == name and c.ctype == want)]
        if guild is None:
            self.glob = box2
        else:
            self.guilds[guild.id] = box2

    def add_command(self, c, guild=None):
        box = self.glob if guild is None else self.guilds.setdefault(guild.id, [])
        if not any(x.name == c.name and x.ctype == c.ctype for x in box):
            box.append(c)

    def copy_global_to(self, guild=None):
        box = self.guilds.setdefault(guild.id, [])
        for c in self.glob:          # discord.py копирует ВСЁ: и слэши, и меню
            if not any(x.name == c.name and x.ctype == c.ctype for x in box):
                box.append(c)

    async def sync(self, guild=None):
        box = self.glob if guild is None else self.guilds.get(guild.id, [])
        self.synced.append(('global' if guild is None else guild.id,
                            [(c.name, c.ctype) for c in box]))
        return box


class GObj:
    def __init__(self, i):
        self.id = i


class Bot:
    def __init__(self):
        self.tree = Tree()
        # 999 — сервер ВНЕ MAIN/EXTRA (бот туда приглашён, но
        # гильдовый синк его не покрывает) — полигон для чужих копий.
        self.guilds = [GObj(777), GObj(999)]

    def get_guild(self, i):
        return GObj(777) if i == 777 else None


CSW.set_disabled('warn', True)
b = Bot()
asyncio.new_event_loop().run_until_complete(SF.full_sync(b))
synced = dict(b.tree.synced)
glob_names = {n for n, _ in synced.get('global', [])}
check(glob_names == {'апелляция'},
      f'глобально остаётся только keep_global /апелляция — дублей нет (glob={sorted(glob_names)})')
check(not any(t != 'chat' for _, t in synced.get('global', [])),
      'контекстные меню НЕ остаются глобальными (иначе были бы дубли)')
g777 = synced.get(777, [])
g777_names = {n for n, _ in g777}
check('warn' not in g777_names and 'ban' in g777_names,
      'на сервер синка без выключенной warn, но с ban')
check('staff-panel' in g777_names, 'остальные команды на месте')
check(('Войс-мут', 'user') in g777 and ('Варн за сообщение', 'message') in g777,
      'контекстные меню доехали до сервера (и только туда)')
check('апелляция' not in g777_names,
      'keep_global НЕ копируется в гильдию — иначе «апелляция» видна дважды')
check(synced.get(999) == [],
      'сервер вне MAIN/EXTRA очищен от старых копий команд (вечные дубли)')
check(any(c.name == 'warn' for c in b.tree.get_commands(guild=GObj(777))),
      'warn вернулась в локальное дерево — панель видит и может включить')

# повторный прогон (как рестарт / кнопка «Синхронизировать команды»):
synced_len1 = len(b.tree.synced)
asyncio.new_event_loop().run_until_complete(SF.full_sync(b))
synced_again = dict(b.tree.synced)
check(dict(b.tree.synced).get('global') == synced.get('global')
      and dict(b.tree.synced).get(777) == g777,
      'повторный синк идемпотентен — пейлоады не растут и не меняются')

CSW.set_disabled('warn', False)        # включили обратно
b2 = Bot()
asyncio.new_event_loop().run_until_complete(SF.full_sync(b2))
synced2 = dict(b2.tree.synced)
check('warn' in {n for n, _ in synced2.get(777, [])},
      'включили warn — снова в Discord')

src_main = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
check('full_sync' in src_main, 'старт бота использует полный синк')
src_app = open(os.path.join(ROOT, 'web', 'app.py'), encoding='utf-8').read()
blog = src_app[src_app.index('def api_bot_sync'):src_app.index('api_global_search')]
check('full_sync' in blog, 'кнопка «Синхронизировать команды» идёт через full_sync')
check('commands-audit' in src_app and 'fetch_commands' in src_app,
      'есть рентген команд: /api/bot/commands-audit читает РЕАЛЬНЫЕ списки из Discord')
import re as _re
check(not _re.search(r'\btree \.sync \(\)', blog),
      'в обработчике кнопки нет сырого глобального tree.sync() (источник дублей)')
CSW.set_disabled('warn', False)

# ═══ 2б. full_sync: защита от дублей и пустого меню ═══════════════════════
print('== full_sync: откаты при провалах ==')


class TreeGuildFail(Tree):
    """Глобальный sync проходит, guild-sync падает (недоступный сервер)."""

    async def sync(self, guild=None):
        if guild is not None:
            raise RuntimeError('429 rate limit')
        return await super().sync(guild)


b3 = Bot()
b3.tree = TreeGuildFail()
r3 = asyncio.new_event_loop().run_until_complete(SF.full_sync(b3))
gl3 = [x for x in b3.tree.synced if x[0] == 'global']
check(r3 == [], 'провал всех guild-синков: ничего не «выдано» в гильдии')
check(len(gl3) == 2, 'глобальный sync вызван дважды: очистка + откат')
check(gl3[1][1] and ('warn', 'chat') in gl3[1][1],
      'откат вернул глобальное меню — команды не пропали из Discord')
check(not any(x[0] == 777 for x in b3.tree.synced),
      'при провале guild-sync в Discord ничего не ушло (меню без дублей)')


class TreeGlobalFail(Tree):
    """Глобальная очистка падает — guild-синк трогать нельзя (будут дубли)."""

    async def sync(self, guild=None):
        if guild is None and not hasattr(self, '_boom'):
            self._boom = True
            raise RuntimeError('HTTP 400')
        return await super().sync(guild)


b4 = Bot()
b4.tree = TreeGlobalFail()
r4 = asyncio.new_event_loop().run_until_complete(SF.full_sync(b4))
check(r4 == [], 'провал глобальной очистки: bail-out, пустой результат')
check(not any(x[0] == 777 for x in b4.tree.synced),
      'guild-синк не тронут — старое глобальное меню осталось, дублей нет')
check(any(c.name == 'warn' for c in b4.tree.get_commands(guild=None)),
      'локальное дерево собрано обратно после bail-out')

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
