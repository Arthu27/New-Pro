# -*- coding: utf-8 -*-
"""Профи-фичи раунда: правила с линками/картинками и статистика модераторов.

Запуск: python3 tests/test_mod_rules_pro.py
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

# Изоляция: БД и data/ уходят в темп — реальные данные репо не трогаем.
_TMP = tempfile.mkdtemp(prefix='aether_modrules_')
os.environ['DB_PATH'] = os.path.join(_TMP, 'bot.db')
os.environ['DEMO_MODE'] = '0'
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'preview123'
os.environ['MAIN_GUILD_ID'] = '987654321098765432'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)

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


GID = '987654321098765432'
NOW = datetime.now(timezone.utc)
ISO = NOW.isoformat()

# ═══ 1. Счётчик сообщений: буфер → flush → чтение ════════════════════════
print('== счётчик сообщений модераторов ==')
from services.mod_activity import record_message, flush, message_counts  # noqa: E402

check(not message_counts(int(GID), days=7), 'пустая база — пустой ответ')
for _ in range(5):
    record_message(int(GID), '1001', 'Sonya')
record_message(int(GID), '1002', 'Artem')
mc = message_counts(int(GID), days=7)
check(mc.get('1001', {}).get('messages') == 5, f'5 сообщений Sonya после flush ({mc.get("1001")})')
check(mc.get('1002', {}).get('messages') == 1, '1 сообщение Artem')
check(mc.get('1002', {}).get('name') == 'Artem', 'имя сохраняется в записи')

# прореживание старых дней (>30) при слиянии
from db import GuildData  # noqa: E402
_st = GuildData('mod_activity')
old_day = (NOW - timedelta(days=40)).strftime('%Y-%m-%d')
_st.set(int(GID), '9001', {'name': 'Oldie', 'days': {old_day: 99}})
record_message(int(GID), '9001', 'Oldie')
flush()
rec = _st.get(int(GID), '9001') or {}
days = rec.get('days') or {}
check(old_day not in days, f'дни старше 30 суток подрезаются ({sorted(days)})')

# ═══ 2. API правил: структура, ссылки, картинки, валидация ══════════════
print('== правила: структура и публикация ==')
from web.app import app as flask_app  # noqa: E402

client = flask_app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'

# легаси-строки → нормализованные объекты
r = client.post(f'/api/guild/{GID}/rules', json=['Будь вежлив', 'Не спамь'])
check(r.status_code == 200 and r.get_json().get('success'), 'сохранение легаси-строк')
r = client.get(f'/api/guild/{GID}/rules')
d = r.get_json()
check(isinstance(d, list) and len(d) == 2 and d[0].get('t') == 'Будь вежлив',
      'GET отдаёт нормализованные объекты {t,u,img,thumb}')
check(all(set(x) >= {'t', 'u', 'img', 'thumb'} for x in d), 'у каждого правила все 4 поля')

# структура с линком/картинкой/миниатюрой
payload = [
    {'t': 'Не спамь', 'u': 'https://discord.gg/example',
     'img': 'https://example.com/r1.png', 'thumb': 'https://example.com/t1.png'},
    {'t': 'Без NSFW'},
]
r = client.post(f'/api/guild/{GID}/rules', json=payload)
check(r.status_code == 200 and r.get_json().get('success'), 'сохранение структурированных правил')
d = client.get(f'/api/guild/{GID}/rules').get_json()
check(d[0]['u'] == 'https://discord.gg/example' and d[0]['img'].endswith('r1.png')
      and d[0]['thumb'].endswith('t1.png'), 'линк/картинка/миниатюра сохраняются и возвращаются')

# валидация URL
r = client.post(f'/api/guild/{GID}/rules', json=[{'t': 'Тест', 'img': 'ftp://bad'}])
check(r.status_code == 400 and 'URL' in r.get_json().get('error', ''),
      'некорректный URL картинки отклоняется с понятной ошибкой')
r = client.post(f'/api/guild/{GID}/rules', json=[{'t': 'Тест', 'u': 'javascript:alert(1)'}])
check(r.status_code == 400, 'javascript:-ссылка отклоняется')

# публикация без канала/правил
r = client.post(f'/api/guild/{GID}/rules/publish', json={'channel_id': '', 'rules': payload})
check(r.status_code == 400 and 'канал' in r.get_json().get('error', '').lower(),
      'публикация без канала — понятная ошибка')
r = client.post(f'/api/guild/{GID}/rules/publish', json={'channel_id': '4002', 'rules': []})
check(r.status_code == 400, 'публикация без правил — 400')

# без бота и не демо — честная ошибка
r = client.post(f'/api/guild/{GID}/rules/publish', json={'channel_id': '4002', 'rules': payload})
d = r.get_json()
check(r.status_code in (200, 502) and not d.get('success') and 'Бот' in str(d.get('error', '')),
      'без бота публикация честно отвечает «Бот офлайн» (не 500)')

# сторож от старого бага двойной обёртки run_coroutine_threadsafe
src_rules = open(os.path.join(ROOT, 'web', 'routes', 'tasks_rules.py'), encoding='utf-8').read()
publish_part = src_rules.split('def api_publish_rules')[1]
check('await ch .send' in publish_part, 'публикация: прямой await в loop бота')
check('_run_async (ch' not in publish_part, 'публикация: нет двойной обёртки (старый 500-баг)')
check('set_image' in publish_part and 'set_thumbnail' in publish_part,
      'публикация: эмбеды поддерживают картинку и миниатюру')

# ═══ 3. /api/mod-stats: действия, сроки, сообщения, голос ════════════════
print('== статистика модераторов ==')
with open('data/mod_data.json', 'w', encoding='utf-8') as f:
    json.dump({'case': {GID: [
        {'user_id': '1', 'mod_id': 'mod.a', 'action': 'mute', 'duration_minutes': 120,
         'timestamp': ISO},
        {'user_id': '2', 'mod_id': 'mod.a', 'action': 'warn', 'timestamp': ISO},
        {'user_id': '3', 'mod_id': 'mod.b', 'action': 'ban',
         'timestamp': (NOW - timedelta(days=30)).isoformat()},
        {'user_id': '4', 'mod_id': 'mod.a', 'action': 'timeout', 'duration': '1d6h',
         'timestamp': (NOW - timedelta(days=20)).isoformat()},
    ]}}, f, ensure_ascii=False)
with open('data/warnings.json', 'w', encoding='utf-8') as f:
    json.dump({GID: {'5': [{'mod': 'mod.a', 'reason': 'x', 'timestamp': ISO}]}}, f)
with open('data/audit_log.json', 'w', encoding='utf-8') as f:
    json.dump({GID: [{'action': 'warn', 'mod_name': 'mod.b', 'user_name': 'x',
                      'timestamp': ISO}]}, f)

_voice = GuildData('voice_stats')
_voice.set(int(GID), 'm1', {'name': 'Mod A', 'avatar': '',
                            'total_seconds': 7200,
                            'daily': {(NOW - timedelta(days=1)).strftime('%Y-%m-%d'): 7200}})
_msgs = GuildData('mod_activity')
_msgs.set(int(GID), 'm1', {'name': 'Mod A', 'days': {NOW.strftime('%Y-%m-%d'): 42}})

r = client.get(f'/api/mod-stats?guild_id={GID}')
check(r.status_code == 200, f'/api/mod-stats отвечает 200 (получено {r.status_code})')
d = r.get_json()
check(d.get('success') is True and isinstance(d.get('rows'), list), 'mod-stats: success + rows')
rows = {x['mod']: x for x in d['rows']}
a = rows.get('mod.a', {})
check(a.get('mutes') == 2 and a.get('warns') == 2, f'действия mod.a посчитаны (mutes={a.get("mutes")}, warns={a.get("warns")})')
check(a.get('week') == 3, f'неделя mod.a: мьют + варн + варн из warnings (получено {a.get("week")})')
check(a.get('duration_min') == 120 + 1800, f'сроки: 120 мин + 1d6h = {a.get("duration_min")} мин')
check(rows.get('mod.b', {}).get('bans') == 1 and rows.get('mod.b', {}).get('total') == 2,
      'mod.b: бан за всё время + варн из аудита')
check(any(x['name'] == 'Mod A' and x.get('messages_week') == 42 and x.get('voice_hours_week') == 2.0
          for x in d['rows']), 'склейка: сообщения и голос привязаны к модератору')
k = d.get('kpis') or {}
check(k.get('actions_total') == 6 and k.get('actions_week') == 4,
      f'KPI: 6 действий всего / 4 за неделю (получено {k})')

# ═══ 4. Шаблоны: поля линков/картинок и блок статистики ═════════════════
print('== шаблоны ==')
t_rules = open(os.path.join(ROOT, 'web', 'templates', 'rules_editor.html'), encoding='utf-8').read()
check('data-field="u"' in t_rules and 'data-field="img"' in t_rules and 'data-field="thumb"' in t_rules,
      'редактор правил: поля ссылки, картинки и миниатюры')
check('pv-media' in t_rules and 'pv-thumb' in t_rules and 'pv-link' in t_rules,
      'редактор правил: превью картинки, миниатюры и ссылки')
check('fa-link' in t_rules and 'fa-image' in t_rules and 'fa-images' in t_rules,
      'редактор правил: FA-иконки полей')
t_mh = open(os.path.join(ROOT, 'web', 'templates', 'modhistory.html'), encoding='utf-8').read()
check('/api/mod-stats' in t_mh and 'mst-' in t_mh, 'лог модерации: блок профи-статистики подключён')
check('mst-week' in t_mh and 'mst-all' in t_mh, 'лог модерации: переключатель неделя/всё время')
check('Сроки наказаний' in t_mh and 'Сообщений / нед' in t_mh and 'Голос / нед' in t_mh,
      'лог модерации: колонки сроков, сообщений и голоса')
src_hook = open(os.path.join(ROOT, 'cogs', 'proactive_mod.py'), encoding='utf-8').read()
check('record_message' in src_hook, 'бот: on_message пишет счётчик сообщений')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
