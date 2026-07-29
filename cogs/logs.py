import discord
from discord.ext import commands
from discord import app_commands
import datetime
import json
import os
import time
import threading
import queue
from typing import Dict, Any

AUDIT_FILE = "data/audit_log.json"

CATEGORIES = {
    'mod':     {'label': 'Модерация',  'emoji': '🔨', 'color': 0xE74C3C, 'channel': 'модерация'},
    'member':  {'label': 'Участники',   'emoji': '👤', 'color': 0x2ECC71, 'channel': 'участники'},
    'message': {'label': 'Сообщения',   'emoji': '💬', 'color': 0x3498DB, 'channel': 'сообщения'},
    'role':    {'label': 'Роли',        'emoji': '🎭', 'color': 0x9B59B6, 'channel': 'сервер'},
    'channel': {'label': 'Каналы',      'emoji': '📺', 'color': 0xF39C12, 'channel': 'сервер'},
    'voice':   {'label': 'Голос',       'emoji': '🔊', 'color': 0x1ABC9C, 'channel': 'голос'},
    'server':  {'label': 'Сервер',      'emoji': '🏰', 'color': 0xE67E22, 'channel': 'сервер'},
    'automod': {'label': 'АвтоМод',     'emoji': '🤖', 'color': 0xE74C3C, 'channel': 'модерация'},
    'invite':  {'label': 'Приглашения', 'emoji': '📨', 'color': 0x95A5A6, 'channel': 'сервер'},
}

DIV = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Кэш сообщений — чтобы знать содержание удалённых
_msg_cache: dict = {}

# Queue-based запись — один поток, нет race condition
_audit_queue: queue.Queue = queue.Queue()
_audit_worker_thread: threading.Thread = None

def _audit_worker():
    while True:
        try:
            event_data = _audit_queue.get(timeout=2.0)
        except queue.Empty:
            continue
        if event_data is None:
            break
        try:
            _write_audit_event(event_data)
        except Exception as e:
            print(f"[AUDIT-WORKER] Ошибка записи: {e}")
        finally:
            _audit_queue.task_done()

