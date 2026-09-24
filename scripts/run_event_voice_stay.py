# -*- coding: utf-8 -*-
"""Демон Event-бота: сидит в войсе 24/7 и не закрывается сам.

Запуск: python3 scripts/run_event_voice_stay.py
Токен/канал из .env (EVENT_BOT_TOKEN, EVENT_VOICE_CHANNEL_ID).
"""
from __future__ import annotations

import asyncio
import os
import signal
import sys
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
os.environ.setdefault('EVENT_VOICE_STAY_ENABLED', '1')

from services import event_voice_bot as EV  # noqa: E402


async def main() -> int:
    tok = EV.event_bot_token()
    if not tok:
        print('FATAL: EVENT_BOT_TOKEN empty', flush=True)
        return 2
    cid = EV._resolve_event_voice_channel_id()
    print(f'event-voice-stay start channel={cid} hint=••••{tok[-4:]}',
          flush=True)
    client = await EV.start_event_bot()
    if client is None:
        print('FATAL: start_event_bot returned None', flush=True)
        return 3
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

    # ждём forever; монитор внутри клиента сам держит войс
    while not stop.is_set():
        await asyncio.sleep(30)
        st = EV.event_bot_status()
        print(
            f'stay online={st.get("online")} voice={st.get("voice_connected")} '
            f'ch={st.get("voice_channel_id")} name={st.get("name")}',
            flush=True)
    try:
        c = EV.get_event_client()
        if c is not None and not c.is_closed():
            await c.close()
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
