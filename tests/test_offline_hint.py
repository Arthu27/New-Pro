# -*- coding: utf-8 -*-
"""«Кнопки не работают» → на самом деле тост «Ошибка: Бот офлайн».

Две причины чиним:
1. В DEMO-витрине мутации каналов не должны пугать офлайн-ошибкой —
   возвращают demo-success (страница остаётся живой для просмотра).
2. Голое «Бот офлайн» из любого эндпоинта централизованно переписывается
   на человеческую подсказку «...запусти его через start.bat...» —
   владелец понимает, что делать, а не пишет «сломано».

Запуск: python3 tests/test_offline_hint.py
"""
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_offhint_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DEMO_MODE'] = '1'

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


print('== 1. Статика ==')
ca = open(os.path.join(ROOT, 'web', 'routes', 'channels_admin.py'), encoding='utf-8').read()
check(ca.count("_app ._demo_mode ():return jsonify ({'success':True ,'demo':True })") == 3,
      'create/update/delete каналов: демо-ответ в трёх мутациях')
app_src = open(os.path.join(ROOT, 'web', 'app.py'), encoding='utf-8').read()
check("_d .get ('error')=='Бот офлайн'" in app_src and 'start.bat' in app_src,
      'after_request: голый «Бот офлайн» переписывается на подсказку')

print('== 2. E2E (демо) ==')
import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'owner'
    s['selected_guild'] = '777'

r = client.post('/api/guild/777/channels/create',
                json={'name': 'тестовый', 'type': 'text'})
d = r.get_json(silent=True) or {}
check(r.status_code == 200 and d.get('success') is True,
      f'create: демо-успех вместо «Бот офлайн» (HTTP {r.status_code}: {d})')

r = client.post('/api/guild/777/channels/5001/update', json={'name': 'новый'})
d = r.get_json(silent=True) or {}
check(r.status_code == 200 and d.get('success') is True, f'update: демо-успех ({d})')

r = client.post('/api/guild/777/channels/5001/delete')
d = r.get_json(silent=True) or {}
check(r.status_code == 200 and d.get('success') is True, f'delete: демо-успех ({d})')

# эндпоинт БЕЗ демо-ветки: голое «Бот офлайн» обязано переписаться после after_request
r = client.post('/api/temp-mod/mute', json={'user_id': '123', 'duration': '1h'})
d = r.get_json(silent=True) or {}
err = d.get('error') or ''
check('start.bat' in err and err != 'Бот офлайн',
      f'голое «Бот офлайн» стало человеческой подсказкой: {err!r}')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
