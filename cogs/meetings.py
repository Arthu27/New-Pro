# -*- coding: utf-8 -*-
"""Собрания стаффа — разделение по типам, ЛС-уведомления, учёт явки.

Идея (2026-09-09):
- Собрания делятся: общее, модерское, хелперское
- Бот авто-отправляет красивую таблицу в настроенный канал (без команды)
- Всем с нужной ролью — ЛС (стафф, нужно)
- Панель: кто придёт, кто не придёт, причина (уважительная)
- Роль хелперов: 948969471916249119

Хранилище: GuildData('meetings'), state = {'next_id':1, 'items':[]}
"""

import io
from datetime import datetime, timezone, timedelta
from typing import Optional

import discord
from discord.ext import commands

from db import GuildData
from logger import get_logger

log = get_logger("meetings")

UTC = timezone.utc

MEETING_TYPES = {
    'general': {'label': 'Общее собрание', 'emoji': '📋', 'color': 0x5865F2},
    'helper': {'label': 'Собрание хелперов', 'emoji': '🙋', 'color': 0x57F287},
    'mod': {'label': 'Собрание модеров', 'emoji': '🛡️', 'color': 0xED4245},
}

HELPER_ROLE_ID = 948969471916249119
# мод-роль берём из services/mod_role или STAFF_MODERATOR_ROLE_ID
ATTENDANCE_STATUSES = ('yes', 'no', 'maybe')
ATT_LABELS = {'yes': 'Буду', 'no': 'Не буду', 'maybe': 'Под вопросом'}
ATT_EMOJI = {'yes': '✅', 'no': '❌', 'maybe': '❓'}


# ─── чистые функции ─────────────────────────────────────────────────

def empty_state():
    return {'next_id': 1, 'items': []}


def _parse_dt(value):
    if not value:
        return None
    try:
        s = str(value).strip()
        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            # наивное время считаем МСК (UTC+3) — как вводит пользователь в панели
            dt = dt.replace(tzinfo=timezone(timedelta(hours=3))).astimezone(UTC)
        return dt
    except Exception:
        return None


def get_meeting(state, meeting_id):
    mid = int(meeting_id or 0)
    for it in (state or {}).get('items', []):
        if int(it.get('id') or 0) == mid:
            return it
    return None


def create_meeting(state, mtype, title, description, scheduled_at, created_by, created_by_id, channel_id=None, ping_role_id=None):
    mtype = str(mtype or 'general').lower()
    if mtype not in MEETING_TYPES:
        mtype = 'general'
    title = str(title or '').strip()[:100] or 'Собрание'
    description = str(description or '').strip()[:1000]
    if not scheduled_at:
        return None, 'Время не указано'
    # scheduled_at может быть datetime или iso-строка
    if isinstance(scheduled_at, datetime):
        sched_dt = scheduled_at
        if sched_dt.tzinfo is None:
            # наивное из панели — считаем МСК
            sched_dt = sched_dt.replace(tzinfo=timezone(timedelta(hours=3))).astimezone(UTC)
    else:
        sched_dt = _parse_dt(scheduled_at)
        if sched_dt is None:
            return None, 'Неверный формат времени'
    # нельзя в прошлом (допуск 1 минута)
    now = datetime.now(UTC)
    if sched_dt < now - timedelta(minutes=1):
        return None, 'Время уже прошло — выберите будущее'

    item = {
        'id': int(state.get('next_id') or 1),
        'type': mtype,
        'title': title,
        'description': description,
        'scheduled_at': sched_dt.isoformat(),
        'created_at': now.isoformat(),
        'created_by': str(created_by),
        'created_by_id': int(created_by_id or 0),
        'status': 'scheduled',
        'channel_id': int(channel_id or 0) if channel_id else 0,
        'message_id': 0,
        'thread_id': 0,
        'ping_role_id': int(ping_role_id or 0) if ping_role_id else 0,
        'attendance': {},  # user_id(str) -> yes/no/maybe
        'excuses': {},     # user_id(str) -> {reason, at, name}
        'dm_sent': 0,
        'dm_failed': 0,
    }
    state['next_id'] = item['id'] + 1
    state['items'].append(item)
    return item, None


