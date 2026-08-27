# -*- coding: utf-8 -*-
"""Апелляции на баны (Appeals Cog)
=================================
Забаненный не может написать на сервере — но может написать боту в личку:

    /апелляция <ID сервера> <текст>     (в ЛС боту)

Модераторы получают карточку с кнопками «Принять» / «Отклонить».
Принят — пользователь разбанен и получает добрую весть в ЛС.
Отклонён — получает отказ (с опциональным комментарием модератора).

- /апелляция <guild_id> <текст>  — подать (в ЛС боту, для забаненных)
- /апелляции настройка #канал    — куда падать карточкам
- /апелляции список              — ожидающие решения

Хранилище — SQLite (GuildData 'appeals'). Кнопки живут в persistent view
и переживают рестарт бота. Метки — aware UTC.
"""
import io
import re
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from db import GuildData
from logger import get_logger
from services.appeal_card import (normalize_appearance, render_appeal_card,
                                  appeal_card_filename)

log = get_logger("appeals")

UTC = timezone.utc
COLOR_PENDING = 0xFEE75C
COLOR_YES = 0x57F287
COLOR_NO = 0xED4245

MAX_TEXT = 500
MAX_PER_USER = 3  # открытых апелляций одновременно


# ─── чистые функции (покрыты тестом) ────────────────────────────────────────

def empty_state():
    return {'next_id': 1, 'items': [], 'log_channel_id': 0}


def pending_items(state):
    return [i for i in state['items'] if i['status'] == 'pending']


def user_pending(state, user_id):
    return [i for i in pending_items(state) if i['user_id'] == user_id]


def create_appeal(state, user_id, user_name, text, now, link=None):
    """Создать апелляцию. Возвращает (item, ошибка)."""
    text = str(text or '').strip()
    link = _clean_link(link)
    if len(text) < 10:
        return None, f'слишком коротко — напишите подробнее (минимум 10 символов)'
    if len(text) > MAX_TEXT:
        return None, f'максимум {MAX_TEXT} символов'
    if len(user_pending(state, user_id)) >= MAX_PER_USER:
        return None, f'уже есть {MAX_PER_USER} открытых — дождитесь решения'
    item = {
        'id': state['next_id'],
        'user_id': int(user_id),
        'user_name': str(user_name),
        'text': text,
        'link': link,
        'status': 'pending',           # pending | accepted | rejected
        'created_at': now.isoformat(),
        'reviewed_by': None,
        'reviewed_at': None,
        'reply': None,
    }
    state['next_id'] += 1
    state['items'].append(item)
    return item, None


def _clean_link(link):
    """Ссылка-доказательство: без протокола — https://, опасные схемы — None."""
    v = str(link or '').strip()
    if not v:
        return None
    if re.match(r'^(javascript|data|vbscript):', v, re.I):
        return None
    if not re.match(r'^https?://', v, re.I):
        v = 'https://' + v
    return v[:500]


def resolve_appeal(state, appeal_id, accept, reviewer_name, now, reply=None):
    """Решение модератора. (item | None, причина_если_None)."""
    for item in state['items']:
        if item['id'] == appeal_id:
            if item['status'] != 'pending':
                return None, f'апелляция #{appeal_id} уже рассмотрена ({item["status"]})'
            item['status'] = 'accepted' if accept else 'rejected'
            item['reviewed_by'] = str(reviewer_name)
            item['reviewed_at'] = now.isoformat()
            item['reply'] = (reply or '').strip()[:300] or None
            return item, None
    return None, f'апелляция #{appeal_id} не найдена'


def get_appeal(state, appeal_id):
    for item in state['items']:
        if item['id'] == appeal_id:
            return item
    return None


def fmt_card_text(item):
    """Текст карточки для мод-канала (экран логики, покрыт тестом)."""
    body = f"**Апелляция #{item['id']}** от {item['user_name']} (`{item['user_id']}`)\n{item['text'][:400]}"
    link = (item.get('link') or '').strip()
    if link:
        body += f"\n🔗 Доказательство: {link}"
    return body


# ─── view с кнопками ────────────────────────────────────────────────────────

