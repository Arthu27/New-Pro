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

_TMP = tempfile.mkdtemp(prefix='hakumo_autoops_test_')
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

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')

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

print('== 7. #45: медиа-лок каналов ==')
with client.session_transaction() as s:
    s.clear()
check(client.get('/api/automation/medialock').status_code in (302, 401, 403),
      'гостю медиа-лок закрыт')
check(client.post('/api/automation/medialock/set', json={}).status_code in (302, 401, 403),
      'гостю нельзя ставить замки')
login('mod')
check(client.get('/api/automation/medialock').status_code == 403,
      'моду медиа-лок закрыт (admin-only)')
login('owner')
r = client.get('/api/automation/medialock')
d = r.get_json()
check(d['success'] and d['channels'] == []
      and [m['key'] for m in d['modes']] == ['media', 'text', 'link'],
      'пустой список + три режима кога')
check(all('label' in m and 'desc' in m for m in d['modes'])
      and not any(EMOJI_RE.search(m['label']) for m in d['modes']),
      'панельные подписи режимов без эмодзи')

r = client.post('/api/automation/medialock/set', json={'channel_id': 'abc', 'mode': 'media'})
check(r.status_code == 400 and r.get_json()['error'] == 'ID канала должен быть числом',
      'буквенный канал — 400')
r = client.post('/api/automation/medialock/set', json={'channel_id': '55', 'mode': 'даже'})
check(r.status_code == 400 and r.get_json()['error'] == 'Неизвестный режим канала',
      'левый режим — 400')
r = client.post('/api/automation/medialock/set', json={'channel_id': '55', 'mode': 'media'})
d = r.get_json()
check(d['success'] and len(d['channels']) == 1
      and d['channels'][0]['mode_label'] == 'Только медиа'
      and d['channels'][0]['exempt_mods'] is True,
      'замок поставлен, моды свободны по умолчанию (1:1 с ml_set)')
stored = json.load(open('data/media_only.json', encoding='utf-8'))
check(stored == {'777': {'55': {'mode': 'media', 'exempt_mods': True}}},
      'файл 1:1 со структурой кога media_only')
r = client.post('/api/automation/medialock/set', json={'channel_id': '55', 'mode': 'text',
                                                       'exempt_mods': False})
d = r.get_json()
check(len(d['channels']) == 1 and d['channels'][0]['mode'] == 'text'
      and d['channels'][0]['exempt_mods'] is False, 'перестановка режима без дубля')
r = client.post('/api/automation/medialock/remove', json={'channel_id': '99'})
check(r.status_code == 404 and r.get_json()['error'] == 'На канале замка не было',
      'честный 404, слова как у кога')
r = client.post('/api/automation/medialock/remove', json={'channel_id': '55'})
d = r.get_json()
check(d['success'] and d['removed']['mode'] == 'text'
      and d['removed']['exempt_mods'] is False and d['channels'] == [],
      'снятие возвращает снапшот для undo, список пуст')

print('== 8. #46-47: ночная сводка ==')
with client.session_transaction() as s:
    s.clear()
check(client.get('/api/automation/night-summary').status_code in (302, 401, 403),
      'гостю сводка закрыта')
login('mod')
check(client.get('/api/automation/night-summary').status_code == 403,
      'моду сводка закрыта (admin-only)')
login('owner')
with open('data/night_summary.json', 'w', encoding='utf-8') as fh:
    json.dump({'777': {'last_date': '2026-08-15'}}, fh)
r = client.get('/api/automation/night-summary')
d = r.get_json()
check(d['success'] and d['enabled'] is True and d['channel_id'] == 0
      and d['tz_offset'] == 3, 'дефолты 1:1 с cfg() кога')
check(d['last_sent'] == '2026-08-15' and bool(d['today']),
      'последняя отправка читается, дата дня есть')

