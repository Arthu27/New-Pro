# -*- coding: utf-8 -*-
"""Регрессия «Экрана дежурного» (/mod-kiosk) после редизайна.

Новые способности экрана (каждая проверяется живым исполнением JS
страницы в Node-харнессе с DOM-стабами):
  • ситуация дня (Спокойно / Внимание / Критично) — считается из данных;
  • пульс сервера: онлайн/участники/пинг + спарклайн пинга;
  • KPI с живыми дельтами (+N, когда счётчик вырос);
  • 24-часовая гистограмма мод-действий (24 столбика, цвет = строгость);
  • топ дежурных сегодня (ранжирование, медали);
  • таймер смены «до конца HH:MM:SS» + прогресс-бар;
  • вспышка панели при появлении новых действий;
  • ночной режим (T) — общий механизм темы панели (localStorage);
  • горячие клавиши: F — фулскрин, T — тема, Esc — назад в штаб.

Запуск: python3 tests/test_mod_kiosk.py
"""
import os
import re
import subprocess
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_kiosk_test_')
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


TPL = open(os.path.join(ROOT, 'web', 'templates', 'mod_kiosk.html'),
           encoding='utf-8').read()

print('== статические проверки шаблона ==')
check('kiosk-sit' in TPL and 'renderSituation' in TPL,
      'индикатор ситуации дня (Спокойно/Внимание/Критично)')
check('kiosk-pulse' in TPL and '/api/stats' in TPL and 'drawSpark' in TPL,
      'пульс сервера (онлайн/участники/пинг) со спарклайном')
check('kioskHisto' in TPL and 'renderHisto' in TPL,
      '24-часовая гистограмма мод-действий')
check('kioskTop' in TPL and 'renderTop' in TPL,
      'топ дежурных сегодня')
check('kioskDutyCountdown' in TPL and 'tickShiftTimer' in TPL and 'kShiftFill' in TPL,
      'живой таймер смены с прогресс-баром')
check("localStorage.setItem('hakumo_theme'" in TPL,
      'ночной режим через общий механизм темы панели')
check('kiosk-flash' in TPL,
      'вспышка панели при новых действиях (kiosk-flash)')
check("e.key === 'F'" in TPL and "e.key === 'T'" in TPL and "e.key === 'Escape'" in TPL,
      'горячие клавиши F/T/Esc')
check(TPL.count('kiosk-kpi"') >= 8 or TPL.count('class="kiosk-kpi"') >= 8,
      'KPI-плиток не меньше 8 (мьюты/баны/варны/апелляции/демки/грани/действия/пинг)')
check('П.5 — критическая сцена' in TPL and '#f5f6f8' in TPL,
      'критический фон первого кадра на месте (анти-белый-экран)')
check('name="viewport"' in TPL, 'viewport meta на месте')
check('prefers-reduced-motion' in TPL, 'анимации уважают reduced-motion')

print('\n== гарнитура: экран обязан наследовать шрифт панели ==')
import glob as _glob
import re as _re
# 1) сам киоск: body.kiosk задаёт панельный шрифт, а не inherit (баг 29.08.2026:
#    font-family:inherit на body брал шрифт с html → Times New Roman на всём экране)
_body_kiosk = _re.search(r'body\.kiosk\s*\{[^}]*\}', TPL, _re.S)
check(_body_kiosk and 'font-family: var(--font)' in _body_kiosk.group(0),
      'body.kiosk задаёт font-family: var(--font) (панельная гарнитура Inter/Segoe UI)')
check("'JetBrains Mono', monospace" not in TPL,
      'моноширинный шрифт через var(--mono), без сырых строк')
# standalone-страница обязана сама подключать веб-шрифты и иконки
# (баг 29.08.2026: экран жил без fonts.css → системный шрифт вместо Inter,
#  и без fontawesome → все иконки пустыми квадратами)
check('/static/vendor/fonts/fonts.css' in TPL,
      'подключён веб-шрифт панели (fonts.css: Inter, JetBrains Mono)')
check('/static/vendor/fontawesome/css/all.min.css' in TPL,
      'подключён FontAwesome — иконки не пустые квадраты')
# 2) системно: ни в одном шаблоне правило с селектором body не сбрасывает
#    гарнитуру в inherit/serif — иначе страница выпадает из шрифта панели
_bad_body_font = []
for _f in sorted(_glob.glob(os.path.join(ROOT, 'web', 'templates', '*.html'))):
    _css = '\n'.join(_re.findall(r'<style>(.*?)</style>', open(_f, encoding='utf-8').read(), _re.S))
    for _m in _re.finditer(r'(?:^|\})\s*([^{}]*\bbody\b[^{}]*)\{([^{}]*)\}', _css, _re.M):
        _decl = _m.group(2)
        _ff = _re.search(r'font-family\s*:\s*([^;]+)', _decl)
        if _ff and _re.search(r'\b(inherit|Times)\b|(?<!sans-)\bserif\b', _ff.group(1)):
            _bad_body_font.append(f"{os.path.basename(_f)}: body → {(_ff.group(1)).strip()}")
