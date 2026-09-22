# -*- coding: utf-8 -*-
"""Бот Мафии — Discord UI по ТЗ.

/mafia start — ведущий в войсе запускает лобби из участников канала.
Раздача ролей, DM + кнопка подтверждения, сводка ведущему, игровой стол.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from logger import get_logger
from services.mafia import (
    PHASE_CONFIRM,
    PHASE_ENDED,
    PHASE_LOBBY,
    PHASE_PLAYING,
    PHASE_READY,
    ROLES,
    STORE,
    Game,
    preset_summary,
)

log = get_logger('mafia')

GOLD = 0xD4AF37
RED = 0xE74C3C
GREEN = 0x2ECC71
BLUE = 0x5EC8FF
DARK = 0x1A1D24


def _phase_label(phase: str) -> str:
    return {
        PHASE_LOBBY: 'Лобби',
        PHASE_CONFIRM: 'Подтверждение',
        PHASE_READY: 'Готово к старту',
        PHASE_PLAYING: 'Идёт игра',
        PHASE_ENDED: 'Завершена',
    }.get(phase, phase)


def _mention(uid: int) -> str:
    return f'<@{uid}>'


def lobby_embed(game: Game) -> discord.Embed:
    n = len(game.players)
    e = discord.Embed(
        title=f'🎲 Мафия · игра #{game.game_id}',
        description=(
            f'Ведущий: {_mention(game.host_id)}\n'
            f'Голос: <#{game.voice_channel_id}>\n'
            f'Игроков: **{n}** (ведущий не в раздаче)\n'
            f'Фаза: **{_phase_label(game.phase)}**'
        ),
        color=BLUE,
    )
    if n >= 6:
        e.add_field(name='Пресет ролей', value=preset_summary(n), inline=False)
    else:
        e.add_field(
            name='Нужно ещё игроков',
            value=f'Минимум 6 · сейчас {n}. Пусть зайдут в войс и нажмите «Обновить состав».',
            inline=False,
        )
    names = ', '.join(_mention(p.user_id) for p in game.players.values()) or '—'
    e.add_field(name='Состав', value=names[:1000], inline=False)
    e.set_footer(text='Hakumo Mafia')
    return e


def host_summary_embed(game: Game) -> discord.Embed:
    conf = game.confirmed_count()
    total = len(game.players)
    color = GREEN if game.all_confirmed() else GOLD
    if game.phase == PHASE_PLAYING:
        color = RED
    if game.phase == PHASE_ENDED:
        color = GREEN if game.winner == 'town' else RED
    e = discord.Embed(
        title=f'📋 Сводка ведущего · #{game.game_id}',
        description=(
            f'Игроков: **{total}**\n'
            f'Подтвердили: **{conf}/{total}**\n'
            f'Фаза: **{_phase_label(game.phase)}**'
        ),
        color=color,
    )
    lines = []
    for p in game.players.values():
        role = ROLES.get(p.role).label if p.role and p.role in ROLES else '—'
        mark = '✅' if p.confirmed else '⏳'
        alive = '' if p.alive else ' · 💀'
        dm = '' if p.dm_ok else ' · ⚠️ DM закрыт'
        lines.append(f'{_mention(p.user_id)} — {role} — {mark}{alive}{dm}')
    e.add_field(name='Распределение', value='\n'.join(lines)[:1020] or '—', inline=False)
    if game.winner:
        label = '🏆 Выиграл мирный город' if game.winner == 'town' else '🏆 Выиграла мафия'
        e.add_field(name='Финал', value=label, inline=False)
    if game.log:
        e.add_field(name='Лог', value='\n'.join(game.log[-8:])[:1020], inline=False)
    e.set_footer(text='Только для ведущего · обновляется автоматически')
    return e


def role_dm_embed(game: Game, player) -> discord.Embed:
    role = ROLES[player.role]
    e = discord.Embed(
        title=f'Ваша роль: {role.name}',
        description=(
            f'{role.emoji} **{role.name}**\n\n'
            f'{role.description}\n\n'
            f'Ведущий: {_mention(game.host_id)}\n'
            f'Игра: **#{game.game_id}**\n\n'
            'Ознакомьтесь с ролью и подтвердите участие кнопкой ниже.'
        ),
        color=RED if role.team == 'mafia' else BLUE,
    )
    e.set_footer(text='Никому не показывайте это сообщение')
    return e


def public_status_embed(game: Game) -> discord.Embed:
    e = discord.Embed(
        title=f'🎲 Мафия #{game.game_id}',
        color=GOLD,
    )
    if game.phase == PHASE_CONFIRM:
        e.description = (
            f'Роли разосланы. Подтвердили: **{game.confirmed_count()}/{len(game.players)}**\n'
            'Проверьте личные сообщения с ботом.'
        )
    elif game.phase == PHASE_READY:
        e.description = '✅ Все подтвердили. Ведущий может начать игру.'
    elif game.phase == PHASE_PLAYING:
        alive = len(game.alive_players())
        dead = [p for p in game.players.values() if not p.alive]
        dead_txt = ', '.join(_mention(p.user_id) for p in dead) if dead else '—'
        e.description = (
            f'Игра идёт · в живых: **{alive}**\n'
            f'Выбыли: {dead_txt}'
        )
        e.color = RED
    elif game.phase == PHASE_ENDED:
        if game.winner == 'town':
            e.description = '🏁 **Выиграл мирный город**'
            e.color = GREEN
        elif game.winner == 'mafia':
            e.description = '🏁 **Выиграла мафия**'
            e.color = RED
        else:
            e.description = 'Игра завершена'
    else:
        e.description = lobby_embed(game).description
    return e


# ── Views ────────────────────────────────────────────────────


class ConfirmView(discord.ui.View):
    """Кнопка подтверждения в ЛС. custom_id уникален на раздачу+игрока."""

    def __init__(self, game_id: str, deal_token: str, user_id: int):
        super().__init__(timeout=None)
        self.game_id = game_id
        self.deal_token = deal_token
        self.user_id = user_id
        self.confirm.custom_id = f'mafia:confirm:{deal_token}:{user_id}'

    @discord.ui.button(
        label='Подтвердить участие',
        style=discord.ButtonStyle.success,
        emoji='✅',
        custom_id='mafia:confirm:pending',
    )
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('Это не ваша кнопка.', ephemeral=True)
            return
        cog: Mafia | None = interaction.client.get_cog('mafia')  # type: ignore
        if cog is None:
            await interaction.response.send_message('Модуль мафии недоступен.', ephemeral=True)
            return
        await cog.handle_confirm(interaction, self.game_id, self.deal_token)


def make_confirm_view(game: Game, user_id: int) -> ConfirmView:
    return ConfirmView(game.game_id, game.deal_token, user_id)


class LobbyView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=600)
        self.guild_id = guild_id

    async def _host_only(self, interaction: discord.Interaction) -> Game | None:
        game = STORE.get(self.guild_id)
        if not game:
            await interaction.response.send_message('Активной игры нет.', ephemeral=True)
            return None
        if interaction.user.id != game.host_id:
            await interaction.response.send_message('Только ведущий.', ephemeral=True)
            return None
        return game

    @discord.ui.button(label='Обновить состав', style=discord.ButtonStyle.secondary, emoji='🔄')
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._host_only(interaction)
        if not game:
            return
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        try:
            members = await cog.voice_members(interaction.guild, game.voice_channel_id, game.host_id)
            game.set_players_from_voice(members)
            STORE.persist(game)
        except Exception as e:
            await interaction.response.send_message(f'Не вышло: {e}', ephemeral=True)
            return
        await interaction.response.edit_message(embed=lobby_embed(game), view=LobbyView(self.guild_id))

    @discord.ui.button(label='Раздать роли', style=discord.ButtonStyle.primary, emoji='🎭')
    async def deal(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._host_only(interaction)
        if not game:
            return
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        await interaction.response.defer(ephemeral=True)
        try:
            await cog.deal_roles(interaction, game)
        except Exception as e:
            await interaction.followup.send(f'Не вышло раздать: {e}', ephemeral=True)

    @discord.ui.button(label='Отменить', style=discord.ButtonStyle.danger, emoji='🗑️')
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._host_only(interaction)
        if not game:
            return
        game.cancel()
        STORE.clear(game.guild_id, archive=True)
        await interaction.response.edit_message(
            embed=discord.Embed(title='Игра отменена', color=DARK),
            view=None,
        )


class HostPanelView(discord.ui.View):
    """Панель ведущего. Один persistent-view на все гильдии:
    guild берётся из interaction.guild_id (либо из активной игры по host_id в ЛС).
    """

    def __init__(self):
        super().__init__(timeout=None)

    async def _host(self, interaction: discord.Interaction) -> Game | None:
        game = None
        if interaction.guild_id:
            game = STORE.get(interaction.guild_id)
        if game is None:
            # сводка в ЛС — guild_id нет, ищем по ведущему
            for g in STORE._by_guild.values():
                if g.host_id == interaction.user.id and g.phase != PHASE_ENDED:
                    game = g
                    break
        if not game:
            if not interaction.response.is_done():
                await interaction.response.send_message('Игры нет.', ephemeral=True)
            return None
        if interaction.user.id != game.host_id:
            if not interaction.response.is_done():
                await interaction.response.send_message('Только ведущий.', ephemeral=True)
            return None
        return game

    async def _need_playing(self, interaction: discord.Interaction) -> Game | None:
        game = await self._host(interaction)
        if not game:
            return None
        if game.phase != PHASE_PLAYING:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    'Доступно только во время игры.', ephemeral=True)
            return None
        return game

    @discord.ui.button(label='Кто не подтвердил', style=discord.ButtonStyle.secondary, emoji='⏳',
                       custom_id='mafia:host:pending', row=0)
    async def pending(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._host(interaction)
        if not game:
            return
        pending = game.unconfirmed()
        if not pending:
            txt = 'Все подтвердили ✅'
        else:
            txt = '\n'.join(f'⏳ {_mention(p.user_id)}' for p in pending)
        await interaction.response.send_message(txt, ephemeral=True)

    @discord.ui.button(label='Напомнить', style=discord.ButtonStyle.secondary, emoji='🔔',
                       custom_id='mafia:host:remind', row=0)
    async def remind(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._host(interaction)
        if not game:
            return
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        await interaction.response.defer(ephemeral=True)
        n = await cog.remind_unconfirmed(game)
        await interaction.followup.send(f'Напомнил {n} игрокам.', ephemeral=True)

    @discord.ui.button(label='Перераздать', style=discord.ButtonStyle.primary, emoji='🎭',
                       custom_id='mafia:host:redeal', row=0)
    async def redeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._host(interaction)
        if not game:
            return
        if game.phase == PHASE_PLAYING:
            await interaction.response.send_message(
                'Во время игры нельзя. Сначала завершите.', ephemeral=True)
            return
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        await interaction.response.defer(ephemeral=True)
        try:
            await cog.deal_roles(interaction, game)
            await interaction.followup.send(
                'Роли переразданы. Старая раздача недействительна.', ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f'Ошибка: {e}', ephemeral=True)

    @discord.ui.button(label='Начать игру', style=discord.ButtonStyle.success, emoji='▶️',
                       custom_id='mafia:host:start', row=1)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._host(interaction)
        if not game:
            return
        try:
            game.start()
            STORE.persist(game)
        except Exception as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        await cog.refresh_host_summary(game)
        await cog.refresh_public(game)
        await interaction.response.send_message(
            'Игра началась. Состав зафиксирован.', ephemeral=True)

    @discord.ui.button(label='Убийство мафии', style=discord.ButtonStyle.danger, emoji='🔫',
                       custom_id='mafia:host:kill', row=1)
    async def kill(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._need_playing(interaction)
        if not game:
            return
        await interaction.response.send_message(
            'Кого убила мафия?',
            view=PlayerSelectView(game.guild_id, mode='kill'),
            ephemeral=True,
        )

    @discord.ui.button(label='Изгнать голосом', style=discord.ButtonStyle.danger, emoji='🗳️',
                       custom_id='mafia:host:vote', row=1)
    async def vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._need_playing(interaction)
        if not game:
            return
        await interaction.response.send_message(
            'Кого изгнали голосованием?',
            view=PlayerSelectView(game.guild_id, mode='vote'),
            ephemeral=True,
        )

    @discord.ui.button(label='Проверка шерифа', style=discord.ButtonStyle.primary, emoji='🕵️',
                       custom_id='mafia:host:sheriff', row=2)
    async def sheriff(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._need_playing(interaction)
        if not game:
            return
        await interaction.response.send_message(
            'Кого проверил шериф?',
            view=PlayerSelectView(game.guild_id, mode='sheriff'),
            ephemeral=True,
        )

    @discord.ui.button(label='Проверка дона', style=discord.ButtonStyle.primary, emoji='👑',
                       custom_id='mafia:host:don', row=2)
    async def don(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._need_playing(interaction)
        if not game:
            return
        await interaction.response.send_message(
            'Кого проверил дон?',
            view=PlayerSelectView(game.guild_id, mode='don'),
            ephemeral=True,
        )

    @discord.ui.button(label='Исключить из состава', style=discord.ButtonStyle.secondary, emoji='🚫',
                       custom_id='mafia:host:exclude', row=2)
    async def exclude(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._host(interaction)
        if not game:
            return
        if game.phase == PHASE_PLAYING:
            await interaction.response.send_message(
                'Во время игры используйте «Изгнать голосом» / «Убийство».', ephemeral=True)
            return
        await interaction.response.send_message(
            'Кого исключить из состава?',
            view=PlayerSelectView(game.guild_id, mode='exclude', alive_only=False),
            ephemeral=True,
        )

    @discord.ui.button(label='Отменить игру', style=discord.ButtonStyle.danger, emoji='🗑️',
                       custom_id='mafia:host:cancel', row=3)
    async def cancel_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._host(interaction)
        if not game:
            return
        gid = game.guild_id
        game.cancel()
        STORE.clear(gid, archive=True)
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        await cog.refresh_public(game)
        await interaction.response.send_message(f'Игра #{game.game_id} отменена.', ephemeral=True)


class PlayerSelectView(discord.ui.View):
    def __init__(self, guild_id: int, mode: str, alive_only: bool = True):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.mode = mode
        game = STORE.get(guild_id)
        options = []
        if game:
            pool = game.alive_players() if alive_only else list(game.players.values())
            for p in pool[:25]:
                role = ROLES.get(p.role).name if p.role and p.role in ROLES else '?'
                options.append(discord.SelectOption(
                    label=p.display_name[:100],
                    value=str(p.user_id),
                    description=f'роль: {role}'[:100],
                ))
        select = discord.ui.Select(
            placeholder='Выберите игрока…',
            options=options or [discord.SelectOption(label='Нет игроков', value='0')],
            min_values=1,
            max_values=1,
        )
        select.callback = self._on_select  # type: ignore
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        game = STORE.get(self.guild_id)
        if not game or interaction.user.id != game.host_id:
            await interaction.response.send_message('Нет доступа.', ephemeral=True)
            return
        raw = interaction.data.get('values', ['0'])[0]  # type: ignore
        uid = int(raw)
        if uid == 0:
            await interaction.response.send_message('Нет игроков.', ephemeral=True)
            return
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        try:
            if self.mode == 'kill':
                p = game.kill(uid)
                msg = f'💀 Убит: **{p.display_name}**'
            elif self.mode == 'vote':
                p = game.vote_out(uid)
                msg = f'🗳️ Изгнан: **{p.display_name}**'
            elif self.mode == 'sheriff':
                rec = game.sheriff_check(uid)
                msg = f'🕵️ {rec["target_name"]}: **{rec["result"]}**\n{rec["detail"]}'
            elif self.mode == 'don':
                rec = game.don_check(uid)
                msg = f'👑 {rec["target_name"]}: **{rec["result"]}**\n{rec["detail"]}'
            elif self.mode == 'exclude':
                p = game.exclude_player(uid)
                msg = f'Исключён: **{p.display_name}**. Нужна новая раздача.'
            else:
                msg = 'Неизвестное действие'
            if game.winner == 'town':
                msg += '\n\n🏁 **Выиграл мирный город**'
            elif game.winner == 'mafia':
                msg += '\n\n🏁 **Выиграла мафия**'
            STORE.persist(game)
            await cog.refresh_host_summary(game)
            await cog.refresh_public(game)
            if game.phase == PHASE_ENDED:
                STORE.clear(game.guild_id, archive=True)
            await interaction.response.edit_message(content=msg, view=None)
        except Exception as e:
            if interaction.response.is_done():
                await interaction.followup.send(str(e), ephemeral=True)
            else:
                await interaction.response.send_message(str(e), ephemeral=True)


# ── Cog ──────────────────────────────────────────────────────


class Mafia(commands.Cog, name='mafia'):
    """🎲 Мафия — раздача ролей и стол ведущего."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        n = STORE.restore_all()
        # один persistent host-panel на все гильдии (guild из interaction)
        self.bot.add_view(HostPanelView())
        for game in list(STORE._by_guild.values()):
            if game.deal_token:
                for uid in game.players:
                    self.bot.add_view(make_confirm_view(game, uid))
        log.info('Mafia: восстановлено активных игр: %s', n)

    async def voice_members(self, guild: discord.Guild, voice_id: int, host_id: int):
        ch = guild.get_channel(int(voice_id))
        if ch is None or not isinstance(ch, discord.VoiceChannel):
            raise RuntimeError('Голосовой канал не найден')
        out = []
        for m in ch.members:
            if m.bot:
                continue
            if m.id == host_id:
                continue
            out.append((m.id, m.display_name))
        return out

    async def deal_roles(self, interaction: discord.Interaction, game: Game):
        counts = game.deal()
        STORE.persist(game)
        sent = failed = 0
        for p in game.players.values():
            member = interaction.guild.get_member(p.user_id) if interaction.guild else None
            user = member or await self.bot.fetch_user(p.user_id)
            view = make_confirm_view(game, p.user_id)
            self.bot.add_view(view)
            try:
                await user.send(embed=role_dm_embed(game, p), view=view)
                sent += 1
            except Exception:
                game.mark_dm_failed(p.user_id)
                failed += 1
        STORE.persist(game)
        host = interaction.user
        if interaction.guild:
            member = interaction.guild.get_member(game.host_id)
            if member:
                host = member
        await self.ensure_host_summary(game, host)
        await self.refresh_public(game)
        if game.lobby_message_id and interaction.channel:
            try:
                msg = await interaction.channel.fetch_message(int(game.lobby_message_id))
                # публично — только статус, без панели ведущего (роли секретны)
                await msg.edit(embed=public_status_embed(game), view=None)
            except Exception:
                pass
        summary = (
            f'Раздано по пресету: {preset_summary(len(game.players))}\n'
            f'DM отправлены: **{sent}**, не дошли: **{failed}**.\n'
            'Сводка у вас в личке.'
        )
        if interaction.response.is_done():
            await interaction.followup.send(summary, ephemeral=True)
        else:
            await interaction.response.send_message(summary, ephemeral=True)
        return counts

    async def ensure_host_summary(self, game: Game, host: discord.abc.User):
        embed = host_summary_embed(game)
        view = HostPanelView()
        self.bot.add_view(view)
        try:
            if game.host_summary_channel_id and game.host_summary_message_id:
                ch = self.bot.get_channel(int(game.host_summary_channel_id))
                if ch is None:
                    ch = await self.bot.fetch_channel(int(game.host_summary_channel_id))
                msg = await ch.fetch_message(int(game.host_summary_message_id))
                await msg.edit(embed=embed, view=view)
                return
        except Exception:
            pass
        try:
            msg = await host.send(embed=embed, view=view)
            game.host_summary_channel_id = msg.channel.id
            game.host_summary_message_id = msg.id
            STORE.persist(game)
        except Exception as e:
            log.warning('mafia host summary DM failed: %s', e)

    async def refresh_host_summary(self, game: Game):
        if not (game.host_summary_channel_id and game.host_summary_message_id):
            return
        try:
            ch = self.bot.get_channel(int(game.host_summary_channel_id))
            if ch is None:
                ch = await self.bot.fetch_channel(int(game.host_summary_channel_id))
            msg = await ch.fetch_message(int(game.host_summary_message_id))
            await msg.edit(embed=host_summary_embed(game), view=HostPanelView())
        except Exception as e:
            log.debug('refresh_host_summary: %s', e)

    async def refresh_public(self, game: Game):
        if not game.lobby_message_id:
            return
        try:
            ch = self.bot.get_channel(int(game.text_channel_id))
            if ch is None:
                ch = await self.bot.fetch_channel(int(game.text_channel_id))
            msg = await ch.fetch_message(int(game.lobby_message_id))
            await msg.edit(embed=public_status_embed(game), view=None)
        except Exception as e:
            log.debug('refresh_public: %s', e)

    async def remind_unconfirmed(self, game: Game) -> int:
        n = 0
        for p in game.unconfirmed():
            try:
                user = self.bot.get_user(p.user_id) or await self.bot.fetch_user(p.user_id)
                view = make_confirm_view(game, p.user_id)
                self.bot.add_view(view)
                await user.send(
                    f'⏰ Напоминание: подтвердите участие в мафии **#{game.game_id}**.',
                    embed=role_dm_embed(game, p) if p.role else None,
                    view=view,
                )
                n += 1
            except Exception:
                game.mark_dm_failed(p.user_id)
        STORE.persist(game)
        return n

    async def handle_confirm(self, interaction: discord.Interaction, game_id: str, deal_token: str):
        game = None
        for g in STORE._by_guild.values():
            if g.game_id == game_id:
                game = g
                break
        if game is None:
            await interaction.response.send_message(
                'Игра не найдена или уже завершена.', ephemeral=True)
            return
        try:
            first = game.confirm(interaction.user.id, deal_token)
        except Exception as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        STORE.persist(game)
        await self.refresh_host_summary(game)
        await self.refresh_public(game)
        if first:
            extra = ''
            if game.phase == PHASE_READY:
                extra = '\n✅ Все подтвердили — ведущий может начать.'
            await interaction.response.send_message(
                f'✅ Участие подтверждено. Ждите ведущего.{extra}', ephemeral=True)
        else:
            await interaction.response.send_message(
                'Вы уже подтвердили участие.', ephemeral=True)

    # ── slash ────────────────────────────────────────────────
    mafia = app_commands.Group(name='mafia', description='Бот Мафии — раздача ролей и стол')

    @mafia.command(name='start', description='Начать новую игру (вы должны быть в голосовом канале)')
    async def mafia_start(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message('Только на сервере.', ephemeral=True)
            return
        existing = STORE.get(interaction.guild.id)
        if existing and existing.phase != PHASE_ENDED:
            await interaction.response.send_message(
                f'Уже есть игра **#{existing.game_id}** ({_phase_label(existing.phase)}). '
                'Сначала `/mafia cancel` или завершите её.',
                ephemeral=True,
            )
            return
        voice = interaction.user.voice.channel if interaction.user.voice else None
        if voice is None:
            await interaction.response.send_message(
                'Зайдите в голосовой канал с игроками, затем снова `/mafia start`.',
                ephemeral=True,
            )
            return
        members = await self.voice_members(interaction.guild, voice.id, interaction.user.id)
        game = Game.create(
            guild_id=interaction.guild.id,
            host_id=interaction.user.id,
            voice_channel_id=voice.id,
            text_channel_id=interaction.channel_id,
            members=members,
        )
        STORE.set(game)
        view = LobbyView(interaction.guild.id)
        await interaction.response.send_message(embed=lobby_embed(game), view=view)
        msg = await interaction.original_response()
        game.lobby_message_id = msg.id
        STORE.persist(game)

    @mafia.command(name='status', description='Статус текущей игры')
    async def mafia_status(self, interaction: discord.Interaction):
        game = STORE.get(interaction.guild.id) if interaction.guild else None
        if not game:
            await interaction.response.send_message('Активной игры нет.', ephemeral=True)
            return
        await interaction.response.send_message(embed=public_status_embed(game), ephemeral=True)

    @mafia.command(name='panel', description='Прислать ведущему сводку ещё раз')
    async def mafia_panel(self, interaction: discord.Interaction):
        game = STORE.get(interaction.guild.id) if interaction.guild else None
        if not game:
            await interaction.response.send_message('Игры нет.', ephemeral=True)
            return
        if interaction.user.id != game.host_id:
            await interaction.response.send_message('Только ведущий.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        game.host_summary_message_id = None
        game.host_summary_channel_id = None
        await self.ensure_host_summary(game, interaction.user)
        await interaction.followup.send('Сводка отправлена в ЛС.', ephemeral=True)

    @mafia.command(name='resend', description='Повторно отправить роль игроку')
    @app_commands.describe(player='Кому переслать роль')
    async def mafia_resend(self, interaction: discord.Interaction, player: discord.Member):
        game = STORE.get(interaction.guild.id) if interaction.guild else None
        if not game or interaction.user.id != game.host_id:
            await interaction.response.send_message('Только ведущий активной игры.', ephemeral=True)
            return
        p = game.players.get(player.id)
        if not p or not p.role:
            await interaction.response.send_message('Игрок без роли / не в составе.', ephemeral=True)
            return
        view = make_confirm_view(game, p.user_id)
        self.bot.add_view(view)
        try:
            await player.send(embed=role_dm_embed(game, p), view=view)
            p.dm_ok = True
            STORE.persist(game)
            await interaction.response.send_message(f'Роль отправлена {player.mention}.', ephemeral=True)
        except Exception:
            game.mark_dm_failed(p.user_id)
            STORE.persist(game)
            await interaction.response.send_message(
                'Не смог написать в ЛС — пусть откроет личку с ботом.', ephemeral=True)

    @mafia.command(name='add', description='Добавить игрока из войса в состав')
    @app_commands.describe(player='Кого добавить')
    async def mafia_add(self, interaction: discord.Interaction, player: discord.Member):
        game = STORE.get(interaction.guild.id) if interaction.guild else None
        if not game or interaction.user.id != game.host_id:
            await interaction.response.send_message('Только ведущий.', ephemeral=True)
            return
        try:
            game.add_player(player.id, player.display_name)
            STORE.persist(game)
            await interaction.response.send_message(
                f'Добавлен {player.mention}. Нужна новая раздача ролей.', ephemeral=True)
            await self.refresh_public(game)
            await self.refresh_host_summary(game)
        except Exception as e:
            await interaction.response.send_message(str(e), ephemeral=True)

    @mafia.command(name='cancel', description='Отменить текущую игру')
    async def mafia_cancel(self, interaction: discord.Interaction):
        game = STORE.get(interaction.guild.id) if interaction.guild else None
        if not game:
            await interaction.response.send_message('Игры нет.', ephemeral=True)
            return
        is_admin = False
        if isinstance(interaction.user, discord.Member):
            is_admin = interaction.user.guild_permissions.administrator
        if interaction.user.id != game.host_id and not is_admin:
            await interaction.response.send_message('Только ведущий или админ.', ephemeral=True)
            return
        game.cancel()
        STORE.clear(game.guild_id, archive=True)
        await interaction.response.send_message(f'Игра #{game.game_id} отменена.', ephemeral=True)
        await self.refresh_public(game)

    @mafia.command(name='presets', description='Показать пресеты ролей по числу игроков')
    async def mafia_presets(self, interaction: discord.Interaction):
        lines = []
        for n in (6, 7, 8, 9, 10, 11, 12, 14):
            try:
                lines.append(f'**{n}** — {preset_summary(n)}')
            except Exception:
                pass
        e = discord.Embed(title='Пресеты мафии', description='\n'.join(lines), color=GOLD)
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Mafia(bot))
