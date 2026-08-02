"""
Голосовые команды
Распознавание голосовых сообщений и преобразование в текст
Использует Whisper API или локальную модель
"""
import discord
from discord.ext import commands
import os
import re
import json
import asyncio
import subprocess
import tempfile
import threading
from typing import Optional

from logger import get_logger

log = get_logger("voice_commands")


# ═══════════════════════════════════════════════════════════════════
#  SELECT-ПАНЕЛЬ ВИДЕО (dropdown-меню)
# ═══════════════════════════════════════════════════════════════════
VIDEO_PANEL_COLOR = 0x3498DB

VIDEO_MAIN_OPTIONS = [
    discord.SelectOption(label="🎬 Анализ видео", value="analyze",
                         description="Прикрепите видео в канал — бот сам сделает анализ и обзор"),
    discord.SelectOption(label="📂 Канал результатов", value="channel",
                         description="Куда отправлять готовые обзоры видео"),
    discord.SelectOption(label="⏱️ Лимит длительности", value="duration",
                         description="Максимальная длина видео для авто-анализа"),
    discord.SelectOption(label="⚙️ Текущие настройки", value="settings",
                         description="Посмотреть текущие настройки видео-анализа"),
]

DURATION_OPTIONS = [
    discord.SelectOption(label="1 мин", value="1", description="Только короткие ролики"),
    discord.SelectOption(label="3 мин", value="3", description="Клипы и короткие видео"),
    discord.SelectOption(label="5 мин", value="5", description="Средние видео"),
    discord.SelectOption(label="10 мин", value="10", description="Стандартный лимит (по умолчанию)"),
    discord.SelectOption(label="15 мин", value="15", description="Длинные видео"),
    discord.SelectOption(label="30 мин", value="30", description="Очень длинные видео (медленно)"),
]