check(not _bad_body_font,
      f'ни один шаблон не сбрасывает шрифт body ({len(_bad_body_font)} наруш.)'
      + ('; ' + '; '.join(_bad_body_font) if _bad_body_font else ''))

print('\n== страница рендерится ==')
from web.app import app as _flask_app  # noqa: E402
client = _flask_app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'KioskTest'
    s['role'] = 'mod'
    s['main_guild_id'] = '777'
r = client.get('/mod-kiosk')
check(r.status_code == 200, f'/mod-kiosk → {r.status_code}')
_html = r.get_data(as_text=True)
for marker in ('kiosk-sit', 'kiosk-pulse', 'kioskHisto', 'kioskTop',
               'kioskDutyCountdown', 'kioskTheme', 'kkSpark'):
    check(marker in _html, f'готовый HTML содержит {marker}')

print('\n== Node-харнесс: живое исполнение логики экрана ==')
# извлекаем inline-скрипты (шим + главный), подменяем Jinja-вставки
scripts = re.findall(r'<script>(.*?)</script>', TPL, re.S)
check(len(scripts) >= 2, f'inline-скриптов: {len(scripts)} (шим + главный)')
page_js = '\n;\n'.join(scripts).replace("{{ main_guild_id }}", "777")

harness = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');  // node HARNESS TARGET

// ── мини-DOM ──
const byId = {};
const themeSets = [];
const lsSet = [];
const keyHandlers = [];
let fullscreenAsked = 0;

function makeEl(id) {
  const e = {
    id, textContent: '', _innerHTML: '', title: '', hidden: false,
    className: '', style: {}, scrollWidth: 500,
    _classes: new Set(), _handlers: {},
    parentElement: { clientWidth: 1200 }
  };
  Object.defineProperty(e, 'innerHTML', {
    get() { return this._innerHTML; },
    set(v) { this._innerHTML = String(v); }
  });
  e.classList = {
    add(c) { e._classes.add(c); }, remove(c) { e._classes.delete(c); },
    contains(c) { return e._classes.has(c); },
    toggle(c, f) { const on = f === undefined ? !e._classes.has(c) : !!f; on ? e._classes.add(c) : e._classes.delete(c); }
  };
  e.addEventListener = (t, fn) => { e._handlers[t] = e._handlers[t] || []; e._handlers[t].push(fn); };
  e.click = () => { (e._handlers['click'] || []).forEach(fn => fn()); };
  e.setAttribute = (k, v) => { e['attr_' + k] = String(v); };
  e.getAttribute = (k) => (e['attr_' + k] === undefined ? null : e['attr_' + k]);
  e.querySelector = (sel) => sel === 'svg' ? (e._svg = e._svg || { innerHTML: '' }) : null;
  return e;
}
const docEl = {
  _theme: null,
  setAttribute(k, v) { if (k === 'data-theme') { this._theme = v; themeSets.push(v); } },
  getAttribute(k) { return k === 'data-theme' ? this._theme : null; },
  requestFullscreen() { fullscreenAsked++; }
};
const doc = {
  getElementById: (id) => byId[id] || (byId[id] = makeEl(id)),
  documentElement: docEl,
  addEventListener: (t, fn) => { if (t === 'keydown') keyHandlers.push(fn); },
  fullscreenElement: null
};

// ── данные API (мутируемые — вторым проходом проверяем дельты) ──
let DATA = {};
function resetData() {
  const now = Date.now();
  const iso = (msAgo) => new Date(now - msAgo).toISOString();
  DATA = {
    stats: { online: 213, users: 1247, latency: 105.4, status: 'online' },
    temp: { muts: [1, 2], bans: [1, 2, 3], scheduled: [] },
    warnings: [0, 1, 2, 3, 4].map(i => ({ timestamp: iso(60000 * (i + 1)) })),
    proofs: { items: [1, 2, 3, 4, 5, 6, 7] },
    guilds: [{ id: '777', name: 'Главный' }],
    appeals: { pending: 2 },
    risk: { risk: { edge: 1 } },
    tickets: [1, 2],
    threat: { threat_score: 70, threat_level: 'высокий' },
    shifts: { current: { name: 'Артём', start: iso(3600000), end: iso(-7200000) } },
    logs: [
      { timestamp: iso(300000), action: 'ban', user_name: 'Гость', mod_name: 'Артём', reason: 'спам' },
      { timestamp: iso(320000), action: 'warn', user_name: 'Лена', mod_name: 'Артём', reason: 'флуд' },
      { timestamp: iso(340000), action: 'mute', user_name: 'Макс', mod_name: 'Соня', reason: 'капс' },
      { timestamp: iso(360000), action: 'ban', user_name: 'Иван', mod_name: 'Артём', reason: 'реклама' },
      { timestamp: iso(25 * 3600000), action: 'ban', user_name: 'Старый', mod_name: 'Артём', reason: 'вне окна 24ч' }
    ],
    feed: { items: [{ ts: Math.floor(now / 1000) - 60, title: 'Тикет закрыт', user: 'Соня', detail: '#12', type: 'ticket', icon: 'fa-ticket', link: '/tickets' }] }
  };
}
resetData();

