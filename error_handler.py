"""
AETHER ANTI-CRASH — централизованная защита от падений (pro-версия)

Возможности:
- Перехват ошибок prefix/slash команд, событий, asyncio-задач, потоков и главного потока
- Watchdog event-loop: ловит зависания цикла (лаг > N сек)
- Circuit breaker по когам: если один модуль сыпет ошибками — алерт (+опц. auto-reload)
- Детектор всплеска ошибок (rate spike)
- Алерты в Discord-канал: очередь + периодическая сводка + лимит в час (без спама)
- Персистентная статистика (переживает рестарт) + настраиваемый конфиг (JSON)
- Команда !anticrash (статус/статистика/конфиг/тест) и API для веб-панели
"""
import asyncio
import os
import json
import time
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

DEFAULT_CONFIG = {
    "master_enabled": True,       # главный выключатель мониторинга
    "log_channel_id": 0,          # ID канала для критических сводок (0 = выкл)
    "alerts_enabled": True,       # слать ли алерты в канал
    "max_alerts_per_hour": 6,     # лимит отправок в канал (анти-спам)
    "alert_flush_sec": 60,        # как часто отправлять накопленную сводку
    "loop_watchdog": True,        # следить за зависанием event-loop
    "loop_lag_threshold": 5.0,    # лаг (сек) выше этого = зависание
    "loop_check_interval": 2.0,   # период измерения лага (сек)
    "health_log_interval": 600,   # период health-сводки в лог (сек)
    "error_rate_alert": 60,       # ошибок за 60 сек → алерт о всплеске
    "cog_breaker": True,          # circuit breaker по когам
    "cog_error_threshold": 20,    # ошибок одного кога в окне → breaker
    "cog_window_sec": 600,        # окно подсчёта (сек)
    "cog_auto_reload": False,     # авто-reload кога при срабатывании breaker'а
    "stats_persist": True,        # сохранять статистику на диск
    "stats_save_sec": 300,        # период записи статистики
}

# Метаданные для веб-панели / справки (рус.)
CONFIG_META = {
    "master_enabled":      ("Мастер-переключатель", "Весь мониторинг и алерты", "bool"),
    "log_channel_id":      ("ID канала алертов", "Куда слать критические сводки (0 — выкл.)", "int"),
    "alerts_enabled":      ("Алерты в Discord", "Разрешить отправку сводок в канал", "bool"),
    "max_alerts_per_hour": ("Лимит алертов/час", "Анти-спам ограничение отправок", "int"),
    "alert_flush_sec":     ("Период сводки (сек)", "Как часто отправляется накопленная сводка", "int"),
    "loop_watchdog":       ("Watchdog цикла", "Отслеживать зависания event-loop", "bool"),
    "loop_lag_threshold":  ("Порог лага (сек)", "Лаг выше — считается зависанием", "float"),
    "loop_check_interval": ("Шаг замера (сек)", "Как часто мерить лаг цикла", "float"),
    "health_log_interval": ("Health-лог (сек)", "Период записи health-сводки в лог", "int"),
    "error_rate_alert":    ("Порог всплеска", "Ошибок/мин, при которых слать алерт", "int"),
    "cog_breaker":         ("Circuit breaker", "Детект «бешеного» модуля по потоку ошибок", "bool"),
    "cog_error_threshold": ("Порог ошибок кога", "Столько ошибок в окне = breaker", "int"),
    "cog_window_sec":      ("Окно breaker (сек)", "Период подсчёта ошибок кога", "int"),
    "cog_auto_reload":     ("Авто-reload кога", "Перезагружать модуль при срабатывании (осторожно)", "bool"),
    "stats_persist":       ("Сохранять статистику", "Писать статистику в файл", "bool"),
    "stats_save_sec":      ("Период записи (сек)", "Как часто сохранять статистику", "int"),
}


def _cast_like(default, raw):
    """Привести строковое значение к типу дефолтного конфига."""
    if isinstance(default, bool):
        if isinstance(raw, bool):
            return raw
        s = str(raw).strip().lower()
        if s in ('1', 'true', 'on', 'да', 'yes', 'вкл'):
            return True
        if s in ('0', 'false', 'off', 'нет', 'no', 'выкл'):
            return False
        raise ValueError("ожидается bool (вкл/выкл)")
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
    return str(raw)


