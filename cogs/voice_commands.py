"""
Голосовые команды — распознавание речи и преобразование в текст
Использует Whisper API или локальную модель
"""
import discord
from discord.ext import commands
import os
import json
import tempfile
from typing import Optional, Dict
import asyncio


class VoiceCommands(commands.Cog):
    """Распознавание голосовых сообщений"""
    
    def __init__(self, bot):
        self.bot = bot
        self.whisper_available = self._check_whisper()
    
    def _check_whisper(self) -> bool:
        """Проверяет доступен ли Whisper"""
        try:
            import whisper
            return True
        except ImportError:
            return False
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Обрабатывает голосовые сообщения"""
        if message.author.bot or not message.guild:
            return
        
        # Проверяем есть ли голосовое сообщение
        if not message.attachments:
            return
        
        for attachment in message.attachments:
            # Проверяем что это аудио файл
            if not self._is_audio_file(attachment.filename):
                continue
            
            # Обрабатываем голосовое сообщение
            await self._process_voice_message(message, attachment)
    
    def _is_audio_file(self, filename: str) -> bool:
        """Проверяет является ли файл аудио"""
        audio_extensions = ['.ogg', '.mp3', '.wav', '.m4a', '.opus']
        return any(filename.lower().endswith(ext) for ext in audio_extensions)
    
    async def _process_voice_message(self, message: discord.Message, attachment: discord.Attachment):
        """Обрабатывает голосовое сообщение"""
        try:
            # Отправляем статус
            status_msg = await message.channel.send(
                f"🎤 Обрабатываю голосовое сообщение от {message.author.mention}..."
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
                    await status_msg.edit(content="❌ Не удалось распознать речь в голосовом сообщении.")
                    return
                
                # Обновляем статус
                await status_msg.edit(
                    content=f"🎤 **{message.author.display_name}** (голосовое):\n> {text}\n\n⚙️ Обрабатываю запрос..."
                )
                
                # Обрабатываем как текстовое сообщение
                # Создаём фейковое сообщение с текстом
                fake_message = type('FakeMessage', (), {
                    'content': text,
                    'author': message.author,
                    'channel': message.channel,
                    'guild': message.guild,
                    'id': message.id,
                    'attachments': [],
                    'mentions': message.mentions,
                    'created_at': message.created_at,
                })()
                
                # Вызываем обработчик текстовых сообщений
                # (AI чат или тикет система обработают это)
                await self.bot.process_commands(fake_message)
                
                # Обновляем статус
                await status_msg.edit(
                    content=f"🎤 **{message.author.display_name}** (голосовое):\n> {text}"
                )
                
            finally:
                # Удаляем временный файл
                try:
                    os.unlink(tmp_path)
                except:
                    pass
        
        except Exception as e:
            print(f"[VOICE] Ошибка обработки голосового: {e}")
            import traceback
            traceback.print_exc()
            
            try:
                await status_msg.edit(content="❌ Ошибка при обработке голосового сообщения.")
            except:
                pass
    
    async def _transcribe_with_whisper(self, audio_path: str) -> Optional[str]:
        """Распознаёт речь с помощью Whisper"""
        try:
            import whisper
            
            # Загружаем модель (маленькую для скорости)
            model = whisper.load_model("base")
            
            # Распознаём
            result = model.transcribe(
                audio_path,
                language="ru",  # Русский язык
                task="transcribe"
            )
            
            return result.get("text", "").strip()
        
        except Exception as e:
            print(f"[WHISPER] Ошибка: {e}")
            return None
    
    async def _transcribe_with_api(self, audio_path: str) -> Optional[str]:
        """Распознаёт речь через внешний API (fallback)"""
        try:
            # Здесь можно подключить внешний API (Google Speech, Azure, etc.)
            # Пока что возвращаем None — Whisper не установлен
            print("[VOICE] Whisper не установлен, API не настроен")
            return None
        
        except Exception as e:
            print(f"[VOICE API] Ошибка: {e}")
            return None
    
    @commands.command(name="voice-status")
    @commands.has_permissions(manage_messages=True)
    async def voice_status(self, ctx):
        """Показывает статус системы голосовых команд"""
        status = "✅ Доступен" if self.whisper_available else "❌ Не установлен"
        
        e = discord.Embed(
            title="Статус голосовых команд",
            color=0x5865F2 if self.whisper_available else 0xFF0000
        )
        e.description = (
            f"**Whisper:** {status}\n\n"
        )
        
        if self.whisper_available:
            e.description += (
                "Система голосовых команд активна.\n"
                "Отправьте голосовое сообщение в канал с AI — "
                "оно будет автоматически распознано и обработано."
            )
        else:
            e.description += (
                "Для работы голосовых команд установите Whisper:\n"
                "```bash\npip install openai-whisper\n```"
            )
        
        e.set_footer(text=f"{ctx.guild.name}")
        await ctx.send(embed=e)


async def setup(bot):
    await bot.add_cog(VoiceCommands(bot))
