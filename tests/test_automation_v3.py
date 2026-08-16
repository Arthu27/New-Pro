# -*- coding: utf-8 -*-
"""Автоматика v3: редактор триггеров + живой предпросмотр мод-дайджеста.

Два пробела страницы автоматики закрыты в одном релизе:

1. Триггеры (автоответы) настраивались только из Discord командой /триг.
   Теперь /automation даёт полный редактор: список, добавление, удаление,
   кулдаун. Валидация — РОВНО та, что в коге (add_trigger/remove_trigger
   как есть): те же ошибки, тот же лимит 50, та же защита от дублей —
   рассинхрона «в панели разрешили, бот отверг» нет в принципе.

2. Дайджест стал красивее (бары долей ▓░ + спарклайн «Ритм по дням»,
   старый формат строк сохранён), а в панели — предпросмотр: те же
   aggregate_digest + digest_embed_dict, что ког шлёт в Discord.

Проверяем: чистые бар/спарк/ритм функции (инжект now), контракт embed
(старые подстроки целы, новые поля добавлены), API дайджест-превью (роли,
клампы дней, сид audit_log), полный цикл триггер-API (валидация 1:1 с
когом, права, персистентность), статику секций шаблона.

Запуск: python3 tests/test_automation_v3.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='aether_autov3_test_')
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


NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)

# ═══ 1. Красота дайджеста: бары / спарк / ритм — чистые функции ═══════════
print('== 1. Бары и спарклайн ==')
from cogs import mod_digest as md  # noqa: E402

check(md.mini_bar(0) == md._BAR_EMPTY * 10 and md.mini_bar(1) == md._BAR_FULL * 10,
      'mini_bar: 0 и 1 — ровно ширина')
check(len(md.mini_bar(0.55)) == 10 and md.mini_bar(0.55).count(md._BAR_FULL) in (5, 6),
      'mini_bar: пропорция держит ширину')
check(md.sparkline([]) == '' and md.sparkline([0, 0, 0]) == '', 'спарклайн: пусто/нули — честная пустота')
sp = md.sparkline([1, 2, 4, 0])
check(len(sp) == 4 and sp[2] == '█' and sp[3] == '▁' and sp[0] < sp[2], f'спарклайн растёт с данными: {sp}')
rs = md.rhythm_series({'2026-08-15': 3, '2026-08-16': 5, '2026-08-01': 99}, days=7, now=NOW)
check(rs == [0, 0, 0, 0, 0, 3, 5], f'ритм за 7 дней выровнен по сегодняшнему дню: {rs}')
rs14 = md.rhythm_series({}, days=60, now=NOW)
check(len(rs14) == md.RHYTHM_DAYS, 'окно ритма капнуто шириной эмбеда (14)')

print('== 2. Контракт embed v2 ==')
events = []
for back, cat, act, mod in ((0, 'warn', 'warn', 'Arthur'), (0, 'warn', 'warn', 'Arthur'),
                            (1, 'mod', 'ban', 'moder'), (2, 'ticket', 'close', 'moder')):
    ts = NOW - timedelta(days=back)
    events.append({'category': cat, 'action': act, 'mod_name': mod, 'timestamp': ts.isoformat()})
summary = md.aggregate_digest(events, days=7, now=NOW)
payload = md.digest_embed_dict(summary, 7, 'Hakumo', now=NOW)
fields = dict(payload['fields'])
check('Предупреждения: **2**' in fields['По категориям'], 'старый формат строки категории цел (обратная совместимость)')
check('▓' in fields['По категориям'] or '░' in fields['По категориям'], 'у категорий появились бары')
check('%' in fields['По категориям'], 'доли в процентах при категориях')
check('Ритм по дням' in fields, 'новое поле «Ритм по дням» есть')
check(fields['Всего событий'] == '4' and 'Arthur' in fields['Активные модераторы'], 'старое содержимое на месте')
cog_src = open(os.path.join(ROOT, 'cogs', 'mod_digest.py'), encoding='utf-8').read()
check('digest_embed_dict(summary, days, guild.name' in cog_src, 'ког зовёт embed совместимо (now — опциональный)')

# ═══ 2. Панель ════════════════════════════════════════════════════════════
print('== 3. Панель: окружение ==')
os.makedirs('data', exist_ok=True)
with open('data/audit_log.json', 'w', encoding='utf-8') as f:
    json.dump({'777': events}, f, ensure_ascii=False)

appmod = importlib.import_module('web.app')
app = appmod.app
app.config['TESTING'] = True
client = app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


class FakeBot:
    def __init__(self):
        self.guilds = [SimpleNamespace(id=777, name='TestGuild')]

    def get_guild(self, gid):
        return self.guilds[0] if int(gid) == 777 else None


print('== 4. Дайджест-превью: роли, клампы, данные ==')
with client.session_transaction() as s:
    s.clear()
r = client.get('/api/automation/digest-preview')
check(r.status_code in (302, 401, 403), f'гостю закрыто ({r.status_code})')
login('uye')
check(client.get('/api/automation/digest-preview').status_code == 403, 'uye нельзя (403)')
login('mod')
check(client.get('/api/automation/digest-preview').status_code == 403, 'mod нельзя — настройки admin-only (403)')

appmod.set_bot_instance(FakeBot())
login('owner')
r = client.get('/api/automation/digest-preview')
d = r.get_json()
check(r.status_code == 200 and d.get('success'), 'owner: 200 + success')
check(d['days'] == 7 and d['summary']['total'] == 4, 'сид audit_log учтён агрегацией')
emb = d.get('embed') or {}
check(emb.get('title', '').startswith('Мод-дайджест · TestGuild'), 'имя сервера резолвится из кэша бота')
check(dict(emb['fields']).get('Ритм по дням'), 'строки эмбеда — те самые из кога (с ритмом)')
r = client.get('/api/automation/digest-preview?days=999')
check(r.get_json()['days'] == 90, 'days клампится к 90')
r = client.get('/api/automation/digest-preview?days=abc')
check(r.get_json()['days'] == 7, 'битый days — мягкий дефолт 7')

print('== 5. Триггеры: права и первичное состояние ==')
with client.session_transaction() as s:
    s.clear()
check(client.get('/api/automation/triggers/state').status_code in (302, 401, 403), 'гость: state закрыт')
login('uye')
check(client.get('/api/automation/triggers/state').status_code == 403, 'uye: state закрыт (403)')
login('mod')
check(client.get('/api/automation/triggers/state').status_code == 403, 'mod: state закрыт — admin-only (403)')
login('owner')
r = client.get('/api/automation/triggers/state')
d = r.get_json()
check(d['success'] and d['state']['items'] == [] and d['state']['cooldown'] == 30 and d['max'] == 50,
      'пустое состояние: items=[], cooldown=30, max=50')

print('== 6. Триггеры: валидация ровно как в коге ==')
from cogs.triggers import add_trigger, empty_state  # noqa: E402

r = client.post('/api/automation/triggers/add', json={'trigger': 'правила', 'response': 'Читай #rules'})
d = r.get_json()
check(r.status_code == 200 and d['success'] and d['state']['items'][0]['id'] == 1, 'первый триггер добавлен')
r = client.post('/api/automation/triggers/add', json={'trigger': 'правила', 'response': 'дубль'})
_st = empty_state()
add_trigger(_st, 'правила', 'x')
_, cog_err = add_trigger(_st, 'правила', 'x')
check(r.status_code == 400 and r.get_json()['error'] == cog_err,
      f'дубль: API-код и текст ошибки 1:1 с когом «{cog_err}»')
_, short_err = add_trigger(empty_state(), 'а', 'x')
r = client.post('/api/automation/triggers/add', json={'trigger': 'а', 'response': 'x'})
check(r.status_code == 400 and r.get_json()['error'] == short_err, 'короткий триггер отвергнут словами кога')
_, empty_err = add_trigger(empty_state(), 'слово', '  ')
r = client.post('/api/automation/triggers/add', json={'trigger': 'слово', 'response': '  '})
check(r.status_code == 400 and r.get_json()['error'] == empty_err, 'пустой ответ отвергнут словами кога')
r = client.post('/api/automation/triggers/add', json={'trigger': 'ip', 'response': 'play.example.com', 'exact': True})
check(r.get_json()['state']['items'][1]['exact'] is True, 'флаг exact сохраняется')

print('== 7. Триггеры: кулдаун, удаление, персистентность ==')
r = client.post('/api/automation/triggers/cooldown', json={'seconds': 'abc'})
check(r.status_code == 400, 'битый кулдаун — 400')
r = client.post('/api/automation/triggers/cooldown', json={'seconds': 99999})
check(r.status_code == 400, 'кулдаун >3600 — 400')
r = client.post('/api/automation/triggers/cooldown', json={'seconds': 15})
check(r.get_json()['state']['cooldown'] == 15, 'кулдаун 15 сохранён')
r = client.post('/api/automation/triggers/remove', json={'id': 999})
check(r.status_code == 404, 'удаление несуществующего — 404')
r = client.post('/api/automation/triggers/remove', json={'id': 2})
check(r.get_json()['success'] and len(r.get_json()['state']['items']) == 1, 'удаление №2 сработало')
r = client.get('/api/automation/triggers/state')
d = r.get_json()
check(d['state']['cooldown'] == 15 and [i['id'] for i in d['state']['items']] == [1],
      'персистентность через GET: кулдаун и список как после операций')
r = client.post('/api/automation/triggers/add', json={'trigger': 'команды', 'response': 'все команды — !help'})
check(r.get_json()['state']['items'][-1]['id'] == 3, 'next_id продолжает сквозную нумерацию (1..3, без переиспользования)')

print('== 8. Шаблон: секции v3 ==')
src = open(os.path.join(ROOT, 'web', 'templates', 'automation.html'), encoding='utf-8').read()
for token in ('triggers-sec', 'digest-sec', 'trg-form', 'dg-embed', 'loadTriggers()',
              'trgRemove', 'loadDigestPreview', '/api/automation/triggers/state',
              '/api/automation/digest-preview'):
    assert token in src, token
check(True, 'секции триггеров и предпросмотра в шаблоне')
check("esc(t.trigger)" in src and "esc(e.title)" in src, 'пользовательские строки через esc()')
EMOJI = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
check(not EMOJI.search(src), 'эмодзи нет (FA-иконки только)')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
