# -*- coding: utf-8 -*-
"""AI-апгрейд: личка выключена, панель — слабая модель, чат прокачан.

Заказ владельца:
1. В личке (DM) ИИ не работает — только серверные каналы (перехват reply
   владельца и его операционные команды — это не ИИ-чат, они живы).
2. В панели — заведомо слабая (дешёвая) модель mistral-small-latest,
   переопределяется AI_PANEL_MODEL в .env; оба вызова _call её используют.
3. Серверный чат прокачан: детерминированная температура 0.25, полные
   ответы (1408 токенов), слепок сервера (каналы/роли/состав команды),
   договор «никогда не отказываться фразами про доступ к данным»,
   запрет выдумывать факты сервера сохранён.

Запуск: python3 tests/test_ai_dm_panel_upgrade.py
"""
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_aiup_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
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


print('== 1. Личка: ИИ выключен ==')
cog = open(os.path.join(ROOT, 'cogs', 'ai_chat.py'), encoding='utf-8').read()
flat = re.sub(r'\s+', '', cog)
check('ИИ-чат теперь работает только на сервере' in cog,
      'в DM уходит вежливое уведомление вместо ответа ИИ')
idx_dm = cog.find('if is_dm :\n            try :')
idx_gate = cog.find('if not (is_dm or is_ai_channel ):')
check(0 < idx_dm < idx_gate,
      'DM-барьер стоит ДО общего AI-ответа')
check('_detect_owner_intent' in cog and cog.find('_detect_owner_intent') < idx_dm,
      'операционные команды владельца в DM работают (не ИИ-чат)')
check("'[AI] DM notice Ошибки: {_dm_ex}'" in cog,
      'отказ в DM без молчаливого except (лог есть)')

print('== 2. Панель — слабая модель ==')
panel = open(os.path.join(ROOT, 'web', 'routes', 'ai_chat.py'),
             encoding='utf-8').read()
check("AI_PANEL_MODEL','mistral-small-latest'" in panel.replace(' ', ''),
      'дефолт панели — mistral-small-latest (дешёвая), через .env меняется')
check(panel.count('model =_AI_PANEL_MODEL') >= 2,
      'оба вызова _call панели идут со слабой моделью')
check('заведомо СЛАБАЯ' in panel, 'намерение задокументировано в коде')

print('== 3. Серверный чат прокачан ==')
captured = {}


def fake_call(messages, max_tokens=2048, temperature=0.7, model=None):
    captured['msg'] = messages
    captured['max_tokens'] = max_tokens
    captured['temperature'] = temperature
    captured['model'] = model
    return ('ок', 'mistral-large-latest', {'provider': 'test'})


import web.ai_helper as H  # noqa: E402
orig_call = H._call
H._call = fake_call
try:
    ans, hist, model, rate = H.ai_assistant(
        'какая погода сегодня?',
        context={
            'user_name': 'Вася',
            'user_id': '11',
            'guild_name': 'Hakumo Demo',
            'guild_id': '777',
            'member_count': 1024,
            'guild_owner': 'Кипарис',
            'staff_roles': [{'name': 'Модератор', 'members': ['Лина', 'Гост']}],
            'channels': ['#общее', '#оффтоп', '  Голос'],
            'roles': ['Админ', 'Хелпер', 'Участник'],
            'channel_context': [
                {'author': 'Люк', 'content': 'привет', 'timestamp': '12:00'},
                {'author': 'Лина', 'content': 'кто шарит по тикетам?',
                 'timestamp': '12:01'}],
            'recent_user_messages': [
                {'channel': 'общее', 'content': 'всем хай', 'timestamp': '11:50'},
                {'channel': 'оффтоп', 'content': 'мне бы роль', 'timestamp': '11:55'}],
            'asker_roles': ['Хелпер', 'Участник'],
            'user_interests': ['музыка', 'игры'],
        },
        history=[])
finally:
    H._call = orig_call

sys_prompt = captured['msg'][0]['content']
check(ans == 'ок' and hist[-1]['content'] == 'ок', 'ответ проходит сквозь')
check(captured['temperature'] == 0.25,
      'температура 0.25 — детерминированные ответы')
check(captured['max_tokens'] == 1408, 'полные ответы (1408 токенов)')
check(captured['model'] is None,
      'модель чата не задана жёстко — сильная дефолтная (large)')