def set_attendance(state, meeting_id, user_id, status):
    if status not in ATTENDANCE_STATUSES:
        return None, 'Неверный статус'
    item = get_meeting(state, meeting_id)
    if not item:
        return None, 'Собрание не найдено'
    if item.get('status') != 'scheduled':
        return None, 'Собрание уже завершено или отменено'
    uid = str(int(user_id))
    item['attendance'][uid] = status
    # если отметил "буду" или "под вопросом" — убираем уважительную причину если была
    if status in ('yes', 'maybe') and uid in item.get('excuses', {}):
        item['excuses'].pop(uid, None)
    return item, None


def add_excuse(state, meeting_id, user_id, user_name, reason):
    item = get_meeting(state, meeting_id)
    if not item:
        return None, 'Собрание не найдено'
    if item.get('status') != 'scheduled':
        return None, 'Собрание уже завершено'
    uid = str(int(user_id))
    reason = str(reason or '').strip()[:500]
    if len(reason) < 5:
        return None, 'Причина слишком короткая — напишите подробнее (минимум 5 символов)'
    item['attendance'][uid] = 'no'
    item['excuses'][uid] = {
        'reason': reason,
        'at': datetime.now(UTC).isoformat(),
        'name': str(user_name)[:100],
    }
    return item, None


def meeting_stats(item):
    att = item.get('attendance') or {}
    yes = sum(1 for v in att.values() if v == 'yes')
    no = sum(1 for v in att.values() if v == 'no')
    maybe = sum(1 for v in att.values() if v == 'maybe')
    total = len(att)
    excuses = item.get('excuses') or {}
    return {'yes': yes, 'no': no, 'maybe': maybe, 'total': total, 'excuses': len(excuses)}


def fmt_meeting_embed(item, guild_name=''):
    mtype = item.get('type') or 'general'
    meta = MEETING_TYPES.get(mtype, MEETING_TYPES['general'])
    color = meta['color']
    emoji = meta['emoji']
    label = meta['label']

    sched = _parse_dt(item.get('scheduled_at'))
    if sched:
        # показываем в МСК для пользователя
        msk = sched.astimezone(timezone(timedelta(hours=3)))
        sched_str = msk.strftime('%d.%m.%Y %H:%M МСК')
    else:
        sched_str = str(item.get('scheduled_at') or '')

    embed = discord.Embed(
        title=f"{emoji} {label} #{item.get('id')} — {item.get('title')}",
        description=(item.get('description') or 'Без описания')[:1000],
        color=color,
        timestamp=sched,
    )
    embed.add_field(name='🕐 Когда', value=f"**{sched_str}**\n<t:{int(sched.timestamp())}:R>" if sched else '—', inline=True)
    embed.add_field(name='📍 Тип', value=label, inline=True)
    embed.add_field(name='👤 Создал', value=str(item.get('created_by') or '—'), inline=True)

    stats = meeting_stats(item)
    embed.add_field(name='📊 Явка', value=f"✅ Буду: **{stats['yes']}**\n❌ Не буду: **{stats['no']}**\n❓ Под вопросом: **{stats['maybe']}**\nВсего откликов: {stats['total']}", inline=False)

    # список уважительных причин (кратко)
    excuses = item.get('excuses') or {}
    if excuses:
        lines = []
        for uid, ex in list(excuses.items())[:5]:
            lines.append(f"• **{ex.get('name','?')}** — {ex.get('reason','')[:80]}")
        if len(excuses) > 5:
            lines.append(f"... и ещё {len(excuses)-5}")
        embed.add_field(name='📝 Уважительные причины', value='\n'.join(lines)[:1024], inline=False)

    if guild_name:
        embed.set_footer(text=f"{guild_name} · Собрания стаффа")
    else:
        embed.set_footer(text="Собрания стаффа")
    return embed