class ErrorHandler:
    """Централизованный обработчик ошибок + anti-crash мониторинг"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = self._load_config()
        self.stats = self._load_stats()
        self.error_counts = self.stats['by_type']  # совместимость со старым API

        self._rate = deque(maxlen=2000)            # ts всех ошибок (для ошибок/час и всплеска)
        self._cog_windows = {}                     # module -> deque(ts)
        self._breaker_state = {}                   # module -> {'tripped': ts, 'reload_at': ts}
        self._alerts = []                          # очередь (title, desc, critical)
        self._alerts_sent_ts = deque(maxlen=100)   # ts отправок (лимит/час)
        self._lag_recent = 0.0
        self._spike_alert_at = 0.0
        self._tasks = []

    # ────────────────────────────────────────────────────────────
    # Конфиг и статистика (диск)
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
                        except Exception:
                            pass
        except Exception as e:
            log.error(f"Anti-crash config okunamadı, varsayılanlar: {e}")
        return cfg

    def save_config(self):
        try:
            os.makedirs('data', exist_ok=True)
            tmp = CONFIG_PATH + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CONFIG_PATH)
        except Exception as e:
            log.error(f"Anti-crash config yazılamadı: {e}")

    def update_config(self, key: str, value):
        """Обновить одну настройку (приведение типа + валидация)."""
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
            'alerts_sent': 0,
            'alerts_dropped': 0,
            'loop_lag_max': 0.0,
            'by_type': {},
            'by_command': {},
            'by_cog': {},
            'by_event': {},
            'breakers': {},
            'last_errors': [],
        }

    def _load_stats(self) -> dict:
        st = self._fresh_stats()
        try:
            if os.path.exists(STATS_PATH):
                with open(STATS_PATH, 'r', encoding='utf-8') as f:
                    old = json.load(f)
                for k, v in old.items():
                    if k == 'started_at':
                        continue  # аптайм считаем с текущего запуска
                    if k in st:
                        st[k] = v
        except Exception:
            pass
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
        except Exception:
            pass

    def reset_stats(self):
        self.stats = self._fresh_stats()
        self.error_counts = self.stats['by_type']
        self._cog_windows.clear()
        self._breaker_state.clear()
        self.save_stats()

    # ────────────────────────────────────────────────────────────
    # Регистрация
    # ────────────────────────────────────────────────────────────
    def setup(self):
        """Зарегистрировать обработчики"""
        @self.bot.event
        async def on_command_error(ctx: commands.Context, error: commands.CommandError):
            await self.handle_command_error(ctx, error)

        # Ошибки событий (on_message, on_member_join...)
        @self.bot.event
        async def on_error(event: str, *args, **kwargs):
            exc = sys.exc_info()[1]
            if exc is None:
                return
            self.stats['by_event'][event] = self.stats['by_event'].get(event, 0) + 1
            self._log_error(f"Event error in '{event}': {exc}", exc, where=f"event:{event}", critical=True)

        tree = self.bot.tree

        async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            await self.handle_app_command_error(interaction, error)

        tree.on_error = on_app_command_error

        self._setup_anticrash()

        # Фоновые задачи мониторинга
        try:
            loop = asyncio.get_running_loop()
            self._tasks = [
                loop.create_task(self._register_commands()),
                loop.create_task(self._loop_watchdog_task()),
                loop.create_task(self._alert_flush_task()),
                loop.create_task(self._health_log_task()),
                loop.create_task(self._persist_task()),
            ]
        except RuntimeError:
            pass

        log.info("Anti-crash PRO активирован (watchdog, breaker, алерты, статистика)")

    async def _register_commands(self):
        """Регистрируем !anticrash как обычный ког (настройка без правки файлов)."""
        try:
            await self.bot.add_cog(AntiCrashCog(self.bot, self))
        except Exception as e:
            log.error(f"Anti-crash komutları yüklenemedi: {e}")

    def _setup_anticrash(self):
        """Перехват падений asyncio-задач, потоков и главного потока"""
        try:
            self._loop = asyncio.get_running_loop()
            self._loop.set_exception_handler(self._loop_exception_handler)
        except RuntimeError:
            pass

        def _sys_hook(exc_type, exc, tb):
            if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
                sys.__excepthook__(exc_type, exc, tb)
                return
            t = "".join(traceback.format_exception(exc_type, exc, tb))
            log.critical(f"НЕПЕРЕХВАЧЕННОЕ ИСКЛЮЧЕНИЕ (main thread):\n{t}")
            self._record(exc_type.__name__, "main_thread", str(exc), critical=True)

        sys.excepthook = _sys_hook

        def _thread_hook(args: "threading.ExceptHookArgs"):
            if issubclass(args.exc_type, (KeyboardInterrupt, SystemExit)):
                return
            t = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
            tname = args.thread.name if args.thread else '?'
            log.critical(f"НЕПЕРЕХВАЧЕННОЕ ИСКЛЮЧЕНИЕ (поток {tname}):\n{t}")
            self._record(args.exc_type.__name__, f"thread:{tname}", str(args.exc_value), critical=True)

        threading.excepthook = _thread_hook

    def _loop_exception_handler(self, loop: asyncio.AbstractEventLoop, context: dict):
        """Ошибки фоновых asyncio-задач: логируем, цикл не останавливаем."""
        exc = context.get("exception")
        msg = context.get("message", "asyncio error")
        if exc is not None:
            self._log_error(f"Asyncio task error: {msg} ({exc})", exc, where="asyncio:task", critical=True)
        else:
            log.error(f"Asyncio error: {msg}")
            self._record("AsyncioError", "asyncio:loop", msg)

    # ────────────────────────────────────────────────────────────
    # Учёт ошибок
    # ────────────────────────────────────────────────────────────
    def _record(self, err_type: str, where: str, message: str, critical: bool = False):
        """Единая точка учёта: счётчики, rate, last_errors, breaker-трекер."""
        s = self.stats
        s['total_errors'] += 1
        if critical:
            s['critical'] += 1
        s['by_type'][err_type] = s['by_type'].get(err_type, 0) + 1
        self._rate.append(time.time())
        s['last_errors'].append({
            'ts': time.time(),
            'type': err_type,
            'where': where,
            'msg': (message or '')[:220],
            'critical': bool(critical),
        })
        del s['last_errors'][:-30]

    def _log_error(self, message: str, error: Exception, where: str = "", critical: bool = False):
        """Залогировать ошибку с трассировкой + учёт."""
        log.error(message)
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        log.error(f"Traceback:\n{tb}")
        self._record(type(error).__name__, where or "unknown", message, critical=critical)
        if critical and self.config.get('master_enabled', True):
            self.queue_alert(
                "Критическая ошибка",
                f"`{type(error).__name__}` — {where or 'система'}\n{str(error)[:180]}",
            )

    def _count(self, error_type: str):
        self.stats['by_type'][error_type] = self.stats['by_type'].get(error_type, 0) + 1

    def _errors_in_window(self, window_sec: float) -> int:
        now = time.time()
        return sum(1 for ts in self._rate if now - ts <= window_sec)

    # ────────────────────────────────────────────────────────────
    # Circuit breaker по когам
    # ────────────────────────────────────────────────────────────
    def _track_cog(self, module: str):
        """Посчитать ошибку кога; при превышении порога — breaker (+опц. reload)."""
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
        # уже сработал? не дублируем чаще раза в 10 минут
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
        """Аккуратная перезагрузка кога; повтор не чаще 10 минут."""
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
    # Алерты: очередь + сводка в Discord-канал (с лимитом)
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
                log.error(f"Alert flush hatası: {e}")

    async def _flush_alerts(self):
        if not self._alerts:
            return
        if not self.config.get('alerts_enabled', True):
            self.stats['alerts_dropped'] += len(self._alerts)
            self._alerts.clear()
            return
        ch_id = int(self.config.get('log_channel_id', 0) or 0)
        if not ch_id:
            # канал не задан — просто забываем (всё уже в лог-файле)
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
            return  # канал недоступен — попробуем в следующий флаш

        # лимит отправок в час
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
            log.error(f"Anti-crash: uyarı kanalına yazılamadı: {e}")

    # ────────────────────────────────────────────────────────────
    # Watchdog event-loop (зависания)
    # ────────────────────────────────────────────────────────────
    async def _loop_watchdog_task(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(30)  # стартовая разминка — не тревожим при загрузке
        last_alert = 0.0
        while not self.bot.is_closed():
            if not self.config.get('loop_watchdog', True):
                await asyncio.sleep(5)
                continue
            iv = max(0.5, float(self.config.get('loop_check_interval', 2.0)))
            t0 = time.monotonic()
            await asyncio.sleep(iv)
            drift = (time.monotonic() - t0) - iv
            self._lag_recent = drift
            if drift > float(self.config.get('loop_lag_threshold', 5.0)):
                if drift > self.stats.get('loop_lag_max', 0.0):
                    self.stats['loop_lag_max'] = round(drift, 2)
                log.critical(f"EVENT-LOOP ЗАВИСАНИЕ: цикл не отвечал {drift:.1f} сек!")
                if time.time() - last_alert > 300:
                    last_alert = time.time()
                    self.queue_alert(
                        "Зависание event-loop",
                        f"Цикл не отвечал **{drift:.1f} сек** — команды и ивенты в это время стояли.\n"
                        f"Частая причина: тяжёлая синхронная операция (сеть/диск/CPU) в async-коде.",
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
                f"ping {ov['latency_ms']}ms | errors total {ov['total_errors']} "
                f"(last hour {ov['errors_last_hour']}, critical {ov['critical']}) | "
                f"loop lag max {ov['loop_lag_max']}s | alerts {ov['alerts_sent']}"
            )
            # всплеск ошибок
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
        return {
            'ok': True,
            'master_enabled': self.config.get('master_enabled', True),
            'uptime_sec': int(uptime),
            'uptime_human': f"{h}ч {m}м {s_}с",
            'total_errors': self.stats['total_errors'],
            'errors_last_hour': self._errors_in_window(3600),
            'critical': self.stats['critical'],
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
            'guilds': len(self.bot.guilds) if self.bot else 0,
            'latency_ms': round(latency * 1000) if latency is not None else 0,
            'channel_configured': bool(int(self.config.get('log_channel_id', 0) or 0)),
            'watchdog_on': self.config.get('loop_watchdog', True),
            'breaker_on': self.config.get('cog_breaker', True),
            'auto_reload_on': self.config.get('cog_auto_reload', False),
        }

    # ────────────────────────────────────────────────────────────
    # Ошибки команд (пользовательские ответы)
    # ────────────────────────────────────────────────────────────
    async def _safe_send(self, ctx: commands.Context, **kwargs):
        try:
            await ctx.send(**kwargs)
        except Exception:
            pass

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
        except Exception:
            pass
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
        except Exception:
            pass

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
            title="🛡 AETHER ANTI-CRASH — Состояние системы",
            color=self.GOLD,
            timestamp=datetime.now(),
        )
        embed.add_field(name="Статус", value=status, inline=True)
        embed.add_field(name="Аптайм", value=f"`{ov['uptime_human']}`", inline=True)
        embed.add_field(name="Пинг", value=f"`{ov['latency_ms']} мс`", inline=True)
        embed.add_field(
            name="Ошибки",
            value=f"Всего: **{ov['total_errors']}**\nЗа час: **{ov['errors_last_hour']}**\nКритических: **{ov['critical']}**",
            inline=True)
        embed.add_field(
            name="Event-loop",
            value=(f"Лаг сейчас: `{ov['loop_lag_recent']}с`\nМакс. лаг: `{ov['loop_lag_max']}с`\n"
                   f"Watchdog: {'🟢' if ov['watchdog_on'] else '🔴'}"),
            inline=True)
        embed.add_field(
            name="Алерты",
            value=(f"Отправлено: **{ov['alerts_sent']}**\nВ очереди: **{ov['alerts_queued']}**\n"
                   f"Канал: {'🟢 задан' if ov['channel_configured'] else '⚪ не задан'}"),
            inline=True)
        br = self.h.stats['breakers']
        br_txt = "\n".join(f"• `{m}` — {c}x" for m, c in list(br.items())[:4]) or "Тишина — ни одного срабатывания ✨"
        embed.add_field(
            name=f"⚡ Circuit breaker {'🟢' if ov['breaker_on'] else '🔴'} (auto-reload: {'🟢' if ov['auto_reload_on'] else '⚪'})",
            value=br_txt, inline=False)
        embed.set_footer(text="!anticrash stats • config • set <ключ> <знач> • kanal • test • reset")
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
        if ov['last_errors']:
            last = "\n".join(
                f"`{datetime.fromtimestamp(e['ts']).strftime('%H:%M')}` **{e['type']}** · {e['where']}"
                for e in ov['last_errors'][:6])
            embed.add_field(name="Последние ошибки", value=last[:1000], inline=False)
        await ctx.send(embed=embed)

    @anticrash.command(name='config', aliases=['конфиг', 'настройки'])
    @commands.has_permissions(administrator=True)
    async def ac_config(self, ctx):
        """Показать текущий конфиг."""
        lines = []
        for k, v in self.h.config.items():
            label = CONFIG_META.get(k, (k,))[0]
            lines.append(f"{k} = {json.dumps(v, ensure_ascii=False)}   # {label}")
        txt = "```\n" + "\n".join(lines) + "\n```"
        embed = discord.Embed(
            title="🛡 Конфигурация anti-crash",
            description=txt[:4000],
            color=self.GOLD)
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
        await ctx.send(f"✅ **{label}** (`{key}`) → `{json.dumps(new_val, ensure_ascii=False)}`")

    @anticrash.command(name='kanal', aliases=['channel'])
    @commands.has_permissions(administrator=True)
    async def ac_channel(self, ctx, channel: discord.TextChannel = None):
        """Задать канал для критических сводок (по умолчанию — текущий)."""
        ch = channel or ctx.channel
        self.h.update_config('log_channel_id', ch.id)
        await ctx.send(f"✅ Критические сводки anti-crash теперь будут приходить в {ch.mention}")

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
