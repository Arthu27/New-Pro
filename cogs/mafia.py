# -*- coding: utf-8 -*-
"""Бот Мафии — Discord UI по ТЗ.

/mafia — одна команда с выпадающим меню: начать, статус, сводка, переслать роль,
добавить, отменить, пресеты. Раздача ролей, DM + подтверждение, стол ведущего.
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
BLACK = 0x000000  # V2 accent как у модпанели


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


def _roster_lines(game: Game, *, limit: int = 16) -> str:
    players = list(game.players.values())
    if not players:
        return '_пусто_'
    lines = [f'{i}. {_mention(p.user_id)}' for i, p in enumerate(players[:limit], 1)]
    if len(players) > limit:
        lines.append(f'… +{len(players) - limit}')
    return '\n'.join(lines)


def lobby_embed(game: Game) -> discord.Embed:
    """Фолбек без V2 — короткий черный эмбед."""
    n = len(game.players)
    need = max(0, 6 - n)
    e = discord.Embed(
        title='Мафия',
        description=(
            f'**Ведущий** {_mention(game.host_id)}\n'
            f'**Войс** <#{game.voice_channel_id}>\n'
            f'**Состав** {n}/6+'
            + (f' · ещё {need}' if need else '')
        ),
        color=BLACK,
    )
    e.add_field(name='Игроки', value=_roster_lines(game)[:1000], inline=False)
    e.set_footer(text='Hakumo · Участвовать')
    return e


def lobby_body_md(game: Game) -> str:
    from services.mafia.ui_v2 import lobby_status_md
    return lobby_status_md(game)


def host_summary_embed(game: Game) -> discord.Embed:
    conf = game.confirmed_count()
    total = len(game.players)
    color = GREEN if game.all_confirmed() else GOLD
    if game.phase == PHASE_PLAYING:
        color = RED
    if game.phase == PHASE_ENDED:
        color = GREEN if game.winner == 'town' else RED
    e = discord.Embed(
        title=f'Сводка · #{game.game_id}',
        description=(
            f'**{_phase_label(game.phase)}** · '
            f'{conf}/{total} подтвердили'
        ),
        color=color,
    )
    lines = []
    for p in game.players.values():
        try:
            from services.mafia.ui_v2 import role_mark
            role = (
                f'{role_mark(p.role)} {ROLES[p.role].name}'
                if p.role and p.role in ROLES else '—'
            )
        except Exception:
            role = ROLES.get(p.role).label if p.role and p.role in ROLES else '—'
        mark = '✓' if p.confirmed else '…'
        alive = '' if p.alive else ' · out'
        dm = '' if p.dm_ok else ' · DM'
        lines.append(f'{mark} {_mention(p.user_id)} — {role}{alive}{dm}')
    e.add_field(name='Стол', value='\n'.join(lines)[:1020] or '—', inline=False)
    if game.winner:
        label = 'Город победил' if game.winner == 'town' else 'Мафия победила'
        e.add_field(name='Финал', value=label, inline=False)
    if game.log:
        e.add_field(name='Лог', value='\n'.join(game.log[-6:])[:1020], inline=False)
    e.set_footer(text='Только ведущему')
    return e


def role_dm_embed(game: Game, player) -> discord.Embed:
    role = ROLES[player.role]
    try:
        from services.mafia.ui_v2 import role_mark
        mark = role_mark(player.role)
    except Exception:
        mark = role.emoji
    e = discord.Embed(
        title=role.name,
        description=(
            f'{mark} **{role.name}**\n\n'
            f'{role.description}\n\n'
            f'-# #{game.game_id} · ведущий {_mention(game.host_id)}'
        ),
        color=RED if role.team == 'mafia' else BLUE,
    )
    e.set_footer(text='Секретно · подтвердите ниже')
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
        try:
            from services.mafia.ui_v2 import sticker
            self.confirm.emoji = sticker('confirm')
        except Exception:
            pass

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


# ── Public lobby buttons (persistent) ────────────────────────────────


class _JoinBtn(discord.ui.Button):
    def __init__(self):
        try:
            from services.mafia.ui_v2 import sticker
            em = sticker('join')
        except Exception:
            em = '✋'
        super().__init__(
            label='Участвовать', style=discord.ButtonStyle.success,
            emoji=em, custom_id='mafia:public:join')

    async def callback(self, interaction: discord.Interaction):
        await _public_join(interaction)


class _LeaveBtn(discord.ui.Button):
    def __init__(self):
        try:
            from services.mafia.ui_v2 import sticker
            em = sticker('leave')
        except Exception:
            em = '🚪'
        super().__init__(
            label='Выйти', style=discord.ButtonStyle.secondary,
            emoji=em, custom_id='mafia:public:leave')

    async def callback(self, interaction: discord.Interaction):
        await _public_leave(interaction)


async def _public_join(interaction: discord.Interaction):
    gid = interaction.guild_id
    game = STORE.get(int(gid)) if gid else None
    if not game or game.phase != PHASE_LOBBY:
        await interaction.response.send_message('Набора нет.', ephemeral=True)
        return
    if interaction.user.id == game.host_id:
        await interaction.response.send_message(
            'Вы ведущий — в состав не входите.', ephemeral=True)
        return
    voice = getattr(getattr(interaction.user, 'voice', None), 'channel', None)
    if voice is None or int(voice.id) != int(game.voice_channel_id):
        await interaction.response.send_message(
            f'Сначала <#{game.voice_channel_id}>, потом снова.',
            ephemeral=True)
        return
    cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
    try:
        name = getattr(interaction.user, 'display_name', None) or str(interaction.user)
        game.add_player(interaction.user.id, name)
        STORE.persist(game)
    except Exception as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return
    kw = await cog.lobby_edit_kwargs(game)
    await interaction.response.edit_message(**kw)
    try:
        await interaction.followup.send(
            f'В составе · **{len(game.players)}**', ephemeral=True)
    except Exception:
        pass


async def _public_leave(interaction: discord.Interaction):
    gid = interaction.guild_id
    game = STORE.get(int(gid)) if gid else None
    if not game or game.phase != PHASE_LOBBY:
        await interaction.response.send_message(
            'Выйти можно только в наборе.', ephemeral=True)
        return
    cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
    try:
        game.leave_player(interaction.user.id)
        STORE.persist(game)
    except Exception as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return
    kw = await cog.lobby_edit_kwargs(game)
    await interaction.response.edit_message(**kw)
    try:
        await interaction.followup.send('Вышли.', ephemeral=True)
    except Exception:
        pass


class MafiaLobbyLayout(discord.ui.LayoutView):
    """Публичная V2-карточка: баннер + состав + Участвовать/Выйти."""

    def __init__(self, game: Game):
        super().__init__(timeout=None)
        self.guild_id = int(game.guild_id)
        self.game_id = game.game_id
        self._banner_name = 'hakumo_events_banner_v15.png'
        self._rebuild(game)

    def _rebuild(self, game: Game):
        self.clear_items()
        from services.mafia.ui_v2 import (
            V2_AVAILABLE, SHOW_MENU_BANNER, lobby_status_md, build_mafia_lobby_items,
        )
        join = _JoinBtn()
        leave = _LeaveBtn()
        row = discord.ui.ActionRow()
        row.add_item(join)
        row.add_item(leave)
        body = lobby_status_md(game)
        banner = self._banner_name if SHOW_MENU_BANNER else None
        if V2_AVAILABLE:
            items = build_mafia_lobby_items(
                body=body, banner_filename=banner, action_row=row)
            if items:
                for it in items:
                    self.add_item(it)
                return
        self.add_item(row)


class PublicLobbyView(discord.ui.View):
    """Фолбек без V2."""

    def __init__(self, guild_id: int = 0):
        super().__init__(timeout=None)
        self.guild_id = int(guild_id or 0)
        self.add_item(_JoinBtn())
        self.add_item(_LeaveBtn())


class HostToolsView(discord.ui.View):
    """Эпhemeral-кнопки ведущего."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=900)
        self.guild_id = int(guild_id)
        try:
            from services.mafia.ui_v2 import sticker
            e_r, e_d, e_c = sticker('refresh'), sticker('deal'), sticker('cancel')
        except Exception:
            e_r = e_d = e_c = None
        self.add_item(_HostSyncBtn(self.guild_id, e_r))
        self.add_item(_HostDealBtn(self.guild_id, e_d))
        self.add_item(_HostCancelBtn(self.guild_id, e_c))