for probe in ('эксперт высшего класса', 'рассудительный', 'на ЛЮБОЙ вопрос',
              '«у меня нет доступа к данным»', 'общие знания, логику',
              'НЕ выдумывай', 'что спросили — то и получи'):
    check(probe in sys_prompt, f'в системе есть: {probe}')
check('#общее' in sys_prompt and '  Голос' in sys_prompt,
      'каналы сервера в контексте')
check('Админ' in sys_prompt and 'Хелпер' in sys_prompt,
      'роли сервера в контексте')
check('Модератор: Лина, Гост' in sys_prompt, 'команда сервера в контексте')
check('Участников на сервере: 1024' in sys_prompt, 'счётчик участников в контексте')
check('Владелец сервера: Кипарис' in sys_prompt, 'владелец сервера в контексте')

print('== 3.1. Экспертиза и живой контекст ==')
for probe in ('МЕТОД РАБОТЫ', 'мысленно разбери вопрос',
              'ФОРМА ОТВЕТА', 'ФОРМАТ Discord', 'Сегодняшняя дата:',
              'РЕАЛЬНЫЕ слеш-команды', '/modpanel',
              '[12:00] Люк: привет', '[12:01] Лина: кто шарит по тикетам?',
              '[11:50] в #общее: всем хай', '[11:55] в #оффтоп: мне бы роль',
              'Хелпер', 'музыка'):
    check(probe in sys_prompt, f'умный движок: {probe}')
check('Роли спрашивающего: Хелпер, Участник' in sys_prompt,
      'роли спрашивающего в контексте')
for probe in ('ТОН: подстраивайся', 'шутят — ответь с лёгким юмором',
              'ЧЕСТНОСТЬ ТОЧНОСТИ', '«вероятнее всего»',
              'НЕ попугайничай'):
    check(probe in sys_prompt, f'ум: {probe}')

try:
    ans2, *_ = H. ai_assistant('кто в онлайне?', context={'guild_id': '777'})
    system2 = captured['msg'][0]['content']
except Exception as e:
    FAIL += 1
    print(f'  FAIL: ai_assistant падает без guild: {e}')

print('== 4. Сервер-статус для всех (ког) ==')
check("if guild and str (user_id )=='987430047889637426':" not in cog,
      'статус сервера не заперт на одного юзера')
check("context ['channels']=" in cog and "context ['roles']=" in cog,
      'ког кладёт каналы/роли в контекст')
check("context ['asker_roles']" in cog, 'ког кладёт роли спрашивающего')

print('== 5. Ког: упоминания читаемые, длинные ответы не падают ==')
import cogs.ai_chat as AC  # noqa: E402

class _M:
    def __init__(self, n): self.display_name = n
class _C:
    def __init__(self, n): self.name = n
class _R:
    def __init__(self, n): self.name = n
class _G:
    def get_member(self, i):
        return _M('Лина') if i == 111111111111111111 else None
    def get_channel(self, i):
        return _C('мод-лог') if i == 222222222222222222 else None
    def get_role(self, i):
        return _R('Админ') if i == 333333333333333333 else None

rr = AC._resolve_mentions(
    'глянь <#222222222222222222> и скажи <@111111111111111111> про <@&333333333333333333>',
    _G())
check(rr == 'глянь #мод-лог и скажи @Лина про @Админ',
      'упоминания → читаемые имена')
check(AC._resolve_mentions('просто текст без упоминаний', None) ==
      'просто текст без упоминаний', 'без guild/без < — как было')

long_text = 'один абзац.\n\n' + 'x' * 1980 + '\n\nфинал'
parts = AC._split_long(long_text)
check(all(len(x) <= 1900 for x in parts) and len(parts) >= 3,
      'сплиттер: все куски ≤1900, абзац внутри не крабится')
check(AC._split_long('коротко') == ['коротко'], 'короткое не трогаем')
check(AC._split_long(' '.join(['слово'] * 600)) and
      all(len(x) <= 1900 for x in AC._split_long(' '.join(['слово'] * 600))),
      'сплошной текст разрежется по словам')
check('_resolve_mentions (content ,message .guild )' in cog,
      'вопрос перед ИИ резолвит упоминания')
check('_split_long (answer )' in cog and "_resolve_mentions (msg .content" in cog,
      'отправка через сплиттер, хроника резолвится')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
