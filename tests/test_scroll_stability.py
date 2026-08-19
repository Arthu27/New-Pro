# -*- coding: utf-8 -*-
"""Регрессия стабильности прокрутки панели.

Баг: клик по каналу / живая перерисовка списков сбрасывала прокрутку
страницы в самый верх. Фикс должен гарантировать:
  * асинхронные перерисовки возвращают позицию ПОСЛЕ обновления DOM
    (window.keepScrollAsync), а не до него;
  * сайдбар-меню помнит позицию между переходами и показывает активный пункт;
  * фокус инпутов не скроллит страницу (preventScroll);
  * сворачивание категорий каналов не уводит список вверх.

Запуск: python3 tests/test_scroll_stability.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_scroll_test_')
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


APP_JS = open(os.path.join(ROOT, 'web', 'static', 'app.js'), encoding='utf-8').read()
CHANNELS = open(os.path.join(ROOT, 'web', 'templates', 'channels.html'), encoding='utf-8').read()
CHAT = open(os.path.join(ROOT, 'web', 'templates', 'chat.html'), encoding='utf-8').read()
MOD_CENTER = open(os.path.join(ROOT, 'web', 'templates', 'mod_center.html'), encoding='utf-8').read()
MOD_INSIGHTS = open(os.path.join(ROOT, 'web', 'templates', 'mod_insights.html'), encoding='utf-8').read()

print('== статические проверки ==')

# 1. keepScrollAsync существует и восстанавливает ПОСЛЕ промиса
check('window.keepScrollAsync = function' in APP_JS,
      'app.js: keepScrollAsync определён')
m = re.search(r'window\.keepScrollAsync = function \(promise\) \{(.*?)\n  \};', APP_JS, re.S)
check(bool(m) and 'Promise.resolve(promise).then' in m.group(1)
      and 'window.scrollTo(x, y)' in m.group(1),
      'app.js: восстановление прокрутки привязано к .then() промиса (после DOM)')

# 2. Сайдбар: память позиции + показ активного пункта
check('aether_sb_scroll' in APP_JS, 'app.js: память прокрутки сайдбара')
check('aether_pg_scroll_' in APP_JS, 'app.js: память прокрутки страницы по маршруту')
check("nav.querySelector('.nav-link.active')" in APP_JS
      and 'sidebarNav' in APP_JS,
      'app.js: активный пункт меню показывается в сайдбаре')

# 3. Каналы: живое обновление через keepScrollAsync, а не синхронный keepScroll
check('keepScrollAsync(loadChannels(true))' in CHANNELS,
      'channels: live-обновление держит прокрутку через keepScrollAsync')
check(re.search(r'keepScroll\s*\(\s*function \(\) \{ loadChannels\(true\)', CHANNELS) is None,
      'channels: старый синхронный keepScroll вокруг async loadChannels убран')
check('keepScrollAsync(loadChannels())' in CHANNELS,
      'channels: смена сервера и кнопка обновления держат прокрутку')
check('anchorTop' in CHANNELS and 'window.scrollBy(0, delta)' in CHANNELS,
      'channels: сворачивание категорий заякорено (список не уезжает вверх)')
check(CHANNELS.count('preventScroll') >= 10,
      'channels: все фокусы без прокрутки страницы')

# 4. Чат: фокусы без прыжков
check(re.search(r'\.focus\(\)', CHAT) is None and CHAT.count('preventScroll') >= 5,
      'chat: ни одного фокуса без preventScroll')

# 5. Досье в mod-insights больше не прыгает к началу страницы
check("scrollIntoView({ behavior: 'smooth', block: 'nearest' })" in MOD_INSIGHTS
      and "block: 'start'" not in MOD_INSIGHTS,
      'mod-insights: досье подводится к ближайшему краю, а не к верху')

# 6. Мод-центр: новые виджеты на месте
for marker in ('mcTicker', 'mcTopOffenders', 'mcTeamLoad', 'loadPeople', 'renderBars'):
    check(marker in MOD_CENTER, f'mod-center: виджет/функция {marker} на месте')

print('== Node-харнесс: keepScrollAsync реально возвращает позицию ==')

node_script = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
const start = src.indexOf('window.renderSafe = function');
const end = src.indexOf('window.keepScroll = function');
if (start < 0 || end < 0 || end <= start) { console.error('блок не найден'); process.exit(1); }
let block = src.slice(start, end);
let raf = [];
let tos = [];
const calls = [];
const fakeWindow = {
  scrollY: 350, scrollX: 0,
  scrollTo(x, y) { calls.push([x, y, this.scrollY]); this.scrollY = y; this.scrollX = x; },
  requestAnimationFrame(fn) { raf.push(fn); return raf.length; },
  setTimeout(fn) { tos.push(fn); return tos.length; }
};
// eslint-disable-next-line no-new-func
const fn = new Function('window', 'requestAnimationFrame', 'setTimeout', block + '\nreturn window;');
const w = fn(fakeWindow, fakeWindow.requestAnimationFrame.bind(fakeWindow), fakeWindow.setTimeout.bind(fakeWindow));
// 1) синхронный вызов восстанавливает позицию
w.renderSafe(function () { fakeWindow.scrollY = 0; });
raf.forEach(f => f()); tos.forEach(f => f());
if (!calls.some(c => c[0] === 0 && c[1] === 350)) { console.error('renderSafe не вернул 350'); process.exit(1); }
console.log('renderSafe: OK (' + calls.length + ' восстановлений)');
// 2) асинхронный: восстановление должно случиться ПОСЛЕ резолва промиса
calls.length = 0; raf.length = 0; tos.length = 0;
let resolved = false;
w.keepScrollAsync(new Promise(function (res) {
  setTimeout(function () { resolved = true; res(); }, 5);
}));
const before = calls.length;
setTimeout(function () {
  if (!resolved) { console.error('промис не дождались'); process.exit(1); }
  raf.forEach(f => f()); tos.forEach(f => f());
  const ok = calls.some(c => c[1] === 350);
  console.log('keepScrollAsync: ' + (ok ? 'OK — позиция вернулась после промиса' : 'FAIL'));
  process.exit(ok ? 0 : 1);
}, 30);
if (before !== 0) { console.error('восстановление случилось ДО резолва промиса'); process.exit(1); }
"""

proc = subprocess.run(['node', '-e', node_script, os.path.join(ROOT, 'web', 'static', 'app.js')],
                      capture_output=True, text=True, timeout=60)
check(proc.returncode == 0, 'харнесс Node: keepScrollAsync восстанавливает позицию после промиса'
      + (f' ({proc.stdout.strip()})' if proc.stdout.strip() else '') + (f' [{proc.stderr.strip()}]' if proc.stderr.strip() else ''))

print('== страницы рендерятся ==')
from web.app import app as _flask_app  # noqa: E402

client = _flask_app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'ScrollTest'
    s['role'] = 'owner'
for path in ('/chat', '/channels', '/mod-center', '/mod-insights'):
    r = client.get(path)
    check(r.status_code == 200, f'{path} → {r.status_code}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
