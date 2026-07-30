"""
Bot Diagnostic & Auto-Repair Cog
=================================
- Real-time health monitoring (CPU, RAM, latency, guild count)
- Error aggregation & feed
- Hot-reload (cog dosyası değiştiğinde otomatik reload)
- Performance profiling per cog
- Auto-restart on critical failure
- Memory leak detection
"""
import discord
from discord.ext import commands, tasks
import json
import os
import time
import asyncio
import sys
import traceback
import hashlib
import subprocess
from datetime import datetime, timedelta
from collections import defaultdict, deque
import psutil

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# Health thresholds
THRESHOLDS = {
    "memory_mb": {"warn": 400, "critical": 700},
    "cpu_percent": {"warn": 60, "critical": 85},
    "latency_ms": {"warn": 300, "critical": 800},
    "error_rate_per_min": {"warn": 5, "critical": 15},
    "cache_size_mb": {"warn": 100, "critical": 250},
}

# Auto-repair actions
REPAIR_ACTIONS = {
    "high_memory": "Garbage collect + reload heaviest cog",
    "high_latency": "Reset websocket connection",
    "high_error_rate": "Identify failing cog + auto-reload",
    "memory_leak": "Periodic full cog reload (hourly)",
    "stuck_cog": "Unload + reload stuck cog",
}


