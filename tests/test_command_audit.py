# -*- coding: utf-8 -*-
"""Команды должны отвечать и не падать: 3с-ack Discord, Snowflake-бан, срок 30 мин.

Заказ: «посмотри все команды бота чтобы ошибок не было».
KEEP_SLASH: modpanel, апелляция, update, afk, report, my-violations.

Запуск: python3 tests/test_command_audit.py
"""
import ast
import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

_TMP = tempfile.mkdtemp(prefix='hakumo_cmd_audit_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['MAIN_GUILD_ID'] = '777'

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


def _src(rel):
    return open(os.path.join(ROOT, rel), encoding='utf-8').read()


def _fn(src, name):
    i = src.index(f'async def {name}')
    nxt = src.find('\n    async def ', i + 1)
    nxt2 = src.find('\n    @', i + 20)
    cuts = [c for c in (nxt, nxt2) if c > i]
    j = min(cuts) if cuts else len(src)
    return src[i:j]


print('== 1. KEEP: первый ответ Discord до тяжёлой работы ==')
# /апелляции больше нет (владелец 2026-09-08: «она у нас в кнопке»):
# путь — кнопка в ЛС → модалка. Дисциплина ответов та же.
_ap_src = _src('cogs/appeals.py')
_modal = _ap_src[_ap_src.index('class AppealModal'):
                 _ap_src.index('class AppealChannelModal')]
check(_modal.find('response.defer') < _modal.find('_submit_appeal'),
      'модалка апелляции: defer до карточки и открытия канала')
_o = _ap_src.index('async def _open')
_open = _ap_src[_o:_o + 2000]
check('send_modal' in _open and '_is_banned' in _open,
      'кнопка в ЛС: бан-чек и сразу форма — ни одного лишнего вопроса')
check("не забанены" in _open
      and _open.find('_is_banned') < _open.find('send_modal'),
      'кнопка в ЛС: «не забанены» ДО открытия формы')

afk = _fn(_src('cogs/afk.py'), 'afk')
check(afk.find('response .defer') < afk.find('user .edit')
      or afk.find('response.defer') < afk.find('user.edit'),
      '/afk: defer до смены ника')
check('guild_id' in afk and 'личке' in afk,
      '/afk в ЛС — отказ, не падает на None')

mod = _fn(_src('cogs/moderation.py'), 'modpanel')
check('await _ack' in mod and mod.find('await _ack') < mod.find('actions_for_member'),
      '/modpanel: _ack до меню')

rep = _fn(_src('cogs/reports.py'), 'report_slash')
check(('response.defer' in rep or 'response.send_message' in rep)
      and (rep.find('response.defer') < rep.find('_open_ticket')
           if '_open_ticket' in rep else True),
      '/report: ack до открытия тикета')

viol = _fn(_src('cogs/reports.py'), 'my_violations_slash')
check(viol.find('guild_id is None') < viol.find('_cfg('),
      '/my-violations: в ЛС отказ до чтения нарушений')
check(viol.find('send_message') < viol.find('_violations_field'),
      '/my-violations: send до сборки поля')

upd = _fn(_src('cogs/diagnostics.py'), 'update')
check('defer' in upd and upd.find('_owner_only') < upd.find('defer'),
      '/update: проверка владельца, затем defer')

health = _fn(_src('cogs/diagnostics.py'), 'health_cmd')
check(health.find('response .defer') < health.find('get_health_snapshot')
      or health.find('response.defer') < health.find('get_health_snapshot'),
      '/health: defer до снимка')

print('== 2. Репорты: бан Snowflake, срок 30 минут ==')
rep_src = _src('cogs/reports.py')
check("guild.ban(int(" not in rep_src,
      'apply_verdict не зовёт guild.ban(int) — Discord ждёт Snowflake')
check('discord.Object(id=int(t[' in rep_src and "kind'] == 'ban'" in rep_src,
      'бан вердикта — discord.Object(id=...)')
dur = _fn(rep_src, 'choose') if 'async def choose' in rep_src else ''
# DurationSelectView.choose
i = rep_src.index('class DurationSelectView')
dur_cls = rep_src[i:rep_src.find('class ', i + 10) if 'class ' in rep_src[i+10:] else i+1200]
check('value=str(hours)' in dur_cls and 'int(hours)' not in dur_cls,
      'срок репорта: 30 минут = 0.5, не int(0.5)=0')

print('== 3. Живой вызов KEEP-команд ==')
import discord  # noqa: E402
from cogs.appeals import Appeals, AppealModal  # noqa: E402
from cogs.reports import Reports, DurationSelectView  # noqa: E402
from cogs.afk import AFK  # noqa: E402


class _Resp:
    def __init__(self):
        self.sent = []
        self.deferred = False
        self._done = False

    def is_done(self):
        return self._done

    async def send_message(self, content=None, embed=None, ephemeral=False, **kw):
        self._done = True
        self.sent.append(('msg', str(content or ''), ephemeral, embed))

    async def send_modal(self, modal):
        self._done = True
        self.sent.append(('modal', type(modal).__name__))

    async def defer(self, ephemeral=False, thinking=False):
        self.deferred = True
        self._done = True
        self.sent.append(('defer', ephemeral))


class _Follow:
    def __init__(self, resp):
        self.resp = resp

    async def send(self, content=None, embed=None, ephemeral=False, **kw):
        self.resp.sent.append(('followup', str(content or ''), ephemeral, embed))


async def _run():
    # модалка апелляции (кнопка в ЛС): defer, затем followup
    cog = Appeals.__new__(Appeals)
    user = NS(id=42, roles=[NS(id=888)])
    g = NS(id=777, name='Тест', get_member=lambda uid: user)
    cog._is_banned = AsyncMock(return_value=True)
    cog._main_guild = lambda: g
    cog._submit_appeal = AsyncMock(return_value=({'id': 9}, None))
    resp = _Resp()
    inter = NS(guild=None, user=user, response=resp, followup=_Follow(resp),
               client=NS())
    modal = AppealModal(cog, g)
    modal.text = NS(value='прошу разбанить')
    await modal.on_submit(inter)
    kinds = [x[0] for x in resp.sent]
    check(kinds[0] == 'defer', f'модалка: сначала defer ({kinds})')
    check('followup' in kinds, f'модалка: ответ через followup ({kinds})')
    check('msg' not in kinds, 'успешная апелляция не шлёт send_message после defer')

    # чистый участник: followup «не забанены» (модалка честно сделала defer)
    cog._is_banned = AsyncMock(return_value=False)
    resp2 = _Resp()
    inter2 = NS(guild=None, user=user, response=resp2, followup=_Follow(resp2),
                client=NS())
    modal2 = AppealModal(cog, g)
    modal2.text = NS(value='любой текст')
    await modal2.on_submit(inter2)
    check(resp2.sent and any(x[0] == 'followup' and 'не забанены' in str(x[1])
                             for x in resp2.sent),
          'чистый — честное «не забанены» через followup')

    # /my-violations в ЛС
    rcog = Reports.__new__(Reports)
    resp3 = _Resp()
    inter3 = NS(guild_id=None, guild=None, user=user, response=resp3)
    await Reports.my_violations_slash.callback(rcog, inter3)
    check(resp3.sent and 'сервере' in resp3.sent[0][1],
          '/my-violations в ЛС — отказ, не падает')

    # /afk в ЛС
    acog = AFK.__new__(AFK)
    acog._afk = {}
    resp4 = _Resp()
    user4 = NS(id=1, display_name='n', display_avatar=NS(url='http://x'))
    inter4 = NS(guild_id=None, user=user4, response=resp4, followup=_Follow(resp4))
    await AFK.afk.callback(acog, inter4, причина='AFK')
    check(resp4.sent and resp4.sent[0][0] == 'msg' and 'личке' in resp4.sent[0][1],
          '/afk в ЛС — отказ до edit ника')

    obj = discord.Object(id=1001)
    check(hasattr(obj, 'id') and obj.id == 1001,
          'discord.Object(id=) — валидный Snowflake для Guild.ban')
    try:
        int_is_snowflake = isinstance(1001, discord.abc.Snowflake)
    except TypeError:
        int_is_snowflake = False
    check(not int_is_snowflake,
          'голый int не Snowflake — guild.ban(int) в discord.py 2.7 падает')

    # DurationSelectView: 30 минут не схлопывается в 0
    view = DurationSelectView('mute')
    sel = next(c for c in view.children if isinstance(c, discord.ui.Select))
    vals = [o.value for o in sel.options]
    check('0.5' in vals, f'опция 30 минут = 0.5 часа ({vals})')
    check(vals.count('0') <= 1, f'нет двух value=0 из int(0.5) ({vals})')


asyncio.run(_run())

print('== 4. AST: у всех slash есть description, KEEP без дублей ==')
keep = {'modpanel', 'update', 'afk', 'report', 'my-violations'}  # 5: /апелляция убрана (владелец 2026-09-08)
seen = {}
bad = []
for rel in ('cogs/appeals.py', 'cogs/afk.py', 'cogs/reports.py',
            'cogs/moderation.py', 'cogs/diagnostics.py'):
    tree = ast.parse(_src(rel), filename=rel)
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            fn = dec.func
            if not (isinstance(fn, ast.Attribute) and fn.attr == 'command'):
                continue
            kw = {k.arg: k.value for k in dec.keywords}
            name = kw.get('name')
            desc = kw.get('description')
            n = name.value if isinstance(name, ast.Constant) else node.name
            d = desc.value if isinstance(desc, ast.Constant) else ''
            if n in keep:
                seen.setdefault(n, []).append(rel)
            if not str(d).strip():
                bad.append(f'{rel}:{n}')
check(not bad, f'KEEP/соседние slash с описанием ({bad})')
dups = {n: v for n, v in seen.items() if len(v) > 1}
check(not dups, f'KEEP-имена не дублируются ({dups})')
check(set(seen) >= keep, f'все KEEP найдены в исходниках ({sorted(set(keep)-set(seen))})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
