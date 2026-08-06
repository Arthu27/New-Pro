"""
Custom Commands — исполнитель своих команд из панели.

Страница панели (/custom-commands) сохраняет команды в
data/custom_cmds_{gid}.json: {id: {trigger, response, type, uses, created_at}}

Теперь бот действительно отвечает: сообщение «!триггер» → ответ команды.
type: text — обычный текст | embed — золотое embed-окно.
Счётчик использований (uses) обновляется и виден в панели.
"""
import os
import json
import discord
from discord.ext import commands
from datetime import datetime, timezone

from logger import get_logger

log = get_logger("custom_commands")

GOLD = 0xD4AF37
PREFIX = '!'


def _path(gid): return f'data/custom_cmds_{gid}.json'


class CustomCommands(commands.Cog):
    """Выполняет пользовательские команды, созданные в панели."""

    def __init__(self, bot):
        self.bot = bot
        self._cache = {}   # gid -> (mtime, {trigger: rec_with_id})

    def _commands(self, guild_id: int) -> dict:
        p = _path(guild_id)
        try:
            mtime = os.path.getmtime(p)
        except Exception:
            self._cache.pop(guild_id, None)
            return {}
        cached = self._cache.get(guild_id)
        if cached and cached[0] == mtime:
            return cached[1]
        out = {}
        try:
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for cid, rec in (data.items() if isinstance(data, dict) else []):
                trig = str(rec.get('trigger', '') or '').strip().lstrip('!').casefold()
                if trig:
                    out[trig] = {**rec, 'id': cid, 'trigger': trig}
        except Exception:
            pass
        self._cache[guild_id] = (mtime, out)
        return out

    def _bump_uses(self, guild_id: int, cid: str):
        try:
            p = _path(guild_id)
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if cid in data:
                data[cid]['uses'] = int(data[cid].get('uses', 0) or 0) + 1
                tmp = p + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, p)
                self._cache.pop(guild_id, None)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        content = (message.content or '').strip()
        if not content.startswith(PREFIX) or len(content) < 2:
            return
        name = content[len(PREFIX):].split()[0].casefold() if content[len(PREFIX):].strip() else ''
        if not name:
            return
        rec = self._commands(message.guild.id).get(name)
        if not rec:
            return

        response = str(rec.get('response', '') or '')[:1900]
        if not response:
            return
        try:
            if str(rec.get('type', 'text')) == 'embed':
                e = discord.Embed(description=response, color=GOLD,
                                  timestamp=datetime.now(timezone.utc))
                e.set_footer(text=f"{message.guild.name} · !{rec['trigger']}")
                await message.channel.send(embed=e)
            else:
                await message.channel.send(response)
            self._bump_uses(message.guild.id, str(rec['id']))
            log.info(f"[CCMD] {message.guild.name}: !{rec['trigger']} → {message.author}")
        except Exception as e:
            log.warning(f"[CCMD] отправка !{rec['trigger']}: {e}")


async def setup(bot):
    await bot.add_cog(CustomCommands(bot))
    log.info("[CCMD] Ког загружен")
