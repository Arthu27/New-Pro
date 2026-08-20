# -*- coding: utf-8 -*-
"""Регрессия условных GET-запросов панели (ETag / HTTP 304).

304 — успешный ответ «не изменилось», но у него нет JSON-тела. Хелпер обязан
вернуть данные из памяти, а после потери памяти (например, при перезагрузке
страницы и сохранённом валидаторе прокси) — один раз запросить полный ответ.

Запуск: python3 tests/test_etag_cache.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_etag_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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


app_js_path = os.path.join(ROOT, 'web', 'static', 'app.js')
app_js = open(app_js_path, encoding='utf-8').read()
start = app_js.find('// ETag-кэш для частых GET-опросов')
end = app_js.find('// ============================================================\n// GLOBAL LIVE REFRESH', start)
helper = app_js[start:end] if start >= 0 and end > start else ''

base_path = os.path.join(ROOT, 'web', 'templates', 'base.html')
base = open(base_path, encoding='utf-8').read()

print('== 1. Контракт хелпера в app.js ==')
check(bool(helper), 'блок ETag-кэша найден')
check('response.status === 304' in helper, '304 обрабатывается отдельно от HTTP-ошибок')
check('_etagCache.has(url)' in helper, 'наличие кэша проверяется без путаницы с undefined')
check("fresh.cache = 'no-store'" in helper, 'при потере JSON выполняется свежий запрос')
check("fresh.headers.delete('If-None-Match')" in helper, 'повторный запрос уходит без старого ETag')
check('/static/api-guard.js?v=3' in base, 'браузер получает новую версию API Guard')
check('/static/app.js' in base, 'кит с ETag-хелпером подключён в base.html')

print('== 2. Функциональный прогон ETag-кэша (Node vm) ==')
NODE_SCENARIO = r'''
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync(process.argv[2], 'utf8');
const out = [];
const note = (ok, msg) => out.push((ok ? 'CACHE_PASS' : 'CACHE_FAIL') + ' ' + msg);

class HeadersMock {
  constructor(init) {
    this.values = Object.create(null);
    if (!init) return;
    if (init instanceof HeadersMock) {
      Object.keys(init.values).forEach(k => { this.values[k] = init.values[k]; });
    } else if (typeof init.forEach === 'function') {
      init.forEach((v, k) => this.set(k, v));
    } else {
      Object.keys(init).forEach(k => this.set(k, init[k]));
    }
  }
  set(key, value) { this.values[String(key).toLowerCase()] = String(value); }
  get(key) {
    const value = this.values[String(key).toLowerCase()];
    return value === undefined ? null : value;
  }
  delete(key) { delete this.values[String(key).toLowerCase()]; }
}

function response(status, etag, data, counter) {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get(name) { return String(name).toLowerCase() === 'etag' ? etag : null; } },
    json() {
      if (counter) counter.count++;
      return Promise.resolve(data);
    },
  };
}

function makeEnv(sequence) {
  const calls = [];
  const sandbox = {
    console: { log() {}, warn() {}, error() {} },
    Object, String, Error, Promise,
    Headers: HeadersMock,
    fetch(url, init) {
      calls.push({ url, init });
      const next = sequence.shift();
      if (!next) return Promise.reject(new Error('unexpected fetch'));
      return Promise.resolve(next);
    },
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  return { sandbox, calls };
}

(async () => {
  // Обычный цикл: 200 сохраняет JSON и ETag, следующий 304 возвращает JSON из памяти.
  const parsed = { count: 0 };
  const logs = [{ action: 'Ban' }];
  let env = makeEnv([
    response(200, '"logs-v1"', logs, parsed),
    response(304, '"logs-v1"', null, parsed),
  ]);
  const first = await env.sandbox.fetchCachedJSON('/api/logs');
  const second = await env.sandbox.fetchCachedJSON('/api/logs');
  note(first === logs && second === logs, '200 -> 304 возвращает тот же сохранённый JSON');
  note(parsed.count === 1, 'пустое тело 304 не пытаются разбирать как JSON');
  note(env.calls.length === 2, 'штатный цикл выполняет ровно два HTTP-запроса');
  note(env.calls[1].init.headers.get('If-None-Match') === '"logs-v1"',
       'повторный GET отправляет If-None-Match');

  // Потерянный JS-кэш: первый 304 не должен привести к Unexpected end of JSON.
  const freshLogs = [{ action: 'Kick' }];
  env = makeEnv([
    response(304, '"stale"', null, parsed),
    response(200, '"logs-v2"', freshLogs, parsed),
  ]);
  const recovered = await env.sandbox.fetchCachedJSON('/api/logs');
  note(recovered === freshLogs, '304 без JSON-кэша восстанавливается полным ответом 200');
  note(env.calls.length === 2, 'при потере кэша выполняется только один повтор');
  note(env.calls[1].init.cache === 'no-store', 'восстановительный GET обходит HTTP-кэш');
  note(env.calls[1].init.headers.get('If-None-Match') === null,
       'восстановительный GET не содержит If-None-Match');

  // Настоящая ошибка по-прежнему отклоняет Promise.
  env = makeEnv([response(500, null, { error: 'boom' }, parsed)]);
  let rejected = false;
  try { await env.sandbox.fetchCachedJSON('/api/logs'); } catch (e) { rejected = /HTTP 500/.test(e.message); }
  note(rejected, 'HTTP 500 не маскируется ETag-кэшем');

  console.log(out.join('\n'));
  process.exit(out.some(line => line.startsWith('CACHE_FAIL')) ? 1 : 0);
})().catch(err => { console.error('HARNESS_ERROR', err); process.exit(2); });
'''

node_bin = shutil.which('node')
if not node_bin:
    print('  SKIP: node не найден — функциональный прогон пропущен')
else:
    helper_path = os.path.join(_TMP, 'etag-helper.js')
    scenario_path = os.path.join(_TMP, 'etag-scenario.js')
    open(helper_path, 'w', encoding='utf-8').write(helper)
    open(scenario_path, 'w', encoding='utf-8').write(NODE_SCENARIO)
    proc = subprocess.run(
        [node_bin, scenario_path, helper_path],
        capture_output=True, text=True, timeout=60,
    )
    lines = [line for line in proc.stdout.splitlines() if line.startswith('CACHE_')]
    node_pass = sum(1 for line in lines if line.startswith('CACHE_PASS'))
    node_fail = [line for line in lines if line.startswith('CACHE_FAIL')]
    for line in lines:
        print('  ' + line.replace('CACHE_PASS', 'PASS').replace('CACHE_FAIL', 'FAIL'))
    check(proc.returncode == 0 and not node_fail,
          f'node-прогон: {node_pass} сценариев зелёные' + (f'; упало: {node_fail}' if node_fail else ''))
    check(node_pass >= 9, f'покрыто сценариев ETag-кэша: {node_pass} (>= 9)')
    check('HARNESS_ERROR' not in proc.stderr,
          'харнесс Node не падал' + (f' ({proc.stderr.strip()})' if proc.stderr.strip() else ''))

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
