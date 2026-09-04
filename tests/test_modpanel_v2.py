# -*- coding: utf-8 -*-
"""Слеш-переезд + бан-апелляция + видимость /modpanel по ролям.

1) префиксных команд в боевом составе больше нет (все — слеш);
2) «бан» из /modpanel не выкидывает с сервера: нужен настроенный канал
   апелляции (панель → Каналы и маршруты), без него — «настройки не
   завершены» с перечислением ТОЛЬКО незавершённого;
3) /modpanel показывает модератору только действия его ролей.

Запуск: python3 tests/test_modpanel_v2.py
"""
import asyncio
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_modpanel_v2_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
# actions_for_member теперь читает и Action ACL (permission_acl → SQLite) —
# изолируем БД, чтобы тест не трогал боевую data/bot.db
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


print('== 1. Слеш-переезд: в боевом составе нет префиксных команд ==')
from services.command_registry import catalog  # noqa: E402

cat = catalog(force=True)
pref = [c['name'] for c in cat['commands'] if c['kind'] == 'prefix']
check(cat.get('prefix', 1) == 0 and not pref,
      f'боевой состав без «!»-команд (осталось: {pref})')
for name, kind in (('modpanel', 'slash'), ('report', 'slash'),
                   ('апелляция', 'slash'), ('update', 'slash')):
    hit = next((c for c in cat['commands'] if c['name'] == name), None)
    check(hit is not None and hit['kind'] == kind,
          f'{name} — слеш-команда')
# Музыка снята 2026-09-01 — /play больше нет в боевом составе
check(not next((c for c in cat['commands'] if c['name'] == 'play'), None),
      '/play снят — музыкальная система выведена из боевого состава')

import slash_budget  # noqa: E402
keep = slash_budget.KEEP_SLASH
# Сетап-команды (verify-setup, report-setup/settings) убраны в панель,
# /afk-remove удалён (AFK спадает авто). С 2026-09-04 в меню снова /proof —
# демка файлом прямо из Discord (просьба владельца: «у нас нет такой команды»).
check(set(keep) == {'modpanel', 'апелляция', 'update',
                    'afk', 'report', 'my-violations', 'proof'},
      f'белый список слеш-меню = 7 команд (сейчас: {sorted(keep)})')
for name in ('modpanel', 'апелляция', 'update', 'afk',
             'report', 'my-violations', 'proof'):
    check(name in keep, f'{name} в KEEP_SLASH (иначе исчезнет из меню)')
for gone in ('afk-remove', 'verify-setup', 'report-setup', 'report-settings'):
    check(gone not in keep, f'{gone} убран из слеш-меню (настройка в панели/авто)')
check('play' not in keep, '/play снят — музыка выведена из боевого состава')
# Тикет-система снята 2026-08-31 — ticket-panel не должен вернуться
check('ticket-panel' not in keep, 'ticket-panel снят — жалобы идут через /report')

# Урезанные из меню имена НЕ должны вернуться в KEEP_SLASH незаметно
for gone in ('backup', 'backup-list', 'diagnose', 'health', 'hotreload',
             'leave', 'logs-setup', 'help', 'warn', 'module'):
    check(gone not in keep, f'{gone} убран из слеш-меню (заказ владельца)')

# warn живёт ВНУТРИ /modpanel (а не отдельной командой)
src_mod = open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read()
check('("warn", "Варн (предупреждение)"' in src_mod,
      'варн — пункт выпадающего меню /modpanel')
check('allowed_contexts' in open(os.path.join(ROOT, 'cogs', 'diagnostics.py'),
                                 encoding='utf-8').read(),
      '/update спрятан в ЛС — на сервере его не видит никто, кроме владельца')

src_appeals = open(os.path.join(ROOT, 'cogs', 'appeals.py'), encoding='utf-8').read()
check("keep_global" in src_appeals, '/апелляция помечена keep_global (работает в ЛС)')
src_sync = open(os.path.join(ROOT, 'services', 'sync_filtered.py'), encoding='utf-8').read()
check('keep_global' in src_sync, 'sync не вычищает глобальные ЛС-команды')

print('== 2. Канал апелляции (бан) в маршрутах ==')
from services import channel_routes as CHR  # noqa: E402