class AppealView(discord.ui.View):
    """Persistent-кнопки под конкретную апелляцию.

    custom_id уникален для каждой апелляции ('appeal:accept:7'), поэтому
    view можно перерегистрировать после рестарта бота (on_ready ниже) —
    кнопки не умирают, пока апелляция ждёт решения.
    """

    def __init__(self, cog, guild_id, appeal_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.appeal_id = appeal_id
        for label, style, verb in (
                ('Принять', discord.ButtonStyle.success, 'accept'),
                ('Отклонить', discord.ButtonStyle.danger, 'reject')):
            btn = discord.ui.Button(
                label=label, style=style,
                custom_id=f'appeal:{verb}:{appeal_id}')
            btn.callback = self._make_cb(verb == 'accept')
            self.add_item(btn)

    def _make_cb(self, accept):
        async def _cb(interaction):
            await self._resolve(interaction, accept)
        return _cb

    async def _resolve(self, interaction, accept):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                ' Нужно право «Управление сервером».', ephemeral=True)
            return
        gid = self.guild_id
        state = self.cog._load(gid)
        item, err = resolve_appeal(state, self.appeal_id, accept,
                                   str(interaction.user), datetime.now(UTC))
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        self.cog._save(gid, state)
        unbanned = False
        if accept:
            guild = self.cog.bot.get_guild(gid)
            if guild is not None:
                member = guild.get_member(item['user_id'])
                # мягкое возвращение: снять роль-бан, изоляцию и таймаут
                if member is not None:
                    try:
                        from services import punish_roles as PR
                        rid = PR.role_for(gid, 'ban')
                        role = guild.get_role(rid) if rid else None
                        if role is not None and role in getattr(member, 'roles', []):
                            await member.remove_roles(
                                role, reason=f'Апелляция #{item["id"]} принята')
                            PR.clear(gid, member.id, rid)
                    except Exception as _ex:
                        log.debug('appeals: снять роль бана: %s', _ex)
                    try:
                        mod = self.cog.bot.get_cog('Moderation')
                        if mod is not None:
                            await mod._unisolate_member(guild, member)
                            await member.timeout(None)
                    except Exception as _ex:
                        log.debug('appeals: снятие изоляции/таймаута: %s', _ex)
                try:
                    await guild.unban(discord.Object(id=item['user_id']),
                                      reason=f'Апелляция #{item["id"]} принята')
                    unbanned = True
                except discord.NotFound:
                    unbanned = True  # уже разбанен руками
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    log.error('appeals: unban %s на %s не удался: %s',
                              item['user_id'], gid, _ex)
        await self.cog._notify_user(item, accept, unbanned)

        for child in self.children:
            child.disabled = True
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.color = COLOR_YES if accept else COLOR_NO
            status = ('принята (разбанен)' if (accept and unbanned)
                      else ('принята' if accept else 'отклонена'))
            embed.title = f'Апелляция #{item["id"]} — {status}'
            embed.set_footer(text=f'Решение: {interaction.user}')
        if embed:
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.edit_message(view=self)


class AppealModal(discord.ui.Modal):
    """Окно подачи: текст апелляции + ссылка-доказательство (необязательно)."""

    def __init__(self, cog, guild):
        super().__init__(title=f'Апелляция · {str(guild.name)[:30]}')
        self.cog = cog
        self.guild = guild
        self.text = discord.ui.TextInput(
            label='Текст апелляции',
            placeholder='Расскажите, что произошло (минимум 10 символов)',
            required=True, max_length=500, style=discord.TextStyle.paragraph)
        self.link = discord.ui.TextInput(
            label='Ссылка-доказательство (необязательно)',
            placeholder='https://… — скрин, видео или сообщение',
            required=False, max_length=500)
        self.add_item(self.text)
        self.add_item(self.link)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self.cog._is_banned(self.guild, interaction.user):
            await interaction.followup.send(
                ' Вы не забанены на этом сервере — апелляция не нужна.', ephemeral=True)
            return
        item, err = await self.cog._submit_appeal(
            interaction.user, self.guild, self.text.value,
            link=self.link.value)
        if err:
            await interaction.followup.send(f' Не получилось: {err}.', ephemeral=True)
            return
        from cogs.embed_utils import hakumo_embed as _ae
        await interaction.followup.send(
            embed=_ae('appeal', f'Апелляция #{item["id"]} отправлена',
                      f'Модераторы сервера **{self.guild.name}** уже получили её. '
                      'Ответ придёт сюда, в личку.'), ephemeral=True)


