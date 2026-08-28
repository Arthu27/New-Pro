# -*- coding: utf-8 -*-
"""Тесты cogs/mod_kit.py: /nuke, /raidcleanup, /dehoist (варн реакцией удалён).

Запуск: python3 tests/test_mod_kit.py
"""
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

_TMP = tempfile.mkdtemp(prefix='hakumo_modkit_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs import mod_kit as mk  # noqa: E402

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


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ═══ 1. Чистые функции: hoisting/залго ═══════════════════════════════════
print('== чистые функции ==')
check(mk.is_hoist('!Вася') and mk.is_hoist('#top') and mk.is_hoist(' spaced'),
      'hoist: ! # и пробел ловятся')
check(not mk.is_hoist('Вася') and not mk.is_hoist('Zed') and not mk.is_hoist('1st')
      and not mk.is_hoist(''), 'hoist: обычные ники и цифры — нет')
zalg = 'a' + '́' * 3
check(mk.is_zalgo(zalg) and not mk.is_zalgo('обычный ник'), 'zalgo: ≥3 combining — ловится')
check(mk.needs_clean('!name') and mk.needs_clean(zalg) and not mk.needs_clean('Норм Ник'),
      'needs_clean: комбо')
check(mk.clean_name('!Вася') == 'Вася', 'clean: срезан ведущий !')
check(mk.clean_name('!!  Petya') == 'Petya', 'clean: срезана цепочка + пробелы')
check(mk.clean_name(zalg) == 'a', 'clean: залго-знаки удалены')
check(mk.clean_name('!!!') == mk.FALLBACK_NAME, 'clean: пустой результат → заглушка')
check(len(mk.clean_name('!' + 'я' * 40)) <= 32, 'clean: ник ≤ 32 символов')

# ═══ 2. raid_candidates ══════════════════════════════════════════════════
print('== raid_candidates ==')


class Perms:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FM:
    def __init__(self, uid, minutes_ago, bot=False, admin=False):
        self.id = uid
        self.bot = bot
        self.display_name = f'User{uid}'
        self.mention = f'<@{uid}>'
        self.joined_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        self.guild_permissions = Perms(administrator=admin, manage_messages=False,
                                       moderate_members=False)
        self.kicked = False
        self.edited_nick = None

    async def kick(self, reason=None):
        self.kicked = True


mems = [FM(1, 2), FM(2, 30), FM(3, 5, bot=True), FM(4, 7, admin=True), FM(5, 9)]
cand = mk.raid_candidates(mems, __import__('time').time(), 10)
check([m.id for m in cand] == [1, 5] or [m.id for m in cand] == [5, 1],
      f'кандидаты: только 1 и 5 из окна 10 мин (выбраны {[m.id for m in cand]})')
cand2 = mk.raid_candidates(mems, __import__('time').time(), 35)
check(len(cand2) == 3 and all(not m.bot and not m.guild_permissions.administrator for m in cand2),
      'кандидаты: окно 35 мин → 3, боты/админы пропущены')

# ═══ 3. Варн реакцией удалён (заказ владельца 2026-08) ═════════════════
print('== варн реакцией удалён ==')
mk_src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'cogs', 'mod_kit.py'), encoding='utf-8').read()
check('on_raw_reaction_add' not in mk_src, 'листенер реакций-варнов вырезан')
check('REACT_EMOJIS' not in mk_src and 'react_mark' not in mk_src,
      'хранилище реактивных варнов вырезано')

# ═══ 4. Ког: колбэки ═════════════════════════════════════════════════════
print('== ког: колбэки ==')


class Resp:
    def __init__(self):
        self.sent = []
        self.deferred = False

    async def send_message(self, **kw):
        self.sent.append(kw)

    async def send(self, **kw):
        self.sent.append(kw)

    async def defer(self, **kw):
        self.deferred = True


class FakeInter:
    def __init__(self, guild, user, channel=None):
        self.guild = guild
        self.user = user
        self.channel = channel
        self.response = Resp()
        self.followup = Resp()


class FakeChannel:
    def __init__(self, name='general'):
        self.name = name
        self.position = 4
        self.mention = f'#{name}'
        self.sent = []
        self.deleted = False
        self.cloned = None
        self.position_set = None
        self.messages = {}

    async def clone(self, reason=None):
        self.cloned = FakeChannel(self.name)
        return self.cloned

    async def edit(self, **kw):
        if 'position' in kw:
            self.position_set = kw['position']

    async def delete(self, reason=None):
        self.deleted = True

    async def send(self, **kw):
        self.sent.append(kw)

    async def fetch_message(self, mid):
        return self.messages[mid]


class FakeGuild:
    def __init__(self, members=()):
        self.id = 777
        self.name = 'Test'
        self.owner_id = 424242
        self.members = list(members)
        self.banned = []
        self.channels = []

    def get_channel(self, cid):
        return None

    async def ban(self, member, reason=None, delete_message_days=0):
        self.banned.append((member, reason, delete_message_days))


class MockUser(FM):
    def __init__(self, uid, minutes_ago=60, manage=False, **kw):
        super().__init__(uid, minutes_ago, **kw)
        self.guild_permissions = Perms(administrator=False, manage_messages=manage,
                                       moderate_members=manage)
        self.bot = False


class BotUser:
    id = 999000


