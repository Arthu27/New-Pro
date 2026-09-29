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
    CYCLE_DAY,
    CYCLE_NIGHT,
    CYCLE_NONE,
    CYCLE_VOTE,
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
    if game.phase == PHASE_PLAYING and game.cycle:
        desc = f'**{game.cycle_label()}** · авто-цикл'
        if game.cycle == CYCLE_NIGHT:
            left = len(game.night_pending())
            desc += f'\nНочные ходы: **{len(game.night_actions)}/{len(game.night_actors_needed())}**'
            if left:
                desc += f' · ждут {left}'
        elif game.cycle == CYCLE_VOTE:
            desc += (
                f'\nГолоса: **{len(game.votes)}/{len(game.alive_players())}**'
                ' · без детализации «кто за кого»'
            )
        elif game.cycle == CYCLE_DAY:
            desc += '\nОбсуждение · дальше — голосование'
    else:
        desc = (
            f'**{_phase_label(game.phase)}** · '
            f'{conf}/{total} подтвердили'
        )
    e = discord.Embed(
        title=f'🤍 Сводка · #{game.game_id}',
        description=desc,
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
        dm = '' if p.dm_ok else ' · DM∅'
        lines.append(f'{mark} {_mention(p.user_id)} — {role}{alive}{dm}')
    e.add_field(name='Стол', value='\n'.join(lines)[:1020] or '—', inline=False)
    if game.last_night_report:
        e.add_field(name='Прошлая ночь', value=game.last_night_report[:500], inline=False)
    if game.last_vote_report:
        e.add_field(name='Прошлое голосование', value=game.last_vote_report[:500], inline=False)
    if game.winner:
        label = 'Город победил' if game.winner == 'town' else 'Мафия победила'
        e.add_field(name='Финал', value=label, inline=False)
    if game.log:
        e.add_field(name='Лог', value='\n'.join(game.log[-5:])[:1020], inline=False)
    e.set_footer(text='Ведущему · роли ходят сами в ЛС')
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
    e.set_footer(text='Секретно · подтвердите · ночью ход придёт сюда же')
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
        cycle = game.cycle_label() or 'игра'
        if game.cycle == CYCLE_NIGHT:
            tip = 'Город спит · в войсе мут · роли ходят в ЛС'
        elif game.cycle == CYCLE_DAY:
            tip = 'Обсуждение в войсе'
        elif game.cycle == CYCLE_VOTE:
            tip = 'Голосование в ЛС у живых'
        else:
            tip = 'Авто-цикл'
        e.description = (
            f'**{cycle}** · в живых: **{alive}**\n'
            f'{tip}\n'
            f'Выбыли: {dead_txt}'
        )
        e.color = RED
        if game.last_night_report and game.cycle in (CYCLE_DAY, CYCLE_VOTE):
            e.add_field(name='Ночь', value=game.last_night_report[:500], inline=False)
        if game.last_vote_report and game.cycle == CYCLE_NIGHT and game.day_number > 1:
            e.add_field(name='Голосование', value=game.last_vote_report[:500], inline=False)
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
        # 🤍 как у демок/анкет — чёрная карточка, без классических эмодзи
        super().__init__(
            label='Участвовать', style=discord.ButtonStyle.secondary,
            emoji='🤍', custom_id='mafia:public:join')

    async def callback(self, interaction: discord.Interaction):
        await _public_join(interaction)


class _LeaveBtn(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label='Выйти', style=discord.ButtonStyle.secondary,
            emoji='🤍', custom_id='mafia:public:leave')

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
    """Панель ведущего v2: мало кнопок, цикл авто.

    До старта: Напомнить · Перераздать · Начать · Отменить
    В игре: Дальше (фаза) · Отменить
    Убийство/шериф/дон/голос — у ролей в ЛС, не у ведущего.
    """

    def __init__(self):
        super().__init__(timeout=None)
        for btn in self.children:
            if getattr(btn, 'emoji', None) is None and hasattr(btn, 'emoji'):
                try:
                    btn.emoji = '🤍'
                except Exception:
                    pass

    async def _host(self, interaction: discord.Interaction) -> Game | None:
        game = None
        if interaction.guild_id:
            game = STORE.get(interaction.guild_id)
        if game is None:
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

    @discord.ui.button(label='Напомнить', style=discord.ButtonStyle.secondary, emoji='🤍',
                       custom_id='mafia:host:remind', row=0)
    async def remind(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._host(interaction)
        if not game:
            return
        if game.phase == PHASE_PLAYING:
            await interaction.response.send_message(
                'Игра уже идёт — роли ходят сами в ЛС.', ephemeral=True)
            return
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        await interaction.response.defer(ephemeral=True)
        n = await cog.remind_unconfirmed(game)
        pending = game.unconfirmed()
        extra = ''
        if pending:
            extra = '\nЖдут: ' + ', '.join(_mention(p.user_id) for p in pending[:12])
        await interaction.followup.send(
            f'Напомнил {n}.{extra}', ephemeral=True)

    @discord.ui.button(label='Перераздать', style=discord.ButtonStyle.secondary, emoji='🤍',
                       custom_id='mafia:host:redeal', row=0)
    async def redeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._host(interaction)
        if not game:
            return
        if game.phase == PHASE_PLAYING:
            await interaction.response.send_message(
                'Во время игры нельзя.', ephemeral=True)
            return
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        await interaction.response.defer(ephemeral=True)
        try:
            await cog.deal_roles(interaction, game)
            await interaction.followup.send(
                'Роли переразданы.', ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f'Ошибка: {e}', ephemeral=True)

    @discord.ui.button(label='Начать / Дальше', style=discord.ButtonStyle.primary, emoji='🤍',
                       custom_id='mafia:host:advance', row=1)
    async def advance(self, interaction: discord.Interaction, button: discord.ui.Button):
        """До игры — старт (ночь 1). В игре — следующая фаза."""
        game = await self._host(interaction)
        if not game:
            return
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        await interaction.response.defer(ephemeral=True)
        try:
            if game.phase != PHASE_PLAYING:
                game.start()
                STORE.persist(game)
                await cog.on_night_started(game)
                await interaction.followup.send(
                    f'Игра началась · **Ночь {game.day_number}** · город спит, войс на муте.',
                    ephemeral=True)
                return
            msg = await cog.advance_cycle(game, force=True)
            await interaction.followup.send(msg or 'Фаза сдвинута.', ephemeral=True)
        except Exception as e:
            await interaction.followup.send(str(e), ephemeral=True)

    @discord.ui.button(label='Отменить игру', style=discord.ButtonStyle.danger, emoji='🤍',
                       custom_id='mafia:host:cancel', row=1)
    async def cancel_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = await self._host(interaction)
        if not game:
            return
        gid = game.guild_id
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        await interaction.response.defer(ephemeral=True)
        try:
            await cog.clear_voice_mutes(game)
        except Exception:
            pass
        game.cancel()
        STORE.clear(gid, archive=True)
        try:
            await cog.refresh_public(game)
            await cog.refresh_lobby_message(game, closed=True)
        except Exception:
            pass
        await interaction.followup.send(f'Игра #{game.game_id} отменена · муты сняты.', ephemeral=True)


def _alive_options(game: Game, *, exclude_id: int = 0) -> list:
    opts = []
    for p in game.alive_players()[:24]:
        if exclude_id and int(p.user_id) == int(exclude_id):
            continue
        opts.append(discord.SelectOption(
            label=p.display_name[:100],
            value=str(p.user_id),
            emoji='🤍',
        ))
    return opts


class NightActionView(discord.ui.View):
    """Ночной ход роли в ЛС — select, без кнопок ведущего."""

    def __init__(self, guild_id: int, actor_id: int, kind: str):
        super().__init__(timeout=600)
        self.guild_id = int(guild_id)
        self.actor_id = int(actor_id)
        self.kind = kind  # kill|heal|block|sheriff|don
        game = STORE.get(self.guild_id)
        options = _alive_options(game, exclude_id=actor_id) if game else []
        options.append(discord.SelectOption(
            label='› Пас', value='0', emoji='🤍',
            description='Пропустить ход'))
        ph = {
            'kill': 'Кого убиваем?',
            'heal': 'Кого лечим?',
            'block': 'Кого блокируем?',
            'sheriff': 'Кого проверить?',
            'don': 'Кого проверить (шериф?)',
        }.get(kind, 'Выберите…')
        sel = discord.ui.Select(
            placeholder=ph, min_values=1, max_values=1,
            options=options[:25],
        )
        sel.callback = self._on_pick  # type: ignore
        self.add_item(sel)

    async def _on_pick(self, interaction: discord.Interaction):
        if int(interaction.user.id) != self.actor_id:
            await interaction.response.send_message('Это не ваш ход.', ephemeral=True)
            return
        game = STORE.get(self.guild_id)
        if not game or game.cycle != CYCLE_NIGHT:
            await interaction.response.send_message('Ночь уже закончилась.', ephemeral=True)
            return
        raw = (self.children[0].values or ['0'])[0]  # type: ignore
        tid = int(raw)
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        try:
            # пас на проверке дона ≠ пас на убийстве
            if tid == 0 and self.kind == 'don':
                kind, tid = 'don', 0
            elif tid == 0:
                kind = 'skip'
            else:
                kind = self.kind
            rec = game.submit_night_action(
                self.actor_id, kind, None if tid == 0 else tid)
            STORE.persist(game)
            msg = 'Ход принят.'
            if rec.get('result'):
                r = rec['result']
                msg = f'Результат: **{r.get("result")}**\n{r.get("detail", "")}'
            elif kind == 'skip':
                msg = 'Пас · ждёте итог ночи.'
            await interaction.response.edit_message(content=msg, view=None, embed=None)
            await cog.refresh_host_summary(game)
            if game.night_ready():
                await cog.advance_cycle(game, force=False)
        except Exception as e:
            if interaction.response.is_done():
                await interaction.followup.send(str(e), ephemeral=True)
            else:
                await interaction.response.send_message(str(e), ephemeral=True)


class VoteSelectView(discord.ui.View):
    """Дневное голосование в ЛС — без показа «кто за кого» ведущему."""

    def __init__(self, guild_id: int, voter_id: int):
        super().__init__(timeout=600)
        self.guild_id = int(guild_id)
        self.voter_id = int(voter_id)
        game = STORE.get(self.guild_id)
        options = _alive_options(game, exclude_id=voter_id) if game else []
        options.append(discord.SelectOption(
            label='› Воздержаться', value='0', emoji='🤍'))
        sel = discord.ui.Select(
            placeholder='Кого изгоняем?',
            min_values=1, max_values=1, options=options[:25],
        )
        sel.callback = self._on_pick  # type: ignore
        self.add_item(sel)

    async def _on_pick(self, interaction: discord.Interaction):
        if int(interaction.user.id) != self.voter_id:
            await interaction.response.send_message('Чужой голос.', ephemeral=True)
            return
        game = STORE.get(self.guild_id)
        if not game or game.cycle != CYCLE_VOTE:
            await interaction.response.send_message('Голосование закрыто.', ephemeral=True)
            return
        raw = (self.children[0].values or ['0'])[0]  # type: ignore
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        try:
            game.submit_vote(self.voter_id, int(raw))
            STORE.persist(game)
            await interaction.response.edit_message(
                content='Голос принят · итог без раскрытия «кто за кого».',
                view=None, embed=None)
            await cog.refresh_host_summary(game)
            if game.vote_ready():
                await cog.advance_cycle(game, force=False)
        except Exception as e:
            if interaction.response.is_done():
                await interaction.followup.send(str(e), ephemeral=True)
            else:
                await interaction.response.send_message(str(e), ephemeral=True)


# совместимость со старыми вызовами
class PlayerSelectView(discord.ui.View):
    """Устарело: ручные ходы ведущего убраны. Оставлен exclude до старта."""

    def __init__(self, guild_id: int, mode: str, alive_only: bool = True):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.mode = mode
        game = STORE.get(guild_id)
        options = []
        if game:
            pool = game.alive_players() if alive_only else list(game.players.values())
            for p in pool[:25]:
                options.append(discord.SelectOption(
                    label=p.display_name[:100], value=str(p.user_id), emoji='🤍'))
        sel = discord.ui.Select(
            placeholder='Выберите…',
            options=options or [discord.SelectOption(label='Нет', value='0')],
            min_values=1, max_values=1)
        sel.callback = self._on_select  # type: ignore
        self.add_item(sel)

    async def _on_select(self, interaction: discord.Interaction):
        game = STORE.get(self.guild_id)
        if not game or interaction.user.id != game.host_id:
            await interaction.response.send_message('Нет доступа.', ephemeral=True)
            return
        uid = int((self.children[0].values or ['0'])[0])  # type: ignore
        if self.mode != 'exclude' or uid == 0:
            await interaction.response.send_message(
                'Ручные ходы убраны — роли ходят в ЛС.', ephemeral=True)
            return
        try:
            p = game.exclude_player(uid)
            STORE.persist(game)
            cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
            await cog.refresh_host_summary(game)
            await interaction.response.edit_message(
                content=f'Исключён: **{p.display_name}**', view=None)
        except Exception as e:
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
                await msg.edit(**self._lobby_closed_kwargs(game))
            else:
                await msg.edit(**await self.lobby_edit_kwargs(game))
        except Exception as e:
            log.debug('refresh_lobby_message: %s', e)

    def _lobby_closed_kwargs(self, game: Game) -> dict:
        """Закрытое лобби — как закрытая демка: ЗАКРЫТО, без кнопок/select."""
        try:
            from services.v2_layouts import V2_AVAILABLE
            from services.mafia.ui_v2 import build_mafia_closed_items
            if V2_AVAILABLE:
                from datetime import datetime, timezone
                when = datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')
                body = (
                    f'**Ведущий** · <@{game.host_id}>\n'
                    f'**Войс** · <#{game.voice_channel_id}>\n'
                    f'**Партия** · #{game.game_id}'
                )
                items = build_mafia_closed_items(
                    body=body,
                    note=f'Лобби закрыто · {when}\n`/mafia` → Начать игру',
                    accent=0xE74C3C,
                )
                if items:
                    view = discord.ui.LayoutView(timeout=None)
                    for it in items:
                        view.add_item(it)
                    return {'view': view, 'embed': None, 'content': None}
        except Exception as ex:
            log.debug('lobby closed v2: %s', ex)
        return {
            'content': None,
            'embed': discord.Embed(
                title='🤍 Мафия · ЗАКРЫТО',
                description='Лобби закрыто.\n-# `/mafia` → Начать игру',
                color=DARK,
            ),
            'view': None,
        }

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

    async def announce(self, game: Game, text: str):
        """Публичная фаза в канал лобби — V2 если можно, иначе embed."""
        try:
            ch = self.bot.get_channel(int(game.text_channel_id))
            if ch is None:
                ch = await self.bot.fetch_channel(int(game.text_channel_id))
            from services.v2_layouts import V2_AVAILABLE, black_container
            if V2_AVAILABLE:
                from discord import ui as dui, SeparatorSpacing
                view = dui.LayoutView(timeout=1)
                view.add_item(black_container(
                    dui.TextDisplay('# 🤍 Мафия'),
                    dui.TextDisplay(f'-# HAKUMO · {game.cycle_label() or "партия"}'),
                    dui.Separator(spacing=SeparatorSpacing.large),
                    dui.TextDisplay(str(text)[:3500]),
                    accent=0x000000,
                ))
                await ch.send(view=view)
                return
            e = discord.Embed(
                title=f'🤍 Мафия · {game.cycle_label() or game.game_id}',
                description=str(text)[:4000], color=BLACK)
            await ch.send(embed=e)
        except Exception as ex:
            log.debug('mafia announce: %s', ex)

    async def set_voice_night_mute(self, game: Game, *, night: bool) -> int:
        """Ночь: сервер-мут всем живым в войсе. День: снять с живых, мёртвые — мут."""
        guild = self.bot.get_guild(int(game.guild_id))
        if guild is None:
            return 0
        n = 0
        voice_id = int(game.voice_channel_id)
        for p in game.players.values():
            member = guild.get_member(int(p.user_id))
            if member is None:
                continue
            vs = getattr(member, 'voice', None)
            if vs is None or vs.channel is None or int(vs.channel.id) != voice_id:
                continue
            want_mute = bool(night) or (not p.alive)
            try:
                if bool(getattr(vs, 'mute', False)) == want_mute:
                    continue
                await member.edit(
                    mute=want_mute,
                    reason=('мафия: ночь — город спит' if night
                            else 'мафия: день'),
                )
                n += 1
            except Exception as ex:
                log.debug('mafia mute %s: %s', p.user_id, ex)
        return n

    async def clear_voice_mutes(self, game: Game) -> int:
        """Снять сервер-мут со всех игроков партии (отмена/конец)."""
        guild = self.bot.get_guild(int(game.guild_id))
        if guild is None:
            return 0
        n = 0
        for p in game.players.values():
            member = guild.get_member(int(p.user_id))
            if member is None:
                continue
            vs = getattr(member, 'voice', None)
            if vs is None or not getattr(vs, 'mute', False):
                continue
            try:
                await member.edit(mute=False, reason='мафия: муты сняты')
                n += 1
            except Exception as ex:
                log.debug('mafia unmute %s: %s', p.user_id, ex)
        return n

    async def send_night_action_dms(self, game: Game) -> int:
        """Разослать ночные select ролям."""
        sent = 0
        for p in game.night_actors_needed():
            kind = {
                'mafia': 'kill',
                'don': 'kill',
                'sheriff': 'sheriff',
                'doctor': 'heal',
                'courtesan': 'block',
            }.get(p.role or '')
            if not kind:
                continue
            try:
                user = self.bot.get_user(p.user_id) or await self.bot.fetch_user(p.user_id)
                role = ROLES.get(p.role)
                title = role.name if role else 'Ход'
                desc = {
                    'kill': 'Ночь · выберите жертву (или пас).',
                    'sheriff': 'Ночь · кого проверить: мафия или мирный?',
                    'heal': 'Ночь · кого лечить?',
                    'block': 'Ночь · чьё действие блокируем?',
                }.get(kind, 'Ночной ход')
                e = discord.Embed(
                    title=f'🤍 {title}',
                    description=f'{desc}\n-# #{game.game_id} · ночь {game.day_number}',
                    color=RED if role and role.team == 'mafia' else BLUE,
                )
                view = NightActionView(game.guild_id, p.user_id, kind)
                await user.send(embed=e, view=view)
                # дон: доп. проверка шерифа
                if p.role == 'don':
                    e2 = discord.Embed(
                        title='🤍 Дон · проверка',
                        description=(
                            'По желанию проверьте игрока: шериф это или нет.\n'
                            '-# Можно пас'
                        ),
                        color=RED,
                    )
                    await user.send(
                        embed=e2,
                        view=NightActionView(game.guild_id, p.user_id, 'don'),
                    )
                sent += 1
            except Exception as ex:
                game.mark_dm_failed(p.user_id)
                log.debug('night dm %s: %s', p.user_id, ex)
        STORE.persist(game)
        return sent

    async def send_vote_dms(self, game: Game) -> int:
        sent = 0
        for p in game.alive_players():
            try:
                user = self.bot.get_user(p.user_id) or await self.bot.fetch_user(p.user_id)
                e = discord.Embed(
                    title='🤍 Голосование',
                    description=(
                        f'День {game.day_number} · кого изгоняем?\n'
                        '-# Голос тайный · ведущий не видит «кто за кого»'
                    ),
                    color=GOLD,
                )
                await user.send(
                    embed=e, view=VoteSelectView(game.guild_id, p.user_id))
                sent += 1
            except Exception as ex:
                game.mark_dm_failed(p.user_id)
                log.debug('vote dm %s: %s', p.user_id, ex)
        STORE.persist(game)
        return sent

    async def on_night_started(self, game: Game):
        """После begin_night: мут + анонс + ЛС ролям."""
        await self.set_voice_night_mute(game, night=True)
        await self.announce(
            game,
            f'## 🌙 Ночь {game.day_number}\n'
            '**Город засыпает.**\n'
            'В войсе — мут. Мафия и спецроли ходят в личке с ботом.',
        )
        await self.send_night_action_dms(game)
        await self.refresh_host_summary(game)
        await self.refresh_public(game)

    async def on_day_started(self, game: Game, night_report: str = ''):
        await self.set_voice_night_mute(game, night=False)
        body = f'## ☀️ День {game.day_number}\n**Город просыпается.**\n'
        if night_report:
            body += f'\n{night_report}\n'
        body += '\nОбсуждайте в войсе. Ведущий жмёт **Начать / Дальше** → голосование.'
        await self.announce(game, body)
        await self.refresh_host_summary(game)
        await self.refresh_public(game)

    async def on_vote_started(self, game: Game):
        n = await self.send_vote_dms(game)
        await self.announce(
            game,
            f'## 🗳️ Голосование · день {game.day_number}\n'
            f'Живые получили select в ЛС (**{n}**).\n'
            '-# Итог без «кто за кого»',
        )
        await self.refresh_host_summary(game)
        await self.refresh_public(game)

    async def advance_cycle(self, game: Game, *, force: bool = False) -> str:
        """Сдвинуть фазу: ночь→день→голос→ночь. force — даже если не все сходили."""
        if game.phase != PHASE_PLAYING:
            raise RuntimeError('Игра не идёт')
        if game.cycle == CYCLE_NIGHT:
            if not force and not game.night_ready():
                left = len(game.night_pending())
                return f'Ночь ещё идёт · ждут ход: {left}'
            # дон мог прислать только check — для resolve это ок; kill optional
            report = game.resolve_night()
            STORE.persist(game)
            await self.refresh_host_summary(game)
            if game.phase == PHASE_ENDED:
                await self.clear_voice_mutes(game)
                await self.announce(
                    game,
                    f'## 🏁 Финал\n{report["report"]}\n'
                    + ('Победа **города**.' if game.winner == 'town'
                       else 'Победа **мафии**.'),
                )
                await self.refresh_public(game)
                STORE.clear(game.guild_id, archive=True)
                return 'Игра окончена.'
            game.begin_day()
            STORE.persist(game)
            await self.on_day_started(game, night_report=report['report'])
            return f'День {game.day_number} · {report["report"]}'

        if game.cycle == CYCLE_DAY:
            game.begin_vote()
            STORE.persist(game)
            await self.on_vote_started(game)
            return f'Голосование · день {game.day_number}'

        if game.cycle == CYCLE_VOTE:
            if not force and not game.vote_ready():
                left = len(game.vote_pending())
                return f'Голосование · ждут: {left}'
            report = game.resolve_vote()
            STORE.persist(game)
            await self.announce(game, f'## Итог голосования\n{report["report"]}')
            await self.refresh_host_summary(game)
            if game.phase == PHASE_ENDED:
                await self.clear_voice_mutes(game)
                await self.announce(
                    game,
                    '## 🏁 Финал\n'
                    + ('Победа **города**.' if game.winner == 'town'
                       else 'Победа **мафии**.'),
                )
                await self.refresh_public(game)
                STORE.clear(game.guild_id, archive=True)
                return 'Игра окончена.'
            game.begin_night()
            STORE.persist(game)
            await self.on_night_started(game)
            return f'Ночь {game.day_number} · город снова спит'

        raise RuntimeError('Неизвестная фаза цикла')

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
        from services.menu_banners import select_label
        try:
            from services.mafia.ui_v2 import sticker
            heart = sticker('menu') or '🤍'
        except Exception:
            heart = '🤍'
        options = [
            discord.SelectOption(
                label=select_label('Начать игру'), value='start', emoji=heart,
                description='Карточка набора в канал'),
            discord.SelectOption(
                label=select_label('Раздать роли'), value='deal', emoji=heart,
                description='ЛС · минимум 6'),
            discord.SelectOption(
                label=select_label('Синхр. из войса'), value='sync', emoji=heart,
                description='Состав = кто в войсе'),
            discord.SelectOption(
                label=select_label('Статус'), value='status', emoji=heart,
                description='Фаза и состав'),
            discord.SelectOption(
                label=select_label('Сводка ведущему'), value='panel', emoji=heart,
                description='Панель ролей в ЛС'),
            discord.SelectOption(
                label=select_label('Переслать роль'), value='resend', emoji=heart,
                description='Повтор ЛС с ролью'),
            discord.SelectOption(
                label=select_label('Добавить игрока'), value='add', emoji=heart,
                description='Вручную в состав'),
            discord.SelectOption(
                label=select_label('Отменить игру'), value='cancel', emoji=heart,
                description='Сбросить партию'),
            discord.SelectOption(
                label=select_label('Пресеты ролей'), value='presets', emoji=heart,
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
