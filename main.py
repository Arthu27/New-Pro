# Автоматически Bağımlılık Kurulumu 
import sys
import os
import subprocess

def _install_requirements():
    """requirements.txt'deki eksik paketleri автоматически kur"""
    req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'requirements.txt')
    if not os.path.exists(req_file):
        print("[WARN] requirements.txt не найдено, bagimlilik контроль atlaniyor")
        return
    
    # requirements.txt'yi oku
    with open(req_file, 'r', encoding='utf-8') as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    # Paket имя -> import имя eslesmesi
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
    
    # Eksik paketleri определить
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
            print(f" -> {pkg}")
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--pre'] + missing)
            print("[INSTALL] Tum paketler kuruldu!")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Paket kurulumu basarisiz: {e}")
            print(f"[INFO] Manuel установка: pip install -r requirements.txt")
            sys.exit(1)
    else:
        print("[OK] Tum bagimliliklar текущий")

# Ilk çalıştırmada автоматически kur
_install_requirements()

import discord
import warnings
warnings.filterwarnings('ignore', category=ResourceWarning)
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

# Централизованная конфигурация и логирование 
from config import Config
from logger import setup_logger, get_logger

Config.ensure_dirs()
log = setup_logger("bot", Config.LOG_FILE, Config.LOG_LEVEL)

# Startup fix: duplicate endpoint'leri clear
import subprocess as _sp, sys as _sys
_fix = os.path.join(os.path.dirname(__file__), 'fix_dup.py')
if os.path.exists(_fix):
    _sp.run([_sys.executable, _fix], capture_output=True)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=Config.COMMAND_PREFIX, intents=intents, help_command=None)

ALERT_ROLE_ID = None  # Panelden настройк

# Web server (gunicorn subprocess) 
_web_server_proc = None
_gunicorn_available = None  # cache: gunicorn kurulu mu?


def _have_gunicorn():
    """gunicorn kurulu mu, sh'ye gerek var mi? subprocess ucuz bir проверить."""
    global _gunicorn_available
    if _gunicorn_available is not None:
        return _gunicorn_available
    try:
        subprocess.run(
            [sys.executable, '-m', 'gunicorn', '--version'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
            timeout=5,
        )
        _gunicorn_available = True
    except Exception:
        _gunicorn_available = False
    return _gunicorn_available


def _start_web_server(app):
    """Gunicorn subprocess baslat. Calismazsa werkzeug fallback."""
    global _web_server_proc
    if _have_gunicorn():
        try:
            cmd = [
                sys.executable, '-m', 'gunicorn',
                '--config', 'web/gunicorn_conf.py',
                'web.wsgi:application',
            ]
            _web_server_proc = subprocess.Popen(
                cmd,
                stdout=sys.stdout, stderr=subprocess.STDOUT,
                # bot kapanirsa web de kapansin (process group)
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None,
            )
            print(f"[WEB] Gunicorn baslatildi (pid={_web_server_proc.pid})")
            return
        except Exception as e:
            print(f"[WEB] Gunicorn baslatilamadi, werkzeug fallback: {e}")

    # Fallback: werkzeug development server (tek thread)
    import logging
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False),
        daemon=True
    ).start()
    print("[WEB] Werkzeug (fallback) baslatildi")


def _stop_web_server():
    """Web server'i kibarca закрыть."""
    global _web_server_proc
    if _web_server_proc and _web_server_proc.poll() is None:
        try:
            _web_server_proc.terminate()
            try:
                _web_server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _web_server_proc.kill()
        except Exception as e:
            print(f"[WEB] Kapatma hatasi: {e}")
        _web_server_proc = None


# Cleanup functions 
def cleanup_on_exit():
    """Bot закрыт temizlik действия"""
    try:
        print("[CLEANUP] Bot закрыт...")
        # Web server'i закрыть
        _stop_web_server()
        # Голос ссылки закрыть
        if hasattr(bot, 'voice_clients'):
            for vc in bot.voice_clients:
                try:
                    asyncio.run_coroutine_threadsafe(vc.disconnect(), bot.loop)
                except Exception:
                    pass
        # Bot'u закрыть
        if not bot.is_closed():
            asyncio.run_coroutine_threadsafe(bot.close(), bot.loop)
    except Exception as e:
        print(f"[CLEANUP] Temizlik ошибки: {e}")

