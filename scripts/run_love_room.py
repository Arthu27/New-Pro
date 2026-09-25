# -*- coding: utf-8 -*-
"""Демон Love Room бота (отдельный процесс).

Запуск: python3 scripts/run_love_room.py
Токен из .env (LOVE_ROOM_BOT_TOKEN). При category/panel ID=0 — idle OK.
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

from services import love_room_bot as LR  # noqa: E402
from services.love_room_store import load_love_room_cfg, cfg_int  # noqa: E402


async def _run_once(stop: asyncio.Event) -> int:
    tok = LR.love_bot_token()
    if not tok:
        print('FATAL: LOVE_ROOM_BOT_TOKEN empty', flush=True)
        return 2
    cfg = load_love_room_cfg()
    print(
        f'love-room start guild={cfg_int(cfg, "guild_id")} '
        f'cat={cfg_int(cfg, "category_id")} panel={cfg_int(cfg, "panel_channel_id")} '
        f'hint={LR.token_hint(tok)}',
        flush=True)
    LR._stop_runner = False
    client = await LR.start_love_room_bot()
    if client is None:
        print('FATAL: start_love_room_bot returned None', flush=True)
        return 3

    while not stop.is_set():
        await asyncio.sleep(20)
        st = LR.love_bot_status()
        print(
            f'love online={st.get("online")} name={st.get("name")} '
            f'cmds={st.get("commands")} sits_voice={st.get("sits_in_voice")}',
            flush=True)
        c = LR.get_love_client()
        if c is None or c.is_closed():
            print('client closed — restarting love loop', flush=True)
            break
    return 0


async def main() -> int:
    stop = asyncio.Event()

    def _sig(*_a):
        print('signal — shutting down love-room', flush=True)
        LR._stop_runner = True
        stop.set()

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, _sig)
        except NotImplementedError:
            pass

    while not stop.is_set():
        try:
            code = await _run_once(stop)
            if code == 2:
                # empty token — wait and retry (env may be filled later)
                print('waiting for LOVE_ROOM_BOT_TOKEN…', flush=True)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    pass
                continue
            if code == 3 and not stop.is_set():
                pass
        except Exception as ex:
            print(f'love loop error: {ex}', flush=True)
        if stop.is_set():
            break
        print('love restart in 3s…', flush=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            pass
        LR._stop_runner = False
        LR._love_client = None
        LR._commands_synced = False

    try:
        c = LR.get_love_client()
        if c is not None and not c.is_closed():
            await c.close()
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
