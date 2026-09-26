# -*- coding: utf-8 -*-
"""Диспетчер data-act (строгий CSP панели, 2026-09-08) — живой Node-харнесс.

Миграция панели на nonce-CSP убрала 'unsafe-inline': кнопки, которые
скрипты создают на лету, больше не могут нести onclick="fn('id')".
Вместо этого — элемент несёт data-act="fn" и аргументы data-a1..a3,
а единый диспетчер в base.html вызывает функцию.

Этот набор исполняет НАСТОЯЩИЙ JS диспетчера в Node с DOM-стабами:
  1. простой вызов data-act + data-a1;
  2. приведение типов: 'true'/'false' → булевы, '-1'/'1' → числа;
  3. data-evt — функция получает событие первым аргументом;
  4. data-el  — функция получает сам элемент первым аргументом;
  5. аватары: data-av-fallback подставляет запасную картинку;
  6. аватары: data-av-letter заменяет узел буквой (className переносится);
  7. диспетчер игнорирует клики мимо [data-act] и ошибки не-IMG.

Запуск: python3 tests/test_data_act_dispatcher.py (нужен node)
"""

import os
import re
import subprocess
import sys
import tempfile

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


print('== 1. Диспетчер извлечён из base.html ==')
base = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
scripts = [m.group(2) for m in re.finditer(r'<script([^>]*)>(.*?)</script>', base, re.S)
           if 'src=' not in m.group(1) and 'application/json' not in m.group(1)]
disp = next((s for s in scripts if 'data-act' in s and "data-a' + n" in s), None)
check(disp is not None, 'скрипт диспетчера найден (data-act, аргументы, аватары)')
check('data-av-fallback' in disp and 'data-av-letter' in disp,
      'обработка аватаров в диспетчере на месте')

HARNESS = r"""
const fs = require('fs');
const code = fs.readFileSync(process.argv[2], 'utf8');
const calls = [];
const listeners = {};
const doc = {
  addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); },
  createElement: (tag) => ({ tagName: tag.toUpperCase(), className: '', textContent: '' })
};
globalThis.document = doc;
globalThis.window = globalThis;

new Function('document', code)(doc);

function makeEl(attrs) {
  const a = Object.assign({}, attrs);
  const el = {
    self: null,
    getAttribute: (n) => (n in a ? a[n] : null),
    hasAttribute: (n) => n in a,
    style: {},
    tagName: 'DIV',
    parentNode: { replaceChild: (x) => calls.push(['replaceChild', x.className]), textContent: '' },
    setAttribute: (n, v) => { a[n] = v; if (n === 'src' && el.self) el.self.src = v; calls.push(['setAttr', n, v]); },
  };
  el.self = el;
  return el;
}

globalThis.fSimple = (x) => calls.push(['fSimple', x]);
globalThis.fTypes = (x, b, n) => calls.push(['fTypes', x, b, n, typeof b, typeof n]);
globalThis.fEvt = (e, x) => calls.push(['fEvt', !!(e && e.isTrusted), x]);
globalThis.fEl = (el, x) => calls.push(['fEl', el.marker, x]);

function click(el) {
  listeners['click'].forEach((fn) => fn({ target: { closest: () => el }, isTrusted: true }));
}

click(makeEl({ 'data-act': 'fSimple', 'data-a1': 'abc' }));
click(makeEl({ 'data-act': 'fTypes', 'data-a1': 'k', 'data-a2': 'true', 'data-a3': '-1' }));
click(makeEl({ 'data-act': 'fEvt', 'data-evt': '', 'data-a1': 'id1' }));
const elObj = makeEl({ 'data-act': 'fEl', 'data-el': '', 'data-a1': 'id2' });
elObj.marker = 'THE-EL';
click(elObj);

// клик мимо data-act — ничего не происходит
const noAct = makeEl({});
listeners['click'].forEach((fn) => fn({ target: { closest: () => null } }));

// аватар: запасная картинка
const img = makeEl({ 'data-av-fallback': 'https://cdn/x.png' });
img.tagName = 'IMG'; img.src = 'broken';
listeners['error'].forEach((fn) => fn({ target: img }));
if (img.src !== 'https://cdn/x.png') { console.error('FAIL fallback'); process.exit(1); }

// аватар: буква вместо узла
const imgL = makeEl({ 'data-av-letter': 'А', 'data-av-cls': 'mst-av mst-av-t' });
imgL.tagName = 'IMG';
listeners['error'].forEach((fn) => fn({ target: imgL }));

// ошибка не-IMG игнорируется
listeners['error'].forEach((fn) => fn({ target: { tagName: 'SCRIPT' } }));

const expected = [
  ['fSimple', 'abc'],
  ['fTypes', 'k', true, -1, 'boolean', 'number'],
  ['fEvt', true, 'id1'],
  ['fEl', 'THE-EL', 'id2'],
];
const flat = JSON.stringify(calls.filter(c => c[0].startsWith('f')));
if (flat !== JSON.stringify(expected)) { console.error('FAIL calls ' + flat); process.exit(1); }
if (!calls.some(c => c[0] === 'replaceChild' && c[1] === 'mst-av mst-av-t')) {
  console.error('FAIL letter'); process.exit(1);
}
console.log('DISPATCHER OK');
"""

print('== 2. Node-харнесс: вызовы, типы, события, аватары ==')
with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
    f.write(HARNESS)
    harness_path = f.name
with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
    f.write(disp)
    disp_path = f.name

try:
    node = subprocess.run(['node', harness_path, disp_path],
                          capture_output=True, text=True, timeout=60)
    out = (node.stdout + node.stderr).strip()
    check(node.returncode == 0 and 'DISPATCHER OK' in out,
          f'харнесс прошёл ({out.splitlines()[-1] if out else "нет вывода"})')
finally:
    os.unlink(harness_path)
    os.unlink(disp_path)

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
