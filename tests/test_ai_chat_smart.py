# -*- coding: utf-8 -*-
"""AI-чат снят с эксплуатации — проверяем, что он не грузится и не в панели.

Запуск: python3 tests/test_ai_chat_smart.py
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


print('== AI-чат retired ==')
from cogs_policy import (  # noqa: E402
    RETIRED_COGS, AI_CHAT_COGS, AI_LEAN_COGS, LEAN_COGS, SLIM_COGS,
    select_from_environment,
)

check('ai_chat.py' in RETIRED_COGS, 'ai_chat.py в RETIRED_COGS')
check('ai_chat.py' not in AI_CHAT_COGS, 'AI_CHAT_COGS пуст (чат снят)')
check('ai_chat.py' not in AI_LEAN_COGS, 'AI_LEAN_COGS без ai_chat')
check('ai_moderation.py' in AI_LEAN_COGS, 'AI-модерация остаётся')
check('ai_chat.py' not in LEAN_COGS and 'ai_chat.py' not in SLIM_COGS,
      'чат не в LEAN/SLIM')

files = sorted(f for f in os.listdir(os.path.join(ROOT, 'cogs')) if f.endswith('.py'))
en, dis = select_from_environment(files, environ={})
check('ai_chat.py' not in en and 'ai_chat.py' in dis, 'LEAN не грузит ai_chat')
en_f, dis_f = select_from_environment(files, environ={'BOT_FULL': '1'})
check('ai_chat.py' not in en_f and 'ai_chat.py' in dis_f,
      'BOT_FULL тоже не грузит retired ai_chat')

menu = open(os.path.join(ROOT, 'services', 'panel_menu.py'), encoding='utf-8').read()
check("{'path': '/ai-chat'" not in menu, 'пункт меню /ai-chat убран')
check("'/ai-moderation'" in menu or "{'path': '/ai-moderation'" in menu,
      'AI Модерация в меню осталась')

rex = open(os.path.join(ROOT, 'web', 'routes_extra.py'), encoding='utf-8').read()
import_block = rex.split('from web.routes import')[-1].split(')')[0]
# Импорт имени модуля (не комментарий «AI-чат…»).
check('ai_chat,' not in import_block and not any(
    ln.strip() == 'ai_chat' or ln.strip().startswith('ai_chat,')
    for ln in import_block.splitlines()),
      'routes_extra не регистрирует ai_chat')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
