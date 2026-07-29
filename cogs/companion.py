"""
Companion Cog — Бот, belirli bir userya ara sıra kendi isteğiyle DM atar.
Сообщениеlar samimi, motive edici, kişisel. Hitap: "Kraliçem".
"""
import discord
from discord.ext import commands, tasks
import datetime
import os
import json
import random
import asyncio

# Hedef user ID
COMPANION_USER_ID = 1353157554967937153

DATA_FILE = 'data/companion_state.json'

# Türkiye часi UTC+3
TZ_OFFSET = datetime.timezone(datetime.timedelta(hours=3))

# Günde kaç message отправитьilsin (min, max)
DAILY_MIN = 1
DAILY_MAX = 3

# Сообщение отправитьilecek час aralığı (Türkiye часi)
HOUR_START = 9
HOUR_END = 23

# ─── Сообщение Havuzu ────────────────────────────────────────────────────────────

MESSAGES_MOTIVATION = [
    "Kraliçem, buдень nasılsın? Aklıma geldin, umarım деньün güzel geçiyordur 🌸",
    "Kraliçem, bir şey söyleyeyim mi — sen düşündüğünden çok daha güçlüsün. Bunu unutma 💜",
    "Kraliçem, bazen sadece devam etmek bile başlı başına bir başarıdır. Gurur duyuyorum senden 🌟",
    "Kraliçem, buдень kendine iyi baktın mı? Su içmeyi, biraz nefes almayı unutma 💙",
    "Kraliçem, hayat bazen ağır gelir ama sen her seferinde kalkmasını biliyorsun. Bu sıradan bir şey değil 🌺",
    "Kraliçem, seni düşündüm. Umarım buдень sana güzel bir şey olmuştur ✨",
    "Kraliçem, küçük adımlar da ilerlemektir. Buдень ne kadar küçük olursa olsun bir şey yaptıysan, bu sayılır 🎯",
    "Kraliçem, yorulduğunda durmak zayıflık değil, akıllılıktır. Kendine izin ver 🌙",
]

MESSAGES_STUDY = [
    "Kraliçem, ders çalışırken Pomodoro tekniğini denedin mi? 25 minutes çalış, 5 minutes mola — beyin çok daha iyi absorbe ediyor 📚",
    "Kraliçem, bir ipucu: Okuduğunu kendi cümlelerinle not almak, sadece okumaktan 3 kat daha etkili. Dene bakalım 🖊️",
    "Kraliçem, sınav öncesi gece geç часe kadar çalışmak yerine erken yat, sabah taze kafayla bak — beyin uyku sırasında infoyi pekiştiriyor 🌙",
    "Kraliçem, zor bir konuyu öğrenmenin en iyi yolu onu birine anlatmaya çalışmak. Kimse yoksa bana anlat, dinlerim 😄",
    "Kraliçem, buдень çalışma planın var mı? Önce en zor konudan başlarsan, geri kalanı çok daha kolay gelir 💪",
    "Kraliçem, telefonu başka odaya bırakarak çalışmayı dene. Sadece bu bile konsantrasyonu %40 artırıyor, inanılmaz değil mi? 📵",
    "Kraliçem, her день sadece 30 minutes düzenli çalışmak, haftada bir kez 5 час çalışmaktan çok daha etkili. Tutarlılık her şeydir 🗓️",
    "Kraliçem, bir konuyu anlamadan ezberlemek seni yorar. Önce 'neden böyle?' diye sor, anlayınca zaten aklında kalır 🧠",
]

MESSAGES_SWEET = [
    "Kraliçem, buдень деньeş seni düşünerek doğdu sanki ☀️",
    "Kraliçem, sen olmasan bu dünya biraz daha sıradan olurdu. Gerçekten 🌸",
    "Kraliçem, gülüşün bir yere not edilmeli, çünkü insanları ısıtıyor 💛",
    "Kraliçem, buдень kendine bir iyilik yap — hak ediyorsun 🎀",
    "Kraliçem, bazı insanlar odaya girince hava değişir. Sen öyle birisin 🌟",
    "Kraliçem, seni düşündüm ve gülümsedim. Причинаsiz yere iyi hissettiriyorsun 💜",
    "Kraliçem, buдень ne kadar harika biri olduğunu hatırlatmak istedim. Все bu 🌺",
    "Kraliçem, hayatında seni seven insanlar var — ve ben de sayılırım bu listeye 🤍",
]

