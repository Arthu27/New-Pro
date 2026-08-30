# -*- coding: utf-8 -*-
"""Достижения временно выключены владельцем (заказ 2026-08-25).

«В боте есть достижение — убери их пока что, не нужны». Проверяем:
флаг, ког не грузится, пункт «Ачивки» исчез из меню, каталог не
показывает команды ачивок даже при EXTRA_COGS, код и данные живы
(вернуть — один флаг).

Запуск: python3 tests/test_achievements_off.py
"""
import asyncio
import importlib
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_achoff_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['EXTRA_COGS'] = 'achievements'   # как на VDS владельца: модуль «разбужен»

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


print('== 1. Флаг и ког ==')
from cogs import achievements as ACH  # noqa: E402

check(ACH.ACHIEVEMENTS_ENABLED is False,
      'достижения выключены «пока что» (ACHIEVEMENTS_ENABLED=False)')
check(len(ACH.ACHIEVEMENTS) > 5, 'каталог достижений и код на месте (не удалены)')


class _FakeBot:
    def __init__(self):
        self.cogs = {}

    def add_cog(self, cog):
        self.cogs[type(cog).__name__] = cog


bot = _FakeBot()
asyncio.run(ACH.setup(bot))
check(not bot.cogs, 'setup() не добавляет ког — бот живёт без достижений')

print('== 2. Меню панели ==')
import services.panel_menu as PM  # noqa: E402

paths = [p['path'] for g in PM.MENU for p in g['pages']]
check('/achievements' not in paths, 'пункт «Ачивки» исчез из меню панели')
check('/music' in paths and '/guardian' in paths, 'соседние пункты на месте')

print('== 3. Каталог команд (даже с EXTRA_COGS=achievements) ==')
from services import command_registry as CR  # noqa: E402

cat = CR.catalog(force=True)
ach_cmds = [c for c in cat['commands']
            if 'achiev' in str(c.get('module', '')).lower()
            or c.get('bare') in ('ачивки', 'ачивлидеры')]
check(not ach_cmds, 'команды ачивок не показываются в каталоге')
# После урезания слеш-меню (заказ владельца) в каталоге ровно 7 команд
# ядра (модерация, тикеты-панель, /play, /update, /afk) — они должны быть на месте.
# ticket-add/remove ушли в кнопки меню тикета (заказ 2026-08-29) — их тут нет.
check(cat['total'] >= 7, f'остальные команды на месте ({cat["total"]})')

print('== 4. Возврат одним флагом ==')
src = open(os.path.join(ROOT, 'cogs', 'achievements.py'), encoding='utf-8').read()
check('ACHIEVEMENTS_ENABLED = True' in src.replace('ACHIEVEMENTS_ENABLED = False',
                                                   '@@'),
      'включить обратно — один флаг, код целый')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
