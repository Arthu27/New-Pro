"""
Aether — Анти-рейд / Защита от рейдов
----------------------------------
Режим: "Наблюдатель" (только чтение).

Поведение:
 * Читает файл `data/antiraid_<guild_id>.json` настроенный из панели.
 * При каждом изменении файла автоматически перезагружается (проверка mtime).
 * Реагирует на флаги `join_raid`, `bot_protection`, `age_filter`.
 * `raid_action` всегда считается "alert": бот никого не кикает/банит, только отправляет embed в канал алертов.
 * Пользователи в `whitelist` освобождены от всех проверок.

Все решения принимаются в панели на странице /antiraid; этот ког — только "движок правил".
"""

from logger import get_logger

_log = get_logger("antiraid")

import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone
from discord import app_commands
from collections import defaultdict
import json
import os
import time
import logging

log = logging.getLogger("aether.antiraid")

class GuildAntiraidConfig:
    """In-memory кэш настроек анти-рейда для одной гильдии, читает с диска."""

    DEFAULTS = {
        "join_raid": False,
        "bot_protection": False,
        "webhook_protection": False,
        "delete_protection": False,
        "age_filter": False,
        "min_age": 5,
        "join_threshold": 5,
        "join_window": 10,
        "raid_action": "alert",
        "alert_channel_id": None,
        "whitelist": [],
        "recent_events": [],
    }

    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.path = f"data/antiraid_{guild_id}.json"
        self.data: dict = dict(self.DEFAULTS)
        self._mtime: float = 0.0
        self.reload()

    def reload(self) -> bool:
        """Читает с диска. Возвращает False если изменений нет, True если изменилось."""
        try:
            if not os.path.exists(self.path):
                return False
            mtime = os.path.getmtime(self.path)
            if mtime == self._mtime and self.data:
                return False
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            merged = dict(self.DEFAULTS)
            merged.update(raw or {})
            self.data = merged
            self._mtime = mtime
            log.info("antiraid config reloaded for guild=%s: %s", self.guild_id,
                     {k: v for k, v in self.data.items() if k != "recent_events"})
            return True
        except Exception as e:
            log.warning("antiraid config reload failed for guild=%s: %s", self.guild_id, e)
            return False

    def is_whitelisted(self, user_id: int) -> bool:
        try:
            return int(user_id) in {int(x) for x in self.data.get("whitelist", []) or []}
        except Exception:
            return False

    def add_event(self, event: dict, limit: int = 20):
        events = self.data.setdefault("recent_events", [])
        events.insert(0, event)
        del events[limit:]
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            self._mtime = os.path.getmtime(self.path)
        except Exception as e:
            log.warning("antiraid event persist failed for guild=%s: %s", self.guild_id, e)


