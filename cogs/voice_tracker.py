import discord
from discord.ext import commands
import json, os, time
from datetime import date

class VoiceTracker(commands.Cog):
    """Ses канал статистика voice_stats_<guild_id>.json formatında сохран."""

    def __init__(self, bot):
        self.bot = bot
        # {guild_id: {user_id: join_timestamp}}
        self.sessions = {}

    def _file(self, guild_id):
        return f'data/voice_stats_{guild_id}.json'

    def _load(self, guild_id):
        f = self._file(guild_id)
        if os.path.exists(f):
            try:
                with open(f, encoding='utf-8') as fp:
                    return json.load(fp)
            except Exception:
                pass
        return {'users': {}, 'today': {}, 'today_date': ''}

    def _save(self, guild_id, data):
        os.makedirs('data', exist_ok=True)
        with open(self._file(guild_id), 'w', encoding='utf-8') as fp:
            json.dump(data, fp, indent=2, ensure_ascii=False)

    def _record(self, guild_id: str, member: discord.Member, elapsed: int):
        """Geçen длительность сохранить"""
        if elapsed <= 0:
            return
        uid = str(member.id)
        data = self._load(guild_id)

        if uid not in data['users']:
            data['users'][uid] = {
                'name': member.display_name,
                'avatar': str(member.display_avatar.url),
                'total_seconds': 0
            }
        data['users'][uid]['total_seconds'] = data['users'][uid].get('total_seconds', 0) + elapsed
        data['users'][uid]['name'] = member.display_name
        data['users'][uid]['avatar'] = str(member.display_avatar.url)

        today = str(date.today())
        if data.get('today_date') != today:
            data['today'] = {}
            data['today_date'] = today
        data['today'][uid] = data['today'].get(uid, 0) + elapsed

        self._save(guild_id, data)

    @commands.Cog.listener()
    async def on_ready(self):
        """Bot başlayınca текущий ses channellarındaki kişileri сохранить"""
        now = time.time()
        for guild in self.bot.guilds:
            gid = str(guild.id)
            if gid not in self.sessions:
                self.sessions[gid] = {}
            for channel in guild.voice_channels:
                for member in channel.members:
                    if not member.bot:
                        uid = str(member.id)
                        # Zaten oturumu yoksa запустить
                        if uid not in self.sessions[gid]:
                            self.sessions[gid][uid] = now

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        gid = str(member.guild.id)
        uid = str(member.id)

        # Канал присоединился
        if before.channel is None and after.channel is not None:
            if gid not in self.sessions:
                self.sessions[gid] = {}
            self.sessions[gid][uid] = time.time()

        # Канал покинул
        elif before.channel is not None and after.channel is None:
            join_time = self.sessions.get(gid, {}).pop(uid, None)
            if join_time is None:
                return
            elapsed = int(time.time() - join_time)
            self._record(gid, member, elapsed)

        # Канал channela geçti — длительность сохранить, новый oturum запустить
        elif before.channel is not None and after.channel is not None and before.channel != after.channel:
            join_time = self.sessions.get(gid, {}).pop(uid, None)
            if join_time:
                elapsed = int(time.time() - join_time)
                self._record(gid, member, elapsed)
            if gid not in self.sessions:
                self.sessions[gid] = {}
            self.sessions[gid][uid] = time.time()


async def setup(bot):
    await bot.add_cog(VoiceTracker(bot))
