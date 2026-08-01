"""
Giveaway Cog
Система розыгрышей — тёмная тема, без эмодзи, русский язык
"""

MENU_GIF = "https://media.tenor.com/x8v1oNUOmg4AAAAC/rain-dark.gif"

import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import json
import os
from datetime import datetime, timedelta
import asyncio
import random
from typing import Dict

from logger import get_logger
log = get_logger("giveaway")


def _save_giveaways(guild_id: int, data: dict):
    os.makedirs("data", exist_ok=True)
    with open(f'data/giveaways_{guild_id}.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_giveaways(guild_id: int) -> dict:
    path = f'data/giveaways_{guild_id}.json'
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


# ═══════════════════════════════════════════════════════════════════
# Embed'ы
# ═══════════════════════════════════════════════════════════════════

def _giveaway_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        color=discord.Color.dark_grey(),
        timestamp=datetime.now()
    )


def _win_dm_embed(prize: str, guild_name: str, guild_icon_url: str) -> discord.Embed:
    e = discord.Embed(
        title="Поздравляем!",
        description=(
            f"Вы выиграли в розыгрыше!\n\n"
            f"**Сервер:** {guild_name}\n"
            f"**Приз:** {prize}\n\n"
            f"Свяжитесь с администрацией для получения приза."
        ),
        color=discord.Color.dark_grey(),
        timestamp=datetime.now()
    )
    if guild_icon_url:
        e.set_footer(text=f"{guild_name} | Розыгрыши", icon_url=guild_icon_url)
    return e


def _ended_embed(prize: str, winners: list, guild) -> discord.Embed:
    if not winners:
        return _giveaway_embed(
            "Розыгрыш завершён",
            "Недостаточно участников для определения победителя."
        )

    winners_text = "\n".join([f"**{w}**" for w in winners])
    return _giveaway_embed(
        "Розыгрыш завершён",
        f"**Приз:** {prize}\n\n**Победители:**\n{winners_text}\n\nПоздравляем! Свяжитесь с администрацией."
    )


# ═══════════════════════════════════════════════════════════════════
# View — кнопка участия
# ═══════════════════════════════════════════════════════════════════

class GiveawayView(View):
    def __init__(self, gw_id: str, guild_id: str):
        super().__init__(timeout=None)
        self.gw_id = gw_id
        self.guild_id = guild_id

    @discord.ui.button(label="Участвовать", style=discord.ButtonStyle.secondary, custom_id="gw_join_v2")
    async def join(self, interaction: discord.Interaction, button: Button):
        if interaction.user.bot:
            return

        data = _load_giveaways(interaction.guild.id)

        if self.gw_id not in data:
            await interaction.response.send_message("Розыгрыш не найден.", ephemeral=True)
            return

        gw = data[self.gw_id]
        if gw.get("status") != "active":
            await interaction.response.send_message("Розыгрыш уже завершён.", ephemeral=True)
            return

        participants = gw.setdefault("participants", [])
        user_id = str(interaction.user.id)

        if user_id in participants:
            await interaction.response.send_message("Вы уже участвуете.", ephemeral=True)
            return

        participants.append(user_id)
        gw.setdefault("user_info", {})[user_id] = {
            "name": interaction.user.display_name,
            "avatar": str(interaction.user.display_avatar.url)
        }
        _save_giveaways(interaction.guild.id, data)

        count = len(participants)
        await interaction.response.send_message(f"Вы участвуете! ({count} участников)", ephemeral=True)

        # Обновляем embed
        try:
            embed = interaction.message.embeds[0]
            embed.set_field_at(0, name="Участников", value=str(count), inline=True)
            await interaction.message.edit(embed=embed)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════
# Cog
# ═══════════════════════════════════════════════════════════════════

