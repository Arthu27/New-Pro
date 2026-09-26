# -*- coding: utf-8 -*-
"""Живые обновления панели: шина services/live_bus.py + SSE-эндпоинт /api/live.

Проверяем:
  • publish/publish_global доходят до подписчиков по маскам;
  • дедуп одинаковых топиков в очереди (не штормим браузер);
  • unsubscribe снимает подписку;
  • потокобезопасность (издатели из разных потоков);
  • SSE отдаёт поток text/event-stream и реагирует на пуш.

Запуск: python3 tests/test_live_bus.py
"""
import os
import sys
import threading
import time
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_live_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('DB_PATH', os.path.join(_TMP, 'data', 'bot.db'))
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ.setdefault('MAIN_GUILD_ID', '777')
os.environ.setdefault('DEMO_MODE', '1')
os.makedirs(os.path.join(_TMP, 'data'), exist_ok=True)

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


from services import live_bus  # noqa: E402

print('== 1. Базовая подписка и доставка по маскам ==')
q, unsub = live_bus.subscribe(['g777:channels', 'g*:guardian'])
live_bus.publish(777, 'channels')
live_bus.publish(777, 'guardian')
live_bus.publish(888, 'channels')    # точная маска g777:channels НЕ ловит 888
live_bus.publish(888, 'guardian')    # широкая маска g*:guardian ловит это
got = set()
deadline = time.time() + 2
while time.time() < deadline:
    try:
        got.add(q.get(timeout=0.3))
    except Exception:
        break
check(got == {'g777:channels', 'g777:guardian', 'g888:guardian'},
      f'маски отфильтровали правильно: {sorted(got)}')
unsub()

# Узкая подписка: чужой сервер не приходит
q1b, unsub1b = live_bus.subscribe(['g777:channels'])
live_bus.publish(888, 'channels')
live_bus.publish(777, 'channels')
try:
    first = q1b.get(timeout=1)
except Exception:
    first = None
rest = False
try:
    q1b.get(timeout=0.3)
    rest = True
except Exception:
    rest = False
unsub1b()
check(first == 'g777:channels' and not rest,
      'узкая маска g777:channels пропускает только свой сервер')

print('== 2. Дедуп одинаковых топиков ==')
q2, unsub2 = live_bus.subscribe(['*'])
for _ in range(50):
    live_bus.publish(777, 'analytics')   # один и тот же топик много раз
n = 0
deadline = time.time() + 1
while time.time() < deadline:
    try:
        q2.get(timeout=0.2)
        n += 1
    except Exception:
        break
check(n == 1, f'одинаковый топик в очереди один раз (получено {n})')
unsub2()

print('== 3. Глобальный топик ==')
q3, unsub3 = live_bus.subscribe(['dashboard', 'g*:*'])
live_bus.publish_global('dashboard')
live_bus.publish(999, 'roles')
got3 = set()
deadline = time.time() + 2
while time.time() < deadline:
    try:
        got3.add(q3.get(timeout=0.3))
    except Exception:
        break
check('dashboard' in got3 and 'g999:roles' in got3,
      f'глобальный и гильдийный сигналы дошли: {sorted(got3)}')
unsub3()

print('== 4. Публикация из нескольких потоков не теряет события ==')
q4, unsub4 = live_bus.subscribe(['g*:members'])
errors = []


def worker(n):
    try:
        for i in range(100):
            live_bus.publish(777, f'members')  # один топик → дедуп до 1
    except Exception as ex:  # noqa: BLE001
        errors.append(ex)


threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
[t.start() for t in threads]
[t.join() for t in threads]
check(not errors, f'публикация из 8 потоков без исключений ({len(errors)})')
val = None
try:
    val = q4.get(timeout=1)
except Exception:
    pass
check(val == 'g777:members', f'событие дошло после нагрузки: {val}')
unsub4()

print('== 5. SSE-эндпоинт отдаёт поток и реагирует на пуш ==')
try:
    from web.app import app
    c = app.test_client()
    with c.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'tester'
        s['role'] = 'owner'
        s['user_id'] = '1'
    # Открываем поток, читаем первые байты и пихаем событие в шину.
    ev = c.get('/api/live?topics=*', buffered=False)
    head = next(ev.response)  # первое событие (retry/hello)
    ok_head = b'retry' in head or b'hello' in head
    check(ok_head and ev.status_code == 200 and 'text/event-stream' in ev.content_type,
          f'SSE открыт: status={ev.status_code}, type={ev.content_type}')
    live_bus.publish(777, 'channels')
    body = b''
    try:
        for _ in range(5):
            chunk = next(ev.response)
            body += chunk
            if b'tick' in body and b'channels' in body:
                break
    except StopIteration:
        pass
    check(b'event: tick' in body and b'g777:channels' in body,
          'SSE доставил tick с топиком после publish')
    ev.close()
except Exception as ex:  # noqa: BLE001
    check(False, f'SSE-эндпоинт: {ex}')

print()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
