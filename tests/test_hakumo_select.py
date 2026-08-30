# -*- coding: utf-8 -*-
"""Регрессия движка кастомных дропдаунов HakumoSelect.

Баг: enhance() переносил <select> внутрь обёртки и только потом вызывал
replaceChild(shell, orig) — orig.parentNode уже был shell, то есть замена
узла на собственного предка → HierarchyRequestError. В итоге селекты не
перевоплощались («ничего не изменилось»), а исключения сыпались при каждой
перерисовке (лаги панели).

Харнесс Node с честной реализацией спецификации replaceChild/appendChild
реально исполняет блок HAKUMO KIT 11 из app.js и проверяет, что селект
оборачивается без исключений, change-события и структура сохраняются.

Запуск: python3 tests/test_hakumo_select.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_select_test_')
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

print('== статические проверки ==')
check('HAKUMO KIT 11' in APP_JS, 'блок HakumoSelect присутствует')
m = re.search(r'parent\.replaceChild\(shell, orig\).*?shell\.appendChild\(orig\)', APP_JS, re.S)
check(bool(m), 'порядок: замена в исходном родителе ДО переноса select внутрь shell')
m = re.search(r'shell\.appendChild\(orig\).*?orig\.parentNode\.replaceChild\(shell, orig\)', APP_JS, re.S)
check(m is None, 'запрещённый порядок (replaceChild по предку) отсутствует')
check('tryEnhance' in APP_JS, 'сбой одного селекта не ломает остальные')

print('== Node-харнесс: реальное исполнение движка ==')
node_script = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
const start = src.indexOf('// ============================================================\n// HAKUMO KIT 11');
const block = start < 0 ? '' : src.slice(start);
if (!block) { console.error('KIT 11 не найден'); process.exit(1); }

function isAncestor(n, node) { let p = node; while (p) { if (p === n) return true; p = p.parentNode; } return false; }
function matchesSel(node, sel) {
  return sel.split(',').some(s => {
    s = s.trim();
    if (s[0] === '.') return node.classList.contains(s.slice(1));
    if (s[0] === '[') return node.getAttribute(s.slice(1, -1)) !== null;
    return node.tagName === s.toUpperCase();
  });
}
function makeNode(tag) {
  const n = {
    tagName: String(tag || 'div').toUpperCase(),
    parentNode: null, children: [], className: '', attrs: {}, value: '',
    style: {},
    classList: {
      add() { for (const c of arguments) if (!this._node.classList.contains(c)) this._node.className = (this._node.className + ' ' + c).trim(); },
      contains(c) { return (' ' + this._node.className + ' ').indexOf(' ' + c + ' ') !== -1; },
      remove(c) { this._node.className = (' ' + this._node.className + ' ').replace(' ' + c + ' ', ' ').trim(); }
    },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
    removeAttribute(k) { delete this.attrs[k]; },
    createElement(tag) { return makeNode(tag); },
    appendChild(c) {
      if (c.parentNode) throw new Error('HierarchyRequestError: already parented');
      c.parentNode = this; this.children.push(c); return c;
    },
    replaceChild(nn, old) {
      if (isAncestor(nn, this)) throw new Error('HierarchyRequestError: ancestor');
      const i = this.children.indexOf(old);
      if (i < 0) throw new Error('NotFoundError');
      old.parentNode = null; this.children[i] = nn; nn.parentNode = this; return old;
    },
    closest(sel) { let p = this; while (p) { if (matchesSel(p, sel)) return p; p = p.parentNode; } return null; },
    matches(sel) { return matchesSel(this, sel); },
    querySelectorAll(sel) { return findAll(this, sel); },
    querySelector(sel) { return findAll(this, sel)[0] || null; },
    addEventListener() {}, dispatchEvent() {},
    get selectedOptions() { return []; },
    get firstElementChild() { return this.children[0] || null; },
    set innerHTML(h) { this.children = []; },
    get innerHTML() { return ''; }
  };
  n.classList._node = n;
  return n;
}
function findAll(root, sel) {
  const out = [];
  (function walk(node) {
    for (const c of node.children) {
      if (matchesSel(c, sel)) out.push(c);
      walk(c);
    }
  })(root);
  return out;
}

const doc = makeNode('#document');
const body = makeNode('body');
doc.appendChild(body);
const form = makeNode('form');
body.appendChild(form);
const sel = makeNode('select');
sel.value = 'g1';
for (const v of ['g1', 'g2']) {
  const o = makeNode('option');
  o.value = v; o.textContent = v === 'g1' ? 'Главный сервер' : 'Второй сервер';
  Object.defineProperty(o, 'textContent', { value: o.textContent, writable: true });
  sel.appendChild(o);
}
form.appendChild(sel);
doc.readyState = 'complete';

class FakeMO { constructor() {} observe() {} disconnect() {} }
const fakeWindow = {
  matchMedia: () => ({ matches: false }),
  addEventListener() {},
  innerWidth: 1400, innerHeight: 900,
  setInterval: () => 1, setTimeout: (fn) => { return 1; }
};
const getComputedStyle = () => ({ display: 'inline-block', minHeight: '0px', minWidth: '0px' });

let threw = null;
try {
  const fn = new Function('document', 'window', 'MutationObserver', 'getComputedStyle', 'setInterval', block);
  fn(doc, fakeWindow, FakeMO, getComputedStyle, () => 1);
  if (typeof fakeWindow.hakumoSelect !== 'object') throw new Error('hakumoSelect не экспортирован');
  fakeWindow.hakumoSelect.rescan();
} catch (e) { threw = e; }

if (threw) { console.error('ИСКЛЮЧЕНИЕ:', threw.message); process.exit(1); }
if (sel.getAttribute('data-aes') !== '1') { console.error('select не помечен enhanced'); process.exit(1); }
const shell = sel.parentNode;
if (!shell || !shell.classList.contains('aes')) { console.error('select не обёрнут в .aes'); process.exit(1); }
const btn = shell.children.find(c => c.classList.contains('aes-btn'));
if (!btn) { console.error('кнопка дропдауна не создана'); process.exit(1); }
if (!sel.classList.contains('aes-native')) { console.error('select не скрыт классом aes-native'); process.exit(1); }
if (shell.parentNode !== form) { console.error('shell встал не на место select в форме'); process.exit(1); }
console.log('enhance: OK — select обёрнут в .aes с кнопкой, форма цела, исключений нет');
"""

