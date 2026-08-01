"""Botun proslie DM разговор загрузить ve dm_log.json'a сохранить"""
import asyncio
import json
import os
from dotenv import load_dotenv
import discord

load_dotenv()
TOKEN = os.getenv('TOKEN')

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'Bağlandı: {client.user}')
    dm_log = {}
    
    # Текущий dm_log varsa загрузить (üzerine add)
    if os.path.exists('data/dm_log.json'):
        try:
            with open('data/dm_log.json', encoding='utf-8') as f:
                dm_log = json.load(f)
        except: pass

    # ai_chat_histories.json'dan bilinen user ID'lerini al
    known_users = set()
    hist_file = 'data/ai_chat_histories.json'
    if os.path.exists(hist_file):
        try:
            with open(hist_file, encoding='utf-8') as f:
                hists = json.load(f)
            for uid in hists.keys():
                if uid.isdigit():
                    known_users.add(int(uid))
        except: pass

    # Текущий dm_log'daki userları da add
    for uid in dm_log.keys():
        if uid.isdigit():
            known_users.add(int(uid))

    print(f'Всего {len(known_users)} user scannacak...')

    for uid in known_users:
        try:
            user = await client.fetch_user(uid)
            channel = await user.create_dm()
            msgs = []
            async for msg in channel.history(limit=None, oldest_first=True):
                msgs.append({
                    'author': msg.author.display_name,
                    'content': msg.content or '[Ek/Embed]',
                    'timestamp': msg.created_at.isoformat(),
                    'from_bot': msg.author.bot,
                })
            if msgs:
                dm_log[str(uid)] = msgs
                print(f' {user.display_name}: {len(msgs)} message')
        except Exception as e:
            print(f' {uid} ошибка: {e}')
        await asyncio.sleep(0.5)  # rate limit

    os.makedirs('data', exist_ok=True)
    with open('data/dm_log.json', 'w', encoding='utf-8') as f:
        json.dump(dm_log, f, ensure_ascii=False, indent=2)
    
    total = sum(len(v) for v in dm_log.values())
    print(f'\nToplam {len(dm_log)} user, {total} message сохранено.')
    await client.close()

client.run(TOKEN)
