# -*- coding: utf-8 -*-
"""Регистрация/вход при имени, введённом НЕ ПОЛНОСТЬЮ (жалоба владельца
2026-09-05: «пишет своё имя не полностью, панель находит её по подсказкам,
но регистрация говорит, что не нашла»).

Причина была в том, что разыменование ника принимало только ТОЧНОЕ полное
имя: подсказки ищут по вхождению, а форма отправляла недопечатанный ник →
«Не нашёл участника». Теперь:
  • клик по подсказке передаёт точный Discord ID скрытым полем resolved_id
    (сервер не угадывает имя вовсе);
  • недопечатанное имя разрешается, если кандидат по началу имени РОВНО
    ОДИН; если несколько — честная просьба выбрать себя из подсказок.
Запуск: python3 tests/test_register_nick.py
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix='reg_nick_')
os.chdir(WORK)
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

os.environ['DEMO_MODE'] = '1'
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DB_PATH'] = os.path.join(WORK, 'data', 'bot.db')

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


# Состав сервера на диске: живой кэш discord.py ПУСТ (реальный сценарий)
with open('data/members_777.json', 'w', encoding='utf-8') as f:
    json.dump({'saved_at': '2026-09-05T00:00:00', 'sig': 1, 'members': {
        '3001': {'id': '3001', 'name': 'anna', 'display_name': 'Анна Киселёва',
                 'bot': False, 'avatar': ''},
        '3002': {'id': '3002', 'name': 'anna_p', 'display_name': 'Анна П.',
                 'bot': False, 'avatar': ''},
        '3003': {'id': '3003', 'name': 'boris', 'display_name': 'Борис',
                 'bot': False, 'avatar': ''},
    }}, f)

import web.app as appmod  # noqa: E402

# живого кэша нет — как на бою, пока бот не прогрелся
appmod._panel_guild_orig = getattr(appmod, '_panel_guild_orig', appmod._panel_guild)
appmod._panel_guild = lambda: None
try:
    print('== Имя не полностью — уникальный кандидат ==')
    check(appmod._resolve_nick_anywhere('Анна Кис') == '3001',
          '«Анна Кис» (начало имени) → ID 3001')
    check(appmod._resolve_nick_anywhere('Борис') == '3003',
          'точное имя по-прежнему работает')
    check(appmod._resolve_nick_anywhere('@boris') == '3003',
          'ник с @ и латиницей работает')

    print('== Имя не полностью — несколько кандидатов ==')
    r = appmod._resolve_nick_anywhere('Анна')
    check(isinstance(r, list) and len(r) == 2,
          '«Анна» (две Анны) → список кандидатов, а не ошибка «не нашла»',
          f'→ {r}')
    check(appmod._resolve_nick_anywhere('Анна Киселёва') == '3001',
          'полное имя среди двух Анн выбирает правильную')

    print('== Никого не нашли — честный None ==')
    check(appmod._resolve_nick_anywhere('Такого-Нет') is None,
          'несуществующее имя → None (форма покажет «выбери из подсказок»)')

    print('== Скрытое поле resolved_id в формах ==')
    reg = open(os.path.join(ROOT, 'web', 'templates', 'register.html'),
               encoding='utf-8').read()
    login = open(os.path.join(ROOT, 'web', 'templates', 'login.html'),
                 encoding='utf-8').read()
    check('name="resolved_id"' in reg and 'name="resolved_id"' in login,
          'resolved_id есть в обеих формах (регистрация и вход)')
    check('rid.value = it.dataset.id' in reg and 'rid.value = it.dataset.id' in login,
          'клик по подсказке запоминает точный Discord ID')
    check("ridEl.value = ''" in reg and "ridEl.value = ''" in login,
          'ручной ввод имени сбрасывает запомненный ID')
    asrc = open(os.path.join(ROOT, 'web', 'app.py'), encoding='utf-8').read()
    check("request .form .get ('resolved_id'" in asrc,
          'сервер принимает resolved_id: имя больше не единственный путь')
finally:
    appmod._panel_guild = appmod._panel_guild_orig

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
