# -*- coding: utf-8 -*-
"""«Выключи все настройки — включать будем сами» (заказ владельца).

1. Дефолты защиты — ВЫКЛ (opt-in): anti_alt, impersonation, security,
   guardian, auto_filter, ai_moderation. Ничего не работает, пока владелец
   сам не включит (панель «Контур защиты» или команды).
2. Фолбэки .get(key, default) в рантайме тоже False — не пробуждаются сами.
3. protection_reset_all: живая кнопка «Выключить всё» гасит уже сохранённые
   True во всех сторах разом (пороги/списки НЕ трогает), идемпотентна.
4. HTTP-эндпоинт сброса работает из панели.

Запуск: python3 tests/test_optin_defaults.py
"""
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_optin_test_')
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


GID = 777

# ── 1. Дефолты всех щитов — ВЫКЛ ────────────────────────────────────────────
print('\n[1] Дефолты защиты — opt-in:')
from cogs import anti_alt, impersonation, security, guardian, auto_filter, ai_moderation

check(anti_alt.DEFAULT_SETTINGS.get('enabled') is False, 'anti_alt: дефолт ВЫКЛ')
check(impersonation.DEFAULT_CFG.get('enabled') is False, 'impersonation(antifake): дефолт ВЫКЛ')
check(all(security._CFG_DEFAULT.get(k) is False for k in ('ai_spam', 'fake_account', 'link_scanner')),
      'security: все три контура дефолт ВЫКЛ')
check(guardian.guardian_default().get('enabled') is False, 'guardian: дефолт ВЫКЛ (пороги на месте)')

fc = auto_filter.merge_config({})
check(fc['enabled'] is False, 'auto_filter: дефолт ВЫКЛ')
check(all(fc[s]['enabled'] is False for s in ('words', 'links', 'caps', 'flood')),
      'auto_filter: все секции дефолт ВЫКЛ')

aim = ai_moderation.AIModeration._default_config(object())
check(aim.get('enabled') is False, 'ai_moderation: дефолт ВЫКЛ')

# classify_message при выключенном корне — полная тишина
cfg_off = auto_filter.merge_config({})
check(auto_filter.classify_message(cfg_off, 'казино https://evil.com АААА') == [],
      'auto_filter ВЫКЛ: ничего не фильтруется, пока не включат')

# ── 2. Рантайм-фолбэки не пробуждают защиту сами ────────────────────────────
print('\n[2] Рантайм-фолбэки — False:')
src_sec = open(os.path.join(ROOT, 'cogs', 'security.py'), encoding='utf-8').read()
check("cfg .get ('link_scanner',False )" in src_sec, 'security: link_scanner-фолбэк False')
check("cfg .get ('ai_spam',False )" in src_sec, 'security: ai_spam-фолбэк False')
src_aim = open(os.path.join(ROOT, 'cogs', 'ai_moderation.py'), encoding='utf-8').read()
check('config .get ("enabled",False )' in src_aim, 'ai_moderation: enabled-фолбэк False')

# ── 3. protection_reset_all гасит сохранённые True со всех сторов ───────────
print('\n[3] protection_reset_all («Выключить всё»):')
import json
from web.routes.security_panel import protection_reset_all

# Рассылаем «включённость» по всем сторам — как после старых бутов
def _w(path, data):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False)

_w(f'data/security_{GID}.json', {'ai_spam': True, 'fake_account': True, 'link_scanner': True,
                                'new_account_days': 21, 'new_account_action': 'ban', 'log_channel': 123})
_w('data/antifake.json', {str(GID): {'enabled': True, 'action': 'jail', 'check_join': True}})
_w(f'data/autofilter_{GID}.json', {'enabled': True,
                                   'words': {'enabled': True, 'action': 'timeout', 'list': ['казино']},
                                   'links': {'enabled': True, 'action': 'delete', 'whitelist': ['ok.ru']},
                                   'caps': {'enabled': True, 'action': 'delete', 'percent': 50, 'min_length': 5},
                                   'flood': {'enabled': True, 'action': 'timeout', 'limit': 3, 'seconds': 4}})
_w(f'data/guardian_{GID}.json', {**guardian.guardian_default(), 'enabled': True})
_w(f'data/ai_mod_config_{GID}.json', {**aim, 'enabled': True})
from db import GuildData
GuildData('anti_alt').set(GID, 'settings', {'enabled': True, 'action': 'ban', 'min_age_days': 30})

flipped = protection_reset_all(GID)
check(len(flipped) >= 5, f'сброшено систем: {len(flipped)} (>=5): {flipped}')

cfg = json.load(open(f'data/security_{GID}.json', encoding='utf-8'))
check(cfg['ai_spam'] is False and cfg['fake_account'] is False and cfg['link_scanner'] is False,
      'security: три флага погашены')
check(cfg['new_account_days'] == 21 and cfg['new_account_action'] == 'ban',
      'security: пороги/действие сохранились (тушили только тумблеры)')

cfg = json.load(open('data/antifake.json', encoding='utf-8'))[str(GID)]
check(cfg['enabled'] is False and cfg['action'] == 'jail', 'antifake: выкл, действие сохранено')

cfg = json.load(open(f'data/autofilter_{GID}.json', encoding='utf-8'))
check(cfg['enabled'] is False
      and all(cfg[s]['enabled'] is False for s in ('words', 'links', 'caps', 'flood')),
      'auto_filter: корень и все секции погашены')
check(cfg['words']['list'] == ['казино'] and cfg['links']['whitelist'] == ['ok.ru'],
      'auto_filter: списки/вайтлист сохранились')

cfg = json.load(open(f'data/guardian_{GID}.json', encoding='utf-8'))
check(cfg['enabled'] is False and cfg['punishment'] == 'strip', 'guardian: выкл, мера сохранена')

cfg = json.load(open(f'data/ai_mod_config_{GID}.json', encoding='utf-8'))
check(cfg['enabled'] is False, 'ai_moderation: выкл')

back = anti_alt.merge_settings(GuildData('anti_alt').get(GID, 'settings', {}))
check(back['enabled'] is False and back['action'] == 'ban' and back['min_age_days'] == 30,
      'anti_alt: выкл, действие/возраст сохранены')

flipped2 = protection_reset_all(GID)
check(isinstance(flipped2, list), 'повторный сброс не падает (идемпотентен)')

# ── 4. HTTP-эндпоинт сброса из панели ───────────────────────────────────────
print('\n[4] Эндпоинт /security-center/protection-reset:')
from web.app import app as flask_app
flask_app.config['TESTING'] = True
client = flask_app.test_client()

# Сбросим всё в True снова, теперь через стор центра
_w(f'data/security_{GID}.json', {'ai_spam': True, 'fake_account': True, 'link_scanner': True})
r = client.post(f'/api/guild/{GID}/security-center/protection-reset')
check(r.status_code == 200, f'POST сброса: статус {r.status_code}')
d = r.get_json(silent=True) or {}
check(d.get('success') is True and d.get('count', 0) >= 1, f'ответ: {d}')
cfg = json.load(open(f'data/security_{GID}.json', encoding='utf-8'))
check(cfg['ai_spam'] is False, 'после POST security погашена')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
