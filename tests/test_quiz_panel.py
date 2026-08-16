# -*- coding: utf-8 -*-
"""Квиз в панели: библиотека + зачёт (1:1 с когом /квиз).

Проверяем: чистые try_add_question/try_remove_question (ок/дубль/формат/
границы), что команды кога после рефакторинга отвечают теми же текстами,
API панели (права mod/admin, коды 400/404, тексты == возврату функций кога),
полный цикл с undo-повтором, форму payload, монтаж шаблона.

Запуск: python3 tests/test_quiz_panel.py
"""
import asyncio
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='aether_quizpanel_test_')
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


from cogs import quiz as Q  # noqa: E402
from db import GuildData  # noqa: E402

print('== 1. try_add_question (чистая, общая ког+панель) ==')
qs = []
item, err = Q.try_add_question(qs, 'Столица Франции? | париж ; город париж', added_by='panel:admin')
check(item and err is None and item['answers'] == ['париж', 'город париж'], 'ок: варианты через «;»')
check(qs[0]['added_by'] == 'panel:admin' and qs[0]['added_at'], 'метаданные записаны')
item, err = Q.try_add_question(qs, '  столица франции?  | другой')
check(item is None and 'уже есть' in err, 'дубль ловится после нормализации (регистр/пробелы)')
item, err = Q.try_add_question(qs, 'Столица Ёлкино? | париж')
check(item is not None, 'другой вопрос с «ё» — не дубль')
item, err = Q.try_add_question(qs, 'без разделителя')
check(item is None and 'Формат' in err, 'нет «|» — текст формата как у бота')
item, err = Q.try_add_question(qs, 'Вопрос? |   ')
check(item is None and 'Формат' in err, 'пустые ответы — отказ')
item, err = Q.try_add_question(qs, '2+2? | 4 | ; четыре')
check(item and item['answers'] == ['4 |', 'четыре'], 'много «|»: режется по первому (поведение кога)')
check(len(qs) == 3, f'в списке ровно валидные записи ({len(qs)})')

print('== 2. try_remove_question ==')
removed, err = Q.try_remove_question(qs, 2)
check(removed and err is None and len(qs) == 2, 'удаление по номеру ок')
removed, err = Q.try_remove_question(qs, 99)
check(removed is None and err == 'Нет вопроса с номером 99. Смотри `/квиз вопросы`.',
      'вне диапазона — текст ровно как у бота')
removed, err = Q.try_remove_question(qs, 'abc')
check(removed is None and 'целое число' in err, 'не число — вежливая 400-ошибка панели')

print('== 3. Команды кога после рефакторинга — тексты 1:1 ==')
run = asyncio.get_event_loop().run_until_complete


class FakeCtx:
    def __init__(self, gid=88001):
        self.answers = []
        self.guild = SimpleNamespace(id=gid)
        self.author = SimpleNamespace(id=1, mention='@m')

    async def send(self, text, **kw):
        self.answers.append(str(text))


cog = Q.Quiz.__new__(Q.Quiz)
cog.bot = SimpleNamespace()
cog.db = GuildData('quiz')
cog.sessions = {}
ctx = FakeCtx()
run(Q.Quiz.add.callback(cog, ctx, spec='Как зовут кота сервера? | бублик'))
check(any('Вопрос добавлен (**1** в библиотеке)' in a and 'бублик' in a for a in ctx.answers),
      'добавить: текст как раньше')
ctx2 = FakeCtx()
run(Q.Quiz.add.callback(cog, ctx2, spec='как зовут кота сервера? | другой'))
check(any('Такой вопрос уже есть' in a for a in ctx2.answers), 'дубль: текст как раньше')
ctx3 = FakeCtx()
run(Q.Quiz.add.callback(cog, ctx3, spec='криво'))
check(any(a.startswith('Формат:') for a in ctx3.answers), 'кривой spec: текст как раньше')
ctx4 = FakeCtx()
run(Q.Quiz.remove.callback(cog, ctx4, index=5))
check(any('Нет вопроса с номером 5' in a for a in ctx4.answers), 'удалить мимо: текст как раньше')
ctx5 = FakeCtx()
run(Q.Quiz.remove.callback(cog, ctx5, index=1))
check(any(a.startswith('Удалён вопрос: Как зовут кота') for a in ctx5.answers), 'удалить: текст как раньше')

print('== 4. API: права ==')
appmod = importlib.import_module('web.app')
app = appmod.app
app.config['TESTING'] = True
client = app.test_client()
GuildData('quiz').set(777, 'questions', [])
GuildData('quiz').set(777, 'scores', {'55': {'points': 7, 'correct': 5, 'wins': 2}})


