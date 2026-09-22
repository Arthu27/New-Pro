# -*- coding: utf-8 -*-
"""AI-чат (DM + панель) снят — регрессия: нет загрузки и нет маршрутов.

Запуск: python3 tests/test_ai_dm_panel_upgrade.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


print('== AI-чат: Discord + панель выключены ==')
from cogs_policy import RETIRED_COGS, select_cog_files  # noqa: E402

check(os.path.isfile(os.path.join(ROOT, 'cogs', 'ai_chat.py')),
      'файл кога ещё на диске (retired, не снесён)')
check('ai_chat.py' in RETIRED_COGS, 'в RETIRED_COGS')

en, gone = select_cog_files(['ai_chat.py', 'ai_moderation.py', 'help.py'], full=True)
check('ai_chat.py' in gone, 'даже BOT_FULL не грузит ai_chat')
check('ai_moderation.py' in en and 'help.py' in en, 'AI-мод и help живы')

menu = open(os.path.join(ROOT, 'services', 'panel_menu.py'), encoding='utf-8').read()
check("{'path': '/ai-chat'" not in menu, 'меню без /ai-chat')
check("'/ai-chat':" not in menu, 'PAGE_MIN_ROLE/PAGE_COGS без /ai-chat')

rex = open(os.path.join(ROOT, 'web', 'routes_extra.py'), encoding='utf-8').read()
import_block = rex.split('from web.routes import')[-1].split(')')[0]
check('ai_chat,' not in import_block and not any(
    ln.strip() == 'ai_chat' or ln.strip().startswith('ai_chat,')
    for ln in import_block.splitlines()),
      'панельные маршруты ai_chat не подключены')

app_src = open(os.path.join(ROOT, 'web', 'app.py'), encoding='utf-8').read()
dispatch = app_src.split('async def dispatch')[1].split('try')[0]
check('AIChat' not in dispatch and 'get_cog' not in dispatch,
      'voice-dispatch больше не зовёт AIChat cog')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
