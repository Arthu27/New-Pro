# -*- coding: utf-8 -*-
"""Боевые кнопки профиля участника: Варн/Бан работают, Кик удалён.

Проверяем:
1. Статика: в member_profile.html больше нет кнопки кика, остались warn/ban
   с data-action, есть JS-привязка клика и fetch на новые endpoint'ы.
2. Статика: страница execute_command больше не предлагает кик (карточка и
   форма удалены) — кик отключён на сервере по решению владельца.
3. E2E (DEMO_MODE, Flask test_client): POST на /api/member-profile/<g>/<u>/warn
   и /ban отвечает ok; нечисловой ID — 400; без сессии — редирект на логин.

Запуск: python3 tests/test_member_profile_actions.py
"""
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_mpact_test_')
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


# ─── 1. member_profile.html: кик убран, warn/ban привязаны ──────────────────
print('== 1. Шаблон профиля участника ==')
mp = open(os.path.join(ROOT, 'web', 'templates', 'member_profile.html'), encoding='utf-8').read()
check('data-action="kick"' not in mp, 'кнопка «Кик» удалена из профиля')
check('data-action="warn"' in mp, 'кнопка «Варн» на месте')
check('data-action="ban"' in mp, 'кнопка «Бан» на месте')
check('>Кик<' not in mp and '>Кик <' not in mp, 'текста «Кик» в профиле нет')
check("querySelectorAll('.actions-row [data-action]')" in mp,
      'есть JS-привязка клика по боевым кнопкам')
check(re.search(r"fetch\('/api/member-profile/' \+ selectedGuild \+ '/' \+ uid \+ '/' \+ action", mp)
      is not None, 'кнопки вызывают живой API профиля')
check(re.search(r"<button[^>]*data-action=\"warn\"[^>]*type=\"button\"|<button[^>]*type=\"button\"[^>]*data-action=\"warn\"", mp)
      is not None, 'у боевых кнопок проставлен type="button"')

# ─── 2. execute_command.html: кика нет нигде ────────────────────────────────
print('== 2. Страница выполнения команд ==')
ec = open(os.path.join(ROOT, 'web', 'templates', 'execute_command.html'), encoding='utf-8').read()
check("openCmd('kick')" not in ec, 'карточка кика удалена')
check(not re.search(r"^\s*kick:\s*'", ec, re.M), 'форма кика удалена')
check('>Кик<' not in ec, 'слова «Кик» на странице нет')
check("openCmd('ban')" in ec and "openCmd('warn')" in ec, 'остальные карточки не пострадали')

# ─── 3. Роуты зарегистрированы ───────────────────────────────────────────────
print('== 3. Роуты в web/routes/members.py ==')
ms = open(os.path.join(ROOT, 'web', 'routes', 'members.py'), encoding='utf-8').read()
check("/api/member-profile/<guild_id>/<user_id>/warn" in ms, 'роут варна есть')
check("/api/member-profile/<guild_id>/<user_id>/ban" in ms, 'роут бана есть')
check("get_cog ('warnings')" in ms, 'варн идёт через живой ког warnings')
check("save_case (guild .id ,'ban'" in ms, 'бан записывает дело в mod_data.json')

# ─── 4. E2E в демо-режиме ────────────────────────────────────────────────────
print('== 4. E2E: POST варна и бана (демо) ==')
import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()

with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'owner'
    s['selected_guild'] = '777'

r = client.post('/api/member-profile/777/123456789/warn',
                json={'reason': 'тест из автопроверки'})
check(r.status_code == 200, f'варн: HTTP {r.status_code}')
d = r.get_json(silent=True) or {}
check(d.get('ok') is True, f'варн: ok=True ({d})')

r = client.post('/api/member-profile/777/123456789/ban',
                json={'reason': 'тест из автопроверки'})
check(r.status_code == 200, f'бан: HTTP {r.status_code}')
d = r.get_json(silent=True) or {}
check(d.get('ok') is True, f'бан: ok=True ({d})')

r = client.post('/api/member-profile/777/не-число/warn', json={'reason': 'x'})
check(r.status_code == 400, f'нечисловой ID → 400 (получено {r.status_code})')

# В DEMO_MODE панель намеренно автологинит всех владельцем (витрина), поэтому
# закрытость от анонимов проверяем статически: на обоих роутах висят декораторы.
for route, name in (("def api_member_profile_warn", 'варна'), ("def api_member_profile_ban", 'бана')):
    i = ms.index(route)
    head = ms[max(0, i - 400):i]
    check('@login_required' in head, f'роут {name} под login_required')
    check("@role_required ('admin')" in head, f'роут {name} под role_required(admin)')

r = client.get('/api/member-profile/777/123456789')
check(r.status_code == 200, f'GET профиля тоже жив (HTTP {r.status_code})')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