proc = subprocess.run(['node', '-e', node_script, os.path.join(ROOT, 'web', 'static', 'app.js')],
                      capture_output=True, text=True, timeout=60)
check(proc.returncode == 0,
      'харнесс Node: движок дропдаунов оборачивает select без исключений'
      + (f' ({proc.stdout.strip()})' if proc.stdout.strip() else '')
      + (f' [{proc.stderr.strip()}]' if proc.stderr.strip() else ''))


# ═══════════════════════════════════════════════════════════════════════
# Регрессия «Каналы и маршруты»: дропдаун поверх плотных рядов.
#
# Три бага (все из жалоб на странице):
#  1) click-guard «лечил» клик по опции открытого дропдауна и пробрасывал
#     его на кнопку ПОД панелью — открывалась другая настройка, выбор не
#     происходил;
#  2) positionPanel занижала высоту панели (min(300,…)) — низ списка
#     вылезал за экран, последние каналы были недостижимы;
#  3) колесо/жест над панелью скроллили страницу сзади — панель
#     закрывалась посреди выбора, страница «уезжала» под курсором.
# ═══════════════════════════════════════════════════════════════════════
print('\n== регрессия «Каналы и маршруты»: клики, позиционирование, скролл ==')

CG_JS = open(os.path.join(ROOT, 'web', 'static', 'click-guard.js'), encoding='utf-8').read()
STYLE_CSS = open(os.path.join(ROOT, 'web', 'static', 'style.css'), encoding='utf-8').read()

check('[role="option"]' in CG_JS and '.aes-opt' in CG_JS,
      'click-guard: опции дропдауна — интерактив (гарда не ворует их клики)')
check('.aes-panel.open' in CG_JS,
      'click-guard: открытая панель дропдауна — осмысленный оверлей (не «лечим»)')
