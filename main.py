
from logger import get_logger

_log = get_logger("main")

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
        # Реальное имя импорта — discord.ext.voice_recv, а не voice_recv:
        # из-за неверного имени чекер считал пакет пропавшим и гонял
        # pip install при КАЖДОМ старте бота.
        'discord-ext-voice-recv': 'discord.ext.voice_recv',
        'flask-session': 'flask_session',
        'duckduckgo-search': 'duckduckgo_search',
        'deep-translator': 'deep_translator',
        'edge-tts': 'edge_tts',
        'faster-whisper': 'faster_whisper',
        # yt-dlp убран вместе с системой музыки (/play), 2026-09-01.
        'PyNaCl': 'nacl',
        # Пакет в pip называется Pillow, импортируется как PIL
        # (без маппинга «Pillow» всегда считался пропавшим).
        'Pillow': 'PIL',
    }
    
    missing = []
    for req in requirements:
        pkg_name = req.split('>=')[0].split('==')[0].split('<')[0].split('>')[0].split('~=')[0].strip()
        import_name = _import_map.get(pkg_name, pkg_name.replace('-', '_'))
        try:
            __import__(import_name)
        except ImportError:
            missing.append(req)
        except Exception as _ex:
            # Пакет стоит, но не загружается (битая нативная DLL/.so — типичный
            # пример: ctranslate2 без Visual C++ Redistributable на Windows).
            # Не валим бота и не переустанавливаем по кругу — просто предупреждаем;
            # связанная фича (распознавание речи) мягко выключится в своём коге.
            if pkg_name in ('faster-whisper', 'edge-tts'):
                print(f"[ИНФО] {pkg_name} не загрузился ({type(_ex).__name__}) — "
                      f"соответствующая фича выключена, бот продолжит работу")
            else:
                missing.append(req)
    
    if missing:
        print(f"[УСТАНОВКА] Устанавливается {len(missing)} недостающих пакетов...")
        for pkg in missing:
            print(f" -> {pkg}")
        try:
            # Сначала СТАБИЛЬНЫЕ версии. Раньше ставилось всё с --pre —
            # так в бота могли приехать нестабильные альфа-билды всех пакетов.
            subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + missing)
        except subprocess.CalledProcessError:
            # Запасной путь: часть пакетов (discord-ext-voice-recv) есть
            # только в виде pre-release — тогда повторяем с --pre.
            print("[УСТАНОВКА] Повтор с --pre (нужны pre-release версии)...")
            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--pre'] + missing)
            except subprocess.CalledProcessError as e:
                # Debian 12+/Ubuntu 23+: pip защищён PEP 668 — легитимный
                # выход для владельческой установки (это не системный Python
                # дистрибутива, бот ставит своё сам).
                print("[УСТАНОВКА] Повтор с --break-system-packages (PEP 668)...")
                try:
                    subprocess.check_call(
                        [sys.executable, '-m', 'pip', 'install',
                         '--break-system-packages', '--pre'] + missing)
                except subprocess.CalledProcessError as e:
                    print(f"[ОШИБКА] Ошибка установки пакетов: {e}")
                    print("[ИНФО] Ручная установка: pip install -r requirements.txt")
                    sys.exit(1)
        print("[УСТАНОВКА] Все пакеты установлены!")
    else:
        print("[ОК] Все зависимости актуальны")

_install_requirements()

# ─── Кодировка вывода: принудительный UTF-8 ────────────────────────────
# Инцидент с VDS (свежий Windows Server, русская локаль): консоль по
# умолчанию cp1251/cp866. Бот печатает эмодзи (⚠ ✅ 🎵 …) и длинные
# русские строки — на cp1251 print(...) бросает UnicodeEncodeError, и
# процесс/окно вывода обрывается («после Anti-crash тишина, бот не
# работает»). Файл лога и так пишется в utf-8, но stdout/stderr шли в
# системной кодировке. Принудительно переоткрываем потоки в UTF-8 с
# заменой непечатаемых символов (на Linux .reconfigure тоже валиден;
# если атрибута нет — не падаем).
for _stream_name in ("stdout", "stderr"):
    try:
        _stream = getattr(sys, _stream_name, None)
        if _stream is not None and hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception as _enc_ex:
        sys.stderr.write(f"[!] не удалось переключить {_stream_name} в UTF-8: {_enc_ex}\n")


# ─── Аварийный лог фатальных ошибок старта ────────────────────────────
# На VDS окно .bat может закрыться/оборваться до того, как поднимется
# основной логгер. Любая необработанная ошибка самого раннего старта
# дописывается в logs/fatal_start.log — причина «не запускается» не теряется.
def _fatal_log_hook(exc_type, exc_value, exc_tb):
    try:
        os.makedirs("logs", exist_ok=True)
        import datetime as _dt
        with open(os.path.join("logs", "fatal_start.log"), "a",
                  encoding="utf-8") as _f:
            _f.write(f"\n===== {_dt.datetime.now()} =====\n")
            import traceback as _tb
            _tb.print_exception(exc_type, exc_value, exc_tb, file=_f)
    except Exception as _hook_ex:
        sys.stderr.write(f"[!] не удалось записать fatal_start.log: {_hook_ex}\n")
    # KeyboardInterrupt — обычный выход, не пугаем трейсбеком.
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    print("\n[ФАТАЛЬНО] Бот упал при старте. Подробности записаны в "
          "logs/fatal_start.log\n", file=sys.stderr)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _fatal_log_hook

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
import json

# python-dotenv может печатать предупреждения о строках-комментариях (русские, с длинным тире и т.п.).
# Они безвредны — скрываем предупреждения, но продолжаем читать значения.
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

# ─── Журнал запусков: «почему бот перезапустился» ─────────────────────
# Каждый старт/останов/обрыв записывается в data/run_log.json (последние
# 50 событий). После перезапуска видно: код выхода, сигнал, причина —
# а не «сидел 14 часов и сам перезапустился».
_RUN_LOG = os.path.join(_BASE_DIR, 'data', 'run_log.json')
_RUN_START_TS = time.time()


def _record_run(event: str, **extra):
    """Записать событие жизненного цикла процесса (start/stop/disconnect)."""
    try:
        rows = []
        if os.path.exists(_RUN_LOG):
            try:
                with open(_RUN_LOG, 'r', encoding='utf-8') as f:
                    rows = json.load(f)
            except Exception:
                rows = []
        import datetime as _dt
        row = {'ts': _dt.datetime.now(_dt.timezone.utc).isoformat(timespec='seconds'),
               'event': event, 'pid': os.getpid(), **extra}
        rows.append(row)
        rows = rows[-50:]
        tmp = _RUN_LOG + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _RUN_LOG)
    except Exception as _ex:
        log.debug('_record_run(): подавлено: %s', _ex)