function router(url, opts) {
  const j = (d) => Promise.resolve({ ok: true, json: () => Promise.resolve(d) });
  if (url === '/api/stats') return j(DATA.stats);
  if (url === '/api/temp-mod/active') return j(DATA.temp);
  if (url === '/api/warnings') return j(DATA.warnings);
  if (url === '/api/proofs') return j(DATA.proofs);
  if (url === '/api/guilds') return j(DATA.guilds);
  if (url.indexOf('/appeals/overview') !== -1) return j(DATA.appeals);
  if (url.indexOf('/mod-control/overview') !== -1) return j(DATA.risk);
  if (url.indexOf('/tickets') !== -1) return j(DATA.tickets);
  if (url.indexOf('/threat-index') !== -1) return j(DATA.threat);
  if (url.indexOf('/staff-shifts') !== -1) return j(DATA.shifts);
  if (url === '/api/logs') return j(DATA.logs);
  if (url === '/api/activity-feed') return j(DATA.feed);
  return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
}

const liveFns = [];
const win = {
  fetch: router,
  fetchCachedJSON: (url) => router(url).then(r => r.json()),
  setLiveRefresh: (fn, ms) => liveFns.push(fn),
  showToast: () => {},
  location: { href: '' }
};

function fail(msg) { console.error('FAIL: ' + msg); process.exit(1); }
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