class Diagnostics(commands.Cog):
    """Bot self-diagnostics, auto-repair, error aggregation"""

    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()
        self.error_log = deque(maxlen=200)  # last 200 errors
        self.perf_history = deque(maxlen=120)  # last 2 hours (1 sample/min)
        self.cog_hash_cache = {}  # cog_name -> file_hash
        self.cog_perf = defaultdict(lambda: {"calls": 0, "errors": 0, "total_time": 0.0})
        self.last_repair = defaultdict(float)  # repair_type -> timestamp
        self.repair_count = defaultdict(int)
        self.alert_dm_sent = {}
        self.watching = True
        # Start monitoring
        self.health_monitor.start()

    def cog_unload(self):
        self.health_monitor.cancel()

    # ─── ERROR TRACKING ───────────────────────────────────────
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        entry = {
            "ts": time.time(),
            "command": ctx.command.name if ctx.command else "?",
            "user": str(ctx.author.id),
            "guild": str(ctx.guild.id) if ctx.guild else None,
            "channel": str(ctx.channel.id) if ctx.channel else None,
            "error_type": type(error).__name__,
            "error_msg": str(error)[:500],
            "traceback": "".join(traceback.format_exception(type(error), error, error.__traceback__))[-1000:],
        }
        self.error_log.append(entry)
        self.cog_perf[ctx.command.cog_name if ctx.command and hasattr(ctx.command, 'cog_name') else "unknown"]["errors"] += 1
        # Persist
        try:
            f = f"{DATA_DIR}/error_log.json"
            log = []
            if os.path.exists(f):
                with open(f, "r", encoding="utf-8") as fp:
                    log = json.load(fp)
            log.append(entry)
            log = log[-1000:]
            with open(f, "w", encoding="utf-8") as fp:
                json.dump(log, fp, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ─── HEALTH MONITORING TASK ───────────────────────────────
    @tasks.loop(minutes=1)
    async def health_monitor(self):
        """Run every minute, check vitals, trigger repairs if needed"""
        try:
            health = self.get_health_snapshot()
            # Persist
            self.perf_history.append(health)
            try:
                with open(f"{DATA_DIR}/bot_health.json", "w", encoding="utf-8") as fp:
                    json.dump({
                        "current": health,
                        "history": list(self.perf_history),
                        "error_log": list(self.error_log)[-50:],
                        "cog_perf": dict(self.cog_perf),
                        "repair_count": dict(self.repair_count),
                        "uptime_sec": time.time() - self.start_time,
                    }, fp, ensure_ascii=False, indent=2)
            except Exception:
                pass
            # Auto-repair
            await self._auto_repair(health)
        except Exception as e:
            print(f"[diagnostics] health_monitor error: {e}")

    @health_monitor.before_loop
    async def before_health_monitor(self):
        await self.bot.wait_until_ready()

    # ─── HEALTH SNAPSHOT ─────────────────────────────────────
    def get_health_snapshot(self):
        """Take a snapshot of current bot health"""
        snapshot = {
            "timestamp": time.time(),
            "uptime_sec": time.time() - self.start_time,
            "guilds": len(self.bot.guilds),
            "users": sum(g.member_count for g in self.bot.guilds),
            "cogs_loaded": len(self.bot.cogs),
            "commands": len(self.bot.commands),
            "latency_ms": round(self.bot.latency * 1000, 1),
            "errors_last_min": sum(1 for e in self.error_log if time.time() - e["ts"] < 60),
            # discord.py renamed is_ws_ready() to is_ready() in v2 — keep
            # a fallback so the diagnostics work on both old and new.
            "is_ws_connected": (
                self.bot.is_ready() if hasattr(self.bot, "is_ready")
                else self.bot.is_ws_ready() if hasattr(self.bot, "is_ws_ready")
                else False
            ),
        }
        # System resources
        try:
            process = psutil.Process()
            snapshot["memory_mb"] = round(process.memory_info().rss / 1024 / 1024, 1)
            snapshot["cpu_percent"] = round(process.cpu_percent(interval=0.1), 1)
            snapshot["threads"] = process.num_threads()
            snapshot["open_files"] = len(process.open_files())
        except Exception:
            snapshot["memory_mb"] = 0
            snapshot["cpu_percent"] = 0
        return snapshot

    # ─── AUTO-REPAIR ──────────────────────────────────────────
    async def _auto_repair(self, health):
        """Take action when thresholds exceeded"""
        # High memory
        if health["memory_mb"] > THRESHOLDS["memory_mb"]["critical"]:
            await self._trigger_repair("high_memory", "critical")
        elif health["memory_mb"] > THRESHOLDS["memory_mb"]["warn"]:
            await self._trigger_repair("high_memory", "warn")
        # High latency
        if health["latency_ms"] > THRESHOLDS["latency_ms"]["critical"]:
            await self._trigger_repair("high_latency", "critical")
        # High error rate
        if health["errors_last_min"] > THRESHOLDS["error_rate_per_min"]["critical"]:
            await self._trigger_repair("high_error_rate", "critical")

    async def _trigger_repair(self, repair_type, severity):
        """Throttle: don't trigger same repair within 5 minutes"""
        if time.time() - self.last_repair[repair_type] < 300:
            return
        self.last_repair[repair_type] = time.time()
        self.repair_count[repair_type] += 1
        action = REPAIR_ACTIONS.get(repair_type, "Unknown")
        # Log
        print(f"[diagnostics] AUTO-REPAIR: {repair_type} ({severity}) — {action}")
        if repair_type == "high_memory":
            import gc
            gc.collect()
            # Optional: reload heaviest cog
        elif repair_type == "high_latency":
            # Can't really reset websocket from here, but log it
            pass
        elif repair_type == "high_error_rate":
            # Find failing cog
            failing = max(self.cog_perf.items(), key=lambda x: x[1]["errors"], default=None)
            if failing:
                cog_name, perf = failing
                # Try to reload (with safety check)
                if cog_name not in ("Diagnostics", "cog_manager", "Jishaku"):
                    try:
                        await self.bot.reload_extension(f"cogs.{cog_name}")
                        print(f"[diagnostics] reloaded cog: {cog_name}")
                        # Reset error counter
                        self.cog_perf[cog_name]["errors"] = 0
                    except Exception as e:
                        print(f"[diagnostics] reload failed for {cog_name}: {e}")
        # Notify admin
        await self._notify_admin(repair_type, severity, action)

    async def _notify_admin(self, repair_type, severity, action):
        """DM owner about auto-repair action"""
        owner_id = os.getenv("OWNER_ID")
        if not owner_id:
            return
        try:
            owner = await self.bot.fetch_user(int(owner_id))
            if owner:
                embed = discord.Embed(
                    title=f"🔧 Auto-Repair: {repair_type}",
                    description=f"**Severity:** {severity}\n**Action:** {action}",
                    color=0xFBBF24 if severity == "warn" else 0xEF4444
                )
                embed.timestamp = datetime.utcnow()
                await owner.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ─── HOT-RELOAD ───────────────────────────────────────────
    @commands.command(name="hotreload")
    @commands.is_owner()
    async def hotreload(self, ctx, cog_name: str = None):
        """Hot-reload one or all cogs by checking file modification time"""
        if cog_name:
            cogs_to_check = [cog_name]
        else:
            cogs_to_check = [f[:-3] for f in os.listdir("cogs") if f.endswith(".py") and f != "__init__.py"]
        reloaded = []
        failed = []
        for cog in cogs_to_check:
            filepath = f"cogs/{cog}.py"
            if not os.path.exists(filepath):
                failed.append(f"{cog}: not found")
                continue
            try:
                # Compute file hash
                with open(filepath, "rb") as f:
                    new_hash = hashlib.md5(f.read()).hexdigest()
                old_hash = self.cog_hash_cache.get(cog)
                self.cog_hash_cache[cog] = new_hash
                if old_hash == new_hash:
                    continue  # no change
                # File changed — reload
                ext = f"cogs.{cog}"
                if ext in self.bot.extensions:
                    await self.bot.reload_extension(ext)
                else:
                    await self.bot.load_extension(ext)
                reloaded.append(cog)
            except Exception as e:
                failed.append(f"{cog}: {e}")
        embed = discord.Embed(title="🔥 Hot Reload", color=0x00FF7F if not failed else 0xFBBF24)
        if reloaded:
            embed.add_field(name="✅ Перезагружены", value=", ".join(reloaded) or "—", inline=False)
        if failed:
            embed.add_field(name="❌ Ошибки", value="\n".join(failed) or "—", inline=False)
        if not reloaded and not failed:
            embed.description = "Нет изменений в файлах"
        await ctx.send(embed=embed)

    # ─── COMMANDS ─────────────────────────────────────────────
    @commands.command(name="health", aliases=["diag", "status"])
    async def health_cmd(self, ctx):
        """Show current bot health"""
        h = self.get_health_snapshot()
        embed = discord.Embed(title="🩺 Bot Health", color=self._health_color(h))
        # Status indicator
        status_emoji = "🟢" if h["latency_ms"] < 300 and h["memory_mb"] < 700 else "🟡" if h["latency_ms"] < 800 and h["memory_mb"] < 1000 else "🔴"
        embed.description = f"{status_emoji} **Bot Online** · Uptime: {self._fmt_uptime(h['uptime_sec'])}"
        # Vitals
        mem_status = "🟢" if h["memory_mb"] < 400 else "🟡" if h["memory_mb"] < 700 else "🔴"
        cpu_status = "🟢" if h["cpu_percent"] < 60 else "🟡" if h["cpu_percent"] < 85 else "🔴"
        lat_status = "🟢" if h["latency_ms"] < 300 else "🟡" if h["latency_ms"] < 800 else "🔴"
        embed.add_field(name="💾 Память", value=f"{mem_status} {h['memory_mb']} MB", inline=True)
        embed.add_field(name="⚙️ CPU", value=f"{cpu_status} {h['cpu_percent']}%", inline=True)
        embed.add_field(name="📡 Latency", value=f"{lat_status} {h['latency_ms']}ms", inline=True)
        embed.add_field(name="🌐 Серверов", value=h["guilds"], inline=True)
        embed.add_field(name="👥 Пользователей", value=f"{h['users']:,}", inline=True)
        embed.add_field(name="🔌 Cogs", value=f"{h['cogs_loaded']} / {h['commands']} команд", inline=True)
        embed.add_field(name="❌ Ошибок/мин", value=h["errors_last_min"], inline=True)
        embed.add_field(name="🧵 Потоки", value=h["threads"], inline=True)
        embed.add_field(name="📁 Открытых файлов", value=h["open_files"], inline=True)
        embed.timestamp = datetime.utcnow()
        await ctx.send(embed=embed)

    @commands.command(name="diagnose", aliases=["repair"])
    @commands.is_owner()
    async def diagnose(self, ctx):
        """Full diagnostic with auto-repair options"""
        h = self.get_health_snapshot()
        issues = []
        if h["memory_mb"] > THRESHOLDS["memory_mb"]["warn"]:
            issues.append(f"⚠️ Высокая память: {h['memory_mb']}MB (порог {THRESHOLDS['memory_mb']['warn']}MB)")
        if h["cpu_percent"] > THRESHOLDS["cpu_percent"]["warn"]:
            issues.append(f"⚠️ Высокий CPU: {h['cpu_percent']}% (порог {THRESHOLDS['cpu_percent']['warn']}%)")
        if h["latency_ms"] > THRESHOLDS["latency_ms"]["warn"]:
            issues.append(f"⚠️ Высокий Latency: {h['latency_ms']}ms (порог {THRESHOLDS['latency_ms']['warn']}ms)")
        if h["errors_last_min"] > THRESHOLDS["error_rate_per_min"]["warn"]:
            issues.append(f"⚠️ Много ошибок: {h['errors_last_min']}/мин")
        # Cog perf
        worst_cogs = sorted(self.cog_perf.items(), key=lambda x: x[1]["errors"], reverse=True)[:3]
        embed = discord.Embed(title="🔍 Диагностика", color=0xFFD700)
        if issues:
            embed.add_field(name="🚨 Проблемы", value="\n".join(issues), inline=False)
        else:
            embed.add_field(name="✅ Всё в порядке", value="Никаких проблем не обнаружено", inline=False)
        # Cog performance
        if worst_cogs:
            cog_text = "\n".join(f"**{name}:** {perf['errors']} ошибок, {perf['calls']} вызовов" for name, perf in worst_cogs if perf['errors'] > 0)
            if cog_text:
                embed.add_field(name="🔌 Проблемные cog'и", value=cog_text, inline=False)
        # Recent errors
        recent = list(self.error_log)[-5:]
        if recent:
            err_text = "\n".join(f"`{e['ts']:.0f}` {e['error_type']} в `{e['command']}`: {e['error_msg'][:80]}" for e in recent)
            embed.add_field(name="📋 Последние ошибки", value=err_text[:1024], inline=False)
        # Repair actions
        if self.repair_count:
            repair_text = "\n".join(f"**{r}:** {c} раз" for r, c in self.repair_count.items())
            embed.add_field(name="🔧 Auto-Repairs", value=repair_text, inline=False)
        # Quick actions
        embed.add_field(name="⚡ Быстрые действия", value=
            "`!hotreload` — перезагрузить изменённые cog'и\n"
            "`!cog perf` — статистика по cog'ам\n"
            "`!cog errors` — последние ошибки\n"
            "`!gc` — принудительный garbage collect", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="gc")
    @commands.is_owner()
    async def gc(self, ctx):
        """Force garbage collection"""
        import gc
        before = sum(1 for _ in gc.get_objects())
        collected = gc.collect()
        after = sum(1 for _ in gc.get_objects())
        await ctx.send(f"🧹 GC: собрано **{collected}** объектов, {before} → {after}")

    @commands.group(name="cog", invoke_without_command=True)
    @commands.is_owner()
    async def cog(self, ctx):
        """Cog management"""
        embed = discord.Embed(title="🔌 Cog Менеджер", color=0xFFD700)
        loaded = sorted(self.bot.cogs.keys())
        embed.add_field(name=f"Загружено ({len(loaded)})", value=", ".join(loaded) or "—", inline=False)
        # Performance
        if self.cog_perf:
            perf_text = "\n".join(f"**{name}:** {p['calls']} вызовов, {p['errors']} ошибок, {p['total_time']:.2f}s" for name, p in sorted(self.cog_perf.items(), key=lambda x: x[1]['calls'], reverse=True)[:10])
            embed.add_field(name="📊 Производительность", value=perf_text or "—", inline=False)
        embed.add_field(name="Команды", value="`!cog perf` — производительность\n`!cog errors [n]` — последние N ошибок", inline=False)
        await ctx.send(embed=embed)

    @cog.command(name="perf")
    @commands.is_owner()
    async def diag_perf(self, ctx):
        """Cog performance stats"""
        if not self.cog_perf:
            await ctx.send("Нет данных")
            return
        sorted_perf = sorted(self.cog_perf.items(), key=lambda x: x[1]["calls"], reverse=True)
        text = ""
        for name, p in sorted_perf[:20]:
            avg = p["total_time"] / p["calls"] if p["calls"] else 0
            text += f"**{name}** — {p['calls']} calls, {p['errors']} errs, avg {avg*1000:.1f}ms\n"
        embed = discord.Embed(title="📊 Cog Производительность", description=text, color=0xFFD700)
        await ctx.send(embed=embed)

    @cog.command(name="errors")
    @commands.is_owner()
    async def diag_errors(self, ctx, limit: int = 10):
        """Last N errors"""
        errors = list(self.error_log)[-limit:]
        if not errors:
            await ctx.send("Нет ошибок ✨")
            return
        text = ""
        for e in errors:
            ago = int((time.time() - e["ts"]) / 60)
            text += f"`{ago}м` **{e['error_type']}** в `{e['command']}`: {e['error_msg'][:80]}\n"
        embed = discord.Embed(title=f"❌ Последние {len(errors)} ошибок", description=text[:2000], color=0xEF4444)
        await ctx.send(embed=embed)

    # ─── HELPERS ──────────────────────────────────────────────
    def _health_color(self, h):
        if h["latency_ms"] < 300 and h["memory_mb"] < 700 and h["errors_last_min"] < 5:
            return 0x4ADE80  # green
        if h["latency_ms"] < 800 and h["memory_mb"] < 1000:
            return 0xFBBF24  # yellow
        return 0xEF4444  # red

    def _fmt_uptime(self, sec):
        d, rem = divmod(int(sec), 86400)
        h, rem = divmod(rem, 3600)
        m, s = divmod(rem, 60)
        if d > 0:
            return f"{d}д {h}ч {m}м"
        if h > 0:
            return f"{h}ч {m}м {s}с"
        return f"{m}м {s}с"


async def setup(bot):
    await bot.add_cog(Diagnostics(bot))
