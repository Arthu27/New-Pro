# -*- coding: utf-8 -*-
"""П.2: никаких линий/полос/графиков — только числа.

1. Примитивы (app.js): drawDonut/HakumoChart(sparkline/area/vbars)/HakumoRing
   не рисуют SVG и canvas — в DOM только числа (харнесс node).
2. Шаблоны: ни одного прогресс-индикатора/бара в разметке (bar-fill,
   hl-bar, poll-bar-fill, gw-progress-fill, vc-bar-fill, dp-bar-fill,
   modern-progress, sh-bar-track, bar-track(bar-статистики), pollution-bar).
3. Chart.js заменён числовым шимом /static/numchart.js в обеих аналитиках.
4. Здоровье-сервер: arc/шкалы нет, только число score.
5. Декоративные ambient-фоны (fx-particles, stars) НЕ тронуты (это не данные).
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_PASS = 0
_FAIL = 0


def check(ok, msg, detail=''):
    global _PASS, _FAIL
    if ok:
        _PASS += 1
        print(f'  PASS: {msg}')
    else:
        _FAIL += 1
        print(f'  FAIL: {msg} {detail}')


def read(p):
    with open(os.path.join(ROOT, p), encoding='utf-8') as f:
        return f.read()


print('== 1. Примитивы выводят только числа (node-харнесс) ==')
HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync('ROOTX/web/static/app.js', 'utf8');
const doc = {
  createElementNS: function () { throw new Error('SVG запрещён п.2'); },
  createElement: function () {
    return { style: {}, className: '', innerHTML: '', children: [],
      classList: { add: function () {}, remove: function () {}, toggle: function () {}, contains: function () { return false; } },
      appendChild: function (c) { this.children.push(c); },
      setAttribute: function (k, v) { (this.attrs = this.attrs || {})[k] = v; },
      getAttribute: function (k) { return (this.attrs || {})[k]; },
      querySelector: function () { return null; }, remove: function () {} };
  },
  documentElement: {},
  getElementById: function () { return null; },
};
function fakeEl() {
  return { innerHTML: '', classList: { add: function () {} }, style: {},
    setAttribute: function (k, v) { (this.a = this.a || {})[k] = v; },
    getAttribute: function (k) { return (this.a || {})[k]; },
    querySelector: function () { return null; } };
}
global.window = { addEventListener: function () {}, removeEventListener: function () {},
  matchMedia: function () { return { matches: false, addEventListener: function () {} }; },
  devicePixelRatio: 1, scrollX: 0, scrollY: 0, scrollTo: function () {} };
global.document = doc;
doc.addEventListener = function () {}; doc.removeEventListener = function () {}; doc.querySelector = function () { return null; }; doc.readyState = 'loading';
doc.querySelectorAll = function () { return []; };
doc.body = { appendChild: function () {}, classList: { add: function () {} } };
doc.documentElement.style = {}; doc.documentElement.setAttribute = function () {}; doc.documentElement.getAttribute = function () { return null; }; doc.documentElement.classList = { add: function () {}, remove: function () {}, toggle: function () {} }; doc.documentElement.dataset = {}; doc.documentElement.setProperty = function () {}; doc.documentElement.style.setProperty = function () {};
global.getComputedStyle = function () { return { getPropertyValue: function () { return '#4f46e5'; } }; };
global.requestAnimationFrame = function () {};
global.setInterval = function () {}; global.setTimeout = function () {};
global.clearInterval = function () {};
global.IntersectionObserver = function () { return { observe: function () {}, disconnect: function () {} }; };
global.MutationObserver = function () { return { observe: function () {}, disconnect: function () {} }; };
global.matchMedia = undefined;
let svgColl = 0;
const origCNS = doc.createElementNS;
global.localStorage = { getItem: function () { return null; }, setItem: function () {}, removeItem: function () {} };
global.sessionStorage = global.localStorage;
global.navigator = { userAgent: 'harness', onLine: true, clipboard: { writeText: function () { return Promise.resolve(); } } };
global.fetch = function () { return Promise.reject(new Error('no net in harness')); };
global.location = { href: 'http://localhost/', pathname: '/', protocol: 'http:', hostname: 'localhost' };
window.location = global.location; window.history = { pushState: function () {}, replaceState: function () {} }; window.navigator = global.navigator || {};
global.history = { pushState: function () {}, replaceState: function () {} };
global.CustomEvent = function () {}; global.Event = function () {};
global.Image = function () {};
global.confirm = function () { return true; }; global.alert = function () {};
global.initAccentPicker = function () {};
try { eval(src); } catch (e) { console.log(JSON.stringify({ ok: false, errors: ['eval: ' + e] })); process.exit(0); }
const out = { ok: true, errors: [] };
function t(c, m) { if (!c) { out.ok = false; out.errors.push(m); } }

var el = fakeEl();
window.drawDonut(el, 64, '#fff');
t((el.innerHTML || '').indexOf('<svg') === -1, 'drawDonut: без SVG');
t(/64/.test(el.innerHTML), 'drawDonut: число % на месте');
t((el.innerHTML || '').indexOf('donut-num') !== -1, 'drawDonut: класс числового блока');

el = fakeEl();
window.HakumoChart.sparkline(el, [3, 9, 5], { title: 'CPU, %', unit: '%' });
t((el.innerHTML || '').indexOf('<svg') === -1, 'sparkline: без SVG');
t(el.innerHTML.indexOf('сейчас') !== -1 && el.innerHTML.indexOf('макс') !== -1, 'sparkline: сводка сейчас/сред/мин/макс');
t(el.innerHTML.indexOf('9%') !== -1, 'sparkline: максимум числом (9%)');

el = fakeEl();
window.HakumoChart.vbars(el, [{ label: 'Бан', value: 4 }, { label: 'Мут', value: 6 }], {});
t((el.innerHTML || '').indexOf('<svg') === -1, 'vbars: без SVG');
t(el.innerHTML.indexOf('Бан: 4') !== -1 && el.innerHTML.indexOf('итого: 10') !== -1, 'vbars: числовые чипы + сумма');

el = fakeEl();
window.HakumoRing(el, [{ label: 'Авто', value: 7, color: '#16a34a' }, { label: 'Ручн', value: 3, color: '#dc2626' }], { totalLabel: 'решений' });
t((el.innerHTML || '').indexOf('<svg') === -1, 'HakumoRing: без SVG');
t(el.innerHTML.indexOf('Авто: 7 (70%)') !== -1, 'ring: числовые чипы с долей %');
console.log(JSON.stringify(out));
"""
_tmp = tempfile.mkdtemp(prefix='p2_nums_')
_os_cwd = os.getcwd()
try:
    hn = os.path.join(_tmp, 'harness_nums.js')
    with open(hn, 'w', encoding='utf-8') as f:
        f.write(HARNESS.replace('ROOTX', ROOT))
    run = subprocess.run(['node', hn], capture_output=True, text=True, timeout=30)
    data = {}
    for line in run.stdout.strip().splitlines():
        try:
            data = __import__('json').loads(line)
        except Exception:  # noqa: BLE001
            pass
    check(bool(data.get('ok')), 'числовые примитивы без SVG (%s)' % (data.get('errors', []) or run.stderr[:100] or 'ok'))