class AppealServerSelect(discord.ui.Select):
    """Выбор сервера для апелляции (в ЛС боту)."""

    def __init__(self, cog, guilds):
        self.cog = cog
        options = [discord.SelectOption(
            label=str(g.name)[:100] or 'Сервер', value=str(g.id),
            description=f'{g.member_count or 0} участников') for g in guilds[:25]]
        super().__init__(placeholder='Выберите сервер…', options=options,
                         min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        guild = self.cog.bot.get_guild(int(self.values[0]))
        if guild is None:
            await interaction.response.send_message(' Сервер не найден — попробуйте ещё раз.', ephemeral=True)
            return
        await interaction.response.send_modal(AppealModal(self.cog, guild))


class AppealViewParent(discord.ui.View):
    """Обёртка select-меню выбора сервера."""

    def __init__(self, cog, guilds):
        super().__init__(timeout=300)
        self.add_item(AppealServerSelect(cog, guilds))


# ─── меню апелляций в канале (не в ЛС) ────────────────────────────────

MENU_CUSTOM_ID = 'appeal:menu:open'


class AppealChannelModal(discord.ui.Modal):
    """Окно подачи апелляции из меню в канале."""

    def __init__(self, cog, guild):
        super().__init__(title=f'Апелляция · {str(guild.name)[:30]}')
        self.cog = cog
        self.guild = guild
        self.text = discord.ui.TextInput(
            label='Что произошло?', style=discord.TextStyle.paragraph,
            placeholder='Расскажите свою версию — спокойно и по делу (от 10 символов)',
            required=True, max_length=500)
        self.link = discord.ui.TextInput(
            label='Ссылка-доказательство (необязательно)',
            placeholder='https://… — скрин, видео или сообщение',
            required=False, max_length=500)
        self.add_item(self.text)
        self.add_item(self.link)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        item, err = await self.cog._submit_channel_appeal(
            interaction.user, self.guild, self.text.value,
            link=self.link.value, channel=interaction.channel)
        if err:
            await interaction.followup.send(f'Не получилось: {err}.', ephemeral=True)
            return
        await interaction.followup.send(
            f'Апелляция **#{item["id"]}** принята — обсуждение в треде. '
            'Модераторы уже видят её.', ephemeral=True)


class AppealMenuSelect(discord.ui.Select):
    """Select «Подать апелляцию» в канале (persistent)."""

    def __init__(self):
        super().__init__(
            custom_id=MENU_CUSTOM_ID,
            placeholder='Несогласны с наказанием? Подайте апелляцию…',
            min_values=1, max_values=1,
            options=[discord.SelectOption(
                label='Подать апелляцию', value='submit',
                description='Откроется окно: что произошло и ссылка-доказательство',
                emoji='⚖️')])

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog('Appeals')
        if cog is None:
            await interaction.response.send_message(
                'Модуль апелляций не загружен.', ephemeral=True)
            return
        await interaction.response.send_modal(
            AppealChannelModal(cog, interaction.guild))


WEBHOOK_NAME = 'Апелляции Hakumo'
HOOK_USERNAME = '⚖ Апелляции'


async def _channel_webhook(channel):
    """Найти/создать вебхук бота в канале.

    Меню и карточки апелляций отправляются вебхуком бота (application-
    owned): красивое имя и аватар вместо сырого аккаунта, а кнопки/селекты
    работают как раньше — интеракции приходят боту. None — вебхук недоступен
    (нет прав или канал не поддерживает), тогда обычная отправка.
    """
    fetch = getattr(channel, 'webhooks', None)
    if fetch is None:
        return None
    try:
        hooks = await fetch()
    except Exception as _ex:
        log.debug('appeals: webhooks(%s): %s', channel, _ex)
        return None
    me_id = None
    try:
        me_id = channel.guild.me.id
    except Exception as _ex:
        log.debug('appeals: guild.me недоступен: %s', _ex)
    for h in hooks or ():
        try:
            if me_id is None or h.user is None or h.user.id == me_id:
                return h
        except Exception as _ex:
            log.debug('appeals: вебхук пропущен: %s', _ex)
    create = getattr(channel, 'create_webhook', None)
    if create is None:
        return None
    try:
        return await create(name=WEBHOOK_NAME)
    except Exception as _ex:
        log.debug('appeals: create_webhook: %s', _ex)
        return None


def _hook_avatar(guild):
    try:
        return guild.icon.url if guild.icon else None
    except Exception:
        return None


class AppealMenuView(discord.ui.View):
    """Обёртка меню (persistent — переживает рестарт)."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(AppealMenuSelect())


# ─── ког ────────────────────────────────────────────────────────────────────

class Appeals(commands.Cog):
    """Приём и разбор апелляций забаненных пользователей."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('appeals')
        self._views_restored = False

    @commands.Cog.listener()
    async def on_ready(self):
        """Перерегистрировать кнопки ожидающих апелляций после рестарта."""
        if self._views_restored:
            return
        self._views_restored = True
        restored = 0
        for guild in list(self.bot.guilds):
            state = self._load(guild.id)
            for item in pending_items(state):
                if item.get('message_id'):
                    self.bot.add_view(AppealView(self, guild.id, item['id']),
                                      message_id=item['message_id'])
                    restored += 1
        try:
            self.bot.add_view(AppealMenuView())
        except Exception as _ex:
            log.debug('appeals: меню-view: %s', _ex)
        if restored:
            log.info('appeals: восстановлено %s view после рестарта', restored)

    def _load(self, guild_id):
        return self.db.get(guild_id, 'state', empty_state()) or empty_state()

    def _save(self, guild_id, state):
        self.db.set(guild_id, 'state', state)

    # ---- меню апелляций в канале ----
    async def publish_appeal_menu(self, channel):
        """Опубликовать меню подачи апелляций в канал (из панели).

        Возвращает (ok, сообщение). Повторная публикация обновляет сообщение.
        """
        if channel is None:
            return False, 'Канал не найден'
        guild = channel.guild
        state = self._load(guild.id)
        embed = discord.Embed(
            title='⚖ Апелляции на наказания',
            description=(
                'Несогласны с наказанием — варном, мутом или баном?\n'
                'Выберите ниже **«Подать апелляцию»**: откроется окно — '
                'расскажите свою версию и, если есть, приложите ссылку '
                'на скрин или видео.\n\n'
                'Для вашей апелляции создастся отдельный тред — '
                'модераторы ответят прямо в нём.'),
            color=0xF1C40F,
            timestamp=datetime.now(UTC))
        embed.set_footer(text=f'{guild.name} · апелляции',
                         icon_url=guild.icon.url if guild.icon else None)
        old = (state.get('menu') or {})
        avatar = _hook_avatar(guild)
        msg = None
        used_hook = None
        # главный путь — вебхук: имя «⚖ Апелляции», кнопки работают как раньше
        hook = await _channel_webhook(channel)
        if hook is not None:
            used_hook = hook
            try:
                if (old.get('message_id')
                        and int(old.get('webhook_id') or 0) == hook.id
                        and int(old.get('channel_id') or 0) == channel.id):
                    msg = await hook.edit_message(
                        int(old['message_id']), embed=embed, view=AppealMenuView())
                else:
                    msg = await hook.send(
                        embed=embed, view=AppealMenuView(), wait=True,
                        username=HOOK_USERNAME, avatar_url=avatar)
            except Exception as _ex:
                log.debug('appeals: меню через вебхук не ушло: %s', _ex)
                msg = None
        # фолбэк — обычная отправка от бота (вебхука нет или не вышло)
        if msg is None:
            try:
                if (old.get('message_id')
                        and int(old.get('channel_id') or 0) == channel.id
                        and not int(old.get('webhook_id') or 0)):
                    msg = await channel.edit_message(
                        int(old['message_id']), embed=embed, view=AppealMenuView())
                if msg is None:
                    msg = await channel.send(embed=embed, view=AppealMenuView())
            except (discord.Forbidden, discord.HTTPException) as _ex:
                return False, f'Бот не может писать в этот канал: {_ex}'
        state['menu'] = {'channel_id': channel.id, 'message_id': msg.id,
                         'webhook_id': getattr(used_hook, 'id', 0) or 0}
        self._save(guild.id, state)
        how = 'вебхуком' if used_hook is not None else 'от бота'
        return True, f'Меню опубликовано в {channel.mention} ({how})'

    async def _submit_channel_appeal(self, user, guild, text, link=None, channel=None):
        """Апелляция из меню в канале: карточка в отдельном треде."""
        guild_id = guild.id
        state = self._load(guild_id)
        item, err = create_appeal(state, user.id, str(user), text,
                                  datetime.now(UTC), link=link)
        if err:
            return None, err
        self._save(guild_id, state)

        if channel is None:
            try:
                from services.channel_routes import get_route
                cid = int(get_route(guild.id, 'appeal_menu_channel') or 0)
                channel = guild.get_channel(cid) if cid else None
            except Exception:
                channel = None
        if channel is None:
            menu = state.get('menu') or {}
            cid = int(menu.get('channel_id') or 0)
            channel = guild.get_channel(cid) if cid else None
        if channel is None:
            channel = self._log_channel(guild, state)
        embed = discord.Embed(
            title=f'Апелляция #{item["id"]} — новая',
            description=item['text'],
            color=COLOR_PENDING, timestamp=datetime.now(UTC))
        if item.get('link'):
            embed.add_field(name='Доказательство', value=item['link'], inline=False)
        embed.set_author(name=str(user),
                         icon_url=user.display_avatar.url
                         if getattr(user, 'display_avatar', None) else None)
        embed.add_field(name='Участник',
                        value=f'{user.mention} · `{user.id}`', inline=False)
        embed.set_footer(text=f'appeal #{item["id"]} · решение — меню под карточкой')
        png = None
        png_name = None
        try:
            appearance = normalize_appearance(state.get('appearance'))
            if appearance['mode'] == 'url' and appearance['url']:
                embed.set_image(url=appearance['url'])
            elif appearance['mode'] == 'auto':
                png = render_appeal_card(
                    appeal_id=item['id'], user_name=item['user_name'],
                    text=item['text'], link=item.get('link'),
                    theme=appearance['theme'])
                if png:
                    png_name = appeal_card_filename(item['id'])
                    embed.set_image(url=f'attachment://{png_name}')
        except Exception as _ex:
            log.debug('appeals: карточка-картинка #%s: %s', item['id'], _ex)

        view = AppealView(self, guild_id, item['id'])
        try:
            if channel is not None:
                name = f'Апелляция #{item["id"]} · {str(user)[:40]}'
                send_kw = {'embed': embed, 'view': view}
                if png and png_name:
                    send_kw['file'] = discord.File(io.BytesIO(png), filename=png_name)
                thread = await channel.create_thread(
                    name=name, type=discord.ChannelType.public_thread)
                # карточку — вебхуком «⚖ Апелляции», фолбэк — от бота
                card = None
                hook = await _channel_webhook(channel)
                if hook is not None:
                    try:
                        card = await hook.send(
                            thread=thread, wait=True,
                            username=f'{HOOK_USERNAME} · {item["id"]}',
                            avatar_url=_hook_avatar(guild), **send_kw)
                    except Exception as _ex:
                        log.debug('appeals: карточка #%s вебхуком: %s',
                                  item['id'], _ex)
                        card = None
                if card is None:
                    card = await thread.send(**send_kw)
                item['message_id'] = card.id
                item['thread_id'] = thread.id
                item['thread_url'] = card.jump_url
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.error('appeals: тред #%s не создан: %s', item['id'], _ex)
        self._save(guild_id, state)
        try:
            await user.send(
                f'Ваша апелляция **#{item["id"]}** на сервере **{guild.name}** '
                'принята. Модераторы ответят в треде.')
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.debug('appeals: ЛС о треде #%s не дошло: %s', item['id'], _ex)
        return item, None

    # ---- подача (ЛС боту) ----
    async def _submit_appeal(self, user, guild, text, link=None):
        """Общая точка создания апелляции: проверка бана, лимит, карточка."""
        guild_id = guild.id
        state = self._load(guild_id)
        item, err = create_appeal(state, user.id, str(user), text,
                                  datetime.now(UTC), link=link)
        if err:
            return None, err
        self._save(guild_id, state)

        embed = discord.Embed(title=f'Апелляция #{item["id"]} — новая',
                              description=item['text'],
                              color=COLOR_PENDING,
                              timestamp=datetime.now(UTC))
        if item.get('link'):
            embed.add_field(name='Доказательство', value=item['link'], inline=False)
        embed.set_author(name=str(user), icon_url=user.display_avatar.url
                         if getattr(user, 'display_avatar', None) else None)
        embed.set_footer(text=f'user_id: {item["user_id"]} · appeal #{item["id"]}')
        channel = self._log_channel(guild, state)
        if channel is not None:
            view = AppealView(self, guild_id, item['id'])
            # Оформление карточки из панели: авто-картинка в выбранной теме,
            # своя картинка по URL или обычный эмбед без картинки.
            appearance = normalize_appearance(state.get('appearance'))
            send_kwargs = {'embed': embed, 'view': view}
            if appearance['mode'] == 'url' and appearance['url']:
                embed.set_image(url=appearance['url'])
            elif appearance['mode'] == 'auto':
                try:
                    png = render_appeal_card(
                        appeal_id=item['id'], user_name=item['user_name'],
                        text=item['text'], link=item.get('link'),
                        theme=appearance['theme'])
                    if png:
                        fn = appeal_card_filename(item['id'])
                        send_kwargs['file'] = discord.File(io.BytesIO(png), filename=fn)
                        embed.set_image(url=f'attachment://{fn}')
                except Exception as _ex:
                    log.debug('appeals: авто-картинка #%s не отрисовалась: %s',
                              item['id'], _ex)
            try:
                msg = await channel.send(**send_kwargs)
                item['message_id'] = msg.id
                self._save(guild_id, state)
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.error('appeals: карточка #%s на %s не ушла: %s',
                          item['id'], guild_id, _ex)
        return item, None

    @app_commands.command(name='апелляция',
                          description='Обжаловать бан: /апелляция в ЛС боту',
                          extras={'keep_global': True})
    @app_commands.describe(сервер='ID сервера, на котором забанили',
                           текст='Что произошло — до 500 символов')
    async def cmd_appeal(self, interaction: discord.Interaction,
                         сервер: str, текст: str):
        """Обжаловать бан: /апелляция <ID сервера> <текст> (в ЛС боту)."""
        if interaction.guild is not None:
            await interaction.response.send_message(
                'Апелляция подаётся в личных сообщениях боту: открой ЛС бота '
                'и вызови команду там.', ephemeral=True)
            return
        try:
            guild_id = int(''.join(c for c in сервер if c.isdigit()))
        except ValueError:
            await interaction.response.send_message(
                'ID сервера должен быть числом.', ephemeral=True)
            return
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await interaction.response.send_message(
                'Я не состою на таком сервере.', ephemeral=True)
            return
        if not await self._is_banned(guild, interaction.user):
            await interaction.response.send_message(
                'Вы не забанены на этом сервере — апелляция не нужна.',
                ephemeral=True)
            return
        item, err = await self._submit_appeal(interaction.user, guild, текст)
        if err:
            await interaction.response.send_message(
                f'Не получилось: {err}.', ephemeral=True)
            return
        from cogs.embed_utils import hakumo_embed
        e = hakumo_embed('appeal', f'Апелляция #{item["id"]} отправлена',
                         f'Модераторы сервера **{guild.name}** уже получили её. '
                         'Ответ придёт в личку.')
        await interaction.response.send_message(embed=e)


    async def _is_banned(self, guild, user):
        try:
            await guild.fetch_ban(discord.Object(id=user.id))
            return True
        except discord.NotFound:
            return False
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.warning('appeals: ban-check %s на %s: %s', user.id, guild.id, _ex)
            return True

    # ---- модераторские ----


    # ---- утилиты ----
    def _log_channel(self, guild, state):
        cid = state.get('log_channel_id')
        ch = guild.get_channel(cid) if cid else None
        return ch or guild.system_channel

    async def _notify_user(self, item, accept, unbanned):
        try:
            user = await self.bot.fetch_user(item['user_id'])
        except (discord.NotFound, discord.HTTPException):
            return
        if accept:
            text = ('Ваша апелляция **принята**, бан снят — добро пожаловать обратно.'
                    if unbanned else 'Ваша апелляция **принята**.')
        else:
            text = 'Ваша апелляция **отклонена**.'
            if item.get('reply'):
                text += f'\nКомментарий модератора: {item["reply"][:200]}'
        try:
            await user.send(text)
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.debug('appeals: ЛС %s закрыты: %s', item['user_id'], _ex)


async def setup(bot):
    cog = Appeals(bot)
    await bot.add_cog(cog)