class _HostSyncBtn(discord.ui.Button):
    def __init__(self, guild_id: int, emoji=None):
        super().__init__(
            label='Синхр. войс', style=discord.ButtonStyle.secondary,
            emoji=emoji or '🔄')
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        game = STORE.get(self.guild_id)
        if not game or interaction.user.id != game.host_id:
            await interaction.response.send_message('Только ведущий.', ephemeral=True)
            return
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        host_voice = getattr(getattr(interaction.user, 'voice', None), 'channel', None)
        if host_voice is None or int(host_voice.id) != int(game.voice_channel_id):
            await interaction.response.send_message(
                f'Зайдите в <#{game.voice_channel_id}>.', ephemeral=True)
            return
        try:
            members = await cog.voice_members(
                interaction.guild, game.voice_channel_id, game.host_id)
            game.set_players_from_voice(members)
            STORE.persist(game)
            await cog.refresh_lobby_message(game)
        except Exception as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        await interaction.response.send_message(
            f'Состав: **{len(game.players)}**', ephemeral=True)


class _HostDealBtn(discord.ui.Button):
    def __init__(self, guild_id: int, emoji=None):
        super().__init__(
            label='Раздать роли', style=discord.ButtonStyle.primary,
            emoji=emoji or '🎭')
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        game = STORE.get(self.guild_id)
        if not game or interaction.user.id != game.host_id:
            await interaction.response.send_message('Только ведущий.', ephemeral=True)
            return
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        await interaction.response.defer(ephemeral=True)
        try:
            await cog.deal_roles(interaction, game)
        except Exception as e:
            await interaction.followup.send(str(e), ephemeral=True)


