"""Etkinlik/Event система - date belirle, hatırlatma отправить"""
import discord
from discord.ext import commands, tasks
from discord import app_commands
import json, os
from datetime import datetime, timedelta

class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_events.start()

    def cog_unload(self):
        self.check_events.cancel()

    def _file(self, guild_id):
        return f'data/events_{guild_id}.json'

    def _load(self, guild_id):
        f = self._file(guild_id)
        if not os.path.exists(f): return {}
        with open(f, 'r', encoding='utf-8') as fp: return json.load(fp)

    def _save(self, guild_id, data):
        os.makedirs('data', exist_ok=True)
        with open(self._file(guild_id), 'w', encoding='utf-8') as fp:
            json.dump(data, fp, indent=2, ensure_ascii=False)

    @tasks.loop(minutes=5)
    async def check_events(self):
        now = datetime.utcnow()
        for guild in self.bot.guilds:
            events = self._load(guild.id)
            changed = False
            for eid, ev in list(events.items()):
                if ev.get('notified'): continue
                try:
                    event_time = datetime.fromisoformat(ev['time'])
                except: continue

                diff_min = (event_time - now).total_seconds() / 60

                # 60 minutes öncesi hatırlatma
                if 55 <= diff_min <= 65 and not ev.get('reminded_1h'):
                    await self._send_reminder(guild, ev, '1 saat')
                    events[eid]['reminded_1h'] = True
                    changed = True

                # 10 minutes öncesi hatırlatma
                if 5 <= diff_min <= 15 and not ev.get('reminded_10m'):
                    await self._send_reminder(guild, ev, '10 minutes')
                    events[eid]['reminded_10m'] = True
                    changed = True

                # Etkinlik başladı
                if diff_min <= 0 and not ev.get('notified'):
                    await self._send_start(guild, ev)
                    events[eid]['notified'] = True
                    changed = True

            if changed:
                self._save(guild.id, events)

    @check_events.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    async def _send_reminder(self, guild, ev, time_str):
        ch = guild.get_channel(int(ev.get('channel_id', 0)))
        if not ch: return
        embed = discord.Embed(
            title=f'⏰ Etkinlik Hatırlatması — {time_str} kaldı!',
            description=f'**{ev["title"]}**\n\n{ev.get("description", "")}',
            color=0xF39C12
        )
        embed.add_field(name='📅 Время', value=f'<t:{int(datetime.fromisoformat(ev["time"]).timestamp())}:F>')
        mention = f'<@&{ev["role_id"]}>' if ev.get('role_id') else '@everyone'
        await ch.send(content=mention, embed=embed)

    async def _send_start(self, guild, ev):
        ch = guild.get_channel(int(ev.get('channel_id', 0)))
        if not ch: return
        embed = discord.Embed(
            title=f'🎉 ETKİNLİK BAŞLADI! — {ev["title"]}',
            description=ev.get('description', ''),
            color=0x2ECC71
        )
        mention = f'<@&{ev["role_id"]}>' if ev.get('role_id') else '@everyone'
        await ch.send(content=mention, embed=embed)

    @app_commands.command(name='etkinlik-создать', description='Создать новое событие')
    @app_commands.describe(
        baslik='Etkinlik başlığı',
        aciklama='Etkinlik описание',
        date='Дата (GG/AA/YYYY)',
        saat='Время (SS:DD)',
        channel='Duyuru канал'
    )
    @app_commands.checks.has_permissions(manage_events=True)
    async def create_event(self, interaction: discord.Interaction,
                           baslik: str, aciklama: str,
                           date: str, saat: str,
                           channel: discord.TextChannel):
        try:
            dt = datetime.strptime(f'{date} {saat}', '%d/%m/%Y %H:%M')
        except ValueError:
            await interaction.response.send_message('❌ Неверный формат даты/времени! Пример: 25/12/2025 20:00', ephemeral=True)
            return

        if dt < datetime.utcnow():
            await interaction.response.send_message('❌ История bir date giremezsin!', ephemeral=True)
            return

        events = self._load(interaction.guild_id)
        eid = str(int(dt.timestamp()))
        events[eid] = {
            'id': eid, 'title': baslik, 'description': aciklama,
            'time': dt.isoformat(), 'channel_id': str(channel.id),
            'created_by': str(interaction.user.id),
            'notified': False, 'reminded_1h': False, 'reminded_10m': False
        }
        self._save(interaction.guild_id, events)

        embed = discord.Embed(title=f'📅 {baslik}', description=aciklama, color=0x3498DB)
        embed.add_field(name='⏰ Время', value=f'<t:{int(dt.timestamp())}:F>')
        embed.add_field(name='📢 Канал', value=channel.mention)
        embed.set_footer(text=f'Etkinlik ID: {eid}')
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='events', description='Показать предстоящие события')
    async def list_events(self, interaction: discord.Interaction):
        events = self._load(interaction.guild_id)
        upcoming = [(eid, ev) for eid, ev in events.items()
                    if not ev.get('notified') and
                    datetime.fromisoformat(ev['time']) > datetime.utcnow()]
        upcoming.sort(key=lambda x: x[1]['time'])

        if not upcoming:
            await interaction.response.send_message('📅 Нет предстоящих событий.', ephemeral=True)
            return

        embed = discord.Embed(title='📅 Yaklaşan Etkinlikler', color=0x3498DB)
        for eid, ev in upcoming[:10]:
            ts = int(datetime.fromisoformat(ev['time']).timestamp())
            embed.add_field(
                name=ev['title'],
                value=f'<t:{ts}:F> (<t:{ts}:R>)',
                inline=False
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='etkinlik-отмена', description='Etkinliği отмена et')
    @app_commands.checks.has_permissions(manage_events=True)
    async def cancel_event(self, interaction: discord.Interaction, etkinlik_id: str):
        events = self._load(interaction.guild_id)
        if etkinlik_id not in events:
            await interaction.response.send_message('❌ Etkinlik не найден!', ephemeral=True)
            return
        title = events[etkinlik_id]['title']
        del events[etkinlik_id]
        self._save(interaction.guild_id, events)
        await interaction.response.send_message(f'✅ **{title}** событие отменено.')

async def setup(bot):
    await bot.add_cog(Events(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
