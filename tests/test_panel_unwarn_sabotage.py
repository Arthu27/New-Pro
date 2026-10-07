# -*- coding: utf-8 -*-
"""Панель: снять варн/бан + саботаж owner + без заглушки AI."""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_pus_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath('data/bot.db')

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== AI: без надписи PANEL-REMOVED ==')
ai = open(os.path.join(ROOT, 'cogs', 'ai_chat.py'), encoding='utf-8').read()
check('PANEL-REMOVED' not in ai,
      'ai_chat больше не пишет docs/PANEL-REMOVED.md в чат')
check("return ''" in ai or 'return ""' in ai,
      'без ai_helper — пустой ответ')
check('if not (answer or' in ai or "if not answer" in ai,
      'пустой ответ не уходит в Discord')

print('== панель: unwarn / unban ==')
app = open(os.path.join(ROOT, 'web', 'app.py'), encoding='utf-8').read()
check("'unwarn'" in app and "'unban'" in app,
      'ROLE_PUNISH / api_punish знают unwarn и unban')
check("Снять варн" in app and "Снять бан" in app,
      'подписи «Снять варн» / «Снять бан»')
check('remove_last_warning' in app, 'api_punish зовёт remove_last_warning')
mem = open(os.path.join(ROOT, 'web', 'templates', 'member.html'),
           encoding='utf-8').read()
pun = open(os.path.join(ROOT, 'web', 'templates', '_punish.html'),
           encoding='utf-8').read()
check('punish_actions' in mem and 'punish-btn' in mem,
      'профиль показывает кнопки мер')
check('punish-row-lab--lift' in pun and 'Снять' in pun and 'unwarn' in pun,
      'диалог: отдельный ряд «Снять» с unwarn/unban')
check('isLift' in pun and "unban: 'снять бан" in pun,
      'снятие без правила, подпись понятная')

print('== антикраш: саботаж owner ==')
ac = open(os.path.join(ROOT, 'web', 'templates', 'anticrash.html'),
          encoding='utf-8').read()
check('Саботаж' in ac and 'bot_action' in ac,
      'блок «Саботаж · боты-нарушители» на Антикраше')
check('bot_whitelist_users' in ac and 'bot_whitelist_roles' in ac,
      'белый список кто может звать ботов')
check("key == 'bot_action'" in app and 'bot_whitelist_users' in app,
      'POST /anticrash сохраняет bot_action и whitelist')
check('Антикраш · Саботаж' in app, 'пункт меню для owner')

print(f'\n{PASS} passed, {FAIL} failed')
sys.exit(1 if FAIL else 0)