class AntiRaid(commands.Cog):
    """Анти-рейд в режиме наблюдателя — никаких авто-действий, только алерты."""

    def __init__(self, bot):
        self.bot = bot
        self.configs: dict[int, GuildAntiraidConfig] = {}
        self.join_tracker: dict[int, list[tuple[float, int]]] = defaultdict(list)
        self.config_watcher.start()

    def cog_unload(self):
        try:
            self.config_watcher.cancel()
        except Exception as _ex:
            _log.debug("cog_unload(): подавлено: %s", _ex)

    def get_config(self, guild_id: int) -> GuildAntiraidConfig:
        cfg = self.configs.get(guild_id)
        if cfg is None:
            cfg = GuildAntiraidConfig(guild_id)
            self.configs[guild_id] = cfg
        else:
            cfg.reload()
        return cfg

    @tasks.loop(seconds=5.0)
    async def config_watcher(self):
        for guild_id in list(self.configs.keys()):
            try:
                self.configs[guild_id].reload()
            except Exception as e:
                log.debug("watcher reload error guild=%s: %s", guild_id, e)
        try:
            for name in os.listdir("data"):
                if not (name.startswith("antiraid_") and name.endswith(".json")):
                    continue
                if name == "antiraid.json":
                    continue
                try:
                    gid = int(name[len("antiraid_"):-len(".json")])
                except ValueError as _ex:
                    _log.debug("config_watcher(): подавлено: %s", _ex)
                    continue
                if gid not in self.configs:
                    self.configs[gid] = GuildAntiraidConfig(gid)
        except Exception as _ex:
            _log.debug("config_watcher(): подавлено: %s", _ex)

    @config_watcher.before_loop
    async def before_config_watcher(self):
        await self.bot.wait_until_ready()

    async def _send_alert(self, guild: discord.Guild, cfg: GuildAntiraidConfig,
                          title: str, description: str, fields: list[tuple[str, str]] | None = None,
                          color: discord.Color = discord.Color.orange()):
        """Отправка алерта в канал алертов, иначе в mod-log, иначе в ЛС владельцу."""
        target = None
        cid = cfg.data.get("alert_channel_id")
        if cid:
            try:
                target = guild.get_channel(int(cid)) or await guild.fetch_channel(int(cid))
            except Exception:
                target = None
        if target is None:
            # Единый резолвер лог-каналов (-модерация → mod-log → …)
            try:
                from cogs.logs import ensure_log_channel
                target = await ensure_log_channel(guild, 'модерация')
            except Exception:
                target = None
        if target is None:
            target = discord.utils.get(guild.text_channels, name="mod-log")
        if target is None:
            try:
                if guild.owner:
                    await guild.owner.send(f"⚠️ **Алерт анти-рейда** (канал mod-log не найден): {title}\n{description}")
            except Exception as _ex:
                _log.debug("_send_alert(): подавлено: %s", _ex)
            return

        embed = discord.Embed(title=title, description=description, color=color,
                              timestamp=datetime.now(timezone.utc))
        embed.set_footer(text="Aether AntiRaid — Режим наблюдения (без авто-действий)")
        for name, value in (fields or []):
            embed.add_field(name=name, value=value, inline=False)
        try:
            await target.send(embed=embed)
        except Exception as e:
            log.warning("antiraid alert send failed: %s", e)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        if member.guild is None:
            return
        cfg = self.get_config(member.guild.id)
        if cfg.is_whitelisted(member.id):
            return

        guild_id = member.guild.id
        now = time.time()
        threshold = int(cfg.data.get("join_threshold", 5) or 5)
        window = int(cfg.data.get("join_window", 10) or 10)

        self.join_tracker[guild_id] = [
            (t, uid) for t, uid in self.join_tracker[guild_id]
            if now - t < window
        ]
        self.join_tracker[guild_id].append((now, member.id))

        account_age_days = (datetime.now(timezone.utc) - member.created_at).days
        min_age = int(cfg.data.get("min_age", 5) or 0)
        if cfg.data.get("age_filter") and min_age > 0 and account_age_days < min_age:
            await self._send_alert(
                member.guild, cfg,
                title="👶 Новый аккаунт присоединился (алерт)",
                description=f"{member.mention} присоединился, но аккаунт слишком новый.",
                fields=[
                    ("Пользователь", f"{member} (`{member.id}`)"),
                    ("Возраст аккаунта", f"{account_age_days} дней (мин: {min_age})"),
                    ("Создан", member.created_at.strftime("%Y-%m-%d %H:%M UTC")),
                ],
                color=discord.Color.yellow(),
            )
            cfg.add_event({
                "type": "young_account",
                "user_id": str(member.id),
                "user_tag": str(member),
                "account_age_days": account_age_days,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        if cfg.data.get("join_raid"):
            count = len(self.join_tracker[guild_id])
            if count >= threshold:
                await self._send_alert(
                    member.guild, cfg,
                    title="🚨 Волна присоединений похожая на рейд (алерт)",
                    description=(
                        f"За последние {window} секунд присоединилось **{count}** человек "
                        f"(порог: {threshold}). **Авто-действия отключены** — "
                        "вы можете вмешаться через страницу `/antiraid` в панели."
                    ),
                    fields=[
                        ("Порог", f"{count}/{threshold} чел / {window}с"),
                        ("Последний", f"{member} (`{member.id}`)"),
                    ],
                    color=discord.Color.dark_red(),
                )
                cfg.add_event({
                    "type": "join_raid",
                    "count": count,
                    "window": window,
                    "threshold": threshold,
                    "last_user": str(member),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not after.bot or before.bot:
            return
        if after.guild is None:
            return
        cfg = self.get_config(after.guild.id)
        if not cfg.data.get("bot_protection"):
            return
        if cfg.is_whitelisted(after.id):
            return
        await self._send_alert(
            after.guild, cfg,
            title="🤖 На сервер добавлен бот (алерт)",
            description=f"{after.mention} присоединился к серверу. **Авто-кик отключен** — проверьте в панели.",
            fields=[
                ("Бот", f"{after} (`{after.id}`)"),
                ("Владелец", "Неизвестно"),
            ],
            color=discord.Color.purple(),
        )
        cfg.add_event({
            "type": "bot_join",
            "user_id": str(after.id),
            "user_tag": str(after),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages:
            return
        guild = messages[0].guild
        if guild is None:
            return
        cfg = self.get_config(guild.id)
        if not cfg.data.get("delete_protection"):
            return
        if len(messages) < 5:
            return
        ch = messages[0].channel
        await self._send_alert(
            guild, cfg,
            title="🗑️ Обнаружено массовое удаление сообщений (алерт)",
            description=f"В канале #{ch.name} было массово удалено **{len(messages)}** сообщений.",
            fields=[
                ("Канал", f"#{ch.name} (`{ch.id}`)"),
                ("Количество", str(len(messages))),
            ],
            color=discord.Color.dark_grey(),
        )
        cfg.add_event({
            "type": "bulk_delete",
            "channel_id": str(ch.id),
            "count": len(messages),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    @app_commands.command(name="antiraid", description="Показать текущий статус системы анти-рейда")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid_status(self, interaction: discord.Interaction):
        cfg = self.get_config(interaction.guild.id)
        d = cfg.data
        e = discord.Embed(
            title="🛡️ Анти-рейд — Состояние",
            color=0x2ECC71 if (d.get("join_raid") or d.get("age_filter") or d.get("bot_protection")) else 0x95A5A6,
        )
        e.description = (
            "**Режим наблюдения**: бот не делает авто-кик/бан/локдаун, "
            "только уведомляет в канал алертов.\n"
            "Все настройки делаются на странице `/antiraid` в панели."
        )
        e.add_field(name="Обнаружение рейда", value="✅ Вкл" if d.get("join_raid") else "❌ Выкл", inline=True)
        e.add_field(name="Фильтр возраста", value="✅ Вкл" if d.get("age_filter") else "❌ Выкл", inline=True)
        e.add_field(name="Защита от ботов", value="✅ Вкл" if d.get("bot_protection") else "❌ Выкл", inline=True)
        e.add_field(name="Защита от массового удаления", value="✅ Вкл" if d.get("delete_protection") else "❌ Выкл", inline=True)
        e.add_field(name="Порог", value=f"{d.get('join_threshold', 5)} чел / {d.get('join_window', 10)}с", inline=True)
        e.add_field(name="Мин. возраст", value=f"{d.get('min_age', 5)} дней", inline=True)
        e.add_field(name="Белый список", value=f"{len(d.get('whitelist', []))} чел", inline=True)
        e.add_field(name="Канал алертов", value=f"<#{d['alert_channel_id']}>" if d.get("alert_channel_id") else "`mod-log` (по умолчанию)", inline=True)
        e.add_field(name="Последние события", value=str(len(d.get("recent_events", []))), inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="antiraid-reload", description="Сейчас перезагрузить конфиг анти-рейда с диска")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid_reload(self, interaction: discord.Interaction):
        cfg = self.get_config(interaction.guild.id)
        changed = cfg.reload()
        await interaction.response.send_message(
            f"🔄 Конфиг {'изменился и перезагружен' if changed else 'уже актуален'}.",
            ephemeral=True,
        )


async def setup(bot):
    # Серверы для slash-команд — из .env (MAIN_GUILD_ID + EXTRA_GUILD_IDS)
    from config import Config
    await bot.add_cog(
        AntiRaid(bot),
        guilds=Config.guild_objects(),
    )
