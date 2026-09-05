# -*- coding: utf-8 -*-
"""Лимиты стаффа: варн 1/день и чистка 10/день у всех + переживают рестарт.

Заказ владельца (2026-09-05):
  • «удаление сообщений у всех 10 штук в день»;
  • «варн 1 в день у всех»;
  • «убедись, что даже после того, как я перезапущу бота, лимиты не
    сбрасывались никаким образом».

Как устроена защита от сброса: счётчики — МЕТКИ ВРЕМЕНИ в файле
data/staff_limits_<gid>.json; каждая проверка читает файл с диска заново
(никакой памяти «с Работы началось»), запись — атомарная. Рестарт процесса
ничего не обнуляет: в новом процессе тот же файл, те же метки. В окне 24 ч
метки старше суток перестают считаться — это ЕСТЕСТВЕННОЕ окно, а не сброс.

Проверяем: новый процесс (настоящий «перезапуск») видит расходку прошлого
процесса и отказывает в превышении; конфиг лимитов тоже живёт на диске.
Запуск: python3 tests/test_limits_persist.py
"""
import json
import os
import subprocess
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix='lim_persist_')
os.chdir(WORK)
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

PASS = FAIL = 0
GID = 777002
MOD_ROLE, CUR_ROLE, ADM_ROLE, OWN_ROLE = '111', '222', '333', '444'
UID = 5100  # куратор


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


class _R:
    def __init__(self, rid):
        self.id = rid


class _M:
    def __init__(self, mid, *rids):
        self.id = mid
        self.roles = [_R(r) for r in rids]
        self.guild_permissions = types.SimpleNamespace(
            manage_messages=False, administrator=False)


class _G:
    id = GID
    owner_id = 999999


# карта ролей персонала (та же настройка, что «Панели и роли»)
with open('data/role_map.json', 'w') as f:
    json.dump({MOD_ROLE: 'mod', CUR_ROLE: 'curator',
               ADM_ROLE: 'admin', OWN_ROLE: 'owner'}, f)

from services import staff_limits as SL  # noqa: E402

print('== 1. Лимиты по тирам (Sabotash 2026-09-02) ==')
for rid, label, want in ((MOD_ROLE, 'Модер', 3), (CUR_ROLE, 'Куратор', 5),
                         (ADM_ROLE, 'Админ', 5)):
    lim, _win = SL.effective_limits(GID, [rid])
    check(lim['warn'] == want and lim['clear'] == 10,
          f'{label}: варн {want}/день, чистка 10/день',
          f'→ warn={lim["warn"]} clear={lim["clear"]}')
lim, _ = SL.effective_limits(GID, [OWN_ROLE])
check(all(lim[k] == 0 for k in ('warn', 'mute', 'unmute', 'ban',
                                'unban', 'clear')),
      'тир владельца: ВСЁ без лимитов, включая варны и чистку '
      '(владелец 2026-09-05: «у владельца без лимит надо сделать все»)',
      f'→ {lim}')

print('== 2. Наберём расходку: 5 варнов + 10 чисток (куратор) ==')
ok, _ = SL.check_action(_G(), _M(UID, CUR_ROLE), 'warn')
assert ok
for _i in range(5):
    SL.record_hit(GID, UID, 'warn', 1)
ok, deny = SL.check_action(_G(), _M(UID, CUR_ROLE), 'warn')
check(not ok and 'Лимит исчерпан' in deny,
      'шестой варн куратора в тот же день уже запрещён', f'→ {deny}')
for i in range(10):
    SL.record_hit(GID, UID, 'clear', 1)
ok, deny = SL.check_action(_G(), _M(UID, CUR_ROLE), 'clear', 1)
check(not ok and '10' in deny,
      '11-я чистка (сверх 10 операций) запрещена', f'→ {deny[:60]}')

cnt_file = SL._cnt_path(GID)
check(os.path.exists(cnt_file),
      f'счётчики на диске: {os.path.basename(cnt_file)}')
before = open(cnt_file, encoding='utf-8').read()
check(json.loads(before).get(str(UID), {}).get('warn'),
      'метка варна реально записана в файл')

# ── «РЕСТАРТ БОТА»: новый процесс с чистым импортом ────────────────────────
print('== 3. Перезапуск бота (новый процесс) — лимиты НЕ сбросились ==')
child = r'''
import sys, types
sys.path.insert(0, %r)
from services import staff_limits as SL

class _R:
    def __init__(self, rid): self.id = rid
class _M:
    def __init__(self, mid, *rids):
        self.id = mid
        self.roles = [_R(r) for r in rids]
        self.guild_permissions = types.SimpleNamespace(
            manage_messages=False, administrator=False)
class _G:
    id = %d
    owner_id = 999999

import json
out = {}
# варн: метки прошлого процесса живы — 6-й варн куратора запрещён
ok, deny = SL.check_action(_G(), _M(%d, %r), 'warn')
out['warn_denied'] = (not ok)
out['warn_txt'] = (deny or '')
# чистка: 10 потрачено — 11-я запрещена
ok, deny = SL.check_action(_G(), _M(%d, %r), 'clear', 1)
out['clear_denied'] = (not ok)
out['clear_used'] = SL._hits(%d, %d, 'clear') and len(
    [t for t in SL._hits(%d, %d, 'clear')[0]
     if SL._now() - t < SL.DEFAULT_WINDOW])
# конфиг лимитов тоже с диска
lim, _ = SL.effective_limits(%d, [%r])
out['warn_limit'] = lim['warn']
out['clear_limit'] = lim['clear']
print(json.dumps(out))
''' % (ROOT, GID, UID, CUR_ROLE, UID, CUR_ROLE,
       GID, UID, GID, UID, GID, CUR_ROLE)
res = subprocess.run([sys.executable, '-c', child], capture_output=True,
                     text=True, timeout=60)
check(res.returncode == 0, 'перезапущенный процесс поднялся',
      res.stderr[-200:] if res.returncode else '')
try:
    out = json.loads(res.stdout.strip().splitlines()[-1])
except Exception as _ex:
    out = {}
    check(False, f'ответ перезапущенного процесса прочитан: {_ex}')

check(out.get('warn_denied') is True,
      'после рестарта 6-й варн куратора по-прежнему запрещён (метки живы)',
      f'→ {out}')
check(out.get('clear_denied') is True,
      'после рестарта чистка сверх 10 по-прежнему запрещена')
check(out.get('clear_used') == 10,
      f'в новом процессе видно все 10 потраченных чисток',
      f'→ {out.get("clear_used")}')
check(out.get('warn_limit') == 5 and out.get('clear_limit') == 10,
      'лимиты warn=5/clear=10 (куратор) в новом процессе те же (конфиг с диска)')

after = open(cnt_file, encoding='utf-8').read()
check(json.loads(after) == json.loads(before),
      'файл счётчиков перезапуском не менялся и не очищался')

# ── статика: в коде нет путей, стирающих счётчики ──────────────────────────
print('== 4. В коде нет сбросов ==')
sl_src = open(os.path.join(ROOT, 'services', 'staff_limits.py'),
              encoding='utf-8').read()
check('os.remove' not in sl_src and 'unlink' not in sl_src,
      'staff_limits.py ничего не удаляет')
cu_src = open(os.path.join(ROOT, 'scripts', 'cleanup_servers.py'),
              encoding='utf-8').read()
check('staff_limits' not in cu_src,
      'cleanup_servers не трогает файлы лимитов')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
