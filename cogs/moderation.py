import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta, timezone
import json
import os
from cogs.embed_utils import gif, now_ts, mod_dm_embed, mod_log_embed, success_embed, error_embed, _divider

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def save_case(self, guild_id, action, user_id, mod_id, reason):
        os.makedirs('data', exist_ok=True)
        filepath = 'data/mod_data.json'
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {'caголос': {}}
            gid = str(guild_id)
            if gid not in data['caголос']:
                data['caголос'][gid] = []
            case_id = len(data['caголос'][gid]) + 1
            data['caголос'][gid].append({
                'id': case_id, 'action': action,
                'user_id': str(user_id), 'mod_id': str(mod_id),
                'reason': reason or 'Не указана',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return case_id
        except Exception as e:
            print(f"Case сохранитьme Ошибкаsı: {e}")
            return 0

    async def send_log(self, guild, embed):
        ch = discord.utils.get(guild.text_channels, name="mod-log")
        if ch:
            await ch.send(embed=embed)

    async def _notify_owner(self, action: str, user, mod, reason: str = None):
        """Owner'a mod действиеi уведомлениеi отправить — sadece уведомление açıksa"""
        owner_id = int(os.getenv('OWNER_ID', '0'))
        if not owner_id or not mod:
            return
        if mod.id == owner_id:
            return
        # Уведомление kapalıysa отправитьme
        flag_file = 'data/mod_notify.json'
        try:
            import json as _j
            enabled = _j.load(open(flag_file, encoding='utf-8')).get('enabled', False) if os.path.exists(flag_file) else False
        except:
            enabled = False
        if not enabled:
            return
        try:
            owner = await self.bot.fetch_user(owner_id)
            action_emoji = {'ban': '🔨', 'kick': '👢', 'timeout': '⏱️', 'warn': '⚠️', 'unban': '✅'}.get(action, '📌')
            msg = (
                f"{action_emoji} **{action.upper()}** — "
                f"**{user.display_name if hasattr(user, 'display_name') else user}** "
                f"| Mod: **{mod.display_name}**"
                + (f" | Причина: *{reason}*" if reason else "")
            )
            await owner.send(msg)
        except Exception as e:
            print(f'[MOD] Owner уведомление Ошибкаsı: {e}')

    async def send_dm(self, user, embed):
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            pass

    def _confirm_embed(self, action: str, user: discord.Member, guild: discord.Guild,
                       reason: str, case_id: int, extra: str = "") -> discord.Embed:
        """Модераторe gösterilen onay embed'i — detaylı ve zengin."""
        configs = {
            "ban":       ("🔨 Бан Uygulandı",       0xE74C3C, "kalıcı olarak uzaklaştırıldı"),
            "kick":      ("👢 Кик Uygulandı",       0xE67E22, "serverdan atıldı"),
            "timeout":   ("🔇 Мут Uygulandı",    0xF39C12, "geçici olarak susturuldu"),
            "untimeout": ("🔊 Мут Снят",   0x2ECC71, "artık message отправитьebilir"),
            "unban":     ("🔓 Бан Снят",       0x2ECC71, "serverya geri dönebilir"),
        }
        title, color, action_text = configs.get(action, ("✅ Действие выполнено", 0x2ECC71, "действие применено"))

        e = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
        e.set_thumbnail(url=user.display_avatar.url)
        e.description = (
            f"```ansi\n\u001b[1;32m✔ İŞLEM BAŞARILI\u001b[0m\n```\n"
            f"{_divider()}\n\n"
            f"{user.mention} **{action_text}**.\n\n"
            f"{_divider()}"
        )
        e.add_field(name="👤 Пользователь", value=f"{user.mention}\n`{user.id}`", inline=True)
        e.add_field(name="🆔 Case", value=f"```#{case_id}```", inline=True)
        e.add_field(name="📨 DM Уведомлениеi", value="```✅ Отправитьildi```", inline=True)
        e.add_field(name="📝 Причина", value=f"```{reason or 'Не указана'}```", inline=False)
        if extra:
            e.add_field(name="ℹ️ Ek Информация", value=extra, inline=False)
        e.add_field(name="🕐 Время", value=f"<t:{now_ts()}:F>", inline=False)
        e.set_footer(
            text=f"Aether Moderasyon • {guild.name}",
            icon_url=guild.icon.url if guild.icon else None
        )
        return e

    @app_commands.command(name="moderate", description="Moderasyon действиеleri: ban, kick, timeout, untimeout, unban")
    @app_commands.choices(action=[
        app_commands.Choice(name="ban", value="ban"),
        app_commands.Choice(name="kick", value="kick"),
        app_commands.Choice(name="timeout", value="timeout"),
        app_commands.Choice(name="untimeout", value="untimeout"),
        app_commands.Choice(name="unban", value="unban")
    ])
    @app_commands.checks.has_permissions(ban_members=True)
    async def moderate_user(self, interaction: discord.Interaction, action: str,
                            user: discord.Member = None, user_id: str = None,
                            minutes: int = None, reason: str = None):
        guild = interaction.guild

        if action == "ban":
            if not user:
                await interaction.response.send_message(embed=error_embed("Банlamak istediğin useryı belirtmelisin."), ephemeral=True)
                return
            try:
                dm = mod_dm_embed("ban", guild, interaction.user, reason)
                await self.send_dm(user, dm)
                await user.ban(reason=reason)
                case_id = self.save_case(guild.id, 'ban', user.id, interaction.user.id, reason)
                log = mod_log_embed("ban", "BAN UYGULANDИ", 0xE74C3C, user, interaction.user, guild, reason, case_id)
                await self.send_log(guild, log)
                confirm = self._confirm_embed("ban", user, guild, reason, case_id)
                await interaction.response.send_message(embed=confirm, ephemeral=True)
                await self._notify_owner('ban', user, interaction.user, reason)
            except discord.Forbidden:
                await interaction.response.send_message(embed=error_embed("Ботun roleü hedef userdan üstte olmalı.", "Право Ошибкаsı"), ephemeral=True)
            except Exception as ex:
                await interaction.response.send_message(embed=error_embed(str(ex)), ephemeral=True)

        elif action == "kick":
            if not user:
                await interaction.response.send_message(embed=error_embed("Atmak istediğin useryı belirtmelisin."), ephemeral=True)
                return
            try:
                dm = mod_dm_embed("kick", guild, interaction.user, reason)
                await self.send_dm(user, dm)
                await user.kick(reason=reason)
                case_id = self.save_case(guild.id, 'kick', user.id, interaction.user.id, reason)
                log = mod_log_embed("kick", "KICK UYGULANDИ", 0xE67E22, user, interaction.user, guild, reason, case_id)
                await self.send_log(guild, log)
                confirm = self._confirm_embed("kick", user, guild, reason, case_id)
                await interaction.response.send_message(embed=confirm, ephemeral=True)
                await self._notify_owner('kick', user, interaction.user, reason)
            except discord.Forbidden:
                await interaction.response.send_message(embed=error_embed("Ботun roleü hedef userdan üstte olmalı.", "Право Ошибкаsı"), ephemeral=True)
            except Exception as ex:
                await interaction.response.send_message(embed=error_embed(str(ex)), ephemeral=True)

        elif action == "timeout":
            if not user:
                await interaction.response.send_message(embed=error_embed("Susturmak istediğin useryı belirtmelisin."), ephemeral=True)
                return
            sure = minutes if minutes is not None else 5
            try:
                until = discord.utils.utcnow() + timedelta(minutes=sure)
                dm = mod_dm_embed(
                    "timeout", guild, interaction.user, reason,
                    extra_fields=[
                        ("⏱️ Süre", f"**{minutes} minutes**", True),
                        ("🔓 Bitiş", f"<t:{int(until.timestamp())}:R>", True),
                    ]
                )
                await self.send_dm(user, dm)
                await user.timeout(until, reason=reason)
                case_id = self.save_case(guild.id, 'timeout', user.id, interaction.user.id, reason)
                log = mod_log_embed("timeout", "TIMEOUT UYGULANDИ", 0xF39C12, user, interaction.user, guild, reason, case_id,
                    extra_fields=[("⏱️ Süre", f"```{sure} minutes```", True), ("🔓 Bitiş", f"<t:{int(until.timestamp())}:R>", True)])
                await self.send_log(guild, log)
                confirm = self._confirm_embed("timeout", user, guild, reason, case_id,
                    extra=f"⏱️ **Süre:** {sure} minutes\n🔓 **Bitiş:** <t:{int(until.timestamp())}:R>")
                await interaction.response.send_message(embed=confirm, ephemeral=True)
                await self._notify_owner('timeout', user, interaction.user, reason)
            except discord.Forbidden:
                await interaction.response.send_message(embed=error_embed("Правоm yok!", "Право Ошибкаsı"), ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(embed=error_embed(str(e)), ephemeral=True)

        elif action == "untimeout":
            if not user:
                await interaction.response.send_message(embed=error_embed("Пользователя belirtmelisin."), ephemeral=True)
                return
            try:
                await user.timeout(None)
                dm = mod_dm_embed("untimeout", guild, interaction.user)
                await self.send_dm(user, dm)
                log = mod_log_embed("untimeout", "TIMEOUT KALDIRILDI", 0x2ECC71, user, interaction.user, guild)
                await self.send_log(guild, log)
                confirm = self._confirm_embed("untimeout", user, guild, reason, 0)
                await interaction.response.send_message(embed=confirm, ephemeral=True)
            except Exception as ex:
                await interaction.response.send_message(embed=error_embed(str(ex)), ephemeral=True)

        elif action == "unban":
            if not user_id:
                await interaction.response.send_message(embed=error_embed("Банı убратьmak istediğin usernın ID'sini `user_id` alanına gir."), ephemeral=True)
                return
            try:
                fetched = await self.bot.fetch_user(int(user_id))
                await guild.unban(fetched)
                e = discord.Embed(
                    title="🔓  Бан Снят",
                    color=0x2ECC71,
                    timestamp=datetime.now(timezone.utc)
                )
                e.set_thumbnail(url=fetched.display_avatar.url)
                e.description = (
                    f"```ansi\n\u001b[1;32m✔ BAN KALDIRILDI\u001b[0m\n```\n"
                    f"{_divider()}\n\n"
                    f"**{fetched.name}** artık serverya geri dönebilir.\n\n"
                    f"{_divider()}"
                )
                e.add_field(name="👤 Пользователь", value=f"`{fetched.name}` • `{fetched.id}`", inline=True)
                e.add_field(name="👮 Модератор", value=interaction.user.mention, inline=True)
                e.add_field(name="🕐 Дата", value=f"<t:{now_ts()}:R>", inline=False)
                e.set_footer(text=f"Aether Moderasyon • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
                await self.send_log(guild, e)
                await interaction.response.send_message(embed=e, ephemeral=True)
            except Exception as ex:
                await interaction.response.send_message(embed=error_embed(str(ex)), ephemeral=True)

    @moderate_user.error
    async def moderate_user_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                embed=error_embed("Bu командаu kullanmak için **Бан Участникleri** правоsine ihtiyacın var.", "Право Ошибкаsı"),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(embed=error_embed(str(error)), ephemeral=True)

    @app_commands.command(name="leaveguild", description="Ботu belirtilen serverdan çıkarır (sadece bot sahibi)")
    async def leave_guild(self, interaction: discord.Interaction, guild_id: str):
        # Sadece bot sahibi kullanabilir
        app_info = await self.bot.application_info()
        if interaction.user.id != app_info.owner.id:
            await interaction.response.send_message(
                embed=error_embed("Bu команда sadece bot sahibi tarafından kullanılabilir.", "Право Ошибкаsı"),
                ephemeral=True
            )
            return
        try:
            target = self.bot.get_guild(int(guild_id))
            if not target:
                await interaction.response.send_message(embed=error_embed(f"`{guild_id}` ID'li server bulunamadı veya bot orada değil."), ephemeral=True)
                return
            guild_name = target.name
            await target.leave()
            e = discord.Embed(title="🚪  Серверdan Çıkıldı", color=0x2ECC71, timestamp=datetime.now(timezone.utc))
            e.description = f"**{guild_name}** (`{guild_id}`) serversundan başarıyla çıkıldı."
            await interaction.response.send_message(embed=e, ephemeral=True)
        except ValueError:
            await interaction.response.send_message(embed=error_embed("Geçersiz server ID'si."), ephemeral=True)
        except Exception as ex:
            await interaction.response.send_message(embed=error_embed(str(ex)), ephemeral=True)

    @app_commands.command(name="utility", description="Yardımcı командаlar: clear, slowmode, lock, unlock, userinfo, serverinfo")
    @app_commands.choices(action=[
        app_commands.Choice(name="clear", value="clear"),
        app_commands.Choice(name="slowmode", value="slowmode"),
        app_commands.Choice(name="lock", value="lock"),
        app_commands.Choice(name="unlock", value="unlock"),
        app_commands.Choice(name="userinfo", value="userinfo"),
        app_commands.Choice(name="serverinfo", value="serverinfo")
    ])
    @app_commands.checks.has_permissions(manage_messages=True)
    async def utility_commands(self, interaction: discord.Interaction, action: str,
                               adet: int = 10, saniye: int = 0, user: discord.Member = None):
        guild = interaction.guild

        if action == "clear":
            await interaction.response.defer(ephemeral=True)
            deleted = await interaction.channel.purge(limit=adet)
            e = discord.Embed(
                title="🗑️  Сообщениеlar Очиститьndi",
                color=0xDC143C,
                timestamp=datetime.now(timezone.utc)
            )
            e.description = (
                f"```ansi\n\u001b[1;31m{len(deleted)} MESAJ SİLİNDİ\u001b[0m\n```\n"
                f"{_divider()}"
            )
            e.add_field(name="📺 Канал", value=interaction.channel.mention, inline=True)
            e.add_field(name="👮 Модератор", value=interaction.user.mention, inline=True)
            e.add_field(name="🗑️ Удалитьinen", value=f"```{len(deleted)} message```", inline=True)
            e.add_field(name="🕐 Дата", value=f"<t:{now_ts()}:R>", inline=False)
            e.set_footer(text=f"Aether Moderasyon • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
            await interaction.followup.send(embed=e, ephemeral=True)

        elif action == "slowmode":
            if saniye < 0 or saniye > 21600:
                await interaction.response.send_message(embed=error_embed("Saniye değeri 0 ile 21600 arasında olmalıdır.", "Geçersiz Değer"), ephemeral=True)
                return
            await interaction.channel.edit(slowmode_delay=saniye)
            e = discord.Embed(title="🐌  Yavaş Mod Обновлено", color=0xDC143C, timestamp=datetime.now(timezone.utc))
            e.description = f"```ansi\n\u001b[1;33mSLOWMODE AKTİF\u001b[0m\n```\n{_divider()}"
            e.add_field(name="📺 Канал", value=interaction.channel.mention, inline=True)
            e.add_field(name="⏱️ Gecikme", value=f"```{saniye} saniye```", inline=True)
            e.add_field(name="👮 Модератор", value=interaction.user.mention, inline=True)
            e.set_footer(text=f"Aether Moderasyon • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
            await interaction.response.send_message(embed=e, ephemeral=True)

        elif action == "lock":
            await interaction.channel.set_permissions(guild.default_role, send_messages=False)
            e = discord.Embed(title="🔒  Канал Kilitlendi", color=0xE74C3C, timestamp=datetime.now(timezone.utc))
            e.description = (
                f"```ansi\n\u001b[1;31m🔒 KANAL KİLİTLENDİ\u001b[0m\n```\n"
                f"{_divider()}\n\n"
                "Bu channel geçici olarak **kilitlenmiştir**.\n"
                "Сообщение отправитьmek şu an devre dışı bırakıldı.\n\n"
                f"{_divider()}"
            )
            e.add_field(name="👮 Kilitleyen", value=interaction.user.mention, inline=True)
            e.add_field(name="🕐 Дата", value=f"<t:{now_ts()}:R>", inline=True)
            e.set_thumbnail(url=guild.icon.url if guild.icon else None)
            e.set_footer(text=f"Aether Moderasyon • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
            await interaction.channel.send(embed=e)
            await interaction.response.send_message("✅ Канал kilitlendi.", ephemeral=True)

        elif action == "unlock":
            await interaction.channel.set_permissions(guild.default_role, send_messages=True)
            e = discord.Embed(title="🔓  Канал Kilidi Открытьıldı", color=0x2ECC71, timestamp=datetime.now(timezone.utc))
            e.description = (
                f"```ansi\n\u001b[1;32m🔓 KİLİT AÇILDI\u001b[0m\n```\n"
                f"{_divider()}\n\n"
                "Bu channelın kilidi **açılmıştır**.\n"
                "Artık tekrar message отправитьebilirsiniz. 🎉\n\n"
                f"{_divider()}"
            )
            e.add_field(name="👮 Открытьan", value=interaction.user.mention, inline=True)
            e.add_field(name="🕐 Дата", value=f"<t:{now_ts()}:R>", inline=True)
            e.set_thumbnail(url=guild.icon.url if guild.icon else None)
            e.set_footer(text=f"Aether Moderasyon • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
            await interaction.channel.send(embed=e)
            await interaction.response.send_message("✅ Канал kilidi açıldı.", ephemeral=True)

        elif action == "userinfo":
            u = user or interaction.user
            rozet = "👑" if u == guild.owner else "🛡️" if u.guild_permissions.administrator else "⚔️" if u.guild_permissions.moderate_members else "👤"
            e = discord.Embed(
                title=f"{rozet}  {u.display_name} — Пользователь Информацияsi",
                color=u.color if u.color != discord.Color.default() else 0x3498DB,
                timestamp=datetime.now(timezone.utc)
            )
            e.set_thumbnail(url=u.display_avatar.url)
            e.description = f"```ansi\n\u001b[1;34mKULLANICI PROFİLİ\u001b[0m\n```\n{_divider()}"
            e.add_field(name="🆔 ID", value=f"```{u.id}```", inline=True)
            e.add_field(name="📛 Пользователь Имяı", value=f"```{u.name}```", inline=True)
            e.add_field(name="🏷️ Takma Имя", value=f"```{u.display_name}```", inline=True)
            e.add_field(name="📅 Hesap Создатьulma", value=f"<t:{int(u.created_at.timestamp())}:F>\n<t:{int(u.created_at.timestamp())}:R>", inline=False)
            e.add_field(name="📥 Серверya Katılma", value=f"<t:{int(u.joined_at.timestamp())}:F>\n<t:{int(u.joined_at.timestamp())}:R>", inline=False)
            roles = [r.mention for r in u.roles[1:]]
            e.add_field(name=f"🎭 Роли ({len(roles)})", value=" ".join(roles[:20]) if roles else "```Role yok```", inline=False)
            e.set_footer(text=f"İsteyen: {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
            await interaction.response.send_message(embed=e)

        elif action == "serverinfo":
            g = guild
            ботlar = sum(1 for m in g.members if m.bot)
            insanlar = g.member_count - ботlar
            e = discord.Embed(
                title=f"🏰  {g.name} — Сервер Информацияsi",
                color=0x3498DB,
                timestamp=datetime.now(timezone.utc)
            )
            e.description = f"```ansi\n\u001b[1;34mSUNUCU İSTATİSTİKLERİ\u001b[0m\n```\n{_divider()}"
            if g.icon:
                e.set_thumbnail(url=g.icon.url)
            if g.banner:
                e.set_image(url=g.banner.url)
            e.add_field(name="👑 Sahip", value=f"{g.owner.mention}", inline=True)
            e.add_field(name="🆔 ID", value=f"```{g.id}```", inline=True)
            e.add_field(name="📅 Создатьulma", value=f"<t:{int(g.created_at.timestamp())}:R>", inline=True)
            e.add_field(name="👥 Всего Участник", value=f"```{g.member_count}```", inline=True)
            e.add_field(name="👤 İnsan", value=f"```{insanlar}```", inline=True)
            e.add_field(name="🤖 Бот", value=f"```{ботlar}```", inline=True)
            e.add_field(name="💬 Metin Каналı", value=f"```{len(g.text_channels)}```", inline=True)
            e.add_field(name="🔊 Голос Каналı", value=f"```{len(g.voice_channels)}```", inline=True)
            e.add_field(name="🎭 Роль", value=f"```{len(g.roles)}```", inline=True)
            e.add_field(name="💎 Boost", value=f"```Уровень {g.premium_tier} • {g.premium_subscription_count} boost```", inline=False)
            e.set_footer(text=f"Aether • {g.name}", icon_url=g.icon.url if g.icon else None)
            await interaction.response.send_message(embed=e)

    @app_commands.command(name="role", description="Пользователю role verir veya alır")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        guild = interaction.guild
        if role in user.roles:
            await user.remove_roles(role)
            action_text, color, title, badge = "убратьıldı", 0xE74C3C, "🎭  Role Снят", "ROL ALINDI"
        else:
            await user.add_roles(role)
            action_text, color, title, badge = "verildi", 0x2ECC71, "🎭  Role Verildi", "ROL VERİLDİ"

        e = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
        e.set_thumbnail(url=user.display_avatar.url)
        e.description = (
            f"```ansi\n\u001b[1;32m✔ {badge}\u001b[0m\n```\n"
            f"{_divider()}\n\n"
            f"{user.mention} usersına {role.mention} roleü **{action_text}**.\n\n"
            f"{_divider()}"
        )
        e.add_field(name="👤 Пользователь", value=f"{user.mention}\n`{user.id}`", inline=True)
        e.add_field(name="🎭 Роль", value=role.mention, inline=True)
        e.add_field(name="👮 Модератор", value=interaction.user.mention, inline=True)
        e.add_field(name="🕐 Дата", value=f"<t:{now_ts()}:R>", inline=False)
        e.set_footer(text=f"Aether Moderasyon • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Moderation(bot), guilds=[discord.Object(id=1421244140359909513), discord.Object(id=1107038411895881788)])
