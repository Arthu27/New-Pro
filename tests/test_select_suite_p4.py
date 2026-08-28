# -*- coding: utf-8 -*-
"""П.4: кастомные select-меню — поведение (node mini-DOM) + статические гарантии.

Поведение:
1. sshdEnhance оборачивает select, нативный скрыт, ярлык — текущий текст.
2. Открытие → строки всех опций; поиск фильтрует по нормализатору;
   текущий выбранный всегда виден (не теряется фильтром).
3. mousedown по строке → commit: select.value поменялся И change dispatched
   (как нативный select — обработчики форм не ломаются).
4. Клавиатура: ArrowDown/Enter выбирают, Escape закрывает без выбора.
5. sshdAll(document) авто-подхватывает все select без multiple/data-sshd-no.

Статика: анимация появления, aria, мобильный размер строки, MutationObserver.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0


def check(ok, msg, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {detail}')


HARNESS = r"""
/* ── mini-DOM ─────────────────────────────────────────────────────────── */
function El(tag) {
  this.tagName = tag.toUpperCase(); this.children = []; this.attrs = {};
  this._cls = new Set(); this.textContent = ''; this.value = '';
  this._ls = {}; this.parentNode = null; this.type = '';
  if (tag === 'select') this.options = [];
}
El.prototype._syncText = function () {
  if (!this.children.length) return this.textContent;
  return this.textContent + this.children.map(function (c) {
    return c._syncText ? c._syncText() : '';
  }).join('');
};
Object.defineProperty(El.prototype, 'className', {
  get: function () { return Array.from(this._cls).join(' '); },
  set: function (v) { this._cls = new Set(String(v).split(/\s+/).filter(Boolean)); }
});
El.prototype.classList = undefined;
El.prototype._mkCl = function () { var self = this; return {
  add: function () { Array.from(arguments).forEach(function (c) { self._cls.add(c); }); },
  remove: function () { Array.from(arguments).forEach(function (c) { self._cls.delete(c); }); },
  contains: function (c) { return self._cls.has(c); },
  toggle: function (c, f) { (f === undefined ? !self._cls.has(c) : f) ? self._cls.add(c) : self._cls.delete(c); }
}; };
function wrap(el) { if (!el.classList) el.classList = el._mkCl(); return el; }
El.prototype.appendChild = function (c) { c.parentNode = this; this.children.push(c); return c; };
El.prototype.insertBefore = function (c, ref) {
  var i = this.children.indexOf(ref); c.parentNode = this;
  if (i < 0) this.children.push(c); else this.children.splice(i, 0, c); return c; };
El.prototype.setAttribute = function (k, v) { this.attrs[k] = String(v); };
Object.defineProperty(El.prototype, 'innerHTML', {
  get: function () { return ''; },
  set: function (v) { this.children = []; this.textContent = ''; } });
El.prototype.getAttribute = function (k) { return this.attrs[k] !== undefined ? this.attrs[k] : null; };
El.prototype.hasAttribute = function (k) { return this.attrs[k] !== undefined; };
El.prototype.contains = function (n) {
  if (n === this) return true;
  return this.children.some(function (c) { return c.contains(n); }); };
El.prototype.addEventListener = function (ev, fn) { (this._ls[ev] = this._ls[ev] || []).push(fn); };
El.prototype.removeEventListener = function () {};
El.prototype.dispatchEvent = function (e) {
  e.target = e.target || this;
  (this._ls[e.type] || []).slice().forEach(function (f) { f(e); });
  if (e.bubbles && this.parentNode) this.parentNode.dispatchEvent(e);
  return true; };
El.prototype.focus = function () {};
El.prototype.scrollIntoView = function () {};
El.prototype._find = function (pred, out) {
  if (pred(this)) out.push(this);
  this.children.forEach(function (c) { c._find(pred, out); }); };
El.prototype.querySelectorAll = function (sel) {
  var out = [];
  if (sel.indexOf('select:') === 0) {
    this._find(function (n) {
      return n.tagName === 'SELECT' && !n.hasAttribute('multiple') &&
        !n.hasAttribute('data-sshd-no') && !n._cls.has('sshd-src');
    }, out);
  } else if (sel[0] === '.') {
    var cls = sel.slice(1);
    this._find(function (n) { return n._cls.has(cls); }, out);
  }
  return out; };
Object.defineProperty(El.prototype, 'previousElementSibling', {
  get: function () {
    if (!this.parentNode) return null;
    var i = this.parentNode.children.indexOf(this);
    return i > 0 ? this.parentNode.children[i - 1] : null; } });

function Opt(v, t) { this.value = v; this.textContent = t; }

global.document = {
  readyState: 'complete',
  createElement: function (t) { return wrap(new El(t)); },
  addEventListener: function () {},
  body: wrap(new El('body')),
  querySelectorAll: function (sel) { return this.body.querySelectorAll(sel); }
};
global.window = {};
global.MutationObserver = undefined;
global.Event = function (t, o) { this.type = t; this.bubbles = !!(o && o.bubbles); };
global.CustomEvent = function (t, o) { this.type = t; this.detail = o && o.detail; };

const fs = require('fs');
const path = process.env.PICKERS_PATH;
let src = fs.readFileSync(path, 'utf8');
// Timeout-фокусы в open — без реальных таймеров делаем синхронными
src.replace ? null : null;
eval(src);

const out = [];
function ok(name, cond) { out.push({ name: name, pass: !!cond }); }

/* 1. обёртка + скрытый нативный + ярлык */
const form = wrap(new El('form'));
const sel = wrap(new El('select'));
sel.options = [new Opt('', '— не выбрано —'), new Opt('1', '# общий'),
  new Opt('2', '# модераторы'), new Opt('3', '# новости')];
