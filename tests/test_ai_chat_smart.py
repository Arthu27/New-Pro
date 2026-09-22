# -*- coding: utf-8 -*-
"""AI-чат: умный Discord + панель, канал 1312…, reply на бота.

Заказ:
1. Канал 1312434963941167134 — ключ AI-чата; reply на сообщения бота → ответ.
2. ИИ сильнее: низкая температура, large-модель, точные простые ответы.
3. Панель: настройки каналов + сильная модель (не small).
4. Баг-фикс: раньше AI_CHANNELS отсекались вторым гейтом (_dynamic only).

Запуск: python3 tests/test_ai_chat_smart.py
"""
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_ai_smart_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
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


print('== 1. Settings: канал по умолчанию ==')
from services import ai_chat_settings as S  # noqa: E402

cfg = S.load_settings()
check(1312434963941167134 in cfg['channels'],
      'дефолтный канал 1312434963941167134 в settings')
check(cfg['reply_to_bot'] is True and cfg['respond_all'] is True,
      'reply_to_bot + respond_all включены')
check(cfg['temperature'] <= 0.2, 'температура ≤0.2 для точности')
check(os.path.isfile('data/ai_chat_settings.json'),
      'файл data/ai_chat_settings.json создан')

cfg2 = dict(cfg)
cfg2['channels'] = [1312434963941167134, 999]
check(S.save_settings(cfg2) and 999 in S.load_settings()['channels'],
      'сохранение каналов работает')

print('== 2. Ког: гейт каналов + reply ==')
cog = open(os.path.join(ROOT, 'cogs', 'ai_chat.py'), encoding='utf-8').read()
check('_ai_allowed_channel_ids' in cog, 'хелпер разрешённых каналов есть')
check('is_reply_to_bot' in cog and 'reply_to_bot' in cog,
      'reply на сообщение бота обрабатывается')
check('отвечает на твоё предыдущее сообщение' in cog,
      'контекст предыдущего ответа бота подмешивается')
# Старый баг: is_allowed_ai только _dynamic_channels
check('message .channel .id in _dynamic_channels or \n            is_ticket_channel' not in cog
      and 'is_allowed_ai' not in cog,
      'баг «только dynamic» убран — settings-каналы работают')
check('msg .author .bot' in cog and '(бот)' in cog,
      'хроника канала включает сообщения бота')

print('== 3. Промпт и параметры силы ==')
import web.ai_helper as H  # noqa: E402

captured = {}


def fake_call(messages, max_tokens=2048, temperature=0.7, model=None):
    captured['msg'] = messages
    captured['max_tokens'] = max_tokens
    captured['temperature'] = temperature
    captured['model'] = model
    return ('ок', 'mistral-large-latest', {'provider': 'test'})


orig = H._call
H._call = fake_call
try:
    H.ai_assistant('сколько будет 2+2?', context={'guild_id': '777'})
finally:
    H._call = orig

sys_prompt = captured['msg'][0]['content']
check(captured['temperature'] == 0.18, 'дефолт temperature 0.18')
check(captured['max_tokens'] == 1600, 'дефолт max_tokens 1600')
for probe in ('ПРОСТЫЕ ВОПРОСЫ', 'не тупи', 'REPLY-ДИАЛОГ',
              'ошибка в простом факте', 'эксперт высшего класса'):
    check(probe.lower() in sys_prompt.lower() or probe in sys_prompt,
          f'промпт: {probe}')

H._call = fake_call
try:
    H.ai_assistant('тест', context={}, temperature=0.1, max_tokens=900,
                   model='mistral-large-latest')
finally:
    H._call = orig
check(captured['temperature'] == 0.1 and captured['max_tokens'] == 900
      and captured['model'] == 'mistral-large-latest',
      'параметры из настроек прокидываются в _call')

print('== 4. Панель: сильная модель + API настроек ==')
panel = open(os.path.join(ROOT, 'web', 'routes', 'ai_chat.py'),
             encoding='utf-8').read()
tpl = open(os.path.join(ROOT, 'web', 'templates', 'ai_chat_panel.html'),
           encoding='utf-8').read()
check("AI_PANEL_MODEL','mistral-large-latest'" in panel.replace(' ', ''),
      'панель по умолчанию mistral-large-latest')
check('/api/ai-chat/settings' in panel, 'API настроек AI-чата есть')
check('ai-channels' in tpl and '1312434963941167134' in tpl,
      'UI настроек каналов на странице AI Чат')
check('ai-settings-save' in tpl and 'loadSettings' in tpl,
      'сохранение настроек с панели')

print('== 5. DM по-прежнему выключен ==')
check('ИИ-чат теперь работает только на сервере' in cog, 'DM отказ сохранён')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
