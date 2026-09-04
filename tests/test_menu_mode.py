# -*- coding: utf-8 -*-
"""Режим слеш-меню: тумблер панели «Команды» важнее BOT_FULL из .env.

Заказ 30.08 «давай удалим все команды, оставим только это»: у владельца
в .env стоит BOT_FULL=1 (его прошлая настройка «покажи всё»), а хочет он
кураторские 7 команд. Править .env из панели нельзя — режим живёт в
data/menu_mode.json:

1. приоритет: тумблер (файл) → BOT_FULL из .env; файла нет — как раньше;
2. сжатие применяется К ЖИВОМУ БОТУ: бюджет чистит дерево, полный синк
   затирает списки Discord — в меню «/» остаётся ровно 7 команд, дублей
   нет, чужие серверы чистятся;
3. эндпоинт панели: доступ админам, сжатие уходит фоном (Flask-поток не
   блокируется), на «вернуть всё» честно отвечает «нужен перезапуск»;
4. каталог команд панели и кэш читают режим из ТОГО ЖЕ источника, что и
   бот (иначе каталог врал бы про полный состав при сжатом меню).

Запуск: python3 tests/test_menu_mode.py
"""
import asyncio
import json
import os
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix='hakumo_menu_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
# БЕЗ demo-режима: в демо панель сама входит владельцем (автовход),
# и проверку «анонима не пускают» честно не сделать
os.environ.pop('DEMO_MODE', None)
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['SECRET_KEY'] = 'test-secret'
# Сценарий владельца: .env «хочет всё», тумблер панели должен победить
os.environ['BOT_FULL'] = '1'

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


import discord  # noqa: E402
from discord import AppCommandType, Object  # noqa: E402
from discord.app_commands import command  # noqa: E402

from services import menu_mode as MM  # noqa: E402
import slash_budget  # noqa: E402


# ═══ A. Приоритет режима: тумблер → .env ═════════════════════════════════
print('== A. Приоритет: файл меню важнее BOT_FULL из .env ==')
check(not os.path.exists('data/menu_mode.json'), 'стартуем без файла-тумблера')
check(MM.is_full() is True, 'без файла действует .env: BOT_FULL=1 → полное')
check(slash_budget.full_menu_mode() is True,
      'slash_budget.full_menu_mode согласован с .env (делегирует)')

MM.set_full(False)
check(MM.is_full() is False,
      'ТУМБЛЕР ПОБЕЖДАЕТ: файл full=false при .env BOT_FULL=1 → кураторское')
check(slash_budget.full_menu_mode() is False,
      'бюджет видит то же (иначе каталог/меню разъехались бы)')
with open('data/menu_mode.json', encoding='utf-8') as fh:
    check(json.load(fh) == {'full': False},
          'файл-тумблер — валидный JSON с full:false')

MM.set_full(True)
check(MM.is_full() is True and slash_budget.full_menu_mode() is True,
      'тумблер full=true работает и при пустом BOT_FULL в .env')

# битый файл — честный откат к .env, а не к тихому «полному»
with open('data/menu_mode.json', 'w', encoding='utf-8') as fh:
    fh.write('{битый json')
check(MM.is_full() is True,
      'битый файл игнорируется → режим из .env (BOT_FULL=1)')


# ═══ B. Бюджет сжимает дерево до кураторских 7 ═══════════════════════════
print('== B. Меню сжимается до 7 команд (настоящий CommandTree) ==')