class _HostCancelBtn(discord.ui.Button):
    def __init__(self, guild_id: int, emoji=None):
        super().__init__(
            label='Отменить', style=discord.ButtonStyle.danger,
            emoji=emoji or '🗑️')
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        game = STORE.get(self.guild_id)
        if not game or interaction.user.id != game.host_id:
            await interaction.response.send_message('Только ведущий.', ephemeral=True)
            return
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        game.cancel()
        STORE.clear(game.guild_id, archive=True)
        try:
            await cog.refresh_lobby_message(game, closed=True)
        except Exception:
            pass
        await interaction.response.send_message(
            'Отменено. `/mafia` → Начать игру.', ephemeral=True)


class MafiaHostMenuLayout(discord.ui.LayoutView):
    """Эпhemeral V2-меню `/mafia` — как модпанель."""

    def __init__(self, cog: 'Mafia', guild_id: int, user_id: int, game: Game | None):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = int(guild_id)
        self.user_id = int(user_id)
        self._banner_name = 'hakumo_events_banner_v15.png'
        self._banner_file = None
        self._rebuild(game)

    def _rebuild(self, game: Game | None):
        self.clear_items()
        from services.mafia.ui_v2 import (
            V2_AVAILABLE, SHOW_MENU_BANNER, menu_status_md, build_mafia_menu_items,
            mafia_banner_file,
        )
        select = MafiaActionSelect()
        # bind owner
        row = discord.ui.ActionRow()
        row.add_item(select)
        body = menu_status_md(game, self.user_id)
        banner = self._banner_name if SHOW_MENU_BANNER else None
        if V2_AVAILABLE:
            items = build_mafia_menu_items(
                body=body, select_row=row, banner_filename=banner)
            if items:
                for it in items:
                    self.add_item(it)
                return
        self.add_item(row)

    def make_banner(self):
        from services.mafia.ui_v2 import mafia_banner_file
        self._banner_file, name = mafia_banner_file()
        if name:
            self._banner_name = name
        return self._banner_file


# совместимость
LobbyView = PublicLobbyView