def signal_handler(signum, frame):
    """Signal handler for graceful shutdown"""
    print(f"[SIGNAL] Signal {signum} alindi, temizlik yapiliyor...")
    cleanup_on_exit()
    sys.exit(0)

# Signal handler'ları сохранить
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup_on_exit)

# Panel link отправить 
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
            # Маленький harf с ara — Discord channel isimleri маленький harf
            panel_ch = discord.utils.get(guild.text_channels, name="aether-panel")
            if not panel_ch:
                # Старый isimli channelları da контроль et
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
                    print(f"[INFO] aether-panel канал olusturuldu: {guild.name}")
            async for msg in panel_ch.history(limit=10):
                if msg.author == bot.user:
                    await msg.delete()
            embed = discord.Embed(
                color=0xc8922a,
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(
                name="Aether — Panel управление",
                icon_url=guild.icon.url if guild.icon else None
            )
            embed.description = f"[**› Вход yap в panel**]({panel_url})"
            embed.set_image(url="https://static.klipy.com/ii/71b2873e478b9d8d0482ea3ec777ba7f/15/36/51ALUZhO.gif")
            embed.add_field(
                name=" Сервер",
                value=f"```{guild.name}```",
                inline=True
            )
            embed.add_field(
                name=" Участники",
                value=f"```{guild.member_count}```",
                inline=True
            )
            embed.add_field(
                name=" Erişim",
                value="```Автоматически как по роли Discord```",
                inline=False
            )
            embed.set_footer(
                text="Aether Panel • Обновляется при каждом запуске",
                icon_url=guild.icon.url if guild.icon else None
            )
            await panel_ch.send(embed=embed)
            print(f"[OK] Panel linki {guild.name} сервер gonderildi")
        except Exception as e:
            print(f"[ERR] Panel linki gonderilemedi ({guild.name}): {e}")

# Cloudflare tüneli 
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
        # 302/401 как cevaplar panel icin normal olabilir, 5xx ise olumsuz
        return e.code < 500
    except Exception:
        return False


def _write_and_broadcast_tunnel_url(url):
    _tunnel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tunnel_url.txt")
    with open(_tunnel_path, "w", encoding="utf-8") as f:
        f.write(url)
    asyncio.run_coroutine_threadsafe(send_panel_link(url), bot.loop)


def _get_cloudflared_binary():
    import shutil, platform, urllib.request, struct
    base_dir = os.path.dirname(os.path.abspath(__file__))
    is_win = platform.system().lower() == "windows"

    def is_valid_exe(path):
        """Win32 PE dosya mı проверить et (minimum 5MB, MZ magic)."""
        if not os.path.exists(path):
            return False
        if os.path.getsize(path) < 5 * 1024 * 1024:  # 5MB minimum
            return False
        try:
            with open(path, 'rb') as f:
                magic = f.read(2)
                if magic != b'MZ':  # PE/EXE magic
                    return False
            return True
        except Exception:
            return False

    for name in ["cloudflared.exe", "cloudflared_new.exe", "cloudflared"]:
        p = os.path.join(base_dir, name)
        if is_valid_exe(p):
            return p
        elif os.path.exists(p):
            # Bozuk dosya, удалить ki yeniden indirilsin
            try: os.remove(p)
            except: pass

    sys_cf = shutil.which("cloudflared") or shutil.which("cloudflared.exe")
    if sys_cf and is_valid_exe(sys_cf):
        return sys_cf

    # Env ile tunnel tamamen kapatilabilir
    if os.getenv('DISABLE_TUNNEL', '0') == '1':
        print("[CLOUDFLARE] DISABLE_TUNNEL=1, tunnel atlandi")
        return None

    try:
        print("[CLOUDFLARE] Исполняемый файл cloudflared не найден. Начинаем автоматическую загрузку...")
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" if is_win else "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
        dest_name = "cloudflared.exe" if is_win else "cloudflared"
        dest_path = os.path.join(base_dir, dest_name)
        urllib.request.urlretrieve(url, dest_path)
        if not is_win:
            os.chmod(dest_path, 0o755)
        if is_valid_exe(dest_path):
            print(f"[CLOUDFLARE] Успешно загружен cloudflared в: {dest_path}")
            return dest_path
        else:
            print(f"[CLOUDFLARE] Загруженный файл невалиден (размер/формат). Удален: {dest_path}")
            try: os.remove(dest_path)
            except: pass
            return None
    except Exception as _e:
        print(f"[CLOUDFLARE] Ошибка автоматической загрузки cloudflared: {_e}")
        return None

def start_tunnel():
    import time
    # Env ile kapatilabilir
    if os.getenv('DISABLE_TUNNEL', '0') == '1':
        print("[CLOUDFLARE] DISABLE_TUNNEL=1, tunnel baslatilmiyor")
        return

    cf_path = _get_cloudflared_binary()
    if not cf_path:
        print(" Не удалось найти или загрузить cloudflared. Туннель Cloudflare отключен.")
        return

    protocols = ["http2", "quic", "auto"]
    proto_idx = 0
    fail_count = 0
    MAX_FAILS = 3
    while fail_count < MAX_FAILS:
        try:
            proto = protocols[proto_idx % len(protocols)]
            print(f"[INFO] Запуск туннеля Cloudflare (протокол: {proto})...")
            cmd = [cf_path, "tunnel", "--no-autoupdate"]
            if proto != "auto":
                cmd.extend(["--protocol", proto])
            cmd.extend(["--url", "http://localhost:5001"])
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="ignore"
            )
            for line in proc.stdout:
                m = re.search(r'https://[a-z0-9\-]+\.trycloudflare\.com', line)
                if m:
                    url = m.group(0)
                    print(f"[LINK] Публичная ссылка Cloudflare: {url}")
                    _tunnel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tunnel_url.txt")
                    with open(_tunnel_path, "w", encoding="utf-8") as f:
                        f.write(url)
                    def _send_when_ready(u):
                        import time as _t
                        for _ in range(30):
                            try:
                                if bot.is_ready():
                                    asyncio.run_coroutine_threadsafe(send_panel_link(u), bot.loop).result(timeout=15)
                                    return
                            except Exception as e:
                                print(f"[ERR] Ошибка отправки ссылки в Discord: {e}")
                                return
                            _t.sleep(1)
                    threading.Thread(target=_send_when_ready, args=(url,), daemon=True).start()
                    fail_count = 0  # basarili, sayaci sifirla
            proc.wait()
            if proc.returncode != 0:
                fail_count += 1
                print(f"[WARN] Туннель отключился (kod={proc.returncode}, deneme {fail_count}/{MAX_FAILS})")
            else:
                print("[WARN] Туннель отключился. Повторный запуск через 4 секунды...")
                fail_count = 0
            time.sleep(4)
            proto_idx += 1
        except FileNotFoundError as e:
            fail_count += 1
            print(f"[ERR] Cloudflare binary bulunamadi/exec edilemedi: {e}")
            print(f"[ERR] Tunnel devre disi birakildi ({fail_count}/{MAX_FAILS}).")
            time.sleep(5)
        except Exception as e:
            fail_count += 1
            print(f"[ERR] Ошибка работы Cloudflare Tunnel ({fail_count}/{MAX_FAILS}): {e}")
            time.sleep(5)

    print(f"[CLOUDFLARE] {MAX_FAILS} ardisik ошибка, tunnel tamamen devre disi.")
    print(f"[CLOUDFLARE] Sorun devam ederse .env'e добавить: DISABLE_TUNNEL=1")