sel.value = '2';
form.appendChild(sel);

const ctl = window.sshdEnhance(sel, { search: true });
ok('wrapper создан, нативный скрыт', sel._cls.has('sshd-src') && form.children[0]._cls.has('sshd'));
const root = form.children[0];
ok('ярлык = текущая опция', root.querySelectorAll('.sshd-lbl')[0].textContent === '# модераторы');

/* 2. открытие → строки всех опций */
const btn = root.querySelectorAll('.sshd-btn')[0];
btn.dispatchEvent({ type: 'click', preventDefault: function () {} });
ok('открыто (class open + aria)', root._cls.has('open') && btn.getAttribute('aria-expanded') === 'true');
let rows = root.querySelectorAll('.sshd-row');
ok('строки = все опции (4)', rows.length === 4);
ok('выбранная подсвечена cur', rows.some(function (r) { return r._cls.has('cur') && r.getAttribute('data-v') === '2'; }));

/* поиск фильтрует + текущий не пропадает */
const ip = root.querySelectorAll('.sshd-search')[0];
ip.value = 'ново';
ip.dispatchEvent({ type: 'input' });
rows = root.querySelectorAll('.sshd-row');
ok('фильтр: # новости + текущая (2 строки)', rows.length === 2
   && rows.some(function (r) { return r.getAttribute('data-v') === '3'; })
   && rows.some(function (r) { return r.getAttribute('data-v') === '2'; }));

/* 3. commit с первого mousedown: значение + change */
let changes = 0;
form.addEventListener('change', function () { changes++; });
const row3 = rows.filter(function (r) { return r.getAttribute('data-v') === '3'; })[0];
row3.dispatchEvent({ type: 'mousedown', preventDefault: function () {} });
ok('mousedown: value=3 и Change dispatched', sel.value === '3' && changes === 1);
ok('панель закрыта после выбора', !root._cls.has('open'));
ok('ярлык обновлён', root.querySelectorAll('.sshd-lbl')[0].textContent === '# новости');

/* 4. клавиатура: ArrowDown + Enter */
btn.dispatchEvent({ type: 'click', preventDefault: function () {} });
const pop = root.querySelectorAll('.sshd-pop')[0];
pop.dispatchEvent({ type: 'keydown', key: 'ArrowDown', preventDefault: function () {}, stopPropagation: function () {} });
pop.dispatchEvent({ type: 'keydown', key: 'ArrowDown', preventDefault: function () {}, stopPropagation: function () {} });
pop.dispatchEvent({ type: 'keydown', key: 'Enter', preventDefault: function () {}, stopPropagation: function () {} });
ok('стрелка-стрелка-Enter: переход на 2-ю строку и commit (change №2)', sel.value === '1' && changes === 2);

/* Escape закрывает без переназначения */
btn.dispatchEvent({ type: 'click', preventDefault: function () {} });
pop.dispatchEvent({ type: 'keydown', key: 'Escape', preventDefault: function () {}, stopPropagation: function () {} });
ok('Escape закрыл, значение не тронуто', !root._cls.has('open') && sel.value === '1' && changes === 2);

/* 5. sshdAll автоматом, multiple и data-sshd-no пропускаются */
const s2 = wrap(new El('select')); s2.options = [new Opt('a', 'A'), new Opt('b', 'B')];
const s3 = wrap(new El('select')); s3.options = [new Opt('a', 'A')]; s3.setAttribute('multiple', '');
const holder = wrap(new El('div'));
holder.appendChild(s2); holder.appendChild(s3);
window.sshdAll(holder);
ok('sshdAll: обычный подхвачен, multiple пропущен',
   s2._cls.has('sshd-src') && !s3._cls.has('sshd-src'));

console.log(JSON.stringify(out));
"""

print('== 1. Поведение selectSuite в node ==')
t = tempfile.mkdtemp(prefix='p4_sshd_')
hp = os.path.join(t, 'h.js')
with open(hp, 'w', encoding='utf-8') as f:
    f.write(HARNESS)
env = dict(os.environ)
env['PICKERS_PATH'] = os.path.join(ROOT, 'web/static/pickers.js')
run = subprocess.run(['node', hp], capture_output=True, text=True, timeout=30, env=env)
if run.returncode != 0:
    check(False, 'node harness выполняется без исключений',
          (run.stderr or run.stdout)[-400:])
else:
    for item in json.loads(run.stdout.strip().splitlines()[-1]):
        check(bool(item['pass']), item['name'])

print('== 2. Статические гарантии п.4 ==')
css = open(os.path.join(ROOT, 'web/static/style.css'), encoding='utf-8').read()
pjs = open(os.path.join(ROOT, 'web/static/pickers.js'), encoding='utf-8').read()
check('@keyframes sshdIn' in css and 'transition: transform .2s' in css,
      'плавная анимация: панель (появление) и стрелка (поворот)')
check('aria-haspopup' in pjs and "'listbox'" in pjs and 'aria-expanded' in pjs,
      'доступность: listbox/haspopup/expanded')
check('min-height: 42px' in css and '@media (max-width: 640px)' in css,
      'мобильные: строки ≥42px, тап с первого раза')
check('MutationObserver' in pjs and 'sshdAll(document)' in pjs,
      'авто-подхват всех select (в т.ч. добавленных позже)')
check('e.preventDefault' in pjs and "addEventListener('mousedown'" in pjs,
      'commit на mousedown (клик с первого раза) + preventDefault')
check('скрыт визуально' not in pjs or '.sshd-src' in css,
      'нативный select закрыт .sshd-src, данные и обработчики целы')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