(async () => {
  new Function('document', 'window', 'localStorage', 'fetch', 'setInterval', src)(
    doc, win,
    { getItem: () => null, setItem: (k, v) => lsSet.push(k + '=' + v) },
    router,
    () => 1
  );
  await sleep(60);  // refresh() дотягивает все API

  // 1) Ситуация: банов 3(+2) + грань 1(+2) + угроза 70(+2) = 6 → КРИТИЧНО
  const sit = byId['kioskSit'];
  if (!sit) fail('kioskSit нет');
  if (sit.getAttribute('data-level') !== 'err') fail('уровень ситуации не err: ' + sit.getAttribute('data-level'));
  if (byId['kioskSitText'].textContent.indexOf('Критическая') === -1) fail('текст ситуации не критичный');

  // 2) Пульс сервера
  if (byId['kpOnlineV'].textContent !== '213') fail('онлайн не показан: ' + byId['kpOnlineV'].textContent);
  if (byId['kpMembersV'].textContent.replace(/\u00A0/g, ' ') !== '1 247') fail('участники не показаны: ' + byId['kpMembersV'].textContent);
  if (byId['kpPingV'].textContent.indexOf('105') === -1) fail('пинг не показан');

  // 3) KPI + спарклайн (рисуется со второй точки — дёргаем опрос пульса ещё раз)
  if (typeof liveFns[0] === 'function') { liveFns[0](); await sleep(20); }
  if (byId['kkMutes'].textContent !== '2') fail('KPI мьютов неверен');
  if (byId['kkBans'].textContent !== '3') fail('KPI банов неверен');
  if (byId['kkToday'].textContent !== '4') fail('KPI «действий сегодня» должен считать только сегодня (4), got ' + byId['kkToday'].textContent);
  if (byId['kkTodayD'] && byId['kkTodayD'].classList.contains('show')) fail('ложная дельта при первом рендере');
  const spark = byId['kkSpark'] && byId['kkSpark']._svg;
  if (!spark || spark.innerHTML.indexOf('polyline') === -1) fail('спарклайн пинга не нарисован');

  // 4) Гистограмма: ровно 24 столбика, час назад — бан+варн+мут, вчерашний — вне окна
  const bars = (byId['kioskHisto'].innerHTML.match(/k-h-bar/g) || []).length;
  if (bars !== 24) fail('столбиков гистограммы ' + bars + ', а нужно 24');
  const hist = byId['kioskHisto'].innerHTML;
  if (hist.indexOf('data-sev="hard"') === -1 || hist.indexOf('data-sev="soft"') === -1
      || hist.indexOf('data-sev="mute"') === -1) fail('сегменты строгости не нарисованы');
  if (hist.indexOf('is-now') === -1) fail('текущий час не подсвечен');
  /* оба бана в одном часе — один сегмент с весом 2 (стек) */
  if (hist.indexOf('data-sev="hard" style="flex:2"') === -1)
    fail('два бана в одном часе должны дать один hard-сегмент с flex:2');

  // 5) Топ дежурных: Артём (3) > Соня (1), первому — медаль
  const top = byId['kioskTop'].innerHTML;
  if (top.indexOf('Артём') === -1 || top.indexOf('Соня') === -1) fail('топ не построен');
  if (top.indexOf('fa-medal') === -1) fail('медаль лидеру не выдана');
  const iA = top.indexOf('Артём'), iS = top.indexOf('Соня');
  if (iA === -1 || iS === -1 || iA > iS) fail('порядок топа неверен (лидер должен быть первым)');

  // 6) Таймер смены: смена идёт (1 из 3 часов) → «до конца смены», прогресс ≈ 33%
  if (byId['kioskDutyCountdown'].textContent.indexOf('до конца смены') === -1)
    fail('таймер до конца смены не показан: ' + byId['kioskDutyCountdown'].textContent);
  const w = parseFloat(byId['kShiftFill'].style.width);
  if (!(w > 30 && w < 40)) fail('прогресс смены должен быть ~33%, got ' + w);

  // 7) Лента событий панели
  if (byId['kioskActivity'].innerHTML.indexOf('Тикет закрыт') === -1) fail('лента событий пуста');
  if (byId['kioskActions'].innerHTML.indexOf('Артём') === -1) fail('мод-действия не отрисованы');

  // 8) Дельта: баны выросли 3 → 4, на плитке появляется +1
  DATA.temp = { muts: [1, 2], bans: [1, 2, 3, 4], scheduled: [] };
  const loadMetrics = liveFns[1];
  if (typeof loadMetrics !== 'function') fail('loadMetrics не в live-очереди');
  loadMetrics();
  await sleep(40);
  if (byId['kkBans'].textContent !== '4') fail('KPI банов не обновился');
  if (!byId['kkBansD'].classList.contains('show') || byId['kkBansD'].textContent !== '+1')
    fail('живая дельта +1 не показана: ' + byId['kkBansD'].textContent + ' show=' + byId['kkBansD'].classList.contains('show'));

  // 9) Ситуация успокаивается: банов 0, грань 0, угроза 10 → «спокойная»
  DATA.temp = { muts: [], bans: [], scheduled: [] };
  DATA.risk = { risk: { edge: 0 } };
  DATA.threat = { threat_score: 10, threat_level: 'низкий' };
  loadMetrics();
  await sleep(40);
  if (sit.getAttribute('data-level') !== 'ok') fail('уровень ситуации не успокоился: ' + sit.getAttribute('data-level'));

  // 10) Ночной режим: клик — data-theme=dark + localStorage (механизм панели)
  byId['kioskTheme'].click();
  if (docEl._theme !== 'dark') fail('тема не переключилась в dark');
  if (!lsSet.some(x => x === 'hakumo_theme=dark')) fail('тема не сохранена в localStorage панели');
  if (byId['kioskThemeIcon'].className.indexOf('fa-sun') === -1) fail('иконка темы не сменилась на солнце');
  byId['kioskTheme'].click();
  if (docEl._theme !== 'light') fail('тема не вернулась в light');

  // 11) Горячие клавиши: F — фулскрин, Esc — назад в штаб
  if (!keyHandlers.length) fail('keydown не подписан');
  keyHandlers[0]({ key: 'f', target: { tagName: 'DIV' } });
  if (fullscreenAsked !== 1) fail('F не просит фулскрин');
  keyHandlers[0]({ key: 'Escape', target: { tagName: 'DIV' } });
  if (win.location.href !== '/mod-center') fail('Esc не ведёт в штаб: ' + win.location.href);

  console.log('OK: ситуация, пульс, дельты KPI, 24-часовая гистограмма, топ дежурных, таймер смены, ночной режим, клавиши');
})().catch(e => { console.error('ИСКЛЮЧЕНИЕ: ' + (e && e.message)); process.exit(1); });
"""

_js_path = os.path.join(_TMP, 'kiosk_page.js')
with open(_js_path, 'w', encoding='utf-8') as fh:
    fh.write(page_js)
_h_path = os.path.join(_TMP, 'kiosk_harness.js')
with open(_h_path, 'w', encoding='utf-8') as fh:
    fh.write(harness)
proc = subprocess.run(['node', _h_path, _js_path],
                      capture_output=True, text=True, timeout=60)
check(proc.returncode == 0,
      'харнесс Node: все способности экрана работают на живом JS'
      + (f' ({proc.stdout.strip()})' if proc.stdout.strip() else '')
      + (f' [{proc.stderr.strip()}]' if proc.stderr.strip() else ''))

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
