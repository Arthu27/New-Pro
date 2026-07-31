"""
Companion Cog — Bot, belirli bir userya ara очередь kendi желание DM atar.
Сообщения samimi, motive edici, личный. Hitap: "Королева".
"""
import discord
from discord.ext import commands, tasks
import datetime
import os
import json
import random
import asyncio

# Цель user ID
COMPANION_USER_ID = 1353157554967937153

DATA_FILE = 'data/companion_state.json'

# Türkiye час UTC+3
TZ_OFFSET = datetime.timezone(datetime.timedelta(hours=3))

# День сколько message отправл (min, max)
DAILY_MIN = 1
DAILY_MAX = 3

# Сообщение отправл часов aralığı (Türkiye час)
HOUR_START = 9
HOUR_END = 23

# ─── Сообщение Кандидатыu ────────────────────────────────────────────────────────────

MESSAGES_MOTIVATION = [
    "Королева, сегодня как? Aklıma geldin, umarım день güzel geçiyordur 🌸",
    "Королева, bir что-то сказатьyeyim mi — sen düşündüğünden очень более мощный. Bunu unutma 💜",
    "Королева, bazen только devam etmek bile başlı başına bir успешно. Gurur duyuyorum senden 🌟",
    "Королева, сегодня kendine iyi baktın mı? Su içmeyi, biraz nefes almayı unutma 💙",
    "Королева, hayat bazen тяжелый gelir ama sen каждый seferinde kalkmasını biliyorsun. Bu очередь bir что-то не 🌺",
    "Королева, seni düşündüm. Umarım сегодня sana güzel bir что-то olmuştur ✨",
    "Королева, маленький adımlar da ilerlemektir. Сегодня ne kadar маленький olursa olsun bir что-то yaptıysan, bu число 🎯",
    "Королева, yorulduğunda durmak zayıflık не, akıllılıktır. Kendine Разрешение ver 🌙",
]

MESSAGES_STUDY = [
    "Королева, ders çalışırken Pomodoro tekniğini denedin mi? 25 minutes çalış, 5 minutes mola — beyin очень более iyi absorbe ediyor 📚",
    "Королева, подсказка: записывать прочитанное своими словами в 3 раза эффективнее, чем просто читать. Попробуй 🖊️",
    "Королева, sınav öncesi gece geç saate kadar работать вместо erken yat, sabah taze kafayla bak — beyin uyku очередь infoyi pekiştiriyor 🌙",
    "Королева, zor bir konuyu öğrenmenin en iyi yolu onu birine anlatmaya работать. Кто yoksa bana anlat, dinlerim 😄",
    "Королева, сегодня работа planın var mı? До en zor konudan başlarsan, geri kalanı очень более kolay gelir 💪",
    "Королева, telefonu başka комната bırakarak работа dene. Только bu bile konsantrasyonu %40 artırıyor, inanılmaz не mi? 📵",
    "Королева, каждый день только 30 minutes düzenli работать, haftada bir kez 5 часов работать очень более etkili. Tutarlılık каждый что-тоdir 🗓️",
    "Королева, bir konuyu anlamadan ezberlemek seni yorar. До 'почему böyle?' diye sor, anlayınca zaten aklında kполучает 🧠",
]

MESSAGES_SWEET = [
    "Королева, сегодня день seni düşünerek doğdu sanki ☀️",
    "Королева, sen olmasan bu вчера biraz более очередь olurdu. Gerçekten 🌸",
    "Королева, твоя улыбка заслуживает записи, она согревает людей 💛",
    "Королева, сегодня kendine bir iyilik yap — hak ediyorsun 🎀",
    "Королева, bazı insanlar комната girince hava değişir. Sen öyle birisin 🌟",
    "Королева, seni düşündüm ve gülümsedim. Причина yere iyi hissettiriyorsun 💜",
    "Королева, сегодня ne kadar harika biri olduğunu hatırlatmak желание. Все bu 🌺",
    "Королева, hayatında seni seven insanlar var — ve ben de число bu listeye 🤍",
]

MESSAGES_RANDOM = [
    "Королева, ortada hiçbir что-то yokken aklıma geldin. Как gerçekten? 💙",
    "Королева, сегодня bir что-то seni mutlu etti mi? Merak ettim 🌸",
    "Королева, şu an ne yapıyorsun acaba? Umarım güzel bir что-тоler 😊",
    "Королева, bazen только 'iyi misin?' demek gerekiyor. İyi misin? 💜",
    "Королева, сегодня kendine güldün mü? Gülmek lazım, очень lazım 😄",
    "Королева, seni düşündüm. Başka bir причина yok, только düşündüm 🌟",
    "Королева, bu gece iyi uyu. Завтра новый bir день, новый bir şans ✨",
    "Королева, сегодня маленький bir что-тоe şükrettin mi? Маленький что-тоler aslında большой 🌺",
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
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._scheduled_sends: list[float] = []  # сегодняkü planlı отправл vakitları (timestamp)
        self.companion_loop.start()

    def cog_unload(self):
        self.companion_loop.cancel()

    def _now_tr(self) -> datetime.datetime:
        return datetime.datetime.now(TZ_OFFSET)

    def _today_str(self) -> str:
        return self._now_tr().strftime('%Y-%m-%d')

    def _pick_message(self, used: list[str]) -> str:
        """Использовать messagelardan rastgele выбрать, tükenirse sıfırla"""
        all_msgs = [m for cat in ALL_CATEGORIES for m in cat]
        available = [m for m in all_msgs if m not in used]
        if not available:
            available = all_msgs  # все использовать sıfırla
        chosen = random.choice(available)
        return chosen

    def _plan_today(self, data: dict):
        """Сегодня для rastgele отправл vakitları planla"""
        now = self._now_tr()
        count = random.randint(DAILY_MIN, DAILY_MAX)
        times = []
        for _ in range(count):
            hour = random.randint(HOUR_START, HOUR_END - 1)
            minute = random.randint(0, 59)
            send_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            # История saatleri сегодня для atla
            if send_time > now:
                times.append(send_time.timestamp())
        self._scheduled_sends = sorted(times)
        data['plan'] = self._scheduled_sends
        data['sent_today'] = 0

    async def _send_dm(self, message: str):
        try:
            user = await self.bot.fetch_user(COMPANION_USER_ID)
            await user.send(message)
            print(f'[Companion] DM отправлено → {user.name}')
        except discord.Forbidden:
            print('[Companion] DM отправл — user DM\'leri закрыт.')
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

        # Отправл vakit geldi mi?
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
            await asyncio.sleep(2)  # rate limit доверие

    @companion_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()
        # Первый запуск сегодня planlanmamışsa planla
        data = _load()
        today = self._today_str()
        if data.get('last_date') != today:
            data['last_date'] = today
            self._plan_today(data)
            _save(data)
        elif data.get('plan'):
            self._scheduled_sends = data['plan']


async def setup(bot: commands.Bot):
    await bot.add_cog(Companion(bot))
