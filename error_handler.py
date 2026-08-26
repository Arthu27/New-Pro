"""
HAKUMO ANTI-CRASH — централизованная защита от падений (PRO, полный набор)

Карта покрытия (аналоги Node.js anti-crash):
- Unhandled Rejection  → asyncio exception handler (задачи/колбэки)
- Uncaught Exception   → sys.excepthook + threading.excepthook
- Warning monitor      → перехват warnings библиотек (Deprecation и др.)
- Webhook-лог          → мгновенная отправка ошибок в скрытый dev-канал
- Детальный вывод      → файл:строка:функция + полный traceback (JSONL-файл)
- Фильтр ошибок        → глушение шумных/повторяющихся ошибок (антиспам)
- ShardError           → on_disconnect/on_shard_disconnect/on_resumed

+ Watchdog event-loop, circuit breaker по когам, детектор всплеска ошибок,
  сводка алертов в канал, персистентная статистика, конфиг в JSON,
  команда !anticrash и API для веб-панели.
"""

from logger import get_logger

_log = get_logger("error_handler")

import asyncio
import os
import json
import time
import math
import warnings as _warnings
import queue as _queue
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
import traceback
import sys
import threading
from datetime import datetime
from collections import deque

from logger import get_logger

log = get_logger("errors")

CONFIG_PATH = 'data/anticrash_config.json'
STATS_PATH = 'data/anticrash_stats.json'
DETAILS_PATH = 'data/anticrash_errors.jsonl'
DETAILS_MAX_BYTES = 5 * 1024 * 1024

DEFAULT_CONFIG = {
    # ── ядро ──
    "master_enabled": True,       # главный выключатель мониторинга
    "log_channel_id": 0,          # ID канала критических сводок (0 = выкл)
    "alerts_enabled": True,       # слать сводки в канал
    "max_alerts_per_hour": 6,     # лимит сводок в час
    "alert_flush_sec": 60,        # период отправки сводки
    # ── watchdog event-loop ──
    "loop_watchdog": True,
    "loop_lag_threshold": 5.0,
    "loop_check_interval": 2.0,
    # ── здоровье/статистика ──
    "health_log_interval": 600,
    "error_rate_alert": 60,
    "stats_persist": True,
    "stats_save_sec": 300,
    # ── circuit breaker ──
    "cog_breaker": True,
    "cog_error_threshold": 20,
    "cog_window_sec": 600,
    "cog_auto_reload": False,
    # ── warning-монитор (библиотеки) ──
    "warning_monitor": True,      # ловить warnings (Deprecation и др.)
    "warning_dedup_sec": 600,     # одинаковый warning — раз в период
    # ── фильтр шумных/повторных ошибок ──
    "filter_enabled": True,
    "filter_substrings": [
        "Unknown Message",                 # сообщение уже удалено
        "Unknown interaction",             # истёк interaction
        "already been acknowledged",       # двойной ответ на interaction
        "Unknown Channel",
        "Cannot send messages to this user",
        "Missing Access",
    ],
    "filter_suppress_repeat_sec": 600,    # повтор той же ошибки — в лог раз в период
    # ── webhook мгновенных ошибок ──
    "webhook_url": "",                    # URL скрытого dev-канала
    "webhook_enabled": False,
    "webhook_dedup_sec": 300,             # тот же тип ошибки — раз в период
    "webhook_max_per_hour": 20,
    # ── детальный файл ошибок ──
    "details_log_enabled": True,          # data/anticrash_errors.jsonl
    # ── монитор соединения (shards/websocket) ──
    "connection_watch": True,
    "disconnect_alert_threshold": 5,      # обрывов в окне → алерт
    "disconnect_window_sec": 600,
}

CONFIG_META = {
    "master_enabled":       ("Мастер-переключатель", "Весь мониторинг и алерты", "bool"),
    "log_channel_id":       ("ID канала алертов", "Куда слать критические сводки (0 — выкл.)", "int"),
    "alerts_enabled":       ("Алерты в Discord", "Разрешить отправку сводок в канал", "bool"),
    "max_alerts_per_hour":  ("Лимит алертов/час", "Анти-спам ограничение отправок", "int"),
    "alert_flush_sec":      ("Период сводки (сек)", "Как часто отправляется накопленная сводка", "int"),
    "loop_watchdog":        ("Watchdog цикла", "Отслеживать зависания event-loop", "bool"),
    "loop_lag_threshold":   ("Порог лага (сек)", "Лаг выше — считается зависанием", "float"),
    "loop_check_interval":  ("Шаг замера (сек)", "Как часто мерить лаг цикла", "float"),
    "health_log_interval":  ("Health-лог (сек)", "Период записи health-сводки в лог", "int"),
    "error_rate_alert":     ("Порог всплеска", "Ошибок/мин, при которых слать алерт", "int"),
    "stats_persist":        ("Сохранять статистику", "Писать статистику в файл", "bool"),
    "stats_save_sec":       ("Период записи (сек)", "Как часто сохранять статистику", "int"),
    "cog_breaker":          ("Circuit breaker", "Детект «бешеного» модуля по потоку ошибок", "bool"),
    "cog_error_threshold":  ("Порог ошибок кога", "Столько ошибок в окне = breaker", "int"),
    "cog_window_sec":       ("Окно breaker (сек)", "Период подсчёта ошибок кога", "int"),
    "cog_auto_reload":      ("Авто-reload кога", "Перезагружать модуль при срабатывании (осторожно)", "bool"),
    "warning_monitor":      ("Монитор предупреждений", "Ловить warning'и библиотек (DeprecationWarning и др.)", "bool"),
    "warning_dedup_sec":    ("Дедуп warning (сек)", "Одинаковое предупреждение — раз в период", "int"),
    "filter_enabled":       ("Фильтр шумных ошибок", "Глушить типовой мусор Discord («Unknown Message», «Unknown interaction»...)", "bool"),
    "filter_substrings":    ("Фразы для фильтра", "Ошибки с этими подстроками не спамят лог и алерты (по строке на фразу)", "list"),
    "filter_suppress_repeat_sec": ("Анти-повтор (сек)", "Одна и та же ошибка пишется в лог раз в этот период", "int"),
    "webhook_url":          ("Webhook URL", "URL скрытого dev-канала для мгновенных ошибок", "str"),
    "webhook_enabled":      ("Webhook включён", "Мгновенно слать новые ошибки в dev-канал", "bool"),
    "webhook_dedup_sec":    ("Дедуп webhook (сек)", "Одинаковая ошибка отправляется раз в период", "int"),
    "webhook_max_per_hour": ("Webhook лимит/час", "Анти-спам ограничение для webhook", "int"),
    "details_log_enabled":  ("Детальный JSONL", "Каждая ошибка с файлом:строкой → data/anticrash_errors.jsonl", "bool"),
    "connection_watch":     ("Монитор соединения", "Обрывы WebSocket (disconnect/shard) → статистика и алерты", "bool"),
    "disconnect_alert_threshold": ("Порог обрывов", "Столько обрывов в окне → алерт о нестабильности", "int"),
    "disconnect_window_sec": ("Окно обрывов (сек)", "Период подсчёта обрывов соединения", "int"),
}