async def _memory_watchdog():
    """Раз в минуту смотрим память: рост → GC + предупреждение в лог.

    Задача: 14 часов аптайма кончились молча — типичный OOM-киллер
    (растущий кэш или утечка). Если RSS близко к критическому, пишем
    в run_log и лог CRITICAL, чтобы причина была видна ДО перезапуска.
    """
    import gc
    try:
        import psutil as _ps
    except Exception:
        return
    minute = 0
    # ВАЖНО (инцидент 30.08, VDS/Windows+антивирус): ПОЛНАЯ сборка
    # (gc.collect() без поколения = gen2, обход всей кучи) на боевой
    # машине занимала до 13.5 секунд замерзания event-loop. Watchdog
    # раньше бил её сам, добавляя фризы к автоматическим. Теперь в
    # горячем пути НИКОГДА нет полной сборки: делаем только дешёвые
    # gen0/gen1 (молодой мусор, миллисекунды). Циклический мусор в
    # старших поколениях соберётся редкой автоматической gen2 (пороги
    # подняты в gc_stabilize до 50000/5000/5000 — на практике раз в
    # часы), а постоянный рост памяти от неё не зависит (утечка — это
    # не освобождаемые ссылки, их GC всё равно не чинит, про неё скажет
    # сам watchdog ниже).
    while True:
        await asyncio.sleep(60)
        minute += 1
        try:
            p = _ps.Process()
            rss = p.memory_info().rss / 1024 / 1024
            threads = p.num_threads()
            mem_warn = 700
            mem_crit = 900
            if rss > mem_warn:
                level = 'warn' if rss < mem_crit else 'critical'
                # Дешёвая частичная сборка: gen0 каждый тик, gen1 раз в
                # 5 минут. Обе не обходят всю кучу — event-loop почти не
                # стоит (никаких 10-секундных фризов как от gen2).
                gen = 1 if minute % 5 == 0 else 0
                try:
                    gc.collect(gen)
                except Exception as _gc_ex:
                    log.debug('memory_watchdog: gen%d-сборка не удалась: %s', gen, _gc_ex)
                log.warning('[ПАМЯТЬ] RSS %.0f МБ, потоков %d — %s '
                            '(частичная сборка gen%d; полная в горячем '
                            'пути отключена, чтобы не морозить event-loop)',
                            rss, threads, level, gen)
            if rss > mem_crit:
                _record_run('memory_high',
                            rss_mb=round(rss, 1), threads=threads)
                log.critical('[ПАМЯТЬ] RSS %.0f МБ — близко к лимиту '
                             '(если процесс умрёт — причина в этом)', rss)
            if minute % 5 == 0 and rss > mem_warn:
                log.warning('[ПАМЯТЬ] стабильно высокое RSS %.0f МБ — '
                            'проверьте кэши/утечки', rss)
        except Exception as _ex:
            log.debug('memory_watchdog(): подавлено: %s', _ex)

# Раньше здесь при КАЖДОМ старте запускался внешний скрипт fix_dup.py
# («очистка дублирующих эндпоинтов»). Сам скрипт удалён из репозитория
# ещё в chore-коммите очистки, но вызов остался — молчаливый
# subprocess.run с capture_output, который ничего не делал и ничего не
# сообщал. Если бы файл вернулся (например, из старого бэкапа рядом с
# ботом), он бы выполнился при запуске без единой строки в логе.
# Убрано: дублей эндпоинтов нет (их стережёт tests/test_panel_no_500.py
# и проверка роутов), а немой запуск постороннего кода на старте — риск.

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=Config.COMMAND_PREFIX, intents=intents, help_command=None)


# ─── Текстовые «!»-команды отключены полностью (заказ владельца 2026-08-28) ─
# «через ! тоже убери, не нужны они нам»: ни одно сообщение-префикс не
# исполняется. Всё живое — слеш-меню (4 команды), кнопки и веб-панель.
# Слушатели on_message когов (антиспам, левелы, тикеты) НЕ затронуты:
# они вешаются через @commands.Cog.listener, а не через этот конвейер.
async def _no_prefix_commands(message):
    return


bot.process_commands = _no_prefix_commands


# ─── Ролевой контроль доступа к командам (Command ACL) ────────────────
async def _acl_check(ctx):
    """Prefix-команды: проверить ролевой доступ (учитывая сабкоманды групп)."""
    try:
        from services import command_switches as _csw
        from services.permission_acl import has_access
        # qualified_name даёт "group sub" для сабкоманд — правила на группу
        # и на сабкоманду ("j2c", "j2c-lobby") срабатывают корректно.
        cmd = None
        if ctx.command:
            cmd = getattr(ctx.command, "qualified_name", None) or ctx.command.name
        if cmd:
            # Команда выключена владельцем из панели — не отвечаем вовсе.
            if _csw.is_disabled(cmd):
                await ctx.send(f"Команда {cmd} выключена владельцем панели.",
                               delete_after=10)
                return False
            if not has_access(ctx.guild.id if ctx.guild else 0, cmd, ctx.author):
                await ctx.send(f"У вас нет доступа к команде {cmd}. "
                               "Доступ настраивает владелец: панель → Доступ → Права команд.",
                               delete_after=12)
                return False
    except Exception as _ex:
        _log.debug("_acl_check(): подавлено: %s", _ex)
    return True

bot.check(_acl_check)


def _find_action_value(options):
    """Рекурсивно найти значение опции action/действие в данных slash-команды.

    /moderate и /utility принимают параметр action (ban/kick/timeout/clear…),
    поэтому «классическое» разрешение на действие проверяем по его значению,
    а не по имени команды.
    """
    if not options:
        return None
    for opt in options:
        if not isinstance(opt, dict):
            continue
        if opt.get("name") in ("action", "действие") and isinstance(opt.get("value"), str):
            return opt["value"]
        sub = opt.get("options")
        if isinstance(sub, list):
            found = _find_action_value(sub)
            if found:
                return found
    return None


async def _acl_slash_check(interaction):
    """Slash-команды: проверить ролевой доступ (учитывая сабкоманды групп)."""
    try:
        from services import command_switches as _csw
        from services.permission_acl import has_access, check_action, ACTION_VALUES
        cmd = None
        if getattr(interaction, "command", None) is not None:
            cmd = getattr(interaction.command, "qualified_name", None) or \
                  getattr(interaction.command, "name", None)
        if not cmd:
            cmd = (interaction.data.get("name") if interaction.data else None)
        if cmd and _csw.is_disabled(cmd):
            await interaction.response.send_message(
                f"Команда /{cmd} выключена владельцем панели.", ephemeral=True)
            return False
        guild = interaction.guild
        if cmd and guild:
            if not has_access(guild.id, cmd, interaction.user):
                await interaction.response.send_message(
                    f"Недостаточно прав: команда /{cmd} доступна не всем ролям. "
                    "Доступ настраивает владелец: панель → Доступ → Права команд.",
                    ephemeral=True)
                return False
        # Классические разрешения: выбранное действие (напр. /moderate action=ban)
        if guild:
            action_value = _find_action_value(
                (interaction.data or {}).get("options"))
            if action_value:
                action_key = ACTION_VALUES.get(action_value)
                if action_key and not check_action(guild.id, interaction.user, action_key):
                    await interaction.response.send_message(
                        "Недостаточно прав: это действие доступно не всем ролям. Панель → Доступ → Права команд.", ephemeral=True)
                    return False
    except Exception as _ex:
        _log.debug("_acl_slash_check(): подавлено: %s", _ex)
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
    """Запуск веб-панели.

    ПО УМОЛЧАНИЮ — В ТОМ ЖЕ ПРОЦЕССЕ, ЧТО БОТ (Werkzeug, threaded).
    Только так панель видит бота: web/app.py хранит bot_instance в памяти
    процесса, и при отдельном процессе (gunicorn) он всегда None → панель
    отвечает «Бот офлайн», изменения из панели не применяются к боту
    (каналы, коги, синк команд, наказания...). Вот это и был разрыв
    «я меняю тут — а там не работает».

    Вернуть старые «внешний процесс без моста» (осознанно): PANEL_PROCESS=gunicorn
    на своём риске — панель НЕ будет видеть бота.
    """
    global _web_server_proc
    _port = int(os.environ.get('PANEL_PORT', '') or 0)
    if not _port:
        try:
            from config import Config
            _port = int(getattr(Config, 'PORT', 0) or 0)
        except Exception:
            _port = 0
    _port = _port or 5001

    _mode = (os.environ.get('PANEL_PROCESS', '') or '').strip().lower()
    if _mode == 'gunicorn' and _have_gunicorn():
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
            print(f"[ВЕБ] Gunicorn запущен (pid={_web_server_proc.pid}) — "
                  f"панель в ОТДЕЛЬНОМ процессе: бота она НЕ видит "
                  f"(настройки из панели не применятся!)")
            return
        except Exception as e:
            print(f"[ВЕБ] Не удалось запустить Gunicorn, fallback на Werkzeug: {e}")

    import logging
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=_port, debug=False,
                               use_reloader=False, threaded=True),
        daemon=True
    ).start()
    print(f"[ВЕБ] Панель запущена ВМЕСТЕ С БОТОМ (единый процесс): "
          f"http://localhost:{_port} — изменения из панели применяются сразу")


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


