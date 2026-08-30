# -*- coding: utf-8 -*-
"""Тесты зеркалирования режима модулей (MOD_ONLY / DISABLED_COGS) в панели:
баннер «Только модерация», гашение пунктов меню с чипом «выкл», чистка
визуального мусора (эмодзи в табах/тостах, битые style, чужой бренд).

Запуск: python3 tests/test_panel_module_mode.py
"""
import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_modmode_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


_ENV_KEYS = ('MOD_ONLY', 'BOT_SLIM', 'BOT_CORE', 'BOT_FULL', 'DISABLED_COGS', 'EXTRA_COGS')


def _set_env(**kw):
    for k in _ENV_KEYS:
        os.environ.pop(k, None)
    for k, v in kw.items():
        if v is not None:
            os.environ[k] = str(v)


# ═══ 1. mapping путей -> выключенные коги ═════════════════════════════════
print('== services/panel_menu: карта и статусы ==')
from services import panel_menu as pm

_set_env()
check(pm.module_mode_active() is False, 'lean: баннер «только модерация» выключен (MOD_ONLY не задан)')
off_lean = pm.module_off_paths()
# /automation не гаснет: на ней живёт и welcome_pro (приветствия включены)
for p in ('/economy', '/giveaway', '/starboard', '/custom-commands',
          '/reaction-roles', '/fun', '/leveling'):
    assert p in off_lean, p
check(True, 'lean (по умолчанию): игровые и соц-страницы честно гаснут чипом «выкл»')
for p in ('/sla', '/tagjail', '/tickets-ops'):
    assert p in off_lean, p
check(True, 'lean: страницы уснувших модулей (SLA/TagJail) гаснут чипом')
check('/security' not in off_lean and '/antifake' not in off_lean,
      'lean: щит жив — /security и /antifake горят зелёным')
check('/mod-report' not in off_lean,
      'lean: /mod-report живёт от аудит-файла — ког mod_report не нужен, чип не вешаем')
for p in ('/music', '/staff-apps', '/ai-chat', '/afk-list',
          '/ai-moderation', '/welcome-editor', '/voice-stats', '/appeals'):
    assert p not in off_lean, p
check(True, 'lean: боевые страницы открыты (модерация/жалобы/музыка/AI/AFK/приветствие)')
check('/tickets-ops' in off_lean, 'lean: /tickets-ops погашена — тикет-система снята (жалобы через /report)')

_set_env(BOT_FULL='1')
# BOT_FULL включает все спящие коги, но RETIRED (ticket.py) снят навсегда —
# его страница /tickets-ops гаснет даже в полном режиме.
_full_off = pm.module_off_paths()
check(_full_off == frozenset({'/tickets-ops'}),
      f'BOT_FULL=1: открыто всё, кроме снятого тикет-модуля ({sorted(_full_off)})')

_set_env(MOD_ONLY='1')
check(pm.module_mode_active() is True, 'MOD_ONLY=1: режим активен')
off = pm.module_off_paths()
for p in ('/economy', '/ai-chat', '/giveaway', '/starboard', '/afk-list',
          '/custom-commands', '/welcome-editor', '/reaction-roles'):
    assert p in off, p
check(True, 'MOD_ONLY: веселуха-пункты приглушены (экономика/AI-чат/раздачи/AFK...)')
for p in ('/proofs', '/logs', '/warnings', '/antiraid', '/ai-moderation', '/temp-moderation'):
    assert p not in off, p
check(True, 'MOD_ONLY: модераторские страницы НЕ приглушены (демки/логи/варны/антирейд)')
check('/autorole' in off, 'MOD_ONLY: /autorole гаснет (оба его кога спят)')

_set_env(MOD_ONLY='1', EXTRA_COGS='economy_cog')
check('/economy' not in pm.module_off_paths(), 'EXTRA_COGS: вернул экономику — пункт снова жив')
check('/ai-chat' in pm.module_off_paths(), 'EXTRA_COGS: остальное по-прежнему гаснет')

_set_env(DISABLED_COGS='giveaway')
check(pm.module_mode_active() is False, 'classic+DISABLED_COGS: баннер не включается')
check('/giveaway' in pm.module_off_paths(),
      'lean+DISABLED_COGS: точечно гаснет и раздача')

_set_env()  # чистим окружение для остальных секций

# ═══ 2. Рендер base.html: баннер и чипы ═══════════════════════════════════
print('== рендер панели ==')
import web.app as panel_app

app = panel_app.app
app.config['TESTING'] = True
client = app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'Arthur'
    s['role'] = 'owner'

_set_env(MOD_ONLY='1')
r = client.get('/')
html = r.get_data(as_text=True)
check(r.status_code == 200, 'главная рендерится в MOD_ONLY')
check('mode-banner' in html and 'Только модерация' in html,
      'баннер «Только модерация» показан в сайдбаре')