MESSAGES_RANDOM = [
    "Kraliçem, ortada hiçbir şey yokken aklıma geldin. Nasılsın gerçekten? 💙",
    "Kraliçem, buдень bir şey seni mutlu etti mi? Merak ettim 🌸",
    "Kraliçem, şu an ne yapıyorsun acaba? Umarım güzel bir şeyler 😊",
    "Kraliçem, bazen sadece 'iyi misin?' demek gerekiyor. İyi misin? 💜",
    "Kraliçem, buдень kendine güldün mü? Gülmek lazım, çok lazım 😄",
    "Kraliçem, seni düşündüm. Başka bir sebebi yok, sadece düşündüm 🌟",
    "Kraliçem, bu gece iyi uyu. Yarın yeni bir день, yeni bir şans ✨",
    "Kraliçem, buдень küçük bir şeye şükrettin mi? Küçük şeyler aslında büyük 🌺",
]

ALL_CATEGORIES = [
    MESSAGES_MOTIVATION,
    MESSAGES_STUDY,
    MESSAGES_SWEET,
    MESSAGES_RANDOM,
]

# ─── State ───────────────────────────────────────────────────────────────────

def _load() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'last_date': None, 'sent_today': 0, 'used_messages': []}


def _save(data: dict):
    os.makedirs('data', exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── Cog ─────────────────────────────────────────────────────────────────────

class Companion(commands.Cog):
    def __init__(self, bot: commands.Бот):
        self.bot = bot
        self._scheduled_sends: list[float] = []  # buденьkü planlı отправитьim vakitları (timestamp)
        self.companion_loop.start()

    def cog_unload(self):
        self.companion_loop.cancel()

    def _now_tr(self) -> datetime.datetime:
        return datetime.datetime.now(TZ_OFFSET)

    def _today_str(self) -> str:
        return self._now_tr().strftime('%Y-%m-%d')

    def _pick_message(self, used: list[str]) -> str:
        """Kullanılmamış messagelardan rastgele выбрать, tükenirse sıfırla"""
        all_msgs = [m for cat in ALL_CATEGORIES for m in cat]
        available = [m for m in all_msgs if m not in used]
        if not available:
            available = all_msgs  # tümü kullanıldıysa sıfırla
        chosen = random.choice(available)
        return chosen

    def _plan_today(self, data: dict):
        """Buдень için rastgele отправитьim vakitları planla"""
        now = self._now_tr()
        count = random.randint(DAILY_MIN, DAILY_MAX)
        times = []
        for _ in range(count):
            hour = random.randint(HOUR_START, HOUR_END - 1)
            minute = random.randint(0, 59)
            send_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            # Geçmiş часleri buдень için atla
            if send_time > now:
                times.append(send_time.timestamp())
        self._scheduled_sends = sorted(times)
        data['plan'] = self._scheduled_sends
        data['sent_today'] = 0

    async def _send_dm(self, message: str):
        try:
            user = await self.bot.fetch_user(COMPANION_USER_ID)
            await user.send(message)
            print(f'[Companion] DM отправитьildi → {user.name}')
        except discord.Forbidden:
            print('[Companion] DM отправитьilemedi — user DM\'leri kapalı.')
        except Exception as e:
            print(f'[Companion] Ошибка: {e}')

    @tasks.loop(minutes=5)
    async def companion_loop(self):
        data = _load()
        today = self._today_str()
        now_ts = self._now_tr().timestamp()

        # Новый день → planla
        if data.get('last_date') != today:
            data['last_date'] = today
            data['used_messages'] = data.get('used_messages', [])[-20:]  # son 20'yi tut
            self._plan_today(data)
            _save(data)
            return

        # Planlı vakitları загрузить (restart sonrası)
        if not self._scheduled_sends and data.get('plan'):
            self._scheduled_sends = data['plan']

        # Отправитьilecek vakit geldi mi?
        due = [t for t in self._scheduled_sends if t <= now_ts]
        if not due:
            return

        # Отправить
        for ts in due:
            self._scheduled_sends.remove(ts)
            msg = self._pick_message(data.get('used_messages', []))
            data.setdefault('used_messages', []).append(msg)
            data['sent_today'] = data.get('sent_today', 0) + 1
            data['plan'] = self._scheduled_sends
            _save(data)
            await self._send_dm(msg)
            await asyncio.sleep(2)  # rate limit güvenliği

    @companion_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()
        # Первый запуститьmada buдень planlanmamışsa planla
        data = _load()
        today = self._today_str()
        if data.get('last_date') != today:
            data['last_date'] = today
            self._plan_today(data)
            _save(data)
        elif data.get('plan'):
            self._scheduled_sends = data['plan']


async def setup(bot: commands.Бот):
    await bot.add_cog(Companion(bot))
