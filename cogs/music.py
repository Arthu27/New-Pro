"""Müzik botu - yt-dlp + ffmpeg + butonlu player"""
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
import yt_dlp

FFMPEG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ffmpeg-8.1-essentials_build', 'bin', 'ffmpeg.exe')

YTDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTS = {
    'executable': FFMPEG_PATH,
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

queues = {}        # guild_id -> list of {title, webpage_url, stream_url, requester}
repeat_mode = {}   # guild_id -> 'off' | 'song' | 'queue'
current_song = {}  # guild_id -> current item
player_messages = {}  # guild_id -> discord.Message (player embed)
_inactivity_tasks = {}


def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = []
    return queues[guild_id]


async def fetch_source(query: str):
    loop = asyncio.get_event_loop()
    with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
        try:
            info = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False)),
                timeout=20
            )
        except asyncio.TimeoutError:
            raise Exception('Aramama vakit aşımına uğradı, tekrar dene')
    if not info:
        raise Exception('результат не найдено')
    if 'entries' in info:
        entries = [e for e in info['entries'] if e]
        if not entries:
            raise Exception('результат не найдено')
        info = entries[0]
    return info['url'], info.get('title', 'Bilinmiyor'), info.get('webpage_url', '')


def _build_player_embed(guild_id: int, title: str, webpage_url: str, requester: str, paused: bool = False) -> discord.Embed:
    mode = repeat_mode.get(guild_id, 'off')
    mode_text = {'off': '🔇 Закрыт', 'song': '🔂 Şarkı', 'queue': '🔁 Очередь'}[mode]
    q = get_queue(guild_id)
    status = "⏸ Duraklatıldı" if paused else "▶️ Çalıyor"

    e = discord.Embed(
        title="🎵 Müzik Çalar",
        description=f"**[{title}]({webpage_url})**",
        color=0xdc143c
    )
    e.add_field(name="Состояние", value=status, inline=True)
    e.add_field(name="Tekrar", value=mode_text, inline=True)
    e.add_field(name="Очередь", value=f"{len(q)} песня", inline=True)
    e.set_footer(text=f"Желание: {requester}")
    return e


class MusicPlayerView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=None)
        self.guild = guild

    def _vc(self):
        return self.guild.voice_client

    async def _update_embed(self, interaction: discord.Interaction):
        item = current_song.get(self.guild.id)
        if not item:
            return
        vc = self._vc()
        paused = vc.is_paused() if vc else False
        embed = _build_player_embed(
            self.guild.id, item['title'], item['webpage_url'],
            item['requester'], paused
        )
        try:
            await interaction.message.edit(embed=embed, view=self)
        except Exception:
            pass

    @discord.ui.button(emoji="⏸", style=discord.ButtonStyle.secondary, custom_id="music_pause", row=0)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self._vc()
        if not vc:
            await interaction.response.send_message("❌ Bot ses в канале не!", ephemeral=True)
            return
        if vc.is_playing():
            vc.pause()
            button.emoji = "▶️"
        elif vc.is_paused():
            vc.resume()
            button.emoji = "⏸"
        await interaction.response.defer()
        await self._update_embed(interaction)

    @discord.ui.button(emoji="⏭", style=discord.ButtonStyle.secondary, custom_id="music_skip", row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self._vc()
        if not vc or (not vc.is_playing() and not vc.is_paused()):
            await interaction.response.send_message("❌ Сейчас ничего не воспроизводится.", ephemeral=True)
            return
        vc.stop()
        await interaction.response.defer()

    @discord.ui.button(emoji="⏹", style=discord.ButtonStyle.danger, custom_id="music_stop", row=0)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self._vc()
        if not vc:
            await interaction.response.send_message("❌ Bot ses в канале не!", ephemeral=True)
            return
        queues[self.guild.id] = []
        current_song.pop(self.guild.id, None)
        vc.stop()
        await vc.disconnect()
        await interaction.response.defer()
        try:
            e = discord.Embed(title="⏹ Müzik Durduruldu", color=0x555555)
            await interaction.message.edit(embed=e, view=None)
        except Exception:
            pass

    @discord.ui.button(emoji="🔉", style=discord.ButtonStyle.secondary, custom_id="music_vol_down", row=1)
    async def vol_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self._vc()
        if not vc or not vc.source:
            await interaction.response.send_message("❌ Сейчас ничего не воспроизводится.", ephemeral=True)
            return
        new_vol = max(0.0, vc.source.volume - 0.1)
        vc.source.volume = new_vol
        await interaction.response.send_message(f"🔉 Ses: **{int(new_vol*100)}%**", ephemeral=True)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, custom_id="music_vol_up", row=1)
    async def vol_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self._vc()
        if not vc or not vc.source:
            await interaction.response.send_message("❌ Сейчас ничего не воспроизводится.", ephemeral=True)
            return
        new_vol = min(1.0, vc.source.volume + 0.1)
        vc.source.volume = new_vol
        await interaction.response.send_message(f"🔊 Ses: **{int(new_vol*100)}%**", ephemeral=True)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="music_repeat", row=1)
    async def toggle_repeat(self, interaction: discord.Interaction, button: discord.ui.Button):
        modes = ['off', 'song', 'queue']
        current = repeat_mode.get(self.guild.id, 'off')
        next_mode = modes[(modes.index(current) + 1) % len(modes)]
        repeat_mode[self.guild.id] = next_mode
        icons = {'off': '🔇', 'song': '🔂', 'queue': '🔁'}
        button.emoji = icons[next_mode]
        await interaction.response.defer()
        await self._update_embed(interaction)

    @discord.ui.button(emoji="📋", style=discord.ButtonStyle.secondary, custom_id="music_queue", row=1)
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        q = get_queue(self.guild.id)
        if not q:
            await interaction.response.send_message("📋 Очередь пусто.", ephemeral=True)
            return
        desc = "\n".join(f"`{i+1}.` {item['title']}" for i, item in enumerate(q[:10]))
        if len(q) > 10:
            desc += f"\n*+{len(q)-10} песня более*"
        e = discord.Embed(title="📋 Müzik Kuyruğu", description=desc, color=0xdc143c)
        await interaction.response.send_message(embed=e, ephemeral=True)


