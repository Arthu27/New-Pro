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


def lobby_embed(game: Game) -> discord.Embed:
    n = len(game.players)
    e = discord.Embed(
        title=f'Мафия · игра #{game.game_id}',
        description=(
            f'Ведущий: {_mention(game.host_id)}\n'
            f'Голос: <#{game.voice_channel_id}>\n'
            f'Игроков: **{n}** (ведущий не в раздаче)\n'
            f'Фаза: **{_phase_label(game.phase)}**\n\n'
            '① Обновить состав из войса\n'
            '② Раздать роли (ЛС)\n'
            '③ Игроки подтверждают → **Начать игру** на сводке ведущего'
        ),
        color=BLACK,
    )
    if n >= 6:
        e.add_field(name='Пресет ролей', value=preset_summary(n), inline=False)
    else:
        e.add_field(
            name='Нужно ещё игроков',
            value=f'Минимум **6** · сейчас {n}. Зайдите в войс и жмите «Обновить состав».',
            inline=False,
        )
    names = ', '.join(_mention(p.user_id) for p in game.players.values()) or '—'
    e.add_field(name='Состав', value=names[:1000], inline=False)
    e.set_footer(text='Hakumo Mafia · V2')
    return e


def lobby_body_md(game: Game) -> str:
    n = len(game.players)
    preset = preset_summary(n) if n >= 6 else f'нужно ещё {max(0, 6 - n)} (мин. 6)'
    names = ', '.join(_mention(p.user_id) for p in game.players.values()) or '—'
    return (
        f'**Ведущий:** {_mention(game.host_id)}\n'
        f'**Войс:** <#{game.voice_channel_id}>\n'
        f'**Игроков:** {n} · фаза **{_phase_label(game.phase)}**\n'
        f'**Пресет:** {preset}\n\n'
        f'**Состав:** {names}\n\n'
        '-# ① Обновить → ② Раздать роли → ③ подтверждения в ЛС → Начать'
    )


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
    """Лобби мафии — кнопки со стикерами Hakumo."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        try:
            from services.mafia.ui_v2 import sticker
            self.refresh.emoji = sticker('refresh')
            self.deal.emoji = sticker('deal')
            self.cancel.emoji = sticker('cancel')
        except Exception:
            pass

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
        await interaction.response.edit_message(
            **await cog.lobby_message_kwargs(game))

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
            embed=discord.Embed(
                title='Игра отменена',
                description='Лобби закрыто. Новый стол — `/mafia` → Начать игру.',
                color=DARK),
            view=None,
        )


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
        # один persistent host-panel на все гильдии (guild из interaction)
        self.bot.add_view(HostPanelView())
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

    async def lobby_message_kwargs(self, game: Game) -> dict:
        """embed+view (+опц. V2 файл) для лобби."""
        view = LobbyView(game.guild_id)
        kw = {'embed': lobby_embed(game), 'view': view}
        try:
            from services.v2_layouts import V2_AVAILABLE
            from services.mafia.ui_v2 import (
                build_mafia_lobby_items, mafia_banner_file, _BANNER)
            if V2_AVAILABLE:
                file, name = mafia_banner_file()
                bname = name or _BANNER
                row = discord.ui.ActionRow()
                # пересоберём кнопки в row для LayoutView
                lv = discord.ui.LayoutView(timeout=600)
                lobby = LobbyView(game.guild_id)
                # классический View надёжнее для edit; V2-карточка статуса отдельно
                # оставляем embed+view, но с чёрным стилем
                _ = (file, bname, row, lv, lobby)  # keep API ready
        except Exception:
            pass
        return kw

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

    async def members_from_signups(self, guild: discord.Guild, signups: list,
                                   host_id: int) -> list:
        """Состав из event-panel signups (без ведущего)."""
        out = []
        for raw in signups or []:
            try:
                uid = int(raw)
            except (TypeError, ValueError):
                continue
            if uid == int(host_id):
                continue
            member = guild.get_member(uid) if guild else None
            name = member.display_name if member else str(uid)
            out.append((uid, name))
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

    @app_commands.command(name='mafia', description='Мафия — меню ведущего (старт, статус, роли…)')
    async def mafia(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message('Только на сервере.', ephemeral=True)
            return
        game = STORE.get(interaction.guild.id)
        embed = menu_embed(game, interaction.user.id)
        view = MafiaMenuView(self, interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def action_start(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message('Только на сервере.', ephemeral=True)
            return
        existing = STORE.get(interaction.guild.id)
        if existing and existing.phase != PHASE_ENDED:
            await interaction.response.send_message(
                f'Уже есть игра **#{existing.game_id}** ({_phase_label(existing.phase)}). '
                'Сначала выберите «Отменить игру» в меню `/mafia`.',
                ephemeral=True,
            )
            return
        voice = interaction.user.voice.channel if interaction.user.voice else None
        if voice is None:
            # fallback: Event-войс
            try:
                from cogs.event_panel import event_voice_channel_id
                vid = event_voice_channel_id()
                ch = interaction.guild.get_channel(vid)
                if isinstance(ch, discord.VoiceChannel):
                    voice = ch
            except Exception:
                pass
        if voice is None:
            await interaction.response.send_message(
                'Зайдите в голосовой канал с игроками, затем снова `/mafia` → «Начать игру».',
                ephemeral=True,
            )
            return
        members = await self.voice_members(interaction.guild, voice.id, interaction.user.id)
        await self._publish_lobby(
            interaction, voice_id=voice.id, members=members)

    async def start_from_event(
        self,
        guild: discord.Guild,
        *,
        host: discord.abc.User,
        channel: discord.abc.Messageable,
        voice_channel_id: int,
        signups: list,
    ) -> Game:
        """Создать лобби мафии из Event-панели (signups + войс Events)."""
        existing = STORE.get(guild.id)
        if existing and existing.phase != PHASE_ENDED:
            raise RuntimeError(
                f'Уже есть мафия #{existing.game_id} ({_phase_label(existing.phase)})')
        members = await self.members_from_signups(guild, signups, host.id)
        # дополнить теми, кто уже в войсе
        try:
            voice_m = await self.voice_members(guild, voice_channel_id, host.id)
            have = {uid for uid, _ in members}
            for uid, name in voice_m:
                if uid not in have:
                    members.append((uid, name))
        except Exception:
            pass
        game = Game.create(
            guild_id=guild.id,
            host_id=host.id,
            voice_channel_id=int(voice_channel_id),
            text_channel_id=int(getattr(channel, 'id', 0) or 0),
            members=members,
        )
        STORE.set(game)
        kw = await self.lobby_message_kwargs(game)
        msg = await channel.send(**kw)
        game.lobby_message_id = msg.id
        game.text_channel_id = int(getattr(channel, 'id', 0) or game.text_channel_id)
        STORE.persist(game)
        return game

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
            game.add_player(player.id, player.display_name)
            STORE.persist(game)
            await interaction.response.send_message(
                f'Добавлен {player.mention}. Нужна новая раздача ролей.', ephemeral=True)
            await self.refresh_public(game)
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
        await self.refresh_public(game)

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
    if game is None:
        desc = (
            'Активной партии нет.\n\n'
            '**Начать игру** — вы в войсе с игроками (или в Event-войсе).\n'
            'Либо с Event-панели: Анонс «Мафия» → набор → **Старт**.'
        )
        color = BLACK
    else:
        host_mark = ' · вы ведущий' if user_id == game.host_id else ''
        desc = (
            f'Игра **#{game.game_id}** · {_phase_label(game.phase)}{host_mark}\n'
            f'Игроков: **{len(game.players)}** · '
            f'подтвердили: **{game.confirmed_count()}/{len(game.players)}**\n'
            f'Войс: <#{game.voice_channel_id}>'
        )
        color = GOLD if game.phase != PHASE_PLAYING else RED
    e = discord.Embed(title='Мафия', description=desc, color=color)
    e.set_footer(text='Hakumo Mafia · V2 · выберите действие ниже')
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
            e_status = sticker('elist')
            e_panel = sticker('remind')
            e_resend = sticker('deal')
            e_add = sticker('signup')
            e_cancel = sticker('cancel')
            e_presets = sticker('deal')
        except Exception:
            e_start = e_status = e_panel = e_resend = e_add = e_cancel = e_presets = None
        options = [
            discord.SelectOption(
                label='Начать игру', value='start', emoji=e_start or '▶',
                description='Лобби из войса / Event-войса'),
            discord.SelectOption(
                label='Статус', value='status', emoji=e_status or '📊',
                description='Фаза и прогресс текущей игры'),
            discord.SelectOption(
                label='Сводка ведущему', value='panel', emoji=e_panel or '📋',
                description='Прислать панель ролей в ЛС ещё раз'),
            discord.SelectOption(
                label='Переслать роль', value='resend', emoji=e_resend or '📨',
                description='Повторно отправить роль игроку'),
            discord.SelectOption(
                label='Добавить игрока', value='add', emoji=e_add or '➕',
                description='Добавить участника в состав'),
            discord.SelectOption(
                label='Отменить игру', value='cancel', emoji=e_cancel or '🗑️',
                description='Сбросить текущую партию'),
            discord.SelectOption(
                label='Пресеты ролей', value='presets', emoji=e_presets or '🎭',
                description='Состав по числу игроков (6–14+)'),
        ]
        super().__init__(
            placeholder='Выберите действие…',
            min_values=1,
            max_values=1,
            options=options,
            custom_id='mafia:menu:action',
        )

    async def callback(self, interaction: discord.Interaction):
        view: MafiaMenuView = self.view  # type: ignore
        if interaction.user.id != view.user_id:
            await interaction.response.send_message('Это чужое меню.', ephemeral=True)
            return
        action = self.values[0]
        cog = view.cog
        if action == 'start':
            await cog.action_start(interaction)
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
                    'Только ведущий активной игры.', ephemeral=True)
                return
            if not game.players:
                await interaction.response.send_message('В составе никого нет.', ephemeral=True)
                return
            await interaction.response.send_message(
                'Кому переслать роль?',
                view=MafiaUserPickView(cog, view.guild_id, mode='resend'),
                ephemeral=True,
            )
        elif action == 'add':
            game = STORE.get(view.guild_id)
            if not game or interaction.user.id != game.host_id:
                await interaction.response.send_message('Только ведущий.', ephemeral=True)
                return
            await interaction.response.send_message(
                'Кого добавить в состав?',
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
