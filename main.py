# Автоматическая установка зависимостей
import sys
import os
import subprocess

def _install_requirements():
    """Автоматически установить недостающие пакеты из requirements.txt"""
    req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'requirements.txt')
    if not os.path.exists(req_file):
        print("[ПРЕДУПРЕЖДЕНИЕ] requirements.txt не найден, проверка зависимостей пропущена")
        return
    
    with open(req_file, 'r', encoding='utf-8') as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
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
    
    missing = []
    for req in requirements:
        pkg_name = req.split('>=')[0].split('==')[0].split('<')[0].split('>')[0].split('~=')[0].strip()
        import_name = _import_map.get(pkg_name, pkg_name.replace('-', '_'))
        try:
            __import__(import_name)
        except ImportError:
            missing.append(req)
    
    if missing:
        print(f"[УСТАНОВКА] Устанавливается {len(missing)} недостающих пакетов...")
        for pkg in missing:
            print(f" -> {pkg}")
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--pre'] + missing)
            print("[УСТАНОВКА] Все пакеты установлены!")
        except subprocess.CalledProcessError as e:
            print(f"[ОШИБКА] Ошибка установки пакетов: {e}")
            print(f"[ИНФО] Ручная установка: pip install -r requirements.txt")
            sys.exit(1)
    else:
        print("[ОК] Все зависимости актуальны")

_install_requirements()

import discord
import warnings
warnings.filterwarnings('ignore', category=ResourceWarning)
from discord.ext import commands
import logging
from dotenv import load_dotenv
import threading
import re
import asyncio
import urllib.request
import urllib.error
import time
import signal
import atexit

# python-dotenv yorum satırlarını (Rusça, uzun çizgili vb.) uyarı olarak basabiliyor.
# Bunlar zararsızdır — uyarıları gizleyip değerleri yine de okumaya devam ediyoruz.
logging.getLogger("dotenv").setLevel(logging.ERROR)

# Загружаем .env из каталога скрипта (надёжно, независимо от рабочей директории)
# и с override=True, чтобы значение из .env всегда применялось.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE_DIR, ".env"), override=True)

# КРИТИЧНО: фиксируем рабочую директорию на корень проекта.
# Коги пишут в относительные пути 'data/...' (mod_data.json, warnings и т.д.).
# Если бот запущен из другого каталога (например, из /home или через systemd),
# данные пишутся в другое место и "теряются" после перезапуска.
# os.chdir решает это глобально — все относительные пути резолвятся к корню.
os.chdir(_BASE_DIR)

# Централизованная конфигурация и логирование 
from config import Config
from logger import setup_logger, get_logger

Config.ensure_dirs()
log = setup_logger("bot", Config.LOG_FILE, Config.LOG_LEVEL)

# Стартовый фикс: очистка дублирующих эндпоинтов
import subprocess as _sp, sys as _sys
_fix = os.path.join(os.path.dirname(__file__), 'fix_dup.py')
if os.path.exists(_fix):
    _sp.run([_sys.executable, _fix], capture_output=True)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=Config.COMMAND_PREFIX, intents=intents, help_command=None)


# ─── Ролевой контроль доступа к командам (Command ACL) ────────────────
async def _acl_check(ctx):
    """Prefix-команды: проверить ролевой доступ."""
    try:
        from services.permission_acl import has_access
        cmd = ctx.command.name if ctx.command else None
        if cmd:
            if not has_access(ctx.guild.id if ctx.guild else 0, cmd, ctx.author):
                await ctx.send("🚫 У вас нет доступа к этой команде.", delete_after=8)
                return False
    except Exception:
        pass
    return True

bot.check(_acl_check)


async def _acl_slash_check(interaction):
    """Slash-команды: проверить ролевой доступ."""
    try:
        from services.permission_acl import has_access
        cmd = getattr(interaction.command, "name", None) or \
              (interaction.data.get("name") if interaction.data else None)
        guild = interaction.guild
        if cmd and guild:
            if not has_access(guild.id, cmd, interaction.user):
                await interaction.response.send_message(
                    "🚫 У вас нет доступа к этой команде.", ephemeral=True)
                return False
    except Exception:
        pass
    return True

bot.tree.interaction_check = _acl_slash_check

