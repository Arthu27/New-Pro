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

_TMP = tempfile.mkdtemp(prefix='aether_modmode_test_')
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


_ENV_KEYS = ('MOD_ONLY', 'DISABLED_COGS', 'EXTRA_COGS')


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
check(pm.module_mode_active() is False, 'classic: режим модулей выключен')
check(pm.module_off_paths() == frozenset(), 'classic: без DISABLED_COGS ничто не приглушено')

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
check(pm.module_off_paths() == frozenset({'/giveaway'}),
      'classic+DISABLED_COGS: гаснет точечно только раздача')

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

_set_env()  # режим выкл
r2 = client.get('/')
html2 = r2.get_data(as_text=True)
check('mode-banner' not in html2 and 'nav-off-chip' not in html2,
      'classic: ни баннера, ни чипов')

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
check('Hakumo' not in all_tpl and 'HAKUMO' not in all_tpl,
      'чужой бренд (Hakumo) вычищен из шаблонов')

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
check('panel_off_paths' in base and 'is-off' in base and 'nav-off-chip' in base,
      'base.html: механика гашения подключена')
check('panel_mod_only' in base, 'base.html: баннер режима подключен')
check('/static/polish.css?v=5' in base, 'версия polish.css поднята (сброс кэша)')

css = open(os.path.join(ROOT, 'web', 'static', 'polish.css'), encoding='utf-8').read()
for marker in ('.mode-banner', '.nav-link.is-off', '.nav-off-chip'):
    assert marker in css, marker
check(css.count('{') == css.count('}'), 'polish.css: стили режима добавлены, скобки сбалансированы')

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
