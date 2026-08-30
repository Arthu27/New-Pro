# -*- coding: utf-8 -*-
"""Апелляции без ID сервера (заказ, пункт 3).

- /апелляция больше НЕ спрашивает сервер: параметр один — необязательный
  текст; без текста открывается форма (AppealModal).
- Главный сервер берётся из конфигурации (Config.MAIN_GUILD_ID); fallback —
  единственный сервер бота; иначе None (вежливый отказ).
- _is_banned видит ОБЕ механики бана: настоящий Discord-ban и панельную
  изоляцию (участник на сервере с ролью «бан» из punish_roles) — никакого
  ложного «вы не в бане».
- В коде не осталось вьюшек выбора сервера; веб-панель апелляций замкнута на
  active_guild_id и не содержит поля сервера.

Запуск: python3 tests/test_appeals_guild.py
"""
import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

_TMP = tempfile.mkdtemp(prefix='hakumo_appeals_guild_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
# MAIN_GUILD_ID читается Config при загрузке модуля — ставим ДО импорта кодов
os.environ['MAIN_GUILD_ID'] = '777'

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

import cogs.appeals as A  # noqa: E402
from cogs.appeals import Appeals, AppealModal  # noqa: E402
from services import punish_roles as PR  # noqa: E402

PR.set_roles(777, ban=888)


def _not_found():
    resp = NS(status=404, reason='nf', url='', headers={}, history=None, text='x')
    return discord.NotFound(resp, 'no ban')


def _forbidden():
    resp = NS(status=403, reason='fo', url='', headers={}, history=None, text='x')
    return discord.Forbidden(resp, 'no perm')


class _Resp:
    def __init__(self):
        self.sent = []

    async def send_message(self, content=None, embed=None, ephemeral=False, view=None):
        self.sent.append(('msg', str(content or ''), ephemeral))

    async def send_modal(self, modal):
        self.sent.append(('modal', type(modal).__name__))


async def _run():
    cog = Appeals.__new__(Appeals)
    role = NS(id=888)
    banned_member = NS(id=42, roles=[role])
    clean_member = NS(id=43, roles=[])

    # ── _is_banned: обе механики ─────────────────────────────────────────
    g = NS(get_member=lambda uid: banned_member, id=777)
    g.fetch_ban = AsyncMock(side_effect=_not_found())
    check(await cog._is_banned(g, banned_member) is True,
          'панельная изоляция (роль «бан») засчитывается как бан')

    g = NS(get_member=lambda uid: clean_member, id=777)
    g.fetch_ban = AsyncMock(return_value=NS(user=43))
    check(await cog._is_banned(g, clean_member) is True,
          'настоящий Discord-бан засчитывается (без роли)')

    g = NS(get_member=lambda uid: clean_member, id=777)
    g.fetch_ban = AsyncMock(side_effect=_not_found())
    check(await cog._is_banned(g, clean_member) is False,
          'чистый участник — ложного «в бане» нет')

    g = NS(get_member=lambda uid: clean_member, id=777)
    g.fetch_ban = AsyncMock(side_effect=_forbidden())
    check(await cog._is_banned(g, clean_member) is True,
          'недоступный ban-check → консервативное True (как раньше)')

    # ── _main_guild: источник сервера ────────────────────────────────────
    cog.bot = NS(get_guild=lambda gid: NS(id=gid) if gid == 777 else None,
                 guilds=[NS(id=777)])
    check(getattr(cog._main_guild(), 'id', None) == 777,
          'сервер берётся из Config.MAIN_GUILD_ID без вопросов')

    import config as C
    keep = C.Config.MAIN_GUILD_ID
    try:
        C.Config.MAIN_GUILD_ID = 0
        cog.bot = NS(get_guild=lambda gid: None, guilds=[NS(id=999)])
        check(getattr(cog._main_guild(), 'id', None) == 999,
              'без конфига — единственный сервер бота как fallback')
        cog.bot = NS(get_guild=lambda gid: None, guilds=[NS(id=1), NS(id=2)])
        check(cog._main_guild() is None,
              'без конфига и при нескольких серверах — None (вежливый отказ)')
    finally:
        C.Config.MAIN_GUILD_ID = keep

    # ── cmd_appeal: поведение команды ────────────────────────────────────
    cog2 = Appeals.__new__(Appeals)

    resp = _Resp()
    inter = NS(guild=NS(id=1), response=resp)
    await Appeals.cmd_appeal.callback(cog2, inter, текст='')
    check(resp.sent and resp.sent[0][0] == 'msg' and resp.sent[0][2] is True,
          'в канале сервера — вежливая подсказка про ЛС (ephemeral)')
    check('сервер' not in resp.sent[0][1].lower() or 'ID' not in resp.sent[0][1],
          'подсказка не просит никакой ID сервера')

    g4 = NS(get_member=lambda uid: banned_member, id=777, name='Тест')
    g4.fetch_ban = AsyncMock(side_effect=_not_found())
    cog2.bot = NS(get_guild=lambda gid: g4 if gid == 777 else None, guilds=[g4])
    resp = _Resp()
    inter = NS(guild=None, user=banned_member, response=resp, client=NS())
    await Appeals.cmd_appeal.callback(cog2, inter, текст='')
    check(resp.sent == [('modal', 'AppealModal')],
          'ЛС забаненного без текста — сразу форма (ни одного вопроса)')

    g5 = NS(get_member=lambda uid: clean_member, id=777, name='Тест')
    g5.fetch_ban = AsyncMock(side_effect=_not_found())
    cog2.bot = NS(get_guild=lambda gid: g5 if gid == 777 else None, guilds=[g5])
    resp = _Resp()
    inter = NS(guild=None, user=clean_member, response=resp, client=NS())
    await Appeals.cmd_appeal.callback(cog2, inter, текст='любой текст')
    check(resp.sent and 'не забанены' in resp.sent[0][1],
          'ЛС чистого участника — честное «апелляция не нужна», без шума')

    # без конфига и при >1 сервере — вежливый отказ
    try:
        C.Config.MAIN_GUILD_ID = 0
        cog2.bot = NS(get_guild=lambda gid: None, guilds=[NS(id=1), NS(id=2)])
        resp = _Resp()
        inter = NS(guild=None, user=banned_member, response=resp, client=NS())
        await Appeals.cmd_appeal.callback(cog2, inter, текст='текст апелляции 123')
        check(resp.sent and 'не настроен' in resp.sent[0][1],
              'бот не настроен — вежливый отказ вместо ошибки')
    finally:
        C.Config.MAIN_GUILD_ID = keep


print('== 1. Параметры команды ==')
cmd = Appeals.cmd_appeal
params = list(getattr(cmd, 'parameters', []) or [])
names = [getattr(p, 'name', '') for p in params]
check('сервер' not in names, 'параметра «сервер» больше нет вообще')
check(names == ['текст'], 'единственный параметр — необязательный текст')
check(params and getattr(params[0], 'required', True) is False
      and getattr(params[0], 'default', None) == '',
      'текст необязателен (default "") → без аргументов откроется форма')
check('__discord_app_commands_base_description__' not in cmd.__dict__,
      'список описаний параметров не провис с «сервер»')

print('== 2. Код: поведение ==')
asyncio.run(_run())

print('== 3. Мёртвые вьюшки и панель ==')
check('AppealServerSelect' not in A.__dict__ and 'AppealViewParent' not in A.__dict__,
      'Select/View выбора сервера удалены из модуля полностью')
src = open(os.path.join(ROOT, 'cogs/appeals.py'), encoding='utf-8').read()
check('Выберите сервер' not in src and 'ID сервера' not in src,
      'ни одной просьбы ввести/выбрать сервер')
check('def _main_guild' in src and 'MAIN_GUILD_ID' in src,
      'сервер — из конфигурации (Config.MAIN_GUILD_ID)')
panel = open(os.path.join(ROOT, 'web/routes/appeals_panel.py'), encoding='utf-8').read()
check('active_guild_id()' in panel, 'API панели замкнут на главный сервер')
tpl = open(os.path.join(ROOT, 'web/templates/appeals.html'), encoding='utf-8').read()
check('ID сервера' not in tpl and 'guild-select' not in tpl,
      'в панели апелляций нет поля выбора/ввода сервера')
# Заказ 2026-08-29 «две апелляции»: серверная /appeal удалена — осталась
# одна глобальная /апелляция (работает в ЛС, сервер берётся из конфигурации).
rsrc = open(os.path.join(ROOT, 'cogs/reports.py'), encoding='utf-8').read()
check("name='appeal'" not in rsrc,
      'второй команды /appeal больше нет — апелляция одна')
check("name='апелляция'" in open(os.path.join(ROOT, 'cogs/appeals.py'),
                                  encoding='utf-8').read(),
      'глобальная /апелляция на месте (ЛС, сервер — из конфигурации)')
check('AppealModal' in dir(A), 'форма модального окна на месте')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
