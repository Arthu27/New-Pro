# -*- coding: utf-8 -*-
"""«Журнал модерации»: наказания без дублей, с причиной, сроком и автором.

Жалоба владельца: «журнал модерации — причина и время не пишутся, и даже
кто дал; сделай не все действия, а нормально, компактно, красиво»
и 2026-09-06: «журнал переделай нормально, некрасиво — разберись,
красиво сделай» (лента карточек вместо таблицы).

Проверяем (/api/logs и склейка дублей):
  1. один мут из /modpanel = ОДНА строка: дело панели + запись слушателя
     + аудит Discord склеены, осталась лучшая версия (настоящий
     модератор, причина, срок мута);
  2. записи «без причины» не склеивают два РАЗНЫХ наказания с разными
     причинами в пределах 2 минут;
  3. не-наказания (входы, роли, каналы) никогда не склеиваются;
  4. варны из warnings.json попадают в журнал (причина + модератор);
  5. коды дел /modpanel переведены: mute_chat → «Мут чата» и т.п.;
  6. срок мута отдаётся единым полем duration (минуты) и из дела,
     и из аудита.

Запуск: python3 tests/test_logs_journal.py
"""
import json
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_logs_journal_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['SECRET_KEY'] = 'test-secret'
os.environ.pop('TOKEN', None)

PASS = 0
FAIL = 0