# on_ready 
_synced = False
VOICE_CHANNEL_ID = None  # Panelden настройк

async def _monitor_voice():
    """Голос ссылка canlı tut — düştüğünde bağlan, каждый 4 dakikada удалить çal."""
    await bot.wait_until_ready()
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
        # Bağlıysa ve 4 dakika geçtiyse удалить ping at
        elif time.time() - last_ping > 240:
            try:
                if not vc.is_playing():
                    # 1 saniyelik sessiz ses
                    import io
                    delete = io.BytesIO(b'\x00' * 3840)  # 20ms PCM удалить
                    source = discord.PCMAudio(delete)
                    vc.play(source)
                last_ping = time.time()
            except Exception:
                pass

@bot.event
async def on_ready():
    global _synced
    if not _synced:
        # Guild-specific sync — anında активен olur
        for guild in bot.guilds:
            try:
                await bot.tree.sync(guild=guild)
                print(f'[SYNC] Slash команды sync edildi: {guild.name}')
            except Exception as e:
                print(f'[SYNC] Ошибка {guild.name}: {e}')
        await bot.tree.sync()  # Global sync de yap
        _synced = True
        bot.loop.create_task(_monitor_voice())
    print(f"[OK] {bot.user} активен | {len(bot.guilds)} сервер")

    # Bot config'den status/activity oku — КАЖДЫЙ on_ready'de çalışır
    import json as _j
    _cfg_file = 'data/bot_config.json'
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

    # Голос в канал bağlan (только ilk başlangıçta)
    channel = bot.get_channel(VOICE_CHANNEL_ID) if VOICE_CHANNEL_ID else None
    if channel and isinstance(channel, discord.VoiceChannel):
        vc = discord.utils.get(bot.voice_clients, guild=channel.guild)
        if not vc:
            try:
                await channel.connect(self_deaf=False)
                print(f"[OK] Голос в канал bağlandı: {channel.name}")
            except Exception as e:
                print(f"[ERR] Голос bağlanma ошибки: {e}")

    # Bot instance'ı обновить
    from web.app import set_bot_instance
    set_bot_instance(bot)

    # Panel channelını контроль et — tunnel URL varsa отправить (только bir kez)
    _tunnel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tunnel_url.txt")
    if not getattr(bot, '_panel_link_sent', False) and os.path.exists(_tunnel_path):
        try:
            with open(_tunnel_path, "r", encoding="utf-8") as _f:
                _url = _f.read().strip()
            if _url:
                await send_panel_link(_url)
                bot._panel_link_sent = True
        except Exception as _e:
            print(f"[ERR] Panel link отправл: {_e}")

