"""DM Logger — надёжно записывает ВСЕ входящие личные сообщения (DM) в data/dm_log.json.

Веб-панель (страница «Чат» → Личные сообщения) читает этот файл, чтобы показать
историю DM и позволить ответить. Этот ког ловит каждое входящее DM независимо от
других когов, поэтому разговор никогда не теряется.
"""
import discord
from discord.ext import commands

import os
import json
import logging
from datetime import datetime

log = logging.getLogger('dm_logger')

DM_LOG_FILE = 'data/dm_log.json'
DM_WHITELIST_FILE = 'data/dm_whitelist.json'
MAX_PER_USER = 200


def _load_dm_log():
    try:
        if os.path.exists(DM_LOG_FILE):
            with open(DM_LOG_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}


def _load_dm_whitelist():
    """Разрешённые пользователи, которым можно писать боту в ЛС.
    Формат: список объектов {'id': '...', 'note': '...'} или список строк-ID."""
    try:
        if os.path.exists(DM_WHITELIST_FILE):
            with open(DM_WHITELIST_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
            ids = []
            for item in d if isinstance(d, list) else []:
                if isinstance(item, dict):
                    ids.append(str(item.get('id', '')))
                elif isinstance(item, (str, int)):
                    ids.append(str(item))
            return set(x for x in ids if x)
    except Exception:
        pass
    return set()


def _save_dm_log(data):
    try:
        os.makedirs('data', exist_ok=True)
        with open(DM_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.info(f'[DM] save error: {e}')


class DMLogger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.whitelist = _load_dm_whitelist()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Только личные сообщения, и только от людей (не от ботов)
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return
        # Пустые (только вложения) тоже полезно сохранить
        try:
            content = message.content or ''
            if not content and message.attachments:
                content = '[Вложение: ' + (message.attachments[0].url or 'файл') + ']'
            data = _load_dm_log()
            uid = str(message.author.id)
            if uid not in data or not isinstance(data[uid], list):
                data[uid] = []
            # Для разрешённых (whitelist) пользователей записываем ВСЕ сообщения всегда.
            is_whitelisted = uid in self.whitelist
            # Защита от дублей: не записываем, если это та же запись (по времени/содержимому)
            # — НЕ применяем к whitelist, чтобы их сообщения не терялись.
            if not is_whitelisted:
                prev = data[uid][-1] if data[uid] else None
                if prev and prev.get('from_bot') is False and prev.get('content') == content:
                    try:
                        t_prev = datetime.fromisoformat(prev.get('timestamp', ''))
                        t_new = message.created_at.replace(tzinfo=t_prev.tzinfo)
                        if abs((t_new - t_prev).total_seconds()) < 2:
                            return
                    except Exception:
                        pass
            data[uid].append({
                'author': message.author.display_name,
                'content': content,
                'timestamp': message.created_at.isoformat(),
                'from_bot': False,
            })
            data[uid] = data[uid][-MAX_PER_USER:]
            _save_dm_log(data)
        except Exception as e:
            log.info(f'[DM] log error: {e}')


async def setup(bot):
    await bot.add_cog(DMLogger(bot))
    log.info('[DM] DMLogger loaded')
