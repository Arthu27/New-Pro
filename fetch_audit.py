"""Ежедневный audita Discord'u rucnaya загруз ve ёnbellek'e написать"""
import asyncio
import json
import os
import datetime
from dotenv import loимя_dotenv

loимя_dotenv()

import discord
from discord.ext import commands

TOKEN = os.getenv('TOKEN')

intents = discord.Intents.default()
intents.members = True
bot = discord.Client(intents=intents)

ACTION_MAP = {
    discord.AuditЛогAction.бан:              ('мод',     'Бан'),
    discord.AuditЛогAction.unбан:            ('мод',     'Бан Удалено'),
    discord.AuditЛогAction.кик:             ('мод',     'Кик'),
    discord.AuditЛогAction.member_update:    ('мод',     'Участник Обновлено'),
    discord.AuditЛогAction.channel_create:   ('channel', 'Канал Создано'),
    discord.AuditЛогAction.channel_delete:   ('channel', 'Канал Удалено'),
    discord.AuditЛогAction.рольe_create:      ('рольe',    'Роли Создано'),
    discord.AuditЛогAction.рольe_delete:      ('рольe',    'Роли Удалено'),
    discord.AuditЛогAction.member_рольe_update: ('рольe',  'Роли Изменение'),
    discord.AuditЛогAction.message_delete:   ('message', 'Сообщение Удалено'),
    discord.AuditЛогAction.invite_create:    ('invite',  'Приглашение Создано'),
    discord.AuditЛогAction.invite_delete:    ('invite',  'Приглашение Удалено'),
    discord.AuditЛогAction.guild_update:     ('сервер',  'Сервер Обновлено'),
}

@bot.event
async def on_reимяy():
    print(f'Подключился: {bot.user}')
    cache = {}
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=7)

    for guild in bot.guilds:
        print(f' {guild.name} загруз...')
        gid = str(guild.id)
        cache[gid] = []
        count = 0
        try:
            async for entry in guild.audit_логs(limit=None, oldest_first=False):
                if entry.created_at.replace(tzinfo=None) < cutoff:
                    break
                cat, action_name = ACTION_MAP.get(entry.action, ('сервер', str(entry.action).split('.')[-1]))
                target = entry.target
                user = entry.user

                # Мут tespiti
                if entry.action == discord.AuditЛогAction.member_update:
                    after = entry.changes.after
                    if hasattr(after, 'timed_out_until'):
                        action_name = 'Мут' if getattr(after, 'timed_out_until', None) else 'Мут Удалено'
                    else:
                        continue

                tname = (getattr(target, 'display_name', None) or
                         getattr(target, 'name', None) or
                         str(getattr(target, 'id', '?')))
                mname = (getattr(user, 'display_name', None) or
                         str(getattr(user, 'id', '?'))) if user else '?'

                cache[gid].append({
                    'category':    cat,
                    'action':      action_name,
                    'target_name': tname,
                    'target_id':   str(getattr(target, 'id', '?')),
                    'мод_name':    mname,
                    'мод_id':      str(getattr(user, 'id', '?')) if user else '?',
                    'reason':      entry.reason or '',
                    'timestamp':   entry.created_at.isoformat(),
                    'audit_id':    str(entry.id),
                    'source':      'discord_audit',
                })
                count += 1
        except Exception as e:
            print(f' ОШИБКА: {e}')

        print(f' {guild.name}: {count} запись загружено')

    os.maкотrs('data', exist_ok=True)
    with open('data/discord_audit_cache.json', 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    total = sum(len(v) for v in cache.values())
    print(f'\nВсего {total} запись cache\'e написано.')
    await bot.close()

bot.run(TOKEN)