class Recorder:
    """HTTP-мок: bulk-upsert пишет журнал, fetch отвечает как Discord
    (что отправили — то и «лежит»; fetch_override — застаревшее состояние)."""

    @staticmethod
    def _ok(app_id, payload):
        out = []
        for i, p in enumerate(payload or []):
            d = dict(p, id=9000 + i, application_id=app_id)
            d.setdefault('description', '')
            d.setdefault('type', 1)
            out.append(d)
        return out

    def __init__(self):
        self.calls = []          # (scope, guild_id, [имена])
        self.global_payload = []             # что «лежит в Discord»
        self.guild_payload = {}              # {guild_id: payload}
        self.fetch_override = {}             # {'global': [имена], 777: [имена]}
                                             # симуляция ЗАСТАРЕВШЕГО Discord

    async def bulk_upsert_global_commands(self, app_id, payload=None):
        names = [p['name'] for p in (payload or [])]
        self.calls.append(('GLOBAL', None, names))
        self.global_payload = [dict(p) for p in (payload or [])]
        return self._ok(app_id, payload)

    async def bulk_upsert_guild_commands(self, app_id, guild_id, payload=None):
        names = [p['name'] for p in (payload or [])]
        self.calls.append(('GUILD', guild_id, names))
        self.guild_payload[guild_id] = [dict(p) for p in (payload or [])]
        return self._ok(app_id, payload)

    async def get_global_commands(self, app_id, *a, **kw):
        names = self.fetch_override.get('global')
        payload = ([{'name': n} for n in names] if names is not None
                   else self.global_payload)      # names≠None: «Discord не обновился»
        return self._ok(app_id, payload)

    async def get_guild_commands(self, app_id, guild_id, *a, **kw):
        names = self.fetch_override.get(guild_id)
        payload = ([{'name': n} for n in names] if names is not None
                   else self.guild_payload.get(guild_id, []))
        return self._ok(app_id, payload)

    def last(self, scope, gid=None):
        for s, g, names in reversed(self.calls):
            if s == scope and g == gid:
                return list(names)
        return []


class Bot:
    """Минимальный клиент discord.py: CommandTree настоящий, HTTP — мок."""

    def __init__(self):
        self.application_id = 42
        self.http = Recorder()
        self.loop = None
        self._connection = types.SimpleNamespace(_command_tree=None, _translator=None)
        self.tree = discord.app_commands.CommandTree(self)
        self._guilds = [types.SimpleNamespace(id=777), types.SimpleNamespace(id=888)]

    def get_guild(self, gid):
        return next((g for g in self._guilds if g.id == gid), None)

    @property
    def guilds(self):
        return list(self._guilds)


async def _cb(interaction):
    pass


def mk(name, keep_global=False):
    extras = {'keep_global': True} if keep_global else {}
    return command(name=name, description=f'cmd {name}', extras=extras)(_cb)


def build_bot():
    """Как боевой LEAN-профиль: 4 глобальных keep_global + 3 гильдовых
    + мусор, который должен исчезнуть из меню (но остаться на префиксе)."""
    bot = Bot()
    tree = bot.tree
    tree.add_command(mk('modpanel', keep_global=True))
    tree.add_command(mk('update', keep_global=True))
    tree.add_command(mk('апелляция', keep_global=True))
    tree.add_command(mk('warnings'))                       # мусор: глобальный
    tree.add_command(mk('report'))                        # жалобы — в белом списке
    tree.add_command(mk('my-violations'))                 # мои нарушения — в белом
    # verify-setup/afk-remove убраны из меню (настройка в панели / авто-AFK) —
    # теперь это мусор, бюджет обязан их вычистить как и warnings/backup.
    tree.add_command(mk('verify-setup'), guild=Object(777))
    for n in ('afk', 'afk-remove', 'backup'):
        tree.add_command(mk(n), guild=Object(777))         # backup/afk-remove — мусор
    return bot


# .env всё ещё BOT_FULL=1, тумблер уже вернули в False
MM.set_full(False)

bot1 = build_bot()
kept, pruned = slash_budget.apply_slash_budget(bot1.tree)
check(set(kept) == {'modpanel', 'update', 'апелляция',
                    'report', 'my-violations', 'afk'},
      f'в дереве остались ровно кураторские 6 ({len(kept)})')
