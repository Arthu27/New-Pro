"""Ежедневный audita Discord'u rucnaya загруз ve önbellek'e yaz"""
import asyncio
import json
import os
import datetime
from dotenv import load_dotenv

load_dotenv()

import discord
from discord.ext import commands

TOKEN = os.getenv('TOKEN')

intents = discord.Intents.default()
intents.members = True
bot = discord.Client(intents=intents)

ACTION_MAP = {
    discord.AuditLogAction.ban:              ('mod',     'Ban'),
    discord.AuditLogAction.unban:            ('mod',     'Ban Удалено'),
    discord.AuditLogAction.kick:             ('mod',     'Kick'),
    discord.AuditLogAction.member_update:    ('mod',     'Участник Обновлено'),
    discord.AuditLogAction.channel_create:   ('channel', 'Канал Создано'),
    discord.AuditLogAction.channel_delete:   ('channel', 'Канал Удалено'),
    discord.AuditLogAction.role_create:      ('role',    'Роли Создано'),
    discord.AuditLogAction.role_delete:      ('role',    'Роли Удалено'),
    discord.AuditLogAction.member_role_update: ('role',  'Роли Изменение'),
    discord.AuditLogAction.message_delete:   ('message', 'Сообщение Удалено'),
    discord.AuditLogAction.invite_create:    ('invite',  'Davet Создано'),
    discord.AuditLogAction.invite_delete:    ('invite',  'Davet Удалено'),
    discord.AuditLogAction.guild_update:     ('сервер',  'Сервер Обновлено'),
}

@bot.event
async def on_ready():
    print(f'Bağlandı: {bot.user}')
    cache = {}
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=7)

    for guild in bot.guilds:
        print(f' {guild.name} загруз...')
        gid = str(guild.id)
        cache[gid] = []
        count = 0
        try:
            async for entry in guild.audit_logs(limit=None, oldest_first=False):
                if entry.created_at.replace(tzinfo=None) < cutoff:
                    break
                cat, action_name = ACTION_MAP.get(entry.action, ('сервер', str(entry.action).split('.')[-1]))
                target = entry.target
                user = entry.user

                # Mute tespiti
                if entry.action == discord.AuditLogAction.member_update:
                    after = entry.changes.after
                    if hasattr(after, 'timed_out_until'):
                        action_name = 'Mute' if getattr(after, 'timed_out_until', None) else 'Mute Удалено'
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
                    'mod_name':    mname,
                    'mod_id':      str(getattr(user, 'id', '?')) if user else '?',
                    'reason':      entry.reason or '',
                    'timestamp':   entry.created_at.isoformat(),
                    'audit_id':    str(entry.id),
                    'source':      'discord_audit',
                })
                count += 1
        except Exception as e:
            print(f' ОШИБКА: {e}')

        print(f' {guild.name}: {count} запись загружено')

    os.makedirs('data', exist_ok=True)
    with open('data/discord_audit_cache.json', 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    total = sum(len(v) for v in cache.values())
    print(f'\nToplam {total} запись cache\'e написано.')
    await bot.close()

bot.run(TOKEN)