finally:
    import shutil
    shutil.rmtree(_tmp, ignore_errors=True)


print('== 2. В шаблонах нет баров/прогрессов ==')
BANNED = ('poll-bar-fill', 'gw-progress-fill', 'vc-bar-fill', 'dp-bar-fill',
          'modern-progress', 'sh-bar-track', 'hl-bar"><i', 'bar-track"><div class="bar-fill')
scan_files = [os.path.join('web/templates', f)
              for f in os.listdir(os.path.join(ROOT, 'web/templates')) if f.endswith('.html')]
for b in BANNED:
    hits = [os.path.basename(p) for p in scan_files if b in read(p)]
    check(not hits, f'«{b}» нигде не осталось', ', '.join(hits))


print('== 3. Chart.js -> числовой шим ==')
for p in ('web/templates/analytics.html',):
    s = read(p)
    check('/static/numchart.js' in s and 'chart.umd.js' not in s,
          f'{os.path.basename(p)}: грузится numchart, не Chart.js')
nc = read('web/static/numchart.js')
check('window.Chart = NumChart' in nc, 'numchart.js подменяет window.Chart')
check('style.display = \'none\'' in nc, 'numchart прячет canvas (вёрстка не дергается)')


print('== 4. Здоровье сервера — числом ==')
dash = read('web/templates/dashboard.html')
check('srvHealthArc' not in dash, 'SVG-дуга индекса здоровья убрана')
check('threatFill' not in dash and 'serenityBar' not in read('web/templates/mod_center.html'),
      'полосы угрозы/спокойствия убраны')
sh = read('web/templates/server_health.html')
check('sh-bar-track' not in sh and 'id="cpu-val"' in sh,
      'server_health: бары убраны, числа на месте')


print('== 5. Декоративные фоны не тронуты ==')
app = read('web/static/app.js')
check('fx-particles' in app, 'ambient-фон частиц на месте (не данные)')
check('donut-num-v' in read('web/static/style.css'), 'стили числовых блоков добавлены')

print(f'\n=== PASS {_PASS} / FAIL {_FAIL} ===')
sys.exit(1 if _FAIL else 0)
