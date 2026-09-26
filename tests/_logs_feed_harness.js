/* Живой прогон ленты «Журнала модерации» (node, без DOM): карточки,
   тона, монограммы, дни, «сколько назад». Вызывается из
   tests/test_logs_journal.py; печатает JSON-строку результата. */
'use strict';
const fs = require('fs');
const path = require('path');

const root = path.dirname(__dirname);
const tpl = fs.readFileSync(path.join(root, 'web/templates/logs.html'), 'utf8');

/* вырезаем чистое ядро скрипта: от esc до таблицы — только определения,
   исполнения нет (start() остаётся за скобками) */
const begin = tpl.indexOf('function esc(s)');
const end = tpl.indexOf('/* ── строка таблицы');
if (begin < 0 || end < 0 || end < begin) {
  console.log(JSON.stringify({ ok: false, errors: ['ядро ленты не найдено в шаблоне'], pass: 0 }));
  process.exit(0);
}
global.window = {};
/* indirect eval — объявления попадают в глобальную область,
   а не в строгую область модуля */
(0, eval)(tpl.slice(begin, end));

const out = { ok: true, errors: [], pass: 0 };
function t(cond, name, detail) {
  if (cond) { out.pass++; }
  else { out.ok = false; out.errors.push(name + (detail ? ' [' + detail + ']' : '')); }
}
function H(raw) { return esc(raw); }  /* как на странице: hlEsc || esc */

/* ── классификация действий ── */
t(actionKind('Бан') === 'ban', 'kind: Бан → ban');
t(actionKind('Разбан') === 'unban', 'kind: Разбан → unban');
t(actionKind('Войс-мут снят') === 'unmute', 'kind: Войс-мут снят → unmute');
t(actionKind('Таймаут') === 'timeout', 'kind: Таймаут → timeout');
t(actionKind('Предупреждение') === 'warn', 'kind: Предупреждение → warn');

/* ── срок ── */
t(fmtDur(150) === '2 ч 30 мин', 'fmtDur: 150 мин → «2 ч 30 мин»', fmtDur(150));
t(fmtDur(60) === '1 ч', 'fmtDur: 60 мин → «1 ч»', fmtDur(60));
t(fmtDur(0) === '', 'fmtDur: без срока — пусто');

/* ── живое время ── */
t(relTime(new Date(Date.now() - 20e3).toISOString()) === 'только что', 'relTime: только что');
t(relTime(new Date(Date.now() - 5 * 60e3).toISOString()) === '5 мин назад', 'relTime: 5 мин назад');
t(relTime(new Date(Date.now() - 2 * 3600e3).toISOString()) === '2 ч назад', 'relTime: 2 ч назад');
t(relTime(new Date(Date.now() - 30 * 86400e3).toISOString()) === '', 'relTime: старше недели — пусто (покажем дату)');

/* ── дни ── */
t(dayLabel(new Date().toISOString()) === 'Сегодня', 'день: сегодня');
t(dayLabel(new Date(Date.now() - 86400e3).toISOString()) === 'Вчера', 'день: вчера');
t(dayLabel('2026-01-05T12:00:00+00:00').indexOf('января') !== -1, 'день: 5 января', dayLabel('2026-01-05T12:00:00+00:00'));

/* ── монограмма ── */
t(initialOf('toxicguy') === 'T', 'монограмма: первая буква — заглавная');
t(hueOf('night') === hueOf('night') && hueOf('night') >= 0 && hueOf('night') < 360,
  'монограмма: цвет стабилен и в диапазоне hsl');
t(hueOf('a') !== hueOf('b'), 'монограмма: разным именам — разные цвета');

/* ── карточка: тон, иконка, состав ── */
const banCard = feedCard({
  action: 'Бан', user_name: 'toxicguy', mod_name: 'lina.mod',
  reason: 'Флуд', duration: 150, until: new Date(Date.now() + 3600e3).toISOString(),
  timestamp: new Date(Date.now() - 10 * 60e3).toISOString()
}, 'ban', H);
t(banCard.indexOf('jl-card tone-critical') !== -1, 'карточка бана: красный тон');
t(banCard.indexOf('fa-gavel') !== -1, 'карточка бана: иконка молотка');
t(banCard.indexOf('jl-ava') !== -1 && banCard.indexOf('hsl(') !== -1, 'карточка: монограмма с цветом');
t(banCard.indexOf('toxicguy') !== -1 && banCard.indexOf('lina.mod') !== -1
  && banCard.indexOf('fa-user-shield') !== -1, 'карточка: участник ← модератор');