class FakeBot:
    def __init__(self, guild=None, warnings_cog=None):
        self.user = BotUser()
        self._guild = guild
        self._wc = warnings_cog
        self.latency = 0.01
        self.guilds = [guild] if guild else []

    def get_guild(self, gid):
        return self._guild if self._guild and self._guild.id == gid else None

    def get_cog(self, name):
        return self._wc if name == 'warnings' else None


class FakeWC:
    def __init__(self):
        self.warns = []

    async def add_warning(self, user, moderator, reason=None):
        self.warns.append((user, moderator, reason))


class FakeMsg:
    def __init__(self, author, content='нарушение!'):
        self.author = author
        self.content = content
        self.reactions_added = []

    async def add_reaction(self, e):
        self.reactions_added.append(e)


class Payload:
    pass


# ── /nuke ──
ch = FakeChannel('флудилка')
mod = MockUser(10, manage=True)
g = FakeGuild()
cog = mk.ModKit(FakeBot(g))

inter = FakeInter(g, mod, ch)
run(mk.ModKit.nuke.callback(cog, inter, channel=ch, confirm=False))
check(inter.response.sent and 'True' in (inter.response.sent[0]['embed'].description or ''),
      '/nuke без confirm: только предупреждение')
check(not ch.deleted and ch.cloned is None, '/nuke без confirm: канал не тронут')

inter = FakeInter(g, mod, ch)
run(mk.ModKit.nuke.callback(cog, inter, channel=ch, confirm=True))
check(inter.response.deferred, '/nuke: defer (долгая операция)')
check(ch.deleted and ch.cloned is not None, '/nuke: старый удалён, клон создан')
check(ch.cloned.position_set == 4, '/nuke: позиция сохранена')
check(ch.cloned.sent and 'пересоздан' in (ch.cloned.sent[0]['embed'].description or ''),
      '/nuke: карточка в новом канале')
check(inter.followup.sent and 'Готово' in (inter.followup.sent[0]['embed'].title or ''),
      '/nuke: мод получил подтверждение')


# ── /raidcleanup ──
async def _no_edit(self, **kw):
    return None


m1, m2 = FM(1, 2), FM(2, 5)
m2.edit = _no_edit.__get__(m2)
g2 = FakeGuild([m1, m2, FM(3, 60), FM(4, 3, bot=True), FM(5, 4, admin=True)])
cog2 = mk.ModKit(FakeBot(g2))

inter = FakeInter(g2, mod)
run(mk.ModKit.raidcleanup.callback(cog2, inter, minutes=10, action=None, confirm=False))
check('2' in (inter.response.sent[0]['embed'].description or ''),
      '/raidcleanup предпросмотр: 2 кандидата')
check(not m1.kicked and not g2.banned, '/raidcleanup без confirm: никого не тронули')

inter = FakeInter(g2, mod)
run(mk.ModKit.raidcleanup.callback(cog2, inter, minutes=10, action='kick', confirm=True))
check(m1.kicked and m2.kicked and not g2.banned, '/raidcleanup kick: оба кикнуты')
check('Обработано: **2**' in (inter.followup.sent[0]['embed'].description or ''),
      '/raidcleanup: отчёт «обработано 2»')

m3 = FM(6, 1)
g2.members.append(m3)
inter = FakeInter(g2, mod)
run(mk.ModKit.raidcleanup.callback(cog2, inter, minutes=10, action='ban', confirm=True))
check(len(g2.banned) == 3 and all(b[2] == 1 for b in g2.banned),
      '/raidcleanup ban: бан с чисткой сообщений (1 день), новый юзер включён')

# ── /dehoist ──
hz = FM(1, 60)
hz.bot = False
hz.display_name = '!выпиратель'


async def _edit_fail(self, **kw):
    raise RuntimeError('denied')


m_bad = FM(2, 60)
m_bad.display_name = '#залго-рик'
m_bad.edit = _edit_fail.__get__(m_bad)
m_ok = FM(3, 60)
m_ok.display_name = 'Нормальный'
g3 = FakeGuild([hz, m_bad, m_ok])
cog3 = mk.ModKit(FakeBot(g3))

inter = FakeInter(g3, mod)
run(mk.ModKit.dehoist.callback(cog3, inter, simulate=True))
check('**2**' in (inter.response.sent[0]['embed'].description or ''),
      '/dehoist симуляция: найдено 2')

renamed = []


async def _edit_ok(self, **kw):
    renamed.append(kw.get('nick'))


hz.edit = _edit_ok.__get__(hz)
inter = FakeInter(g3, mod)
run(mk.ModKit.dehoist.callback(cog3, inter, simulate=False))
check(renamed == ['выпиратель'], f'/dehoist: первый переименован ({renamed})')
check('Не удалось' in (inter.followup.sent[0]['embed'].description or '')
      and '**1**' in inter.followup.sent[0]['embed'].description,
      '/dehoist: сбой прав посчитан, но не уронил команду')

# ═══ 5. Регистрация ══════════════════════════════════════════════════════
print('== setup ==')
reg = {}


class RegBot(FakeBot):
    async def add_cog(self, c):
        reg['cog'] = c


rb = RegBot()
run(mk.setup(rb))
check(isinstance(reg.get('cog'), mk.ModKit), 'setup: ког регистрируется')

names = [c.name for c in mk.ModKit.__cog_app_commands__] if hasattr(mk.ModKit, '__cog_app_commands__') else []
check('nuke' in names and 'raidcleanup' in names and 'dehoist' in names,
      f'слэши nuke/raidcleanup/dehoist объявлены ({names})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
