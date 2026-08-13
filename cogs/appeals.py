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
from datetime import datetime, timezone

import discord
from discord.ext import commands

from db import GuildData
from logger import get_logger

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


def create_appeal(state, user_id, user_name, text, now):
    """Создать апелляцию. Возвращает (item, ошибка)."""
    text = str(text or '').strip()
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
        'status': 'pending',           # pending | accepted | rejected
        'created_at': now.isoformat(),
        'reviewed_by': None,
        'reviewed_at': None,
        'reply': None,
    }
    state['next_id'] += 1
    state['items'].append(item)
    return item, None


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
    return (
        f"**Апелляция #{item['id']}** от {item['user_name']} (`{item['user_id']}`)\n"
        f"{item['text'][:400]}"
    )


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
    @commands.hybrid_command(name='апелляция', aliases=['appeal'],
                             description='Обжаловать бан: /апелляция <ID сервера> <текст>')
    async def cmd_appeal(self, ctx, сервер: str, *, текст: str):
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
        banned = True
        try:
            await guild.fetch_ban(discord.Object(id=ctx.author.id))
        except discord.NotFound:
            banned = False
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.warning('appeals: ban-check %s на %s: %s', ctx.author.id, guild_id, _ex)
        if not banned:
            await ctx.reply('Вы не забанены на этом сервере — апелляция не нужна.')
            return

        state = self._load(guild_id)
        item, err = create_appeal(state, ctx.author.id, str(ctx.author), текст,
                                  datetime.now(UTC))
        if err:
            await ctx.reply(f'Не получилось: {err}.')
            return
        self._save(guild_id, state)
        await ctx.reply(f'Апелляция **#{item["id"]}** отправлена модераторам '
                        f'сервера **{guild.name}**. Ответ придёт сюда, в личку.')

        embed = discord.Embed(title=f'Апелляция #{item["id"]} — новая',
                              description=item['text'],
                              color=COLOR_PENDING,
                              timestamp=datetime.now(UTC))
        embed.set_author(name=f'{ctx.author}', icon_url=ctx.author.display_avatar.url
                         if ctx.author.display_avatar else None)
        embed.set_footer(text=f'user_id: {item["user_id"]} · appeal #{item["id"]}')
        channel = self._log_channel(guild, state)
        if channel is not None:
            view = AppealView(self, guild_id, item['id'])
            try:
                msg = await channel.send(embed=embed, view=view)
                item['message_id'] = msg.id
                self._save(guild_id, state)
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.error('appeals: карточка #%s на %s не ушла: %s',
                          item['id'], guild_id, _ex)

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