check(set(pruned) == {'warnings', 'backup', 'afk-remove', 'verify-setup'},
      f'мусор убран из меню, но жив на префиксе ({sorted(pruned)})')

from services import sync_filtered as SF  # noqa: E402

async def _run_b():
    await SF.full_sync(bot1)
    glob, guild = bot1.http.last('GLOBAL'), bot1.http.last('GUILD', 777)
    check(set(glob) == {'modpanel', 'update', 'апелляция'},
          f'глобальный список = 3 keep_global ({sorted(glob)})')
    check(set(guild) == {'afk', 'report', 'my-violations'},
          f'сервер 777 = гильдовые + глобальные НЕ-keep ({sorted(guild)})')
    check(set(glob) & set(guild) == set(), 'глобаль∩гильдия пусто — дублей нет')
    check(bot1.http.last('GUILD', 888) == [], 'чужой сервер 888 очищен')
    check('warnings' not in glob + guild and 'backup' not in glob + guild,
          'мусор ни в один список не попал')

asyncio.run(_run_b())


# ═══ C. Живое применение кнопкой (menu_mode.apply_to_bot) ════════════════
print('== C. Кнопка панели применяет режим к живому боту ==')
bot2 = build_bot()          # свежий бот с мусором, режим уже кураторский

async def _run_c():
    ok, kept2, pruned2 = await MM.apply_to_bot(bot2)
    check(ok is True, 'apply_to_bot отработал')
    check(set(kept2) == {'modpanel', 'update', 'апелляция',
                          'report', 'my-violations', 'afk'},
          'бюджет внутри apply_to_bot сжал дерево до 6')
    check(set(pruned2) == {'warnings', 'backup', 'afk-remove', 'verify-setup'},
          'мусор вынесен из меню')
    glob2, guild2 = bot2.http.last('GLOBAL'), bot2.http.last('GUILD', 777)
    check(set(glob2) == {'modpanel', 'update', 'апелляция'}
          and set(guild2) == {'afk', 'report', 'my-violations'},
          'синк внутри apply_to_bot доставил те же списки в Discord')
    with open('data/sync_last.json', encoding='utf-8') as fh:
        verdict = json.load(fh).get('verify', '')
    check(verdict.startswith('ок:'),
          f'сверка с РЕАЛЬНЫМ Discord записана и чистая ({verdict})')

asyncio.run(_run_c())

# ─── C2. Discord «застрял» со старым мусором — сверка это ловит ────────
print('== C2. Сверка ловит застаревшее меню (жалоба «не удалились, дубли») ==')
bot3 = build_bot()

async def _run_c2():
    bot3.http.fetch_override[777] = ['afk', 'afk-remove',
                                     'backup', 'warnings', 'апелляция']
    await MM.apply_to_bot(bot3)
    with open('data/sync_last.json', encoding='utf-8') as fh:
        verdict2 = json.load(fh).get('verify', '')
    check(verdict2.startswith('РАСХОЖДЕНИЯ:'),
          f'застаревший мусор пойман сверкой ({verdict2[:80]}…)')
    check('лишние' in verdict2 and 'backup' in verdict2,
          'сверка называет ЛИШНИЕ команды по именам')
    check('дубли глобальных' in verdict2 and 'апелляция' in verdict2,
          'сверка называет гильдейские КОПИИ глобальных (источник дублей)')
    syncs = sum(1 for s_, g_, n_ in bot3.http.calls if s_ == 'GUILD' and n_)
    check(syncs >= 2, f'при расхождении сделан ПОВТОРНЫЙ синк ({syncs} guild-вызовов)')

asyncio.run(_run_c2())


# ═══ D. Панель: эндпоинт, доступы, страница ══════════════════════════════
print('== D. Панель: эндпоинт /api/commands/menu-mode ==')
from web.app import app as _flask_app  # noqa: E402

client = _flask_app.test_client()


def login_as(role):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'MenuModeTest'
        s['role'] = role


