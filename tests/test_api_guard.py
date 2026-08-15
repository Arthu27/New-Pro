# -*- coding: utf-8 -*-
"""API Guard (web/static/api-guard.js): тост на любой не-OK fetch-ответ.

История: пользователь видел в консоли голое «Failed to load resource: 400»
и не понимал, что панель ему сказала. Теперь каждый не-2xx ответ любого
запроса сам всплывает тостом «МЕТОД /путь · HTTP код — причина».

Тест: статика (подключён в base.html, ключевые механики на месте) +
функциональный прогон скрипта в Node (vm-песочница с моками fetch/showToast,
если node есть в системе — иначе функциональная часть пропускается).

Запуск: python3 tests/test_api_guard.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_guard_test_')
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


JS_PATH = os.path.join(ROOT, 'web', 'static', 'api-guard.js')

print('== 1. Подключение и статика ==')
base = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('/static/api-guard.js' in base, 'api-guard.js подключён в base.html')
check(base.count('/static/api-guard.js') == 1, 'подключён ровно один раз')
check(os.path.exists(JS_PATH), 'файл web/static/api-guard.js существует')
js = open(JS_PATH, encoding='utf-8').read()
check('__apiGuardInstalled' in js, 'защита от двойной установки (флаг)')
check('guardSilent' in js and 'X-Guard-Silent' in js, 'opt-out: опция и заголовок')
check('DEDUP_MS' in js, 'анти-спам одинаковых тостов')
check('showToast' in js, 'использует общий showToast панели')
check('.clone()' in js, 'тело ответа читается через clone — вызывающий код не тронут')

print('== 2. Функциональный прогон (Node vm) ==')
NODE_SCENARIO = r'''
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync(process.argv[2], 'utf8');
let out = [];
const note = (ok, msg) => out.push((ok ? 'GUARD_PASS' : 'GUARD_FAIL') + ' ' + msg);

function makeEnv(fetchImpl) {
  const toasts = [];
  const sandbox = {
    console: { warn() {}, log() {}, error() {} },
    URL, Date, JSON, String, Number, Object, Array, RegExp, Math, Promise, Error,
    setTimeout, setImmediate,
  };
  sandbox.window = sandbox;
  sandbox.location = { origin: 'http://panel.test' };
  sandbox.showToast = (m, ok) => toasts.push({ m, ok });
  sandbox.fetch = fetchImpl;
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  return { sandbox, toasts };
}

const flush = () => new Promise(r => setTimeout(r, 20));

(async () => {
  // 1) 2xx — молчим
  let env = makeEnv(() => Promise.resolve({ ok: true, status: 200 }));
  env.sandbox.showToast ? null : null;
  env.sandbox.fetch2 = null;
  const okFetch = env.sandbox.hasOwnProperty('fetch');
  await env.sandbox.window.fetch('/api/ping');
  await flush();
  note(okFetch && env.toasts.length === 0, '200 OK -> тоста нет');

  // 2) 400 с JSON-ошибкой — тост с причиной, методом и путём
  env = makeEnv(() => Promise.resolve({
    ok: false, status: 400,
    clone() { return { json: () => Promise.resolve({ error: 'Пустое сообщение' }) }; },
  }));
  const resp = await env.sandbox.window.fetch('http://panel.test/api/send-message', { method: 'POST' });
  await flush();
  note(resp.ok === false, 'ответ возвращён вызывающему без изменений');
  note(env.toasts.length === 1, `ровно один тост (${env.toasts.length})`);
  const t = (env.toasts[0] && env.toasts[0].m) || '';
  note(t.includes('POST') && t.includes('/api/send-message') && t.includes('400') && t.includes('Пустое сообщение'),
       'тост: метод, путь, статус и причина сервера -> ' + t);
  note(env.toasts[0] && env.toasts[0].ok === false, 'тост красный (error-стиль)');

  // 3) анти-спам: тот же 400 сразу повторно — второго тоста нет
  await env.sandbox.window.fetch('/api/send-message', { method: 'POST' });
  await flush();
  note(env.toasts.length === 1, 'дедуп: повторный тост придушен');

  // 4) opt-out guardSilent — молчим
  await env.sandbox.window.fetch('/api/other', { method: 'POST', guardSilent: true });
  await flush();
  note(env.toasts.length === 1, 'guardSilent отключает тост');

  // 5) не-JSON тело 500 — тост без причины
  env = makeEnv(() => Promise.resolve({
    ok: false, status: 500,
    clone() { return { json: () => Promise.reject(new Error('html')) }; },
  }));
  await env.sandbox.window.fetch('/api/boom');
  await flush();
  note(env.toasts.length === 1 && /HTTP 500/.test(env.toasts[0].m), '500 без JSON-тела -> HTTP статус в тосте');

  // 6) сетевая ошибка: rejection долетает до вызывающего + тост
  env = makeEnv(() => Promise.reject(new Error('boom')));
  let caught = false;
  try { await env.sandbox.window.fetch('/api/down'); } catch (e) { caught = true; }
  await flush();
  note(caught, 'сетевая ошибка пробрасывается вызывающему коду');
  note(env.toasts.length === 1 && env.toasts[0].m.includes('сеть недоступна'), 'и при этом показан тост про сеть');

  // 7) двойная установка не плодит обёртки
  env = makeEnv(() => Promise.resolve({ ok: true, status: 200 }));
  vm.runInContext(code, env.sandbox);
  note(env.sandbox.window.__apiGuardInstalled === true, 'повторная установка идемпотентна');

  console.log(out.join('\n'));
  process.exit(out.some(l => l.startsWith('GUARD_FAIL')) ? 1 : 0);
})().catch(e => { console.error('HARNESS_ERROR', e); process.exit(2); });
'''

node_bin = shutil.which('node')
if not node_bin:
    print('  SKIP: node не найден — функциональный прогон пропущен (статика покрыла контракт)')
else:
    scenario = os.path.join(_TMP, 'guard_scenario.js')
    open(scenario, 'w', encoding='utf-8').write(NODE_SCENARIO)
    proc = subprocess.run([node_bin, scenario, JS_PATH], capture_output=True, text=True, timeout=60)
    lines = [l for l in proc.stdout.splitlines() if l.startswith('GUARD_')]
    node_pass = sum(1 for l in lines if l.startswith('GUARD_PASS'))
    node_fail = [l for l in lines if l.startswith('GUARD_FAIL')]
    for l in lines:
        print('  ' + l.replace('GUARD_FAIL', 'FAIL').replace('GUARD_PASS', 'PASS'))
    check(proc.returncode == 0 and not node_fail,
          f'node-прогон: {node_pass} сценариев зелёные' + (f'; упало: {node_fail}' if node_fail else ''))
    check(node_pass >= 11, f'покрыто сценариев API Guard: {node_pass} (>= 11)')
    check('HARNESS_ERROR' not in proc.stderr, 'харнесс node не падал')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