t(banCard.indexOf('jl-reason') !== -1 && banCard.indexOf('Флуд') !== -1, 'карточка: причина цитатой');
t(banCard.indexOf('jl-dur') !== -1 && banCard.indexOf('2 ч 30 мин') !== -1, 'карточка: чип срока');
t(banCard.indexOf('10 мин назад') !== -1, 'карточка: «сколько назад» живое');

t(feedCard({ action: 'Разбан', user_name: 'u', timestamp: new Date().toISOString() }, 'unban', H)
  .indexOf('tone-ok') !== -1, 'разбан: зелёный тон');
t(feedCard({ action: 'Мут', user_name: 'u', timestamp: new Date().toISOString() }, 'mute', H)
  .indexOf('fa-volume-xmark') !== -1, 'мьют: иконка перечёркнутого звука');
t(feedCard({ action: 'Таймаут', user_name: 'u', timestamp: new Date().toISOString() }, 'timeout', H)
  .indexOf('fa-hourglass-half') !== -1, 'таймаут: песочные часы');

/* без причины/модератора блоки не рисуются */
const bare = feedCard({ action: 'Кик', user_name: 'ghost', timestamp: new Date().toISOString() }, 'kick', H);
t(bare.indexOf('jl-reason') === -1, 'без причины — блока причины нет');
t(bare.indexOf('fa-user-shield') === -1, 'без модератора — строки модератора нет');

/* XSS: причина уходит в esc() */
const xss = feedCard({
  action: 'Бан', user_name: 'u', mod_name: 'm',
  reason: '<script>alert(1)</script>', timestamp: new Date().toISOString()
}, 'ban', H);
t(xss.indexOf('<script>') === -1 && xss.indexOf('&lt;script&gt;') !== -1, 'XSS: причина экранирована');

/* ── лента: разделители дней ── */
/* даты задаём календарно (полдень дня), а не сдвигом часов — иначе
   между 00:00 и 02:00 ночи «now − 26 ч» уезжает на два дня назад
   и подпись «Вчера» не собирается (поймано полным прогоном 2026-09-07) */
const _now = new Date();
const noon = (d) => new Date(_now.getFullYear(), _now.getMonth(),
                             _now.getDate() - d, 12, 0, 0);
const feed = renderFeed([
  { action: 'Бан', user_name: 'a', mod_name: 'm', reason: 'r', timestamp: _now.toISOString() },
  { action: 'Кик', user_name: 'b', mod_name: 'm', reason: 'r', timestamp: noon(1).toISOString() },
  { action: 'Мут', user_name: 'c', mod_name: 'm', reason: 'r', timestamp: noon(2).toISOString() }
], H);
t((feed.match(/jl-day/g) || []).length === 3, 'лента: три разделителя на три дня');
t(feed.indexOf('Сегодня') !== -1 && feed.indexOf('Вчера') !== -1, 'лента: подписи «Сегодня»/«Вчера»');
t(feed.indexOf('jl-card') !== -1, 'лента: карточки собраны');

/* ── голый ID вместо имени — моноширинный чип, не «ник из 18 цифр» ── */
t(isRawId('723456789012345679') === true, 'isRawId: снежок распознан');
t(isRawId('toxicguy') === false && isRawId('123') === false,
  'isRawId: короткие числа и ники не трогаем');
t(whoCell('723456789012345679', H).indexOf('id-chip') !== -1
  && whoCell('723456789012345679', H).indexOf('jl-cname') === -1,
  'голый ID рисуется чипом «ID …», не жирным ником');
t(whoCell('toxicguy', H).indexOf('jl-cname') !== -1, 'ник остаётся ником');
const idCard = feedCard({
  action: 'Бан', user_name: '723456789012345679', mod_name: 'lina.mod',
  reason: 'r', timestamp: new Date().toISOString()
}, 'ban', H);
t(idCard.indexOf('id-chip') !== -1, 'карточка: неизвестный — чип ID');
t(idCard.indexOf('>#</span>') !== -1, 'карточка: монограмма «#» у неизвестного');

console.log(JSON.stringify(out));
