# -*- coding: utf-8 -*-
"""AI-ассистент безопасен (заказ владельца 2026-08-26).

«ИИ не должен мочь давать муты никому» — проверяем железно:
- parse_ai_actions НЕИЗМЕННО игнорирует наказания (варн/тюрьма/роли/чистка)
  и вычищает их из текста; работает только эскалация к человеку;
- промпты не учат ИИ наказаниям (нет ACTION:WARN/JAIL в инструкциях);
- тикетный поток не исполняет наказаний и не слает кнопки «Мут/Ban»;
- отчёт модерации строится на реальном журнале, при пустом журнале —
  честный ответ без выдумок и без вызова модели.

Запуск: python3 tests/test_ai_safety.py
"""
import importlib
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_ai_safety_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DEMO_MODE'] = '1'

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


print('== 1. parse_ai_actions: наказания нейтрализованы ==')
from web.ai_helper import parse_ai_actions  # noqa: E402

r = parse_ai_actions(
    "Спокойно, разберёмся.\n"
    "ACTION:WARN:user_id=123:reason=оскорбление\n"
    "ACTION:JAIL:user_id=123:duration=60:reason=травля\n"
    "ACTION:ROLE_ASSIGN:user_id=123:role_id=456\n"
    "ACTION:DELETE_MESSAGES:channel_id=789:count=5\n"
    "ACTION:ESCALATE")
check(r['варн'] is None, 'варн игнорируется')
check(r['тюрьма'] is None, 'тюрьма (мут) игнорируется')
check(r['role_assign'] is None, 'выдача ролей игнорируется')
check(r['channel_redirect'] is None, 'перенаправления игнорируются')
check(r['delete_messages'] is None, 'чистка сообщений игнорируется')
check(r['escalate'] is True, 'эскалация к модератору работает')
check('ACTION:' not in r['cleaned_response'], 'служебные маркеры вычищены из текста')
check('разберёмся' in r['cleaned_response'], 'текст ответа сохранён')

r2 = parse_ai_actions('Обычный ответ без действий')
check(r2['escalate'] is False and r2['cleaned_response'] == 'Обычный ответ без действий',
      'чистый ответ проходит насквозь')

print('== 2. Промпты не учат наказаниям ==')
from web import ai_helper as AH  # noqa: E402

for cat in ('complaint', 'question', 'technical', 'other'):
    p = AH._get_prompt_by_category(cat)
    check('ACTION:WARN' not in p, f'{cat}: нет инструкции варнов')
    check('ACTION:JAIL' not in p, f'{cat}: нет инструкции мутов/тюрьмы')

src = open(os.path.join(ROOT, 'web', 'ai_helper.py'), encoding='utf-8').read()
check('информационный AI-ассистент' in src, 'роль ИИ — информационная, не «модератор»')
check('AI-ассистент и модератор' not in src, 'ИИ больше не называет себя модератором')
check('временный мут (timeout)' not in src, 'советов «применяй мут» больше нет')
check('НЕ выдумывай' in src, 'в системном промпте запрет выдумывать факты')

print('== 3. Тикетный поток не наказывает ==')
tsrc = open(os.path.join(ROOT, 'cogs', 'ticket.py'), encoding='utf-8').read()
check("actions .get ('jail')" not in tsrc, 'тикет не применяет тюрьму по команде ИИ')
check("actions .get ('warn')" not in tsrc, 'тикет не применяет варн по команде ИИ')
check('AI рекомендация' not in tsrc, 'кнопок «наказать по рекомендации ИИ» нет')
check("_assign_role (message .guild ,actions" not in tsrc, 'ИИ не выдаёт роли')

print('== 4. Отчёт модерации: только реальный журнал ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'

resp = client.post('/api/ai/mod-report')
body = resp.get_json()
check(resp.status_code == 200 and body.get('ok'), 'endpoint отвечает')
rep = body.get('report') or ''
check('нет ни одного действия' in rep, 'пустой журнал → честный «нет данных»')
check('17' not in rep, 'выдуманных цифр («17 случаев») больше нет')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
