# -*- coding: utf-8 -*-
"""Демон Event-бота: сидит в войсе 24/7 без ограничений.

Запуск: python3 scripts/run_event_voice_stay.py
Токен/канал из .env (EVENT_BOT_TOKEN, EVENT_VOICE_CHANNEL_ID).

Если процесс/клиент упал — сам поднимается снова. Stay выключить нельзя.
Если voice=False несколько циклов подряд — hard-restart клиента
(после gateway drop connect мог зависнуть).
"""
from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

envp = ROOT / '.env'
if envp.is_file():
    for line in envp.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v

os.environ.setdefault('EVENT_VOICE_CHANNEL_ID', '1550986919981351043')
# Stay всегда on — игнор выключателя
os.environ['EVENT_VOICE_STAY_ENABLED'] = '1'

from services import event_voice_bot as EV  # noqa: E402

# Сколько подряд heartbeat'ов с voice=False → hard restart клиента
_MISS_LIMIT = 2  # 2 × 10с ≈ 20с без войса → перезапуск сессии


async def _hard_restart_client(reason: str) -> None:
    """Закрыть клиент — внешний loop поднимет заново."""
    print(f'HARD RESTART ({reason})', flush=True)
    EV._stop_runner = True
    try:
        c = EV.get_event_client()
        if c is not None and not c.is_closed():
            await c.close()
    except Exception as ex:
        print(f'hard restart close: {ex}', flush=True)
    EV._event_client = None
    EV._commands_synced = False
    EV._joining = False
    EV._suppress_rejoin_until = 0.0
    EV._rejoin_task = None
    EV._monitor_task = None


async def _run_once(stop: asyncio.Event) -> int:
    tok = EV.event_bot_token()
    if not tok:
        print('FATAL: EVENT_BOT_TOKEN empty', flush=True)
        return 2
    cid = EV._resolve_event_voice_channel_id()
    print(f'event-voice-stay start channel={cid} hint=••••{tok[-4:]}',
          flush=True)
    EV._stop_runner = False
    client = await EV.start_event_bot()
    if client is None:
        print('FATAL: start_event_bot returned None', flush=True)
        return 3

    miss = 0
    while not stop.is_set():
        await asyncio.sleep(10)
        st = EV.event_bot_status()
        print(
            f'stay online={st.get("online")} voice={st.get("voice_connected")} '
            f'ch={st.get("voice_channel_id")} name={st.get("name")}',
            flush=True)

        c = EV.get_event_client()
        if c is None or c.is_closed():
            print('client closed — restarting stay loop', flush=True)
            break

        if st.get('online') and st.get('voice_connected'):
            miss = 0
            # soft reconnect по таймеру
            try:
                from services.voice_stay_health import needs_soft_reconnect
                if needs_soft_reconnect(
                        getattr(EV, '_last_join_ts', 0) or 0, time.time()):
                    print('heartbeat soft-reconnect', flush=True)
                    EV._schedule_rejoin(c, 'soft-reconnect', force=True)
            except Exception as ex:
                print(f'heartbeat soft: {ex}', flush=True)
            continue

        if st.get('online') and not st.get('voice_connected'):
            miss += 1
            print(f'voice miss #{miss}/{_MISS_LIMIT}', flush=True)
            try:
                EV._schedule_rejoin(c, 'daemon-heartbeat', force=True)
            except Exception as ex:
                print(f'heartbeat rejoin: {ex}', flush=True)
            if miss >= _MISS_LIMIT:
                await _hard_restart_client(f'voice miss ×{miss}')
                break
        else:
            # offline — тоже считаем
            miss += 1
            if miss >= _MISS_LIMIT:
                await _hard_restart_client(f'offline ×{miss}')
                break
    return 0


async def main() -> int:
    stop = asyncio.Event()

    def _sig(*_a):
        print('signal — shutting down event-voice-stay', flush=True)
        EV._stop_runner = True
        stop.set()

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, _sig)
        except NotImplementedError:
            pass

    while not stop.is_set():
        try:
            await _run_once(stop)
        except Exception as ex:
            print(f'stay loop error: {ex}', flush=True)
        if stop.is_set():
            break
        print('stay restart in 2s…', flush=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass
        EV._stop_runner = False
        EV._event_client = None
        EV._commands_synced = False
        EV._joining = False
        EV._suppress_rejoin_until = 0.0

    try:
        c = EV.get_event_client()
        if c is not None and not c.is_closed():
            await c.close()
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