def check(ok, msg, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {detail}')


print('== _log_merge_duplicates: один мут — одна строка ==')
import web.app as A  # noqa: E402

T = '2026-09-06T18:00:00+00:00'
T2 = '2026-09-06T18:01:10+00:00'          # копия из аудита — на минуту позже
T3 = '2026-09-06T18:04:30+00:00'          # отдельное наказание (>2 минут)
events = [
    # 1) мут из /modpanel: дело (модератор-человек, причина, срок)
    {'guild_id': '777', 'category': 'mod', 'action': 'Таймаут',
     'user_id': '100', 'user_name': '100', 'mod_name': 'Lina', 'mod_id': '7',
     'reason': 'Флуд в общем чате', 'timestamp': T, 'duration': 120,
     'until': '2026-09-06T20:00:00+00:00', 'source': 'case'},
    # 2) тот же мут из слушателя (без модератора и срока)
    {'guild_id': '777', 'category': 'mod', 'action': 'Мут',
     'user_id': '100', 'user_name': 'spam_user', 'mod_name': '', 'mod_id': '',
     'reason': 'Флуд в общем чате', 'timestamp': T2, 'source': 'listener'},
    # 3) тот же мут из аудита Discord (исполнитель — сам бот)
    {'guild_id': '777', 'category': 'mod', 'action': 'Мут',
     'user_id': '100', 'user_name': 'spam_user', 'mod_name': 'Hakumo',
     'mod_id': '999', 'reason': 'Флуд в общем чате', 'timestamp': T2,
     'source': 'discord_audit'},
    # 4) другой мут тому же человеку спустя 4 минуты — отдельное наказание
    {'guild_id': '777', 'category': 'mod', 'action': 'Мут',
     'user_id': '100', 'user_name': 'spam_user', 'mod_name': 'Sonya',
     'mod_id': '8', 'reason': 'Повторный флуд', 'timestamp': T3},
    # 5) не-наказания — не трогаем
    {'guild_id': '777', 'category': 'member', 'action': 'Участник вошёл',
     'user_id': '100', 'user_name': 'spam_user', 'timestamp': T},
    {'guild_id': '777', 'category': 'role', 'action': 'Роль выдана',
     'user_id': '100', 'user_name': 'spam_user', 'timestamp': T2},
]
merged = A._log_merge_duplicates([dict(e) for e in events])
mutes_100 = [e for e in merged if e['user_id'] == '100'
             and A._log_act_class(e['action']) == 'mute']
check(len(mutes_100) == 2,
      'мут №1 склеен из трёх копий, мут №4 (через 4 мин) остался отдельным',
      f'{len(mutes_100)} строк')
first = min(mutes_100, key=lambda e: e['timestamp'])
check(first.get('mod_name') == 'Lina',
      'в склееной строке — настоящий модератор из дела, не бот',
      f"mod_name={first.get('mod_name')!r}")
check(first.get('duration') == 120 and first.get('until'),
      'срок мута и «до какого» сохранены при склейке',
      f"duration={first.get('duration')} until={first.get('until')!r}")
check(first.get('user_name') == 'spam_user',
      'имя участника подтянуто из записи с именем (не голый ID)',
      f"user_name={first.get('user_name')!r}")
non_pun = [e for e in merged if e['action'] in ('Участник вошёл', 'Роль выдана')]
check(len(non_pun) == 2, 'не-наказания склейкой не тронуты')

# разные причины рядом → НЕ склеиваются (это два разных дела)
two = A._log_merge_duplicates([
    {'guild_id': '777', 'action': 'Предупреждение', 'user_id': '200',
     'reason': 'капс', 'mod_name': 'Lina', 'timestamp': T},
    {'guild_id': '777', 'action': 'Предупреждение', 'user_id': '200',
     'reason': 'офтоп', 'mod_name': 'Sonya', 'timestamp': T2},
])
check(len(two) == 2, 'два варна с разными причинами — две строки')

# «без причины» липнет к группе с причиной, не порождая четвёртую строку
junk = A._log_merge_duplicates([
    {'guild_id': '777', 'action': 'Мут', 'user_id': '300', 'mod_name': 'Lina',
     'reason': 'Спам', 'timestamp': T},
    {'guild_id': '777', 'action': 'Мут', 'user_id': '300', 'mod_name': '',
     'reason': '', 'timestamp': T2},
    {'guild_id': '777', 'action': 'Мут', 'user_id': '300', 'mod_name': 'Hakumo',
     'reason': 'мут', 'timestamp': T2},
])
check(len(junk) == 1, 'записи «без причины» влиты в строку с причиной',
      f'{len(junk)} строк')

print('== /api/logs: варны, перевод кодов, срок ==')
A.MAIN_GUILD_ID = '777'
with open('data/audit_log.json', 'w', encoding='utf-8') as f:
    json.dump({'777': [
        {'category': 'mod', 'action': 'Мут', 'user_id': '100',
         'user_name': 'spam_user', 'mod_name': 'Lina', 'mod_id': '7',
         'reason': 'Флуд', 'timestamp': T, 'duration_minutes': 90},
        {'category': 'member', 'action': 'Участник вошёл', 'user_id': '55',
         'user_name': 'newbie', 'timestamp': T},
    ]}, f, ensure_ascii=False)
with open('data/mod_data.json', 'w', encoding='utf-8') as f:
    json.dump({'cases': {'777': [
        {'id': 1, 'action': 'mute_chat', 'user_id': '100', 'mod_id': '7',
         'mod_name': 'Lina', 'reason': 'Флуд', 'duration_minutes': 90,
         'timestamp': T2},
        {'id': 2, 'action': 'vunmute', 'user_id': '400', 'mod_id': '8',
         'mod_name': 'Sonya', 'reason': 'исправление', 'timestamp': T3},
    ]}}, f, ensure_ascii=False)
with open('data/warnings.json', 'w', encoding='utf-8') as f:
    json.dump({'777': {'600': [
        {'id': 1, 'reason': 'капс', 'mod': 'Artem', 'mod_id': '9',
         'timestamp': '2026-09-05T10:00:00+00:00'},
    ]}}, f, ensure_ascii=False)

client = A.app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'
    s['selected_guild'] = '777'
r = client.get('/api/logs')
rows = r.get_json(silent=True) or []
check(r.status_code == 200 and rows, '/api/logs отвечает', f'code={r.status_code}')

mutes = [x for x in rows if x.get('user_id') == '100'
         and A._log_act_class(x.get('action')) == 'mute']
check(len(mutes) == 1, 'дело + журнал склеены в один мут', f'{len(mutes)} строк')
if mutes:
    check(mutes[0].get('duration') == 90,
          'срок из duration_minutes понят единым полем duration',
          f"duration={mutes[0].get('duration')}")
    check('Lina' in str(mutes[0].get('mod_name')),
          'модератор из дела панели', f"{mutes[0].get('mod_name')!r}")
acts = {x.get('action') for x in rows}
check('Мут чата' in acts, 'mute_chat переведён в «Мут чата»', f'{sorted(acts)}')
check('Войс-мут снят' in acts, 'vunmute переведён в «Войс-мут снят»', f'{sorted(acts)}')
check('Участник вошёл' in acts, 'не-наказания по-прежнему в общем журнале')
warns = [x for x in rows if x.get('user_id') == '600']
check(len(warns) == 1 and warns[0].get('reason') == 'капс'
      and 'Artem' in str(warns[0].get('mod_name')),
      'варн из warnings.json: с причиной и модератором',
      f'{warns[:1]}')

print('== Имена вместо голых ID (жалоба 2026-09-06 «проблема с именем») ==')
# 700 — имя знает только кэш участников (member_store): бот офлайн
with open('data/members_777.json', 'w', encoding='utf-8') as f:
    json.dump({'members': {'700': {'id': '700', 'name': 'kicked_boy',
                                   'display_name': 'KickedBoy'}},
               'roles': {}, 'saved_at': 1}, f, ensure_ascii=False)
# 800 — имя осталось только в старой записи журнала (участник вышел)
# 900 — имени нет нигде: честный ID, интерфейс покажет его чипом
with open('data/audit_log.json', 'w', encoding='utf-8') as f:
    json.dump({'777': [
        {'category': 'mod', 'action': 'Кик', 'user_id': '800',
         'user_name': 'gone_but_remembered', 'mod_name': 'Lina',
         'reason': 'старое дело', 'timestamp': T},
        {'category': 'member', 'action': 'Участник вышел', 'user_id': '800',
         'user_name': 'gone_but_remembered', 'timestamp': T},
    ]}, f, ensure_ascii=False)
with open('data/mod_data.json', 'w', encoding='utf-8') as f:
    json.dump({'cases': {'777': [
        {'id': 10, 'action': 'kick', 'user_id': '700', 'mod_id': '7',
         'mod_name': 'Lina', 'reason': 'реклама', 'timestamp': T2},
        {'id': 11, 'action': 'ban', 'user_id': '800', 'mod_id': '7',
         'mod_name': 'Lina', 'reason': 'ушёл с баном', 'timestamp': T},
        {'id': 12, 'action': 'ban', 'user_id': '900', 'mod_id': '7',
         'mod_name': 'Lina', 'reason': 'неизвестный', 'timestamp': T},
    ]}}, f, ensure_ascii=False)
for _p in ('data/audit_log.json', 'data/mod_data.json', 'data/warnings.json',
           'data/members_777.json'):
    A._store.invalidate_path(_p)
rows2 = client.get('/api/logs').get_json(silent=True) or []
r700 = [x for x in rows2 if x.get('user_id') == '700']
check(r700 and r700[0].get('user_name') == 'KickedBoy',
      'имя из кэша участников (member_store) — даже когда бот офлайн',
      f"{r700[:1] and r700[0].get('user_name')!r}")
r800 = [x for x in rows2 if x.get('user_id') == '800'
        and A._log_act_class(x.get('action')) == 'ban']
check(r800 and r800[0].get('user_name') == 'gone_but_remembered',
      'имя из старых записей журнала — участник вышел, имя осталось',
      f"{r800[:1] and r800[0].get('user_name')!r}")
r900 = [x for x in rows2 if x.get('user_id') == '900'
        and A._log_act_class(x.get('action')) == 'ban']
check(r900 and r900[0].get('user_name') == '900',
      'имени нет нигде — остаётся честный ID (интерфейс покажет чипом)',
      f"{r900[:1] and r900[0].get('user_name')!r}")

print('== «Кто выдал»: бот-исполнитель не подменяет модератора (2026-09-07) ==')


class _FU:
    name = 'Moderation'
    display_name = 'Moderation'
    global_name = 'Moderation'
    id = '999888777666555444'


class _FB:
    user = _FU()


_prev_bot = A.bot_instance
A.bot_instance = _FB()
try:
    # 1) склейка: копия панели (человек) против копии аудита (бот «Moderation»)
    merged2 = A._log_merge_duplicates([
        {'guild_id': '777', 'action': 'untimeout', 'user_id': '100',
         'user_name': 'spam_user', 'mod_id': '999888777666555444',
         'mod_name': 'Moderation', 'reason': '', 'timestamp': T,
         'source': 'discord_audit'},
        {'guild_id': '777', 'action': 'untimeout', 'user_id': '100',
         'user_name': 'spam_user', 'mod_id': '', 'mod_name': 'Панель: lina.mod',
         'reason': 'Снят через панель', 'timestamp': T2, 'source': 'panel'},
    ])
    check(len(merged2) == 1 and 'lina.mod' in str(merged2[0].get('mod_name')),
          'склейка: человек из панели выигрывает у бота «Moderation»',
          f"{merged2[:1]}")

    # 2) запись из панели: размьют пишет настоящего модератора
    from web.routes.admin_api import _journal_panel_action
    _journal_panel_action('777', 'Мут снят', 'untimeout', '100', 'spam_user',
                          'sonya.staff', 'Снят через панель (временные меры)')
    from cogs.logs import flush_audit
    flush_audit()
    A._store.invalidate_path('data/audit_log.json')
    rows3 = client.get('/api/logs').get_json(silent=True) or []
    r100 = [x for x in rows3 if x.get('user_id') == '100']
    check(r100 and r100[0].get('mod_name') == 'Панель: sonya.staff',
          'размьют из панели: журнал показывает пользователя панели, не бота',
          f"{r100[:1]}")

    # 3) старое панельное дело: модератор спрятан в причине «[Panel] …»
    with open('data/audit_log.json', 'w', encoding='utf-8') as f:
        json.dump({'777': [
            {'category': 'mod', 'action': 'Мут', 'user_id': '250',
             'user_name': 'old_case', 'mod_id': '999888777666555444',
             'mod_name': 'Moderation', 'reason': '[Panel] artem.mods: Флуд',
             'timestamp': T},
        ]}, f, ensure_ascii=False)
    A._store.invalidate_path('data/audit_log.json')
    rows4 = client.get('/api/logs').get_json(silent=True) or []
    r250 = [x for x in rows4 if x.get('user_id') == '250']
    check(r250 and r250[0].get('mod_name') == 'Панель: artem.mods'
          and r250[0].get('reason') == 'Флуд',
          'старое дело: модератор вытащен из «[Panel] …» причины',
          f"{r250[:1]}")
finally:
    A.bot_instance = _prev_bot

print('== Шаблон: вид «только наказания» и компактная таблица ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'logs.html'),
           encoding='utf-8').read()
for marker, label in [
    ('id="jl-view-pun"', 'переключатель «Только наказания»'),
    ('id="jl-view-all"', 'переключатель «Все события»'),
    ('PUNISH_KINDS', 'фильтр видов наказаний'),
    ('jl-reason', 'причина в две строки'),
    ('fmtDur', 'срок мута в ячейке действия'),
    ('id="stat-total-label"', 'KPI учитывает вид журнала'),
    ('jl-charts', 'компактные графики над таблицей'),
]:
    check(marker in tpl, f'шаблон: {label}')
check('col-sel' not in tpl, 'шаблон: убрана колонка чекбоксов (компактно)')

print('== Шаблон: лента карточек — красивый вид журнала (2026-09-06) ==')
for marker, label in [
    ('id="logs-feed"', 'контейнер ленты'),
    ('jl-card', 'карточка записи'),
    ('TONE_CLASS', 'цвет карточки по виду наказания'),
    ('KIND_ICON', 'иконка плитки по виду наказания'),
    ('id="jl-shape-feed"', 'переключатель «Лента»'),
    ('id="jl-shape-table"', 'переключатель «Таблица» (запасной вид)'),
    ('jl-ava', 'монограмма участника'),
    ('jl-day', 'разделители дней «Сегодня/Вчера»'),
    ('relTime', 'живое «сколько времени назад»'),
    ('id="logs-more"', '«показать ещё» — общий для ленты и таблицы'),
    ('hidden', 'неактивный вид скрыт'),
]:
    check(marker in tpl, f'шаблон: {label}')
check(tpl.index('id="logs-feed"') < tpl.index('id="logs-table-wrap"'),
      'лента идёт раньше таблицы — основной вид')
tpl_tm = open(os.path.join(ROOT, 'web', 'templates', 'temp_moderation.html'),
              encoding='utf-8').read()
check("'unmut'" not in tpl_tm and "'unmute'" in tpl_tm,
      'временные меры: «Снять досрочно» зовёт /unmute (опечатка «unmut» чинена)')

print('== Лента: живой прогон рендера (node-харнесс) ==')
import subprocess  # noqa: E402
node = shutil.which('node')
harness = os.path.join(ROOT, 'tests', '_logs_feed_harness.js')
if node and os.path.exists(harness):
    r = subprocess.run([node, harness], capture_output=True, text=True,
                       timeout=60)
    line = (r.stdout or '').strip().splitlines()[-1] if r.stdout.strip() else ''
    try:
        res = json.loads(line)
    except Exception:
        res = {'ok': False, 'errors': [f'харнесс не ответил: {r.stderr[:200]}'], 'pass': 0}
    for err in res.get('errors', []):
        check(False, f'харнесс: {err}')
    if res.get('ok'):
        check(True, f'харнесс ленты: {res["pass"]} проверок — тон, иконки, '
                    'монограммы, дни, сроки, XSS')
else:
    check(False, 'node-харнес недоступен')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
os.chdir(ROOT)
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
