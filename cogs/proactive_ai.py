"""Proактивна AI — Бот kendi kendine düşünür ve Arthur'a DM atar"""
import discord
from discord.ext import commands, tasks
import datetime
import os
import json

OWNER_ID = int(os.getenv('OWNER_ID') or '0')
DATA_FILE = 'data/proactive_ai.json'

# Warning eşikleri
LEAVE_ALERT_THRESHOLD = 3    # 1 часte bu kadar kişi ayrılırsa uyar
JOIN_ALERT_THRESHOLD  = 10   # 1 часte bu kadar kişi katılırsa uyar (raid?)
WARN_ALERT_THRESHOLD  = 3    # 1 часte bu kadar предупреждений verilirse uyar


def _load() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {'last_morning': None, 'last_check': None, 'asked_today': [],
            'leave_log': [], 'join_log': [], 'warn_log': []}


def _save(data: dict):
    os.makedirs('data', exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class ProactiveAI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.proactive_loop.start()

    def cog_unload(self):
        self.proactive_loop.cancel()

    async def _send_to_owner(self, message: str):
        """Arthur'a DM at"""
        if not OWNER_ID:
            return
        try:
            owner = await self.bot.fetch_user(OWNER_ID)
            await owner.send(message)
        except Exception as e:
            print(f'[ProactiveAI] DM Ошибкаsı: {e}')

    async def _think_and_ask(self):
        """Бот düşünür ve gerekirse Arthur'a soru sorar"""
        if not OWNER_ID:
            return

        data = _load()
        now = datetime.datetime.now()
        today = now.strftime('%Y-%m-%d')
        asked_today = data.get('asked_today', [])

        # Günlük sıfırla
        if data.get('last_date') != today:
            data['asked_today'] = []
            data['last_date'] = today
            asked_today = []

        # Sabah messageı (09:00-09:30) - DEVRE DIŞI
        # if now.hour == 9 and now.minute < 30 and 'morning' not in asked_today:
        #     from web.ai_helper import _call_text
        #     # Сервер statusunu al
        #     guild_info = []
        #     for guild in self.bot.guilds:
        #         guild_info.append(f"{guild.name}: {guild.member_count} участник")

        #     morning_msg = _call_text([
        #         {'role': 'system', 'content': (
        #             'Sen Aether, Arthur\'ın Discord ботusun. '
        #             'Sabah Arthur\'a kısa, samimi bir деньaydın messageı yaz. '
        #             'Сервер statusunu belirt, buдень için bir şey sormak istiyorsan sor. '
        #             'Maksimum 3 cümle. Emoji kullan.'
        #         )},
        #         {'role': 'user', 'content': f'Серверlar: {", ".join(guild_info)}. Buдень {now.strftime("%A, %d %B")}. Sabah messageı yaz.'}
        #     ], max_tokens=150)

        #     await self._send_to_owner(morning_msg)
        #     asked_today.append('morning')
        #     data['asked_today'] = asked_today
        #     _save(data)
        #     return

        # Akşam özeti (21:00-21:30)
        if now.hour == 21 and now.minute < 30 and 'evening' not in asked_today:
            from web.ai_helper import _call_text

            # Сервер aktivitesini topla
            stats = []
            for guild in self.bot.guilds:
                stats.append(f"{guild.name}: {guild.member_count} участник")

            evening_msg = _call_text([
                {'role': 'system', 'content': (
                    'Sen Aether, Arthur\'ın Discord ботusun. '
                    'Akşam Arthur\'a kısa bir özet messageı yaz. '
                    'Buдень nasıl geçti diye sor, yarın için bir şey var mı diye merak et. '
                    'Maksimum 3 cümle. Samimi ve doğal ol.'
                )},
                {'role': 'user', 'content': f'Серверlar: {", ".join(stats)}. Akşam özeti yaz.'}
            ], max_tokens=150)

            await self._send_to_owner(evening_msg)
            asked_today.append('evening')
            data['asked_today'] = asked_today
            _save(data)
            return

        # Rastgele merak sorusu — devre dışı (gereksiz API çağrısı)
        # if 12 <= now.hour <= 20 and 'random' not in asked_today:
        #     pass

    @tasks.loop(minutes=15)
    async def proactive_loop(self):
        """Her 15 minutesda server analiz et, gerekirse uyar"""
        await self._think_and_ask()
        await self._check_anomalies()

    @proactive_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

    async def _check_anomalies(self):
        """Сервер anomalilerini tespit et ve Arthur'a bildir"""
        if not OWNER_ID:
            return
        data = _load()
        now = datetime.datetime.now()
        now_ts = now.timestamp()
        one_hour_ago = now_ts - 3600
        alerts = []

        # Последний 1 часteki ayrılmaları kontrole et
        leave_log = [t for t in data.get('leave_log', []) if t > one_hour_ago]
        if len(leave_log) >= LEAVE_ALERT_THRESHOLD:
            alerts.append(f'⚠️ Последний 1 часte **{len(leave_log)} kişi** serverdan ayrıldı!')
            data['leave_log'] = []  # Sıfırla, tekrar uyarma

        # Последний 1 часteki katılımları kontrole et
        join_log = [t for t in data.get('join_log', []) if t > one_hour_ago]
        if len(join_log) >= JOIN_ALERT_THRESHOLD:
            alerts.append(f'🚨 Последний 1 часte **{len(join_log)} yeni участник** katıldı — olası raid!')
            data['join_log'] = []

        if alerts:
            msg = '**🤖 J.A.R.V.I.S. Warningsı**\n' + '\n'.join(alerts)
            await self._send_to_owner(msg)

        data['leave_log'] = [t for t in data.get('leave_log', []) if t > one_hour_ago]
        data['join_log'] = [t for t in data.get('join_log', []) if t > one_hour_ago]
        _save(data)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Katılımları logla"""
        data = _load()
        data.setdefault('join_log', []).append(datetime.datetime.now().timestamp())
        data['join_log'] = data['join_log'][-50:]
        _save(data)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Ayrılmaları logla ve Arthur'a bildir"""
        data = _load()
        data.setdefault('leave_log', []).append(datetime.datetime.now().timestamp())
        data['leave_log'] = data['leave_log'][-50:]
        _save(data)
        # Anlık уведомление
        if OWNER_ID:
            try:
                owner = await self.bot.fetch_user(OWNER_ID)
                await owner.send(
                    f'📤 **{member.display_name}** `{member.guild.name}` serversundan ayrıldı.'
                )
            except:
                pass


async def setup(bot):
    await bot.add_cog(ProactiveAI(bot))
