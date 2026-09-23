#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Живой smoke-тест мафии против Discord API.

Требует в окружении / .env:
  TOKEN=...              токен бота (Hakumo или отдельный MAFIA_BOT_TOKEN)
  MAIN_GUILD_ID=...      сервер для гильдового синка /mafia

Что проверяет:
  1) логин бота
  2) загрузка cogs.mafia
  3) guild-sync группы /mafia (start/status/panel/…)
  4) что команды видны через HTTP fetch

Запуск:
  python3 scripts/mafia_live_smoke.py
"""
from __future__ import annotations

import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# подтянуть .env если есть
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, '.env'))
except Exception:
    pass

TOKEN = (os.environ.get('MAFIA_BOT_TOKEN') or os.environ.get('TOKEN') or '').strip()
GUILD = (os.environ.get('MAIN_GUILD_ID') or '').strip()


async def main() -> int:
    if not TOKEN:
        print('SKIP: нет TOKEN / MAFIA_BOT_TOKEN — живой Discord-smoke невозможен')
        return 0
    if not GUILD:
        print('SKIP: нет MAIN_GUILD_ID')
        return 0

    import discord
    from discord.ext import commands

    intents = discord.Intents.default()
    intents.members = True
    intents.guilds = True
    intents.voice_states = True
    bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

    @bot.event
    async def on_ready():
        print(f'OK login as {bot.user} ({bot.user.id})')
        try:
            await bot.load_extension('cogs.mafia')
            print('OK cogs.mafia loaded')
        except Exception as e:
            print(f'FAIL load mafia: {e}')
            await bot.close()
            return

        gobj = discord.Object(id=int(GUILD))
        # гильдовый синк только группы mafia — не трогаем боевое меню целиком
        try:
            # команды кога уже в tree; синхронизируем guild scope
            synced = await bot.tree.sync(guild=gobj)
            names = sorted({c.name for c in synced})
            print(f'OK guild sync → {len(synced)} cmds, names sample: {names[:20]}')
            if 'mafia' not in names and not any(getattr(c, 'name', '') == 'mafia' for c in synced):
                # группы приходят как одно имя
                print(f'WARN: mafia group may be nested; full names: {names}')
            else:
                print('OK /mafia в гильдовом меню')
        except Exception as e:
            print(f'FAIL sync: {e}')

        # fetch back
        try:
            remote = await bot.http.get_guild_commands(bot.user.id, int(GUILD))
            rnames = sorted({c.get('name') for c in remote})
            print(f'OK fetch guild commands: {rnames}')
            print('PASS' if 'mafia' in rnames else 'FAIL: mafia missing remotely')
        except Exception as e:
            print(f'FAIL fetch: {e}')

        await bot.close()

    try:
        await bot.start(TOKEN)
    except Exception as e:
        print(f'FAIL start: {e}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
