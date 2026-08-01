"""
Централизованная обработка ошибок
Перехватывает все ошибки команд и interaction'ов
"""
import discord
from discord.ext import commands
from discord import app_commands
import traceback
import sys
from datetime import datetime

from logger import get_logger

log = get_logger("errors")


class ErrorHandler:
    """Централизованный обработчик ошибок для бота"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.error_counts = {}  # Для отслеживания частоты ошибок
    
    def setup(self):
        """Зарегистрировать обработчики"""
        # Обработчик ошибок команд (prefix commands)
        @self.bot.event
        async def on_command_error(ctx: commands.Context, error: commands.CommandError):
            await self.handle_command_error(ctx, error)
        
        # Обработчик ошибок application commands (slash)
        tree = self.bot.tree
        _original_on_error = tree.on_error
        
        async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            await self.handle_app_command_error(interaction, error)
        
        tree.on_error = on_app_command_error
        
        log.info("Централизованный обработчик ошибок активирован")
    
    async def handle_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Обработка ошибок prefix-команд"""
        # Игнорируем, если у cog'a есть свой обработчик
        if ctx.cog and ctx.cog.has_error_handler():
            return
        
        error = getattr(error, 'original', error)
        
        # === Права доступа ===
        if isinstance(error, commands.MissingPermissions):
            missing = ", ".join(error.missing_permissions)
            embed = self._error_embed(
                "Недостаточно прав",
                f"Отсутствуют права: `{missing}`"
            )
            await ctx.send(embed=embed, delete_after=15)
            return
        
        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            embed = self._error_embed(
                "У бота нет прав",
                f"Боту не хватает прав: `{missing}`"
            )
            await ctx.send(embed=embed, delete_after=15)
            return
        
        # === Команда не найдена ===
        if isinstance(error, commands.CommandNotFound):
            # Просто игнорируем — не спамить
            return
        
        # === Неверные аргументы ===
        if isinstance(error, commands.MissingRequiredArgument):
            embed = self._error_embed(
                "Не указан аргумент",
                f"Пропущен обязательный параметр: `{error.param.name}`\n\nИспользуйте `!help {ctx.command.name}` для справки"
            )
            await ctx.send(embed=embed, delete_after=20)
            return
        
        if isinstance(error, commands.BadArgument):
            embed = self._error_embed(
                "Неверный аргумент",
                f"Не удалось разобрать аргумент: {error}"
            )
            await ctx.send(embed=embed, delete_after=15)
            return
        
        # === Кулдаун ===
        if isinstance(error, commands.CommandOnCooldown):
            embed = self._error_embed(
                "Команда на перезарядке",
                f"Попробуйте через {error.retry_after:.1f} сек."
            )
            await ctx.send(embed=embed, delete_after=10)
            return
        
        # === Проверки не пройдены ===
        if isinstance(error, commands.CheckFailure):
            embed = self._error_embed(
                "Проверка не пройдена",
                "У вас нет доступа к этой команде"
            )
            await ctx.send(embed=embed, delete_after=15)
            return
        
        # === Неизвестная ошибка ===
        self._log_error(f"Command error in {ctx.command}: {error}", error)
        
        embed = self._error_embed(
            "Произошла ошибка",
            "Непредвиденная ошибка при выполнении команды. Администрация уже уведомлена."
        )
        try:
            await ctx.send(embed=embed, delete_after=20)
        except Exception:
            pass
    
    async def handle_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Обработка ошибок slash-команд"""
        error = getattr(error, 'original', error)
        
        # === Права доступа ===
        if isinstance(error, app_commands.MissingPermissions):
            missing = ", ".join(error.missing_permissions)
            embed = self._error_embed(
                "Недостаточно прав",
                f"Отсутствуют права: `{missing}`"
            )
            await self._respond(interaction, embed=embed)
            return
        
        if isinstance(error, app_commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            embed = self._error_embed(
                "У бота нет прав",
                f"Боту не хватает прав: `{missing}`"
            )
            await self._respond(interaction, embed=embed)
            return
        
        # === Кулдаун ===
        if isinstance(error, app_commands.CommandOnCooldown):
            embed = self._error_embed(
                "Команда на перезарядке",
                f"Попробуйте через {error.retry_after:.1f} сек."
            )
            await self._respond(interaction, embed=embed)
            return
        
        # === Проверки ===
        if isinstance(error, app_commands.CheckFailure):
            embed = self._error_embed(
                "Проверка не пройдена",
                "У вас нет доступа к этой команде"
            )
            await self._respond(interaction, embed=embed)
            return
        
        # === Неизвестная ошибка ===
        cmd_name = interaction.command.name if interaction.command else "unknown"
        self._log_error(f"App command error in {cmd_name}: {error}", error)
        
        embed = self._error_embed(
            "Произошла ошибка",
            "Непредвиденная ошибка при выполнении команды. Администрация уже уведомлена."
        )
        await self._respond(interaction, embed=embed)
    
    def _log_error(self, message: str, error: Exception):
        """Залогировать ошибку с трассировкой"""
        log.error(message)
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        log.error(f"Traceback:\n{tb}")
        
        # Подсчёт ошибок для мониторинга
        error_type = type(error).__name__
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
    
    def _error_embed(self, title: str, description: str) -> discord.Embed:
        """Создать embed с ошибкой (тёмная тема, без эмодзи)"""
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        return embed
    
    async def _respond(self, interaction: discord.Interaction, embed: discord.Embed):
        """Безопасный ответ на interaction"""
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            pass
    
    def get_error_stats(self) -> dict:
        """Получить статистику ошибок"""
        return dict(self.error_counts)


async def setup(bot: commands.Bot):
    """Зарегистрировать обработчик ошибок"""
    handler = ErrorHandler(bot)
    handler.setup()
    bot.error_handler = handler  # Сохраняем для доступа из других модулей