def _cast_like(default, raw):
    """Привести значение к типу дефолтного конфига."""
    if isinstance(default, bool):
        if isinstance(raw, bool):
            return raw
        s = str(raw).strip().lower()
        if s in ('1', 'true', 'on', 'да', 'yes', 'вкл'):
            return True
        if s in ('0', 'false', 'off', 'нет', 'no', 'выкл'):
            return False
        raise ValueError("ожидается bool (вкл/выкл)")
    if isinstance(default, list):
        if isinstance(raw, list):
            return [str(x) for x in raw if str(x).strip()]
        s = str(raw).strip()
        if not s:
            return []
        try:
            v = json.loads(s)
            if isinstance(v, list):
                return [str(x) for x in v if str(x).strip()]
        except Exception as _ex:
            _log.debug("_cast_like(): подавлено: %s", _ex)
        return [x.strip() for x in s.split('\n') if x.strip()]
    if isinstance(default, int):
        v = int(float(str(raw).strip()))
        if v < 0:
            raise ValueError("ожидается число >= 0")
        return v
    if isinstance(default, float):
        v = float(str(raw).strip().replace(',', '.'))
        if v < 0:
            raise ValueError("ожидается число >= 0")
        return v
    return str(raw).strip()


def _loc_from_tb(tb) -> str:
    """Кадр с местом ошибки: файл:строка (функция) — приоритет коду проекта."""
    try:
        frames = traceback.extract_tb(tb)
        if not frames:
            return ""
        own = [f for f in frames
               if 'site-packages' not in f.filename and os.sep + 'discord' + os.sep not in f.filename]
        f = own[-1] if own else frames[-1]
        return f"{os.path.basename(f.filename)}:{f.lineno} ({f.name})"
    except Exception:
        return ""