def _write_audit_event(event_data: Dict[str, Any]):
    guild_id = event_data['guild_id']
    category = event_data['category']
    action   = event_data['action']
    details  = event_data['details']

    os.makedirs("data", exist_ok=True)
    data = {}
    if os.path.exists(AUDIT_FILE):
        for _ in range(5):
            try:
                with open(AUDIT_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                break
            except (json.JSONDecodeError, OSError):
                time.sleep(0.1)

    gid = str(guild_id)
    data.setdefault(gid, [])
    data[gid].append({
        'category':  category,
        'action':    action,
        'timestamp': datetime.datetime.utcnow().isoformat(),
        **details
    })
    if len(data[gid]) > 2000:
        data[gid] = data[gid][-2000:]

    tmp = AUDIT_FILE + f'.tmp{os.getpid()}'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        for _ in range(5):
            try:
                if os.path.exists(AUDIT_FILE):
                    os.replace(tmp, AUDIT_FILE)
                else:
                    os.rename(tmp, AUDIT_FILE)
                break
            except PermissionError:
                time.sleep(0.2)
    except Exception as e:
        print(f"[AUDIT] Ошибка записи: {e}")
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except:
            pass

def _ensure_worker():
    global _audit_worker_thread
    if _audit_worker_thread is None or not _audit_worker_thread.is_alive():
        _audit_worker_thread = threading.Thread(target=_audit_worker, daemon=True, name="audit-worker")
        _audit_worker_thread.start()

def save_event(guild_id, category, action, details: dict):
    if action == 'Сообщение отправлено':
        return
    _ensure_worker()
    _audit_queue.put({
        'guild_id': guild_id,
        'category': category,
        'action':   action,
        'details':  details,
    })


# Имена лог-каналов
LOG_CHANNELS = {
    'модерация':  '🔨-модерация',
    'участники':  '👤-участники',
    'сообщения':  '💬-сообщения',
    'голос':      '🔊-голос',
    'сервер':     '⚙️-сервер',
}
LOG_CATEGORY_NAME = '📋 Логи'


class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_log_channel(self, guild, category: str = 'server'):
        """Найти канал для конкретной категории логов"""
        ch_name = CATEGORIES.get(category, {}).get('channel', 'сервер')
        target = LOG_CHANNELS.get(ch_name, LOG_CHANNELS['сервер'])

        # Ищем по точному имени
        ch = discord.utils.get(guild.text_channels, name=target)
        if ch:
            return ch

        # Fallback: ищем старый server-log
        ch = discord.utils.get(guild.text_channels, name="server-log")
        if ch:
            return ch

        # Fallback: ищем aether-logs
        ch = discord.utils.get(guild.text_channels, name="aether-logs")
        return ch

    # ─── КОМАНДА: СОЗДАТЬ ЛОГ-КАНАЛЫ ─────────────────────────────────

    @app_commands.command(name="setup-logs", description="Создать категорию и каналы для логов")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_logs(self, interaction: discord.Interaction):
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)

        # Проверяем есть ли уже категория
        existing_cat = discord.utils.get(guild.categories, name=LOG_CATEGORY_NAME)

        if not existing_cat:
            # Создаём категорию с правами
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    read_messages=False,
                ),
                guild.me: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    embed_links=True,
                    attach_files=True,
                    read_message_history=True,
                ),
            }
            # Даём доступ модераторам (роли с правом kick/ban)
            for role in guild.roles:
                if role.permissions.kick_members or role.permissions.ban_members or role.permissions.administrator:
                    overwrites[role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=False,
                        read_message_history=True,
                    )

            existing_cat = await guild.create_category(
                LOG_CATEGORY_NAME,
                overwrites=overwrites,
                reason="Aether: создание категории логов"
            )

        created = []
        already = []

        for ch_name in LOG_CHANNELS.values():
            existing = discord.utils.get(guild.text_channels, name=ch_name)
            if existing:
                # Перемещаем в категорию если не в ней
                if existing.category != existing_cat:
                    await existing.edit(category=existing_cat)
                already.append(ch_name)
            else:
                ch = await guild.create_text_channel(
                    ch_name,
                    category=existing_cat,
                    reason="Aether: создание лог-канала",
                    topic=f"Журнал событий: {ch_name}"
                )
                created.append(ch_name)

        # Создаём канал для приветствий если нет
        welcome_ch = discord.utils.get(guild.text_channels, name="👋-приветствия")
        if not welcome_ch:
            welcome_ch = await guild.create_text_channel(
                "👋-приветствия",
                category=existing_cat,
                reason="Aether: канал приветствий",
                topic="Приветствия и прощания с участниками"
            )
            created.append("👋-приветствия")
        else:
            already.append("👋-приветствия")

        result_lines = []
        if created:
            result_lines.append(f"✅ **Создано ({len(created)}):**\n" + "\n".join(f"• {c}" for c in created))
        if already:
            result_lines.append(f"📌 **Уже существуют ({len(already)}):**\n" + "\n".join(f"• {a}" for a in already))

        e = discord.Embed(
            title="📋 Система логов настроена",
            description="\n\n".join(result_lines),
            color=0x2ECC71,
            timestamp=datetime.datetime.utcnow()
        )
        e.add_field(
            name="📂 Каналы",
            value=(
                "🔨 **-модерация** — баны, кики, муты, предупреждения\n"
                "👤 **-участники** — вход, выход, смена ника\n"
                "💬 **-сообщения** — удаление, редактирование\n"
                "🔊 **-голос** — вход/выход из голосовых\n"
                "⚙️ **-сервер** — каналы, роли, инвайты, сервер\n"
                "👋 **-приветствия** — приветствия и прощания"
            ),
            inline=False
        )
        e.set_footer(text=f"Aether • {guild.name}", icon_url=guild.icon.url if guild.icon else None)
        await interaction.followup.send(embed=e, ephemeral=True)

    # ─── УЧАСТНИКИ ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member):
        age_days = (discord.utils.utcnow() - member.created_at).days
        save_event(member.guild.id, 'member', 'Участник вошёл', {
            'user_id': str(member.id),
            'user_name': str(member),
            'avatar': str(member.display_avatar.url),
            'account_age_days': age_days,
        })

        # Приветственное сообщение
        try:
            wcfg_path = f'data/welcome_{member.guild.id}.json'
            if os.path.exists(wcfg_path):
                with open(wcfg_path, 'r', encoding='utf-8') as f:
                    wcfg = json.load(f)
                w = wcfg.get('welcome', {})
                if w.get('channel_id'):
                    wch = member.guild.get_channel(int(w['channel_id']))
                    if wch:
                        title = (w.get('title') or 'Добро пожаловать, {user}!').replace('{user}', member.display_name).replace('{server}', member.guild.name).replace('{count}', str(member.guild.member_count)).replace('{mention}', member.mention)
                        msg = (w.get('message') or '{mention} добро пожаловать на сервер!').replace('{user}', member.display_name).replace('{server}', member.guild.name).replace('{count}', str(member.guild.member_count)).replace('{mention}', member.mention)
                        color = int(w.get('color', '#c8922a').lstrip('#'), 16)
                        e = discord.Embed(title=title, description=msg, color=color)
                        e.set_thumbnail(url=member.display_avatar.url)
                        await wch.send(embed=e)
        except Exception as _e:
            print(f'[WELCOME] Ошибка: {_e}')

        ch = await self.get_log_channel(member.guild, 'member')
        if not ch:
            return

        age_text = f"новый аккаунт ({age_days} дн.)" if age_days < 7 else f"{age_days} дн."
        member_count = member.guild.member_count
        join_ts = int(datetime.datetime.utcnow().timestamp())

        e = discord.Embed(color=0xC8922A, timestamp=datetime.datetime.utcnow())
        e.description = (
            f"## Добро пожаловать!\n"
            f"### {member.mention} присоединился к серверу\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**Пользователь** — {member.display_name}\n"
            f"**ID** — `{member.id}`\n"
            f"**Аккаунт** — {age_text}\n"
            f"**Участник** — {member_count}-й на сервере\n"
            f"**Присоединился** — <t:{join_ts}:R>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        e.set_thumbnail(url=member.display_avatar.url)
        if member.guild.banner:
            e.set_image(url=member.guild.banner.url)
        e.set_footer(text=f"{member.guild.name}")
        await ch.send(embed=e)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        save_event(member.guild.id, 'member', 'Участник вышел', {
            'user_id': str(member.id),
            'user_name': str(member),
            'avatar': str(member.display_avatar.url),
            'roles': [r.name for r in member.roles[1:]],
        })

        # Прощальное сообщение
        try:
            wcfg_path = f'data/welcome_{member.guild.id}.json'
            if os.path.exists(wcfg_path):
                with open(wcfg_path, 'r', encoding='utf-8') as f:
                    wcfg = json.load(f)
                lv = wcfg.get('leave', {})
                if lv.get('channel_id'):
                    lch = member.guild.get_channel(int(lv['channel_id']))
                    if lch:
                        title = (lv.get('title') or 'До свидания, {user}!').replace('{user}', member.display_name).replace('{server}', member.guild.name).replace('{count}', str(member.guild.member_count)).replace('{mention}', member.mention)
                        msg = (lv.get('message') or '{user} покинул сервер.').replace('{user}', member.display_name).replace('{server}', member.guild.name).replace('{count}', str(member.guild.member_count)).replace('{mention}', member.mention)
                        color = int(lv.get('color', '#e05555').lstrip('#'), 16)
                        e = discord.Embed(title=title, description=msg, color=color)
                        e.set_thumbnail(url=member.display_avatar.url)
                        await lch.send(embed=e)
        except Exception as _e:
            print(f'[LEAVE] Ошибка: {_e}')

        ch = await self.get_log_channel(member.guild, 'member')
        if not ch:
            return

        roles_str = ", ".join(r.name for r in member.roles[1:]) if member.roles[1:] else "нет"
        member_count = member.guild.member_count
        # Вычисляем сколько был на сервере
        joined_ago = ""
        if member.joined_at:
            days_on_server = (datetime.datetime.utcnow() - member.joined_at.replace(tzinfo=None)).days
            if days_on_server == 0:
                joined_ago = "менее дня"
            elif days_on_server == 1:
                joined_ago = "1 день"
            elif days_on_server < 30:
                joined_ago = f"{days_on_server} дн."
            elif days_on_server < 365:
                joined_ago = f"{days_on_server // 30} мес."
            else:
                joined_ago = f"{days_on_server // 365} г. {days_on_server % 365 // 30} мес."

        e = discord.Embed(color=0xE74C3C, timestamp=datetime.datetime.utcnow())
        e.description = (
            f"## Участник вышел\n"
            f"### {member.display_name} покинул сервер\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**Пользователь** — {member.display_name}\n"
            f"**ID** — `{member.id}`\n"
            f"**Был на сервере** — {joined_ago}\n"
            f"**Роли** — {roles_str[:200]}\n"
            f"**Участников** — {member_count}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        e.set_thumbnail(url=member.display_avatar.url)
        e.set_footer(text=f"{member.guild.name}")
        await ch.send(embed=e)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        save_event(guild.id, 'mod', 'Бан', {
            'user_id': str(user.id),
            'user_name': str(user),
            'avatar': str(user.display_avatar.url),
        })

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        save_event(guild.id, 'mod', 'Бан снят', {
            'user_id': str(user.id),
            'user_name': str(user),
        })

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        # Смена ролей
        if before.roles != after.roles:
            added = [r for r in after.roles if r not in before.roles]
            removed = [r for r in before.roles if r not in after.roles]
            if added or removed:
                save_event(before.guild.id, 'role', 'Роли изменены', {
                    'user_id': str(before.id),
                    'user_name': str(before),
                    'added_roles': [r.name for r in added],
                    'removed_roles': [r.name for r in removed],
                })
                ch = await self.get_log_channel(before.guild, 'role')
                if ch:
                    e = discord.Embed(color=0x9B59B6, timestamp=datetime.datetime.utcnow())
                    desc = f"## Роли изменены\n**{before.display_name}** · `{before.id}`\n\n"
                    if added:
                        desc += f"Добавлены: {', '.join(r.mention for r in added)}\n"
                    if removed:
                        desc += f"Сняты: {', '.join(r.mention for r in removed)}"
                    e.description = desc
                    e.set_footer(text=f"{before.guild.name}")
                    await ch.send(embed=e)

        # Мут
        before_to = getattr(before, 'timed_out_until', None)
        after_to  = getattr(after,  'timed_out_until', None)
        if before_to != after_to:
            if after_to:
                save_event(before.guild.id, 'mod', 'Мут', {
                    'user_id': str(after.id),
                    'user_name': after.display_name,
                    'action': 'timeout',
                    'reason': 'Через Discord',
                    'until': after_to.isoformat() if after_to else '',
                })
                # Записываем в mod_data.json
                try:
                    os.makedirs('data', exist_ok=True)
                    _f = 'data/mod_data.json'
                    _d = {'cases': {}}
                    if os.path.exists(_f):
                        with open(_f, 'r', encoding='utf-8') as fp:
                            _d = json.load(fp)
                    _gid = str(before.guild.id)
                    _d['cases'].setdefault(_gid, [])
                    _d['cases'][_gid].append({
                        'id': len(_d['cases'][_gid]) + 1,
                        'action': 'timeout',
                        'user_id': str(after.id),
                        'mod_id': 'system',
                        'reason': 'Через Discord',
                        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()
                    })
                    with open(_f, 'w', encoding='utf-8') as fp:
                        json.dump(_d, fp, indent=2, ensure_ascii=False)
                except Exception as _e:
                    print(f'[LOGS] Ошибка записи мута: {_e}')
            else:
                save_event(before.guild.id, 'mod', 'Мут снят', {
                    'user_id': str(after.id),
                    'user_name': after.display_name,
                    'action': 'untimeout',
                })

        # Смена ника
        if before.nick != after.nick:
            save_event(before.guild.id, 'member', 'Ник изменён', {
                'user_id': str(before.id),
                'user_name': str(before),
                'old_nick': before.nick or before.name,
                'new_nick': after.nick or after.name,
            })
            ch = await self.get_log_channel(before.guild, 'member')
            if ch:
                e = discord.Embed(color=0x3498DB, timestamp=datetime.datetime.utcnow())
                e.description = (
                    f"## Ник изменён\n"
                    f"**{before.display_name}** · `{before.id}`\n\n"
                    f"Было: `{before.nick or before.name}`\n"
                    f"Стало: `{after.nick or after.name}`"
                )
                e.set_footer(text=f"{before.guild.name}")
                await ch.send(embed=e)

    # ─── СООБЩЕНИЯ ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        content = message.content[:500] if message.content else '[Вложение/Embed]'
        _msg_cache[message.id] = {
            'content': message.content or '',
            'author_id': message.author.id,
            'author_name': message.author.display_name,
            'channel_id': message.channel.id,
            'channel_name': message.channel.name,
            'guild_id': message.guild.id,
            'timestamp': message.created_at.isoformat(),
        }
        if len(_msg_cache) > 5000:
            oldest = list(_msg_cache.keys())[:2500]
            for k in oldest:
                del _msg_cache[k]

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild:
            return
        cached = _msg_cache.pop(message.id, None)
        content = message.content or (cached['content'] if cached else '') or '[Содержимое не найдено]'
        save_event(message.guild.id, 'message', 'Сообщение удалено', {
            'user_id': str(message.author.id),
            'user_name': str(message.author),
            'channel': message.channel.name,
            'channel_id': str(message.channel.id),
            'content': content[:500],
        })
        ch = await self.get_log_channel(message.guild, 'message')
        if not ch:
            return
        e = discord.Embed(color=0xE74C3C, timestamp=datetime.datetime.utcnow())
        e.description = (
            f"## Сообщение удалено\n"
            f"**{message.author.display_name}** · `{message.author.id}`\n"
            f"Канал: {message.channel.mention}\n\n"
            f"> {content[:500] or '[Вложение]'}"
        )
        e.set_footer(text=f"{message.guild.name}")
        await ch.send(embed=e)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or before.content == after.content or not before.guild:
            return
        save_event(before.guild.id, 'message', 'Сообщение изменено', {
            'user_id': str(before.author.id),
            'user_name': str(before.author),
            'channel': before.channel.name,
            'channel_id': str(before.channel.id),
            'before': before.content[:300],
            'after': after.content[:300],
        })
        ch = await self.get_log_channel(before.guild, 'message')
        if not ch:
            return
        e = discord.Embed(color=0x3498DB, timestamp=datetime.datetime.utcnow())
        e.description = (
            f"## Сообщение изменено\n"
            f"**{before.author.display_name}** · `{before.author.id}`\n"
            f"Канал: {before.channel.mention} · [Перейти]({after.jump_url})\n\n"
            f"Было:\n> {before.content[:400] or '[Пусто]'}\n\n"
            f"Стало:\n> {after.content[:400] or '[Пусто]'}"
        )
        e.set_footer(text=f"{before.guild.name}")
        await ch.send(embed=e)

    # ─── ГОЛОСОВЫЕ КАНАЛЫ ────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel == after.channel:
            return
        if after.channel:
            action = 'Вошёл в голосовой'
            detail = {'channel': after.channel.name}
            color = 0x1ABC9C
            icon = "🔊"
            desc = f"**{member.display_name}** подключился к голосовому каналу."
        else:
            action = 'Вышел из голосового'
            detail = {'channel': before.channel.name}
            color = 0x95A5A6
            icon = "🔇"
            desc = f"**{member.display_name}** отключился от голосового канала."

        save_event(member.guild.id, 'voice', action, {
            'user_id': str(member.id),
            'user_name': str(member),
            **detail
        })
        ch = await self.get_log_channel(member.guild, 'voice')
        if not ch:
            return
        title_text = "Подключился к голосовому" if after.channel else "Отключился от голосового"
        e = discord.Embed(color=color, timestamp=datetime.datetime.utcnow())
        e.description = (
            f"## {title_text}\n"
            f"**{member.display_name}** · `{member.id}`\n\n"
            f"Канал: **{detail['channel']}**"
        )
        e.set_footer(text=f"{member.guild.name}")
        await ch.send(embed=e)

    # ─── КАНАЛЫ ───────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        save_event(channel.guild.id, 'channel', 'Канал создан', {
            'channel_id': str(channel.id),
            'channel_name': channel.name,
            'channel_type': str(channel.type),
        })
        ch = await self.get_log_channel(channel.guild, 'channel')
        if not ch:
            return
        e = discord.Embed(color=0x2ECC71, timestamp=datetime.datetime.utcnow())
        e.description = (
            f"## Канал создан\n"
            f"**{channel.name}** · `{channel.id}`\n\n"
            f"Тип: {str(channel.type)}"
        )
        e.set_footer(text=f"{channel.guild.name}")
        await ch.send(embed=e)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        save_event(channel.guild.id, 'channel', 'Канал удалён', {
            'channel_id': str(channel.id),
            'channel_name': channel.name,
            'channel_type': str(channel.type),
        })
        ch = await self.get_log_channel(channel.guild, 'channel')
        if not ch:
            return
        e = discord.Embed(color=0xE74C3C, timestamp=datetime.datetime.utcnow())
        e.description = (
            f"## Канал удалён\n"
            f"**{channel.name}** · `{channel.id}`\n\n"
            f"Тип: {str(channel.type)}"
        )
        e.set_footer(text=f"{channel.guild.name}")
        await ch.send(embed=e)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if before.name != after.name:
            save_event(before.guild.id, 'channel', 'Канал переименован', {
                'channel_id': str(before.id),
                'old_name': before.name,
                'new_name': after.name,
            })

    # ─── РОЛИ ─────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        save_event(role.guild.id, 'role', 'Роль создана', {
            'role_id': str(role.id),
            'role_name': role.name,
        })

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        save_event(role.guild.id, 'role', 'Роль удалена', {
            'role_id': str(role.id),
            'role_name': role.name,
        })

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        if before.name != after.name:
            save_event(before.guild.id, 'role', 'Роль переименована', {
                'role_id': str(before.id),
                'old_name': before.name,
                'new_name': after.name,
            })

    # ─── ПРИГЛАШЕНИЯ ──────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        save_event(invite.guild.id, 'invite', 'Приглашение создано', {
            'user_id': str(invite.inviter.id) if invite.inviter else '?',
            'user_name': str(invite.inviter) if invite.inviter else '?',
            'code': invite.code,
            'channel': invite.channel.name if invite.channel else '?',
            'max_uses': invite.max_uses or '∞',
        })

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        save_event(invite.guild.id, 'invite', 'Приглашение удалено', {
            'code': invite.code,
            'channel': invite.channel.name if invite.channel else '?',
        })

    # ─── СЕРВЕР ───────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        if before.name != after.name:
            save_event(before.id, 'server', 'Сервер переименован', {
                'old_name': before.name,
                'new_name': after.name,
            })

    # ─── DISCORD AUDIT LOG SYNC ───────────────────────────────────────

    async def _sync_discord_audit_log(self):
        seen_file = 'data/audit_seen.json'
        seen = {}
        if os.path.exists(seen_file):
            try:
                with open(seen_file, 'r', encoding='utf-8') as f:
                    seen = json.load(f)
            except:
                pass

        action_map = {
            discord.AuditLogAction.ban:                ('mod',     'Бан'),
            discord.AuditLogAction.unban:              ('mod',     'Бан снят'),
            discord.AuditLogAction.kick:               ('mod',     'Кик'),
            discord.AuditLogAction.member_update:      ('mod',     'Участник обновлён'),
            discord.AuditLogAction.channel_create:     ('channel', 'Канал создан'),
            discord.AuditLogAction.channel_delete:     ('channel', 'Канал удалён'),
            discord.AuditLogAction.channel_update:     ('channel', 'Канал обновлён'),
            discord.AuditLogAction.role_create:        ('role',    'Роль создана'),
            discord.AuditLogAction.role_delete:        ('role',    'Роль удалена'),
            discord.AuditLogAction.role_update:        ('role',    'Роль обновлена'),
            discord.AuditLogAction.member_role_update: ('role',    'Роли изменены'),
            discord.AuditLogAction.invite_create:      ('invite',  'Приглашение создано'),
            discord.AuditLogAction.invite_delete:      ('invite',  'Приглашение удалено'),
            discord.AuditLogAction.message_delete:     ('message', 'Сообщение удалено'),
            discord.AuditLogAction.message_bulk_delete:('message', 'Массовое удаление'),
            discord.AuditLogAction.guild_update:       ('server',  'Сервер обновлён'),
            discord.AuditLogAction.webhook_create:     ('server',  'Вебхук создан'),
            discord.AuditLogAction.webhook_delete:     ('server',  'Вебхук удалён'),
        }

        cache_file = 'data/discord_audit_cache.json'
        cache = {}
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
            except:
                pass

        for guild in self.bot.guilds:
            gid = str(guild.id)
            last_id = seen.get(gid)
            new_entries = []
            try:
                if not last_id:
                    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=7)
                    async for entry in guild.audit_logs(limit=None, oldest_first=False):
                        if entry.created_at.replace(tzinfo=None) < cutoff:
                            break
                        new_entries.append(entry)
                else:
                    async for entry in guild.audit_logs(limit=100, oldest_first=False):
                        if entry.id <= int(last_id):
                            break
                        new_entries.append(entry)
            except discord.Forbidden:
                continue
            except Exception as e:
                print(f'[LOGS] Ошибка audit log ({guild.name}): {e}')
                continue

            if not new_entries:
                continue

            seen[gid] = str(new_entries[0].id)
            if gid not in cache:
                cache[gid] = []

            for entry in reversed(new_entries):
                cat, action_name = action_map.get(entry.action, ('server', str(entry.action).split('.')[-1]))
                target = entry.target
                user = entry.user

                # Определение мута
                if entry.action == discord.AuditLogAction.member_update:
                    after_attr = entry.changes.after
                    if hasattr(after_attr, 'timed_out_until'):
                        action_name = 'Мут' if getattr(after_attr, 'timed_out_until', None) else 'Мут снят'
                    else:
                        continue

                tname = (getattr(target, 'display_name', None) or
                         getattr(target, 'name', None) or
                         str(getattr(target, 'id', '?')))
                mname = (getattr(user, 'display_name', None) or
                         str(getattr(user, 'id', '?'))) if user else '?'

                ev = {
                    'category':    cat,
                    'action':      action_name,
                    'target_name': tname,
                    'target_id':   str(getattr(target, 'id', '?')),
                    'mod_name':    mname,
                    'mod_id':      str(getattr(user, 'id', '?')) if user else '?',
                    'reason':      entry.reason or '',
                    'timestamp':   entry.created_at.isoformat(),
                    'audit_id':    str(entry.id),
                    'source':      'discord_audit',
                }

                save_event(guild.id, cat, action_name, {
                    'target_name': tname,
                    'target_id':   str(getattr(target, 'id', '?')),
                    'mod_name':    mname,
                    'mod_id':      str(getattr(user, 'id', '?')) if user else '?',
                    'reason':      entry.reason or '',
                    'audit_id':    str(entry.id),
                    'source':      'discord_audit',
                })

                cache[gid].append(ev)

            if len(cache[gid]) > 1000:
                cache[gid] = cache[gid][-1000:]

        try:
            os.makedirs('data', exist_ok=True)
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f'[LOGS] Ошибка записи кэша: {e}')

        try:
            with open(seen_file, 'w', encoding='utf-8') as f:
                json.dump(seen, f)
        except:
            pass

    @commands.Cog.listener()
    async def on_ready(self):
        import asyncio
        await asyncio.sleep(5)
        asyncio.get_event_loop().create_task(self._audit_sync_loop())

    async def _audit_sync_loop(self):
        import asyncio
        fail_count = 0
        while True:
            try:
                await self._sync_discord_audit_log()
                fail_count = 0
                await asyncio.sleep(30)
            except Exception as e:
                fail_count += 1
                wait = min(60 * fail_count, 300)
                print(f'[LOGS] Ошибка sync ({fail_count}): {e} — ждём {wait}с')
                await asyncio.sleep(wait)


async def setup(bot):
    await bot.add_cog(Logs(bot))
