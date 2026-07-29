"""
Ses команды — raspoznavanie reci ve preobrazovanie в metin
Ispolzuet Whisper API или lokalnuyu model
"""
import discord
from discord.ext import commands
import os
import json
import tempfile
from typing import Optional, Dict
import asyncio


class VoiceCommands(commands.Cog):
    """Raspoznavanie ses сообщение"""
    
    def __init__(self, bot):
        self.bot = bot
        self.whisper_available = self._check_whisper()
    
    def _check_whisper(self) -> bool:
        """Контроль ediyor erişisimlerin mı Whisper"""
        try:
            import whisper
            return True
        except ImportError:
            return False
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Obrabativaet ses сообщения"""
        if message.author.bot or not message.guild:
            return
        
        # Контроль ediyoruz var mı ses сообщение
        if not message.attachments:
            return
        
        for attachment in message.attachments:
            # Контроль ediyoruz ne bu audio dosya
            if not self._is_audio_file(attachment.filename):
                continue
            
            # Işliyoruz ses сообщение
            await self._process_voice_message(message, attachment)
    
    def _is_audio_file(self, filename: str) -> bool:
        """Контроль ediyor yavlyaetsya mı dosya audio"""
        audio_extensions = ['.ogg', '.mp3', '.wav', '.m4a', '.opus']
        return any(filename.lower().endswith(ext) for ext in audio_extensions)
    
    async def _process_voice_message(self, message: discord.Message, attachment: discord.Attachment):
        """Obrabativaet ses сообщение"""
        try:
            # Отправл состояние
            status_msg = await message.channel.send(
                f"🎤 Işliyorum ses сообщение den {message.author.mention}..."
            )
            
            # Skacivaem dosya
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(attachment.filename)[1]) as tmp_file:
                await attachment.save(tmp_file.name)
                tmp_path = tmp_file.name
            
            try:
                # Raspoznaem разговор
                if self.whisper_available:
                    text = await self._transcribe_with_whisper(tmp_path)
                else:
                    text = await self._transcribe_with_api(tmp_path)
                
                if not text or len(text.strip()) < 3:
                    await status_msg.edit(content="❌ Не успешно oldu raspoznat разговор в seste soobsenii.")
                    return
                
                # Обновл состояние
                await status_msg.edit(
                    content=f"🎤 **{message.author.display_name}** (ses):\n> {text}\n\n⚙️ Işliyorum sorgu..."
                )
                
                # Işliyoruz как metinovoe сообщение
                # Создал feykovoe сообщение с metinle
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
                
                # Çтяжелыйıyoruz obrabotcik metin сообщение
                # (AI sohbet или ticket система obçalışmayut bu)
                await self.bot.process_commands(fake_message)
                
                # Обновл состояние
                await status_msg.edit(
                    content=f"🎤 **{message.author.display_name}** (ses):\n> {text}"
                )
                
            finally:
                # Udalyaem vremenniy dosya
                try:
                    os.unlink(tmp_path)
                except:
                    pass
        
        except Exception as e:
            print(f"[VOICE] Ошибка obrabotki ses: {e}")
            import traceback
            traceback.print_exc()
            
            try:
                await status_msg.edit(content="❌ Ошибка iken obrabotke ses сообщения.")
            except:
                pass
    
    async def _transcribe_with_whisper(self, audio_path: str) -> Optional[str]:
        """Raspoznaet разговор с с Whisper"""
        try:
            import whisper
            
            # Загруз model (malenkuyu для skorosti)
            model = whisper.load_model("base")
            
            # Raspoznaem
            result = model.transcribe(
                audio_path,
                language="ru",  # Russi текст
                task="transcribe"
            )
            
            return result.get("text", "").strip()
        
        except Exception as e:
            print(f"[WHISPER] Ошибка: {e}")
            return None
    
    async def _transcribe_with_api(self, audio_path: str) -> Optional[str]:
        """Raspoznaet разговор с vnesniy API (fallback)"""
        try:
            # Здесь mümkün podanahtarit vnesniy API (Google Speech, Azure, etc.)
            # Пока ne vozvrasaem None — Whisper не kuruldu
            print("[VOICE] Whisper не kuruldu, API не nastroen")
            return None
        
        except Exception as e:
            print(f"[VOICE API] Ошибка: {e}")
            return None
    
    @commands.command(name="voice-status")
    @commands.has_permissions(manage_messages=True)
    async def voice_status(self, ctx):
        """Henüzzivaet состояние система ses команд"""
        status = "✅ Erişisimlerin" if self.whisper_available else "❌ Не kuruldu"
        
        e = discord.Embed(
            title="Состояние ses команд",
            color=0x5865F2 if self.whisper_available else 0xFF0000
        )
        e.description = (
            f"**Whisper:** {status}\n\n"
        )
        
        if self.whisper_available:
            e.description += (
                "Система ses команд активен.\n"
                "Denhaklarınte ses сообщение в канал с AI — "
                "ono olacak автоматически как raspoznano ve obçalışmano."
            )
        else:
            e.description += (
                "Для работа ses команд ustanovite Whisper:\n"
                "```bash\npip install openai-whisper\n```"
            )
        
        e.set_footer(text=f"{ctx.guild.name}")
        await ctx.send(embed=e)


async def setup(bot):
    await bot.add_cog(VoiceCommands(bot))
