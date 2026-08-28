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


// ── Крайние имена (п.6: эмодзи/пробелы/спецсимволы/кириллица/длина) ─────
function mkHarness(nameList, selected) {
  var opts2 = [mkOpt('', '— не выбрано —')].concat(nameList.map(function (n, i) {
    return mkOpt(String(1000 + i), n);
  }));
  var sel2 = {
    options: opts2, value: String(selected),
    addEventListener: function (type, fn) { sel2._fl = fn; },
  };
  var inp2 = {
    value: '',
    classList: { toggle: function () {} },
    _ls: {},
    addEventListener: function (type, fn) { inp2._ls[type] = fn; },
  };
  window.attachSelectSearch(sel2, inp2);
  function vis() {
    return opts2.filter(function (o) { return !o.hidden; }).map(function (o) { return o.value; });
  }
  return { sel: sel2, inp: inp2, vis: vis, opts: opts2 };
}

var CRAY = '🔥💀⭐ #1 Мой Любимый Голосовой-Канал @Снап* {топ} [vip] 42'.repeat(3);
var big1 = mkHarness([
  CRAY,                          // очень длинное имя с эмодзи и спецсимволами
  'БОЛЬШИЕ БУКВЫ И Обычные',     // капс-лок кириллица
  'My Chat With Spaces  And  Doubles',
  'c++ voice',                   // спецсимволы в начале (латиница)
  'emoji-only 💯🎉🔥',
  'trim  edge  name',
], '1001');

// длинное имя: ищется по подстроке из середины, без эмодзи, регистр любой
big1.inp.value = 'любимый голосовой';
big1.inp._ls.input();
t(big1.vis().indexOf('1000') !== -1 && big1.sel.value === '1001',
  'edge: очень длинное имя находится по подстроке из середины; значение не меняется');

big1.inp.value = 'БОЛЬШИЕ ';
big1.inp._ls.input(); // капс-запрос ищет капс-имя
t(big1.vis().indexOf('1001') !== -1, 'edge: КАПС запрос находит КАПС имя');

big1.inp.value = 'chat with spaces';
big1.inp._ls.input(); // сжатые пробелы vs двойные в имени
t(big1.vis().indexOf('1002') !== -1, 'edge: двойные пробелы в имени не мешают');

big1.inp.value = 'c++';
big1.inp._ls.input(); // спецсимвол-запрос: нормализуется до «c» и находит
t(big1.vis().indexOf('1003') !== -1, 'edge: запрос со спецсимволами «c++» находит канал');

big1.inp.value = '';
big1.inp._ls.input(); // пустой запрос — весь список
t(big1.vis().length === 7, 'edge: сброс возвращает все 7 вариантов');

// ── 1500 каналов: фильтр не теряет, не подлагивает, скролл-независим ────
var NAMES = [];
for (var i2 = 0; i2 < 1500; i2++) NAMES.push((i2 % 3 ? '# ' : '🔊 ') + 'канал-' + i2 + ' всеобший');
NAMES[1499] = '⭐ ИГОЛКА стог сена ⭐';
var big2 = mkHarness(NAMES, '2499');
var t0 = Date.now();
big2.inp.value = 'иголка';
big2.inp._ls.input();
var ms = Date.now() - t0;
t(big2.vis().length === 2 && big2.vis().indexOf('2499') !== -1, // none + иголка(она же выбранная)
  'edge: среди 1500 опций находится иголка; видны none и совпадение');
var before = big2.sel.value;
big2.inp.value = 'ZZZZ ничего нет';
big2.inp._ls.input();
t(big2.vis().length === 2 && big2.sel.value === before, // none + selected всегда видны
  'edge: пустой результат поиска НЕ скрывает выбранное и none; значение неизменно');
big2.inp.value = '';
big2.inp._ls.input();
t(big2.vis().length === 1501, 'edge: все 1500 каналов возвращаются после сброса (ничего не пропало)');
var t1 = Date.now();
big2.inp.value = 'канал';
big2.inp._ls.input();
var ms2 = Date.now() - t1;
t(ms < 500 && ms2 < 500, 'edge: фильтр 1500 опций быстрый (' + ms + 'ms/' + ms2 + 'ms)');

console.log(JSON.stringify(out));