async def play_next(guild: discord.Guild, channel: discord.TextChannel = None):
    q = get_queue(guild.id)
    vc = guild.voice_client
    if not vc:
        return

    mode = repeat_mode.get(guild.id, 'off')

    if mode == 'song' and guild.id in current_song:
        item = current_song[guild.id]
        try:
            stream_url, _, _ = await fetch_source(item.get('webpage_url') or item['title'])
            item = dict(item)
            item['stream_url'] = stream_url
        except Exception:
            pass
    elif q:
        item = q.pop(0)
        if mode == 'queue':
            q.append(dict(item))
        current_song[guild.id] = item
    else:
        current_song.pop(guild.id, None)
        # Player messageını обновить
        msg = player_messages.pop(guild.id, None)
        if msg:
            try:
                e = discord.Embed(title="✅ Очередь завершена", description="Все песни воспроизведены.", color=0x2ecc71)
                asyncio.run_coroutine_threadsafe(msg.edit(embed=e, view=None), guild._state.loop)
            except Exception:
                pass
        return

    try:
        source = discord.FFmpegPCMAudio(item['stream_url'], **FFMPEG_OPTS)
        source = discord.PCMVolumeTransformer(source, volume=0.5)

        def after(err):
            if err:
                print(f"[Music] Oynatma Ошибки: {err}")
            asyncio.run_coroutine_threadsafe(play_next(guild, channel), guild._state.loop)

        vc.play(source, after=after)

        # Player embed'ini обновить или отправить
        embed = _build_player_embed(guild.id, item['title'], item['webpage_url'], item['requester'])
        view = MusicPlayerView(guild)

        existing_msg = player_messages.get(guild.id)
        if existing_msg:
            try:
                asyncio.run_coroutine_threadsafe(
                    existing_msg.edit(embed=embed, view=view), guild._state.loop
                )
            except Exception:
                player_messages.pop(guild.id, None)
        elif channel:
            async def _send():
                msg = await channel.send(embed=embed, view=view)
                player_messages[guild.id] = msg
            asyncio.run_coroutine_threadsafe(_send(), guild._state.loop)

    except Exception as ex:
        print(f"Müzik Ошибки: {ex}")
        asyncio.run_coroutine_threadsafe(play_next(guild, channel), guild._state.loop)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="play", description="Воспроизведение музыки с YouTube")
    async def cal(self, interaction: discord.Interaction, sorgu: str):
        if not interaction.user.voice:
            await interaction.response.send_message("❌ До bir ses в канал gir!", ephemeral=True)
            return

        await interaction.response.defer()

        vc = interaction.guild.voice_client
        if vc and not vc.is_connected():
            vc = None
        if not vc:
            vc = await interaction.user.voice.channel.connect()
        elif vc.channel != interaction.user.voice.channel:
            await vc.move_to(interaction.user.voice.channel)

        try:
            stream_url, title, webpage_url = await fetch_source(sorgu)
        except Exception as e:
            await interaction.followup.send(f"❌ {e}")
            return

        item = {
            'stream_url': stream_url,
            'title': title,
            'webpage_url': webpage_url,
            'requester': interaction.user.display_name
        }
        q = get_queue(interaction.guild.id)

        if vc.is_playing() or vc.is_paused():
            q.append(item)
            e = discord.Embed(
                title="📋 Kuyruğa Добавлено",
                description=f"**[{title}]({webpage_url})**\nSıra: #{len(q)}",
                color=0x3498db
            )
            e.set_footer(text=f"Желание: {interaction.user.display_name}")
            await interaction.followup.send(embed=e)
            # Текущий player embed'ini обновить
            msg = player_messages.get(interaction.guild.id)
            if msg:
                item_now = current_song.get(interaction.guild.id)
                if item_now:
                    embed = _build_player_embed(
                        interaction.guild.id, item_now['title'],
                        item_now['webpage_url'], item_now['requester'],
                        vc.is_paused()
                    )
                    try:
                        await msg.edit(embed=embed, view=MusicPlayerView(interaction.guild))
                    except Exception:
                        pass
        else:
            q.insert(0, item)
            await play_next(interaction.guild, interaction.channel)
            await interaction.followup.send("▶️ Запуск...", delete_after=3)

    @app_commands.command(name="leave", description="Отключить бота от голосового канала")
    async def ayril(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if not vc:
            await interaction.response.send_message("❌ Bot ses в канале не!", ephemeral=True)
            return
        queues[interaction.guild.id] = []
        current_song.pop(interaction.guild.id, None)
        player_messages.pop(interaction.guild.id, None)
        _inactivity_tasks.pop(interaction.guild.id, None)
        await vc.disconnect()
        await interaction.response.send_message("👋 Покинул.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        guild = member.guild
        vc = guild.voice_client
        if not vc:
            return
        if not vc.is_playing() and not vc.is_paused():
            return
        if before.channel and before.channel == vc.channel:
            humans = [m for m in vc.channel.members if not m.bot]
            if not humans:
                queues.pop(guild.id, None)
                current_song.pop(guild.id, None)
                player_messages.pop(guild.id, None)
                await vc.disconnect()


async def setup(bot):
    await bot.add_cog(Music(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788), discord.Object(id=1498837105915330562)])
