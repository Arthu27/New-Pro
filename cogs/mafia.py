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
from services.mafia.roles import is_mafia_team

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
            desc += f'\nОчередь: **{game.night_step_label()}**'
            left = len(game.night_pending())
            if left:
                desc += f' · ждут ход: {left}'
        elif game.cycle == CYCLE_VOTE:
            desc += (
                f'\nОчередь голоса: **{game.vote_turn_label()}**'
                ' · без «кто за кого»'
            )
        elif game.cycle == CYCLE_DAY:
            desc += '\nОбсуждение · Дальше → голосование по очереди'
    elif game.phase == PHASE_ENDED:
        desc = '**Финал** · можно очистить сообщения партии'
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


def role_dm_embed(
        game: Game, player, *, invite_url: str | None = None) -> discord.Embed:
    role = ROLES[player.role]
    try:
        from services.mafia.ui_v2 import role_mark
        mark = role_mark(player.role)
    except Exception:
        mark = role.emoji
    body = (
        f'{mark} **{role.name}**\n\n'
        f'{role.description}\n'
    )
    # мафия знает семью сразу
    if is_mafia_team(player.role):
        team = game.mafia_team()
        lines = []
        for t in team:
            tr = ROLES.get(t.role)
            you = ' · **вы**' if t.user_id == player.user_id else ''
            lines.append(
                f'🤍 {_mention(t.user_id)} — {tr.name if tr else "?"}{you}')
        body += '\n**Ваша семья**\n' + '\n'.join(lines) + '\n'
        if invite_url:
            body += (
                f'\n**Сервер семьи** · ваш личный вход (1 раз):\n{invite_url}\n'
                '-# После матча выгонят. Чужих на сервере быть не должно.\n'
            )
        else:
            body += '\n-# Ночью — сервер семьи (инвайт вторым сообщением).\n'
        body += '-# Днём молчите о ролях.\n'
    body += f'\n-# #{game.game_id} · ведущий {_mention(game.host_id)}'
    e = discord.Embed(
        title=f'🤍 {role.name}',
        description=body[:4000],
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
            tip = 'Город спит · войс на муте · ходы в ЛС'
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

    async def _host(self, interaction: discord.Interaction,
                    *, allow_ended: bool = False) -> Game | None:
        game = None
        if interaction.guild_id:
            game = STORE.get(interaction.guild_id)
        if game is None:
            for g in STORE._by_guild.values():
                if g.host_id != interaction.user.id:
                    continue
                if g.phase == PHASE_ENDED and not allow_ended:
                    continue
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
        game = await self._host(interaction, allow_ended=True)
        if not game:
            return
        gid = game.guild_id
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        await interaction.response.defer(ephemeral=True)
        try:
            await cog.clear_voice_mutes(game)
        except Exception:
            pass
        try:
            await cog.evict_mafia_family(game)
        except Exception:
            pass
        if game.phase != PHASE_ENDED:
            game.cancel()
        n = 0
        try:
            n = await cog.cleanup_game_messages(game)
        except Exception:
            pass
        STORE.clear(gid, archive=True)
        await interaction.followup.send(
            f'Игра #{game.game_id} закрыта · семья выгнана · удалено: **{n}**.',
            ephemeral=True)

    @discord.ui.button(label='Очистить сообщения', style=discord.ButtonStyle.secondary, emoji='🤍',
                       custom_id='mafia:host:cleanup', row=2)
    async def cleanup_msgs(self, interaction: discord.Interaction, button: discord.ui.Button):
        """В конце катки — убрать анонсы/лобби из канала."""
        game = await self._host(interaction, allow_ended=True)
        if not game:
            return
        if game.phase not in (PHASE_ENDED, PHASE_PLAYING):
            await interaction.response.send_message(
                'Очистка после финала или отмены.', ephemeral=True)
            return
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        await interaction.response.defer(ephemeral=True)
        n = await cog.cleanup_game_messages(game)
        if game.phase == PHASE_ENDED:
            STORE.clear(game.guild_id, archive=True)
        await interaction.followup.send(
            f'Удалено сообщений партии: **{n}**.', ephemeral=True)


def _alive_options(game: Game, *, exclude_id: int = 0,
                   include_self_id: int = 0, self_label: str = None) -> list:
    opts = []
    for p in game.alive_players()[:24]:
        if exclude_id and int(p.user_id) == int(exclude_id):
            continue
        opts.append(discord.SelectOption(
            label=p.display_name[:100],
            value=str(p.user_id),
            emoji='🤍',
        ))
    if include_self_id:
        me = game.players.get(int(include_self_id))
        if me and me.alive:
            # не дублировать если уже в списке
            if not any(o.value == str(include_self_id) for o in opts):
                opts.insert(0, discord.SelectOption(
                    label=(self_label or f'Себя · {me.display_name}')[:100],
                    value=str(include_self_id),
                    emoji='🤍',
                    description='Самохил',
                ))
    return opts


class MafiaChatModal(discord.ui.Modal, title='Сообщение семье'):
    text = discord.ui.TextInput(
        label='Текст семье',
        style=discord.TextStyle.paragraph,
        max_length=400, required=True,
        placeholder='Только живая мафия увидит это в ЛС…')

    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id = int(guild_id)

    async def on_submit(self, interaction: discord.Interaction):
        game = STORE.get(self.guild_id)
        if not game or game.phase != PHASE_PLAYING:
            return await interaction.response.send_message(
                'Игра не идёт.', ephemeral=True)
        me = game.players.get(int(interaction.user.id))
        if not me or not me.alive or not me.role or not is_mafia_team(me.role):
            return await interaction.response.send_message(
                'Только живая мафия.', ephemeral=True)
        cog: Mafia = interaction.client.get_cog('mafia')  # type: ignore
        n = await cog.relay_mafia_chat(
            game, author=me, text=str(self.text.value or ''))
        await interaction.response.send_message(
            f'Отправлено семье · **{n}**', ephemeral=True)


class NightActionView(discord.ui.View):
    """Ночной ход роли в ЛС — select; у мафии ещё чат семьи."""

    def __init__(self, guild_id: int, actor_id: int, kind: str):
        super().__init__(timeout=600)
        self.guild_id = int(guild_id)
        self.actor_id = int(actor_id)
        self.kind = kind  # kill|heal|block|sheriff|don
        game = STORE.get(self.guild_id)
        options = []
        if game and kind == 'heal':
            others = _alive_options(game, exclude_id=actor_id)
            if game.can_doctor_self_heal():
                me = game.players.get(int(actor_id))
                options.append(discord.SelectOption(
                    label='💉 Себя (1× / 2 ночи)'[:100],
                    value=str(actor_id), emoji='🤍',
                    description='Самохил доступен'))
            options.extend(others)
            ph = ('Кого лечим? · себя можно' if game.can_doctor_self_heal()
                  else 'Кого лечим? · себя пока нельзя')
        else:
            options = _alive_options(game, exclude_id=actor_id) if game else []
            ph = {
                'kill': 'Кого убиваем?',
                'block': 'Кого блокируем?',
                'sheriff': 'Кого проверить?',
                'don': 'Кого проверить (шериф?)',
            }.get(kind, 'Выберите…')
        options.append(discord.SelectOption(
            label='› Пас', value='0', emoji='🤍',
            description='Пропустить ход'))
        sel = discord.ui.Select(
            placeholder=ph[:150], min_values=1, max_values=1,
            options=options[:25],
        )
        sel.callback = self._on_pick  # type: ignore
        self.add_item(sel)
        if kind == 'kill':
            btn = discord.ui.Button(
                label='Написать семье', style=discord.ButtonStyle.secondary,
                emoji='🤍')
            btn.callback = self._mafia_chat  # type: ignore
            self.add_item(btn)

    async def _mafia_chat(self, interaction: discord.Interaction):
        if int(interaction.user.id) != self.actor_id:
            return await interaction.response.send_message(
                'Это не ваш ход.', ephemeral=True)
        await interaction.response.send_modal(MafiaChatModal(self.guild_id))

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
            await cog.after_night_action(game)
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
                content='Голос принят · ждите остальных по очереди.',
                view=None, embed=None)
            await cog.after_vote_action(game)
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
        self._family_guard_task = None

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
        if self._family_guard_task is None or self._family_guard_task.done():
            self._family_guard_task = self.bot.loop.create_task(
                self._family_guard_loop(), name='mafia-family-guard')
        log.info('Mafia: восстановлено активных игр: %s', n)

    async def cog_unload(self):
        t = self._family_guard_task
        if t is not None and not t.done():
            t.cancel()

    async def _family_guard_loop(self) -> None:
        """Пока идёт партия — выгонять чужих с сервера семьи (без Members Intent)."""
        await self.bot.wait_until_ready()
        from services.mafia.family_guild import purge_strangers
        while not self.bot.is_closed():
            try:
                active = any(
                    getattr(g, 'mafia_family_ids', None)
                    and g.phase in (PHASE_CONFIRM, PHASE_READY, PHASE_PLAYING)
                    for g in list(STORE._by_guild.values())
                )
                if active:
                    n = await purge_strangers(self.bot)
                    if n:
                        log.info('mafia family guard: выгнано чужих %s', n)
            except Exception as ex:
                log.debug('family guard: %s', ex)
            await discord.utils.sleep_until(
                discord.utils.utcnow() + __import__('datetime').timedelta(seconds=20)
            )

    @commands.Cog.listener()
    async def on_voice_state_update(
            self,
            member: discord.Member,
            before: discord.VoiceState,
            after: discord.VoiceState,
    ) -> None:
        """Ночью снова мутим, если кто-то зашёл в войс или снял мут."""
        if member is None or member.bot or member.guild is None:
            return
        game = STORE.get(member.guild.id)
        if game is None or game.phase != PHASE_PLAYING:
            return
        voice_id = int(game.voice_channel_id)
        if game.cycle != CYCLE_NIGHT:
            return
        in_game_voice = (
            after.channel is not None and int(after.channel.id) == voice_id
        )
        if not in_game_voice:
            return
        await self._apply_voice_mute_member(
            game, member, night=True,
            reason='мафия: ночь — войс на муте',
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """На сервер семьи — только текущая мафия; чужих выгоняем."""
        if member is None or member.bot or member.guild is None:
            return
        from services.mafia.family_guild import family_guild_id, kick_if_not_mafia
        if int(member.guild.id) != family_guild_id():
            return
        await kick_if_not_mafia(self.bot, member)

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
        # 2) voice_states гильдии (если атрибут есть — у fetch_guild его нет)
        for uid, vs in self._iter_guild_voice_states(guild):
            if vs is None or getattr(vs, 'channel', None) is None:
                continue
            if int(vs.channel.id) != voice_id:
                continue
            if uid in seen or uid == host_id:
                continue
            member = guild.get_member(uid)
            if member is None:
                continue
            _add(member)
        return out

    def _iter_guild_voice_states(self, guild: discord.Guild):
        """Безопасно: у fetch_guild / части Guild нет .voice_states."""
        states = getattr(guild, 'voice_states', None)
        if states is None:
            states = getattr(guild, '_voice_states', None)
        if not states:
            return
        try:
            items = states.items()
        except Exception:
            return
        for uid, vs in items:
            yield int(uid), vs

    async def _members_in_voice_channel(
            self, guild: discord.Guild, voice_id: int) -> list[discord.Member]:
        """Кто в войсе: channel.members + voice_states (если есть) + fetch."""
        voice_id = int(voice_id)
        ch = guild.get_channel(voice_id)
        if ch is None:
            try:
                ch = await guild.fetch_channel(voice_id)
            except Exception:
                ch = None
        if ch is None or not isinstance(ch, discord.VoiceChannel):
            return []

        out: dict[int, discord.Member] = {}
        for m in list(getattr(ch, 'members', None) or []):
            if m is not None and not m.bot:
                out[int(m.id)] = m
        for uid, vs in self._iter_guild_voice_states(guild):
            if vs is None or getattr(vs, 'channel', None) is None:
                continue
            if int(vs.channel.id) != voice_id:
                continue
            if uid in out:
                continue
            member = guild.get_member(uid)
            if member is None:
                try:
                    member = await guild.fetch_member(uid)
                except Exception:
                    continue
            if member is not None and not member.bot:
                out[uid] = member
        return list(out.values())

    def _voice_mute_wanted(
            self, game: Game, user_id: int, *, night: bool) -> bool | None:
        """None — не менять server-mute. True/False — целевое состояние."""
        uid = int(user_id)
        if uid == int(game.host_id):
            return None
        p = game.players.get(uid)
        if p is not None:
            if not p.alive:
                return True
            return bool(night)
        if night:
            return True
        return None

    async def _apply_voice_mute_member(
            self,
            game: Game,
            member: discord.Member,
            *,
            night: bool,
            reason: str,
    ) -> bool:
        voice_id = int(game.voice_channel_id)
        vs = getattr(member, 'voice', None)
        if vs is None and member.guild is not None:
            for uid, state in self._iter_guild_voice_states(member.guild):
                if uid == int(member.id):
                    vs = state
                    break
        if vs is None or vs.channel is None or int(vs.channel.id) != voice_id:
            return False
        want = self._voice_mute_wanted(game, member.id, night=night)
        if want is None:
            return False
        if bool(getattr(vs, 'mute', False)) == want:
            return False
        try:
            await member.edit(mute=want, reason=reason)
            return True
        except discord.Forbidden:
            log.warning(
                'mafia mute %s: нет Mute Members (бот %s)',
                member.id, getattr(getattr(self.bot, 'user', None), 'id', '?'))
        except Exception as ex:
            log.warning('mafia mute %s: %s', member.id, ex)
        return False

    async def deal_roles(self, interaction: discord.Interaction, game: Game):
        counts = game.deal()
        STORE.persist(game)
        # сначала инвайты для ВСЕЙ семьи (с паузами/ретраями)
        invites: dict = {}
        try:
            from services.mafia.family_guild import create_invites_for_team
            invites = await create_invites_for_team(self.bot, game)
            STORE.persist(game)
        except Exception as ex:
            log.warning('mafia create invites: %s', ex)

        sent = failed = 0
        for p in game.players.values():
            member = interaction.guild.get_member(p.user_id) if interaction.guild else None
            user = member or await self.bot.fetch_user(p.user_id)
            view = make_confirm_view(game, p.user_id)
            self.bot.add_view(view)
            inv = invites.get(int(p.user_id))
            try:
                url = inv[0] if inv and is_mafia_team(p.role) else None
                emb = role_dm_embed(game, p, invite_url=url)
                if url:
                    view.add_item(discord.ui.Button(
                        label='Войти к семье',
                        style=discord.ButtonStyle.link,
                        url=url,
                        emoji='🤍',
                    ))
                await user.send(embed=emb, view=view)
                sent += 1
            except Exception as ex:
                game.mark_dm_failed(p.user_id)
                failed += 1
                log.warning('mafia role dm %s: %s', p.user_id, ex)
        # дубль: отдельная карточка семьи с инвайтом (если роль-DM без кнопки)
        try:
            inv_sent = await self.send_mafia_briefing(game, invites=invites)
        except Exception as ex:
            log.warning('mafia briefing: %s', ex)
            inv_sent = 0
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
                await msg.edit(embed=public_status_embed(game), view=None)
            except Exception:
                pass
        team_n = len(game.mafia_team())
        summary = (
            f'Раздано: {preset_summary(len(game.players))}\n'
            f'DM: **{sent}**, не дошли: **{failed}**.\n'
            f'Инвайты семьи: **{len(invites)}/{team_n}** · карточки: **{inv_sent}**.\n'
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

    async def announce(self, game: Game, text: str, *, accent: int = None):
        """Публичная фаза в канал — V2, сообщение трекается для очистки."""
        try:
            ch = self.bot.get_channel(int(game.text_channel_id))
            if ch is None:
                ch = await self.bot.fetch_channel(int(game.text_channel_id))
            from services.v2_layouts import V2_AVAILABLE, black_container
            color = accent if accent is not None else (
                0x2C3E6B if game.cycle == CYCLE_NIGHT else
                0xC4A35A if game.cycle == CYCLE_DAY else
                0x8B3A3A if game.cycle == CYCLE_VOTE else
                0x000000
            )
            msg = None
            if V2_AVAILABLE:
                from discord import ui as dui, SeparatorSpacing
                view = dui.LayoutView(timeout=1)
                view.add_item(black_container(
                    dui.TextDisplay('# 🤍 Мафия'),
                    dui.TextDisplay(
                        f'-# HAKUMO · {game.cycle_label() or "партия"} · #{game.game_id}'),
                    dui.Separator(spacing=SeparatorSpacing.large),
                    dui.TextDisplay(str(text)[:3500]),
                    accent=color,
                ))
                msg = await ch.send(view=view)
            else:
                e = discord.Embed(
                    title=f'🤍 Мафия · {game.cycle_label() or game.game_id}',
                    description=str(text)[:4000], color=color)
                e.set_footer(text=f'#{game.game_id}')
                msg = await ch.send(embed=e)
            if msg is not None:
                game.track_public_message(msg.id)
                STORE.persist(game)
        except Exception as ex:
            log.debug('mafia announce: %s', ex)

    async def set_voice_night_mute(self, game: Game, *, night: bool) -> int:
        """Ночь: все живые на муте в войсе (семья только в ЛС). День: живые говорят, мёртвые — мут."""
        # только кэш get_guild — у fetch_guild нет voice_states / members
        guild = self.bot.get_guild(int(game.guild_id))
        if guild is None:
            log.warning('mafia mute: guild %s не в кэше бота', game.guild_id)
            return 0
        me = guild.me
        if me is not None and not me.guild_permissions.mute_members:
            log.warning(
                'mafia mute: у бота нет права Mute Members на сервере %s',
                game.guild_id,
            )
        reason = (
            'мафия: ночь — все на муте, семья в ЛС' if night else 'мафия: день'
        )
        n = 0
        members = await self._members_in_voice_channel(
            guild, int(game.voice_channel_id))
        # добрать состав партии по fetch_member + member.voice
        seen = {int(m.id) for m in members}
        for p in game.players.values():
            uid = int(p.user_id)
            if uid in seen:
                continue
            m = guild.get_member(uid)
            if m is None:
                try:
                    m = await guild.fetch_member(uid)
                except Exception:
                    continue
            if m is None or m.bot:
                continue
            vs = getattr(m, 'voice', None)
            if vs is None or vs.channel is None:
                continue
            if int(vs.channel.id) != int(game.voice_channel_id):
                continue
            members.append(m)
            seen.add(uid)
        for member in members:
            if await self._apply_voice_mute_member(
                    game, member, night=night, reason=reason):
                n += 1
        if night and n == 0 and members:
            log.warning(
                'mafia mute: ночь %s — в войсе %s чел., муты не применились',
                game.day_number, len(members),
            )
        elif night:
            log.info(
                'mafia mute: ночь %s — замьючено %s (в войсе ~%s)',
                game.day_number, n, len(members),
            )
        return n

    async def send_mafia_briefing(
            self, game: Game, *, invites: dict | None = None) -> int:
        """Каждому мафиози — карточка семьи + его личный одноразовый инвайт."""
        from services.mafia.family_guild import (
            create_invites_for_team, family_guild_id,
        )
        team = game.mafia_team()
        if not team:
            return 0
        if not invites:
            invites = await create_invites_for_team(self.bot, game)
        lines = []
        for t in team:
            tr = ROLES.get(t.role)
            lines.append(
                f'🤍 {_mention(t.user_id)} — **{tr.name if tr else "?"}**')
        roster = '\n'.join(lines)
        game.mafia_family_ids = [int(t.user_id) for t in team]
        sent = 0
        for p in team:
            try:
                user = self.bot.get_user(p.user_id) or await self.bot.fetch_user(p.user_id)
                inv = (invites or {}).get(int(p.user_id))
                url = inv[0] if inv else None
                invite_block = (
                    f'**Ваш вход** (только для вас, 1 раз):\n{url}\n'
                    if url else
                    '⚠️ Инвайт не создался — напишите ведущему '
                    f'(`{family_guild_id()}`).\n'
                )
                e = discord.Embed(
                    title='🤍 Семья мафии',
                    description=(
                        f'Партия **#{game.game_id}**\n\n'
                        f'{roster}\n\n'
                        f'{invite_block}\n'
                        'Ночью общайтесь **там**. В общем войсе все на муте.\n'
                        '-# Чужих на сервере выгоняют автоматически'
                    ),
                    color=RED,
                )
                view = None
                if url:
                    view = discord.ui.View(timeout=None)
                    view.add_item(discord.ui.Button(
                        label='Войти к семье',
                        style=discord.ButtonStyle.link,
                        url=url,
                        emoji='🤍',
                    ))
                await user.send(embed=e, view=view)
                sent += 1
                log.info('mafia briefing OK uid=%s has_invite=%s', p.user_id, bool(url))
            except Exception as ex:
                game.mark_dm_failed(p.user_id)
                log.warning('mafia briefing %s: %s', p.user_id, ex)
        STORE.persist(game)
        return sent

    async def evict_mafia_family(self, game: Game) -> int:
        from services.mafia.family_guild import evict_family
        try:
            n = await evict_family(self.bot, game)
            STORE.persist(game)
            return n
        except Exception as ex:
            log.warning('mafia family evict: %s', ex)
            return 0

    async def relay_mafia_chat(self, game: Game, *, author, text: str) -> int:
        """Переслать сообщение всем живым мафиям в ЛС."""
        body = (text or '').strip()[:400]
        if not body:
            return 0
        n = 0
        e = discord.Embed(
            title='🤍 Семья · сообщение',
            description=(
                f'**{author.display_name}**: {body}\n'
                f'-# #{game.game_id} · ночь {game.day_number}'
            ),
            color=RED,
        )
        for p in game.alive_mafia_team():
            try:
                user = self.bot.get_user(p.user_id) or await self.bot.fetch_user(p.user_id)
                await user.send(embed=e)
                n += 1
            except Exception as ex:
                log.debug('mafia chat %s: %s', p.user_id, ex)
        game.add_event(f'🔴 Семья переписывалась ({author.display_name})')
        STORE.persist(game)
        return n

    async def clear_voice_mutes(self, game: Game) -> int:
        """Снять сервер-мут со всех игроков партии (отмена/конец)."""
        guild = self.bot.get_guild(int(game.guild_id))
        if guild is None:
            try:
                guild = await self.bot.fetch_guild(int(game.guild_id))
            except Exception:
                return 0
        n = 0
        for p in game.players.values():
            member = guild.get_member(int(p.user_id))
            if member is None:
                try:
                    member = await guild.fetch_member(int(p.user_id))
                except Exception:
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

    async def send_night_step_dms(self, game: Game) -> int:
        """Только текущий шаг очереди — шериф не раньше мафии/доктора."""
        step = game.current_night_step()
        if not step:
            return 0
        kind = step.get('kind') or 'kill'
        sent = 0
        for uid in step.get('actors') or []:
            p = game.players.get(int(uid))
            if not p or not p.alive:
                continue
            try:
                user = self.bot.get_user(p.user_id) or await self.bot.fetch_user(p.user_id)
                role = ROLES.get(p.role)
                title = step.get('label') or (role.name if role else 'Ход')
                desc = {
                    'kill': 'Ваш ход · выберите жертву (или пас).',
                    'sheriff': 'Ваш ход · кого проверить: мафия или мирный?',
                    'heal': 'Ваш ход · кого лечить?',
                    'block': 'Ваш ход · чьё действие блокируем?',
                    'don': 'Ваш ход · проверка: это шериф? (можно пас)',
                }.get(kind, 'Ваш ход')
                e = discord.Embed(
                    title=f'🤍 {title}',
                    description=(
                        f'{desc}\n'
                        f'-# #{game.game_id} · ночь {game.day_number} · '
                        f'{game.night_step_label()}'
                    ),
                    color=RED if role and role.team == 'mafia' else BLUE,
                )
                await user.send(
                    embed=e,
                    view=NightActionView(game.guild_id, p.user_id, kind),
                )
                sent += 1
            except Exception as ex:
                game.mark_dm_failed(p.user_id)
                log.debug('night dm %s: %s', p.user_id, ex)
        STORE.persist(game)
        return sent

    async def send_current_vote_dm(self, game: Game) -> bool:
        """Следующий голосующий по очереди — один DM."""
        vid = game.current_voter_id()
        if vid is None:
            return False
        p = game.players.get(int(vid))
        if not p or not p.alive:
            game.vote_index = int(game.vote_index or 0) + 1
            STORE.persist(game)
            return await self.send_current_vote_dm(game)
        try:
            user = self.bot.get_user(p.user_id) or await self.bot.fetch_user(p.user_id)
            e = discord.Embed(
                title='🤍 Голосование',
                description=(
                    f'День {game.day_number} · **ваша очередь** '
                    f'({game.vote_turn_label()})\n'
                    'Кого изгоняем?\n'
                    '-# Голос тайный'
                ),
                color=GOLD,
            )
            await user.send(
                embed=e, view=VoteSelectView(game.guild_id, p.user_id))
            STORE.persist(game)
            return True
        except Exception as ex:
            game.mark_dm_failed(p.user_id)
            log.debug('vote dm %s: %s', p.user_id, ex)
            game.vote_index = int(game.vote_index or 0) + 1
            STORE.persist(game)
            return await self.send_current_vote_dm(game)

    async def after_night_action(self, game: Game):
        """После хода: следующий шаг очереди или итог ночи."""
        STORE.persist(game)
        await self.refresh_host_summary(game)
        if not game.night_step_ready():
            return
        # шаг закрыт → следующий или resolve
        more = game.advance_night_step()
        STORE.persist(game)
        if more:
            await self.send_night_step_dms(game)
            await self.refresh_host_summary(game)
            return
        # очередь кончилась — сразу день
        await self.advance_cycle(game, force=False)

    async def after_vote_action(self, game: Game):
        STORE.persist(game)
        await self.refresh_host_summary(game)
        if game.vote_ready():
            await self.advance_cycle(game, force=False)
            return
        await self.send_current_vote_dm(game)

    async def cleanup_game_messages(self, game: Game) -> int:
        """Удалить все сообщения бота по партии + сводку ведущего."""
        n = 0
        ch = None
        try:
            ch = self.bot.get_channel(int(game.text_channel_id))
            if ch is None:
                ch = await self.bot.fetch_channel(int(game.text_channel_id))
        except Exception:
            ch = None
        ids = list(game.public_message_ids or [])
        if game.lobby_message_id:
            ids.append(int(game.lobby_message_id))
        seen = set()
        for mid in ids:
            mid = int(mid or 0)
            if not mid or mid in seen or ch is None:
                continue
            seen.add(mid)
            try:
                msg = await ch.fetch_message(mid)
                await msg.delete()
                n += 1
            except Exception:
                pass
        # дочистить оставшиеся сообщения бота в канале партии
        me = getattr(self.bot, 'user', None)
        if ch is not None and me is not None:
            try:
                def _is_bot(m: discord.Message) -> bool:
                    return (
                        m.author is not None
                        and int(m.author.id) == int(me.id)
                        and int(m.id) not in seen
                    )
                deleted = await ch.purge(limit=80, check=_is_bot, bulk=True)
                n += len(deleted or [])
            except Exception as ex:
                log.debug('mafia purge bot msgs: %s', ex)
        # сводка в ЛС ведущего
        try:
            if game.host_summary_channel_id and game.host_summary_message_id:
                hch = self.bot.get_channel(int(game.host_summary_channel_id))
                if hch is None:
                    hch = await self.bot.fetch_channel(
                        int(game.host_summary_channel_id))
                hmsg = await hch.fetch_message(int(game.host_summary_message_id))
                await hmsg.delete()
                n += 1
        except Exception:
            pass
        game.public_message_ids = []
        game.lobby_message_id = None
        game.host_summary_message_id = None
        game.host_summary_channel_id = None
        try:
            STORE.persist(game)
        except Exception:
            pass
        return n

    async def on_night_started(self, game: Game):
        """После begin_night: мут + короткий анонс + ЛС ходов."""
        await self.set_voice_night_mute(game, night=True)
        await self.announce(
            game,
            f'## 🌙 Ночь {game.day_number}\n'
            'Город спит · **войс на муте**.\n'
            '-# Ходы — в ЛС',
            accent=0x2C3E6B,
        )
        await self.send_night_step_dms(game)
        await self.refresh_host_summary(game)

    async def send_mafia_night_chat(self, game: Game) -> int:
        """Ночью семье — панель «Написать семье» (общение в ЛС)."""
        sent = 0
        team = game.alive_mafia_team()
        if len(team) < 1:
            return 0
        for p in team:
            try:
                user = self.bot.get_user(p.user_id) or await self.bot.fetch_user(p.user_id)
                e = discord.Embed(
                    title='🤍 Связь семьи',
                    description=(
                        f'Ночь **{game.day_number}** · город спит, войс на муте.\n'
                        'Общайтесь с семьёй кнопкой ниже — сообщение уйдёт всем в ЛС.'
                    ),
                    color=RED,
                )
                view = discord.ui.View(timeout=900)
                btn = discord.ui.Button(
                    label='Написать семье',
                    style=discord.ButtonStyle.secondary, emoji='🤍')

                async def _cb(interaction: discord.Interaction, uid=p.user_id):
                    if int(interaction.user.id) != int(uid):
                        return await interaction.response.send_message(
                            'Не ваша панель.', ephemeral=True)
                    await interaction.response.send_modal(
                        MafiaChatModal(game.guild_id))

                btn.callback = _cb  # type: ignore
                view.add_item(btn)
                await user.send(embed=e, view=view)
                sent += 1
            except Exception as ex:
                log.debug('mafia night chat %s: %s', p.user_id, ex)
        return sent

    async def on_day_started(self, game: Game, night_report: str = ''):
        await self.set_voice_night_mute(game, night=False)
        body = f'## ☀️ День {game.day_number}\n'
        if night_report:
            body += f'{night_report}\n'
        body += '-# Обсуждение в войсе · **Дальше** → голос'
        await self.announce(game, body, accent=0xC4A35A)
        await self.refresh_host_summary(game)

    async def on_vote_started(self, game: Game):
        await self.send_current_vote_dm(game)
        await self.announce(
            game,
            f'## 🗳️ Голос · день {game.day_number}\n'
            f'Очередь: **{game.vote_turn_label()}**',
            accent=0x8B3A3A,
        )
        await self.refresh_host_summary(game)

    async def _finish_game(self, game: Game, headline: str) -> str:
        await self.clear_voice_mutes(game)
        kicked = 0
        try:
            kicked = await self.evict_mafia_family(game)
        except Exception:
            pass
        # сначала чистим всё от бота, потом одно сообщение «Финал»
        n = await self.cleanup_game_messages(game)
        try:
            ch = self.bot.get_channel(int(game.text_channel_id))
            if ch is None:
                ch = await self.bot.fetch_channel(int(game.text_channel_id))
            from services.v2_layouts import V2_AVAILABLE, black_container
            color = 0x2ECC71 if game.winner == 'town' else 0xE74C3C
            if V2_AVAILABLE:
                from discord import ui as dui, SeparatorSpacing
                view = dui.LayoutView(timeout=1)
                view.add_item(black_container(
                    dui.TextDisplay('# 🤍 Финал'),
                    dui.TextDisplay(f'-# #{game.game_id}'),
                    dui.Separator(spacing=SeparatorSpacing.large),
                    dui.TextDisplay(str(headline)[:3500]),
                    accent=color,
                ))
                await ch.send(view=view)
            else:
                e = discord.Embed(
                    title='🤍 Финал',
                    description=str(headline)[:4000],
                    color=color,
                )
                await ch.send(embed=e)
        except Exception as ex:
            log.debug('mafia final announce: %s', ex)
        STORE.clear(game.guild_id, archive=True)
        return (
            f'Финал · семья выгнана (**{kicked}**) · '
            f'сообщений бота удалено: **{n}**'
        )

    async def advance_cycle(self, game: Game, *, force: bool = False) -> str:
        """Сдвинуть фазу. force — пропуск текущего шага/очереди."""
        if game.phase != PHASE_PLAYING:
            raise RuntimeError('Игра не идёт')
        if game.cycle == CYCLE_NIGHT:
            if not force and not game.night_ready():
                # force=False и шаг не готов — ждём
                if not game.night_step_ready():
                    left = len(game.night_pending())
                    step = game.current_night_step()
                    return (
                        f'Ночь · ждут **{(step or {}).get("label", "?")}** '
                        f'({left})'
                    )
                # шаг готов но очередь не кончилась — подвинуть
                await self.after_night_action(game)
                return f'Ночь · {game.night_step_label()}'
            if force and not game.night_ready():
                # добить очередь пустыми skip и resolve
                game.night_step = len(game.night_queue or [])
            report = game.resolve_night()
            STORE.persist(game)
            await self.refresh_host_summary(game)
            if game.phase == PHASE_ENDED:
                return await self._finish_game(
                    game,
                    report['report'] + '\n'
                    + ('Победа **города**.' if game.winner == 'town'
                       else 'Победа **мафии**.'))
            game.begin_day()
            STORE.persist(game)
            await self.on_day_started(game, night_report=report['report'])
            return f'День {game.day_number} · {report["report"]}'

        if game.cycle == CYCLE_DAY:
            game.begin_vote()
            STORE.persist(game)
            await self.on_vote_started(game)
            return f'Голосование · {game.vote_turn_label()}'

        if game.cycle == CYCLE_VOTE:
            if not force and not game.vote_ready():
                left = len(game.vote_pending())
                return f'Голосование · очередь: {game.vote_turn_label()} · ждут {left}'
            if force and not game.vote_ready():
                game.vote_index = len(game.vote_order or [])
            report = game.resolve_vote()
            STORE.persist(game)
            await self.announce(
                game, f'## Итог\n{report["report"]}', accent=0x8B3A3A)
            await self.refresh_host_summary(game)
            if game.phase == PHASE_ENDED:
                return await self._finish_game(
                    game,
                    ('Победа **города**.' if game.winner == 'town'
                     else 'Победа **мафии**.'))
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