def attendance_table_text(item):
    att = item.get('attendance') or {}
    excuses = item.get('excuses') or {}
    if not att:
        return "Пока никто не отметился — нажмите кнопки ниже."

    lines = []
    # сортируем: yes, maybe, no
    order = {'yes': 0, 'maybe': 1, 'no': 2}
    sorted_att = sorted(att.items(), key=lambda kv: (order.get(kv[1], 9), kv[0]))
    for uid, status in sorted_att:
        name = f"<@{uid}>"
        # если есть excuse — показываем причину
        ex = excuses.get(uid)
        if ex and status == 'no':
            lines.append(f"{ATT_EMOJI.get(status,'•')} {name} — {ATT_LABELS.get(status,status)} | Причина: {ex.get('reason','')[:100]}")
        else:
            lines.append(f"{ATT_EMOJI.get(status,'•')} {name} — {ATT_LABELS.get(status,status)}")
    return '\n'.join(lines)[:1800]


# ─── Views ──────────────────────────────────────────────────────────

class MeetingExcuseModal(discord.ui.Modal):
    def __init__(self, cog, guild_id, meeting_id):
        super().__init__(title='Уважительная причина')
        self.cog = cog
        self.guild_id = guild_id
        self.meeting_id = meeting_id
        self.reason = discord.ui.TextInput(
            label='Почему не сможете быть?',
            placeholder='Напишите уважительную причину (минимум 5 символов)',
            required=True, max_length=500, style=discord.TextStyle.paragraph
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        state = self.cog._load(self.guild_id)
        item, err = add_excuse(state, self.meeting_id, interaction.user.id, str(interaction.user), self.reason.value)
        if err:
            await interaction.response.send_message(f'Не получилось: {err}', ephemeral=True)
            return
        self.cog._save(self.guild_id, state)
        # обновляем карточку
        try:
            guild = self.cog.bot.get_guild(self.guild_id)
            embed = fmt_meeting_embed(item, str(getattr(guild, 'name', '') or ''))
            table = attendance_table_text(item)
            # если есть сообщение — обновляем
            if guild and item.get('channel_id') and item.get('message_id'):
                ch = self.cog._guild_ch(guild, int(item['channel_id']))
                if ch:
                    try:
                        msg = await ch.fetch_message(int(item['message_id']))
                        # второй embed с таблицей явки
                        table_embed = discord.Embed(
                            title='📋 Таблица явки',
                            description=table,
                            color=0x95A5A6,
                        )
                        await msg.edit(embeds=[embed, table_embed])
                    except Exception:
                        pass
        except Exception as _ex:
            log.debug('meetings: update card after excuse: %s', _ex)

        await interaction.response.send_message(
            f"Причина сохранена для собрания **#{self.meeting_id}** — куратор увидит в панели.\n> {self.reason.value[:200]}",
            ephemeral=True
        )


class MeetingView(discord.ui.View):
    def __init__(self, cog, guild_id, meeting_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.meeting_id = meeting_id
        for status, label, style, emoji in (
            ('yes', 'Буду', discord.ButtonStyle.success, '✅'),
            ('no', 'Не буду (уваж.)', discord.ButtonStyle.danger, '❌'),
            ('maybe', 'Под вопросом', discord.ButtonStyle.secondary, '❓'),
        ):
            btn = discord.ui.Button(
                label=label, style=style, emoji=emoji,
                custom_id=f"meeting:{status}:{meeting_id}"
            )
            btn.callback = self._make_cb(status)
            self.add_item(btn)

    def _make_cb(self, status):
        async def _cb(interaction: discord.Interaction):
            gid = self.guild_id
            mid = self.meeting_id
            state = self.cog._load(gid)
            item = get_meeting(state, mid)
            if not item:
                await interaction.response.send_message('Собрание не найдено или уже завершено.', ephemeral=True)
                return
            if item.get('status') != 'scheduled':
                await interaction.response.send_message(f"Собрание уже {item.get('status')} — явку не изменить.", ephemeral=True)
                return

            if status == 'no':
                await interaction.response.send_modal(MeetingExcuseModal(self.cog, gid, mid))
                return

            # yes / maybe
            item, err = set_attendance(state, mid, interaction.user.id, status)
            if err:
                await interaction.response.send_message(err, ephemeral=True)
                return
            self.cog._save(gid, state)

            # обновляем карточку в канале
            try:
                guild = self.cog.bot.get_guild(gid)
                embed = fmt_meeting_embed(item, str(getattr(guild, 'name', '') or ''))
                table = attendance_table_text(item)
                table_embed = discord.Embed(title='📋 Таблица явки', description=table, color=0x95A5A6)
                if interaction.message and interaction.message.embeds:
                    try:
                        await interaction.message.edit(embeds=[embed, table_embed], view=self)
                    except Exception:
                        pass
            except Exception as _ex:
                log.debug('meetings: edit card: %s', _ex)

            await interaction.response.send_message(
                f"{ATT_EMOJI.get(status,'')} Отмечено: **{ATT_LABELS.get(status,status)}** для собрания **#{mid}**",
                ephemeral=True
            )
        return _cb


# ─── Cog ────────────────────────────────────────────────────────────

class Meetings(commands.Cog):
    """Собрания стаффа — авто-отправка таблицы, ЛС, панель явки."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('meetings')
        self._views_restored = False

    @commands.Cog.listener()
    async def on_ready(self):
        if self._views_restored:
            return
        self._views_restored = True
        restored = 0
        pending_sent = 0
        for guild in list(self.bot.guilds):
            state = self._load(guild.id)
            for item in (state or {}).get('items', []):
                if item.get('status') == 'scheduled' and item.get('message_id'):
                    try:
                        self.bot.add_view(MeetingView(self, guild.id, item['id']), message_id=int(item['message_id']))
                        restored += 1
                    except Exception as _ex:
                        log.debug('meetings: restore view #%s: %s', item.get('id'), _ex)
                # авто-отправка карточек, созданных офлайн (без message_id)
                elif item.get('status') == 'scheduled' and not item.get('message_id'):
                    # не шлём прошедшие собрания (старше 1 дня)
                    try:
                        sched = _parse_dt(item.get('scheduled_at'))
                        if sched and sched < datetime.now(UTC) - timedelta(days=1):
                            continue
                    except Exception:
                        pass
                    try:
                        # берём свежий item из БД
                        fresh_state = self._load(guild.id)
                        fresh_item = get_meeting(fresh_state, item.get('id'))
                        if not fresh_item:
                            continue
                        msg, err = await self._send_meeting_card(guild, fresh_item)
                        if msg and not err:
                            pending_sent += 1
                            # ЛС
                            try:
                                await self._notify_dm(guild, fresh_item)
                            except Exception as _ex:
                                log.debug('meetings: pending DM #%s: %s', fresh_item.get('id'), _ex)
                    except Exception as _ex:
                        log.debug('meetings: pending send #%s: %s', item.get('id'), _ex)

        if restored:
            log.info('meetings: восстановлено %s view', restored)
        if pending_sent:
            log.info('meetings: отправлено %s отложенных карточек', pending_sent)

    def _load(self, guild_id):
        return self.db.get(guild_id, 'state', empty_state()) or empty_state()

    def _save(self, guild_id, state):
        self.db.set(guild_id, 'state', state)
        # live-push для панели /meetings — без мигания, мгновенно
        try:
            from services.live_bus import publish as _live_pub
            _live_pub(guild_id, 'meetings')
        except Exception:
            pass

    def _guild_ch(self, guild, cid):
        if not cid or guild is None:
            return None
        try:
            cid = int(cid)
        except Exception:
            return None
        ch = guild.get_channel(cid)
        if ch:
            return ch
        fn = getattr(guild, 'get_channel_or_thread', None)
        if callable(fn):
            ch = fn(cid)
            if ch:
                return ch
        return None

    def _get_target_channel(self, guild, mtype, state=None):
        """Куда постим карточку собрания — по типу."""
        # порядок: специфичный канал типа → общий канал собраний → системный → первый текстовый
        try:
            from services.channel_routes import resolve_route, channel_on_guild
            keys = []
            if mtype == 'helper':
                keys = ['meeting_helper_channel', 'meeting_channel']
            elif mtype == 'mod':
                keys = ['meeting_mod_channel', 'meeting_channel']
            else:
                keys = ['meeting_channel', 'meeting_mod_channel', 'meeting_helper_channel']

            for k in keys:
                cid = int(resolve_route(guild.id, k, guild) or 0)
                if cid:
                    ch = channel_on_guild(guild, cid)
                    if ch:
                        return ch
        except Exception as _ex:
            log.debug('meetings: route: %s', _ex)

        # fallback из state (если панель сохраняла channel_id)
        if state:
            cid = int(state.get('log_channel_id') or 0)
            if cid:
                ch = self._guild_ch(guild, cid)
                if ch:
                    return ch

        # known fallback — общий канал собраний
        try:
            from services.channel_routes import KNOWN_CHANNELS, channel_on_guild
            for k in ('meeting_channel', 'meeting_helper_channel', 'meeting_mod_channel'):
                guess = int(KNOWN_CHANNELS.get(k) or 0)
                if guess:
                    ch = channel_on_guild(guild, guess)
                    if ch:
                        return ch
        except Exception:
            pass

        if getattr(guild, 'system_channel', None):
            return guild.system_channel
        for ch in getattr(guild, 'text_channels', []):
            try:
                if ch.permissions_for(guild.me).send_messages:
                    return ch
            except Exception:
                continue
        return None

    def _get_ping_role(self, guild, mtype, custom_role_id=None):
        if custom_role_id:
            try:
                rid = int(custom_role_id)
                if rid:
                    role = guild.get_role(rid)
                    if role:
                        return role
            except Exception:
                pass

        # по типу
        if mtype == 'helper':
            role = guild.get_role(HELPER_ROLE_ID)
            if role:
                return role
            # fallback из env
            try:
                from config import Config
                rid = int(getattr(Config, 'STAFF_HELPER_ROLE_ID', 0) or 0)
                if rid:
                    return guild.get_role(rid)
            except Exception:
                pass
        elif mtype == 'mod':
            try:
                from services.mod_role import resolve_mod_role
                r = resolve_mod_role(guild)
                if r:
                    return r
            except Exception:
                pass
            try:
                from config import Config
                rid = int(getattr(Config, 'STAFF_MODERATOR_ROLE_ID', 0) or 0)
                if rid:
                    return guild.get_role(rid)
            except Exception:
                pass
        else:  # general — обе роли
            # вернём None, пинговать будем обе отдельно
            return None
        return None

    def _get_all_ping_roles(self, guild, mtype, custom_role_id=None):
        roles = []
        custom = self._get_ping_role(guild, mtype, custom_role_id)
        if custom:
            roles.append(custom)
            return roles

        if mtype == 'general':
            # обе роли
            try:
                rh = guild.get_role(HELPER_ROLE_ID)
                if rh:
                    roles.append(rh)
            except Exception:
                pass
            try:
                from services.mod_role import resolve_mod_role
                rm = resolve_mod_role(guild)
                if rm:
                    roles.append(rm)
            except Exception:
                pass
            # дедуп
            seen = set()
            uniq = []
            for r in roles:
                if r.id not in seen:
                    seen.add(r.id)
                    uniq.append(r)
            return uniq
        elif mtype == 'helper' or mtype == 'mod':
            if custom:
                return [custom]
            # пробуем найти по типу
            r = self._get_ping_role(guild, mtype)
            return [r] if r else []
        return roles

    async def _send_meeting_card(self, guild, item):
        """Авто-отправка таблицы в канал (без команды) — красивая карточка."""
        target = self._get_target_channel(guild, item.get('type'), None)
        if not target:
            log.warning('meetings: нет канала для собрания #%s типа %s', item.get('id'), item.get('type'))
            return None, 'Канал собраний не настроен — укажите в Панель → Каналы и маршруты'

        embed = fmt_meeting_embed(item, str(guild.name))
        table = attendance_table_text(item)
        table_embed = discord.Embed(title='📋 Таблица явки (авто-обновляется)', description=table, color=0x95A5A6)
        table_embed.set_footer(text='Нажмите кнопки ниже чтобы отметиться')

        view = MeetingView(self, guild.id, item['id'])

        # пинг ролей
        ping_roles = self._get_all_ping_roles(guild, item.get('type'), item.get('ping_role_id'))
        ping_text = ''
        if ping_roles:
            ping_text = ' '.join(r.mention for r in ping_roles) + f" — новое {MEETING_TYPES.get(item.get('type'), {}).get('label','собрание')}!"

        try:
            msg = await target.send(content=ping_text or None, embeds=[embed, table_embed], view=view,
                                    allowed_mentions=discord.AllowedMentions(roles=True, users=True))
            # сохраняем id в актуальном состоянии БД (а не в старом объекте)
            try:
                fresh = self._load(guild.id)
                fresh_item = get_meeting(fresh, item.get('id'))
                if fresh_item is not None:
                    fresh_item['channel_id'] = target.id
                    fresh_item['message_id'] = msg.id
                    # thread_id пока 0, обновим ниже
                    self._save(guild.id, fresh)
                    # обновим ссылку для дальнейшего использования
                    item = fresh_item
            except Exception as _ex:
                log.debug('meetings: save after send: %s', _ex)
                # fallback — старый объект
                item['channel_id'] = target.id
                item['message_id'] = msg.id
                try:
                    self._save(guild.id, self._load(guild.id))
                except Exception:
                    pass

            # тред для обсуждения
            try:
                thread = await msg.create_thread(name=f"Обсуждение — {item.get('title')[:50]}", auto_archive_duration=1440)
                # сохраняем thread_id
                try:
                    fresh2 = self._load(guild.id)
                    fi2 = get_meeting(fresh2, item.get('id'))
                    if fi2 is not None:
                        fi2['thread_id'] = thread.id
                        self._save(guild.id, fresh2)
                except Exception:
                    item['thread_id'] = thread.id
                await thread.send(f"Обсуждение собрания **#{item['id']}** — {item.get('title')}\nВремя: <t:{int(_parse_dt(item.get('scheduled_at')).timestamp())}:F>")
            except Exception as _ex:
                log.debug('meetings: thread: %s', _ex)

            return msg, None
        except Exception as _ex:
            log.error('meetings: send card #%s: %s', item.get('id'), _ex)
            return None, str(_ex)

    async def _notify_dm(self, guild, item):
        """ЛС всем с нужной ролью — собрание стаффа, нужно."""
        # собираем участников по ролям
        roles = self._get_all_ping_roles(guild, item.get('type'), item.get('ping_role_id'))
        if not roles:
            # если ролей нет — берём всех с helper_role как fallback
            try:
                rh = guild.get_role(HELPER_ROLE_ID)
                if rh:
                    roles = [rh]
            except Exception:
                pass

        # собираем уникальных участников по id (Member не всегда hashable в set)
        members_by_id = {}
        for role in roles:
            try:
                for m in role.members:
                    if not getattr(m, 'bot', False):
                        members_by_id[int(m.id)] = m
            except Exception:
                pass

        # если ролей нет или члены не в кэше — берём всех членов гильдии с этой ролью
        if not members_by_id:
            try:
                for m in guild.members:
                    if not getattr(m, 'bot', False) and any(r.id == HELPER_ROLE_ID for r in getattr(m, 'roles', [])):
                        members_by_id[int(m.id)] = m
            except Exception:
                pass

        members = list(members_by_id.values())

        # если всё ещё пусто — не спамим всех, просто лог
        if not members:
            log.info('meetings: DM — нет участников для #%s', item.get('id'))
            return 0, 0

        embed = fmt_meeting_embed(item, str(guild.name))
        embed.description = (embed.description or '') + f"\n\n**Вам нужно отметиться:** нажмите кнопки под карточкой в канале <#{item.get('channel_id')}>"

        sent = 0
        failed = 0
        # анти-спам: семафор 3 одновременных ЛС
        import asyncio as _aio
        sem = _aio.Semaphore(3)

        async def _send_one(member):
            nonlocal sent, failed
            async with sem:
                try:
                    await member.send(embed=embed)
                    sent += 1
                except Exception as _ex:
                    failed += 1
                    log.debug('meetings: DM %s: %s', member.id, _ex)
                await _aio.sleep(0.6)  # защита от лимитов

        await _aio.gather(*[_send_one(m) for m in members[:80]], return_exceptions=True)  # лимит 80 за раз

        # сохраняем статистику
        try:
            state = self._load(guild.id)
            it = get_meeting(state, item['id'])
            if it:
                it['dm_sent'] = sent
                it['dm_failed'] = failed
                self._save(guild.id, state)
        except Exception:
            pass

        log.info('meetings: DM #%s — отправлено %s, ошибок %s', item.get('id'), sent, failed)
        return sent, failed

    async def create_and_publish(self, guild, mtype, title, description, scheduled_at, created_by, created_by_id, ping_role_id=None):
        """Создать собрание из панели — авто-отправка таблицы + ЛС."""
        state = self._load(guild.id)
        item, err = create_meeting(state, mtype, title, description, scheduled_at, created_by, created_by_id, ping_role_id=ping_role_id)
        if err:
            return None, err
        self._save(guild.id, state)

        # авто-отправка в канал
        msg, err2 = await self._send_meeting_card(guild, item)
        if err2:
            # не критично — собрание создано, но карточка не ушла
            log.warning('meetings: карточка #%s не ушла: %s', item['id'], err2)
        else:
            # сохраняем id сообщения
            state = self._load(guild.id)
            it = get_meeting(state, item['id'])
            if it and msg:
                it['channel_id'] = msg.channel.id if hasattr(msg, 'channel') else it['channel_id']
                it['message_id'] = msg.id
                self._save(guild.id, state)
                item = it

        # ЛС — в фоне, чтобы не блокировать панель
        try:
            import asyncio as _aio2
            # пробуем через loop бота (совместимость) или напрямую
            loop = getattr(self.bot, 'loop', None)
            if loop and hasattr(loop, 'create_task'):
                loop.create_task(self._notify_dm(guild, item))
            else:
                _aio2.create_task(self._notify_dm(guild, item))
        except Exception as _ex:
            log.debug('meetings: DM task: %s', _ex)
            # fallback — await
            try:
                await self._notify_dm(guild, item)
            except Exception as _ex2:
                log.debug('meetings: DM fallback: %s', _ex2)

        return item, None

    async def update_card(self, guild, meeting_id):
        state = self._load(guild.id)
        item = get_meeting(state, meeting_id)
        if not item or not item.get('message_id') or not item.get('channel_id'):
            return
        try:
            ch = self._guild_ch(guild, int(item['channel_id']))
            if not ch:
                return
            msg = await ch.fetch_message(int(item['message_id']))
            embed = fmt_meeting_embed(item, str(guild.name))
            table = attendance_table_text(item)
            table_embed = discord.Embed(title='📋 Таблица явки (авто-обновляется)', description=table, color=0x95A5A6)
            view = MeetingView(self, guild.id, item['id'])
            await msg.edit(embeds=[embed, table_embed], view=view)
        except Exception as _ex:
            log.debug('meetings: update_card #%s: %s', meeting_id, _ex)


async def setup(bot):
    await bot.add_cog(Meetings(bot))