m = re.search(r'if \(sh > ch\) \{[^{}]*\}\s*e\.preventDefault\(\);', APP_JS)
check(bool(m),
      'колесо над открытой панелью всегда поглощается: страница за дропдауном не двигается')
check('!doc.contains(currentOrig)) closePanel()' in APP_JS,
      'панель закрывается, когда её select удалён из DOM (перерисовка страницы)')
check(re.search(r'\.aes-panel \{[^}]*overscroll-behavior:\s*contain', STYLE_CSS, re.S) is not None,
      'CSS: .aes-panel гасит скролл-цепочку (overscroll-behavior: contain)')
check('.aes-panel .aes-search { touch-action: none; }' in STYLE_CSS,
      'CSS: жест по полю поиска дропдауна не тянет страницу сзади')

# ── Node-харнесс click-guard.js: реальное исполнение лечилки кликов ─────
cg_harness = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');  // node HARNESS TARGET

// Мини-DOM: только то, что использует click-guard
function matchesSimple(node, s) {
  s = s.trim();
  let notAttr = null;
  const nm = s.match(/^(.*):not\(\[(\w+)\]\)$/);
  if (nm) { s = nm[1]; notAttr = nm[2]; }
  if (s[0] === '.') {
    const classes = s.slice(1).split('.');
    for (const c of classes) if (!node.classList.contains(c)) return false;
  } else if (s[0] === '[') {
    if (node.getAttribute(s.slice(1, -1)) === null) return false;
  } else if (s[0] === '#') {
    if (node.id !== s.slice(1)) return false;
  } else if (node.tagName !== s.toUpperCase()) return false;
  if (notAttr && node.getAttribute(notAttr) !== null) return false;
  return true;
}
function matchesSel(node, sel) { return sel.split(',').some(s => matchesSimple(node, s)); }

let clicks = [];
let preventDefaultCalls = 0;
function makeNode(tag, cls, role) {
  const n = {
    tagName: String(tag).toUpperCase(), className: cls || '', id: '',
    attrs: role ? { role } : {}, disabled: false, parentNode: null, children: [],
    classList: {
      contains(c) { return (' ' + this._node.className + ' ').indexOf(' ' + c + ' ') !== -1; }
    },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
    closest(sel) { let p = this; while (p) { if (matchesSel(p, sel)) return p; p = p.parentNode; } return null; },
    matches(sel) { return matchesSel(this, sel); },
    click() { clicks.push(this); },
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  };
  n.classList._node = n;
  return n;
}

const panel = makeNode('div', 'aes-panel open');
const list = makeNode('div', 'aes-list'); panel.appendChild(list);
const opt = makeNode('div', 'aes-opt', 'option'); opt.attrs['data-v'] = '123'; list.appendChild(opt);
const plainOpt = makeNode('div', 'aes-opt');           // без role (страховочный слой)
const padding = makeNode('div', 'aes-pad'); list.appendChild(padding);

const underlyingBtn = makeNode('button', 'chs-save');  // чужая кнопка ПОД панелью
const underlyingLink = makeNode('a', 'nav-link'); underlyingLink.attrs['href'] = '/bot-settings';
const overlayDiv = makeNode('div', 'ghost');           // невидимый «вор» кликов

let openPanel = panel; // что возвращает querySelector для оверлеев (панель ОТКРЫТА)
let stackAt = [];       // что лежит под точкой тапа
const handlers = {};
const fakeDoc = {
  addEventListener(type, fn) { handlers[type] = fn; },
  querySelector(sel) {
    // overlayIntentional ищет открытые оверлеи; понимаем .aes-panel.open
    if (sel.indexOf('.aes-panel.open') !== -1) return openPanel;
    return null;
  },
  getElementById() { return null; },
  elementsFromPoint() { return stackAt; }
};
const fakeWin = { console: { warn() {}, error: console.error.bind(console), log: console.log.bind(console) } };

new Function('document', 'window', src)(fakeDoc, fakeWin);
const h = handlers['pointerdown'];
if (!h) { console.error('pointerdown-обработчик не зарегистрирован'); process.exit(1); }
function tap(target, stack) {
  clicks = []; preventDefaultCalls = 0;
  stackAt = stack || [target];
  h({ button: 0, target, clientX: 10, clientY: 10,
      preventDefault() { preventDefaultCalls++; }, stopPropagation() {} });
}

