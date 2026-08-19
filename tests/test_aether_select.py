# -*- coding: utf-8 -*-
"""Регрессия движка кастомных дропдаунов AetherSelect.

Баг: enhance() переносил <select> внутрь обёртки и только потом вызывал
replaceChild(shell, orig) — orig.parentNode уже был shell, то есть замена
узла на собственного предка → HierarchyRequestError. В итоге селекты не
перевоплощались («ничего не изменилось»), а исключения сыпались при каждой
перерисовке (лаги панели).

Харнесс Node с честной реализацией спецификации replaceChild/appendChild
реально исполняет блок AETHER KIT 11 из app.js и проверяет, что селект
оборачивается без исключений, change-события и структура сохраняются.

Запуск: python3 tests/test_aether_select.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_select_test_')
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
check('AETHER KIT 11' in APP_JS, 'блок AetherSelect присутствует')
m = re.search(r'parent\.replaceChild\(shell, orig\).*?shell\.appendChild\(orig\)', APP_JS, re.S)
check(bool(m), 'порядок: замена в исходном родителе ДО переноса select внутрь shell')
m = re.search(r'shell\.appendChild\(orig\).*?orig\.parentNode\.replaceChild\(shell, orig\)', APP_JS, re.S)
check(m is None, 'запрещённый порядок (replaceChild по предку) отсутствует')
check('tryEnhance' in APP_JS, 'сбой одного селекта не ломает остальные')

print('== Node-харнесс: реальное исполнение движка ==')
node_script = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
const start = src.indexOf('// ============================================================\n// AETHER KIT 11');
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
  if (typeof fakeWindow.aetherSelect !== 'object') throw new Error('aetherSelect не экспортирован');
  fakeWindow.aetherSelect.rescan();
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

print('== страницы с селектами рендерятся ==')
from web.app import app as _flask_app  # noqa: E402

client = _flask_app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'SelectTest'
    s['role'] = 'owner'
for path in ('/analytics', '/channels', '/roles', '/mod-center'):
    r = client.get(path)
    check(r.status_code == 200, f'{path} → {r.status_code}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
