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
                'Нужно право «Управление сервером».', ephemeral=True)
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
                'Вы не забанены на этом сервере — апелляция не нужна.', ephemeral=True)
            return
        item, err = await self.cog._submit_appeal(
            interaction.user, self.guild, self.text.value,
            link=self.link.value)
        if err:
            await interaction.followup.send(f'Не получилось: {err}.', ephemeral=True)
            return
        await interaction.followup.send(
            f'Апелляция **#{item["id"]}** отправлена модераторам сервера '
            f'**{self.guild.name}**. Ответ придёт сюда, в личку.', ephemeral=True)


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
            await interaction.response.send_message('Сервер не найден.', ephemeral=True)
            return
        await interaction.response.send_modal(AppealModal(self.cog, guild))


class AppealViewParent(discord.ui.View):
    """Обёртка select-меню выбора сервера."""

    def __init__(self, cog, guilds):
        super().__init__(timeout=300)
        self.add_item(AppealServerSelect(cog, guilds))


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
        if restored:
            log.info('appeals: восстановлено %s view после рестарта', restored)

    def _load(self, guild_id):
        return self.db.get(guild_id, 'state', empty_state()) or empty_state()

    def _save(self, guild_id, state):
        self.db.set(guild_id, 'state', state)

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

    @commands.command(name='апелляция', aliases=['appeal'])
    async def cmd_appeal(self, ctx, сервер: str, *, текст: str):
        """Обжаловать бан: !апелляция <ID сервера> <текст> (в ЛС боту)."""
        if ctx.guild is not None:
            await ctx.reply('Апелляция подаётся в личных сообщениях боту.',
                            mention_author=False)
            return
        try:
            guild_id = int(''.join(c for c in сервер if c.isdigit()))
        except ValueError:
            await ctx.reply('ID сервера должен быть числом.')
            return
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await ctx.reply('Я не состою на таком сервере.')
            return
        if not await self._is_banned(guild, ctx.author):
            await ctx.reply('Вы не забанены на этом сервере — апелляция не нужна.')
            return
        item, err = await self._submit_appeal(ctx.author, guild, текст)
        if err:
            await ctx.reply(f'Не получилось: {err}.')
            return
        await ctx.reply(f'Апелляция **#{item["id"]}** отправлена модераторам '
                        f'сервера **{guild.name}**. Ответ придёт сюда, в личку.')

    @app_commands.command(name='апелляция', description='Обжаловать бан — выберите сервер')
    async def cmd_appeal_slash(self, interaction: discord.Interaction):
        if interaction.guild is not None:
            await interaction.response.send_message(
                'Апелляция подаётся в личных сообщениях боту.', ephemeral=True)
            return
        guilds = [g for g in self.bot.guilds]
        if not guilds:
            await interaction.response.send_message(
                'Бот пока не состоит ни на одном сервере.', ephemeral=True)
            return
        view = AppealViewParent(self, guilds)
        await interaction.response.send_message(
            'Выберите сервер, на котором вы забанены:', view=view, ephemeral=True)

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
    @commands.hybrid_group(name='апелляции', aliases=['appeals'],
                           description='Настройка апелляций')
    @commands.has_permissions(manage_guild=True)
    async def grp(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.reply('Команды: `канал`, `список`.', mention_author=False)

    @grp.command(name='канал', description='Куда падать карточки апелляций')
    async def cmd_channel(self, ctx, канал: discord.TextChannel):
        state = self._load(ctx.guild.id)
        state['log_channel_id'] = канал.id
        self._save(ctx.guild.id, state)
        await ctx.reply(f'Апелляции идут в {канал.mention}.', mention_author=False)

    @grp.command(name='список', description='Ожидающие апелляции')
    async def cmd_list(self, ctx):
        rows = pending_items(self._load(ctx.guild.id))
        if not rows:
            await ctx.reply('Ожидающих апелляций нет.', mention_author=False)
            return
        embed = discord.Embed(title=f'Апелляции в ожидании — {len(rows)}',
                              color=COLOR_PENDING,
                              description='\n\n'.join(fmt_card_text(i) for i in rows[:10]))
        await ctx.reply(embed=embed, mention_author=False)

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
