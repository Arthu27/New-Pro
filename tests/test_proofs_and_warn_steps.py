# -*- coding: utf-8 -*-
"""Доказательства (переделка) + роли наказаний с настройками warn.

A. Демки:
1. upload → media_url отдаётся, файл читается (200, правильный content-type).
2. Лайтбокс pf-lb: центр (`align-items: center`, max-height 80vh), backdrop,
   Esc-закрытие, клик по фону закрывает, frame клик — нет.
3. Пикер участника — СТАНДАРТНЫЙ attachMemberPicker с onPick (ни одного
   самописного dropdown'а больше нет).

B. Роли наказаний — «для каждого наказания»:
4. settings_view: kinds+levels как раньше + punish_info (каждое наказание
   видно карточкой, таймаут/кик/разбан объяснены). Ступеней действий здесь
   НЕТ — они на /ladder (единое место, без дублей).
5. ladder API: add → ступень сохранена в общий warn_config (cogs читают
   ключ 'steps'), dedup по count, remove убирает, помойка → 400; vmute —
   отдельное действие (войс-мут ≠ чат-мут).
"""
import io
import os
import json
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix='pf_warn_')
os.chdir(_TMP)
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ['MAIN_GUILD_ID'] = '777'
sys.path.insert(0, ROOT)

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


import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s.update(logged_in=True, username='admin', role='admin', selected_guild='777')

print('== A. Демки: загрузка и просмотр ==')
data = {'file': (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'0' * 300), 'shot.png', 'image/png'),
        'user_id': '123456789012345678', 'user_name': 'Вася',
        'action': 'варн', 'reason': 'тест'}
r = client.post('/api/proofs/upload', data=data, content_type='multipart/form-data')
d = r.get_json() or {}
check(r.status_code == 200 and d.get('success') and d.get('media_url'),
      f'прямая загрузка демки работает ({r.status_code})')
if d.get('media_url'):
    r3 = client.get(d['media_url'])
    check(r3.status_code == 200 and 'image' in (r3.content_type or ''),
          f'демка открывается с диска ({r3.content_type})')
r = client.get('/proofs')
h = r.get_data(as_text=True)
check(r.status_code == 200 and 'pf-lb' in h and 'pf-lb-media' in h,
      'страница демок включает новый лайтбокс')
check("attachMemberPicker($('pf-member')" in h and 'onPick' in h,
      'member-пикер — стандартный, с onPick-колбэком')
check('pf-member-list' not in h and 'pf-pick' not in h,
      'самописный список подсказок вырезан')

css = open(os.path.join(ROOT, 'web/static/style.css'), encoding='utf-8').read()
check('align-items: center' in css[css.index('.pf-lb'):css.index('.pf-lb-frame')],
      'лайтбокс — по центру (не сверху за краем)')
check('max-height: 80vh' in css and 'backdrop-filter' in css and 'z-index: 3000' in css,
      'медиа влезает целиком (80vh), фон-стекло, слой 3000')

print('== B. Роли наказаний: каждое наказание + настройки warn ==')
r = client.get('/api/guild/777/role-settings')
d = r.get_json() or {}
keys_info = [x['key'] for x in d.get('punish_info', [])]
check(set(keys_info) == {'timeout', 'kick', 'unban'}, f'punish_info покрывает все наказания ({keys_info})')
check('warn_steps' not in d, 'на /role-settings ступеней действий больше нет (единое место — /ladder)')
# Ступени действий — ТОЛЬКО через лестницу (/api/.../ladder/*)
r = client.post('/api/guild/777/ladder/add',
                json={'count': 3, 'action': 'mute', 'duration': 30, 'unit': 'minute'})
d = r.get_json() or {}
check(r.status_code == 200 and d.get('success'), f'ступень add ({r.status_code})')
from cogs.warnings import load_warn_config  # noqa: E402
cfg = load_warn_config('777')
steps = cfg.get('steps') or []
check(any(int(s.get('count', 0)) == 3 and s.get('action') == 'mute' for s in steps),
      f'ступень лежит в общем warn_config, которое читает ког ({steps})')
# войс-мут — отдельное действие
rv = client.post('/api/guild/777/ladder/add',
                 json={'count': 2, 'action': 'vmute', 'duration': 15, 'unit': 'minute'})
rvj = rv.get_json() or {}
check(rv.status_code == 200 and rvj.get('success'), f'войс-мут как ступень принят ({rv.status_code})')
r2 = client.post('/api/guild/777/ladder/add',
                 json={'count': 3, 'action': 'kick'})
steps2 = r2.get_json().get('steps', [])
check(r2.status_code == 200 and len([s for s in steps2 if int(s.get('count', 0)) == 3]) == 1,
      'степень с тем же count — заменяется, не дублируется')
r3 = client.get('/api/guild/777/ladder/view')
vsteps = (r3.get_json() or {}).get('steps', [])
check(any(s.get('action') == 'vmute' for s in vsteps)
      and any(s.get('action') == 'kick' and int(s.get('count', 0)) == 3 for s in vsteps),
      'ladder/view отдаёт и войс-мут, и заменённый кик')
r4 = client.post('/api/guild/777/ladder/remove', json={'count': 3})
check(r4.status_code == 200 and r4.get_json().get('success'), 'remove убирает ступень')
r5 = client.post('/api/guild/777/ladder/add', json={'count': 'x', 'action': 'bogus'})
check(r5.status_code == 400 and not r5.get_json().get('success'), 'мусор в add → 400')
# старый role-settings warn-step маршрут удалён
r6 = client.post('/api/guild/777/role-settings/warn-step', json={'count': 1, 'action': 'mute'})
check(r6.status_code == 404, 'дублирующий warn-step на /role-settings больше не существует')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