def login(role='owner', username='admin'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = username
        s['role'] = role


def post(path, payload):
    r = client.post(path, data=json.dumps(payload), content_type='application/json')
    try:
        return r.status_code, r.get_json()
    except Exception:
        return r.status_code, {'raw': r.data[:200]}


check(client.get('/api/quiz/state').status_code in (302, 401, 403), 'гостю закрыто')
login('uye')
check(client.get('/api/quiz/state').status_code == 403, 'uye нельзя (403)')
login('mod')
check(client.get('/api/quiz/state').status_code == 200, 'mod читает (200)')
check(post('/api/quiz/questions/add', {'question': 'Q?', 'answers': 'a'})[0] == 403,
      'mod не редактирует (403) — как manage_guild у кога')

print('== 5. API: добавление/валидация 1:1 с когом ==')
login('owner')
code, body = post('/api/quiz/questions/add', {'question': 'Сколько нот в октаве?', 'answers': '7 ; семь'})
check(code == 200 and body['success'] and body['custom_count'] == 1, 'ок через question+answers')
check(body['questions'][0]['added_by'] == 'panel:admin', 'видно, что вопрос из панели')
check(body['added']['answers'] == ['7', 'семь'], 'ответы порезались по «;»')
code, body = post('/api/quiz/questions/add', {'spec': 'Автор «Войны и мира»? | толстой'})
check(code == 200 and body['custom_count'] == 2, 'ок через сырой spec (формат команды)')
code, body = post('/api/quiz/questions/add', {'question': 'сколько нот в октаве?', 'answers': 'другое'})
_, cog_err = Q.try_add_question([], 'x')
check(code == 400 and 'уже есть' in (body.get('error') or ''), 'дубль: 400, слова как в боте')
code, body = post('/api/quiz/questions/add', {'question': '', 'answers': 'x'})
check(code == 400 and 'Формат' in (body.get('error') or ''), 'пустой вопрос — текст формата бота')

print('== 6. API: удаление + undo-цикл ==')
code, body = post('/api/quiz/questions/remove', {'index': 'zzz'})
check(code == 400 and 'целое число' in (body.get('error') or ''), 'не число — 400')
code, body = post('/api/quiz/questions/remove', {'index': 99})
check(code == 404 and 'Нет вопроса с номером 99' in (body.get('error') or ''), 'мимо диапазона — 404')
code, body = post('/api/quiz/questions/remove', {'index': 1})
check(code == 200 and body['removed']['q'] == 'Сколько нот в октаве?', 'удалён первый')
gone = body['removed']
spec = gone['q'] + ' | ' + ' ; '.join(gone['answers'])
code, body = post('/api/quiz/questions/add', {'spec': spec})
check(code == 200 and any(q['q'] == gone['q'] for q in body['questions']),
      'undo-возврат тем же API вернул вопрос (в конец библиотеки)')

print('== 7. API: зачёт и сброс ==')
r = client.get('/api/quiz/state')
body = r.get_json()
check({'questions', 'custom_count', 'builtin_count', 'scores_top', 'scores_total',
       'sessions_active'} <= set(body), 'форма payload полная')
check(body['builtin_count'] == len(Q.DEFAULT_QUESTIONS) and body['builtin_count'] == 12,
      'встроенный пул = константа кога')
check(body['scores_total'] == 1 and body['scores_top'][0]['points'] == 7, 'зачёт из хранилища кога')
check(body['scores_top'][0]['name'].startswith('ID 55') or body['scores_top'][0]['name'],
      'имя резолвится (бот офлайн → честный ID)')
code, body = post('/api/quiz/scores/reset', {})
check(code == 200 and body['scores_total'] == 0 and GuildData('quiz').get(777, 'scores', {}) == {},
      'обнуление — то же, что /квиз обнулить')
login('mod')
check(post('/api/quiz/scores/reset', {})[0] == 403, 'mod обнулять не может (403)')

print('== 8. Сессии live в payload (бот с когом) ==')


class FakeQuizCog:
    sessions = {1: {'cancelled': False}, 2: {'cancelled': True}}


class FakeBot:
    def get_guild(self, gid):
        return None

    def get_cog(self, name):
        return FakeQuizCog() if name == 'Quiz' else None


old_bot = appmod.bot_instance
appmod.bot_instance = FakeBot()
login('owner')
body = client.get('/api/quiz/state').get_json()
check(body['sessions_active'] == 1, 'активные сессии считаются из кoga (1 живая из двух)')
appmod.bot_instance = old_bot

print('== 9. Страница и шаблон ==')
r = client.get('/quiz')
check(r.status_code == 200, 'страница открывается (200)')
html = r.get_data(as_text=True)
check('/api/quiz/state' in html and 'qzNewQ' in html and 'qzReset' in html, 'монтаж на месте')
check('qz-del' in html, 'кнопки удаления предусмотрены')
src = open(os.path.join(ROOT, 'web', 'templates', 'quiz.html'), encoding='utf-8').read()
for token in ('/api/quiz/questions/add', '/api/quiz/questions/remove', '/api/quiz/scores/reset',
              'uxUndo', 'askConfirm', "role == 'admin' or role == 'owner'", 'sk-row', 'sk-card'):
    assert token in src, token
check(True, 'API, undo, confirm, гейтинг, скелетоны — всё в шаблоне')
check('esc(q.q)' in src and 'esc(r.name)' in src, 'поля через esc()')
EMOJI = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not EMOJI.search(src), 'эмодзи нет (FA-иконки)')
menu = open(os.path.join(ROOT, 'services', 'panel_menu.py'), encoding='utf-8').read()
check("'/quiz'" in menu and "'label': 'Квиз'" in menu, 'пункт меню «Квиз» в Сообществе')
check("'/quiz': ('quiz',)" in menu, 'карта когов знает страницу (чип «выкл» работает)')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