// A) Панель открыта: тап по опции (role=option) — гарда НЕ вмешивается,
//    клик уходит в выбор опции, а не на кнопку под панелью.
tap(opt, [opt, list, panel, underlyingBtn]);
if (clicks.length || preventDefaultCalls) { console.error('A: гарда вмешалась в клик по опции'); process.exit(1); }

// A2) Панель открыта: опция без role — спасает слой «осмысленный оверлей».
tap(plainOpt, [plainOpt, list, panel, underlyingLink]);
if (clicks.length || preventDefaultCalls) { console.error('A2: гарда кликнула мимо опции'); process.exit(1); }

// B) Панель открыта: тап по паддингу панели (не интерактив) — НЕ пробрасываем
//    на кнопку под панелью: открытый дропдаун — осмысленное перекрытие.
tap(padding, [padding, panel, underlyingBtn]);
if (clicks.length || preventDefaultCalls) { console.error('B: гарда пробросила клик сквозь открытый дропдаун'); process.exit(1); }

// C) Панель ЗАКРЫТА: гарда по-прежнему лечит — невидимый слой поверх кнопки.
openPanel = null;
tap(overlayDiv, [overlayDiv, underlyingBtn]);
if (clicks.length !== 1 || clicks[0] !== underlyingBtn || !preventDefaultCalls) {
  console.error('C: самолечение кликов сломано'); process.exit(1);
}

// D) Панель закрыта: честный тап по кнопке — без вмешательства.
tap(underlyingBtn, [underlyingBtn]);
if (clicks.length || preventDefaultCalls) { console.error('D: гарда мешает честному клику'); process.exit(1); }

console.log('click-guard: OK — опции дропдауна не воруются, самолечение живо');
"""

_tmpdir = tempfile.mkdtemp(prefix='hakumo_cg_test_')
_cg_path = os.path.join(_tmpdir, 'cg_harness.js')
with open(_cg_path, 'w', encoding='utf-8') as fh:
    fh.write(cg_harness)
proc = subprocess.run(['node', _cg_path, os.path.join(ROOT, 'web', 'static', 'click-guard.js')],
                      capture_output=True, text=True, timeout=60)
check(proc.returncode == 0,
      'харнесс Node: клики по опциям дропдауна не воруются гардой, самолечение живо'
      + (f' ({proc.stdout.strip()})' if proc.stdout.strip() else '')
      + (f' [{proc.stderr.strip()}]' if proc.stderr.strip() else ''))


# ── Node-харнесс positionPanel: реальный код из app.js + сценарии экранов ─
def _extract_fn(src, signature):
    i = src.find(signature)
    if i < 0:
        return None
    j = src.find('{', i)
    depth, k = 0, j
    while k < len(src):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
        k += 1
    return None


_pp_src = _extract_fn(APP_JS, 'function positionPanel(btn)')
check(_pp_src is not None, 'positionPanel найдена в app.js для харнесса')

if _pp_src:
    _pp_path = os.path.join(_tmpdir, 'position_panel.js')
    with open(_pp_path, 'w', encoding='utf-8') as fh:
        fh.write(_pp_src)
    pp_harness = r"""
const fs = require('fs');
const fnSrc = fs.readFileSync(process.argv[2], 'utf8');  // node HARNESS TARGET
const positionPanel = new Function('panel', 'listEl', 'win', 'btn', fnSrc + '\nreturn positionPanel(btn);');

function run(vh, h, btnTop, btnBottom) {
  const listEl = { style: {} };
  // Высота панели = 100 (поиск/отступы) + высота списка. Как в проде:
  // базовая высота списка живёт в CSS (max-height: min(52vh,320px)),
  // а positionPanel ставит ИНЛАЙНОВЫЙ maxHeight только когда ужимает.
  const panel = { style: {}, offsetWidth: 280, _list: listEl, _cssList: h - 100 };
  Object.defineProperty(panel, 'offsetHeight', {
    get() {
      const inline = parseInt(this._list.style.maxHeight, 10);
      return 100 + (isNaN(inline) ? this._cssList : inline);
    },
    configurable: true
  });
  const win = { innerHeight: vh, innerWidth: 1400 };
  const btn = { getBoundingClientRect: () => ({ left: 100, top: btnTop, bottom: btnBottom, width: 260 }) };
  positionPanel(panel, listEl, win, btn);
  const top = parseFloat(panel.style.top);
  const height = panel.offsetHeight;
  return { top, height, bottom: top + height, listMax: listEl.style.maxHeight || '' };
}