# ── Cloudflare-туннель: запускается ВМЕСТЕ с ботом ───────────────────────────
# Активируется сам после scripts/setup_panel_tunnel.bat: нашли конфиг
# туннеля — поднимаем панель на домене (hakumods.xyz) прямо из start.bat.
# Если туннель уже крутится службой Windows — не дублируем.
# Отключить: TUNNEL_AUTOSTART=0 в .env.
# Старый quick-туннель со случайной ссылкой выключен по умолчанию
# (вернуть: QUICK_TUNNEL=1, см. main() внизу).
_tunnel_proc = None


def _tunnel_service_running_windows():
    """Туннель уже поставлен службой Windows (setup_panel_tunnel.bat)?"""
    if os.name != 'nt':
        return False
    try:
        out = subprocess.check_output(['sc', 'query', 'cloudflared'],
                                      stderr=subprocess.DEVNULL, timeout=5)
        return b'RUNNING' in out
    except Exception:
        # службы нет/не ответила — будем запускать сами
        return False


def _start_tunnel_sidecar():
    global _tunnel_proc
    raw = (os.environ.get('TUNNEL_AUTOSTART', '') or '').strip().lower()
    if raw in ('0', 'false', 'no', 'off'):
        return
    from services import named_tunnel as _nt
    root = os.path.dirname(os.path.abspath(__file__))
    cfg = _nt.find_config(root)
    if not cfg:
        return  # туннель ещё не настраивали — работаем локально, не шумим
    # Windows-грабли: «localhost» в origin резолвится в ::1 (IPv6), а панель
    # слушает 0.0.0.0 (IPv4) → «dial tcp [::1]:5001: connectex: connection
    # refused». Чиним все копии конфига ДО запуска туннеля/службы.
    try:
        _healed = _nt.heal_all_origins(root, cfg)
    except Exception:
        _healed = []
    if _healed:
        print('[ТУННЕЛЬ] Починил origin в конфиге: localhost -> 127.0.0.1 '
              f'({len(_healed)} файл.) — панель слушает IPv4, '
              'а localhost на Windows резолвится в IPv6 ::1')
    # Протокол до края Cloudflare: QUIC (UDP, по умолчанию cloudflared) на
    # капризных сетях VDS рвётся каждые ~20 секунд («timeout: no recent
    # network activity», «failed to accept QUIC stream») и домен флапает.
    # http2 (TCP) стабилен — потому он и дефолт. Вернуть QUIC: TUNNEL_PROTOCOL=quic.
    proto = (os.environ.get('TUNNEL_PROTOCOL', '') or 'http2').strip().lower()
    if proto not in ('http2', 'quic', 'auto'):
        print(f'[ТУННЕЛЬ] TUNNEL_PROTOCOL={proto} не понял — использую http2.')
        proto = 'http2'
    try:
        _prototuned = _nt.ensure_protocol_line(root, cfg, proto)
    except Exception:
        _prototuned = []
    if _prototuned:
        print(f'[ТУННЕЛЬ] Прописал protocol: {proto} в конфиг '
              f'({len(_prototuned)} файл.) — QUIC/UDP нестабилен, '
              'http2/TCP держит соединение; службе Windows флаг не передать, '
              'потому пишем в конфиг.')
    pub = _nt.public_url(cfg)
    if pub:
        # Постоянную ссылку (https://домен) бот отправит в канал панели —
        # она больше никогда не меняется между запусками.
        _nt.remember_url(root, pub)
    # Портативные копии конфига/ключа в scripts/ — для заливки на VDS.
    _nt.export_portable(root, cfg)
    scripts_dir = os.path.join(root, 'scripts')
    exe = next((c for c in (os.path.join(scripts_dir, 'cloudflared.exe'),
                            os.path.join(scripts_dir, 'cloudflared'))
                if os.path.exists(c)), None)
    if not exe:
        # VDS-режим «только start.bat»: докачиваем бинарник сами —
        # настраивать руками ничего не нужно.
        print('[ТУННЕЛЬ] cloudflared не найден — скачиваю автоматически...')
        exe = _nt.ensure_binary(scripts_dir)
    if exe:
        # Ключ туннеля мог остаться на старом ПК — поднимем портативную копию
        # из scripts/ или пересоздадим туннель прямо здесь (cert.pem уже есть).
        # Чиним ДО проверки службы: «служба крутится, но туннель мёртв»
        # после переезда — штатный случай VDS.
        if _nt.ensure_credentials(root, scripts_dir, exe):
            print('[ТУННЕЛЬ] Ключ туннеля восстановлен на этой машине (переезд).')
    if _tunnel_service_running_windows():
        print('[ТУННЕЛЬ] Уже крутится службой Windows — панель доступна: '
              + (pub or 'ваш домен'))
        return
    if not exe:
        print('[ТУННЕЛЬ] Не удалось скачать cloudflared (интернет?) — '
              'туннель пропущен, панель остаётся локальной.')
        return
    # Конфиг мог переехать с другого ПК (credentials-путь там старый) —
    # подменяем его на наш credentials-файл из scripts/.
    run_cfg = _nt.runtime_config(root, cfg)
    try:
        _tunnel_proc = subprocess.Popen(
            [exe, '--protocol', proto, '--config', run_cfg, 'tunnel', 'run'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=1, text=True, encoding='utf-8', errors='replace',
        )
    except Exception as e:
        print(f'[ТУННЕЛЬ] Не удалось запустить: {e}')
        return

    def _echo_tunnel_log():
        # Инцидент 30.08: ~60 строк cloudflared за рестарт прятали
        # сообщения бота. Показываем только значимое: ошибки, регистрации
        # соединений, итог пре-чеков (см. services/startup_info.py).
        from services.startup_info import tunnel_line_worth
        try:
            for line in _tunnel_proc.stdout:
                line = (line or '').rstrip()
                if line and tunnel_line_worth(line):
                    print(f'[ТУННЕЛЬ] {line}')
        except Exception as e:
            print(f'[ТУННЕЛЬ] Чтение лога: {e}')
        print(f'[ТУННЕЛЬ] Остановился (код {_tunnel_proc.poll()}) — следующий запуск бота поднимет снова.')

    threading.Thread(target=_echo_tunnel_log, daemon=True).start()
    print('[ТУННЕЛЬ] Запущен вместе с ботом'
          + (f' — панель: {pub}' if pub else ' — панель на домене активна.'))


def _stop_tunnel_sidecar():
    global _tunnel_proc
    if _tunnel_proc and _tunnel_proc.poll() is None:
        try:
            _tunnel_proc.terminate()
            try:
                _tunnel_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _tunnel_proc.kill()
        except Exception as e:
            print(f'[ТУННЕЛЬ] Остановка: {e}')
        _tunnel_proc = None


_cleanup_done = False


def cleanup_on_exit():
    """Действия очистки при закрытии бота (ровно один запуск)"""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
    try:
        print("[ОЧИСТКА] Бот закрывается...")
        _stop_web_server()
        _stop_tunnel_sidecar()
        try:
            loop = getattr(bot, 'loop', None)
            if loop and loop.is_running():
                if hasattr(bot, 'voice_clients'):
                    for vc in bot.voice_clients:
                        try:
                            asyncio.run_coroutine_threadsafe(vc.disconnect(), loop)
                        except Exception as _ex:
                            _log.debug("cleanup_on_exit(): подавлено: %s", _ex)
                if not bot.is_closed():
                    asyncio.run_coroutine_threadsafe(bot.close(), loop)
        except Exception as _ex:
            _log.debug("cleanup_on_exit(): подавлено: %s", _ex)
    except Exception as e:
        print(f"[ОЧИСТКА] Ошибка очистки: {e}")

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного выключения"""
    name = signal.Signals(signum).name if signum in signal.Signals._value2member_map_ else str(signum)
    print(f"[СИГНАЛ] Получен сигнал {signum} ({name}), выполняется очистка...")
    _record_run('stop', reason=f'signal_{name}', signal=signum)
    cleanup_on_exit()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup_on_exit)

async def send_panel_link(url):
    import json as _json
    panel_url = url

    for guild in bot.guilds:
        try:
            panel_ch = discord.utils.get(guild.text_channels, name="hakumo-panel")
            if not panel_ch:
                for old_name in ["panel-link", "hakumo-panel", "Hakumo-panel"]:
                    panel_ch = discord.utils.get(guild.text_channels, name=old_name)
                    if panel_ch:
                        await panel_ch.edit(name="hakumo-panel")
                        break
                if not panel_ch:
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    }
                    role = guild.get_role(ALERT_ROLE_ID) if ALERT_ROLE_ID else None
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(read_messages=True)
                    panel_ch = await guild.create_text_channel("hakumo-panel", overwrites=overwrites)
                    print(f"[ИНФО] Канал hakumo-panel создан: {guild.name}")
            async for msg in panel_ch.history(limit=10):
                if msg.author == bot.user:
                    await msg.delete()
            embed = discord.Embed(
                color=0xc8922a,
                timestamp=discord.utils.utcnow()
            )
            embed.set_author(
                name="Hakumo — Управление панелью",
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
                text="Hakumo Panel • Обновляется при каждом запуске",
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
                magic = f.read(4)
            # ВАЖНО: сигнатура зависит от платформы! Раньше проверяли только
            # Windows 'MZ' — из-за этого на Linux валидный ELF-бинарь
            # cloudflared удалялся как «битый», и туннель не работал никогда.
            if is_win:
                return magic[:2] == b'MZ'          # PE-файл Windows
            return magic[:4] == b'\x7fELF'          # ELF-файл Linux/macOS
        except Exception:
            return False

    for name in ["cloudflared.exe", "cloudflared_new.exe", "cloudflared"]:
        p = os.path.join(base_dir, name)
        if is_valid_exe(p):
            return p
        elif os.path.exists(p):
            try: os.remove(p)
            except Exception as _ex:
                _log.debug("_get_cloudflared_binary(): подавлено: %s", _ex)

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
            except Exception as _ex:
                _log.debug("_get_cloudflared_binary(): подавлено: %s", _ex)
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
            cmd.extend(["--url", "http://127.0.0.1:5001"])
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
    print("[CLOUDFLARE] Если проблема продолжается, добавьте в .env: DISABLE_TUNNEL=1")


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
            except Exception as _ex:
                _log.debug("_monitor_voice(): подавлено: %s", _ex)
        elif time.time() - last_ping > 240:
            try:
                if not vc.is_playing():
                    import io
                    delete = io.BytesIO(b'\x00' * 3840)
                    source = discord.PCMAudio(delete)
                    vc.play(source)
                last_ping = time.time()
            except Exception as _ex:
                _log.debug("_monitor_voice(): подавлено: %s", _ex)

@bot.event
async def on_disconnect():
    # Разрыв шлюза Discord: короткие — НОРМА (Discord сам рвёт связь,
    # discord.py тут же переподключается). Пишем, чтобы в логах было
    # видно: «отключался и вернулся», а не «пропал неизвестно зачем».
    # ЗАПАСНОЙ обработчик: когда загружен анти-краш (error_handler.py),
    # он перекрывает этот и ведёт ПОЛНЫЙ учёт (обрывы, resume, простой,
    # алерты). Здесь остаётся фолбэк на случай, если анти-краш не грузится.
    print("[СЕТЬ] Соединение с Discord потеряно — переподключаюсь...")
    _log.warning("Соединение с Discord потеряно (автопереподключение)")


@bot.event
async def on_resumed():
    print("[СЕТЬ] Соединение восстановлено (RESUME) — события не потеряны")
    _log.info("Соединение с Discord восстановлено (resume)")


# Сколько ждём синк команд, прежде чем признать его зависшим. Обычный
# синк укладывается в 1–5 секунд; 180с — с огромным запасом на ретраи
# внутри full_sync (3 попытки × 2с паузы на каждый скоуп).
SYNC_TIMEOUT_SEC = int((os.environ.get('SYNC_TIMEOUT_SEC', '') or '180').strip() or 180)


async def _sync_commands_bg():
    """Синк слеш-команд ФОНОМ, с таймаутом — не блокирует запуск бота.

    Любой исход (успех, ошибка, зависание) не мешает боту работать:
    статус, голос и веб-панель поднимаются независимо в on_ready.
    """
    from services.sync_filtered import full_sync as _full_sync
    # Честно пишем, КУДА команды попадают. Жалоба «у создателя бота не
    # грузятся команды» почти всегда про одно из двух: команды гильдовые и
    # живут только на MAIN_GUILD_ID/EXTRA_GUILD_IDS (на прочих серверах бот
    # их стирает), либо меню в лёгком составе и в нём всего несколько имён.
    # Без этой строки причину видно только в data/sync_last.json.
    try:
        from config import Config as _Cfg
        _ids = [o.id for o in _Cfg.guild_objects()]
    except Exception as _cfg_ex:
        _ids = []
        _log.debug('цели синка не определить: %s', _cfg_ex)
    try:
        import slash_budget as _sb
        _full_menu = _sb.full_menu_mode()
    except Exception:
        _full_menu = False
    _where = ', '.join(str(i) for i in _ids) or 'ГЛОБАЛЬНО (Discord показывает с задержкой до часа)'
    print(f'[СИНХРОНИЗАЦИЯ] Режим меню: '
          f'{"полный (BOT_FULL=1)" if _full_menu else "лёгкий (кураторский список)"}; '
          f'команды ставим на: {_where}')
    if _ids:
        _log.info('Команды регистрируются гильдовыми на серверах: %s — там они '
                  'видны сразу. На остальных серверах бот их стирает; нужно '
                  'там меню — добавьте сервер в EXTRA_GUILD_IDS в .env', _where)
    else:
        _log.info('MAIN_GUILD_ID не задан — команды регистрируются глобально, '
                  'Discord показывает их с задержкой до часа')
    if not _full_menu:
        _log.info('Меню в лёгком составе: в Discord видно только кураторский '
                  'список, /update при этом живёт в ЛС бота. Полный состав — '
                  'BOT_FULL=1 в .env или кнопка «Вернуть все» на странице '
                  '«Команды» панели')
    try:
        _n = len(await asyncio.wait_for(_full_sync(bot), timeout=SYNC_TIMEOUT_SEC))
        print(f'[СИНХРОНИЗАЦИЯ] Slash команды синхронизированы: {_n}')
        _log.info('Синхронизация слеш-команд завершена: %s команд', _n)
    except asyncio.TimeoutError:
        print(f'[СИНХРОНИЗАЦИЯ] ⚠ Не уложилась в {SYNC_TIMEOUT_SEC}с — '
              f'пропускаю. Бот РАБОТАЕТ, в Discord осталось прежнее меню '
              f'команд. Причина обычно внешняя: rate limit Discord или сеть. '
              f'Повторить вручную — кнопка «Синхронизировать» в веб-панели.')
        _log.warning('Синк команд не уложился в %sс — бот продолжает работу '
                     'со старым меню', SYNC_TIMEOUT_SEC)
        try:
            from services.sync_filtered import note_sync_error as _nse
            _nse(bot, TimeoutError(f'таймаут {SYNC_TIMEOUT_SEC}с'),
                 mode='on-ready-timeout')
        except Exception as _nse_ex:
            _log.debug('note_sync_error(timeout): %s', _nse_ex)
    except Exception as e:
        print(f'[СИНХРОНИЗАЦИЯ] Ошибка: {e} — бот продолжает работу')
        # причину видно и в панели (sync_last.json), не только в консоли
        try:
            from services.sync_filtered import note_sync_error as _nse
            _nse(bot, e, mode='on-ready-failed')
        except Exception as _nse_ex:
            _log.warning("on_ready(): не записали ошибку синка в sync_last.json: %s", _nse_ex)


@bot.event
async def on_ready():
    global _synced
    if not _synced:
        _synced = True
        # Команды живут НА СЕРВЕРЕ (guild-команды): мгновенно появляются
        # и мгновенно исчезают при выключении в панели. Выключенные
        # («Команды вкл/выкл») в Discord вообще не попадают.
        #
        # ВАЖНО (инцидент 30.08 «бот не включается»): синк уходит ФОНОВОЙ
        # задачей и НЕ держит on_ready. Раньше здесь стояло `await
        # full_sync(bot)` — а у синка нет своего таймаута: он ходит в
        # Discord bulk-upsert'ами, и один залипший запрос (429 с длинным
        # retry_after, моргнувшая сеть, туннель) вешал on_ready НАВСЕГДА.
        # Всё, что идёт ниже, не выполнялось никогда: бот не выставлял
        # статус (в Discord выглядел офлайн — «не включается»), не
        # подключался к голосовому, и главное — не звал
        # web.app.set_bot_instance(bot), поэтому веб-панель не видела бота.
        # Логи при этом обрывались на строке фоновой задачи тикетов, будто
        # «всё зависло». Теперь падение/зависание синка — это просто
        # предупреждение в логе: бот остаётся живым и управляемым.
        bot.loop.create_task(_sync_commands_bg())
        # Куча к этому моменту построена: замораживаем стартовый граф и
        # делаем сборки редкими — мультисекундные паузы GC рвали цикл
        # (инцидент 30.08: зависания 6–10 сек каждые ~3 мин, стек-монитор
        # видел только «виновник уже завершился»).
        try:
            from error_handler import gc_stabilize
            gc_stabilize()
        except Exception as _ex:
            _log.warning("on_ready(): GC-стабилизация не удалась: %s", _ex)
        bot.loop.create_task(_monitor_voice())
        # Фоновая дозагрузка участников в кэш (раз в 20с, по одной гильдии) —
        # чтобы поиск/пикеры/профили панели видели и тех, кого «нет в листе».
        try:
            from services.member_sync import start_member_sync
            start_member_sync(bot)
        except Exception as _ex:
            _log.debug("on_ready(): member_sync: %s", _ex)
        # Если только что кончило самообновление (/update) — отчитаться в канал
        try:
            from services import self_update as _SU
            bot.loop.create_task(_SU.announce_pending(bot, os.path.abspath('.')))
        except Exception as _ex:
            _log.debug("on_ready(): announce_pending: %s", _ex)
    print(f"[ОК] {bot.user} активен | {len(bot.guilds)} серверов")

    _cfg_file = 'data/bot_config.json'
    _status = discord.Status.online   # дефолт — зелёный: idle выглядел как «бот отключился»
    _activity_type = discord.ActivityType.watching   # «Смотрит Hakumo» — заказ владельца 30.08
    _activity_text = 'Hakumo'
    try:
        # чтение конфига статуса — в рабочем потоке (не блокируем event loop)
        from services.async_io import load_json_async as _lj
        _cfg = await _lj(_cfg_file, {}, log=_log) or {}
        if _cfg:
            _status_map = {'online': discord.Status.online, 'idle': discord.Status.idle, 'dnd': discord.Status.dnd, 'invisible': discord.Status.invisible}
            _type_map = {'listening': discord.ActivityType.listening, 'playing': discord.ActivityType.playing, 'watching': discord.ActivityType.watching, 'competing': discord.ActivityType.competing}
            _status = _status_map.get(_cfg.get('status', 'online'), discord.Status.online)
            _activity_type = _type_map.get(_cfg.get('activity_type', 'watching'), discord.ActivityType.watching)
            # пустая строка в конфиге не должна оставлять бота без подписи
            _activity_text = str(_cfg.get('activity_text', 'Hakumo') or '').strip()[:80] or 'Hakumo'
    except Exception as _ex:
        _log.debug("on_ready(): подавлено: %s", _ex)

    # Каждый шаг ниже — В СВОЁМ try и с таймаутом: on_ready обязан дойти
    # до конца (инцидент 30.08). Один зависший сетевой вызов не должен
    # оставлять бота без статуса и — главное — без связи с веб-панелью.
    try:
        await asyncio.wait_for(bot.change_presence(
            activity=discord.Activity(type=_activity_type, name=_activity_text),
            status=_status
        ), timeout=30)
        print(f"[ОК] Статус: {_status} | Активность: {_activity_text}")
    except asyncio.TimeoutError:
        print("[СТАТУС] ⚠ Discord не ответил за 30с — статус не выставлен, "
              "бот продолжает работу")
        _log.warning("on_ready(): change_presence не уложился в 30с")
    except Exception as _ex:
        print(f"[СТАТУС] ⚠ Не удалось выставить статус: {_ex}")
        _log.warning("on_ready(): change_presence: %s", _ex)

    try:
        channel = bot.get_channel(VOICE_CHANNEL_ID) if VOICE_CHANNEL_ID else None
        if channel and isinstance(channel, discord.VoiceChannel):
            vc = discord.utils.get(bot.voice_clients, guild=channel.guild)
            if not vc:
                try:
                    await asyncio.wait_for(channel.connect(self_deaf=False),
                                           timeout=60)
                    print(f"[ОК] Подключен к голосовому каналу: {channel.name}")
                except asyncio.TimeoutError:
                    print("[ОШИБКА] Голосовой канал не ответил за 60с — пропускаю")
                except Exception as e:
                    print(f"[ОШИБКА] Ошибка подключения к голосу: {e}")
    except Exception as _ex:
        _log.warning("on_ready(): голосовое подключение: %s", _ex)

    # Стартовые роли из config/role_seed.json — применяем один раз при старте
    # бота (роли персонала для уровней/лимитов + роль бана), чтобы выкатка
    # на VPS сразу подняла настройки владельца. Панель делает то же у себя.
    try:
        from services.role_seed import apply_role_seed
        # боевой gid: MAIN_GUILD_ID, если бот реально в нём, иначе первая
        # гильдия (так punish-роли и action_acl применятся, даже когда
        # MAIN_GUILD_ID в .env ещё не прописан на VPS).
        _seed_gid = 0
        try:
            from config import Config as _Cfg
            _mg = int(getattr(_Cfg, "MAIN_GUILD_ID", 0) or 0)
            if _mg and bot.get_guild(_mg):
                _seed_gid = _mg
            elif bot.guilds:
                _seed_gid = bot.guilds[0].id
        except Exception:
            _seed_gid = int(getattr(bot.guilds[0], "id", 0) or 0) if bot.guilds else 0
        _rep = apply_role_seed(guild_id=_seed_gid or None)
        if _rep.get("applied") and (_rep.get("role_map_added")
                                    or _rep.get("punish_added")
                                    or _rep.get("action_acl_actions")):
            print(f"[РОЛИ] Сид применён: персонал {_rep.get('role_map_added')}, "
                  f"роли наказаний {_rep.get('punish_added')}, "
                  f"разрешения действий {_rep.get('action_acl_actions')}")
    except Exception as _ex:
        _log.debug("on_ready(): role_seed: %s", _ex)

    # Связь с веб-панелью — САМОЕ ВАЖНОЕ в хвосте on_ready: без неё панель
    # показывает «бот выключен», хотя он в сети. Держим отдельно и защищённо.
    try:
        from web.app import set_bot_instance
        set_bot_instance(bot)
        print("[ВЕБ] Панель подключена к боту")
    except Exception as _ex:
        print(f"[ВЕБ] ⚠ Панель не получила бота: {_ex}")
        _log.error("on_ready(): set_bot_instance: %s", _ex)

    _tunnel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tunnel_url.txt")
    if not getattr(bot, '_panel_link_sent', False) and os.path.exists(_tunnel_path):
        try:
            # чтение файла со ссылкой — в рабочем потоке (event loop не встаёт)
            import asyncio as _aio_t
            _url = (await _aio_t.to_thread(
                lambda: open(_tunnel_path, "r", encoding="utf-8").read())).strip()
            if _url:
                await send_panel_link(_url)
                bot._panel_link_sent = True
        except Exception as _e:
            print(f"[ОШИБКА] Отправка ссылки панели: {_e}")

async def load_cogs():
    # Какие модули грузить — решает cogs_policy (MOD_ONLY / DISABLED_COGS /
    # EXTRA_COGS из .env). Хелперы (__init__, embed_utils…) там же.
    from cogs_policy import select_from_environment
    # Слеш-бюджет: Discord ограничивает глобальное меню 100 командами —
    # после каждого модуля дерево чистится, всё лишнее живёт на префиксе.
    import slash_budget
    from slash_budget import apply_slash_budget

    try:
        import error_handler
        await error_handler.setup(bot)
        log.info("Централизованный обработчик ошибок загружен")
    except Exception as e:
        log.error(f"Ошибка загрузки обработчика ошибок: {e}")

    bot.remove_command('help')

    all_files = [f for f in os.listdir("./cogs") if f.endswith(".py")]
    cog_files, disabled_files = select_from_environment(all_files)
    if disabled_files:
        log.info(f"Модули отключены ({len(disabled_files)}): {', '.join(disabled_files)}")
    log.info(f"Загружаю {len(cog_files)} из {len(all_files)} модулей cogs/")
    for filename in cog_files:
        ext = f"cogs.{filename[:-3]}"
        log.info(f"Загрузка: {filename}")
        try:
            await asyncio.wait_for(bot.load_extension(ext), timeout=20)
            apply_slash_budget(bot.tree)
            log.info(f"Загружено: {filename}")
        except asyncio.TimeoutError:
            log.error(f"Таймаут кога (20с): {filename}")
        except Exception as e:
            import traceback
            log.error(f"Ошибка загрузки кога ({filename}): {e}")
            traceback.print_exc()

    _kept, _pruned = apply_slash_budget(bot.tree)
    try:
        from services.text_format import spell as _spell
    except Exception:                       # текстовый хелпер не критичен
        def _spell(n, one, few, many):      # запасной вариант без склонений
            return f'{n} {many}'

    # честный счётчик: сколько команд реально отвечает на префикс «!»
    # (гибридные команды живут и в меню, и на префиксе). Раньше здесь
    # писался итог ПОСЛЕДНЕГО прохода чистки (0) — вводило в заблуждение.
    _prefix_total = len({c.name for c in bot.commands})
    if slash_budget.full_menu_mode():
        log.info(
            f"Слеш-меню: {_spell(len(_kept), 'команда', 'команды', 'команд')}"
            f" — полный состав, лимит Discord 100"
            + (f" (лишние {_spell(len(_pruned), 'команда', 'команды', 'команд')}"
               f" — на префикс «!»)" if _pruned else "")
        )
    else:
        # ВАЖНО: префиксные «!»-команды в этом боте ОТКЛЮЧЕНЫ целиком
        # (bot.process_commands = _no_prefix_commands, заказ 2026-08-28).
        # Раньше строка обещала «ещё N команд доступны через префикс «!»» —
        # владелец шёл пробовать !варн, ничего не происходило, и это
        # выглядело как «бот не работает». Пишем правду: остальные команды
        # СПЯТ, вернуть их можно только в слеш-меню.
        log.info(
            f"Слеш-меню: {_spell(len(_kept), 'команда', 'команды', 'команд')}"
            f" — лёгкий состав (кураторский список). Остальные "
            f"{_spell(_prefix_total, 'команда спит', 'команды спят', 'команд спят')}"
            f": префикс «!» отключён, в меню их нет. Включить все — "
            f"BOT_FULL=1 в .env или кнопка «Вернуть все» на странице "
            f"«Команды» панели"
        )
    if len(_kept) >= slash_budget.WARN_AT:
        log.warning(f"Слеш-меню почти полное ({len(_kept)}/100) — пора пересмотреть KEEP_SLASH")

async def _bridge_loop(bot):
    """Пульс бота для веб-панели, работающей ОТДЕЛЬНЫМ процессом.

    Раз в ~5 секунд пишет data/bot_state.json (статус, пинг, гильдии) и
    обновляет дисковый снимок ролей data/bot_roles_<gid>.json — только когда
    роли реально изменились. Панель читает эти файлы из любого процесса
    (services/bot_bridge): без моста отдельная панель (start_panel, gunicorn,
    VDS) всегда видела bot_instance=None и писала «Бот офлайн», даже когда
    бот работал. Файлы крошечные, диск не дёргается.
    """
    from services import bot_bridge as _bb
    while True:
        try:
            if bot is None:
                _bb.write_state('offline')
            else:
                try:
                    closed = bool(bot.is_closed())
                except Exception:
                    closed = False
                if closed:
                    _bb.write_state('offline')
                    await asyncio.sleep(5)
                    continue
                guilds = list(getattr(bot, 'guilds', None) or [])
                if guilds and bot.is_ready():
                    lat_ms = None
                    try:
                        _lat = getattr(bot, 'latency', None)
                        if _lat is not None:
                            lat_ms = round(float(_lat) * 1000, 1)
                    except Exception:
                        lat_ms = None
                    _bb.write_state(
                        'online', latency_ms=lat_ms,
                        guilds=[{'id': str(g.id),
                                 'name': str(getattr(g, 'name', '') or ''),
                                 'member_count': int(getattr(g, 'member_count', 0) or 0)}
                                for g in guilds])
                    # Роли и каналы меняются редко: снимки пишутся по сигнатуре
                    # (только реальные изменения) — диск не дёргается.
                    for g in guilds:
                        try:
                            _bb.write_roles(g.id,
                                            getattr(g, 'roles', None) or [])
                            _bb.write_channels(g.id,
                                               getattr(g, 'channels', None) or [])
                        except Exception as _r_ex:
                            log.debug('_bridge_loop: роли/каналы %s: %s',
                                      g.id, _r_ex)
                else:
                    _bb.write_state(
                        'starting',
                        guilds=[{'id': str(g.id),
                                 'name': str(getattr(g, 'name', '') or ''),
                                 'member_count': int(getattr(g, 'member_count', 0) or 0)}
                                for g in guilds])
        except Exception as _ex:
            log.debug('_bridge_loop: %s', _ex)
        await asyncio.sleep(5)


async def main():
    # ПЕРВАЯ строка запуска — какой код вообще работает. Инцидент 30.08:
    # /update со стандартным источником (main, без фиксов) молча откатил
    # бота на старую версию — и в логе не было ни одного признака этого.
    try:
        from services.startup_info import version_stamp
        _vs = version_stamp(os.path.abspath('.'))
        print(f"[ВЕРСИЯ] Код: {_vs}")
        _log.info("ВЕРСИЯ КОДА: %s", _vs)
    except Exception as _ex:
        _log.debug("version_stamp(): %s", _ex)

    # Предупреждения о среде: три главные причины «странных» зависаний
    # (инцидент 30.08: Downloads + вложенная папка + Python 3.14)
    try:
        from error_handler import environment_warnings
        for msg in environment_warnings(os.path.abspath('.')):
            print(f"[СРЕДА] ⚠ {msg}")
            _log.warning("СРЕДА: %s", msg)
    except Exception as _ex:
        _log.debug("environment_warnings(): %s", _ex)

    # Журнал жизненного цикла: старт (и предыдущая сессия видна в файле)
    try:
        first = True
        if os.path.exists(_RUN_LOG):
            first = False
        _record_run('start', first_run=first)
        print("[ЖИЗНЕННЫЙ ЦИКЛ] Старт записан в data/run_log.json"
              " (перезапуски теперь не «внезапные» — видно причину)")
    except Exception as _ex:
        log.debug('main(): run-log start: %s', _ex)

    # Сторож памяти: раз в минуту, до OOM-киллера
    try:
        asyncio.create_task(_memory_watchdog())
    except Exception as _ex:
        log.debug('main(): memory watchdog: %s', _ex)

    # Разовый «чистый старт» (заказ владельца 2026-08): стереть все логи
    # и ГАРАНТИРОВАННО выключить защиту — старые конфиги на диске могли
    # хранить enabled: true ещё с эпохи «всё включено» (отсюда сюрпризы
    # вида «за спам отлетел»). Маркер data/.freshstart_v1.json защищает
    # от повтора: всё, что хозяин включит потом, никто не трогает.
    try:
        _root = os.path.dirname(os.path.abspath(__file__))
        from services import fresh_start as _fs
        _rep = _fs.run_once(_root)
        if _rep:
            print('[СБРОС] Чистый старт: защита выключена (%s), логов стёрто: %d шт.'
                  % (', '.join(_rep['disabled']) or 'уже была выключена',
                     len(_rep['wiped_files'])))
    except Exception as _e:
        print(f'[СБРОС] Чистый старт не выполнен: {_e}')

    # ─── Предстартовая проверка настроек и соединений (preflight) ──
    # Единая наглядная сводка: токен, владелец, серверы, БД, папки,
    # порты, хардкод-ID и AI-ключи. Ошибки (error) критичны для работы,
    # предупреждения (warn) — необязательные функции. Network-проверка
    # добавится ниже, когда сделаем TCP-тест до Discord.
    try:
        from services import preflight as _pf
        _facts = {}
        # БД: реально ли открывается на запись (путь из Config.DB_PATH)
        try:
            import sqlite3 as _sqlite3
            from config import Config as _Cfg
            os.makedirs(os.path.dirname(_Cfg.DB_PATH), exist_ok=True)
            _c = _sqlite3.connect(_Cfg.DB_PATH, timeout=5)
            _c.execute("SELECT 1")
            _c.close()
            _facts['db_ok'] = True
            _facts['db_path'] = os.path.relpath(_Cfg.DB_PATH) or 'data/bot.db'
        except Exception as _dbex:
            _facts['db_ok'] = False
            _log.debug('preflight db: %s', _dbex)
        # Папки данных/логов
        try:
            _need = [_BASE_DIR + '/data', _BASE_DIR + '/logs']
            _facts['dirs_ok'] = all(os.path.isdir(d) or os.access(_BASE_DIR, os.W_OK)
                                    for d in _need)
            _facts['dirs'] = ['data', 'logs']
        except Exception:
            _facts['dirs_ok'] = True
        # Порты панели/WS
        try:
            _facts['panel_port'] = int(os.environ.get('PORT', '') or 0) or 5001
            _facts['ws_port'] = int(os.environ.get('WS_PORT', '') or 0) or 8765
        except Exception as _port_ex:
            log.debug('preflight: порты панели/WS не прочитаны: %s', _port_ex)
        # Хардкод-ID из config.py (дефолты с сервера разработки)
        try:
            from config import Config as _Cfg2
            _facts['hardcoded_ids'] = {
                'LOG_CHANNEL_ID': _Cfg2.LOG_CHANNEL_ID,
                'APPLY_CHANNEL_ID': _Cfg2.APPLY_CHANNEL_ID,
                'REQUIRED_ROLE_ID': _Cfg2.REQUIRED_ROLE_ID,
            }
        except Exception:
            _facts['hardcoded_ids'] = {}
        # Музыка (/play) полностью удалена из проекта (2026-09-01): коги,
        # ffmpeg-бутстрап и веб-страница снесены — диагностика ffmpeg больше
        # не нужна (факт в отчёт не добавляем, preflight его не печатает).
        _results = _pf.run_checks(facts=_facts)
        print("[ПРОВЕРКА] Предстартовая диагностика настроек:")
        print(_pf.format_report(_results))
        if _pf.count_errors(_results):
            log.warning("Preflight: критичных замечаний — %d (см. [ОШИБКА] выше)",
                        _pf.count_errors(_results))
        if _pf.count_warns(_results):
            log.info("Preflight: необязательных замечаний — %d (см. [!] выше)",
                     _pf.count_warns(_results))
    except Exception as _ex:
        log.debug('preflight: %s', _ex)

    from web.app import app, set_bot_instance
    set_bot_instance(bot)
    # Пульс состояния бота → data/bot_state.json + снимки ролей: чтобы
    # панель, запущенная отдельным процессом (start_panel, gunicorn, VDS),
    # видела «бот онлайн» и живые роли, а не вечное «Бот офлайн».
    try:
        asyncio.create_task(_bridge_loop(bot))
    except Exception as _ex:
        log.debug('main(): bridge loop: %s', _ex)
    _start_web_server(app)
    print("[ВЕБ] Веб панель: http://localhost:5001")
    _start_tunnel_sidecar()

    try:
        from web.websocket_server import start_websocket_thread
        _ws_host = (os.environ.get('WS_HOST', '') or '').strip() or '0.0.0.0'
        _ws_port = int(os.environ.get('WS_PORT', '') or 0) or 8765
        start_websocket_thread(host=_ws_host, port=_ws_port)
        log.info("WebSocket сервер запущен на %s:%s", _ws_host, _ws_port)
    except Exception as e:
        log.warning(f"WebSocket сервер не запущен: {e}")

    # Старый «случайный» quick-туннель (trycloudflare-адрес менялся каждый
    # запуск) теперь ВЫКЛЮЧЕН: у панели постоянный домен, его поднимает
    # _start_tunnel_sidecar выше (или служба Windows). Вернуть старое
    # поведение можно через QUICK_TUNNEL=1 в .env.
    _quick_raw = (os.environ.get('QUICK_TUNNEL', '') or '').strip().lower()
    if _quick_raw in ('1', 'true', 'yes', 'on'):
        def delayed_tunnel():
            import time
            time.sleep(3)
            start_tunnel()
        threading.Thread(target=delayed_tunnel, daemon=True).start()
    else:
        # Постоянного домена пока нет и quick-туннель выключен — убираем
        # старую случайную ссылку, чтобы бот не постил её в канал панели.
        from services import named_tunnel as _nt
        _root = os.path.dirname(os.path.abspath(__file__))
        if not _nt.find_config(_root):
            _nt.drop_stale_url(_root)

    print("[БОТ] Запускается... (загрузка когов -> вход в Discord)")
    async with bot:
        print("[БОТ] Коги загружаются...")
        await load_cogs()
        # Выключенные владельцем команды сразу прячем из slash-меню
        # (парковка — включение обратно без перезагрузки бота).
        try:
            from services import command_switches as _csw
            _hid, _res = _csw.apply_to_bot(bot)
            if _hid:
                log.info(f"Команды выключены владельцем: {', '.join(_hid)}")
        except Exception as _ex:
            log.warning(f"Переключатели команд не применены: {_ex}")
        # GC: к этому моменту загружены ВСЕ модули и построены их объекты —
        # замораживаем стартовый граф и делаем сборки редкими СЕЙЧАС, до
        # входа в Discord. Повторный gc_stabilize в on_ready — дешёвый
        # no-op поверх (frozen уже учтён). Раньше первая стабилизация
        # ждала on_ready, и тяжёлый стартовый граф успевал попасть под
        # первые gen2-сборки (инцидент 30.08: паузы 2–9 сек на старте).
        try:
            from error_handler import gc_stabilize as _gc_stab
            _gc_stab()
        except Exception as _ex:
            log.warning(f"GC-стабилизация после загрузки когов не удалась: {_ex}")
        _token = (os.getenv("TOKEN", "") or os.getenv("TОКEN", "")).strip()
        if not _token:
            print("[ОШИБКА] Токен не найден! Добавьте токен в .env файл (строка TOKEN=ваш_токен) "
                  "из https://discord.com/developers/applications")
            sys.exit(7)

        # ─── Предстартовая проверка связи с Discord ──────────────────
        # На VDS самая частая причина «бот молчит и не выходит в сеть» —
        # закрытый исходящий 443, фаервол/блокировка провайдера или нужен
        # прокси. Раньше бот просто бесконечно писал «Cannot connect to
        # host discord.com», не объясняя причину. Делаем разовый TCP-тест
        # до боевых хостов и сразу говорим, в чём дело.
        async def _check_discord_reachable():
            import socket
            hosts = ("discord.com", "gateway.discord.gg")
            ok = []
            for host in hosts:
                try:
                    fut = asyncio.open_connection(host, 443)
                    reader, writer = await asyncio.wait_for(fut, timeout=10)
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        _ = 'сокет уже закрыт — неважно для TCP-проверки'
                    ok.append(host)
                except Exception:
                    _ = f'{host} недоступен:443 — учтём в проверке ниже'
            return ok

        try:
            _reachable = await _check_discord_reachable()
        except Exception:
            _reachable = ["discord.com"]  # не смогли проверить — не мешаем старту
        if not _reachable:
            print("[СЕТЬ] ⚠ НЕТ ДОСТУПА к Discord (discord.com:443 / gateway не отвечают).")
            print("       Бот будет пытаться подключиться, но на этом VDS, похоже, "
                  "закрыт исходящий порт 443 или адрес блокируется провайдером/фаерволом.")
            print("       Что проверить на VDS:")
            print("         1) исходящий TCP 443 открыт (брандмауэр Windows/ufw/iptables);")
            print("         2) есть интернет: откройте https://discord.com в браузере сервера;")
            print("         3) если Discord заблокирован у хостера — нужен VPN/прокси на сервере.")
            _record_run('network_blocked', hosts='discord.com:443,gateway:443')
            log.error("Предстартовая проверка: Discord недоступен с этого сервера "
                      "(443 закрыт или блокировка) — нужен фаервол/VPN на VDS")
        else:
            print(f"[СЕТЬ] Доступ к Discord есть ({', '.join(_reachable)}:443)")

        # Anti-crash: автоперезапуск при сетевых сбоях, но с нарастающей паузой,
        # чтобы не долбить Discord во время сбоя (5 -> 10 -> 20 ... макс. 60 сек).
        _delay = 5
        _conn_fails = 0
        while True:
            try:
                print("[БОТ] Подключение к Discord...")
                await bot.start(_token)
                _delay = 5  # удачная сессия — сбросить паузу
                _conn_fails = 0
            except discord.LoginFailure:
                print("[ОШИБКА] Недействительный токен Discord! Исправьте TOKEN в .env — "
                      "перезапуск не поможет.")
                sys.exit(7)
            except Exception as e:
                _conn_fails += 1
                _emsg = str(e)
                print(f"[ОШИБКА] Бот отключился: {_emsg}")
                # Сетевая недоступность Discord — отдельный понятный совет
                # (на VDS это фаервол/блокировка, а не баг бота).
                if _conn_fails <= 3 and (
                        "Cannot connect to host" in _emsg
                        or "discord.com" in _emsg):
                    print("[СЕТЬ] ⚠ Похоже, сервер НЕ МОЖЕТ достучаться до Discord.")
                    print("       Проверьте на VDS: открыт ли исходящий порт 443, "
                          "есть ли интернет и не блокирует ли Discord провайдер/фаервол.")
                print(f"[БОТ] Автоперезапуск через {_delay} сек...")
                _uptime = int(time.time() - _RUN_START_TS)
                _record_run('reconnect', error=_emsg[:300],
                            uptime_sec=_uptime, retry_in=_delay)
                log.warning('Бот отключился после %dс аптайма: %s — '
                            'автопереподключение через %dс',
                            _uptime, e, _delay)
                await asyncio.sleep(_delay)
                _delay = min(60, _delay * 2)

if __name__ == "__main__":
    asyncio.run(main())
