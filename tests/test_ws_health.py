# -*- coding: utf-8 -*-
"""Живой тест WebSocket-сервера панели (реальный сокет, не мок).

Поднимает сервер на эфемерном порту в отдельном потоке и проверяет:
1. Handshake: клиент шлёт {"room_id", "user_id"} → сервер отвечает
   {"type": "connected"} с теми же полями.
2. Ping → pong.
3. Мусорный JSON не рвёт соединение: после него ping снова отвечает.
4. Подключение без room_id закрывается сервером с кодом 1008 (policy violation).
5. Broadcast: два клиента в одной комнате — сообщение typing одного
   доходит до второго.

Запуск: python3 tests/test_ws_health.py
"""
import asyncio
import json
import sys
import time

ROOT = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0
SKIP = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


try:
    import websockets
    from web.websocket_server import start_websocket_thread, ws_server
except ImportError as e:
    print(f'SKIP: нет зависимостей для WS-теста ({e})')
    sys.exit(0)

PORT = 9765


def _close_code(exc):
    rcvd = getattr(exc, 'rcvd', None)
    if rcvd is not None and hasattr(rcvd, 'code'):
        return rcvd.code
    return getattr(exc, 'code', None)


async def _recv(ws, timeout=8.0):
    return json.loads(await asyncio.wait_for(ws.recv(), timeout))


async def _run_checks():
    uri = f'ws://127.0.0.1:{ws_server.port}'

    # 1-2. handshake + ping/pong
    async with websockets.connect(uri) as a:
        await a.send(json.dumps({'room_id': 'dashboard', 'user_id': 'tester-a'}))
        hello = await _recv(a)
        check(hello.get('type') == 'connected'
              and hello.get('room_id') == 'dashboard'
              and hello.get('user_id') == 'tester-a',
              f'handshake: connected с верными room_id/user_id ({hello.get("type")})')

        await a.send(json.dumps({'type': 'ping'}))
        pong = await _recv(a)
        check(pong.get('type') == 'pong', f'ping → {pong.get("type")}')

        # 3. мусорный JSON не рвёт соединение
        await a.send('this is not json')
        await asyncio.sleep(0.2)
        await a.send(json.dumps({'type': 'ping'}))
        pong2 = await _recv(a)
        check(pong2.get('type') == 'pong', 'после мусорного JSON ping снова → pong')

        # 5. broadcast: второй клиент в той же комнате получает typing
        async with websockets.connect(uri) as b:
            await b.send(json.dumps({'room_id': 'dashboard', 'user_id': 'tester-b'}))
            hello_b = await _recv(b)
            check(hello_b.get('type') == 'connected', f'клиент B подключился ({hello_b.get("type")})')

            await a.send(json.dumps({'type': 'typing', 'user_id': 'tester-a', 'is_typing': True}))
            got_b = await _recv(b)
            check(got_b.get('type') == 'typing' and got_b.get('user_id') == 'tester-a',
                  f'B получил broadcast typing от A ({got_b.get("type")})')

    # 4. без room_id — сервер закрывает с кодом 1008
    try:
        async with websockets.connect(uri) as c:
            await c.send(json.dumps({'user_id': 'ghost'}))
            await _recv(c)
            check(False, 'без room_id сервер должен закрыть соединение')
    except websockets.exceptions.ConnectionClosed as e:
        code = _close_code(e)
        check(code == 1008, f'без room_id закрыто с кодом {code} (ожидалось 1008)')
    except Exception as e:  # noqa: BLE001
        check(False, f'неожиданная ошибка в сценарии 1008: {type(e).__name__}: {e}')


print('== WebSocket: запуск сервера на эфемерном порту ==')
thread = start_websocket_thread('127.0.0.1', PORT)
deadline = time.time() + 10
while time.time() < deadline and not getattr(ws_server, 'port', None):
    time.sleep(0.1)
check(bool(getattr(ws_server, 'port', None)), f'сервер поднялся на порту {getattr(ws_server, "port", None)}')

if getattr(ws_server, 'port', None):
    asyncio.run(_run_checks())
else:
    print('  SKIP: сервер не поднялся — остальные проверки пропущены')
    SKIP += 1

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===' + (' (skipped)' if SKIP else ''))
sys.exit(1 if FAIL else 0)
