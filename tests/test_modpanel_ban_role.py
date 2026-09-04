# -*- coding: utf-8 -*-
"""Бан-роль без «Бан участников» + выбор цели без повторного ника.

Заказы владельца 2026-09-04:
1. «почему боту нужно разрешение на бан участников, если он просто должен
   дать роль бана — с сервера выкидывать не надо». Проверяем: бан-конвейер
   НИГДЕ не зовёт guild.ban и не требует ban_members; нужен только
   manage_roles (роль + канал апелляции).
2. «выбрал участника — после этого просит ник ещё раз, убери». Проверяем:
   модалка действия, открытая после выбора мышкой, НЕ содержит поля цели;
   цель берётся из выбора; при ручном пути поле остаётся.

Запуск: python3 tests/test_modpanel_ban_role.py
"""
import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace as NS

os.environ['DB_PATH'] = os.path.join(tempfile.mkdtemp(prefix='br_db_'), 'bot.db')
os.chdir(tempfile.mkdtemp(prefix='br_ws_'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.makedirs('data', exist_ok=True)

from cogs import moderation as M

PASS = 0
FAIL = 0


def check(ok, label, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


print('== 1. Бан = роль, не Discord-бан ==')
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'cogs', 'moderation.py'), encoding='utf-8').read()
check("'ban': ('manage_roles'" in src and "'ban': ('ban_members'" not in src,
      'бан требует manage_roles, ban_members из предпроверки УБРАН')
# в ветке бана нет guild.ban(
_ban_branch = src[src.index('if action =="ban"'):src.index('elif action =="kick"')]
check('.ban (' not in _ban_branch.replace('add_roles', '') and 'guild .ban (' not in _ban_branch,
      'ветка бана не вызывает guild.ban (участник остаётся на сервере)')
check('add_roles (_brole' in _ban_branch.replace(' ', '') or 'add_roles' in _ban_branch,
      'ветка бана выдаёт роль бана')

print('== 2. Цель без повторного вопроса ==')
cog = M.Moderation(bot=None)
modal = M.ModActionModal(cog, 'ban', guild=NS(id=777), prefill_target='12345678901234567')
check(modal.fixed_target_id == '12345678901234567',
      'выбранная мышкой цель зафиксирована в модалке')
check(not hasattr(modal, 'target'),
      'поле «Цель» в модалке ОТСУТСТВУЕТ, когда участник выбран мышкой')
modal2 = M.ModActionModal(cog, 'ban', guild=NS(id=777), prefill_target='')
check(hasattr(modal2, 'target'),
      'ручной путь: поле цели на месте (выбор мышкой не обязателен)')
check(modal2.fixed_target_id is None, 'ручной путь: fixed-цели нет')

print('== 3. Префлайт: бан не требует Discord-прав бота ==')


class _Role:
    def __init__(self, name):
        self.name = name

    def __ge__(self, other):
        return False


me = NS(top_role=_Role('Бот'), guild_permissions=NS(
    manage_roles=True, ban_members=False, moderate_members=False))
user = NS(id=300, top_role=_Role('Участник'))
guild = NS(id=777, owner_id=42, me=me)
run = asyncio.new_event_loop()
_reason = run.run_until_complete(cog.preflight_reason(guild, user, 'ban'))
check(_reason is None,
      'без ban_members бан проходит предпроверку (нужен только manage_roles)',
      f'→ {_reason}')
me2 = NS(top_role=_Role('Бот'),
         guild_permissions=NS(manage_roles=False, ban_members=False,
                              moderate_members=False))
_reason2 = run.run_until_complete(
    cog.preflight_reason(NS(id=777, owner_id=42, me=me2), user, 'ban'))
check(_reason2 is not None and 'Управление ролями' in _reason2,
      'без manage_roles — понятная подсказка про роли, не про «Бан участников»',
      f'→ {_reason2}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