G = 700500
check(CHR.get_route(G, 'ban_appeal_channel') == 0, 'из коробки канал не задан')
check(CHR.set_route(G, 'ban_appeal_channel', 123456), 'канал сохраняется')
check(CHR.get_route(G, 'ban_appeal_channel') == 123456, 'канал читается back')
check(CHR.set_route(G, 'ban_appeal_channel', 0), '0 = очистить')
spec = CHR.spec_for('ban_appeal_channel')
check(spec is not None and spec['kind'] == 'native', 'спека маршрута на месте')
adapters = open(os.path.join(ROOT, 'web', 'routes', 'channel_settings.py'),
                encoding='utf-8').read()
check("'ban_appeal_channel': (CHR.get_route, CHR.set_route)" in adapters,
      'страница «Каналы и маршруты» подхватила маршрут')

print('== 3. Видимость /modpanel по ролям ==')
from services import staff_limits as SL  # noqa: E402

check(SL.role_scoped_actions(G, ()) is None, 'без своих настроек — видно всё (None)')
check(SL.role_scoped_actions(G, (601,)) is None, 'роль без настроек не режет меню')
SL.set_role_limits(G, 601, who='t', role_name='Мут-роль', mute=10)
check(SL.role_scoped_actions(G, (601,)) == {'mute'},
      'роль с лимитом мута → только mute')
SL.set_role_limits(G, 602, who='t', role_name='Бан-роль', ban=3)
check(SL.role_scoped_actions(G, (601, 602)) == {'mute', 'ban'},
      'две роли → объединение их действий')
SL.set_role_windows(G, 603, who='t', role_name='Окно-роль', clear=3600)
check(SL.role_scoped_actions(G, (603,)) == {'clear'}, 'окно тоже считается действием')
SL.set_role_durations(G, 604, who='t', role_name='Потолок-роль', mute=1800)
check(SL.role_scoped_actions(G, (604,)) == {'mute'}, 'потолок мута тоже открывает муты')

from cogs.moderation import actions_for_member, MODPANEL_ACTIONS  # noqa: E402


class _Role:
    def __init__(self, i):
        self.id = i


class _Guild:
    def __init__(self, i, owner=1):
        self.id = i
        self.owner_id = owner


class _Member:
    def __init__(self, i, roles, owner=False):
        self.id = i
        self.roles = roles
        self._owner = owner

    @property
    def guild(self):
        return None


g = _Guild(G)
# Строгая модель: видно только то, что владелец РАЗРЕШИЛ роли в панели.
# Discord-админ/владелец сервера прав не дают; владелец БОТА (OWNER_ID) — всё.
import os as _os  # noqa: E402
from services.permission_acl import set_action_rule, save_action_acl  # noqa: E402
_os.environ['OWNER_ID'] = '1'   # член с id=1 — владелец бота, видит всё
save_action_acl(G, {})
check(actions_for_member(g, _Member(1, [])) == MODPANEL_ACTIONS,
      'владелец БОТА (OWNER_ID) видит все действия')
# Без единого разрешения модератор не видит ничего (default-deny).
check(actions_for_member(g, _Member(77, [_Role(G), _Role(601)])) == [],
      'модератор без выданных разрешений не видит ни одного действия')

# Разрешаем ролям действия (как владелец в панели) — ЛИМИТЫ остаются вторым,
# пересекающим фильтром: мут-роль (лимит на мут) + разрешения mute/vmute/timeout
# видит мут-семейство; бан срезан лимитом мута.
set_action_rule(G, 'mute', [601, 604])
set_action_rule(G, 'vmute', [601, 604])
set_action_rule(G, 'timeout', [601, 604])
set_action_rule(G, 'ban', [601, 602])
set_action_rule(G, 'purge', [603])
m_mute = actions_for_member(g, _Member(7, [_Role(G), _Role(601)]))
check([a[0] for a in m_mute] == ['timeout', 'mute_chat', 'vmute'],
      f'мут-роль: лимит мута ∩ разрешения = только муты: {[a[0] for a in m_mute]}')
