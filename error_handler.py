"""
Централизованная обработка ошибок + анти-краш защита
Перехватывает все ошибки команд, interaction'ов, событий,
фоновых задач (asyncio) и потоков — бот не должен падать молча.
"""
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import traceback
import sys
import threading
from datetime import datetime

from logger import get_logger

log = get_logger("errors")


class ErrorHandler:
    """Централизованный обработчик ошибок для бота (anti-crash)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.error_counts = {}  # Для отслеживания частоты ошибок
        self._loop = None

    def setup(self):
        """Зарегистрировать обработчики"""
        # Обработчик ошибок команд (prefix commands)
        @self.bot.event
        async def on_command_error(ctx: commands.Context, error: commands.CommandError):
            await self.handle_command_error(ctx, error)

        # Обработчик ошибок событий (on_message, on_member_join и т.д.)
        # Без него необработанное исключение в ивенте просто пишется в консоль
        @self.bot.event
        async def on_error(event: str, *args, **kwargs):
            exc = sys.exc_info()[1]
            if exc is None:
                return
            self._log_error(f"Event error in '{event}': {exc}", exc)

        # Обработчик ошибок application commands (slash)
        tree = self.bot.tree

        async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            await self.handle_app_command_error(interaction, error)

        tree.on_error = on_app_command_error

        self._setup_anticrash()

        log.info("Централизованный обработчик ошибок + anti-crash активирован")

    def _setup_anticrash(self):
        """Перехват падений фоновых задач, потоков и главного потока"""
        # 1) asyncio: исключения в create_task()/колбэках — "Task exception was never retrieved"
        try:
            self._loop = asyncio.get_running_loop()
            self._loop.set_exception_handler(self._loop_exception_handler)
        except RuntimeError:
            pass

        # 2) Главный поток: критическое исключение уходит в лог, а не только в stderr
        def _sys_hook(exc_type, exc, tb):
            if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
                sys.__excepthook__(exc_type, exc, tb)
                return
            t = "".join(traceback.format_exception(exc_type, exc, tb))
            log.critical(f"НЕПЕРЕХВАЧЕННОЕ ИСКЛЮЧЕНИЕ (main thread):\n{t}")
            self._count(exc_type.__name__)

        sys.excepthook = _sys_hook

        # 3) Фоновые потоки (веб-сервер, туннели): исключение в потоке не убьёт бота молча
        def _thread_hook(args: "threading.ExceptHookArgs"):
            if issubclass(args.exc_type, (KeyboardInterrupt, SystemExit)):
                return
            t = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
            log.critical(f"НЕПЕРЕХВАЧЕННОЕ ИСКЛЮЧЕНИЕ (поток {args.thread.name if args.thread else '?'}):\n{t}")
            self._count(args.exc_type.__name__)

        threading.excepthook = _thread_hook

    def _loop_exception_handler(self, loop: asyncio.AbstractEventLoop, context: dict):
        """Ошибки фоновых asyncio-задач: логируем, цикл не останавливаем."""
        exc = context.get("exception")
        msg = context.get("message", "asyncio error")
        if exc is not None:
            self._log_error(f"Asyncio task error: {msg} ({exc})", exc)
        else:
            log.error(f"Asyncio error: {msg}")

    def _count(self, error_type: str):
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

    async def _safe_send(self, ctx: commands.Context, **kwargs):
        """Отправка, которая сама не может уронить обработчик (канал удалён, нет прав...)"""
        try:
            await ctx.send(**kwargs)
        except Exception:
            pass

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
            await self._safe_send(ctx, embed=embed, delete_after=15)
            return

        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            embed = self._error_embed(
                "У бота нет прав",
                f"Боту не хватает прав: `{missing}`"
            )
            await self._safe_send(ctx, embed=embed, delete_after=15)
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
            await self._safe_send(ctx, embed=embed, delete_after=20)
            return

        if isinstance(error, commands.BadArgument):
            embed = self._error_embed(
                "Неверный аргумент",
                f"Не удалось разобрать аргумент: {error}"
            )
            await self._safe_send(ctx, embed=embed, delete_after=15)
            return

        # === Кулдаун ===
        if isinstance(error, commands.CommandOnCooldown):
            embed = self._error_embed(
                "Команда на перезарядке",
                f"Попробуйте через {error.retry_after:.1f} сек."
            )
            await self._safe_send(ctx, embed=embed, delete_after=10)
            return

        # === Проверки не пройдены ===
        if isinstance(error, commands.CheckFailure):
            embed = self._error_embed(
                "Проверка не пройдена",
                "У вас нет доступа к этой команде"
            )
            await self._safe_send(ctx, embed=embed, delete_after=15)
            return

        # === Неизвестная ошибка ===
        self._log_error(f"Command error in {ctx.command}: {error}", error)

        embed = self._error_embed(
            "Произошла ошибка",
            "Непредвиденная ошибка при выполнении команды. Администрация уже уведомлена."
        )
        await self._safe_send(ctx, embed=embed, delete_after=20)

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
        self._count(type(error).__name__)

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
