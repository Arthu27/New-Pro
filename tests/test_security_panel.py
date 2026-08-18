# -*- coding: utf-8 -*-
"""Центр безопасности (идеи #131-135).

Настройки частичного файла 1:1 с /security (get-дефолты), тоглы и порог
новых аккаунтов, сканер ссылок (точное + поддомен), фейк-аккаунт на
настоящем скорере кога, спам-симуляция на живом msg_history, справочник
правил, CSV, права, шаблон, меню.

Запуск: python3 tests/test_security_panel.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_security_test_')
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


from cogs import security as SC  # noqa: E402
from web.routes import security_panel as SP  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')

json.dump({'ai_spam': False, 'link_scanner': True},
          open('data/security_777.json', 'w', encoding='utf-8'))

print('== 1. Настройки 1:1 ==')
view = SP.cfg_view(SP._load('777'))
feats = {f['key']: f for f in view['features']}
check(feats['ai_spam']['status'] == ' Закрыт' and feats['link_scanner']['status'] == ' Активен',
      'флаги из файла словами бота')
check(feats['fake_account']['enabled'] is False,
      'частичный файл: отсутствующий ключ — выкл, как у кога (get без дефолта)')
check(view['new_account_days'] == 7 and view['new_account_action'] == 'warn',
      'дефолты порога')
ok, err, _ = SP.toggle_feature('777', 'мимо', True)
check(not ok and err == 'Неизвестная функция безопасности', 'чужой ключ не трогаем')
ok, err, payload = SP.toggle_feature('777', 'fake_account', True)
check(ok and payload['status'] == ' Активен', 'включили фейк-детект')
check(SP._load('777')['fake_account'] is True, 'записано в файл бота')
ok, err, _ = SP.set_newaccount('777', 'abc', 'warn')
check(not ok and err == 'Порог — число дней', 'не число')
ok, err, _ = SP.set_newaccount('777', '0', 'warn')
check(not ok and err == 'Порог: от 1 до 365 дней', 'границы порога')
ok, err, _ = SP.set_newaccount('777', '10', 'yeet')
check(not ok and err == 'Действие: warn, kick или ban', 'действия — из choices бота')
ok, err, payload = SP.set_newaccount('777', '10', 'ban')
check(ok and payload['message'] == 'Порог: 10 дн., действие: ban', 'порог записан')
check(SP._load('777')['new_account_action'] == 'ban', 'действие в файле')

print('== 2. Сканер ссылок ==')
r = SP.scan_text('лови нитро https://grabify.link/x и ещё https://google.com')
check(r['malicious'] is True and r['domains'] == ['grabify.link'], 'точное совпадение')
check('google.com' in r['extracted'] and 'grabify.link' in r['extracted'],
      'оба домена извлечены')
r = SP.scan_text('зайди на https://evil.grabify.link/scam')
check(r['malicious'] is True and r['domains'] == ['evil.grabify.link'],
      'поддомен ловится, как у кога')
r = SP.scan_text('обычный текст https://discord.com/channels/1')
check(r['malicious'] is False and r['domains'] == [], 'чистая ссылка')
r = SP.scan_text('без ссылок вообще')
check(r['malicious'] is False and r['extracted'] == [], 'без ссылок — пусто')

print('== 3. Фейк-аккаунт ==')
cfg = SP._load('777')  # порог уже 10
ok, err, d = SP.fake_account_preview('0', 'Free Nitro Admin1234', cfg)
check(ok and d['score'] == 1.0 and len(d['warnings']) == 3 and d['suspicious_name'],
      'максимально рыжий: возраст+аватар+имя → cap 1.0')
ok, err, d = SP.fake_account_preview('5', 'Обычная Маша', cfg, avatar_default=False)
check(ok and d['score'] == 0.3 and len(d['warnings']) == 1
      and not d['suspicious_name'], 'по порогу 10: только +0.3 за возраст')
ok, err, d = SP.fake_account_preview('30', 'Маша', cfg, avatar_default=False)
check(ok and d['score'] == 0.0 and d['warnings'] == [], 'чистый профиль — нули')
ok, err, _ = SP.fake_account_preview('x', 'Имя', cfg)
check(not ok and err == 'Возраст — число дней', 'возраст не число')
ok, err, _ = SP.fake_account_preview('-1', 'Имя', cfg)
check(not ok and err == 'Возраст: от 0 до 3650 дней', 'возраст вне диапазона')

print('== 4. Спам-симуляция ==')
ok, err, d = SP.spam_simulate('зайди на мой сайт', '5')
scores = [t['score'] for t in d['trail']]
check(ok and scores == [0.0, 0.475, 0.6, 0.725, 0.783],
      f'траектория скора 1:1 с когом (пришла {scores})')
check(d['trail'][0]['reason'] == 'normal' and 'повтор' in d['trail'][-1]['reason'],
      'причины нарастают')
ok, err, _ = SP.spam_simulate('текст', '13')
check(not ok and err == 'От 1 до 12 сообщений в симуляции', 'лимит симуляции')
ok, err, _ = SP.spam_simulate('текст', 'x')
check(not ok and err == 'Сколько раз — число', 'не число')

print('== 5. Справочник и CSV ==')
ref = SP.rules_reference()
check(ref['domains_total'] == 22 and ref['patterns_total'] == 9,
      'двадцать два домена, девять паттернов кога')
check('discord.gift' in ref['domains'] and ref['domains'] == sorted(ref['domains']),
      'домены отсортированы')
rows = SP.csv_rows(SP._load('777'))
check(rows[0] == ('section', 'key', 'value') and len(rows) == 38,
      f'шапка + 37 строк (пришло {len(rows)})')
check(('feature', 'ai_spam', 'Закрыт') in rows and ('new_account', 'action', 'ban') in rows,
      'настройки в выгрузке')

print('== 6. API и права ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


OV = '/api/guild/777/security-center/overview'
check(client.get('/security').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.get(OV).status_code in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get(OV).status_code == 403, 'uye нельзя')
login('mod')
page = client.get('/security')
check(page.status_code == 200 and 'Центр безопасности' in page.get_data(as_text=True),
      'mod открывает страницу')
ov = client.get(OV).get_json()
check(ov['success'] and ov['can_edit'] is False, 'mod без права тоглов')
check(ov['cfg']['new_account_days'] == 10 and ov['rules']['domains_total'] == 22,
      'обзор видит записанное')
r = client.post('/api/guild/777/security-center/scan', json={'text': ''})
check(r.status_code == 400 and r.get_json()['error'] == 'Пустой текст — нечего сканировать',
      'пустой скан — 400')
r = client.post('/api/guild/777/security-center/scan',
                json={'text': 'https://discord-nitro.gift/claim'})
check(r.get_json()['malicious'] is True, 'нитро-скам пойман через API')
r = client.post('/api/guild/777/security-center/toggle',
                json={'feature': 'ai_spam', 'enabled': True})
check(r.status_code == 403, 'mod не тоглит')
login('admin')
r = client.post('/api/guild/777/security-center/toggle',
                json={'feature': 'ai_spam', 'enabled': True})
check(r.get_json()['success'] and SP._load('777')['ai_spam'] is True, 'admin тоглит')
r = client.post('/api/guild/777/security-center/newaccount',
                json={'days': '14', 'action': 'kick'})
check(r.get_json()['success'] and SP._load('777')['new_account_days'] == 14,
      'admin меняет порог')
r = client.post('/api/guild/777/security-center/fake-score',
                json={'age_days': '0', 'name': 'steam gift support1234'})
check(r.get_json()['score'] >= 0.9, 'песочница через API')
r = client.post('/api/guild/777/security-center/spam-sim',
                json={'content': 'тест', 'times': '5'})
check(r.get_json()['final']['score'] == 0.813,
      'API: короткий текст (+0.03 за аномалию длины) — тоже 1:1')

login('mod')
csv_r = client.get('/api/guild/777/security-center/export.csv')
body = csv_r.get_data(as_text=True)
check(csv_r.status_code == 200
      and 'security_777.csv' in csv_r.headers.get('Content-Disposition', ''), 'имя файла')
check(body.startswith('\ufeffsection;key;value'), 'BOM + шапка')
check('malicious_domain;domain;discord.gift' in body
      and 'name_pattern;regex;giveaway' in body, 'правила в выгрузке')
check(len(body.strip().split('\n')) == 38, 'строк в выгрузке')
login('uye')
check(client.get('/api/guild/777/security-center/export.csv').status_code == 403,
      'uye не выгружает')

print('== 7. Шаблон, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/security.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
base_tpl = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('data-theme="light"' in base_tpl, 'светлая тема учтена (общий shell)')
for fid in ('scKpis', 'scScanText', 'scFakeAge', 'scSpamText', 'scRules', 'scCsv',
            'scDays', 'scAction'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check("'/overview'" in tpl and "'/toggle'" in tpl and "'/scan'" in tpl
      and "'/fake-score'" in tpl and "'/spam-sim'" in tpl and '/export.csv' in tpl,
      'API-пути в шаблоне')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
import services.panel_menu as PM
mod_pages = [pg['path'] for g in PM.MENU if g['key'] == 'mod' for pg in g['pages']]
check('/security' in mod_pages, 'пункт меню «Безопасность» в «Модерации»')
check(PM.PAGE_COGS.get('/security') == ('security',), 'security-ког привязан')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('security_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
