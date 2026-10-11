# -*- coding: utf-8 -*-
"""Демон Broadcaster-бота. Токен: BROADCASTER_BOT_TOKEN в .env, не в коде."""
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
        key, _, value = line.partition('=')
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

import discord  # noqa: E402
from discord.ext import commands  # noqa: E402

from logger import get_logger  # noqa: E402
from services.broadcaster_cog import BroadcasterCog  # noqa: E402
from services.broadcaster_config import load_cfg  # noqa: E402

log = get_logger('broadcaster.run')


def token() -> str:
    return (os.environ.get('BROADCASTER_BOT_TOKEN') or '').strip()


def token_hint(raw: str) -> str:
    if not raw:
        return ''
    return ('••••' + raw[-4:]) if len(raw) >= 4 else '••••'


def build_bot() -> commands.Bot:
    intents = discord.Intents.none()
    intents.guilds = True
    intents.voice_states = True
    cfg = load_cfg()
    gid = int(cfg.get('guild_id') or 0)
    guilds = [discord.Object(id=gid)] if gid else []

    class BroadcasterBot(commands.Bot):
        def __init__(self):
            super().__init__(
                command_prefix=commands.when_mentioned,
                intents=intents,
                help_command=None,
            )
            self._slash_synced = False

        async def setup_hook(self):
            # До on_ready, иначе циклы открытия и лав-рума не стартуют.
            if guilds:
                await self.add_cog(BroadcasterCog(self), guilds=guilds)
            else:
                await self.add_cog(BroadcasterCog(self))

        async def on_ready(self):
            if not self._slash_synced:
                self._slash_synced = True
                try:
                    if guilds:
                        for guild in guilds:
                            synced = await self.tree.sync(guild=guild)
                            log.info(
                                'slash sync guild=%s → %s',
                                gid, [c.name for c in (synced or [])],
                            )
                    else:
                        synced = await self.tree.sync()
                        log.info(
                            'slash sync global → %s',
                            [c.name for c in (synced or [])],
                        )
                except Exception as ex:
                    self._slash_synced = False
                    log.warning('slash sync: %s', ex)
                    log.warning(
                        'Если бота нет на сервере, пригласи: '
                        'https://discord.com/api/oauth2/authorize?client_id=%s'
                        '&permissions=8&scope=bot%%20applications.commands',
                        getattr(self.user, 'id', ''),
                    )
            log.info(
                'broadcaster online as %s token=%s guilds=%s',
                self.user, token_hint(token()), [g.id for g in self.guilds],
            )
            try:
                await self.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.watching,
                        name='трибуны',
                    )
                )
            except Exception:
                pass

    return BroadcasterBot()


async def main() -> int:
    raw = token()
    if not raw:
        print('FATAL: BROADCASTER_BOT_TOKEN empty', flush=True)
        return 2
    stop = asyncio.Event()

    def _sig(*_a):
        print('signal — broadcaster shutdown', flush=True)
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _sig)
        except NotImplementedError:
            pass

    while not stop.is_set():
        bot = build_bot()
        task = asyncio.create_task(bot.start(raw))
        wait_stop = asyncio.create_task(stop.wait())
        done, _pending = await asyncio.wait(
            {task, wait_stop}, return_when=asyncio.FIRST_COMPLETED,
        )
        if wait_stop in done:
            await bot.close()
            break
        exc = task.exception() if task.done() else None
        log.warning('broadcaster client stopped: %s', exc)
        if stop.is_set():
            break
        await asyncio.sleep(3)
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
