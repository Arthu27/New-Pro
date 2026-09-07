# -*- coding: utf-8 -*-
"""«История решений»: срок мута и причина видны, дубли склеены.

Жалоба владельца: «в панельке не видно, насколько дали мут и по какой
причине — вижу только кто, кого и когда». Проверяем /api/mod-history:

  1. дело бота с duration_minutes/until отдаёт поля duration и until;
  2. срок понимается и в строковом виде ('2ч' → 120), 'Belirtilmedi'
     переведён в «Не указана»;
  3. мут из аудита Discord несёт срок (duration_minutes → duration);
  4. дубль «дело панели + аудит» склеивается в ОДНУ строку: настоящий
     модератор, причина панели, срок из дела;
  5. старое дело-заглушка «С Discord» подтягивает причину и модератора
     из аудита (для ручных мутов через интерфейс Discord);
  6. два настоящих варна подряд НЕ склеиваются (это не дубли);
  7. чужие серверы по-прежнему не просачиваются.

Запуск: python3 tests/test_mod_history_duration.py
"""
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_modhist_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['DEMO_MODE'] = '1'
os.environ.pop('TOKEN', None)
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'preview123'

PASS = 0
FAIL = 0


def check(cond, label, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


print('== /api/mod-history: срок и причина мута ==')
import web.app as A  # noqa: E402

MAIN = '111222333444555666'
FOREIGN = '999888777666555444'
A.MAIN_GUILD_ID = MAIN

TS = '2026-09-05T18:00:00+00:00'
TS2 = '2026-09-05T18:01:20+00:00'      # дубль из аудита — на минуту позже
UNTIL = '2026-09-05T20:00:00+00:00'

# 1) дело панели: мут со сроком и «до какого времени»
# 2) дело с турецким легаси-дефолтом причины и строковым сроком
# 3) мут вручную из Discord: заглушка «С Discord» + запись аудита с причиной
with open('data/mod_data.json', 'w', encoding='utf-8') as f:
    json.dump({'cases': {MAIN: [
        {'id': 1, 'action': 'timeout', 'user_id': '100', 'mod_id': '7',
         'mod_name': 'Lina', 'reason': 'Флуд в общем чате',
         'duration_minutes': 120, 'until': UNTIL, 'timestamp': TS},
        {'id': 2, 'action': 'mute', 'user_id': '200', 'mod_id': '8',
         'reason': 'Belirtilmedi', 'duration': '2ч', 'timestamp': TS},
        {'id': 3, 'action': 'timeout', 'user_id': '300', 'mod_id': 'system',
         'mod_name': 'Discord', 'reason': 'С Discord', 'timestamp': TS2},
    ], FOREIGN: [
        {'id': 9, 'action': 'timeout', 'user_id': '1', 'mod_id': '2',
         'reason': 'чужой мут', 'duration_minutes': 60, 'timestamp': TS},
    ]}}, f, ensure_ascii=False)

# аудит: дубль мута №1 (исполнитель — сам бот) и «настоящий» мут №3
with open('data/discord_audit_cache.json', 'w', encoding='utf-8') as f:
    json.dump({MAIN: [
        {'category': 'mod', 'action': 'Мут', 'target_name': 'spam_user',
         'target_id': '100', 'mod_name': 'Hakumo', 'mod_id': '999',
         'reason': 'Флуд в общем чате', 'timestamp': TS2,
         'duration_minutes': 120, 'until': UNTIL, 'source': 'discord_audit'},
        {'category': 'mod', 'action': 'Мут', 'target_name': 'manual_user',
         'target_id': '300', 'mod_name': 'Sabotash', 'mod_id': '55',
         'reason': 'Оскорбления в голосовом', 'timestamp': '2026-09-05T18:01:40+00:00',
         'duration_minutes': 30, 'source': 'discord_audit'},
    ], FOREIGN: [
        {'category': 'mod', 'action': 'Мут', 'target_id': '1',
         'mod_name': 'x', 'reason': 'чужой', 'timestamp': TS},
    ]}, f, ensure_ascii=False)

# два настоящих варна подряд — НЕ дубли, склеивать нельзя
with open('data/warnings.json', 'w', encoding='utf-8') as f:
    json.dump({MAIN: {'400': [
        {'id': 1, 'reason': 'капс', 'mod': 'Lina', 'mod_id': '7',
         'timestamp': '2026-09-05T18:05:00+00:00'},
        {'id': 2, 'reason': 'офтоп', 'mod': 'Sonya', 'mod_id': '8',
         'timestamp': '2026-09-05T18:06:30+00:00'},
    ]}}, f, ensure_ascii=False)

c = A.app.test_client()
with c.session_transaction() as sess:
    sess['logged_in'] = True
    sess['username'] = 't'
    sess['role'] = 'owner'

r = c.get('/api/mod-history')
rows = r.get_json(silent=True) or []
check(r.status_code == 200 and isinstance(rows, list) and rows,
      'история отдаётся', f'code={r.status_code} rows={len(rows)}')
check(all(str(x.get('guild_id')) == MAIN for x in rows),
      'изоляция: только главный сервер',
      f'{[x.get("guild_id") for x in rows][:6]}')
check(not any('чужой' in str(x.get('reason', '')).lower() for x in rows),
      'изоляция: чужие причины не просочились')

# ── 1. Дубль «дело + аудит» склеен в одну строку с лучшими данными ──
mutes_100 = [x for x in rows if str(x.get('target_id')) == '100']
check(len(mutes_100) == 1,
      'мут из /modpanel показан ОДНОЙ строкой (дело+аудит склеены)',
      f'{len(mutes_100)} строк')
if mutes_100:
    m = mutes_100[0]
    check(m.get('duration') == 120, 'срок мута виден (120 минут)',
          f'duration={m.get("duration")}')
    check(m.get('until') == UNTIL, '«до какого времени» виден', f'until={m.get("until")}')
    check(m.get('reason') == 'Флуд в общем чате', 'причина на месте',
          f'reason={m.get("reason")!r}')
    check('Lina' in str(m.get('mod_name')), 'модератор — человек из дела, не бот',
          f'mod_name={m.get("mod_name")!r}')

# ── 2. Легаси-данные: строковый срок и турецкий дефолт причины ──
mutes_200 = [x for x in rows if str(x.get('target_id')) == '200']
check(len(mutes_200) == 1 and mutes_200[0].get('duration') == 120,
      "строковый срок '2ч' понят как 120 минут",
      f'{[x.get("duration") for x in mutes_200]}')
check(len(mutes_200) == 1 and mutes_200[0].get('reason') == 'Не указана',
      "легаси 'Belirtilmedi' → «Не указана»",
      f'{[x.get("reason") for x in mutes_200]}')

# ── 3. Ручной мут из Discord: причина и модератор из аудита ──
mutes_300 = [x for x in rows if str(x.get('target_id')) == '300']
check(len(mutes_300) == 1,
      'заглушка «С Discord» склеена с аудитом в одну строку',
      f'{len(mutes_300)} строк')
if mutes_300:
    m = mutes_300[0]
    check(m.get('reason') == 'Оскорбления в голосовом',
          'причина ручного мута взята из аудита', f'reason={m.get("reason")!r}')
    check('Sabotash' in str(m.get('mod_name')),
          'модератор ручного мута — из аудита', f'mod_name={m.get("mod_name")!r}')
    check(m.get('duration') == 30, 'срок ручного мута — из аудита',
          f'duration={m.get("duration")}')

# ── 4. Два настоящих варна подряд не склеены ──
warns = [x for x in rows if str(x.get('target_id')) == '400']
check(len(warns) == 2, 'два разных варна остались двумя строками',
      f'{len(warns)}')

# ── 5. Поле duration_minutes нормализовано в duration ──
raw_keys = [k for x in rows for k in x if k == 'duration_minutes']
check(not raw_keys, 'наружу отдаётся только нормализованный duration')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
import shutil
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