class GiveawayCog(commands.Cog):
    """Система розыгрышей"""

    def __init__(self, bot):
        self.bot = bot
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    @tasks.loop(minutes=1)
    async def check_giveaways(self):
        """Проверяет завершённые розыгрыши"""
        await self.bot.wait_until_ready()

        for guild in self.bot.guilds:
            data = _load_giveaways(guild.id)
            changed = False

            for gw_id, gw in data.items():
                if gw.get("status") != "active":
                    continue

                ends_at = datetime.fromisoformat(gw["ends_at"])
                if datetime.now() < ends_at:
                    continue

                # Розыгрыш завершён
                gw["status"] = "ended"
                changed = True

                channel = guild.get_channel(int(gw.get("channel_id", 0)))
                if not channel:
                    continue

                participants = gw.get("participants", [])
                winners_count = gw.get("winners", 1)
                prize = gw.get("prize", "Не указан")

                if not participants:
                    await channel.send(embed=_giveaway_embed(
                        "Розыгрыш завершён",
                        "Недостаточно участников."
                    ))
                    continue

                winner_ids = random.sample(participants, min(winners_count, len(participants)))
                winner_mentions = []
                icon_url = guild.icon.url if guild.icon else None

                for uid in winner_ids:
                    try:
                        user = await guild.fetch_member(int(uid))
                        if user:
                            winner_mentions.append(user.mention)
                            try:
                                await user.send(embed=_win_dm_embed(prize, guild.name, icon_url))
                            except discord.Forbidden:
                                pass
                    except (discord.NotFound, ValueError):
                        pass

                await channel.send(embed=_ended_embed(prize, winner_mentions, guild))

            if changed:
                _save_giveaways(guild.id, data)

    # ── Команды ──────────────────────────────────────────────────────

    @commands.command(name="giveaway", aliases=["гивка", "розыгрыш"])
    @commands.has_permissions(administrator=True)
    async def create_giveaway(self, ctx, duration: str, winners: int, *, prize: str):
        """Создать розыгрыш. Пример: !giveaway 1h 1 Nitro"""
        # Парсинг длительности
        unit = duration[-1].lower()
        try:
            value = int(duration[:-1])
        except ValueError:
            await ctx.send(embed=_giveaway_embed("Ошибка", "Формат: `!giveaway 1h 1 Приз` (1h, 30m, 2d)"))
            return

        if unit == "m":
            delta = timedelta(minutes=value)
        elif unit == "h":
            delta = timedelta(hours=value)
        elif unit == "d":
            delta = timedelta(days=value)
        else:
            await ctx.send(embed=_giveaway_embed("Ошибка", "Используйте: m (минуты), h (часы), d (дни)"))
            return

        if winners < 1:
            winners = 1

        ends_at = datetime.now() + delta
        gw_id = f"gw_{int(ends_at.timestamp())}"

        # Сохраняем
        data = _load_giveaways(ctx.guild.id)
        data[gw_id] = {
            "prize": prize,
            "winners": winners,
            "ends_at": ends_at.isoformat(),
            "channel_id": str(ctx.channel.id),
            "status": "active",
            "participants": [],
            "user_info": {},
            "created_by": str(ctx.author.id),
        }

        # Embed
        embed = discord.Embed(
            title="Розыгрыш",
            description=(
                f"**Приз:** {prize}\n"
                f"**Победителей:** {winners}\n"
                f"**Завершение:** {discord.utils.format_dt(ends_at, 'R')}\n\n"
                f"Нажмите кнопку ниже для участия."
            ),
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Участников", value="0", inline=True)
        embed.set_footer(text=f"ID: {gw_id}")

        view = GiveawayView(gw_id, str(ctx.guild.id))
        msg = await ctx.send(embed=embed, view=view)

        data[gw_id]["message_id"] = str(msg.id)
        _save_giveaways(ctx.guild.id, data)

        try:
            await ctx.message.delete()
        except Exception:
            pass

        log.info(f"Розыгрыш создан: {gw_id} — {prize}")

    @commands.command(name="rerolel", aliases=["reroll"])
    @commands.has_permissions(administrator=True)
    async def reroll(self, ctx, gw_id: str):
        """Перевыбрать победителя"""
        data = _load_giveaways(ctx.guild.id)

        if gw_id not in data:
            await ctx.send(embed=_giveaway_embed("Ошибка", "Розыгрыш не найден."))
            return

        gw = data[gw_id]
        participants = gw.get("participants", [])

        if not participants:
            await ctx.send(embed=_giveaway_embed("Ошибка", "Нет участников."))
            return

        winners = random.sample(participants, min(gw.get("winners", 1), len(participants)))
        winner_mentions = []
        for uid in winners:
            try:
                user = await ctx.guild.fetch_member(int(uid))
                if user:
                    winner_mentions.append(user.mention)
            except (discord.NotFound, ValueError):
                pass

        await ctx.send(embed=_ended_embed(gw.get("prize", ""), winner_mentions, ctx.guild))

    @commands.Cog.listener()
    async def on_ready(self):
        # Регистрируем persistent view для всех активных розыгрышей
        for guild in self.bot.guilds:
            data = _load_giveaways(guild.id)
            for gw_id, gw in data.items():
                if gw.get("status") == "active":
                    self.bot.add_view(GiveawayView(gw_id, str(guild.id)))


async def setup(bot):
    await bot.add_cog(GiveawayCog(bot))
    log.info("GiveawayCog загружен")
