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
from datetime import datetime

from logger import get_logger

log = get_logger("voice_commands")


class VoiceCommands(commands.Cog):
    """Распознавание голосовых сообщений"""

    def __init__(self, bot):
        self.bot = bot
        self.whisper_available = self._check_whisper()

    def _check_whisper(self) -> bool:
        """Проверить доступность Whisper"""
        try:
            import whisper
            return True
        except ImportError:
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
        """Распознавание речи через Whisper"""
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
                "```bash\npip install openai-whisper\n```"
            )

        embed.set_footer(text=ctx.guild.name)
        await ctx.send(embed=embed)

    # ═══════════════════════════════════════════════════════════════
    #  АНАЛИЗ ВИДЕО (видео → звук → текст → AI-обзор)
    # ═══════════════════════════════════════════════════════════════
    def _find_ffmpeg(self) -> Optional[str]:
        """Найти ffmpeg (из пути музыки или из PATH)"""
        import shutil
        candidates = [
            os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ffmpeg-8.1-essentials_build', 'bin', 'ffmpeg.exe'),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        for name in ('ffmpeg', 'ffmpeg.exe'):
            p = shutil.which(name)
            if p:
                return p
        return None

    @commands.command(name="video-analiz", aliases=["video-analyze", "video-ozet", "video-обзор"])
    @commands.has_permissions(manage_messages=True)
    async def video_analiz(self, ctx, link: str = None):
        """Анализ видео: прикрепите файл или дайте ссылку. Извлекает речь и делает AI-обзор."""
        import subprocess
        import shutil

        attachment = ctx.message.attachments[0] if ctx.message.attachments else None
        if not link and not attachment:
            await ctx.send("❌ Прикрепите видео-файл или дайте ссылку на видео.\nПример: `!video-analiz @видео.mp4`")
            return

        status = await ctx.send("⏳ Анализирую видео... это может занять время.")

        tmp_video = None
        tmp_audio = None
        try:
            # Скачиваем видео, если прикреплён файл
            if attachment:
                if not any(attachment.filename.lower().endswith(e) for e in ('.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v', '.mpg')):
                    await status.edit(content="❌ Неподдерживаемый формат видео. Поддерживаются: mp4, mov, mkv, webm, avi, m4v.")
                    return
                tmp_video = os.path.join(tempfile.gettempdir(), attachment.filename.replace(' ', '_'))
                await attachment.save(tmp_video)
                await status.edit(content="✅ Видео получено. Извлекаю звук...")
            else:
                # Ссылка — скачиваем через yt-dlp (без звука, только аудио)
                await status.edit(content="🔽 Скачиваю аудио из ссылки...")
                tmp_audio = os.path.join(tempfile.gettempdir(), "video_analiz_audio.mp3")
                try:
                    from yt_dlp import YoutubeDL
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': os.path.join(tempfile.gettempdir(), 'video_analiz_audio.%(ext)s'),
                        'quiet': True,
                    }
                    with YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(link, download=True)
                        ext = info.get('ext', 'mp3')
                        tmp_audio = os.path.join(tempfile.gettempdir(), f'video_analiz_audio.{ext}')
                        await status.edit(content="✅ Аудио скачано. Распознаю речь...")
                except Exception as e:
                    await status.edit(content=f"❌ Не удалось скачать видео по ссылке: {str(e)[:100]}")
                    return

            # Извлекаем звук из видео через ffmpeg
            if tmp_video:
                tmp_audio = os.path.join(tempfile.gettempdir(), "video_analiz_audio.wav")
                ffmpeg = self._find_ffmpeg()
                if not ffmpeg:
                    await status.edit(content="❌ ffmpeg не найден. Установите ffmpeg для анализа видео.")
                    return
                await status.edit(content="🎵 Извлекаю звук из видео...")
                result = subprocess.run(
                    [ffmpeg, '-y', '-i', tmp_video, '-vn', '-ar', '16000', '-ac', '1', tmp_audio],
                    capture_output=True, timeout=120
                )
                if not os.path.exists(tmp_audio):
                    await status.edit(content="❌ Не удалось извлечь звук из видео.")
                    return
                await status.edit(content="🗣️ Распознаю речь (Whisper)...")

            # Распознаём речь
            text = None
            if self.whisper_available:
                text = await self._transcribe_with_whisper(tmp_audio)
            if not text or len(text.strip()) < 3:
                await status.edit(content="⚠️ В видео не удалось распознать речь (или видео без звука).")
                return

            # AI-обзор текста
            await status.edit(content="🤖 Составляю AI-обзор...")
            summary = await self._ai_summarize(text)

            # Отправляем результат
            embed = discord.Embed(
                title="🎬 Анализ видео",
                color=0x3498DB,
                timestamp=datetime.now()
            )
            embed.add_field(name="📝 Транскрипт", value=f"```{text[:1500]}```", inline=False)
            if summary and summary != text:
                embed.add_field(name="🤖 AI-обзор", value=summary[:1500], inline=False)
            embed.set_footer(text=f"Анализировал: {ctx.author.display_name}")
            await status.edit(content=None, embed=embed)

        except Exception as e:
            log.error(f"Video analyze error: {e}")
            import traceback
            traceback.print_exc()
            try:
                await status.edit(content=f"❌ Ошибка анализа видео: {str(e)[:150]}")
            except Exception:
                pass
        finally:
            for p in (tmp_video, tmp_audio):
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass

    async def _ai_summarize(self, text: str) -> str:
        """Отправить текст в AI для получения обзора"""
        try:
            from web.ai_helper import _call_text
            prompt = (
                "Ты — AI-аналитик видео. Ниже транскрипт речи из видео.\n"
                "Составь краткий, структурированный обзор на русском языке:\n"
                "1. Тема видео\n2. Основные моменты (3-5 пунктов)\n3. Вывод\n\n"
                f"ТРАНСКРИПТ:\n{text[:3000]}"
            )
            resp = await self.bot.loop.run_in_executor(
                None,
                lambda: _call_text(
                    [{"role": "system", "content": "Ты — полезный аналитик. Отвечай кратко и структурированно."},
                     {"role": "user", "content": prompt}],
                    max_tokens=700, temperature=0.4
                )
            )
            return (resp or "").strip()
        except Exception as e:
            log.error(f"AI summarize error: {e}")
            return text


async def setup(bot):
    await bot.add_cog(VoiceCommands(bot))
    log.info("VoiceCommands загружен")