r = client.post('/api/automation/night-summary', json={})
check(r.status_code == 400 and r.get_json()['error'] == 'Нечего сохранять', 'пустой POST — 400')
r = client.post('/api/automation/night-summary', json={'tz_offset': 'полночь'})
check(r.status_code == 400 and r.get_json()['error'] == 'Смещение — число часов', 'tz не число — 400')
r = client.post('/api/automation/night-summary', json={'tz_offset': 99})
check(r.status_code == 400 and r.get_json()['error'] == 'Смещение: от -12 до +14 часов',
      'tz вне диапазона — 400')
r = client.post('/api/automation/night-summary', json={'channel_id': -5})
check(r.status_code == 400 and r.get_json()['error'] == 'ID канала — число (0 — авто)',
      'отрицательный канал — 400')
r = client.post('/api/automation/night-summary', json={'enabled': False, 'channel_id': 123,
                                                       'tz_offset': 0})
d = r.get_json()
check(d['success'] and d['enabled'] is False and d['channel_id'] == 123
      and d['tz_offset'] == 0, 'настройки сохранены')
stored = json.load(open('data/night_summary.json', encoding='utf-8'))
check(stored['777'].get('last_date') == '2026-08-15'
      and stored['777']['enabled'] is False,
      'last_date кога не затёрт правкой панели')

now_ts = datetime.now(timezone.utc).timestamp()
with open('data/mod_data.json', 'w', encoding='utf-8') as fh:
    json.dump({'cases': {'777': [
        {'action': 'warn', 'timestamp': now_ts, 'mod_id': '42'},
        {'action': 'ban', 'timestamp': now_ts - 10 * 86400, 'mod_id': '42'},
    ]}}, fh)
r = client.get('/api/automation/night-summary/preview')
d = r.get_json()
check(r.status_code == 200 and d['success'] and d['tz_offset'] == 0
      and d['enabled'] is False, 'предпросмотр живёт, эхо настроек')
s = d['stats']
check(s['warns'] == 1 and s['bans'] == 0 and s['top_mod_id'] == 42
      and s['top_mod_count'] == 1,
      'collect_day кога: варн сегодня учтён, старый бан за днём, модератор дня')

print('== 9. #48: фаза ночного режима ==')
from datetime import timezone as _tz  # noqa: E402

U = _tz.utc
ph = AU.night_phase({}, now=datetime(2026, 8, 16, 23, 30, tzinfo=U))
check(ph['is_night'] is True and ph['next_change'] == 'утро'
      and ph['next_change_in_s'] == 27000, '23:30 в окне 23–7: до утра 7ч30м')
ph = AU.night_phase({}, now=datetime(2026, 8, 16, 12, 15, 30, tzinfo=U))
check(ph['is_night'] is False and ph['next_change'] == 'ночь'
      and ph['next_change_in_s'] == 38670, '12:15 днём: до ночи 10ч44м30с')
ph = AU.night_phase({'start_hour': 7, 'end_hour': 7},
                    now=datetime(2026, 8, 16, 3, 0, tzinfo=U))
check(ph['is_night'] is False and ph['next_change_in_s'] is None
      and ph['next_change'] is None, 'пустое окно (start==end) — ночи нет, перелома нет')
ph = AU.night_phase({})
check(ph['window'] == '23:00–07:00 UTC' and len(ph['lines']) == 5
      and ph['enabled'] is False, 'окно и строки плана — самим когом (window_text/plan_lines)')

with client.session_transaction() as s:
    s.clear()
check(client.get('/api/automation/night-phase').status_code in (302, 401, 403),
      'гостю фаза закрыта')
login('mod')
check(client.get('/api/automation/night-phase').status_code == 403, 'моду фаза закрыта')
login('owner')
d = client.get('/api/automation/night-phase').get_json()
check(d['success'] and isinstance(d['is_night'], bool) and d['window'] == '23:00–07:00 UTC',
      'эндпоинт отвечает фазой по умолчанию')

print('== 10. #49: предпросмотр приветствий PRO ==')
with client.session_transaction() as s:
    s.clear()