class HostPanelView(discord.ui.View):
    """Панель ведущего. Persistent + стикеры Hakumo."""

    def __init__(self):
        super().__init__(timeout=None)
        try:
            from services.mafia.ui_v2 import sticker
            mapping = {
                'pending': 'pending', 'remind': 'remind', 'redeal': 'deal',
                'start': 'play', 'kill': 'kill', 'vote': 'vote',
                'sheriff': 'sheriff', 'don': 'don', 'exclude': 'exclude',
                'cancel_game': 'cancel',
            }
            for attr, kind in mapping.items():
                btn = getattr(self, attr, None)
                if btn is not None:
                    btn.emoji = sticker(kind)
        except Exception:
            pass

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
        self.bot.add_view(HostPanelView())
        # persistent join/leave (custom_id) — через legacy View-регистрацию
        self.bot.add_view(PublicLobbyView(0))
        for game in list(STORE._by_guild.values()):
            if game.deal_token:
                for uid in game.players:
                    self.bot.add_view(make_confirm_view(game, uid))
        try:
            from services.menu_emojis import schedule_ensure_menu_emojis
            schedule_ensure_menu_emojis(self.bot)
        except Exception:
            pass
        log.info('Mafia: восстановлено активных игр: %s', n)

    def _make_lobby_view(self, game: Game):
        try:
            from services.v2_layouts import V2_AVAILABLE
            if V2_AVAILABLE:
                return MafiaLobbyLayout(game)
        except Exception:
            pass
        return PublicLobbyView(game.guild_id)

    async def lobby_message_kwargs(self, game: Game, *, with_banner: bool = True) -> dict:
        """Публичное лобби V2 (баннер + Участвовать)."""
        view = self._make_lobby_view(game)
        try:
            from services.v2_layouts import V2_AVAILABLE
            if V2_AVAILABLE and isinstance(view, discord.ui.LayoutView):
                kw = {'view': view, 'embed': None, 'content': None}
                if with_banner:
                    from services.mafia.ui_v2 import mafia_banner_file
                    file, _ = mafia_banner_file()
                    if file is not None:
                        kw['file'] = file
                return kw
        except Exception as ex:
            log.debug('lobby v2 kw: %s', ex)
        return {'embed': lobby_embed(game), 'view': PublicLobbyView(game.guild_id)}

    async def lobby_edit_kwargs(self, game: Game) -> dict:
        """Edit публичной карточки — только view= (как модпанель)."""
        view = self._make_lobby_view(game)
        try:
            from services.v2_layouts import V2_AVAILABLE
            if V2_AVAILABLE and isinstance(view, discord.ui.LayoutView):
                return {'view': view}
        except Exception:
            pass
        return {'embed': lobby_embed(game), 'view': PublicLobbyView(game.guild_id)}

    async def refresh_lobby_message(self, game: Game, *, closed: bool = False):
        if not game.lobby_message_id:
            return
        try:
            ch = self.bot.get_channel(int(game.text_channel_id))
            if ch is None:
                ch = await self.bot.fetch_channel(int(game.text_channel_id))
            msg = await ch.fetch_message(int(game.lobby_message_id))
            if closed:
                await msg.edit(
                    content=None,
                    embed=discord.Embed(
                        title='Мафия',
                        description='Лобби закрыто.\n-# `/mafia` → Начать игру',
                        color=DARK,
                    ),
                    view=None,
                )
            else:
                await msg.edit(**await self.lobby_edit_kwargs(game))
        except Exception as e:
            log.debug('refresh_lobby_message: %s', e)

    async def voice_members(self, guild: discord.Guild, voice_id: int, host_id: int):
        """Только живые люди сейчас в этом войсе (без ботов и ведущего)."""
        voice_id = int(voice_id)
        host_id = int(host_id)
        ch = guild.get_channel(voice_id)
        if ch is None:
            try:
                ch = await guild.fetch_channel(voice_id)
            except Exception:
                ch = None
        if ch is None or not isinstance(ch, discord.VoiceChannel):
            raise RuntimeError('Голосовой канал не найден')

        out = []
        seen = set()

        def _add(member: discord.Member) -> None:
            if member is None or member.bot:
                return
            if int(member.id) == host_id:
                return
            vs = member.voice
            if vs is None or vs.channel is None or int(vs.channel.id) != voice_id:
                return
            if member.id in seen:
                return
            seen.add(member.id)
            out.append((member.id, member.display_name))

        # 1) кэш канала
        for m in list(ch.members):
            _add(m)
        # 2) voice_states гильдии — надёжнее, если кэш members устарел
        try:
            for uid, vs in (guild.voice_states or {}).items():
                if vs is None or vs.channel is None:
                    continue
                if int(vs.channel.id) != voice_id:
                    continue
                if int(uid) in seen or int(uid) == host_id:
                    continue
                member = guild.get_member(int(uid))
                if member is None:
                    continue
                _add(member)
        except Exception:
            pass
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

    # ── slash: одна /mafia → выпадающее меню ─────────────────

    @app_commands.command(name='mafia', description='Мафия — меню ведущего')
    async def mafia(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message('Только на сервере.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            from services.menu_emojis import schedule_ensure_menu_emojis
            schedule_ensure_menu_emojis(self.bot)
        except Exception:
            pass
        game = STORE.get(interaction.guild.id)
        try:
            from services.v2_layouts import V2_AVAILABLE
            if V2_AVAILABLE:
                view = MafiaHostMenuLayout(
                    self, interaction.guild.id, interaction.user.id, game)
                banner = view.make_banner()
                edit_kw = {'view': view, 'content': None, 'embed': None, 'embeds': []}
                if banner is not None:
                    edit_kw['attachments'] = [banner]
                else:
                    edit_kw['attachments'] = []
                await interaction.edit_original_response(**edit_kw)
                return
        except Exception as ex:
            log.debug('mafia menu v2: %s', ex)
        embed = menu_embed(game, interaction.user.id)
        view = MafiaMenuView(self, interaction.guild.id, interaction.user.id)
        await interaction.edit_original_response(embed=embed, view=view)

    async def action_start(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message('Только на сервере.', ephemeral=True)
            return
        existing = STORE.get(interaction.guild.id)
        if existing and existing.phase != PHASE_ENDED:
            await interaction.response.send_message(
                f'Уже есть игра **#{existing.game_id}** ({_phase_label(existing.phase)}). '
                'Сначала «Отменить игру» в меню `/mafia`.',
                ephemeral=True,
            )
            return
        voice = getattr(getattr(interaction.user, 'voice', None), 'channel', None)
        if voice is None or not isinstance(voice, discord.VoiceChannel):
            await interaction.response.send_message(
                'Зайдите в голосовой канал, затем снова «Начать игру».',
                ephemeral=True,
            )
            return
        # Пустой набор — участники записываются кнопкой (не чужой войс)
        game = await self._publish_lobby(
            interaction, voice_id=voice.id, members=[])
        try:
            await interaction.followup.send(
                content=(
                    f'**#{game.game_id}** · <#{voice.id}>\n'
                    f'-# Игроки жмут Участвовать · вам — кнопки ниже'
                ),
                view=HostToolsView(interaction.guild.id),
                ephemeral=True,
            )
        except Exception as e:
            log.debug('host tools followup: %s', e)

    async def _publish_lobby(self, interaction: discord.Interaction, *,
                             voice_id: int, members: list) -> Game:
        game = Game.create(
            guild_id=interaction.guild.id,
            host_id=interaction.user.id,
            voice_channel_id=voice_id,
            text_channel_id=interaction.channel_id,
            members=members,
        )
        STORE.set(game)
        kw = await self.lobby_message_kwargs(game)
        await interaction.response.send_message(**kw)
        msg = await interaction.original_response()
        game.lobby_message_id = msg.id
        STORE.persist(game)
        return game

    async def action_deal(self, interaction: discord.Interaction) -> None:
        game = STORE.get(interaction.guild.id) if interaction.guild else None
        if not game or interaction.user.id != game.host_id:
            await interaction.response.send_message('Только ведущий активной игры.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self.deal_roles(interaction, game)
        except Exception as e:
            await interaction.followup.send(f'Не вышло раздать: {e}', ephemeral=True)

    async def action_sync_voice(self, interaction: discord.Interaction) -> None:
        game = STORE.get(interaction.guild.id) if interaction.guild else None
        if not game or interaction.user.id != game.host_id:
            await interaction.response.send_message('Только ведущий активной игры.', ephemeral=True)
            return
        if game.phase != PHASE_LOBBY:
            await interaction.response.send_message('Синхрон только в лобби (до раздачи).', ephemeral=True)
            return
        host_voice = getattr(getattr(interaction.user, 'voice', None), 'channel', None)
        if host_voice is None or int(host_voice.id) != int(game.voice_channel_id):
            await interaction.response.send_message(
                f'Зайдите в <#{game.voice_channel_id}>, затем снова.',
                ephemeral=True,
            )
            return
        try:
            members = await self.voice_members(
                interaction.guild, game.voice_channel_id, game.host_id)
            game.set_players_from_voice(members)
            STORE.persist(game)
            await self.refresh_lobby_message(game)
        except Exception as e:
            await interaction.response.send_message(f'Не вышло: {e}', ephemeral=True)
            return
        await interaction.response.send_message(
            f'Состав из войса: **{len(game.players)}**.', ephemeral=True)

    async def action_status(self, interaction: discord.Interaction) -> None:
        game = STORE.get(interaction.guild.id) if interaction.guild else None
        if not game:
            await interaction.response.send_message('Активной игры нет.', ephemeral=True)
            return
        await interaction.response.send_message(embed=public_status_embed(game), ephemeral=True)

    async def action_panel(self, interaction: discord.Interaction) -> None:
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

    async def action_resend(self, interaction: discord.Interaction, player: discord.Member) -> None:
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

    async def action_add(self, interaction: discord.Interaction, player: discord.Member) -> None:
        game = STORE.get(interaction.guild.id) if interaction.guild else None
        if not game or interaction.user.id != game.host_id:
            await interaction.response.send_message('Только ведущий.', ephemeral=True)
            return
        try:
            game.add_player(player.id, player.display_name, allow_reset=True)
            STORE.persist(game)
            await interaction.response.send_message(
                f'Добавлен {player.mention}.', ephemeral=True)
            await self.refresh_lobby_message(game)
            await self.refresh_host_summary(game)
        except Exception as e:
            await interaction.response.send_message(str(e), ephemeral=True)

    async def action_cancel(self, interaction: discord.Interaction) -> None:
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
        await self.refresh_lobby_message(game, closed=True)

    async def action_presets(self, interaction: discord.Interaction) -> None:
        lines = []
        for n in (6, 7, 8, 9, 10, 11, 12, 14):
            try:
                lines.append(f'**{n}** — {preset_summary(n)}')
            except Exception:
                pass
        e = discord.Embed(title='Пресеты мафии', description='\n'.join(lines), color=GOLD)
        await interaction.response.send_message(embed=e, ephemeral=True)


def menu_embed(game: Game | None, user_id: int) -> discord.Embed:
    """Фолбек эмбед меню."""
    from services.mafia.ui_v2 import menu_status_md
    e = discord.Embed(
        title='Мафия',
        description=menu_status_md(game, user_id),
        color=BLACK if game is None else GOLD,
    )
    e.set_footer(text='Hakumo · ведущий')
    return e


class MafiaMenuView(discord.ui.View):
    """Главное меню /mafia — одно select вместо кучи подкоманд."""

    def __init__(self, cog: 'Mafia', guild_id: int, user_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.add_item(MafiaActionSelect())


class MafiaActionSelect(discord.ui.Select):
    def __init__(self):
        try:
            from services.mafia.ui_v2 import sticker
            e_start = sticker('play')
            e_deal = sticker('deal')
            e_sync = sticker('refresh')
            e_status = sticker('elist')
            e_panel = sticker('remind')
            e_resend = sticker('deal')
            e_add = sticker('signup')
            e_cancel = sticker('cancel')
            e_presets = sticker('courtesan')
        except Exception:
            e_start = e_deal = e_sync = e_status = e_panel = e_resend = e_add = e_cancel = e_presets = None
        options = [
            discord.SelectOption(
                label='Начать игру', value='start', emoji=e_start or '▶',
                description='Карточка набора в канал'),
            discord.SelectOption(
                label='Раздать роли', value='deal', emoji=e_deal or '🎭',
                description='ЛС · минимум 6'),
            discord.SelectOption(
                label='Синхр. из войса', value='sync', emoji=e_sync or '🔄',
                description='Состав = кто в войсе'),
            discord.SelectOption(
                label='Статус', value='status', emoji=e_status or '📊',
                description='Фаза и состав'),
            discord.SelectOption(
                label='Сводка ведущему', value='panel', emoji=e_panel or '📋',
                description='Панель ролей в ЛС'),
            discord.SelectOption(
                label='Переслать роль', value='resend', emoji=e_resend or '📨',
                description='Повтор ЛС с ролью'),
            discord.SelectOption(
                label='Добавить игрока', value='add', emoji=e_add or '➕',
                description='Вручную в состав'),
            discord.SelectOption(
                label='Отменить игру', value='cancel', emoji=e_cancel or '🗑️',
                description='Сбросить партию'),
            discord.SelectOption(
                label='Пресеты ролей', value='presets', emoji=e_presets or '💋',
                description='Мафия · путана · …'),
        ]
        super().__init__(
            placeholder='Выберите действие…',
            min_values=1,
            max_values=1,
            options=options,
            custom_id='mafia:menu:action',
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        owner = getattr(view, 'user_id', None)
        cog = getattr(view, 'cog', None)
        if owner is not None and interaction.user.id != owner:
            await interaction.response.send_message('Это чужое меню.', ephemeral=True)
            return
        if cog is None:
            await interaction.response.send_message('Меню недоступно.', ephemeral=True)
            return
        action = self.values[0]
        if action == 'start':
            await cog.action_start(interaction)
        elif action == 'deal':
            await cog.action_deal(interaction)
        elif action == 'sync':
            await cog.action_sync_voice(interaction)
        elif action == 'status':
            await cog.action_status(interaction)
        elif action == 'panel':
            await cog.action_panel(interaction)
        elif action == 'presets':
            await cog.action_presets(interaction)
        elif action == 'cancel':
            await cog.action_cancel(interaction)
        elif action == 'resend':
            game = STORE.get(view.guild_id)
            if not game or interaction.user.id != game.host_id:
                await interaction.response.send_message(
                    'Только ведущий.', ephemeral=True)
                return
            if not game.players:
                await interaction.response.send_message('Состав пуст.', ephemeral=True)
                return
            await interaction.response.send_message(
                'Кому переслать роль?',
                view=MafiaUserPickView(cog, view.guild_id, mode='resend'),
                ephemeral=True,
            )
        elif action == 'add':
            game = STORE.get(view.guild_id)
            if not game or interaction.user.id != game.host_id:
                await interaction.response.send_message(
                    'Только ведущий.', ephemeral=True)
                return
            await interaction.response.send_message(
                'Кого добавить?',
                view=MafiaUserPickView(cog, view.guild_id, mode='add'),
                ephemeral=True,
            )


class MafiaUserPickView(discord.ui.View):
    """UserSelect для resend / add из меню."""

    def __init__(self, cog: 'Mafia', guild_id: int, mode: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id
        self.mode = mode
        self.picker = discord.ui.UserSelect(
            placeholder='Выберите игрока…',
            min_values=1,
            max_values=1,
        )
        self.picker.callback = self._on_pick  # type: ignore
        self.add_item(self.picker)

    async def _on_pick(self, interaction: discord.Interaction):
        if not self.picker.values:
            await interaction.response.send_message('Никого не выбрали.', ephemeral=True)
            return
        member = self.picker.values[0]
        if self.mode == 'resend':
            await self.cog.action_resend(interaction, member)  # type: ignore
        else:
            await self.cog.action_add(interaction, member)  # type: ignore


async def setup(bot: commands.Bot):
    from config import Config
    guilds = Config.guild_objects()
    if guilds:
        await bot.add_cog(Mafia(bot), guilds=guilds)
    else:
        await bot.add_cog(Mafia(bot))