class ErrorHandler:
    """Централизованный обработчик ошибок + anti-crash мониторинг (PRO)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = self._load_config()
        self.stats = self._load_stats()
        self.error_counts = self.stats['by_type']  # совместимость со старым API

        self._rate = deque(maxlen=2000)            # ts ошибок (ошибки/час, всплеск)
        self._cog_windows = {}                     # module -> deque(ts)
        self._breaker_state = {}                   # module -> {'tripped', 'reload_at'}
        self._alerts = []                          # очередь сводок в канал
        self._alerts_sent_ts = deque(maxlen=100)
        self._lag_recent = 0.0
        self._spike_alert_at = 0.0
        self._tasks = []

        self._repeat = {}                          # дедуп повторных ошибок
        self._warn_seen = {}                       # дедуп warning'ов
        self._webhook_q = _queue.Queue(maxsize=500)  # thread-safe → consumer в loop
        self._webhook_sent_ts = deque(maxlen=200)
        self._webhook_seen = {}                    # дедуп отправок
        self._webhook_session = None
        self._disconnects = deque(maxlen=200)
        self._disconnect_alert_at = 0.0

    # ────────────────────────────────────────────────────────────
    # Конфиг / статистика (диск)
    # ────────────────────────────────────────────────────────────
    def _load_config(self) -> dict:
        cfg = dict(DEFAULT_CONFIG)
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    user_cfg = json.load(f)
                for k in DEFAULT_CONFIG:
                    if k in user_cfg:
                        try:
                            cfg[k] = _cast_like(DEFAULT_CONFIG[k], user_cfg[k])
                        except Exception as _ex:
                            _log.debug("_load_config(): подавлено: %s", _ex)
        except Exception as e:
            log.error(f"Anti-crash: не удалось прочитать конфиг, используются значения по умолчанию: {e}")
        return cfg

    def save_config(self):
        try:
            os.makedirs('data', exist_ok=True)
            tmp = CONFIG_PATH + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CONFIG_PATH)
        except Exception as e:
            log.error(f"Anti-crash: не удалось записать конфиг: {e}")

    def update_config(self, key: str, value):
        if key not in DEFAULT_CONFIG:
            raise KeyError(f"неизвестный ключ: {key}")
        self.config[key] = _cast_like(DEFAULT_CONFIG[key], value)
        self.save_config()
        return self.config[key]

    def _fresh_stats(self) -> dict:
        return {
            'started_at': time.time(),
            'total_errors': 0,
            'critical': 0,
            'filtered': 0,
            'repeats_hidden': 0,
            'warnings_total': 0,
            'warnings': {},
            'disconnects': 0,
            'alerts_sent': 0,
            'alerts_dropped': 0,
            'webhook_sent': 0,
            'webhook_dropped': 0,
            'loop_lag_max': 0.0,
            'by_type': {},
            'by_command': {},
            'by_cog': {},
            'by_event': {},
            'breakers': {},
            'last_errors': [],
            'daily': {},
        }

    def _load_stats(self) -> dict:
        st = self._fresh_stats()
        try:
            if os.path.exists(STATS_PATH):
                with open(STATS_PATH, 'r', encoding='utf-8') as f:
                    old = json.load(f)
                for k, v in old.items():
                    if k == 'started_at':
                        continue
                    if k in st and isinstance(st[k], type(v)):
                        st[k] = v
        except Exception as _ex:
            _log.debug("_load_stats(): подавлено: %s", _ex)
        if not isinstance(st.get('last_errors'), list):
            st['last_errors'] = []
        return st

    def save_stats(self):
        if not self.config.get('stats_persist', True):
            return
        try:
            os.makedirs('data', exist_ok=True)
            tmp = STATS_PATH + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=1)
            os.replace(tmp, STATS_PATH)
        except Exception as _ex:
            _log.debug("save_stats(): подавлено: %s", _ex)

    def reset_stats(self):
        self.stats = self._fresh_stats()
        self.error_counts = self.stats['by_type']
        self._cog_windows.clear()
        self._breaker_state.clear()
        self._repeat.clear()
        self.save_stats()

    # ────────────────────────────────────────────────────────────
    # Регистрация
    # ────────────────────────────────────────────────────────────
    def setup(self):
        """Зарегистрировать все обработчики"""
        @self.bot.event
        async def on_command_error(ctx: commands.Context, error: commands.CommandError):
            await self.handle_command_error(ctx, error)

        @self.bot.event
        async def on_error(event: str, *args, **kwargs):
            exc = sys.exc_info()[1]
            if exc is None:
                return
            self.stats['by_event'][event] = self.stats['by_event'].get(event, 0) + 1
            self._log_error(f"Event error in '{event}': {exc}", exc, where=f"event:{event}", critical=True)

        # ── монитор соединения (аналог shardError) ──
        @self.bot.event
        async def on_disconnect():
            self._on_disconnect("gateway")

        @self.bot.event
        async def on_shard_disconnect(shard_id: int):
            self._on_disconnect(f"shard:{shard_id}")

        @self.bot.event
        async def on_resumed():
            log.info("Соединение с Discord восстановлено (session resumed)")

        @self.bot.event
        async def on_shard_resumed(shard_id: int):
            log.info(f"Shard {shard_id} восстановил сессию")

        tree = self.bot.tree

        async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            await self.handle_app_command_error(interaction, error)

        tree.on_error = on_app_command_error

        self._setup_anticrash()
        self._setup_warning_monitor()

        try:
            loop = asyncio.get_running_loop()
            self._tasks = [
                loop.create_task(self._register_commands()),
                loop.create_task(self._loop_watchdog_task()),
                loop.create_task(self._alert_flush_task()),
                loop.create_task(self._health_log_task()),
                loop.create_task(self._persist_task()),
                loop.create_task(self._webhook_task()),
            ]
        except RuntimeError as _ex:
            _log.debug("setup(): подавлено: %s", _ex)

        log.info("Anti-crash PRO активирован (watchdog, breaker, фильтр, webhook, warnings, shards)")

    async def _register_commands(self):
        try:
            await self.bot.add_cog(AntiCrashCog(self.bot, self))
        except Exception as e:
            log.error(f"Anti-crash: не удалось загрузить команды: {e}")

    def _setup_anticrash(self):
        """Uncaught Exception: asyncio-задачи, потоки, главный поток"""
        try:
            asyncio.get_running_loop().set_exception_handler(self._loop_exception_handler)
        except RuntimeError as _ex:
            _log.debug("_setup_anticrash(): подавлено: %s", _ex)

        def _sys_hook(exc_type, exc, tb):
            if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
                sys.__excepthook__(exc_type, exc, tb)
                return
            t = "".join(traceback.format_exception(exc_type, exc, tb))
            log.critical(f"НЕПЕРЕХВАЧЕННОЕ ИСКЛЮЧЕНИЕ (main thread):\n{t}")
            self._record_and_publish(exc_type.__name__, "main_thread", str(exc),
                                     critical=True, tb_text=t, loc=_loc_from_tb(tb))

        sys.excepthook = _sys_hook

        def _thread_hook(args: "threading.ExceptHookArgs"):
            if issubclass(args.exc_type, (KeyboardInterrupt, SystemExit)):
                return
            t = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
            tname = args.thread.name if args.thread else '?'
            log.critical(f"НЕПЕРЕХВАЧЕННОЕ ИСКЛЮЧЕНИЕ (поток {tname}):\n{t}")
            self._record_and_publish(args.exc_type.__name__, f"thread:{tname}", str(args.exc_value),
                                     critical=True, tb_text=t, loc=_loc_from_tb(args.exc_traceback))

        threading.excepthook = _thread_hook

    def _loop_exception_handler(self, loop: asyncio.AbstractEventLoop, context: dict):
        """Unhandled Rejection: исключения asyncio-задач — логируем, цикл жив."""
        exc = context.get("exception")
        msg = context.get("message", "asyncio error")
        if exc is not None:
            self._log_error(f"Asyncio task error: {msg} ({exc})", exc, where="asyncio:task", critical=True)
        else:
            log.error(f"Asyncio error: {msg}")
            self._record("AsyncioError", "asyncio:loop", msg)

    # ────────────────────────────────────────────────────────────
    # Warning-монитор (библиотеки/система)
    # ────────────────────────────────────────────────────────────
    def _setup_warning_monitor(self):
        """Перехват warnings.warn: Deprecation/Runtime и пр. → в лог и статистику."""
        orig = _warnings.showwarning

        def _hook(message, category, filename, lineno, file=None, line=None):
            try:
                if self.config.get('warning_monitor', True):
                    self._on_warning(category.__name__, str(message), filename, lineno)
            except Exception as _ex:
                _log.debug("_hook(): подавлено: %s", _ex)
            try:
                orig(message, category, filename, lineno, file=file, line=line)
            except Exception as _ex:
                _log.debug("_hook(): подавлено: %s", _ex)

        _warnings.showwarning = _hook
        self._orig_showwarning = orig

    def _on_warning(self, cat: str, msg: str, filename: str, lineno: int):
        key = f"{cat}|{msg[:80]}"
        now = time.time()
        last = self._warn_seen.get(key, 0)
        if now - last < float(self.config.get('warning_dedup_sec', 600)):
            self.stats['warnings_total'] += 1
            return
        self._warn_seen[key] = now
        self.stats['warnings_total'] += 1
        self.stats['warnings'][cat] = self.stats['warnings'].get(cat, 0) + 1
        log.warning(f"WARNING [{cat}] {os.path.basename(filename)}:{lineno} — {msg[:300]}")

    # ────────────────────────────────────────────────────────────
    # Монитор соединения (аналог shardError)
    # ────────────────────────────────────────────────────────────
    def _on_disconnect(self, kind: str):
        if not self.config.get('connection_watch', True):
            return
        now = time.time()
        self.stats['disconnects'] += 1
        self._disconnects.append(now)
        log.warning(f"Соединение с Discord потеряно ({kind}) — всего обрывов: {self.stats['disconnects']}")
        window = float(self.config.get('disconnect_window_sec', 600))
        thr = int(self.config.get('disconnect_alert_threshold', 5))
        recent = sum(1 for ts in self._disconnects if now - ts <= window)
        if recent >= thr and now - self._disconnect_alert_at > 600:
            self._disconnect_alert_at = now
            self.queue_alert(
                "Нестабильное соединение",
                f"**{recent}** обрывов WebSocket за {int(window // 60)} мин.\n"
                "Discord переподключается автоматически, но проверьте сеть/хостинг.",
            )

    # ────────────────────────────────────────────────────────────
    # Учёт ошибок (ядро)
    # ────────────────────────────────────────────────────────────
    def _record(self, err_type: str, where: str, message: str, critical: bool = False, loc: str = ""):
        s = self.stats
        s['total_errors'] += 1
        if critical:
            s['critical'] += 1
        s['by_type'][err_type] = s['by_type'].get(err_type, 0) + 1
        # Дневные корзины для графика за 7 дней (храним до 14)
        try:
            day = time.strftime('%Y-%m-%d', time.localtime())
            daily = s.setdefault('daily', {})
            daily[day] = daily.get(day, 0) + 1
            if len(daily) > 14:
                for old_day in sorted(daily.keys())[:-14]:
                    daily.pop(old_day, None)
        except Exception as _ex:
            _log.debug("_record(): подавлено: %s", _ex)
        self._rate.append(time.time())
        s['last_errors'].append({
            'ts': time.time(), 'type': err_type, 'where': where,
            'loc': loc, 'msg': (message or '')[:220], 'critical': bool(critical),
        })
        del s['last_errors'][:-30]

    def _is_filtered(self, text: str) -> bool:
        if not self.config.get('filter_enabled', True):
            return False
        tl = text.lower()
        return any(sub.lower() in tl for sub in self.config.get('filter_substrings', []))

    def _write_details(self, rec: dict):
        """Детальный вывод: каждая ошибка JSON-строкой (файл:строка, время, traceback)."""
        if not self.config.get('details_log_enabled', True):
            return
        try:
            os.makedirs('data', exist_ok=True)
            if os.path.exists(DETAILS_PATH) and os.path.getsize(DETAILS_PATH) > DETAILS_MAX_BYTES:
                os.replace(DETAILS_PATH, DETAILS_PATH + '.old')
            with open(DETAILS_PATH, 'a', encoding='utf-8') as f:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        except Exception as _ex:
            _log.debug("_write_details(): подавлено: %s", _ex)

    def _record_and_publish(self, err_type, where, message, *, critical=False, tb_text="", loc=""):
        """Единый конвейер: статистика + JSONL + webhook."""
        self._record(err_type, where, message, critical=critical, loc=loc)
        rec = {
            'ts': time.time(), 'type': err_type, 'where': where, 'loc': loc,
            'msg': (message or '')[:500], 'critical': bool(critical),
            'traceback': (tb_text or '')[-1500:],
        }
        self._write_details(rec)
        self._enqueue_webhook(rec)

    def _log_error(self, message: str, error: Exception, where: str = "", critical: bool = False):
        """Ошибка исключения: фильтр шума → анти-повтор → лог+traceback → jsonl+webhook."""
        raw = str(error)
        loc = _loc_from_tb(error.__traceback__)

        # 1) Фильтр шумных ошибок — только счётчик, без спама
        if self._is_filtered(f"{raw} {message}"):
            self.stats['filtered'] += 1
            return

        err_type = type(error).__name__
        self._record(err_type, where, message, critical=critical, loc=loc)

        # 2) Анти-повтор: полный лог — раз в filter_suppress_repeat_sec
        key = f"{err_type}|{where}|{raw[:60]}"
        now = time.time()
        ent = self._repeat.get(key)
        write_full = True
        if ent is not None:
            ent['count'] += 1
            if now - ent['last_log'] < float(self.config.get('filter_suppress_repeat_sec', 600)):
                write_full = False
                self.stats['repeats_hidden'] += 1
            else:
                ent['last_log'] = now
                log.error(f"{message}  (повторов подряд: {ent['count']})")
                ent['count'] = 0
        else:
            self._repeat[key] = {'count': 0, 'last_log': now}

        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        if write_full:
            log.error(message)
            log.error(f"Traceback ({loc}):\n{tb}")

        # 3) Детальный файл + webhook (первая/новая серия — сразу)
        self._write_details({
            'ts': now, 'type': err_type, 'where': where, 'loc': loc,
            'msg': raw[:500], 'message': message[:500],
            'critical': bool(critical), 'traceback': tb[-1500:],
        })
        if write_full:
            self._enqueue_webhook({
                'ts': now, 'type': err_type, 'where': where, 'loc': loc,
                'msg': raw[:500], 'critical': bool(critical),
                'traceback': tb[-1500:],
            })

        if critical and self.config.get('master_enabled', True):
            self.queue_alert(
                "Критическая ошибка",
                f"`{err_type}` — {where or 'система'} · `{loc}`\n{raw[:180]}",
            )

    def _count(self, error_type: str):
        self.stats['by_type'][error_type] = self.stats['by_type'].get(error_type, 0) + 1

    def _errors_in_window(self, window_sec: float) -> int:
        now = time.time()
        return sum(1 for ts in self._rate if now - ts <= window_sec)

    # ────────────────────────────────────────────────────────────
    # Webhook мгновенных ошибок (скрытый dev-канал)
    # ────────────────────────────────────────────────────────────
    def _enqueue_webhook(self, rec: dict):
        """Thread-safe постановка в очередь; реальная отправка — в loop-задаче."""
        if not self.config.get('webhook_enabled', False):
            return
        if not (self.config.get('webhook_url') or '').strip():
            return
        key = f"{rec['type']}|{rec['where']}|{rec['msg'][:60]}"
        now = time.time()
        if now - self._webhook_seen.get(key, 0) < float(self.config.get('webhook_dedup_sec', 300)):
            self.stats['webhook_dropped'] += 1
            return
        self._webhook_seen[key] = now
        try:
            self._webhook_q.put_nowait(rec)
        except _queue.Full:
            self.stats['webhook_dropped'] += 1

    async def _webhook_task(self):
        """Отправка очереди в webhook: дедуп уже пройден, здесь — лимит/час и сеть."""
        await self.bot.wait_until_ready()
        try:
            self._webhook_session = aiohttp.ClientSession()
            while not self.bot.is_closed():
                try:
                    while not self._webhook_q.empty():
                        rec = self._webhook_q.get_nowait()
                        await self._send_webhook(rec)
                except Exception as e:
                    log.error(f"Ошибка очереди webhook: {e}")
                await asyncio.sleep(3)
        finally:
            try:
                if self._webhook_session and not self._webhook_session.closed:
                    await self._webhook_session.close()
            except Exception as _ex:
                _log.debug("_webhook_task(): подавлено: %s", _ex)

    async def _send_webhook(self, rec: dict):
        url = (self.config.get('webhook_url') or '').strip()
        if not url:
            return
        now = time.time()
        while self._webhook_sent_ts and now - self._webhook_sent_ts[0] > 3600:
            self._webhook_sent_ts.popleft()
        if len(self._webhook_sent_ts) >= int(self.config.get('webhook_max_per_hour', 20)):
            self.stats['webhook_dropped'] += 1
            return
        ts_str = datetime.fromtimestamp(rec['ts']).strftime('%d.%m %H:%M:%S')
        embed = {
            'title': f"🔥 {rec['type']}" if rec.get('critical') else f"⚠️ {rec['type']}",
            'description': f"```\n{rec['msg'][:600]}\n```",
            'color': 0xE74C3C if rec.get('critical') else 0xF39C12,
            'fields': [
                {'name': 'Контекст', 'value': f"`{rec['where']}`", 'inline': True},
                {'name': 'Место', 'value': f"`{rec.get('loc') or '—'}`", 'inline': True},
                {'name': 'Время', 'value': f"`{ts_str}`", 'inline': True},
            ],
            'footer': {'text': 'HAKUMO anti-crash • мгновенный webhook'},
        }
        tb = (rec.get('traceback') or '').strip()
        if tb:
            embed['fields'].append({'name': 'Traceback', 'value': f"```py\n{tb[-900:]}\n```"})
        payload = {'username': 'HAKUMO ANTI-CRASH', 'embeds': [embed]}
        try:
            async with self._webhook_session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status in (200, 204):
                    self._webhook_sent_ts.append(now)
                    self.stats['webhook_sent'] += 1
                else:
                    self.stats['webhook_dropped'] += 1
                    log.error(f"Webhook HTTP {resp.status}")
        except Exception as e:
            self.stats['webhook_dropped'] += 1
            log.error(f"Webhook не доставлен: {e}")

    # ────────────────────────────────────────────────────────────
    # Circuit breaker по когам
    # ────────────────────────────────────────────────────────────
    def _track_cog(self, module: str):
        if not module or not self.config.get('cog_breaker', True):
            return
        now = time.time()
        window = float(self.config.get('cog_window_sec', 600))
        dq = self._cog_windows.setdefault(module, deque(maxlen=500))
        dq.append(now)
        recent = [ts for ts in dq if now - ts <= window]
        threshold = int(self.config.get('cog_error_threshold', 20))
        if len(recent) < threshold:
            return
        state = self._breaker_state.get(module)
        if state and now - state['tripped'] < window:
            return
        self._breaker_state[module] = {'tripped': now, 'reload_at': 0}
        dq.clear()
        self.stats['breakers'][module] = self.stats['breakers'].get(module, 0) + 1
        log.critical(f"CIRCUIT BREAKER: модуль {module} — {len(recent)} ошибок за {int(window)} сек!")
        self.queue_alert(
            "Circuit breaker сработал",
            f"Модуль `{module}` выдал **{len(recent)}** ошибок за {int(window // 60)} мин.\n"
            + ("Попытка авто-reload..." if self.config.get('cog_auto_reload') else
               "Авто-reload выключен — проверьте модуль вручную."),
        )
        if self.config.get('cog_auto_reload', False):
            asyncio.get_event_loop().create_task(self._try_reload(module))

    async def _try_reload(self, module: str):
        try:
            state = self._breaker_state.get(module)
            now = time.time()
            if state and state.get('reload_at') and now - state['reload_at'] < 600:
                return
            if state:
                state['reload_at'] = now
            await self.bot.reload_extension(module)
            log.warning(f"Anti-crash: модуль {module} перезагружен (auto-reload)")
            self.queue_alert("Авто-reload выполнен", f"Модуль `{module}` перезагружен успешно.")
        except Exception as e:
            log.error(f"Anti-crash: reload {module} не удался: {e}")
            self.queue_alert("Авто-reload не удался", f"`{module}`: {str(e)[:180]}")

    # ────────────────────────────────────────────────────────────
    # Сводки алертов в Discord-канал (очередь + лимит)
    # ────────────────────────────────────────────────────────────
    def queue_alert(self, title: str, desc: str):
        if not self.config.get('master_enabled', True):
            return
        if len(self._alerts) < 50:
            self._alerts.append({'title': title, 'desc': desc, 'ts': time.time()})

    async def _alert_flush_task(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(20)
        while not self.bot.is_closed():
            await asyncio.sleep(max(15, int(self.config.get('alert_flush_sec', 60))))
            try:
                await self._flush_alerts()
            except Exception as e:
                log.error(f"Ошибка отправки сводки алертов: {e}")

    async def _flush_alerts(self):
        if not self._alerts:
            return
        if not self.config.get('alerts_enabled', True):
            self.stats['alerts_dropped'] += len(self._alerts)
            self._alerts.clear()
            return
        ch_id = int(self.config.get('log_channel_id', 0) or 0)
        if not ch_id:
            self.stats['alerts_dropped'] += len(self._alerts)
            self._alerts.clear()
            return
        channel = self.bot.get_channel(ch_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(ch_id)
            except Exception:
                channel = None
        if channel is None:
            return

        now = time.time()
        while self._alerts_sent_ts and now - self._alerts_sent_ts[0] > 3600:
            self._alerts_sent_ts.popleft()
        if len(self._alerts_sent_ts) >= int(self.config.get('max_alerts_per_hour', 6)):
            self.stats['alerts_dropped'] += len(self._alerts)
            self._alerts.clear()
            log.warning("Anti-crash: лимит алертов/час исчерпан, сводка пропущена")
            return

        items, self._alerts = self._alerts[:10], self._alerts[10:]
        embed = discord.Embed(
            title="🛡 ANTI-CRASH — Критические события",
            color=0xD4AF37,
            timestamp=datetime.now(),
        )
        lines = []
        for it in items:
            t = datetime.fromtimestamp(it['ts']).strftime('%H:%M:%S')
            lines.append(f"**[{t}] {it['title']}**\n{it['desc']}")
        embed.description = "\n\n".join(lines)[:3900]
        if self._alerts:
            embed.set_footer(text=f"…и ещё {len(self._alerts)} событий • подробности в лог-файле")
        try:
            await channel.send(embed=embed)
            self._alerts_sent_ts.append(now)
            self.stats['alerts_sent'] += 1
        except Exception as e:
            log.error(f"Anti-crash: не удалось отправить в канал алертов: {e}")

    # ────────────────────────────────────────────────────────────
    # Watchdog event-loop
    # ────────────────────────────────────────────────────────────
    async def _loop_watchdog_task(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(30)
        last_alert = 0.0
        # Если пауза между тиками > 180с — это сон/гибернация ОС или заморозка контейнера, а не зависание event loop кодом
        MAX_SLEEP_DRIFT = 180.0
        while not self.bot.is_closed():
            if not self.config.get('loop_watchdog', True):
                await asyncio.sleep(5)
                continue
            iv = max(0.5, float(self.config.get('loop_check_interval', 2.0)))
            t0 = time.monotonic()
            await asyncio.sleep(iv)
            drift = (time.monotonic() - t0) - iv
            self._lag_recent = drift

            # Проверяем, не спала ли система (сон ноутбука / ПК / приостановка виртуалки)
            if drift > MAX_SLEEP_DRIFT:
                log.info(
                    f"[WATCHDOG] Система возобновила работу после сна / приостановки (~{drift:.1f} сек). "
                    "Пауза сна не считается зависанием event-loop."
                )
                await asyncio.sleep(2)
                continue

            if drift > float(self.config.get('loop_lag_threshold', 5.0)):
                if drift > self.stats.get('loop_lag_max', 0.0):
                    self.stats['loop_lag_max'] = round(drift, 2)
                log.critical(f"EVENT-LOOP ЗАВИСАНИЕ: цикл не отвечал {drift:.1f} сек!")
                if time.time() - last_alert > 300:
                    last_alert = time.time()
                    self.queue_alert(
                        "Зависание event-loop",
                        f"Цикл не отвечал **{drift:.1f} сек** — команды и ивенты в это время стояли.\n"
                        "Частая причина: тяжёлая синхронная операция (сеть/диск/CPU) в async-коде.",
                    )

    # ────────────────────────────────────────────────────────────
    # Health-лог + персист
    # ────────────────────────────────────────────────────────────
    async def _health_log_task(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(max(60, int(self.config.get('health_log_interval', 600))))
            if not self.config.get('master_enabled', True):
                continue
            ov = self.get_overview()
            log.info(
                f"HEALTH | uptime {ov['uptime_human']} | guilds {ov['guilds']} | "
                f"ping {ov['latency_ms']}ms | errors {ov['total_errors']} "
                f"(hour {ov['errors_last_hour']}, crit {ov['critical']}, "
                f"filtered {ov['filtered']}, repeats {ov['repeats_hidden']}) | "
                f"warn {ov['warnings_total']} | dc {ov['disconnects']} | "
                f"webhook {ov['webhook_sent']}/{ov['webhook_dropped']} | "
                f"lag max {ov['loop_lag_max']}s | alerts {ov['alerts_sent']}"
            )
            per_min = self._errors_in_window(60)
            if per_min >= int(self.config.get('error_rate_alert', 60)):
                if time.time() - self._spike_alert_at > 600:
                    self._spike_alert_at = time.time()
                    self.queue_alert(
                        "Всплеск ошибок",
                        f"**{per_min}** ошибок за последнюю минуту — возможно, что-то массово ломается.",
                    )

    async def _persist_task(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(max(60, int(self.config.get('stats_save_sec', 300))))
            self.save_stats()

    # ────────────────────────────────────────────────────────────
    # Обзор для веб-панели / команды
    # ────────────────────────────────────────────────────────────
    def get_overview(self) -> dict:
        now = time.time()
        uptime = now - self.stats.get('started_at', now)
        h, m, s_ = int(uptime // 3600), int((uptime % 3600) // 60), int(uptime % 60)
        top_types = sorted(self.stats['by_type'].items(), key=lambda x: -x[1])[:5]
        top_cogs = sorted(self.stats['by_cog'].items(), key=lambda x: -x[1])[:5]
        latency = getattr(self.bot, 'latency', None)
        lat_ms = 0
        if latency is not None:
            try:
                if math.isfinite(latency):
                    lat_ms = round(latency * 1000)
            except Exception:
                lat_ms = 0
        dc = sum(1 for ts in self._disconnects if now - ts <= 3600)
        # График за последние 7 дней (с нулевым заполнением пропусков)
        daily_src = self.stats.get('daily') or {}
        daily7 = []
        for i in range(6, -1, -1):
            dkey = time.strftime('%Y-%m-%d', time.localtime(now - i * 86400))
            daily7.append({'day': dkey, 'count': int(daily_src.get(dkey, 0))})
        return {
            'ok': True,
            'master_enabled': self.config.get('master_enabled', True),
            'uptime_sec': int(uptime),
            'uptime_human': f"{h}ч {m}м {s_}с",
            'total_errors': self.stats['total_errors'],
            'errors_last_hour': self._errors_in_window(3600),
            'critical': self.stats['critical'],
            'filtered': self.stats.get('filtered', 0),
            'repeats_hidden': self.stats.get('repeats_hidden', 0),
            'warnings_total': self.stats.get('warnings_total', 0),
            'warnings': dict(sorted(self.stats.get('warnings', {}).items(), key=lambda x: -x[1])[:5]),
            'disconnects': self.stats.get('disconnects', 0),
            'disconnects_hour': dc,
            'webhook_sent': self.stats.get('webhook_sent', 0),
            'webhook_dropped': self.stats.get('webhook_dropped', 0),
            'webhook_on': bool(self.config.get('webhook_enabled') and (self.config.get('webhook_url') or '').strip()),
            'alerts_sent': self.stats['alerts_sent'],
            'alerts_dropped': self.stats['alerts_dropped'],
            'alerts_queued': len(self._alerts),
            'loop_lag_max': self.stats.get('loop_lag_max', 0.0),
            'loop_lag_recent': round(self._lag_recent, 2),
            'top_types': [{'name': n, 'count': c} for n, c in top_types],
            'top_cogs': [{'name': n, 'count': c} for n, c in top_cogs],
            'breakers': [
                {'module': mod, 'count': cnt,
                 'tripped_at': self._breaker_state.get(mod, {}).get('tripped')}
                for mod, cnt in self.stats['breakers'].items()
            ],
            'last_errors': list(reversed(self.stats['last_errors'][-15:])),
            'daily7': daily7,
            'guilds': len(self.bot.guilds) if self.bot else 0,
            'latency_ms': lat_ms,
            'channel_configured': bool(int(self.config.get('log_channel_id', 0) or 0)),
            'watchdog_on': self.config.get('loop_watchdog', True),
            'breaker_on': self.config.get('cog_breaker', True),
            'auto_reload_on': self.config.get('cog_auto_reload', False),
            'filter_on': self.config.get('filter_enabled', True),
            'connection_watch_on': self.config.get('connection_watch', True),
            'warning_monitor_on': self.config.get('warning_monitor', True),
        }

    # ────────────────────────────────────────────────────────────
    # Ошибки команд (пользовательские ответы)
    # ────────────────────────────────────────────────────────────
    async def _safe_send(self, ctx: commands.Context, **kwargs):
        try:
            await ctx.send(**kwargs)
        except Exception as _ex:
            _log.debug("_safe_send(): подавлено: %s", _ex)

    async def handle_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Обработка ошибок prefix-команд"""
        if ctx.cog and ctx.cog.has_error_handler():
            return

        error = getattr(error, 'original', error)

        if isinstance(error, commands.MissingPermissions):
            missing = ", ".join(error.missing_permissions)
            embed = self._error_embed("Недостаточно прав", f"Отсутствуют права: `{missing}`")
            await self._safe_send(ctx, embed=embed, delete_after=15)
            return

        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            embed = self._error_embed("У бота нет прав", f"Боту не хватает прав: `{missing}`")
            await self._safe_send(ctx, embed=embed, delete_after=15)
            return

        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingRequiredArgument):
            embed = self._error_embed(
                "Не указан аргумент",
                f"Пропущен обязательный параметр: `{error.param.name}`\n\nИспользуйте `!help {ctx.command.name}` для справки")
            await self._safe_send(ctx, embed=embed, delete_after=20)
            return

        if isinstance(error, commands.BadArgument):
            embed = self._error_embed("Неверный аргумент", f"Не удалось разобрать аргумент: {error}")
            await self._safe_send(ctx, embed=embed, delete_after=15)
            return

        if isinstance(error, commands.CommandOnCooldown):
            embed = self._error_embed("Команда на перезарядке", f"Попробуйте через {error.retry_after:.1f} сек.")
            await self._safe_send(ctx, embed=embed, delete_after=10)
            return

        if isinstance(error, commands.CheckFailure):
            embed = self._error_embed("Проверка не пройдена", "У вас нет доступа к этой команде")
            await self._safe_send(ctx, embed=embed, delete_after=15)
            return

        # === Неизвестная ошибка — полный учёт ===
        cmd_name = str(ctx.command) if ctx.command else "unknown"
        cog_name = type(ctx.cog).__module__ if ctx.cog else None
        self.stats['by_command'][cmd_name] = self.stats['by_command'].get(cmd_name, 0) + 1
        if cog_name:
            self.stats['by_cog'][cog_name] = self.stats['by_cog'].get(cog_name, 0) + 1
        self._log_error(f"Command error in {cmd_name}: {error}", error,
                        where=f"cmd:{cmd_name}", critical=True)
        if cog_name:
            self._track_cog(cog_name)

        embed = self._error_embed(
            "Произошла ошибка",
            "Непредвиденная ошибка при выполнении команды. Администрация уже уведомлена.")
        await self._safe_send(ctx, embed=embed, delete_after=20)

    async def handle_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Обработка ошибок slash-команд"""
        error = getattr(error, 'original', error)

        if isinstance(error, app_commands.MissingPermissions):
            missing = ", ".join(error.missing_permissions)
            embed = self._error_embed("Недостаточно прав", f"Отсутствуют права: `{missing}`")
            await self._respond(interaction, embed=embed)
            return

        if isinstance(error, app_commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            embed = self._error_embed("У бота нет прав", f"Боту не хватает прав: `{missing}`")
            await self._respond(interaction, embed=embed)
            return

        if isinstance(error, app_commands.CommandOnCooldown):
            embed = self._error_embed("Команда на перезарядке", f"Попробуйте через {error.retry_after:.1f} сек.")
            await self._respond(interaction, embed=embed)
            return

        if isinstance(error, app_commands.CheckFailure):
            embed = self._error_embed("Проверка не пройдена", "У вас нет доступа к этой команде")
            await self._respond(interaction, embed=embed)
            return

        cmd_name = interaction.command.name if interaction.command else "unknown"
        module = None
        try:
            if interaction.command and getattr(interaction.command, 'binding', None) is not None:
                module = type(interaction.command.binding).__module__
        except Exception as _ex:
            _log.debug("handle_app_command_error(): подавлено: %s", _ex)
        self.stats['by_command'][cmd_name] = self.stats['by_command'].get(cmd_name, 0) + 1
        if module:
            self.stats['by_cog'][module] = self.stats['by_cog'].get(module, 0) + 1
        self._log_error(f"App command error in {cmd_name}: {error}", error,
                        where=f"slash:{cmd_name}", critical=True)
        if module:
            self._track_cog(module)

        embed = self._error_embed(
            "Произошла ошибка",
            "Непредвиденная ошибка при выполнении команды. Администрация уже уведомлена.")
        await self._respond(interaction, embed=embed)

    def _error_embed(self, title: str, description: str) -> discord.Embed:
        return discord.Embed(
            title=title,
            description=description,
            color=discord.Color.dark_grey(),
            timestamp=datetime.now())

    async def _respond(self, interaction: discord.Interaction, embed: discord.Embed):
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as _ex:
            _log.debug("_respond(): подавлено: %s", _ex)

    def get_error_stats(self) -> dict:
        return dict(self.stats['by_type'])


# ────────────────────────────────────────────────────────────────
# Команды управления (!anticrash)
# ────────────────────────────────────────────────────────────────
class AntiCrashCog(commands.Cog):
    """🛡 Управление anti-crash системой (только админы)."""

    GOLD = 0xD4AF37

    def __init__(self, bot, handler: ErrorHandler):
        self.bot = bot
        self.h = handler

    @commands.group(name='anticrash', aliases=['ac', 'antikrash'], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def anticrash(self, ctx):
        """Статус anti-crash системы."""
        ov = self.h.get_overview()
        status = "🟢 Активна" if ov['master_enabled'] else "🔴 Отключена (master_enabled=0)"
        embed = discord.Embed(
            title="🛡 HAKUMO ANTI-CRASH — Состояние системы",
            color=self.GOLD,
            timestamp=datetime.now(),
        )
        embed.add_field(name="Статус", value=status, inline=True)
        embed.add_field(name="Аптайм", value=f"`{ov['uptime_human']}`", inline=True)
        embed.add_field(name="Пинг", value=f"`{ov['latency_ms']} мс`", inline=True)
        embed.add_field(
            name="Ошибки",
            value=(f"Всего: **{ov['total_errors']}**\nЗа час: **{ov['errors_last_hour']}**\n"
                   f"Критических: **{ov['critical']}**"),
            inline=True)
        embed.add_field(
            name="Шум / Warnings",
            value=(f"Отфильтровано: **{ov['filtered']}**\nСкрыто повторов: **{ov['repeats_hidden']}**\n"
                   f"Warning'ов: **{ov['warnings_total']}** {'🟢' if ov['warning_monitor_on'] else '🔴'}"),
            inline=True)
        embed.add_field(
            name="Соединение",
            value=(f"Обрывов всего: **{ov['disconnects']}**\nЗа час: **{ov['disconnects_hour']}**\n"
                   f"Watch: {'🟢' if ov['connection_watch_on'] else '🔴'}"),
            inline=True)
        embed.add_field(
            name="Event-loop",
            value=(f"Лаг сейчас: `{ov['loop_lag_recent']}с`\nМакс. лаг: `{ov['loop_lag_max']}с`\n"
                   f"Watchdog: {'🟢' if ov['watchdog_on'] else '🔴'}"),
            inline=True)
        embed.add_field(
            name="Алерты",
            value=(f"Канал: {'🟢 задан' if ov['channel_configured'] else '⚪ не задан'} "
                   f"(отправлено **{ov['alerts_sent']}**)\n"
                   f"Webhook: {'🟢' if ov['webhook_on'] else '⚪ выкл'} "
                   f"(отправлено **{ov['webhook_sent']}**, дедуп **{ov['webhook_dropped']}**)"),
            inline=True)
        embed.add_field(
            name="Фильтр",
            value=f"{'🟢 вкл' if ov['filter_on'] else '🔴 выкл'} · {len(self.h.config.get('filter_substrings', []))} фраз",
            inline=True)
        br = self.h.stats['breakers']
        br_txt = "\n".join(f"• `{m}` — {c}x" for m, c in list(br.items())[:4]) or "Тишина — ни одного срабатывания ✨"
        embed.add_field(
            name=f"⚡ Circuit breaker {'🟢' if ov['breaker_on'] else '🔴'} (auto-reload: {'🟢' if ov['auto_reload_on'] else '⚪'})",
            value=br_txt, inline=False)
        embed.set_footer(text="!anticrash stats • config • set • kanal • webhook <url> • test • test-webhook • reset")
        await ctx.send(embed=embed)

    @anticrash.command(name='stats', aliases=['стата', 'статистика'])
    @commands.has_permissions(administrator=True)
    async def ac_stats(self, ctx):
        """Подробная статистика ошибок."""
        ov = self.h.get_overview()
        embed = discord.Embed(title="🛡 Статистика ошибок", color=self.GOLD, timestamp=datetime.now())
        top_t = "\n".join(f"`{t['count']:>4}` — {t['name']}" for t in ov['top_types']) or "—"
        top_c = "\n".join(f"`{t['count']:>4}` — {t['name']}" for t in ov['top_cogs']) or "—"
        embed.add_field(name="Топ типов ошибок", value=top_t, inline=True)
        embed.add_field(name="Топ модулей", value=top_c, inline=True)
        if ov['warnings']:
            w = "\n".join(f"`{c:>4}` — {n}" for n, c in ov['warnings'].items())
            embed.add_field(name="Типы warning'ов", value=w, inline=True)
        if ov['last_errors']:
            last = "\n".join(
                f"`{datetime.fromtimestamp(e['ts']).strftime('%H:%M')}` **{e['type']}** · {e['where']}"
                + (f" · `{e.get('loc')}`" if e.get('loc') else "")
                for e in ov['last_errors'][:6])
            embed.add_field(name="Последние ошибки", value=last[:1000], inline=False)
        embed.set_footer(text=f"Детальный файл: data/anticrash_errors.jsonl ({'вкл' if self.h.config.get('details_log_enabled') else 'выкл'})")
        await ctx.send(embed=embed)

    @anticrash.command(name='config', aliases=['конфиг', 'настройки'])
    @commands.has_permissions(administrator=True)
    async def ac_config(self, ctx):
        """Показать текущий конфиг."""
        lines = []
        for k, v in self.h.config.items():
            label = CONFIG_META.get(k, (k,))[0]
            if isinstance(v, list):
                v = f"[{len(v)} фраз]"
            lines.append(f"{k} = {json.dumps(v, ensure_ascii=False)}   # {label}")
        txt = "```\n" + "\n".join(lines) + "\n```"
        if len(txt) > 4000:
            txt = txt[:3900] + "\n...```"
        embed = discord.Embed(title="🛡 Конфигурация anti-crash", description=txt, color=self.GOLD)
        embed.set_footer(text="Изменить: !anticrash set <ключ> <значение> • Панель: /anticrash")
        await ctx.send(embed=embed)

    @anticrash.command(name='set')
    @commands.has_permissions(administrator=True)
    async def ac_set(self, ctx, key: str = None, *, value: str = None):
        """Изменить настройку: !anticrash set loop_lag_threshold 3"""
        if not key or value is None:
            return await ctx.send("Формат: `!anticrash set <ключ> <значение>`\nСписок ключей: `!anticrash config`")
        try:
            new_val = self.h.update_config(key, value)
        except KeyError:
            return await ctx.send(f"❌ Неизвестный ключ `{key}`. Список: `!anticrash config`")
        except ValueError as e:
            return await ctx.send(f"❌ Неверное значение: {e}")
        label = CONFIG_META.get(key, (key,))[0]
        shown = f"[{len(new_val)} фраз]" if isinstance(new_val, list) else json.dumps(new_val, ensure_ascii=False)
        await ctx.send(f"✅ **{label}** (`{key}`) → `{shown}`")

    @anticrash.command(name='kanal', aliases=['channel'])
    @commands.has_permissions(administrator=True)
    async def ac_channel(self, ctx, channel: discord.TextChannel = None):
        """Задать канал для критических сводок (по умолчанию — текущий)."""
        ch = channel or ctx.channel
        self.h.update_config('log_channel_id', ch.id)
        await ctx.send(f"✅ Критические сводки anti-crash теперь будут приходить в {ch.mention}")

    @anticrash.command(name='webhook')
    @commands.has_permissions(administrator=True)
    async def ac_webhook(self, ctx, url: str = None):
        """Включить мгновенный webhook: !anticrash webhook <url> (или 'off')"""
        if not url:
            cur = (self.h.config.get('webhook_url') or '').strip()
            state = "🟢 вкл" if self.h.config.get('webhook_enabled') else "🔴 выкл"
            return await ctx.send(f"Webhook: {state} · URL: {'задан' if cur else 'не задан'}\n"
                                  "Включить: `!anticrash webhook <url>` · Выключить: `!anticrash webhook off`")
        if url.lower() in ('off', 'выкл', '0'):
            self.h.update_config('webhook_enabled', False)
            return await ctx.send("✅ Мгновенный webhook **отключён** (URL сохранён).")
        if not url.startswith(('https://discord.com/api/webhooks/', 'https://canary.discord.com/api/webhooks/')):
            return await ctx.send("❌ Это не похоже на Discord webhook URL.\n"
                                  "Создайте: канал → Настройки → Интеграция → Вебхуки → Скопировать URL")
        self.h.update_config('webhook_url', url)
        self.h.update_config('webhook_enabled', True)
        await ctx.send("✅ Мгновенный webhook **включён**! Ошибки будут прилетать сразу.\n"
                       "Проверка: `!anticrash test-webhook`")

    @anticrash.command(name='test-webhook', aliases=['testwebhook'])
    @commands.has_permissions(administrator=True)
    async def ac_test_webhook(self, ctx):
        """Тестовая отправка в webhook канал."""
        if not (self.h.config.get('webhook_enabled') and (self.h.config.get('webhook_url') or '').strip()):
            return await ctx.send("⚠ Сначала настройте: `!anticrash webhook <url>`")
        self.h._enqueue_webhook({
            'ts': time.time(), 'type': 'TestError', 'where': 'cmd:test-webhook',
            'loc': 'error_handler.py:test', 'msg': 'Тестовая ошибка — доставка работает! ✅',
            'critical': True, 'traceback': 'Traceback (test)',
        })
        await ctx.send("✅ Тестовая ошибка поставлена в очередь webhook (придёт за ~3 сек).")

    @anticrash.command(name='test')
    @commands.has_permissions(administrator=True)
    async def ac_test(self, ctx):
        """Тестовый алерт в канал сводок."""
        ch_id = int(self.h.config.get('log_channel_id', 0) or 0)
        if not ch_id:
            return await ctx.send("⚠ Сначала задайте канал: `!anticrash kanal`")
        self.h.queue_alert("Тестовое событие", "Проверка доставки критических сводок — всё работает! ✅")
        await ctx.send(f"✅ Тестовый алерт поставлен в очередь (придёт в течение {self.h.config['alert_flush_sec']} сек.)")

    @anticrash.command(name='reset', aliases=['сброс'])
    @commands.has_permissions(administrator=True)
    async def ac_reset(self, ctx):
        """Сбросить статистику ошибок."""
        self.h.reset_stats()
        await ctx.send("✅ Статистика anti-crash сброшена.")

    @anticrash.command(name='reload-cog', aliases=['reload'])
    @commands.has_permissions(administrator=True)
    async def ac_reload(self, ctx, module: str = None):
        """Перезагрузить модуль вручную: !anticrash reload-cog cogs.music_cog"""
        if not module:
            return await ctx.send("Формат: `!anticrash reload-cog cogs.<имя>`")
        try:
            await self.bot.reload_extension(module)
            await ctx.send(f"✅ Модуль `{module}` перезагружен.")
        except Exception as e:
            await ctx.send(f"❌ Не удалось: {e}")

    @anticrash.error
    async def ac_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("🚫 Только для администраторов.", delete_after=8)


async def setup(bot: commands.Bot):
    """Зарегистрировать обработчик ошибок"""
    handler = ErrorHandler(bot)
    handler.setup()
    bot.error_handler = handler  # Сохраняем для доступа из других модулей
