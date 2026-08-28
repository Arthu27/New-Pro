# -*- coding: utf-8 -*-
"""Авто-остывание статуса нарушителя (services/freshness).

Пороги — свой файл (warn_config пересобирается лестницей и стёр бы ключи),
уровни hot/warm/cold/clean считаются от последнего нарушения (варны +
мод-аудит), в карточке 360° блок «Статус нарушителя», настройки — на
странице лестницы (admin+).

Запуск: python3 tests/test_freshness.py
"""
import importlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

_TMP = tempfile.mkdtemp(prefix='hakumo_fresh_test_')
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


from services import freshness as FSH  # noqa: E402

NOW = datetime.now()

print('== 1. пороги ==')
c = FSH.cooldown_config('777')
check(c == {'warm_days': 14, 'cold_days': 45}, f'дефолты 14/45: {c}')
cfg, err = FSH.save_cooldown_config('777', 7, 30)
check(err is None and cfg == {'warm_days': 7, 'cold_days': 30},
      'пороги сохраняются в свой файл')
cfg, err = FSH.save_cooldown_config('777', 40, 10)
check(cfg is None and 'позже' in err, 'cold <= warm отклонён словами')
c = FSH.cooldown_config('777')
check(c['warm_days'] == 7 and c['cold_days'] == 30, 'конфиг читается обратно')

print('== 2. уровни остывания ==')
check(FSH.freshness_of('777', '1')['level'] == 'clean',
      'чистый участник — «Чистый» без цифр')


def warn_at(days_ago):
    json.dump({'777': {'1': [{'id': 1, 'reason': 'флуд', 'mod': 'Мод',
                              'timestamp': (NOW - timedelta(days=days_ago)).isoformat()}]}},
              open('data/warnings.json', 'w', encoding='utf-8'))


def audit_at(days_ago, uid='1'):
    json.dump({'777': [{'category': 'mod', 'action': 'mute', 'user_id': uid,
                        'mod_name': 'Мод',
                        'timestamp': (NOW - timedelta(days=days_ago)).isoformat()}]},
              open('data/audit_log.json', 'w', encoding='utf-8'))


warn_at(2)
f = FSH.freshness_of('777', '1', now=NOW)
check(f['level'] == 'hot' and f['days_without'] == 2 and 'тёплого' in f['to_next'],
      f'2 дня после варна — горячий ({f["days_without"]} дн)')
warn_at(10)
f = FSH.freshness_of('777', '1', now=NOW)
check(f['level'] == 'warm' and 0 < f['progress'] < 100,
      f'10 дней — тёплый, прогресс {f["progress"]}%')
warn_at(60)
f = FSH.freshness_of('777', '1', now=NOW)
check(f['level'] == 'cold' and f['progress'] == 100,
      '60 дней — холодный, шкала полная')
# аудит свежее варнов — дата берётся максимальная
warn_at(60)
audit_at(3)
f = FSH.freshness_of('777', '1', now=NOW)
check(f['level'] == 'hot' and f['days_without'] == 3,
      'свежее событие аудита перебивает старый варн')
check(FSH.freshness_of('777', '2', now=NOW)['level'] == 'clean',
      'чужой участник не подхватывает чужие нарушения')

print('== 3. веб ==')
appmod = importlib.import_module('web.app')
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


login('owner')
# пороги на странице лестницы
r = client.get('/api/guild/777/ladder/view').get_json()
check(r.get('success') and r['cooldown']['warm_days'] == 7,
      'пороги приезжают в обзор лестницы')
r = client.post('/api/guild/777/ladder/cooldown',
                json={'warm_days': 10, 'cold_days': 25})
check(r.get_json().get('success'), 'сохранение порогов через лестницу')
c = FSH.cooldown_config('777')
check(c == {'warm_days': 10, 'cold_days': 25}, 'пороги применились')
r = client.post('/api/guild/777/ladder/cooldown',
                json={'warm_days': 30, 'cold_days': 3})
check(r.status_code == 400, 'битая пара порогов — 400')
login('mod')
r = client.post('/api/guild/777/ladder/cooldown',
                json={'warm_days': 1, 'cold_days': 2})
check(r.status_code in (302, 401, 403), 'меняет только admin+')

# карточка 360° несёт блок остывания
login('owner')
r = client.get('/api/guild/777/member-card/lookup?user=1').get_json()
check(r.get('success') and r['card'].get('freshness')
      and r['card']['freshness']['level'] in ('hot', 'warm', 'cold', 'clean'),
      'freshness в досье участника')
mf = r['card']['freshness']
check(mf['days_without'] == 3 and mf['label'] and mf['to_next'],
      'детали остывания: дни, ярлык, до следующего уровня')
js = open(os.path.join(ROOT, 'web', 'static', 'member_card.js'), encoding='utf-8').read()
check('Статус нарушителя' in js and 'Прогресс остывания' in js,
      'рендер блока в общей карточке')
lt = open(os.path.join(ROOT, 'web', 'templates', 'ladder.html'), encoding='utf-8').read()
check('id="ldWarmDays"' in lt and 'id="ldColdDays"' in lt and "'/cooldown'" in lt,
      'форма порогов на странице лестницы')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
