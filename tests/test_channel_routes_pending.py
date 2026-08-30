# -*- coding: utf-8 -*-
"""Регрессия страницы «Каналы и маршруты»: несохранённые выборы.

Жалоба: «когда нажимаю одну кнопку [сохранить], другая настройка слетает —
приходится по одному настраивать». Причина: chsSave после сохранения ОДНОГО
маршрута вызывал render() всего списка, который перерисовывал остальные
строки из сохранённых значений и ЗАТИРАЛ несохранённые выборы.

Харнесс исполняет настоящий JS страницы (из шаблона) в Node с DOM-стабами и
проверяет: несохранённый выбор живёт в PENDING, переживает сохранение
соседа (без полной перерисовки), «Сохранить всё» применяет всё разом,
«Сбросить» возвращает сохранённые значения, при уходе со страницы —
предупреждение.

Запуск: python3 tests/test_channel_routes_pending.py
"""
import os
import re
import subprocess
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_chs_pending_')
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


TPL = open(os.path.join(ROOT, 'web', 'templates', 'channel_settings.html'),
           encoding='utf-8').read()

print('== статические проверки шаблона ==')
check('var PENDING = {};' in TPL,
      'карта несохранённых изменений (PENDING) на месте')
check('onchange="chsPending(' in TPL,
      'смена канала в строке фиксируется как несохранённая')
check('chsSaveAll' in TPL and 'Сохранить всё' in TPL,
      'кнопка «Сохранить всё» — настраиваем много, сохраняем разом')
check('chsResetPending' in TPL and 'Сбросить' in TPL,
      'кнопка «Сбросить» для несохранённых изменений')
check("beforeunload" in TPL,
      'уход со страницы с несохранёнными маршрутами не молчит')
check(TPL.find('delete PENDING[key]') != -1 and 'render()' in TPL,
      'структура сохранения/перерисовки на месте')

m = re.search(r'<script>(.*?)</script>', TPL, re.S)
check(m is not None, 'скрипт страницы найден для харнесса')

