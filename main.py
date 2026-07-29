# ── Otomatik Bağımlılık Kurulumu ─────────────────────────────────────────────
import sys
import os
import subprocess

def _install_requirements():
    """requirements.txt'deki eksik paketleri otomatik kur"""
    req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'requirements.txt')
    if not os.path.exists(req_file):
        print("[WARN] requirements.txt bulunamadi, bagimlilik kontroleu atlaniyor")
        return
    
    # requirements.txt'yi oku
    with open(req_file, 'r', encoding='utf-8') as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    # Paket adi -> import adi eslesmesi
    _import_map = {
        'discord.py': 'discord',
        'python-dotenv': 'dotenv',
        'discord-ext-voice-recv': 'voice_recv',
        'flask-session': 'flask_session',
        'duckduckgo-search': 'duckduckgo_search',
        'deep-translator': 'deep_translator',
        'edge-tts': 'edge_tts',
        'faster-whisper': 'faster_whisper',
        'yt-dlp': 'yt_dlp',
        'PyNaCl': 'nacl',
    }
    
    # Eksik paketleri tespit et
    missing = []
    for req in requirements:
        pkg_name = req.split('>=')[0].split('==')[0].split('<')[0].split('>')[0].split('~=')[0].strip()
        import_name = _import_map.get(pkg_name, pkg_name.replace('-', '_'))
        try:
            __import__(import_name)
        except ImportError:
            missing.append(req)
    
    # Eksik paketleri kur
    if missing:
        print(f"[INSTALL] {len(missing)} eksik paket kuruluyor...")
        for pkg in missing:
            print(f"  -> {pkg}")
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--pre'] + missing)
            print("[INSTALL] Tum paketler kuruldu!")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Paket kurulumu basarisiz: {e}")
            print(f"[INFO] Manuel kurulum: pip install -r requirements.txt")
            sys.exit(1)
    else:
        print("[OK] Tum bagimliliklar mevcut")

# Первый çalıştırmada otomatik kur
_install_requirements()

import discord
import warnings
warnings.filterwarnings('ignore', category=ResourceWarninging)
from discord.ext import commands
from dotenv import load_dotenv
import threading
import subprocess
import re
import asyncio
import urllib.request
import urllib.error
import time
import signal
import atexit

load_dotenv()

# Startup fix: duplicate endpoint'leri clear
import subprocess as _sp, sys as _sys
_fix = os.path.join(os.path.dirname(__file__), 'fix_dup.py')
if os.path.exists(_fix):
    _sp.run([_sys.executable, _fix], capture_output=True)

intents = discord.Intents.all()
бот = commands.Бот(command_prefix="!", intents=intents, help_command=None)

ALERT_ROLE_ID = None  # Панельden настроитьnacak

# ── Cleanup functions ───────────────────────────────────────────────────────
def cleanup_on_exit():
    """Бот закрытьılırken temizlik действиеleri"""
    try:
        print("[CLEANUP] Бот закрытьiliyor...")
        # Голос bağlantılarını закрыть
        if hasattr(bot, 'voice_clients'):
            for vc in bot.voice_clients:
                try:
                    asyncio.run_coroutine_threadsafe(vc.disconnect(), bot.loop)
                except Exception:
                    pass
        # Бот'u закрыть
        if not bot.is_closed():
            asyncio.run_coroutine_threadsafe(bot.close(), bot.loop)
    except Exception as e:
        print(f"[CLEANUP] Temizlik ошибкаsı: {e}")

def signal_handler(signum, frame):
    """Signal handler for graceful shutdown"""
    print(f"[SIGNAL] Signal {signum} alindi, temizlik yapiliyor...")
    cleanup_on_exit()
    sys.exit(0)

# Signal handler'ları сохранить
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup_on_exit)