# Cog загрузить 
async def load_cogs():
    # These cogs have duplicate commands with other cogs
    SKIP_COGS = {
        "embed_utils.py", "__init__.py",
        "help_card.py", "_card_style.py",  # helper modules, not cogs (no setup())
        # Duplicate cog'lar (yenileri tercih ediliyor)
        "leveling_engagement.py",  # rank/leaderboard conflicts with level_cog/gamification_cog
        "temp_moderation.py",      # unban/mute conflicts with moderation_cog
        "ticket_commands.py",      # duplicate of ticket_cog
        "ticket_cog.py",           # use the advanced AI ticket.py instead of ticket_cog.py
        "utility_cog.py",          # help/botinfo/avatar/userinfo conflicts with info_tools
        "music.py",                # duplicate of music_cog (requires yt-dlp)
        "economy_cmds.py",         # duplicate of economy_cog
        "fun.py",                  # duplicate of fun_cog
        "utility.py",              # duplicate of utility_cog
        "automod.py",              # duplicate of automod_cog
    }
    
    # Загружаем централизованный обработчик ошибок ПЕРВЫМ
    try:
        import error_handler
        await error_handler.setup(bot)
        log.info("Централизованный обработчик ошибок загружен")
    except Exception as e:
        log.error(f"Ошибка загрузки обработчика ошибок: {e}")
    
    # Удаляем стандартную команду help discord.py, чтобы загрузить наш кастомный help cog
    bot.remove_command('help')

    cog_files = sorted([f for f in os.listdir("./cogs") if f.endswith(".py") and f not in SKIP_COGS])
    for filename in cog_files:
        ext = f"cogs.{filename[:-3]}"
        log.info(f"Загрузка: {filename}")
        try:
            await asyncio.wait_for(bot.load_extension(ext), timeout=20)
            log.info(f"Загружено: {filename}")
        except asyncio.TimeoutError:
            log.error(f"Cog timeout (20s): {filename}")
        except Exception as e:
            import traceback
            log.error(f"Ошибка загрузки cog ({filename}): {e}")
            traceback.print_exc()

# Main 
async def main():
    # Web paneli запустить (bot başlamadan до - только bir kez)
    from web.app import app, set_bot_instance
    set_bot_instance(bot)
    _start_web_server(app)
    print("[WEB] Web panel: http://localhost:5001")

    # WebSocket сервер запустить (real-time обновления)
    try:
        from web.websocket_server import start_websocket_thread
        start_websocket_thread()
        log.info("WebSocket сервер запущен на порту 8765")
    except Exception as e:
        log.warning(f"WebSocket сервер не запущен: {e}")

    # Cloudflare tüneli запустить (Flask'ın ayağa kalkması для 3 sn badd)
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
                # Ağ/Discord доступ anlık düşerse panel de ayakta kalsın diye
                # botu öldürmüyoruz; краткий baddyip tekrar deniyoruz.
                print(f"[ERR] Bot baslatma ошибки: {e}")
                await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