if m:
    script = m.group(1)
    script = script.replace(
        "{% if role == 'admin' or role == 'owner' %}true{% else %}false{% endif %}",
        'true')

    harness = r"""
// Node-харнесс: исполняем настоящий JS страницы с DOM-стабами
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');  // node HARNESS TARGET

const byId = {};
let listRenders = 0;          // сколько раз перерисовывался ВЕСЬ список
const posts = [];             // POST /api/channel-routes/<key>
const toasts = [];
const listeners = [];

function makeEl(id) {
  const e = {
    id, className: '', textContent: '', value: '', disabled: false,
    _innerHTML: '', _outerHTML: '', _classes: new Set()
  };
  Object.defineProperty(e, 'innerHTML', {
    get() { return this._innerHTML; },
    set(v) {
      this._innerHTML = String(v);
      if (id === 'chsList') listRenders++;
    }
  });
  Object.defineProperty(e, 'outerHTML', {
    get() { return this._outerHTML; },
    set(v) { this._outerHTML = String(v); }
  });
  e.classList = {
    toggle(name, force) {
      const on = force === undefined ? !e._classes.has(name) : !!force;
      if (on) e._classes.add(name); else e._classes.delete(name);
    },
    add(n) { e._classes.add(n); },
    remove(n) { e._classes.delete(n); },
    contains(n) { return e._classes.has(n); }
  };
  return e;
}
const docStub = { getElementById: (id) => byId[id] || (byId[id] = makeEl(id)) };
const winStub = {
  renderSafe: (fn) => fn(),
  showToast: (msg, ok) => toasts.push({ msg, ok }),
  addEventListener: (t) => listeners.push(t)
};

const CHANNELS = [
  { id: '111', name: 'general', type: 'text' },
  { id: '222', name: 'доказательства', type: 'text' },
  { id: '333', name: 'апелляции', type: 'text' },
  { id: '444', name: 'приветствия', type: 'text' }
];
const ROUTES = [
  { key: 'proof_channel', label: 'Доказательства', icon: '', what: '', empty: '',
    access: 'Админ', channel_id: '111' },
  { key: 'appeals_channel', label: 'Апелляции', icon: '', what: '', empty: '',
    access: 'Админ', channel_id: null },
  { key: 'welcome_channel', label: 'Приветствия', icon: '', what: '', empty: '',
    access: 'Админ', channel_id: null }
];

function fetchStub(url, opts) {
  const method = (opts && opts.method) || 'GET';
  if (url === '/api/channels') {
    return Promise.resolve({ ok: true, json: () => Promise.resolve(CHANNELS) });
  }
  if (url === '/api/channel-routes') {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, routes: ROUTES }) });
  }
  if (url.indexOf('/api/channel-routes/') === 0 && method === 'POST') {
    posts.push({ url, body: JSON.parse(opts.body) });
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true }) });
  }
  return Promise.resolve({ ok: false, json: () => Promise.resolve({ success: false, error: 'нет такого' }) });
}

function fail(msg) { console.error('FAIL: ' + msg); process.exit(1); }

(async () => {
  new Function('document', 'window', 'fetch',
    src + '\n;globalThis.__chs = { PENDING: () => PENDING, CHS_ROUTES: () => CHS_ROUTES,' +
    ' render, chsPending, chsSave, chsSaveAll, chsResetPending };'
  )(docStub, winStub, fetchStub);
  const X = globalThis.__chs;
  await new Promise(r => setTimeout(r, 30));   // chsLoad() дотягивает данные

  // 1) Загрузка: список отрисован, сохранённые значения на месте
  const list = docStub.getElementById('chsList');
  if (listRenders < 1) fail('список не отрисовался после загрузки');
  if (list.innerHTML.indexOf('value="111" selected') === -1) fail('сохранённый канал не выбран в селекте');
  if (list.innerHTML.indexOf('не сохранено') !== -1) fail('ложное «не сохранено» сразу после загрузки');

  // 2) Пользователь настраивает ДВА маршрута (не сохраняя)
  docStub.getElementById('chs-proof_channel').value = '222';
  X.chsPending('proof_channel');
  docStub.getElementById('chs-appeals_channel').value = '333';
  X.chsPending('appeals_channel');
  if (X.PENDING().proof_channel !== '222') fail('PENDING не поймал выбор proof_channel');
  if (X.PENDING().appeals_channel !== '333') fail('PENDING не поймал выбор appeals_channel');
  if (!docStub.getElementById('chs-cur-proof_channel').outerHTML.match(/не сохранено/)) fail('бейдж «не сохранено» не показан');
  if (!docStub.getElementById('chsPendBar').classList.contains('show')) fail('панель несохранённых не открылась');
  if (docStub.getElementById('chsPendCount').textContent !== '2') fail('счётчик несохранённых != 2');

  // 3) ГЛАВНОЕ: сохраняем ОДИН маршрут — второй несохранённый НЕ СЛЕТАЕТ
  const rendersBefore = listRenders;
  const okSave = await X.chsSave('proof_channel');
  if (!okSave) fail('chsSave вернул false');
  if (X.PENDING().hasOwnProperty('proof_channel')) fail('сохранённый маршрут остался в PENDING');
  if (X.PENDING().appeals_channel !== '333') fail('РЕГРЕССИЯ: несохранённый соседний маршрут слетел!');
  if (listRenders !== rendersBefore) fail('полная перерисовка списка при сохранении одного маршрута (затирает соседей)');
  if (!posts.some(p => p.url.indexOf('proof_channel') !== -1 && p.body.channel_id === '222')) fail('POST не ушёл с верным каналом');
  const savedRoute = X.CHS_ROUTES().find(r => r.key === 'proof_channel');
  if (savedRoute.channel_id !== '222') fail('модель не обновлена после сохранения');
  if (docStub.getElementById('chs-cur-proof_channel').outerHTML.indexOf('доказательства') === -1)
    fail('бейдж сохранённого маршрута не обновился точечно');
  if (docStub.getElementById('chsPendCount').textContent !== '1') fail('счётчик не уменьшился до 1');

  // 4) «Сохранить всё»: оставшиеся несохранённые применяются разом
  await X.chsSaveAll();
  if (Object.keys(X.PENDING()).length !== 0) fail('после «Сохранить всё» PENDING не пуст');
  if (!posts.some(p => p.url.indexOf('appeals_channel') !== -1 && p.body.channel_id === '333')) fail(' appeals_channel не сохранился через «Сохранить всё»');
  if (X.CHS_ROUTES().find(r => r.key === 'appeals_channel').channel_id !== '333') fail('модель appeals не обновлена');
  if (!toasts.some(t => String(t.msg).indexOf('Сохранено маршрутов: 1') !== -1)) fail('итоговый тост «Сохранить всё» не показан');
  if (docStub.getElementById('chsPendBar').classList.contains('show')) fail('панель несохранённых не спряталась');

  // 5) «Сбросить»: несохранённое уходит, сохранённое возвращается
  docStub.getElementById('chs-welcome_channel').value = '444';
  X.chsPending('welcome_channel');
  if (X.PENDING().welcome_channel !== '444') fail('welcome не попал в PENDING');
  X.chsResetPending();
  if (Object.keys(X.PENDING()).length !== 0) fail('после «Сбросить» PENDING не пуст');
  if (!docStub.getElementById('chsPendBar').classList.contains('show') === false) fail('панель не спряталась после сброса');
  if (list.innerHTML.indexOf('value="444" selected') !== -1) fail('сброшенный выбор утёк в селект');

  // 6) Несохранённое ПЕРЕЖИВАЕТ перерисовку (живой рефреш и т.п.)
  docStub.getElementById('chs-welcome_channel').value = '444';
  X.chsPending('welcome_channel');
  X.render();
  if (list.innerHTML.indexOf('value="444" selected') === -1) fail('перерисовка затёрла несохранённый выбор!');
  if (list.innerHTML.indexOf('не сохранено') === -1) fail('перерисовка потеряла бейдж «не сохранено»');

  // 7) Предупреждение при уходе со страницы зарегистрировано
  if (listeners.indexOf('beforeunload') === -1) fail('beforeunload не подписан');

  console.log('OK: несохранённые выборы переживают сохранение соседа, «Сохранить всё» и перерисовки');
})().catch(e => { console.error('ИСКЛЮЧЕНИЕ: ' + (e && e.message)); process.exit(1); });
"""
    _js_path = os.path.join(_TMP, 'page_script.js')
    with open(_js_path, 'w', encoding='utf-8') as fh:
        fh.write(script)
    _h_path = os.path.join(_TMP, 'harness.js')
    with open(_h_path, 'w', encoding='utf-8') as fh:
        fh.write(harness)
    proc = subprocess.run(['node', _h_path, _js_path],
                          capture_output=True, text=True, timeout=60)
    check(proc.returncode == 0,
          'харнесс Node: страница живая — сохранить один ≠ слетает другой'
          + (f' ({proc.stdout.strip()})' if proc.stdout.strip() else '')
          + (f' [{proc.stderr.strip()}]' if proc.stderr.strip() else ''))

print('\n== страница рендерится ==')
from web.app import app as _flask_app  # noqa: E402
client = _flask_app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'ChsTest'
    s['role'] = 'owner'
r = client.get('/channel-settings')
check(r.status_code == 200, f'/channel-settings → {r.status_code}')
check('chsSaveAll' in r.get_data(as_text=True), 'кнопка «Сохранить всё» в готовом HTML')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