# ── Панель link отправить ────────────────────────────────────────────────────────
async def send_panel_link(url):
    import json as _json
    tokens_file = os.path.join(os.path.dirname(__file__), 'data', 'tokens.json')
    owner_token = None
    if os.path.exists(tokens_file):
        with open(tokens_file, 'r', encoding='utf-8') as _f:
            _tokens = _json.load(_f)
        for t, v in _tokens.items():
            if v.get('username') == 'owner':
                owner_token = t
                break

    panel_url = url

    for guild in bot.guilds:
        try:
            # Küçük harf ile ara — Discord channel имяleri küçük harf
            panel_ch = discord.utils.get(guild.text_channels, name="aether-panel")
            if not panel_ch:
                # Старый имяli channelları da kontrole et
                for old_name in ["panel-link", "aether-panel", "Aether-panel"]:
                    panel_ch = discord.utils.get(guild.text_channels, name=old_name)
                    if panel_ch:
                        await panel_ch.edit(name="aether-panel")
                        break
                if not panel_ch:
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    }
                    role = guild.get_role(ALERT_ROLE_ID) if ALERT_ROLE_ID else None
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(read_messages=True)
                    panel_ch = await guild.create_text_channel("aether-panel", overwrites=overwrites)
                    print(f"[INFO] aether-panel channeli olusturuldu: {guild.name}")
            async for msg in panel_ch.history(limit=10):
                if msg.author == bot.user:
                    await msg.delete()
            embed = discord.Embed(
                color=0xc8922a,
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(
                name="Aether — Панель управления",
                icon_url=guild.icon.url if guild.icon else None
            )
            embed.description = f"[**› Войти в panel**]({panel_url})"
            embed.set_image(url="https://static.klipy.com/ii/71b2873e478b9d8d0482ea3ec777ba7f/15/36/51ALUZhO.gif")
            embed.add_field(
                name="🏰  Сервер",
                value=f"```{guild.name}```",
                inline=True
            )
            embed.add_field(
                name="👥  Участники",
                value=f"```{guild.member_count}```",
                inline=True
            )
            embed.add_field(
                name="🔐  Доступ",
                value="```Автоматически по роли Discord```",
                inline=False
            )
            embed.set_footer(
                text="Aether Панель • Обновляется при каждом запуске",
                icon_url=guild.icon.url if guild.icon else None
            )
            await panel_ch.send(embed=embed)
            print(f"[OK] Панель linki {guild.name} serversuna gonderildi")
        except Exception as e:
            print(f"[ERR] Панель linki gonderilemedi ({guild.name}): {e}")

# ── Cloudflare tüneli ────────────────────────────────────────────────────────
def _is_tunnel_alive(url):
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            status = getattr(resp, "status", 200)
            body = resp.read(512).decode("utf-8", errors="ignore")
            if status >= 500:
                return False
            if "The origin has been unregistered from Argo Tunnel" in body:
                return False
            return True
    except urllib.error.HTTPError as e:
        # 302/401 gibi cevaplar panel icin normal olabilir, 5xx ise olumsuz
        return e.code < 500
    except Exception:
        return False


def _write_and_broadcast_tunnel_url(url):
    _tunnel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tunnel_url.txt")
    with open(_tunnel_path, "w", encoding="utf-8") as f:
        f.write(url)
    asyncio.run_coroutine_threadsafe(send_panel_link(url), bot.loop)


def start_tunnel():
    import time
    base_dir = os.path.dirname(__file__)
    cf_path = os.path.join(base_dir, "cloudflared.exe")
    if not os.path.exists(cf_path):
        cf_path = os.path.join(base_dir, "cloudflared_new.exe")
    if not os.path.exists(cf_path):
        print("⚠️ cloudflared.exe bulunamadı")
        return
    while True:
        try:
            print("[INFO] Cloudflare tuneli baslatiliyor...")
            proc = subprocess.Popen(
                [cf_path, "tunnel", "--no-autoupdate", "--protocol", "http2", "--url", "http://localhost:5001"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="ignore"
            )
            for line in proc.stdout:
                m = re.search(r'https://[a-z0-9\-]+\.trycloudflare\.com', line)
                if m:
                    url = m.group(0)
                    print(f"[LINK] Herkese acik link: {url}")
                    # URL'yi dosyaya yaz
                    _tunnel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tunnel_url.txt")
                    with open(_tunnel_path, "w", encoding="utf-8") as f:
                        f.write(url)
                    # Бот hazır olana kadar badd, sonra отправить
                    def _send_when_ready(u):
                        import time as _t
                        for _ in range(30):  # max 30 saniye badd
                            try:
                                if bot.is_ready():
                                    asyncio.run_coroutine_threadsafe(send_panel_link(u), bot.loop).result(timeout=15)
                                    return
                            except Exception as e:
                                print(f"[ERR] Панель link отправитьilemedi: {e}")
                                return
                            _t.sleep(1)
                    threading.Thread(target=_send_when_ready, args=(url,), daemon=True).start()
            proc.wait()
            print("[WARN] Tunel dustu, 5 saniye sonra yeniden baglaniyor...")
            time.sleep(5)
        except Exception as e:
            print(f"[ERR] Tunel ошибкаsi: {e}")
            time.sleep(5)

# ── on_ready ─────────────────────────────────────────────────────────────────
_synced = False
VOICE_CHANNEL_ID = None  # Панельden настроитьnacak

async def _monitor_voice():
    """Голос bağlantısını canlı tut — düştüğünde bağlan, her 4 dakikada silence çal."""
    await бот.wait_until_ready()
    await asyncio.sleep(10)
    last_ping = 0
    while not bot.is_closed():
        await asyncio.sleep(30)
        channel = bot.get_channel(VOICE_CHANNEL_ID) if VOICE_CHANNEL_ID else None
        if not channel or not isinstance(channel, discord.VoiceChannel):
            continue
        vc = discord.utils.get(bot.voice_clients, guild=channel.guild)
        
        # Bağlı değilse bağlan
        if not vc or not vc.is_connected():
            try:
                vc = await channel.connect(self_deaf=False)
                last_ping = time.time()
            except Exception:
                pass
        # Bağlıysa ve 4 dakika geçtiyse silence ping at
        elif time.time() - last_ping > 240:
            try:
                if not vc.is_playing():
                    # 1 saniyelik голосsiz голос
                    import io
                    silence = io.BytesIO(b'\x00' * 3840)  # 20ms PCM silence
                    source = discord.PCMAudio(silence)
                    vc.play(source)
                last_ping = time.time()
            except Exception:
                pass

@бот.event
async def on_ready():
    global _synced
    if not _synced:
        # Guild-specific sync — anında активен olur
        for guild in bot.guilds:
            try:
                await bot.tree.sync(guild=guild)
                print(f'[SYNC] Slash командаlar sync edildi: {guild.name}')
            except Exception as e:
                print(f'[SYNC] Ошибка {guild.name}: {e}')
        await bot.tree.sync()  # Global sync de yap
        _synced = True
        bot.loop.create_task(_monitor_voice())
    print(f"[OK] {bot.user} активен | {len(bot.guilds)} server")

    # Бот config'den status/activity oku — HER on_ready'de çalışır
    import json as _j
    _cfg_file = 'data/бот_config.json'
    _status = discord.Status.idle
    _activity_type = discord.ActivityType.listening
    _activity_text = '.gg/Aether'
    if os.path.exists(_cfg_file):
        try:
            with open(_cfg_file, encoding='utf-8') as _f:
                _cfg = _j.load(_f)
            _status_map = {'online': discord.Status.online, 'idle': discord.Status.idle, 'dnd': discord.Status.dnd, 'invisible': discord.Status.invisible}
            _type_map = {'listening': discord.ActivityType.listening, 'playing': discord.ActivityType.playing, 'watching': discord.ActivityType.watching, 'competing': discord.ActivityType.competing}
            _status = _status_map.get(_cfg.get('status', 'idle'), discord.Status.idle)
            _activity_type = _type_map.get(_cfg.get('activity_type', 'listening'), discord.ActivityType.listening)
            _activity_text = _cfg.get('activity_text', '.gg/Aether')
        except Exception:
            pass

    await bot.change_presence(
        activity=discord.Activity(type=_activity_type, name=_activity_text),
        status=_status
    )
    print(f"[OK] Status: {_status} | Activity: {_activity_text}")

    # Голос channelına bağlan (sadece ilk başlangıçta)
    channel = bot.get_channel(VOICE_CHANNEL_ID) if VOICE_CHANNEL_ID else None
    if channel and isinstance(channel, discord.VoiceChannel):
        vc = discord.utils.get(bot.voice_clients, guild=channel.guild)
        if not vc:
            try:
                await channel.connect(self_deaf=False)
                print(f"[OK] Голос channelına bağlandı: {channel.name}")
            except Exception as e:
                print(f"[ERR] Голос bağlanma ошибкаsı: {e}")

    # Бот instance'ı обновить
    from web.app import set_bot_instance
    set_bot_instance(bot)

    # Панель channelını kontrole et — tunnel URL varsa отправить (sadece bir kez)
    _tunnel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tunnel_url.txt")
    if not getattr(bot, '_panel_link_sent', False) and os.path.exists(_tunnel_path):
        try:
            with open(_tunnel_path, "r", encoding="utf-8") as _f:
                _url = _f.read().strip()
            if _url:
                await send_panel_link(_url)
                бот._panel_link_sent = True
        except Exception as _e:
            print(f"[ERR] Панель link отправитьilemedi: {_e}")

# ── Cog yükle ────────────────────────────────────────────────────────────────
async def load_cogs():
    SKIP_COGS = {"embed_utils.py", "__init__.py"}
    cog_files = sorted([f for f in os.listdir("./cogs") if f.endswith(".py") and f not in SKIP_COGS])
    for filename in cog_files:
        ext = f"cogs.{filename[:-3]}"
        print(f"[LOAD] Yukleniyor: {filename}")
        try:
            await asyncio.wait_for(bot.load_extension(ext), timeout=20)
            print(f"[LOAD] Yuklendi: {filename}")
        except asyncio.МутError:
            print(f"[ERR] Cog timeout (20s): {filename}")
        except Exception as e:
            import traceback
            print(f"[ERR] Cog yukleme ошибкаsi ({filename}): {e}")
            traceback.print_exc()

# ── Main ─────────────────────────────────────────────────────────────────────
async def main():
    # Web paneli запустить (bot başlamadan önce - sadece bir kez)
    from web.app import app, set_bot_instance
    set_bot_instance(bot)
    # Werkzeug terminal colorlerini закрыть
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)
    threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False),
        daemon=True
    ).start()
    print("[WEB] Web panel: http://localhost:5001")

    # Cloudflare tüneli запустить (Flask'ın ayağa kalkması için 3 sn badd)
    def delayed_tunnel():
        import time
        time.sleep(3)
        start_tunnel()
    threading.Thread(target=delayed_tunnel, daemon=True).start()

    print("[BOT] Baslatiliyor... (cog yukleme -> Discord giris)")
    async with bot:
        print("[BOT] Cog'lar yukleniyor...")
        await load_cogs()
        while True:
            try:
                print("[BOT] Discord'a baglaniliyor...")
                await bot.start(os.getenv("TOKEN"))
            except Exception as e:
                # Ağ/Discord erişimi anlık düşerse panel de ayakta kalsın diye
                # ботu öldürmüyoruz; kısa baddyip tekrar deniyoruz.
                print(f"[ERR] Бот baslatma ошибкаsi: {e}")
                await asyncio.sleep(10)

asyncio.run(main())