m_ban = actions_for_member(g, _Member(8, [_Role(602)]))
check([a[0] for a in m_ban] == ['ban'], f'бан-роль видит только бан: {[a[0] for a in m_ban]}')
m_none = actions_for_member(g, _Member(9, [_Role(603)]))
check([a[0] for a in m_none] == ['clear'], 'роль с окном чистки видит только чистку')
# роль без настроек лимитов и БЕЗ разрешений — ничего (default-deny)
m_free = actions_for_member(g, _Member(10, [_Role(699)]))
check(m_free == [], 'роль без настроек и без разрешений — не видит ничего')
save_action_acl(G, {})
_os.environ.pop('OWNER_ID', None)

print('== 4. «Бан» живьём: без канала — отказ, с каналом — изоляция ==')


class _Ch:
    def __init__(self, i):
        self.id = i
        self.mention = f'<#{i}>'
        self.overwrites = {}

    async def set_permissions(self, user, overwrite=None):
        self.overwrites[user.id] = overwrite


TID = 999000000000000999


class _Target:
    """«Нарушитель» — резолвится через guild.members."""

    id = TID
    name = 'BadGuy'
    display_name = 'BadGuy'
    bot = False
    mention = f'<@{TID}>'

    def __str__(self):
        return 'BadGuy'


class _GuildBig(_Guild):
    def __init__(self, i):
        super().__init__(i, owner=1)
        self.channels = [_Ch(100 + k) for k in range(5)]
        self.text_channels = self.channels
        self.members = [_Target()]

    def get_channel(self, cid):
        return next((c for c in self.channels if c.id == cid), None)


SENT = {}


class _Followup:
    async def send(self, embed=None, ephemeral=False, **kw):
        SENT['text'] = getattr(embed, 'description', str(embed)); SENT['done'] = True


class _Resp:
    def is_done(self):
        return False

    async def send_message(self, embed=None, ephemeral=False, **kw):
        SENT['text'] = getattr(embed, 'description', str(embed)); SENT['done'] = True


class _Inter:
    def __init__(self, user, guild):
        self.user = user
        self.guild = guild
        self.response = _Resp()
        self.followup = _Followup()


class _User:
    def __init__(self, i, roles=()):
        self.id = i
        self.roles = [_Role(r) for r in roles]
        self.bot = False

    def __str__(self):
        return 'Mod'


class _Tgt(str):
    def __new__(cls, i):
        return super().__new__(cls, str(i))

    @property
    def id(self):
        return int(self)


import cogs.moderation as M  # noqa: E402

mod = M.Moderation.__new__(M.Moderation)
gb = _GuildBig(G)
# у модератора права есть (без ролей-лимитов), «бан» без канала:
_inter = _Inter(_User(42, ()), gb)


async def _run(action, amount, proof='https://proof'):
    SENT.clear()
    try:
        await mod._execute_mod_action(_inter, action, _Tgt(TID), 'тест', amount,
                                      proof_link=proof)
        return SENT.get('done', False), (SENT.get('text', '') or '')
    except Exception as ex:                     # дошло до discord API
        return 'API', type(ex).__name__


ok, txt = asyncio.run(_run('ban', None))
check(ok is True and 'Настройки не завершены' in txt and 'канал апелляции' in txt,
      f'без канала — отказ с перечислением незавершённого ({txt[:80]}…)')
check('мут' not in txt.lower() or 'мут' not in txt.split('.')[0],
      'в отказе только НЕЗАВЕРШЁННОЕ, лишнего нет')

CHR.set_route(G, 'ban_appeal_channel', 102)     # канал №102 — уже существует
gb.channels = [_Ch(100), _Ch(101), _Ch(102), _Ch(103), _Ch(104)]
ok, txt = asyncio.run(_run('ban', None))
closed = sum(1 for c in gb.channels if TID in c.overwrites and c.id != 102)
iso_ch = gb.get_channel(102)
iso_open = TID in iso_ch.overwrites
check(ok in (True, 'API'), 'с настроенным каналом «бан» выполняется')
check(closed == 4, f'все каналы, кроме апелляции, закрыты ({closed} из 4)')
check(iso_open, 'в канале апелляции доступ открыт')

print('== 5. /апелляция — слеш-команда, ЛС ==')
import cogs.appeals as AP  # noqa: E402

check(hasattr(AP.Appeals, 'cmd_appeal'), 'метод команды на месте')
src = src_appeals
check("@commands.command" not in src and 'app_commands.command' in src,
      'в appeals больше нет префиксной команды')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
