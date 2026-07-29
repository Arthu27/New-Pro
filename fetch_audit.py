"""Журнал аудита Discord'u ручная загрузка и кэш'e записать"""
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
бот = discord.Client(intents=intents)

ACTION_MAP = {
    discord.AuditЛогAction.ban:              ('mod',     'Бан'),
    discord.AuditЛогAction.unban:            ('mod',     'Бан Снят'),
    discord.AuditЛогAction.kick:             ('mod',     'Кик'),
    discord.AuditЛогAction.member_update:    ('mod',     'Участник Обновитьndi'),
    discord.AuditЛогAction.channel_create:   ('channel', 'Канал Создатьuldu'),
    discord.AuditЛогAction.channel_delete:   ('channel', 'Канал Удалено'),
    discord.AuditЛогAction.role_create:      ('role',    'Role Создатьuldu'),
    discord.AuditЛогAction.role_delete:      ('role',    'Role Удалено'),
    discord.AuditЛогAction.member_role_update: ('role',  'Role Değişikliği'),
    discord.AuditЛогAction.message_delete:   ('message', 'Сообщение Удалено'),
    discord.AuditЛогAction.invite_create:    ('invite',  'Davet Создатьuldu'),
    discord.AuditЛогAction.invite_delete:    ('invite',  'Davet Удалено'),
    discord.AuditЛогAction.guild_update:     ('server',  'Сервер Обновитьndi'),
}

@бот.event
async def on_ready():
    print(f'Подключено: {bot.user}')
    cache = {}
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=7)

    for guild in bot.guilds:
        print(f'  {guild.name} загрузитьiliyor...')
        gid = str(guild.id)
        cache[gid] = []
        count = 0
        try:
            async for entry in guild.audit_logs(limit=None, oldest_first=False):
                if entry.created_at.replace(tzinfo=None) < cutoff:
                    break
                cat, action_name = ACTION_MAP.get(entry.action, ('server', str(entry.action).split('.')[-1]))
                target = entry.target
                user = entry.user

                # Мут tespiti
                if entry.action == discord.AuditЛогAction.member_update:
                    after = entry.changes.after
                    if hasattr(after, 'timed_out_until'):
                        action_name = 'Мут' if getattr(after, 'timed_out_until', None) else 'Мут Снят'
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
            print(f'  HATA: {e}')

        print(f'  {guild.name}: {count} записей загружено')

    os.makedirs('data', exist_ok=True)
    with open('data/discord_audit_cache.json', 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    total = sum(len(v) for v in cache.values())
    print(f'\nВсего {total} записей cache\'e записано.')
    await bot.close()

бот.run(TOKEN)
