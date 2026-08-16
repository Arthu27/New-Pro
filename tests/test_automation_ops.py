# -*- coding: utf-8 -*-
"""Автоматика: обратная связь (идеи #41-44).

1. #41 Карточка «Каналы-счётчики» (server_stats) в редакторе автоматики:
   новый вид поля counters (textarea 'ID | шаблон'), правила строк 1:1 с
   cmd_add кога (нужна переменная, шаблон режется до 80), замечания по
   битым строкам — в ответе сохранения, не молча.
2. #42 Сухой прогон триггеров: какое правило ответит на сообщение —
   find_match/matches кога как есть, живая карта кулдаунов бота, когда он
   онлайн; без неё — честный cooldown_known=False.
3. #43 Живой предпросмотр счётчиков: render_counter+gather_stats кога на
   живом сервере; офлайн — честный 503.
4. #44 Экспорт/импорт триггеров JSON: merge доливает (дубли отсекаются
   самим add_trigger кога), replace пересобирает начисто, лимит 50 бьёт
   так же, как в Discord-команде.

Запуск: python3 tests/test_automation_ops.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='aether_autoops_test_')
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


from web.routes import automation as AU  # noqa: E402

print('== 1. #41: parse_counters — правила строк 1:1 с когом ==')
ch, issues = AU.parse_counters('123 | Участники: {members}')
check(ch == {'123': 'Участники: {members}'} and issues == [], 'валидная строка принята')
ch, issues = AU.parse_counters(' 555 |  Голос: {voice} \n\n777 | Роли: {roles}')
check(ch == {'555': 'Голос: {voice}', '777': 'Роли: {roles}'},
      'пробелы и пустые строки проглочены')
_ch, issues = AU.parse_counters('123 участники')
check(issues == ['строка 1: нет разделителя «|»'], 'нет разделителя — замечание с номером строки')
_ch, issues = AU.parse_counters('abc | X {m}')
check(issues == ['строка 1: ID канала должен быть числом'], 'буквенный ID отвергнут')
_ch, issues = AU.parse_counters('123 | просто текст')
check(issues == ['строка 1: шаблону нужна переменная, напр. {members}'],
      'шаблон без переменной — отказ, как у /счётчики добавить')
_ch, issues = AU.parse_counters('123 | ')
check(issues == ['строка 1: пустой шаблон'], 'пустой шаблон — замечание')
ch, _i = AU.parse_counters('1 | A {m}\n1 | B {m}')
check(ch == {'1': 'B {m}'}, 'повторный ID — последний выигрывает (textarea = полное состояние)')
ch, _i = AU.parse_counters('9 | {members}' + 'x' * 100)
check(len(ch['9']) == 80, 'шаблон режется до 80, 1:1 с merge кога')
_ch, issues = AU.parse_counters('\n123 | {m}\nбитая')
check(issues == ['строка 3: нет разделителя «|»'], 'нумерация строк считает и пустые')
ch, issues = AU.parse_counters('')
check(ch == {} and issues == [], 'пустой ввод — пустое состояние без замечаний')

print('== 2. #41: сериализация/очистка и карточка в реестре ==')
ser = AU._serialize('server_stats', {'enabled': True,
                                     'channels': {'1': 'A {m}', '2': 'B {c}'}})
check(ser['channels'] == '1 | A {m}\n2 | B {c}', 'dict -> построчный текст')
check(ser['enabled'] is True, 'остальные поля не тронуты')
raw = AU._clean_payload('server_stats', {'channels': '7 | X {m}\nбитая', 'enabled': True})
check(raw['channels'] == {'7': 'X {m}'} and raw['enabled'] is True,
      'очистка: валидное сохранено, битая строка отброшена')
check('hack' not in AU._clean_payload('server_stats', {'hack': 1, 'enabled': False}),
      'чужие ключи не пролезают')
spec = AU.MODULE_EDITORS.get('server_stats')
check(spec is not None and spec['ns'] == 'server_stats', 'карточка счётчиков в реестре')
import cogs.server_stats as SS
check(getattr(spec['merge'], '__func__', spec['merge']) is SS.merge_settings,
      'merge — ровно функция кога (staticmethod-обёртка реестра)')
kinds = [f['kind'] for f in spec['fields']]
check(kinds == ['bool', 'counters'], 'поля карточки: включение + счётчики')

print('== 3. Права на новые API ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


NEW_APIS = ['/api/automation/counters-preview', '/api/automation/triggers/export']
with client.session_transaction() as s:
    s.clear()
check(all(client.get(u).status_code in (302, 401, 403) for u in NEW_APIS),
      'гостю GET-API закрыты')
check(client.post('/api/automation/triggers/test', json={}).status_code in (302, 401, 403)
      and client.post('/api/automation/triggers/import', json={}).status_code in (302, 401, 403),
      'гостю POST-API закрыты')
login('mod')
check(all(client.get(u).status_code == 403 for u in NEW_APIS),
      'моду — GET закрыты (автоматика admin-only)')
check(client.post('/api/automation/triggers/test', json={'text': 'x'}).status_code == 403,
      'моду — сухой прогон закрыт')

print('== 4. #41/#43: карточка, сохранение, живой предпросмотр ==')
login('owner')
mod = client.get('/api/automation').get_json()['modules']
check('server_stats' in mod and mod['server_stats']['values']['channels'] == '',
      'карточка в индексе, счётчиков пока нет')
r = client.post('/api/automation/server_stats', json={
    'enabled': True,
    'channels': '11 | Участники: {members}\n12 | Голос: {voice}\nбитая строка'})
d = r.get_json()
check(d['success'] and d['issues'] == ['строка 3: нет разделителя «|»'],
      'сохранение вернуло замечание по битой строке')
check(d['values']['channels'] == '11 | Участники: {members}\n12 | Голос: {voice}',
      'валидные строки сохранены')

prev = client.get('/api/automation/counters-preview')
check(prev.status_code == 503
      and prev.get_json()['error'] == 'Бот офлайн — живые числа недоступны',
      'без бота — честный 503, не муляж чисел')

CHANS = [SimpleNamespace(id=11, name='zala-schet')]
GUILD = SimpleNamespace(id=777, name='TestGuild', member_count=12, members=[],
                        text_channels=[], voice_channels=[], channels=CHANS,
                        roles=[1, 2, 3], premium_subscription_count=4)
GUILD.get_channel = lambda cid: next((c for c in CHANS if c.id == cid), None)


class FakeBot:
    def __init__(self, cogs=None):
        self.guilds = [GUILD]
        self._cogs = cogs or {}

    def get_guild(self, gid):
        return self.guilds[0] if int(gid) == 777 else None

    def get_cog(self, name):
        return self._cogs.get(name)


appmod.set_bot_instance(FakeBot())
prev = client.get('/api/automation/counters-preview')
d = prev.get_json()
check(prev.status_code == 200 and d['success'] and d['enabled'] is True,
      'с ботом предпросмотр живёт')
rows = {r['channel_id']: r for r in d['rows']}
check(rows['11']['rendered'] == 'Участники: 12'
      and rows['11']['channel_name'] == 'zala-schet' and rows['11']['missing'] is False,
      'рендер 1:1 с когом (render_counter + gather_stats)')
check(rows['12']['rendered'] == 'Голос: 0' and rows['12']['missing'] is True,
      'мёртвый канал честно помечен')

print('== 5. #42: сухой прогон триггеров ==')
from db import GuildData  # noqa: E402

state = {'next_id': 4, 'cooldown': 45, 'items': [
    {'id': 1, 'trigger': 'правила', 'response': 'Ссылка тут', 'exact': False,
     'uses': 0, 'created_at': 't'},
    {'id': 2, 'trigger': 'ip', 'response': 'play.example', 'exact': True,
     'uses': 0, 'created_at': 't'},
    {'id': 3, 'trigger': 'правила сервера', 'response': 'Полный свод', 'exact': False,
     'uses': 0, 'created_at': 't'},
]}
GuildData('triggers').set(777, 'state', state)

r = client.post('/api/automation/triggers/test', json={'text': '  '})
check(r.status_code == 400 and r.get_json()['error'] == 'Введите текст сообщения',
      'пустой текст — 400')
r = client.post('/api/automation/triggers/test', json={'text': 'скиньте правила'})
d = r.get_json()
check(d['matched'] and d['winner']['id'] == 1 and d['hits_total'] == 1,
      'подстрока срабатывает, победитель №1')
check(d['cooldown'] == 45 and d['cooldown_known'] is False and d['on_cooldown'] is False,
      'кулдаун из состояния; бот без кога — карта честно «неизвестна»')
r = client.post('/api/automation/triggers/test', json={'text': 'дайте правила сервера, срочно'})
d = r.get_json()
check(d['matched'] and d['winner']['id'] == 3 and d['hits_total'] == 2,
      'самое длинное слово выигрывает (find_match 1:1), тень посчитана')
check({h['id'] for h in d['hits']} == {1, 3}, 'в hits оба совпавших')
r = client.post('/api/automation/triggers/test', json={'text': 'какой ip у сервера?'})
d = r.get_json()
check(d['matched'] and d['winner']['exact'] is True and d['winner']['response'] == 'play.example',
      'точное слово ловится целиком')
r = client.post('/api/automation/triggers/test', json={'text': 'скрипты'})
check(not r.get_json()['matched'] and r.get_json()['hits_total'] == 0,
      '«скрипты» не цепляют точный «ip» — промах честный')

CDS = {777: {2: datetime.now(timezone.utc).isoformat()}}
appmod.set_bot_instance(FakeBot(cogs={'Triggers': SimpleNamespace(_cooldowns=CDS)}))
r = client.post('/api/automation/triggers/test', json={'text': 'ну какой ip'})
d = r.get_json()
check(not d['matched'] and d['on_cooldown'] is True and d['hits_total'] == 1
      and d['cooldown_known'] is True,
      'живой кулдаун бота: промолчит, и это видно')
appmod.set_bot_instance(FakeBot())
r = client.post('/api/automation/triggers/test', json={'text': 'ну какой ip'})
check(r.get_json()['matched'] and r.get_json()['cooldown_known'] is False,
      'без кога триггеров — прогон без кулдаунов, флаг честный')

print('== 6. #44: экспорт/импорт ==')
ex = client.get('/api/automation/triggers/export')
check(ex.status_code == 200 and 'triggers_777.json' in ex.headers.get('Content-Disposition', ''),
      'экспорт отдаёт файл с именем сервера')
payload = json.loads(ex.get_data(as_text=True))
check(payload['version'] == 1 and payload['cooldown'] == 45 and len(payload['items']) == 3,
      'в файле версия, кулдаун и все триггеры')
check(set(payload['items'][0].keys()) == {'trigger', 'response', 'exact'},
      'экспорт без служебных полей (id/uses не утаскиваются)')

r = client.post('/api/automation/triggers/import', json={'mode': 'полный', 'items': []})
check(r.status_code == 400 and r.get_json()['error'] == 'Неизвестный режим импорта',
      'левая мода отвергнута')
r = client.post('/api/automation/triggers/import', json={'mode': 'merge', 'items': 'опять правила'})
check(r.status_code == 400 and r.get_json()['error'] == 'Файл не похож на экспорт триггеров',
      'items не список — 400')
r = client.post('/api/automation/triggers/import', json={'mode': 'merge', 'items': [
    {'trigger': 'ip', 'response': 'ещё раз', 'exact': True},
    {'trigger': 'новости', 'response': 'Дайджест тут'},
    'не-словарь',
]})
d = r.get_json()
check(d['success'] and d['added'] == 1 and d['skipped_total'] == 2,
      'merge: дубль и мусор пропущены, новое долито')
check(d['skipped'][0]['trigger'] == 'ip' and 'уже есть' in d['skipped'][0]['reason'],
      'причина пропуска дубля — текст кога')
check(d['skipped'][1]['reason'] == 'не объект', 'мусорная строка помечена')
st = GuildData('triggers').get(777, 'state')
check(len(st['items']) == 4 and st['cooldown'] == 45,
      'merge не трогает кулдаун, хранилище пополнено')
r = client.post('/api/automation/triggers/import', json={'mode': 'merge', 'items': [
    {'trigger': 'новости', 'response': 'снова'}]})
check(r.get_json()['added'] == 0, 'повторный merge того же — идемпотентен')

r = client.post('/api/automation/triggers/import', json={'mode': 'replace', 'cooldown': 10,
                                                         'items': [{'trigger': 'соло',
                                                                    'response': 'один'}]})
d = r.get_json()
check(d['added'] == 1 and len(d['state']['items']) == 1 and d['state']['items'][0]['id'] == 1
      and d['state']['cooldown'] == 10, 'replace пересобрал начисто с новым кулдауном')

many = [{'trigger': f'w{i:02d}', 'response': 'r'} for i in range(50)]
r = client.post('/api/automation/triggers/import', json={'mode': 'replace', 'items': many})
check(r.get_json()['added'] == 50, 'полный набор из 50 импортирован')
r = client.post('/api/automation/triggers/import', json={'mode': 'merge',
                                                         'items': [{'trigger': 'лишний',
                                                                    'response': 'x'}]})
d = r.get_json()
check(d['added'] == 0 and 'максимум 50 триггеров' in d['skipped'][0]['reason'],
      'лимит бьёт словами кога')

print('== 7. Шаблон, меню, коги страницы ==')
tpl = open(os.path.join(ROOT, 'web/templates/automation.html'), encoding='utf-8').read()
emoji = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not emoji.search(tpl), 'в шаблоне нет эмодзи')
for needle in ("id=\"trg-test-text\"", "id=\"trg-import-box\"", "id=\"trg-import-mode\"",
               'triggers/test', 'triggers/export', 'triggers/import', 'counters-preview',
               'askConfirm', "data-kind=\"counters\"", 'server_stats'):
    check(needle in tpl, f'в шаблоне есть {needle}')
import services.panel_menu as PM
check('server_stats' in PM.PAGE_COGS['/automation'], 'счётчики учтены в когах страницы автоматики')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