def _panel_footer_embed(title: str, description: str, color=VIDEO_PANEL_COLOR) -> discord.Embed:
    """Общий стиль embed для видео-панели."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text="Видео-анализ • Aether")
    return embed


class VideoMainSelect(discord.ui.Select):
    """Главный dropdown с выбором действия."""

    def __init__(self, cog):
        super().__init__(
            placeholder="Выберите действие...",
            options=VIDEO_MAIN_OPTIONS,
            min_values=1,
            max_values=1,
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        guild = interaction.guild

        if value == "analyze":
            embed = _panel_footer_embed(
                "🎬 Как анализировать видео",
                "Просто **прикрепите видеофайл** в любой текстовый канал сервера.\n"
                "Бот **сам** его скачает, извлечёт речь и пришлёт AI-обзор.\n\n"
                "**Поддерживаемые форматы:** mp4, mov, mkv, webm, avi, m4v\n\n"
                "Результат появится в канале результатов (см. меню «📂 Канал результатов»).",
            )
            await interaction.response.edit_message(embed=embed, view=VideoPanelView(self.cog))

        elif value == "channel":
            view = VideoPanelView(self.cog)
            view.add_item(VideoChannelSelect(self.cog))
            embed = _panel_footer_embed(
                "📂 Выберите канал для результатов",
                "Выберите текстовый канал, куда бот будет отправлять готовые обзоры видео.",
            )
            await interaction.response.edit_message(embed=embed, view=view)

        elif value == "duration":
            view = VideoPanelView(self.cog)
            view.add_item(VideoDurationSelect(self.cog))
            cur = self.cog._get_max_duration(guild) // 60
            embed = _panel_footer_embed(
                "⏱️ Выберите лимит длительности",
                f"Сейчас лимит: **{cur} мин**.\nВидео длиннее лимита не анализируются (чтобы не грузить бота).",
            )
            await interaction.response.edit_message(embed=embed, view=view)

        elif value == "settings":
            embed = self.cog._video_settings_embed(guild)
            await interaction.response.edit_message(embed=embed, view=VideoPanelView(self.cog))


class VideoChannelSelect(discord.ui.ChannelSelect):
    """Выбор канала для результатов."""

    def __init__(self, cog):
        super().__init__(
            placeholder="Выберите текстовый канал...",
            channel_types=[discord.ChannelType.text],
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        self.cog._set_guild_cfg(interaction.guild, "channel_id", channel.id)
        embed = _panel_footer_embed(
            "✅ Канал назначен",
            f"Готовые обзоры видео теперь отправляются в {channel.mention}.",
            color=discord.Color.green(),
        )
        await interaction.response.edit_message(embed=embed, view=VideoPanelView(self.cog))


class VideoDurationSelect(discord.ui.Select):
    """Выбор лимита длительности."""

    def __init__(self, cog):
        super().__init__(
            placeholder="Выберите лимит...",
            options=DURATION_OPTIONS,
            min_values=1,
            max_values=1,
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        minutes = int(self.values[0])
        self.cog._set_guild_cfg(interaction.guild, "max_duration_seconds", minutes * 60)
        embed = _panel_footer_embed(
            "✅ Лимит установлен",
            f"Авто-анализ теперь обрабатывает видео длиной до **{minutes} мин**.",
            color=discord.Color.green(),
        )
        await interaction.response.edit_message(embed=embed, view=VideoPanelView(self.cog))


class VideoPanelView(discord.ui.View):
    """Главный view панели: dropdown + кнопка закрытия."""

    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog
        self.add_item(VideoMainSelect(cog))

    @discord.ui.button(label="Закрыть", style=discord.ButtonStyle.secondary, emoji="✖", row=1)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Панель закрыта.", embed=None, view=None)


class VoiceCommands(commands.Cog):
    """Распознавание голосовых сообщений"""

    def __init__(self, bot):
        self.bot = bot
        self.whisper_available = self._check_whisper()
        # Кэш модели Whisper: загружается один раз и переиспользуется.
        self._whisper_model = None
        self.whisper_model_name = None
        self._whisper_load_error = None
        self._whisper_model_lock = threading.Lock()
        # Расположение скачанных моделей (чтобы не качать каждый раз).
        self.whisper_models_dir = os.path.join("data", "whisper_models")

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
        """Обработка голосовых сообщений и автоматический анализ видео"""
        if message.author.bot or not message.guild:
            return

        if not message.attachments:
            return

        for attachment in message.attachments:
            if self._is_video_file(attachment.filename):
                await self._process_video_message(message, attachment)
            elif self._is_audio_file(attachment.filename):
                await self._process_voice_message(message, attachment)

    def _is_audio_file(self, filename: str) -> bool:
        """Проверить, является ли файл аудио"""
        audio_extensions = ['.ogg', '.mp3', '.wav', '.m4a', '.opus']
        return any(filename.lower().endswith(ext) for ext in audio_extensions)

    def _is_video_file(self, filename: str) -> bool:
        """Проверить, является ли файл видео"""
        video_extensions = ['.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v', '.mpg', '.mpeg']
        return any(filename.lower().endswith(ext) for ext in video_extensions)

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
        """Распознавание речи через Whisper.

        Порядок:
        1) локальная faster-whisper модель (если скачана);
        2) openai-whisper (если установлен);
        3) облачный OpenAI Whisper API (если есть OPENAI_API_KEY) — без скачивания модели.
        """
        # 1) faster-whisper — предпочтительный бэкенд (уже в requirements.txt)
        try:
            text = await self._transcribe_with_faster_whisper(audio_path)
            if text:
                return text
        except Exception as e:
            log.warning(f"faster-whisper не сработал, пробуем openai-whisper: {e}")

        # 2) fallback: openai-whisper (локальная библиотека)
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
            log.warning(f"openai-whisper не сработал: {e}")

        # 3) fallback: облачный OpenAI Whisper API — не требует скачивания модели
        text = await self._transcribe_with_cloud_api(audio_path)
        if text:
            return text

        log.error("Все способы распознавания речи не сработали")
        return None

    async def _transcribe_with_cloud_api(self, audio_path: str) -> Optional[str]:
        """Распознавание речи через облачный OpenAI Whisper API (whisper-1).

        Работает без скачивания локальной модели — достаточно OPENAI_API_KEY.
        """
        try:
            import requests
            api_url = os.getenv("OPENAI_AUDIO_URL", "https://api.openai.com/v1/audio/transcriptions")
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return None
            with open(audio_path, "rb") as f:
                resp = requests.post(
                    api_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    data={"model": "whisper-1", "language": "ru", "response_format": "text"},
                    files={"file": (os.path.basename(audio_path), f, "audio/wav")},
                    timeout=180,
                )
            if resp.status_code == 200 and resp.text.strip():
                return resp.text.strip()
            log.error(f"Cloud Whisper ошибка {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            log.error(f"Cloud Whisper исключение: {e}")
        return None

    def _get_whisper_model(self):
        """Загрузить модель faster-whisper один раз и кэшировать (потокобезопасно).

        Размер модели берётся из WHISPER_MODEL (tiny/base/small). tiny скачивается
        и работает быстрее. По умолчанию base.

        Стабильность скачивания:
          - отключаем Xet (новый ненадёжный бэкенд HF) → классическая загрузка;
          - поддерживаем зеркало hf-mirror.com через HF_ENDPOINT (для РФ/Китая).
        """
        if self._whisper_model is not None:
            return self._whisper_model
        with self._whisper_model_lock:
            if self._whisper_model is not None:
                return self._whisper_model
            self._whisper_load_error = None
            try:
                # Отключаем Xet-бэкенд HuggingFace (частый источник CAS-ошибок).
                os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
                # Если пользователь указал зеркало (HF_ENDPOINT) — huggingface_hub
                # подхватит его автоматически.
                from faster_whisper import WhisperModel
                model_name = os.getenv("WHISPER_MODEL", "base").strip().lower()
                if model_name not in ("tiny", "base", "small"):
                    model_name = "base"
                os.makedirs(self.whisper_models_dir, exist_ok=True)
                log.info(f"Загрузка модели Whisper '{model_name}' (первый запуск)...")

                # Пробуем загрузить с повторными попытками (сеть может падать).
                model = None
                endpoint = os.getenv("HF_ENDPOINT") or "HuggingFace (по умолчанию)"
                for attempt in range(1, 4):
                    try:
                        model = WhisperModel(
                            model_name, device="cpu", compute_type="int8",
                            download_root=self.whisper_models_dir,
                        )
                        break
                    except Exception as e:
                        self._whisper_load_error = str(e)
                        log.error(f"Попытка {attempt}/3 загрузки Whisper не удалась ({endpoint}): {e}")
                        import time
                        time.sleep(2)
                if model is None:
                    self._whisper_model = None
                    return None

                self._whisper_model = model
                self.whisper_model_name = model_name
                log.info(f"Whisper модель '{model_name}' загружена (dir={self.whisper_models_dir})")
            except Exception as e:
                self._whisper_load_error = str(e)
                log.error(f"Whisper model load error: {e}", exc_info=True)
                self._whisper_model = None
        return self._whisper_model

    async def _preload_whisper_model(self):
        """Предзагрузить модель Whisper в фоне сразу после старта бота,
        чтобы первый видео-анализ не заставлял пользователя ждать скачивание."""
        try:
            await asyncio.sleep(3)  # дать боту дочитаться
            await self.bot.loop.run_in_executor(None, self._get_whisper_model)
            if self._whisper_model is not None:
                log.info("Whisper модель предзагружена в фоне")
            else:
                log.warning("Whisper модель не смогла предзагрузиться (будет попытка при анализе)")
        except Exception as e:
            log.error(f"Предзагрузка Whisper не удалась: {e}")

    async def _transcribe_with_faster_whisper(self, audio_path: str) -> Optional[str]:
        """Распознавание речи через faster-whisper (CTranslate2). Выполняется в потоке."""
        loop = self.bot.loop
        try:
            model = await loop.run_in_executor(None, self._get_whisper_model)
            if model is None:
                return None

            def _run():
                segments, _info = model.transcribe(
                    audio_path,
                    language="ru",
                    vad_filter=True,
                    beam_size=5,
                )
                return " ".join(seg.text.strip() for seg in segments).strip()

            text = await loop.run_in_executor(None, _run)
            return text or None
        except Exception as e:
            log.error(f"faster-whisper ошибка: {e}")
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

    # ═══════════════════════════════════════════════════════════════
    #  АВТОМАТИЧЕСКИЙ АНАЛИЗ ВИДЕО (видео → звук → текст → AI-обзор)
    #  Срабатывает сам, когда пользователь прикрепляет видео. Результат
    #  отправляется в отдельный канал (по умолчанию #video-analiz).
    # ═══════════════════════════════════════════════════════════════
    CONFIG_FILE = os.path.join("data", "video_analiz_config.json")
    DEFAULT_MAX_DURATION = 600  # 10 минут

    def _load_config(self) -> dict:
        """Загрузить настройки видео-анализа по серверам."""
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log.error(f"video config load error: {e}")
        return {}

    def _save_config(self, config: dict):
        """Сохранить настройки видео-анализа."""
        try:
            os.makedirs(os.path.dirname(self.CONFIG_FILE), exist_ok=True)
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"video config save error: {e}")

    def _get_guild_cfg(self, guild) -> dict:
        cfg = self._load_config()
        return cfg.get(str(guild.id), {})

    def _set_guild_cfg(self, guild, key, value):
        cfg = self._load_config()
        gid = str(guild.id)
        cfg.setdefault(gid, {})
        cfg[gid][key] = value
        self._save_config(cfg)

    def _get_max_duration(self, guild) -> int:
        return int(self._get_guild_cfg(guild).get("max_duration_seconds", self.DEFAULT_MAX_DURATION))

    async def _get_analiz_channel(self, guild) -> discord.TextChannel:
        """Найти канал для результатов. Сначала назначенный, потом #video-analiz, иначе создать."""
        cid = self._get_guild_cfg(guild).get("channel_id")
        if cid:
            ch = guild.get_channel(cid)
            if ch and isinstance(ch, discord.TextChannel):
                return ch
        ch = discord.utils.get(guild.text_channels, name="video-analiz")
        if ch:
            return ch
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        return await guild.create_text_channel("video-analiz", overwrites=overwrites)

    def _get_video_duration(self, path: str) -> Optional[int]:
        """Получить длительность видео в секундах через ffmpeg."""
        ffmpeg = self._find_ffmpeg()
        if not ffmpeg:
            return None
        try:
            result = subprocess.run([ffmpeg, "-i", path], capture_output=True, text=True, timeout=15)
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+)", result.stderr or "")
            if m:
                h, mn, s = map(int, m.groups())
                return h * 3600 + mn * 60 + s
        except Exception as e:
            log.warning(f"get video duration error: {e}")
        return None

    async def _process_video_message(self, message: discord.Message, attachment: discord.Attachment):
        """Автоматически проанализировать видео и отправить результат в отдельный канал."""
        tmp_video = None
        tmp_audio = None
        status = None
        try:
            status = await message.channel.send("⏳ Видео обнаружено, анализирую...")
            tmp_video = os.path.join(
                tempfile.gettempdir(),
                f"auto_{attachment.id}_{attachment.filename.replace(' ', '_')}",
            )
            await attachment.save(tmp_video)

            # Проверка длительности
            dur = self._get_video_duration(tmp_video)
            max_dur = self._get_max_duration(message.guild)
            if dur and max_dur and dur > max_dur:
                await status.edit(
                    content=f"⏱️ Видео **{dur // 60} мин** — дольше лимита (**{max_dur // 60} мин**). Не анализировал."
                )
                return

            # Извлекаем звук
            ffmpeg = self._find_ffmpeg()
            if not ffmpeg:
                await status.edit(content="❌ ffmpeg не найден. Установите ffmpeg для анализа видео.")
                return
            await status.edit(content="🎵 Извлекаю звук из видео...")
            tmp_audio = os.path.join(tempfile.gettempdir(), f"auto_{attachment.id}.wav")
            subprocess.run(
                [ffmpeg, "-y", "-i", tmp_video, "-vn", "-ar", "16000", "-ac", "1", tmp_audio],
                capture_output=True, timeout=180,
            )
            if not os.path.exists(tmp_audio):
                await status.edit(content="❌ Не удалось извлечь звук из видео.")
                return

            # Распознаём речь
            if self.whisper_available:
                if self._whisper_model is None:
                    await status.edit(
                        content="🔄 Загружаю модель Whisper. Это первый запуск, скачивание "
                                "может занять 1–3 минуты. Подождите, пожалуйста..."
                    )
                else:
                    await status.edit(content="🗣️ Распознаю речь (Whisper)...")
            text = None
            if self.whisper_available:
                text = await self._transcribe_with_whisper(tmp_audio)
            if not text or len(text.strip()) < 3:
                if self.whisper_available and self._whisper_model is None and not os.getenv("OPENAI_API_KEY"):
                    await status.edit(
                        content="❌ Не удалось скачать модель Whisper и нет OPENAI_API_KEY для облачной "
                                "расшифровки. Добавьте в .env один из вариантов:\n"
                                "```\nOPENAI_API_KEY=<токен>   # облачная расшифровка (рекомендую)\n"
                                "# или\nHF_ENDPOINT=https://hf-mirror.com\nWHISPER_MODEL=tiny\n```\n"
                                f"Последняя ошибка: `{str(self._whisper_load_error)[:120] or 'нет'}`"
                    )
                else:
                    await status.edit(content="⚠️ В видео не распознана речь (или видео без звука).")
                return

            # AI-обзор
            await status.edit(content="🤖 Составляю AI-обзор...")
            summary = await self._ai_summarize(text)

            # Отправляем результат в отдельный канал
            target = await self._get_analiz_channel(message.guild)
            embed = discord.Embed(
                title="🎬 Автоматический анализ видео",
                color=0x3498DB,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
            embed.add_field(name="📝 Транскрипт", value=f"```{text[:1500]}```", inline=False)
            if summary and summary != text:
                embed.add_field(name="🤖 AI-обзор", value=summary[:1500], inline=False)
            embed.add_field(name="🔗 Видео", value=attachment.url, inline=False)
            embed.set_footer(text=message.guild.name)
            await target.send(embed=embed)
            await status.edit(content=f"✅ Готово! Результат в канале {target.mention}")

        except Exception as e:
            log.error(f"Auto video analyze error: {e}")
            import traceback
            traceback.print_exc()
            if status:
                try:
                    await status.edit(content=f"❌ Ошибка анализа видео: {str(e)[:120]}")
                except Exception:
                    pass
        finally:
            for p in (tmp_video, tmp_audio):
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass

    # ═══════════════════════════════════════════════════════════════
    #  АНАЛИЗ ВИДЕО ПО КОМАНДЕ (видео → звук → текст → AI-обзор)
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
            if self.whisper_available:
                if self._whisper_model is None:
                    await status.edit(
                        content="🔄 Загружаю модель Whisper. Это первый запуск, скачивание "
                                "может занять 1–3 минуты. Подождите, пожалуйста..."
                    )
                else:
                    await status.edit(content="🗣️ Распознаю речь (Whisper)...")
            text = None
            if self.whisper_available:
                text = await self._transcribe_with_whisper(tmp_audio)
            if not text or len(text.strip()) < 3:
                if self.whisper_available and self._whisper_model is None and not os.getenv("OPENAI_API_KEY"):
                    await status.edit(
                        content="❌ Не удалось скачать модель Whisper и нет OPENAI_API_KEY для облачной "
                                "расшифровки. Добавьте в .env один из вариантов:\n"
                                "```\nOPENAI_API_KEY=<токен>   # облачная расшифровка (рекомендую)\n"
                                "# или\nHF_ENDPOINT=https://hf-mirror.com\nWHISPER_MODEL=tiny\n```\n"
                                f"Последняя ошибка: `{str(self._whisper_load_error)[:120] or 'нет'}`"
                    )
                else:
                    await status.edit(content="⚠️ В видео не удалось распознать речь (или видео без звука).")
                return

            # AI-обзор текста
            await status.edit(content="🤖 Составляю AI-обзор...")
            summary = await self._ai_summarize(text)

            # Отправляем результат
            embed = discord.Embed(
                title="🎬 Анализ видео",
                color=0x3498DB,
                timestamp=discord.utils.utcnow()
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

    @commands.command(name="video-kanal", aliases=["video-channel", "video-kanal-ayarla"])
    @commands.has_permissions(manage_messages=True)
    async def video_kanal(self, ctx, channel: discord.TextChannel = None):
        """Назначить канал для результатов автоматического анализа видео."""
        channel = channel or ctx.channel
        self._set_guild_cfg(ctx.guild, "channel_id", channel.id)
        embed = discord.Embed(
            title="🎬 Канал результатов",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.description = f"Результаты анализа видео теперь отправляются в {channel.mention}"
        await ctx.send(embed=embed)

    @commands.command(name="video-sure", aliases=["video-limit", "video-sure-siniri"])
    @commands.has_permissions(manage_messages=True)
    async def video_sure(self, ctx, minutes: int = 10):
        """Установить лимит длительности видео для авто-анализа (в минутах)."""
        if minutes < 1:
            await ctx.send("❌ Лимит должен быть хотя бы 1 минута.")
            return
        seconds = minutes * 60
        self._set_guild_cfg(ctx.guild, "max_duration_seconds", seconds)
        embed = discord.Embed(
            title="⏱️ Лимит длительности",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.description = f"Авто-анализ обрабатывает видео длиной до **{minutes} мин**."
        await ctx.send(embed=embed)

    def _video_settings_embed(self, guild) -> discord.Embed:
        """Embed с текущими настройками видео-анализа."""
        cfg = self._get_guild_cfg(guild)
        cid = cfg.get("channel_id")
        max_sec = int(cfg.get("max_duration_seconds", self.DEFAULT_MAX_DURATION))
        ch = guild.get_channel(cid) if cid else None
        embed = _panel_footer_embed(
            "⚙️ Настройки видео-анализа",
            "Текущие настройки автоматического анализа видео.",
        )
        embed.add_field(name="📂 Канал результатов",
                        value=ch.mention if ch else "Не назначен (по умолчанию #video-analiz)", inline=False)
        embed.add_field(name="⏱️ Максимальная длительность",
                        value=f"**{max_sec // 60} мин**", inline=True)
        embed.add_field(name="🎬 Форматы",
                        value="`mp4, mov, mkv, webm, avi, m4v`", inline=True)
        return embed

    @commands.command(name="video", aliases=["video-panel", "video-menu", "video-panel-ac"])
    async def video_panel(self, ctx):
        """🎬 Открыть панель видео-анализа (меню)."""
        embed = _panel_footer_embed(
            "🎬 Видео-анализ",
            "Добро пожаловать в панель видео-анализа!\n\n"
            "**Что это?** Бот автоматически анализирует видео, которые участники "
            "прикрепляют в каналы: извлекает речь и делает AI-обзор.\n\n"
            "Выберите действие в меню ниже.",
        )
        embed.add_field(name="📌 Быстрый старт",
                        value="Просто **прикрепите видео** в любой канал — бот сам пришлёт обзор в канал результатов.",
                        inline=False)
        view = VideoPanelView(self)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="video-ayar", aliases=["video-settings"])
    @commands.has_permissions(manage_messages=True)
    async def video_ayar(self, ctx):
        """Показать настройки автоматического анализа видео."""
        await ctx.send(embed=self._video_settings_embed(ctx.guild))

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
    cog = VoiceCommands(bot)
    await bot.add_cog(cog)
    # Предзагружаем модель Whisper в фоне, чтобы первый анализ не заставлял ждать скачивание.
    if cog.whisper_available:
        try:
            bot.loop.create_task(cog._preload_whisper_model())
        except Exception as e:
            log.warning(f"Не удалось запустить предзагрузку Whisper: {e}")
    log.info("VoiceCommands загружен")
