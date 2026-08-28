/* Живой прогон pickers.js: attachSelectSearch + pickerNorm (node, без DOM).
   Вызывается из tests/test_ux_pickers.py; печатает JSON-строку результата. */
'use strict';
const fs = require('fs');
const path = require('path');

const root = path.dirname(__dirname);
const src = fs.readFileSync(path.join(root, 'web/static/pickers.js'), 'utf8');

global.window = {};
global.document = {
  createElement: function () { throw new Error('harness: DOM не нужен'); },
  addEventListener: function () {},
};
eval(src);

const out = { ok: true, errors: [] };
function t(cond, name, detail) {
  if (!cond) { out.ok = false; out.errors.push(name + (detail ? ' [' + detail + ']' : '')); }
}

// ── pickerNorm ───────────────────────────────────────────────────────────
t(window.pickerNorm('Общий Чат') === 'общий чат', 'norm: регистр снимается');
t(window.pickerNorm('#  логи   модов 🌟') === 'логи модов', 'norm: пробелы и эмодзи не мешают');
t(window.pickerNorm('Апа-БАН') === 'апа бан', 'norm: дефис как пробел');
t(window.pickerNorm('🌟🌟') === '', 'norm: чистые эмодзи = пустой запрос (без ошибок)');

// ── attachSelectSearch ───────────────────────────────────────────────────
function mkOpt(v, txt) { return { value: v, textContent: txt, hidden: false }; }
const options = [
  mkOpt('', '— не выбрано —'),
  mkOpt('1', '# Общий Чат'),
  mkOpt('2', '# 🌟 логи  модов'),
  mkOpt('3', '# апа-БАН'),
];
const selListeners = {};
const sel = {
  options: options,
  value: '3',
  addEventListener: function (type, fn) { selListeners[type] = fn; },
};
const input = {
  value: '',
  classList: { toggle: function () {} },
  _ls: {},
  addEventListener: function (type, fn) { input._ls[type] = fn; },
};
window.attachSelectSearch(sel, input);

function visible() {
  return options.filter(function (o) { return !o.hidden; }).map(function (o) { return o.value; });
}

input.value = 'ЛОГИ';
input._ls.input();
t(String(visible()) === ',2,3', 'фильтр: регистр; видны none, совпадение и текущий выбранный');
t(sel.value === '3', 'фильтр не меняет значение (никаких случайных выборов)');

input.value = 'модов';
input._ls.input();
t(String(visible()) === ',2,3', 'фильтр: пробелы/эмодзи в названии канала не мешают найти');

input.value = 'апа бан';
input._ls.input();
t(String(visible()) === ',3', 'фильтр: дефис-пробел перенос заказчика тоже ловит');

input.value = '🌟';
input._ls.input();
t(String(visible()) === ',1,2,3', 'запрос из одних эмодзи = без фильтра (не обнуляет список)');

// Escape чистит запрос
input.value = 'логи';
input._ls.input();
input._ls.keydown({ key: 'Escape' });
t(input.value === '' && String(visible()) === ',1,2,3', 'Escape возвращает полный список');

// фокус на select при набранном запросе мягко очищает фильтр
input.value = 'логи';
input._ls.input();
selListeners.focus();
t(input.value === '' && String(visible()) === ',1,2,3', 'focus select сбрасывает фильтр мягко');

console.log(JSON.stringify(out));