check(client.get('/api/automation/welcome-preview').status_code in (302, 401, 403),
      'гостю предпросмотр закрыт')
login('mod')
check(client.get('/api/automation/welcome-preview').status_code == 403,
      'моду предпросмотр закрыт')
login('owner')
appmod.set_bot_instance(None)
d = client.get('/api/automation/welcome-preview').get_json()
check(d['success'] and d['sample'] is False and d['server'] == 'Сервер'
      and d['count'] == 128, 'без бота — честный флаг sample и муляжи помечены')
check(len(d['templates']) == 3 and '@Новенький' in d['templates'][0]['rendered']
      and d['templates'][0]['source'].startswith('Добро пожаловать'),
      'дефолтные шаблоны кога отрендерены')
check(d['enabled'] is False and d['dm_enabled'] is False, 'дефолты выключателей 1:1')

appmod.set_bot_instance(FakeBot())
d = client.get('/api/automation/welcome-preview').get_json()
check(d['sample'] is True and d['server'] == 'TestGuild' and d['count'] == 13,
      'с ботом — живые имя сервера и следующий номер')
check('TestGuild' in d['templates'][1]['rendered'], 'имя сервера подставлено рендером кога')

r = client.post('/api/automation/welcome_pro', json={
    'dm_enabled': True, 'dm_text': 'Салют, {user} на {server}!',
    'templates': 'Первая {mention}\nБитая {переменная}'})
check(r.get_json()['success'], 'шаблоны и ЛС сохранены через карточку')
d = client.get('/api/automation/welcome-preview').get_json()
check(len(d['templates']) == 2 and d['templates'][1]['rendered'] == 'Битая {переменная}',
      'неизвестная переменная не роняет рендер (SafeDict кога)')
check(d['dm_rendered'] == 'Салют, Новенький на TestGuild!', 'ЛС отрендерено 1:1')

print('== 11. #50: перенос автоматики ==')
client.post('/api/automation/triggers/import', json={'mode': 'replace', 'cooldown': 30,
                                                     'items': [{'trigger': 'имп-база',
                                                                'response': 'ответ базы'}]})
with client.session_transaction() as s:
    s.clear()
check(client.get('/api/automation/export-all').status_code in (302, 401, 403),
      'гостю экспорт закрыт')
check(client.post('/api/automation/import-all', json={}).status_code in (302, 401, 403),
      'гостю импорт закрыт')
login('owner')
ex = client.get('/api/automation/export-all')
check('automation_777.json' in ex.headers.get('Content-Disposition', ''),
      'имя файла с сервером')
bundle = json.loads(ex.get_data(as_text=True))
check(bundle['app'] == 'hakumo-automation' and bundle['version'] == 1
      and bundle['guild_id'] == '777', 'шапка бандла')
check(set(bundle['modules']) == set(AU.MODULE_EDITORS)
      and bundle['modules']['server_stats']['channels'] ==
      '11 | Участники: {members}\n12 | Голос: {voice}',
      'модули сериализованы формой (счётчики построчно)')
check(all('uses' not in it and 'id' not in it for it in bundle['triggers']['items']),
      'триггеры без служебных полей')
check(bundle['night_summary'] == {'enabled': False, 'channel_id': 123, 'tz_offset': 0}
      and bundle['medialock']['channels'] == {}, 'сводка и замки в чистом виде')

r = client.post('/api/automation/import-all', json={'app': 'nope'})
check(r.status_code == 400 and r.get_json()['error'] == 'Файл не похож на экспорт автоматики',
      'чужой файл — 400')
r = client.post('/api/automation/import-all', json={'app': 'hakumo-automation'})
d = r.get_json()
check(d['success'] and d['applied']['modules'] == [] and d['applied']['triggers'] == 0,
      'пустой бандл — ничего не применилось, не упало')