check('/api/commands/menu-mode' in {str(r) for r in _flask_app.url_map.iter_rules()},
      'роут зарегистрирован в приложении')

with client.session_transaction() as s:
    s.clear()
r = client.get('/api/commands/menu-mode')
check(r.status_code in (302, 401, 403), f'без логина закрыт ({r.status_code})')

login_as('uye')
check(client.get('/api/commands/menu-mode').status_code in (302, 403),
      'участника uye не пускают')

login_as('mod')
check(client.get('/api/commands/menu-mode').status_code in (302, 403),
      'модератора не пускают (только admin/owner)')

login_as('owner')
r = client.get('/api/commands/menu-mode')
d = r.get_json()
check(r.status_code == 200 and d.get('success') and d.get('full') is False,
      f'owner видит режим: тумблер false при .env BOT_FULL=1 ({d})')

r = client.post('/api/commands/menu-mode', json={})
check(r.status_code == 400, 'POST без параметра full → 400')

r = client.post('/api/commands/menu-mode', json={'full': True})
d = r.get_json()
check(d.get('success') and d.get('full') is True and d.get('restart_needed') is True,
      'включение полного меню честно просит перезапуск')

r = client.post('/api/commands/menu-mode', json={'full': False})
d = r.get_json()
check(d.get('success') and d.get('full') is False,
      'сжатие меню записалось (бот офлайн в тесте — применится при запуске)')
check(d.get('applied_live') is False,
      'без живого бота ничего не «применяем» фоном')

page = client.get('/commands').get_data(as_text=True)
check('id="menuModeBox"' in page and 'id="menuModeBtn"' in page,
      'страница «Команды»: баннер режима и кнопка на месте')
check('Сжать до 7' in page and 'menu-mode' in page,
      'баннер зовёт в API и говорит по-русски')

login_as('uye')
page_u = client.get('/commands').get_data(as_text=True)
check('menuModeBox' not in page_u,
      'участнику баннер режима не показываем (только admin/owner)')


# ═══ E. Каталог и кэш читают режим из одного источника ═══════════════════
print('== E. Каталог команд: единый источник режима ==')
src_cr = open(os.path.join(ROOT, 'services', 'command_registry.py'),
              encoding='utf-8').read()
check('full_requested = bool(full_menu_mode())' in src_cr,
      'каталог берёт режим из full_menu_mode (тумблер→.env, как бот)')
# прямой читок BOT_FULL разрешён ТОЛЬКО как аварийный fallback (2 ветки
# except: фильтр честности + ключ кэша). Появится третий — источник разъехал
_env_reads = src_cr.count("os.environ.get('BOT_FULL'")
check(_env_reads == 2,
      f'прямой читок BOT_FULL — только в fallback ({_env_reads} шт., ожидали 2)')
check('full_menu_mode' in src_cr,
      'каталог спрашивает full_menu_mode (тумблер→.env, как бот)')
check("'menu:'" in src_cr, 'ключ кэша каталога чувствителен к режиму меню')

src_bs = open(os.path.join(ROOT, 'web', 'templates', 'bot_stats.html'),
              encoding='utf-8').read()
check('Проверка меню после сжатия' in src_bs and 'РАСХОЖДЕНИЯ' in src_bs,
      'панель «Статистика» показывает итог сверки (ок/РАСХОЖДЕНИЯ)')
check('failed-global-clear' in src_bs,
      'панель честно предупреждает о неудавшейся глобальной очистке')

src_cp = open(os.path.join(ROOT, 'web', 'routes', 'commands_panel.py'),
              encoding='utf-8').read()
check("role_required('admin')" in src_cp.split('/api/commands/menu-mode')[1].split('def ')[0],
      'эндпоинт режима — только admin+')
check('run_coroutine_threadsafe' in src_cp,
      'сжатие уходит в цикл бота фоном (Flask-поток не блокируется)')

print()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