check('href="/cog-manager"' in html, 'баннер ведёт в менеджер модулей')
m = re.search(r'<a href="/economy"[^>]*class="[^"]*is-off[^"]*"', html)
check(bool(m), 'пункт «Экономика» приглушён (is-off)')
check(bool(re.search(r'<a href="/economy".*?nav-off-chip">выкл<', html, re.S)),
      'у приглушённого пункта чип «выкл»')
proofs_m = re.search(r'<a href="/proofs"[^>]*class="([^"]*)"', html)
check(proofs_m and 'is-off' not in proofs_m.group(1), '«Демки» без is-off')
menu_paths = {it['path'] for g in pm.MENU for it in g['pages']}
expected_off = menu_paths & set(off)
check(html.count('is-off') == len(expected_off) and len(expected_off) >= 8,
      f'гашение точечное 1-в-1 с картой ({len(expected_off)} спящих пунктов)')

_set_env(BOT_FULL='1')  # полный состав — классический вид без чипов
r2 = client.get('/')
html2 = r2.get_data(as_text=True)
check('mode-banner' not in html2,
      'BOT_FULL=1: баннера режима нет — классический вид')
# снятый навсегда тикет-модуль остаётся погашен даже в полном составе
check(html2.count('nav-off-chip') <= 1,
      'BOT_FULL=1: чип «выкл» максимум у одного снятого пункта (tickets-ops)')

_set_env()  # обратно в lean
r3 = client.get('/')
html3 = r3.get_data(as_text=True)
check('nav-off-chip">выкл<' in html3, 'lean: спящие пункты снабжены чипом «выкл»')

# ═══ 3. Визуальный мусор вычищен ══════════════════════════════════════════
print('== чистота шаблонов ==')
EMOJI = re.compile('[\U0001F000-\U0001FAFF\u2B00-\u2BFF\uFE0F]|[☀-➿]')

for name in ('temp_moderation.html', 'base.html', 'dashboard.html', 'proofs.html'):
    src = open(os.path.join(ROOT, 'web', 'templates', name), encoding='utf-8').read()
    junk = [l.strip()[:70] for l in src.splitlines() if EMOJI.search(l)]
    check(not junk, f'{name}: эмодзи вычищены {junk[:2]}')

all_tpl = ''
for fn in os.listdir(os.path.join(ROOT, 'web', 'templates')):
    if fn.endswith('.html'):
        all_tpl += open(os.path.join(ROOT, 'web', 'templates', fn), encoding='utf-8').read()
check('style="!important' not in all_tpl, 'битые style="!important; ..." вычищены везде')
check('Aether' not in all_tpl and 'AETHER' not in all_tpl,
      'старый бренд Aether не встречается (бренд — Hakumo)')

# глобальный эмодзи-сторож: декоративные классы запрещены во всех шаблонах
# (функциональные пикеры <option>/<input> и валидаторы — вне этих классов)
banned = [
    '🗑️', '🧹', '🚪', '🥇', '🥈', '🥉', '🇷🇺', '🇹🇷', '🇬🇧', '💾',
    '📢</div>', '💤', '🌱', "'⚠️ ", '"⚠️ ', "'✅ ", '"✅ ', "'✓ ", "'✗ ",
    '>✅ ', '>❌ ',
]
rest = [b for b in banned if b in all_tpl]
check(not rest, f'декоративные эмодзи истреблены глобально (остаток: {rest})')

dash = open(os.path.join(ROOT, 'web', 'templates', 'dashboard.html'), encoding='utf-8').read()
check('g.name' in dash and "gName = 'Hakumo'" not in dash,
      'герой дашборда берёт имя сервера из API, а не из хардкода')

base = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
# сайдбар живёт в partial _sidebar_nav.html (включается в base и рендерится
# в /api/panel/sidebar для живого обновления меню на открытых страницах)
_snav = open(os.path.join(ROOT, 'web', 'templates', '_sidebar_nav.html'), encoding='utf-8').read()
check('panel_off_paths' in _snav and 'is-off' in _snav and 'nav-off-chip' in _snav
      and 'include "_sidebar_nav.html"' in base,
      'base.html + _sidebar_nav.html: механика гашения подключена')
check('panel_mod_only' in base, 'base.html: баннер режима подключен')
check('/static/style.css' in base, 'базовая дизайн-система подключена')

css = open(os.path.join(ROOT, 'web', 'static', 'style.css'), encoding='utf-8').read()
for marker in ('.mode-banner', '.nav-link.is-off', '.nav-off-chip'):
    assert marker in css, marker
check(css.count('{') == css.count('}'), 'style.css: стили режима добавлены, скобки сбалансированы')

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