function ok(name, cond, extra) {
  if (!cond) { console.error(name + ' FAIL ' + JSON.stringify(extra)); process.exit(1); }
}

// 1) Обычный экран: панель открывается ВНИЗ и целиком влезает.
let r = run(900, 400, 160, 200);
ok('вниз влезает', r.top === 206 && r.bottom <= 892 && r.listMax === '', r);

// 2) Репорт пользователя: «меню появляется СНИЗУ ВВЕРХ, а должно сверху вниз».
//    Кнопка в нижней трети: целиком вниз не влезает (места 286, панели 420) —
//    список УЖИМАЕТСЯ под свободное место, панель всё равно открывается ВНИЗ.
r = run(800, 420, 460, 500);
ok('вниз с ужиманием', r.top === 506 && r.listMax === '186px' && r.bottom <= 800, r);

// 3) Вверх — только у самого края экрана (внизу не помещается даже минимум
//    из ~3 опций): панель разворачивается вверх целиком.
r = run(900, 400, 760, 800);
ok('вверх у края', r.top === 354 && r.bottom <= 892 && r.listMax === '', r);

// 4) Регрессия: середина экрана, панель не влезает ни вниз, ни вверх.
//    Старый код (оценка min(300,…)) ставил top=346 и низ вылезал на 246px
//    за экран — последние каналы были недостижимы. Теперь — вверх с ужиманием.
r = run(500, 400, 300, 340);
ok('впритык прижата', r.top >= 8 && r.bottom <= 500 && r.listMax === '186px', r);

// 5) Крошечный экран/крупный зум: список ужимается, панель влезает целиком.
r = run(300, 420, 110, 150);
ok('малый экран', r.listMax === '184px' && r.top >= 8 && r.bottom <= 300, r);

// 6) Направление «сверху вниз» — дефолт: инвариант по всем позициям/экранам
//    (панель всегда в экране) + подсчёт на реальных экранах (>=640px):
//    вниз открывается в разы чаще, вверх — только у нижней кромки.
let flipped = 0, downs = 0;
for (const vh of [640, 720, 800, 900, 1080]) {
  for (let t = 40; t < vh - 40; t += 40) {
    const x = run(vh, 400, t, t + 40);
    if (x.top < 8 || x.bottom > vh) { console.error('вылезла: ' + JSON.stringify({vh, t, x})); process.exit(1); }
    if (x.top >= t + 40) downs++; else flipped++;
  }
}
ok('вниз — преобладает', downs > flipped * 2, { downs, flipped });
console.log('positionPanel: OK — вниз по умолчанию, вверх только у края, всегда в экране (вниз ' + downs + ' / вверх ' + flipped + ')');
"""
    _pph_path = os.path.join(_tmpdir, 'pp_harness.js')
    with open(_pph_path, 'w', encoding='utf-8') as fh:
        fh.write(pp_harness)
    proc = subprocess.run(['node', _pph_path, _pp_path],
                          capture_output=True, text=True, timeout=60)
    check(proc.returncode == 0,
          'харнесс Node: панель дропдауна всегда целиком в экране (все вьюпорты)'
          + (f' ({proc.stdout.strip()})' if proc.stdout.strip() else '')
          + (f' [{proc.stderr.strip()}]' if proc.stderr.strip() else ''))

try:
    shutil.rmtree(_tmpdir, ignore_errors=True)
except Exception:
    pass


print('== страницы с селектами рендерятся ==')
from web.app import app as _flask_app  # noqa: E402

client = _flask_app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'SelectTest'
    s['role'] = 'owner'
for path in ('/analytics', '/channels', '/roles', '/mod-center', '/channel-settings'):
    r = client.get(path)
    check(r.status_code == 200, f'{path} → {r.status_code}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
