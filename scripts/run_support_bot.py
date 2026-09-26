# -*- coding: utf-8 -*-
"""Support Discord bot — /verify V2 (отдельный процесс).

Токен ТОЛЬКО из env SUPPORT_BOT_TOKEN (никогда не коммитить).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from logger import get_logger, setup_logger

setup_logger()
log = get_logger('support_bot')


def _mask(token: str) -> str:
    t = (token or '').strip()
    if len(t) < 8:
        return '••••'
    return '••••' + t[-4:]


async def amain():
    token = (os.environ.get('SUPPORT_BOT_TOKEN') or '').strip()
    if not token:
        log.error('SUPPORT_BOT_TOKEN не задан — выход')
        return 2

    import discord
    from discord.ext import commands
    from services import support_bot_config as CFG
    from services import support_emojis as EMO
    from cogs import support_verify as SV

    cfg = CFG.load_config()
    intents = discord.Intents.default()
    intents.guilds = True
    # Server Members Intent — только если включён в Dev Portal.
    # Иначе PrivilegedIntentsRequired. Резолв ника → query_members / fetch.
    intents.members = (os.environ.get('SUPPORT_MEMBERS_INTENT') or '0').strip() in (
        '1', 'true', 'yes', 'on')
    intents.message_content = False

    bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)
    boot = {'done': False}

    async def _setup_guild(g: discord.Guild):
        try:
            await SV.ensure_infra(g)
        except Exception as ex:
            log.warning('infra guild=%s: %s', g.id, ex)
        try:
            bot.tree.copy_global_to(guild=discord.Object(id=g.id))
            synced = await bot.tree.sync(guild=discord.Object(id=g.id))
            log.info('slash synced guild=%s n=%s', g.id, len(synced))
        except Exception as ex:
            log.warning('slash sync guild=%s: %s', g.id, ex)

    @bot.event
    async def on_ready():
        log.info('support online as %s | guilds=%s | token=%s',
                 bot.user, len(bot.guilds), _mask(token))
        if boot['done']:
            return
        boot['done'] = True
        try:
            await EMO.ensure_support_emojis(bot)
        except Exception as ex:
            log.warning('emojis: %s', ex)
        gid = CFG.gid(cfg)
        g = bot.get_guild(gid)
        if g is None and bot.guilds:
            g = bot.guilds[0]
            log.warning('guild %s not found — using %s', gid, g.id)
        if g is not None:
            await _setup_guild(g)
        else:
            log.warning(
                'бот ещё не в гильдии %s — ждём invite; синхронизирую /verify глобально',
                gid)
            try:
                synced = await bot.tree.sync()
                log.info('slash synced global n=%s', len(synced))
            except Exception as ex:
                log.warning('slash global sync: %s', ex)
        try:
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching, name='verify · support'))
        except Exception:
            pass

    @bot.event
    async def on_guild_join(guild: discord.Guild):
        log.info('joined guild %s (%s)', guild.name, guild.id)
        await _setup_guild(guild)

    await bot.add_cog(SV.SupportVerify(bot))
    log.info('starting support bot…')
    await bot.start(token)


def main():
    try:
        raise SystemExit(asyncio.run(amain()) or 0)
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    raise SystemExit(main() or 0)
