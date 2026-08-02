"""
Голосовые команды
Распознавание голосовых сообщений и преобразование в текст
Использует Whisper API или локальную модель
"""
import discord
from discord.ext import commands
import os
import tempfile
from typing import Optional

from logger import get_logger

log = get_logger("voice_commands")


class VoiceCommands(commands.Cog):
    """Распознавание голосовых сообщений"""

    def __init__(self, bot):
        self.bot = bot
        self.whisper_available = self._check_whisper()

    def _check_whisper(self) -> bool:
        """Проверить доступность Whisper (faster-whisper или openai-whisper)"""
        for lib in ("faster_whisper", "whisper"):
            try:
                __import__(lib)
                return True
            except ImportError:
                continue
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Обработка голосовых сообщений"""
        if message.author.bot or not message.guild:
            return

        if not message.attachments:
            return

        for attachment in message.attachments:
            if not self._is_audio_file(attachment.filename):
                continue
            await self._process_voice_message(message, attachment)

    def _is_audio_file(self, filename: str) -> bool:
        """Проверить, является ли файл аудио"""
        audio_extensions = ['.ogg', '.mp3', '.wav', '.m4a', '.opus']
        return any(filename.lower().endswith(ext) for ext in audio_extensions)

    async def _process_voice_message(self, message: discord.Message, attachment: discord.Attachment):
        """Обработать голосовое сообщение"""
        status_msg = None
        try:
            status_msg = await message.channel.send(
                f"Обрабатываю голосовое сообщение от {message.author.mention}..."
            )

            # Скачиваем файл
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(attachment.filename)[1]) as tmp_file:
                await attachment.save(tmp_file.name)
                tmp_path = tmp_file.name

            try:
                # Распознаём речь
                if self.whisper_available:
                    text = await self._transcribe_with_whisper(tmp_path)
                else:
                    text = await self._transcribe_with_api(tmp_path)

                if not text or len(text.strip()) < 3:
                    await status_msg.edit(content="Не удалось распознать речь в голосовом сообщении.")
                    return

                # Обновляем статус
                await status_msg.edit(
                    content=f"**{message.author.display_name}** (голос):\n> {text}"
                )

            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        except Exception as e:
            log.error(f"Ошибка обработки голоса: {e}")
            if status_msg:
                try:
                    await status_msg.edit(content="Ошибка при обработке голосового сообщения.")
                except Exception:
                    pass

    async def _transcribe_with_whisper(self, audio_path: str) -> Optional[str]:
        """Распознавание речи через Whisper (faster-whisper или openai-whisper)"""
        # faster-whisper
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, _info = model.transcribe(
                audio_path,
                language="ru",
                vad_filter=True,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            if text:
                return text
        except Exception as e:
            log.warning(f"faster-whisper не сработал, пробуем openai-whisper: {e}")

        # openai-whisper
        try:
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(
                audio_path,
                language="ru",
                task="transcribe"
            )
            return result.get("text", "").strip()
        except Exception as e:
            log.error(f"Whisper ошибка: {e}")
            return None

    async def _transcribe_with_api(self, audio_path: str) -> Optional[str]:
        """Распознавание речи через внешний API (fallback)"""
        try:
            log.warning("Whisper не установлен, API не настроен")
            return None
        except Exception as e:
            log.error(f"Voice API ошибка: {e}")
            return None

    @commands.command(name="voice-status")
    @commands.has_permissions(manage_messages=True)
    async def voice_status(self, ctx):
        """Показать состояние системы голосовых команд"""
        status = "Доступен" if self.whisper_available else "Не установлен"

        embed = discord.Embed(
            title="Голосовые команды",
            color=discord.Color.dark_grey()
        )
        embed.description = f"**Whisper:** {status}\n\n"

        if self.whisper_available:
            embed.description += (
                "Система голосовых команд активна.\n"
                "Голосовые сообщения в каналах будут автоматически распознаваться."
            )
        else:
            embed.description += (
                "Для работы голосовых команд установите Whisper:\n"
                "```bash\npip install faster-whisper   # рекомендуется\n# или\npip install openai-whisper\n```"
            )

        embed.set_footer(text=ctx.guild.name)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(VoiceCommands(bot))
    log.info("VoiceCommands загружен")