payload = {
    'app': 'hakumo-automation', 'version': 1,
    'modules': {
        'night_mode': {'enabled': True, 'start_hour': 22, 'end_hour': 6,
                       'slowmode_seconds': 30},
        'server_stats': {'enabled': True, 'channels': '77 | Онлайн: {online}\nбитая'},
        'unknown_mod': {'enabled': True},
    },
    'triggers': {'cooldown': 15, 'items': [
        {'trigger': 'имп-база', 'response': 'ещё раз'},
        {'trigger': 'имп-новая', 'response': 'свежая'}]},
    'medialock': {'channels': {
        '88': {'mode': 'link', 'exempt_mods': False},
        'битый': {'mode': 'media'},
        '89': {'mode': 'недопустимый'}}},
    'night_summary': {'enabled': False, 'channel_id': 5, 'tz_offset': 7},
}
r = client.post('/api/automation/import-all', json=payload)
d = r.get_json()
check(d['success'] and d['applied']['modules'] == ['night_mode', 'server_stats'],
      'модули применены по порядку реестра')
check(d['applied']['triggers'] == 1 and d['applied']['medialock'] == 1
      and d['applied']['night_summary'] is True, 'триггер/замок/сводка применены')
check(d['skipped_total'] == 4, 'четыре пропуска: левый модуль, битый канал, левый режим, дубль')
reasons = {(s['section'], s['reason']) for s in d['skipped']}
check(('modules', 'неизвестный модуль') in reasons
      and ('medialock', 'битый канал или режим') in reasons,
      'причины пропусков читаемые')
check(d['issues'] == ['строка 2: нет разделителя «|»'], 'замечания счётчиков всплыли')
nm = GuildData('night_mode').get(777, 'settings')
check(nm['enabled'] is True and nm['start_hour'] == 22 and nm['slowmode_seconds'] == 30,
      'ночной режим записан (merge кога)')
st = GuildData('triggers').get(777, 'state')
check(len(st['items']) == 2 and st['cooldown'] == 15, 'триггеры долиты, кулдаун приянят')
ml_stored = json.load(open('data/media_only.json', encoding='utf-8'))
check(ml_stored['777']['88'] == {'mode': 'link', 'exempt_mods': False}
      and '89' not in ml_stored['777'], 'медиа-лок долит мягко')
ns = json.load(open('data/night_summary.json', encoding='utf-8'))
check(ns['777']['tz_offset'] == 7 and ns['777'].get('last_date') == '2026-08-15',
      'сводка перенесена, last_date цел')
r = client.post('/api/automation/import-all', json={'app': 'hakumo-automation',
                                                    'night_summary': {'tz_offset': 99}})
d = r.get_json()
check(d['applied']['night_summary'] is False
      and d['skipped'][0]['reason'] == 'Смещение: от -12 до +14 часов',
      'битое смещение отклонено словами валидатора')

print('== 12. Шаблон, меню, коги страницы ==')
tpl = open(os.path.join(ROOT, 'web/templates/automation.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
for needle in ("id=\"trg-test-text\"", "id=\"trg-import-box\"", "id=\"trg-import-mode\"",
               'triggers/test', 'triggers/export', 'triggers/import', 'counters-preview',
               'askConfirm', "data-kind=\"counters\"", 'server_stats',
               "id=\"au-night-phase\"", "id=\"welcome-sec\"", "id=\"transfer-sec\"",
               "id=\"tr-import-box\"", 'export-all', 'import-all', 'welcome-preview',
               'night-phase',
               "id=\"medialock-sec\"", "id=\"nightsum-sec\"", "id=\"ml-mode\"", "id=\"ns-tz\"",
               'medialock/set', 'medialock/remove', 'night-summary/preview', 'uxUndo'):
    check(needle in tpl, f'в шаблоне есть {needle}')
import services.panel_menu as PM
check('server_stats' in PM.PAGE_COGS['/automation'], 'счётчики учтены в когах страницы автоматики')
check('media_only' in PM.PAGE_COGS['/automation']
      and 'night_summary' in PM.PAGE_COGS['/automation'],
      'медиа-лок и ночная сводка учтены в когах страницы')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