ALERT_ROLE_ID = None

_web_server_proc = None
_gunicorn_available = None


def _have_gunicorn():
    """Проверка установлен ли gunicorn"""
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
    """Запуск подпроцесса Gunicorn. Если не получится — fallback на Werkzeug."""
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
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None,
            )
            print(f"[ВЕБ] Gunicorn запущен (pid={_web_server_proc.pid})")
            return
        except Exception as e:
            print(f"[ВЕБ] Не удалось запустить Gunicorn, fallback на Werkzeug: {e}")

    import logging
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False),
        daemon=True
    ).start()
    print("[ВЕБ] Werkzeug (fallback) запущен")


def _stop_web_server():
    """Корректно закрыть веб-сервер."""
    global _web_server_proc
    if _web_server_proc and _web_server_proc.poll() is None:
        try:
            _web_server_proc.terminate()
            try:
                _web_server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _web_server_proc.kill()
        except Exception as e:
            print(f"[ВЕБ] Ошибка закрытия: {e}")
        _web_server_proc = None


def cleanup_on_exit():
    """Действия очистки при закрытии бота"""
    try:
        print("[ОЧИСТКА] Бот закрывается...")
        _stop_web_server()
        if hasattr(bot, 'voice_clients'):
            for vc in bot.voice_clients:
                try:
                    asyncio.run_coroutine_threadsafe(vc.disconnect(), bot.loop)
                except Exception:
                    pass
        if not bot.is_closed():
            asyncio.run_coroutine_threadsafe(bot.close(), bot.loop)
    except Exception as e:
        print(f"[ОЧИСТКА] Ошибка очистки: {e}")

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного выключения"""
    print(f"[СИГНАЛ] Получен сигнал {signum}, выполняется очистка...")
    cleanup_on_exit()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup_on_exit)

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
            panel_ch = discord.utils.get(guild.text_channels, name="aether-panel")
            if not panel_ch:
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
                    print(f"[ИНФО] Канал aether-panel создан: {guild.name}")
            async for msg in panel_ch.history(limit=10):
                if msg.author == bot.user:
                    await msg.delete()
            embed = discord.Embed(
                color=0xc8922a,
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(
                name="Aether — Управление панелью",
                icon_url=guild.icon.url if guild.icon else None
            )
            embed.description = f"[**› Войти в панель**]({panel_url})"
            embed.set_image(url="https://static.klipy.com/ii/71b2873e478b9d8d0482ea3ec777ba7f/15/36/51ALUZhO.gif")
            embed.add_field(
                name="🖥 Сервер",
                value=f"```{guild.name}```",
                inline=True
            )
            embed.add_field(
                name="👥 Участники",
                value=f"```{guild.member_count}```",
                inline=True
            )
            embed.add_field(
                name="🔓 Доступ",
                value="```Автоматически по роли Discord```",
                inline=False
            )
            embed.set_footer(
                text="Aether Panel • Обновляется при каждом запуске",
                icon_url=guild.icon.url if guild.icon else None
            )
            await panel_ch.send(embed=embed)
            print(f"[ОК] Ссылка на панель отправлена: {guild.name}")
        except Exception as e:
            print(f"[ОШИБКА] Не удалось отправить ссылку на панель ({guild.name}): {e}")

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
        return e.code < 500
    except Exception:
        return False


def _write_and_broadcast_tunnel_url(url):
    _tunnel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tunnel_url.txt")
    with open(_tunnel_path, "w", encoding="utf-8") as f:
        f.write(url)
    asyncio.run_coroutine_threadsafe(send_panel_link(url), bot.loop)


def _get_cloudflared_binary():
    import shutil, platform, urllib.request
    base_dir = os.path.dirname(os.path.abspath(__file__))
    is_win = platform.system().lower() == "windows"

    def is_valid_exe(path):
        if not os.path.exists(path):
            return False
        if os.path.getsize(path) < 5 * 1024 * 1024:
            return False
        try:
            with open(path, 'rb') as f:
                magic = f.read(2)
                if magic != b'MZ':
                    return False
            return True
        except Exception:
            return False

    for name in ["cloudflared.exe", "cloudflared_new.exe", "cloudflared"]:
        p = os.path.join(base_dir, name)
        if is_valid_exe(p):
            return p
        elif os.path.exists(p):
            try: os.remove(p)
            except: pass

    sys_cf = shutil.which("cloudflared") or shutil.which("cloudflared.exe")
    if sys_cf and is_valid_exe(sys_cf):
        return sys_cf

    if os.getenv('DISABLE_TUNNEL', '0') == '1':
        print("[CLOUDFLARE] DISABLE_TUNNEL=1, туннель пропущен")
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
            print(f"[CLOUDFLARE] Загруженный файл невалиден. Удален: {dest_path}")
            try: os.remove(dest_path)
            except: pass
            return None
    except Exception as _e:
        print(f"[CLOUDFLARE] Ошибка автоматической загрузки cloudflared: {_e}")
        return None

def start_tunnel():
    import time
    if os.getenv('DISABLE_TUNNEL', '0') == '1':
        print("[CLOUDFLARE] DISABLE_TUNNEL=1, туннель не запускается")
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
            print(f"[ИНФО] Запуск туннеля Cloudflare (протокол: {proto})...")
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
                    print(f"[ССЫЛКА] Публичная ссылка Cloudflare: {url}")
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
                                print(f"[ОШИБКА] Ошибка отправки ссылки в Discord: {e}")
                                return
                            _t.sleep(1)
                    threading.Thread(target=_send_when_ready, args=(url,), daemon=True).start()
                    fail_count = 0
            proc.wait()
            if proc.returncode != 0:
                fail_count += 1
                print(f"[ПРЕДУПРЕЖДЕНИЕ] Туннель отключился (код={proc.returncode}, попытка {fail_count}/{MAX_FAILS})")
            else:
                print("[ПРЕДУПРЕЖДЕНИЕ] Туннель отключился. Повторный запуск через 4 секунды...")
                fail_count = 0
            time.sleep(4)
            proto_idx += 1
        except FileNotFoundError as e:
            fail_count += 1
            print(f"[ОШИБКА] Бинарь Cloudflare не найден: {e}")
            print(f"[ОШИБКА] Туннель отключен ({fail_count}/{MAX_FAILS}).")
            time.sleep(5)
        except Exception as e:
            fail_count += 1
            print(f"[ОШИБКА] Ошибка работы Cloudflare Tunnel ({fail_count}/{MAX_FAILS}): {e}")
            time.sleep(5)

    print(f"[CLOUDFLARE] {MAX_FAILS} подряд ошибок, туннель полностью отключен.")
    print(f"[CLOUDFLARE] Если проблема продолжается, добавьте в .env: DISABLE_TUNNEL=1")


_synced = False
VOICE_CHANNEL_ID = None

async def _monitor_voice():
    """Держим голосовое подключение живым — переподключаемся при падении, каждые 4 минуты играем тишину."""
    await bot.wait_until_ready()
    await asyncio.sleep(10)
    last_ping = 0
    while not bot.is_closed():
        await asyncio.sleep(30)
        channel = bot.get_channel(VOICE_CHANNEL_ID) if VOICE_CHANNEL_ID else None
        if not channel or not isinstance(channel, discord.VoiceChannel):
            continue
        vc = discord.utils.get(bot.voice_clients, guild=channel.guild)
        
        if not vc or not vc.is_connected():
            try:
                vc = await channel.connect(self_deaf=False)
                last_ping = time.time()
            except Exception:
                pass
        elif time.time() - last_ping > 240:
            try:
                if not vc.is_playing():
                    import io
                    delete = io.BytesIO(b'\x00' * 3840)
                    source = discord.PCMAudio(delete)
                    vc.play(source)
                last_ping = time.time()
            except Exception:
                pass

@bot.event
async def on_ready():
    global _synced
    if not _synced:
        for guild in bot.guilds:
            try:
                await bot.tree.sync(guild=guild)
                print(f'[СИНХРОНИЗАЦИЯ] Slash команды синхронизированы: {guild.name}')
            except Exception as e:
                print(f'[СИНХРОНИЗАЦИЯ] Ошибка {guild.name}: {e}')
        await bot.tree.sync()
        _synced = True
        bot.loop.create_task(_monitor_voice())
    print(f"[ОК] {bot.user} активен | {len(bot.guilds)} серверов")

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
    print(f"[ОК] Статус: {_status} | Активность: {_activity_text}")

    channel = bot.get_channel(VOICE_CHANNEL_ID) if VOICE_CHANNEL_ID else None
    if channel and isinstance(channel, discord.VoiceChannel):
        vc = discord.utils.get(bot.voice_clients, guild=channel.guild)
        if not vc:
            try:
                await channel.connect(self_deaf=False)
                print(f"[ОК] Подключен к голосовому каналу: {channel.name}")
            except Exception as e:
                print(f"[ОШИБКА] Ошибка подключения к голосу: {e}")

    from web.app import set_bot_instance
    set_bot_instance(bot)

    _tunnel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tunnel_url.txt")
    if not getattr(bot, '_panel_link_sent', False) and os.path.exists(_tunnel_path):
        try:
            with open(_tunnel_path, "r", encoding="utf-8") as _f:
                _url = _f.read().strip()
            if _url:
                await send_panel_link(_url)
                bot._panel_link_sent = True
        except Exception as _e:
            print(f"[ОШИБКА] Отправка ссылки панели: {_e}")

async def load_cogs():
    SKIP_COGS = {
        # Cog değil, yardımcı modüller (başka dosyalardan import edilir)
        "embed_utils.py", "__init__.py",
        "_card_style.py",
        "leveling_engagement.py",
    }
    
    try:
        import error_handler
        await error_handler.setup(bot)
        log.info("Централизованный обработчик ошибок загружен")
    except Exception as e:
        log.error(f"Ошибка загрузки обработчика ошибок: {e}")
    
    bot.remove_command('help')

    cog_files = sorted([f for f in os.listdir("./cogs") if f.endswith(".py") and f not in SKIP_COGS])
    for filename in cog_files:
        ext = f"cogs.{filename[:-3]}"
        log.info(f"Загрузка: {filename}")
        try:
            await asyncio.wait_for(bot.load_extension(ext), timeout=20)
            log.info(f"Загружено: {filename}")
        except asyncio.TimeoutError:
            log.error(f"Таймаут кога (20с): {filename}")
        except Exception as e:
            import traceback
            log.error(f"Ошибка загрузки кога ({filename}): {e}")
            traceback.print_exc()

async def main():
    from web.app import app, set_bot_instance
    set_bot_instance(bot)
    _start_web_server(app)
    print("[ВЕБ] Веб панель: http://localhost:5001")

    try:
        from web.websocket_server import start_websocket_thread
        start_websocket_thread()
        log.info("WebSocket сервер запущен на порту 8765")
    except Exception as e:
        log.warning(f"WebSocket сервер не запущен: {e}")

    def delayed_tunnel():
        import time
        time.sleep(3)
        start_tunnel()
    threading.Thread(target=delayed_tunnel, daemon=True).start()

    print("[БОТ] Запускается... (загрузка когов -> вход в Discord)")
    async with bot:
        print("[БОТ] Коги загружаются...")
        await load_cogs()
        _token = (os.getenv("TOKEN", "") or os.getenv("TОКEN", "")).strip()
        if not _token:
            print("[ОШИБКА] Токен не найден! Добавьте токен в .env файл (строка TOKEN=ваш_токен) "
                  "из https://discord.com/developers/applications")
            sys.exit(1)
        # Anti-crash: автоперезапуск при сетевых сбоях, но с нарастающей паузой,
        # чтобы не долбить Discord во время сбоя (5 -> 10 -> 20 ... макс. 60 сек).
        _delay = 5
        while True:
            try:
                print("[БОТ] Подключение к Discord...")
                await bot.start(_token)
                _delay = 5  # удачная сессия — сбросить паузу
            except discord.LoginFailure:
                print("[ОШИБКА] Недействительный токен Discord! Исправьте TOKEN в .env — "
                      "перезапуск не поможет.")
                sys.exit(1)
            except Exception as e:
                print(f"[ОШИБКА] Бот отключился: {e}")
                print(f"[БОТ] Автоперезапуск через {_delay} сек...")
                await asyncio.sleep(_delay)
                _delay = min(60, _delay * 2)

if __name__ == "__main__":
    asyncio.run(main())
