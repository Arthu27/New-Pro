# -*- coding: utf-8 -*-
"""Мафия — голосовая игра для ведущего (ТЗ «Бот по Мафии», 2026-09-21).

/mafia start в текстовом канале — бот берёт голосовой канал ведущего,
собирает всех, кто в нём сидит (кроме самого ведущего), и открывает
панель подготовки. Дальше — пресет состава, «Раздать роли» (каждому
личным сообщением, роль видит только он), подтверждение участия,
«Начать игру» и разбор партии кнопками (убийства/голосование/проверки
шерифа и дона) с авто-детектом победителя.

Все состояния партии — В ПАМЯТИ процесса (services/mafia_core.REGISTRY),
рестарт бота посреди игры её обрывает: ведущий открывает /mafia start
заново. Постоянное хранилище не нужно — партия живёт один вечер.

Дискорд-слой тонкий и покрыт tests/test_mafia_cog.py; вся арифметика
ролей/победы — services/mafia_core.py (tests/test_mafia_core.py).
"""
import discord
from discord import app_commands
from discord.ext import commands

from logger import get_logger
from services import mafia_core as MC

log = get_logger('mafia')

_BLACK = 0x000000
_MAFIA_RED = 0xE74C3C
_GOOD_GREEN = 0x2ECC71
_WAIT_GOLD = 0xF39C12


def _v2_available() -> bool:
    try:
        from services.v2_layouts import V2_AVAILABLE
        return V2_AVAILABLE
    except Exception:
        return False


def _container(text: str, *, buttons=None, accent=None, footer: str = ''):
    """Один чёрный V2-блок: текст (+футер) + ряд кнопок. None — если V2 нет
    (вызывающий код тогда отправляет обычный embed)."""
    if not _v2_available():
        return None
    from discord import ui as _ui
    from services.v2_layouts import black_container
    children = [_ui.TextDisplay(text[:4000])]
    if footer:
        children.append(_ui.TextDisplay(f'-# {footer}'[:500]))
    if buttons:
        row = _ui.ActionRow()
        for b in buttons:
            row.add_item(b)
        children.append(row)
    return black_container(*children, accent=accent if accent is not None else _BLACK)


def _fallback_embed(text: str, *, colour=None, footer: str = ''):
    e = discord.Embed(description=text[:4000], colour=colour or _BLACK)
    if footer:
        e.set_footer(text=footer[:2048])
    return e


def _game_for_channel(channel_id):
    return MC.REGISTRY.get(channel_id)


async def _safe_dm(user, **kwargs) -> bool:
    try:
        await user.send(**kwargs)
        return True
    except Exception as ex:
        log.debug('mafia: DM %s не прошло: %s', getattr(user, 'id', '?'), ex)
        return False


def _host_only(game: MC.MafiaGame, uid) -> bool:
    return game is not None and uid == game.host_id


# ═══════════════════════════════════════════════════════════════════
#  РОЛЕВАЯ КАРТОЧКА (ЛС игроку / эфемерный self-check «Моя роль»)
# ═══════════════════════════════════════════════════════════════════
class RoleConfirmView(discord.ui.LayoutView):
    """Личная карточка роли: видит только сам игрок. Кнопка идемпотентна —
    повторный клик не создаёт лишних событий (MC.MafiaGame.confirm)."""

    def __init__(self, game: MC.MafiaGame, uid, *, cog=None):
        super().__init__(timeout=None)
        self.game = game
        self.uid = uid
        self.cog = cog
        self._btn = discord.ui.Button(
            style=discord.ButtonStyle.success, emoji='✅',
            label='Подтвердить участие')
        self._btn.callback = self._confirm
        self._rebuild()

    def _text(self) -> str:
        p = self.game.players.get(self.uid)
        role = p.role if p else None
        status_line = ('✅ Участие подтверждено'
                       if p and p.status == MC.STATUS_CONFIRMED
                       else 'Ожидает подтверждения')
        return (f'**Ваша роль:** {MC.role_emoji(role)} {MC.role_label(role)}\n'
                f'**Ведущий:** <@{self.game.host_id}>\n'
                f'**Игра:** #{self.game.id}\n\n'
                'Ознакомьтесь со своей ролью и подтвердите участие.\n'
                f'-# {status_line}')

    def _rebuild(self):
        self.clear_items()
        p = self.game.players.get(self.uid)
        confirmed = bool(p and p.status == MC.STATUS_CONFIRMED)
        self._btn.disabled = confirmed
        self._btn.style = (discord.ButtonStyle.secondary if confirmed
                           else discord.ButtonStyle.success)
        self._btn.label = '✅ Подтверждено' if confirmed else 'Подтвердить участие'
        box = _container(self._text(), buttons=[self._btn])
        if box is not None:
            self.add_item(box)

    def fallback_kwargs(self) -> dict:
        p = self.game.players.get(self.uid)
        confirmed = bool(p and p.status == MC.STATUS_CONFIRMED)
        self._btn.disabled = confirmed
        v = discord.ui.View(timeout=None)
        v.add_item(self._btn)
        return {'embed': _fallback_embed(self._text()), 'view': v}

    async def send_or_dm(self, target) -> bool:
        """Отправить карточку (ЛС или эфемерная отправка через followup)."""
        kw = {'view': self} if _v2_available() else self.fallback_kwargs()
        try:
            await target.send(**kw)
            return True
        except Exception as ex:
            log.debug('mafia: карточка роли не ушла: %s', ex)
            return False

    async def _confirm(self, interaction: discord.Interaction):
        changed = self.game.confirm(self.uid)
        self._rebuild()
        try:
            if _v2_available():
                await interaction.response.edit_message(view=self)
            else:
                await interaction.response.edit_message(**self.fallback_kwargs())
        except Exception as ex:
            log.debug('mafia: confirm edit_message: %s', ex)
            try:
                await interaction.response.send_message(
                    '✅ Участие подтверждено.', ephemeral=True)
            except Exception:
                pass
        if changed and self.cog is not None:
            await self.cog.refresh_panel(self.game)


# ═══════════════════════════════════════════════════════════════════
#  ПАНЕЛЬ ПОДГОТОВКИ (setup → confirm), одно сообщение в игровом канале
# ═══════════════════════════════════════════════════════════════════
class PresetSelect(discord.ui.Select):
    def __init__(self, game: MC.MafiaGame):
        opts = []
        suggested = game.suggested_preset()
        for i in range(len(MC.PRESETS)):
            opts.append(discord.SelectOption(
                label=MC.preset_range_label(i),
                value=str(i),
                description=MC.preset_description(i)[:100],
                default=(i == suggested)))
        super().__init__(placeholder='Пресет состава ролей', options=opts,
                         min_values=1, max_values=1)
        self.game = game

    async def callback(self, interaction: discord.Interaction):
        if not _host_only(self.game, interaction.user.id):
            return await interaction.response.send_message(
                'Пресет выбирает только ведущий.', ephemeral=True)
        self.game.preset_idx = int(self.values[0])
        view: 'SetupPanelView' = self.view
        view._rebuild()
        await interaction.response.edit_message(**view.edit_kwargs())


class SetupPanelView(discord.ui.LayoutView):
    """Один и тот же вид редактируется на всём пути setup → confirm."""

    def __init__(self, game: MC.MafiaGame, *, cog=None):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.preset_select = None
        self._deal_btn = discord.ui.Button(
            style=discord.ButtonStyle.primary, emoji='🎲', label='Раздать роли')
        self._deal_btn.callback = self._on_deal
        self._refresh_voice_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji='🔄',
            label='Обновить список из войса')
        self._refresh_voice_btn.callback = self._on_refresh_voice
        self._cancel_btn = discord.ui.Button(
            style=discord.ButtonStyle.danger, emoji='❌', label='Отменить')
        self._cancel_btn.callback = self._on_cancel
        self._myrole_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji='🎭', label='Показать мою роль')
        self._myrole_btn.callback = self._on_myrole
        self._start_btn = discord.ui.Button(
            style=discord.ButtonStyle.success, emoji='🚀', label='Начать игру')
        self._start_btn.callback = self._on_start
        self._redeal_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji='🔀', label='Переиграть роли')
        self._redeal_btn.callback = self._on_deal
        self._remind_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary, emoji='🔔', label='Напомнить')
        self._remind_btn.callback = self._on_remind
        self._rebuild()

    # ── текст ────────────────────────────────────────────────────────
    def _status_text(self) -> str:
        g = self.game
        head = f'# 🎭 Мафия — игра #{g.id}\n-# HAKUMO · ведущий <@{g.host_id}>'
        if g.phase == MC.PHASE_SETUP:
            names = ', '.join(f'<@{uid}>' for uid in g.players) or '—'
            body = (f'**Игроков в наборе:** {g.player_count()}\n{names}\n\n')
            idx = g.preset_idx if g.preset_idx is not None else g.suggested_preset()
            if idx is None:
                body += (f'⚠️ Нужно минимум {MC.MIN_PLAYERS} игроков в '
                        'голосовом канале, чтобы раздать роли.')
            else:
                body += (f'**Пресет:** {MC.preset_range_label(idx)}\n'
                        f'{MC.preset_description(idx)}')
            return f'{head}\n\n{body}'
        if g.phase == MC.PHASE_CONFIRM:
            lines = []
            for uid, p in g.players.items():
                mark = '✅' if p.status == MC.STATUS_CONFIRMED else '⏳'
                lines.append(f'{mark} <@{uid}>')
            body = (f'**Подтвердили участие:** {g.confirmed_count()}/'
                   f'{g.player_count()}\n' + '\n'.join(lines))
            if g.all_confirmed():
                body += ('\n\n✅ **Все игроки подтвердили участие. '
                        'Игра готова к запуску.**')
            return f'{head}\n\n{body}'
        return f'{head}\n\nИгра уже началась — эта панель больше не активна.'

    # ── сборка (несколько чёрных блоков, как у /modpanel) ──────────────
    def _rebuild(self):
        self.clear_items()
        if not _v2_available():
            return
        from discord import ui as _ui
        from services.v2_layouts import black_container
        g = self.game
        items = [black_container(_ui.TextDisplay(self._status_text()[:4000]))]
        if g.phase == MC.PHASE_SETUP:
            self.preset_select = PresetSelect(g)
            sel_row = _ui.ActionRow()
            sel_row.add_item(self.preset_select)
            items.append(black_container(_ui.TextDisplay('**Пресет**'), sel_row))
            self._deal_btn.disabled = (g.suggested_preset() is None
                                       and g.preset_idx is None)
            btn_row = _ui.ActionRow()
            for b in (self._deal_btn, self._refresh_voice_btn, self._cancel_btn):
                btn_row.add_item(b)
            items.append(black_container(btn_row))
        elif g.phase == MC.PHASE_CONFIRM:
            self._start_btn.disabled = not g.all_confirmed()
            buttons = [self._myrole_btn]
            if g.all_confirmed():
                buttons.append(self._start_btn)
            buttons += [self._remind_btn, self._redeal_btn, self._cancel_btn]
            btn_row = _ui.ActionRow()
            for b in buttons:
                btn_row.add_item(b)
            items.append(black_container(btn_row))
        for it in items:
            self.add_item(it)

    def edit_kwargs(self) -> dict:
        if _v2_available():
            return {'view': self}
        return {'embed': _fallback_embed(self._status_text()), 'view': self}

    # ── кнопки: ведущий ──────────────────────────────────────────────
    async def _on_deal(self, interaction: discord.Interaction):
        g = self.game
        if not _host_only(g, interaction.user.id):
            return await interaction.response.send_message(
                'Раздавать роли может только ведущий.', ephemeral=True)
        if g.phase not in (MC.PHASE_SETUP, MC.PHASE_CONFIRM):
            return await interaction.response.send_message(
                'Игра уже началась.', ephemeral=True)
        try:
            mapping = g.deal(g.preset_idx)
        except ValueError as ex:
            return await interaction.response.send_message(str(ex), ephemeral=True)
        await interaction.response.defer()
        self._rebuild()
        await interaction.edit_original_response(**self.edit_kwargs())
        if self.cog is not None:
            await self.cog.deliver_roles(g)
            await self.cog.refresh_panel(g)

    async def _on_refresh_voice(self, interaction: discord.Interaction):
        g = self.game
        if not _host_only(g, interaction.user.id):
            return await interaction.response.send_message(
                'Только ведущий.', ephemeral=True)
        if g.phase != MC.PHASE_SETUP:
            return await interaction.response.send_message(
                'Список меняется только до раздачи ролей.', ephemeral=True)
        added = 0
        vc = interaction.guild.get_channel(g.voice_channel_id) \
            if interaction.guild else None
        for m in (getattr(vc, 'members', None) or []):
            if getattr(m, 'bot', False):
                continue
            if g.add_player(m.id, m.display_name):
                added += 1
        self._rebuild()
        await interaction.response.edit_message(**self.edit_kwargs())
        if added:
            await interaction.followup.send(
                f'Добавлено {added} новых игроков из голосового канала.',
                ephemeral=True)

    async def _on_cancel(self, interaction: discord.Interaction):
        g = self.game
        if not _host_only(g, interaction.user.id):
            return await interaction.response.send_message(
                'Отменить может только ведущий.', ephemeral=True)
        g.phase = MC.PHASE_ENDED
        g.log_event('Игра отменена ведущим')
        MC.REGISTRY.remove(g.channel_id)
        self.clear_items()
        box = _container(f'# 🎭 Мафия — игра #{g.id} отменена', accent=0x99AAB5)
        if box is not None:
            self.add_item(box)
        try:
            await interaction.response.edit_message(
                view=self, embed=None if _v2_available() else
                _fallback_embed(f'Игра #{g.id} отменена ведущим.'))
        except Exception as ex:
            log.debug('mafia: cancel edit: %s', ex)

    async def _on_start(self, interaction: discord.Interaction):
        g = self.game
        if not _host_only(g, interaction.user.id):
            return await interaction.response.send_message(
                'Начать игру может только ведущий.', ephemeral=True)
        try:
            g.start()
        except ValueError as ex:
            return await interaction.response.send_message(str(ex), ephemeral=True)
        self._rebuild()
        await interaction.response.edit_message(**self.edit_kwargs())
        if self.cog is not None:
            await self.cog.launch_active_panel(g, interaction.channel)

    async def _on_remind(self, interaction: discord.Interaction):
        g = self.game
        if not _host_only(g, interaction.user.id):
            return await interaction.response.send_message(
                'Только ведущий.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        pending = [uid for uid, p in g.players.items()
                  if p.status != MC.STATUS_CONFIRMED]
        if self.cog is not None:
            await self.cog.remind_players(g, pending)
        mentions = ', '.join(f'<@{uid}>' for uid in pending) or 'никого — все подтвердили'
        await interaction.followup.send(
            f'Напомнил в ЛС: {mentions}', ephemeral=True)

    async def _on_myrole(self, interaction: discord.Interaction):
        g = self.game
        p = g.players.get(interaction.user.id)
        if p is None:
            return await interaction.response.send_message(
                'Ты не участвуешь в этой партии.', ephemeral=True)
        card = RoleConfirmView(g, interaction.user.id, cog=self.cog)
        kw = {'view': card} if _v2_available() else card.fallback_kwargs()
        kw['ephemeral'] = True
        await interaction.response.send_message(**kw)


# ═══════════════════════════════════════════════════════════════════
#  АКТИВНАЯ ПАРТИЯ: панель ведущего (убийства/голосование/проверки)
# ═══════════════════════════════════════════════════════════════════
class TargetSelectView(discord.ui.View):
    """Одноразовый эфемерный выбор живого игрока для действия ведущего."""

    def __init__(self, game: MC.MafiaGame, action: str, *, cog=None):
        super().__init__(timeout=120)
        self.game = game
        self.action = action
        self.cog = cog
        alive = [uid for uid in game.players if game.players[uid].alive]
        options = [discord.SelectOption(label=game.players[uid].name,
                                        value=str(uid))
                  for uid in alive][:25]
        sel = discord.ui.Select(placeholder='Кого?', options=options or [
            discord.SelectOption(label='Нет живых игроков', value='none')])
        sel.callback = self._pick
        self.add_item(sel)
        self._sel = sel

    async def _pick(self, interaction: discord.Interaction):
        if not self._sel.values or self._sel.values[0] == 'none':
            return await interaction.response.send_message(
                'Нет доступных игроков.', ephemeral=True)
        uid = int(self._sel.values[0])
        await interaction.response.defer(ephemeral=True)
        if self.cog is not None:
            await self.cog.record_action(interaction, self.game, self.action, uid)


class ActivePanelView(discord.ui.LayoutView):
    """Панель ведущего во время партии — устранения и проверки."""

    ACTIONS = (
        ('kill', 'Мафия убила', '☠️', discord.ButtonStyle.danger),
        ('voteout', 'Исключить голосованием', '🗳️', discord.ButtonStyle.secondary),
        ('check', 'Проверка Шерифа', '🕵️', discord.ButtonStyle.primary),
        ('doncheck', 'Проверка Дона', '👑', discord.ButtonStyle.primary),
    )

    def __init__(self, game: MC.MafiaGame, *, cog=None):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self._buttons = {}
        for key, label, emoji, style in self.ACTIONS:
            btn = discord.ui.Button(style=style, emoji=emoji, label=label)
            btn.callback = self._make_cb(key)
            self._buttons[key] = btn
        self._rebuild()

    def _make_cb(self, action):
        async def _cb(interaction: discord.Interaction):
            if not _host_only(self.game, interaction.user.id):
                return await interaction.response.send_message(
                    'Действия ведёт только ведущий.', ephemeral=True)
            if self.game.phase != MC.PHASE_ACTIVE:
                return await interaction.response.send_message(
                    'Игра уже завершена.', ephemeral=True)
            await interaction.response.send_message(
                view=TargetSelectView(self.game, action, cog=self.cog),
                ephemeral=True)
        return _cb

    def _status_text(self) -> str:
        g = self.game
        mafia_alive = sum(1 for uid in g.alive_ids()
                          if g.players[uid].role in MC.MAFIA_SIDE)
        good_alive = sum(1 for uid in g.alive_ids()
                         if g.players[uid].role in MC.GOOD_SIDE)
        head = f'# 🎭 Мафия — игра #{g.id} · в игре\n-# HAKUMO · ведущий <@{g.host_id}>'
        body = (f'**Живых:** 🔴 мафия {mafia_alive} · 👥 мирные {good_alive}\n\n'
               'Отмечай убийства, голосования и проверки — победитель '
               'определяется автоматически.')
        if g.phase == MC.PHASE_ENDED and g.winner:
            title = 'выиграл мирный город' if g.winner == 'good' else 'выиграла мафия'
            body += f'\n\n🏁 **Игра окончена: {title}.**'
        return f'{head}\n\n{body}'

    def _rebuild(self):
        self.clear_items()
        active = self.game.phase == MC.PHASE_ACTIVE
        buttons = [self._buttons[k] for k, *_r in self.ACTIONS] if active else []
        box = _container(self._status_text(), buttons=buttons,
                         accent=(_GOOD_GREEN if self.game.winner == 'good'
                                else _MAFIA_RED if self.game.winner == 'mafia'
                                else _BLACK))
        if box is not None:
            self.add_item(box)

    def edit_kwargs(self) -> dict:
        if _v2_available():
            return {'view': self}
        return {'embed': _fallback_embed(self._status_text()), 'view': self}


def _win_banner(game: MC.MafiaGame):
    title = ('🏙️ Победа мирных жителей!' if game.winner == 'good'
             else '🔪 Победа мафии!')
    accent = _GOOD_GREEN if game.winner == 'good' else _MAFIA_RED
    lines = [f'# {title}', f'-# Игра #{game.id}', '']
    lines.append('**Роли всех игроков:**')
    for uid, p in game.players.items():
        alive_mark = '' if p.alive else ' — выбыл'
        lines.append(f'{MC.role_emoji(p.role)} <@{uid}> — {MC.role_label(p.role)}'
                     f'{alive_mark}')
    text = '\n'.join(lines)
    box = _container(text, accent=accent)
    if box is not None:
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(box)
        return {'view': view}
    return {'embed': _fallback_embed(text, colour=accent)}


# ═══════════════════════════════════════════════════════════════════
#  КОГ
# ═══════════════════════════════════════════════════════════════════
class Mafia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── общие хелперы, вызываются из View ───────────────────────────
    async def deliver_roles(self, game: MC.MafiaGame):
        """ЛС каждому игроку с его ролью. Неудачные ЛС — dm_ok=False,
        игрок всё равно может нажать «Показать мою роль» на панели."""
        for uid, p in list(game.players.items()):
            member = None
            try:
                guild = self.bot.get_guild(game.guild_id)
                member = guild.get_member(uid) if guild else None
            except Exception as ex:
                log.debug('mafia: get_member %s: %s', uid, ex)
            if member is None:
                p.dm_ok = False
                continue
            card = RoleConfirmView(game, uid, cog=self)
            ok = await card.send_or_dm(member)
            p.dm_ok = ok
        await self.send_host_summary(game)

    async def remind_players(self, game: MC.MafiaGame, uids):
        guild = self.bot.get_guild(game.guild_id)
        for uid in uids:
            member = guild.get_member(uid) if guild else None
            if member is None:
                continue
            card = RoleConfirmView(game, uid, cog=self)
            kw = {'view': card} if _v2_available() else card.fallback_kwargs()
            reminder = ('⏳ Не забудь подтвердить участие в игре '
                       f'#{game.id} — жду тебя!')
            try:
                if _v2_available():
                    await member.send(content=reminder)
                    await member.send(**kw)
                else:
                    kw['content'] = reminder
                    await member.send(**kw)
            except Exception as ex:
                log.debug('mafia: remind %s: %s', uid, ex)

    async def resend_role(self, game: MC.MafiaGame, uid) -> bool:
        guild = self.bot.get_guild(game.guild_id)
        member = guild.get_member(uid) if guild else None
        if member is None:
            return False
        card = RoleConfirmView(game, uid, cog=self)
        ok = await card.send_or_dm(member)
        game.players[uid].dm_ok = ok
        return ok

    async def send_host_summary(self, game: MC.MafiaGame):
        guild = self.bot.get_guild(game.guild_id)
        host = guild.get_member(game.host_id) if guild else None
        if host is None:
            return
        text = self._host_summary_text(game)
        ref = game.host_summary_ref
        if ref is not None:
            try:
                await ref.edit(content=text)
                return
            except Exception as ex:
                log.debug('mafia: host summary edit: %s', ex)
        try:
            msg = await host.send(content=text)
            game.host_summary_ref = msg
        except Exception as ex:
            log.debug('mafia: host summary send: %s', ex)

    def _host_summary_text(self, game: MC.MafiaGame) -> str:
        lines = [f'**Игра #{game.id}**', f'Игроков: {game.player_count()}',
                 f'Подтвердили: {game.confirmed_count()}/{game.player_count()}',
                 '', '**Распределение ролей:**']
        for uid, p in game.players.items():
            mark = '✅' if p.status == MC.STATUS_CONFIRMED else '⏳'
            dm_note = '' if p.dm_ok is not False else ' (ЛС закрыты)'
            lines.append(f'<@{uid}> — {MC.role_emoji(p.role)} {MC.role_label(p.role)}'
                        f' — {mark}{dm_note}')
        return '\n'.join(lines)

    async def refresh_panel(self, game: MC.MafiaGame):
        ref = game.panel_message_ref
        if ref is not None:
            msg, view = ref
            view._rebuild()
            try:
                await msg.edit(**view.edit_kwargs())
            except Exception as ex:
                log.debug('mafia: refresh_panel: %s', ex)
        await self.send_host_summary(game)

    async def launch_active_panel(self, game: MC.MafiaGame, channel):
        view = ActivePanelView(game, cog=self)
        try:
            msg = await channel.send(**view.edit_kwargs())
            game.active_panel_ref = (msg, view)
        except Exception as ex:
            log.warning('mafia: launch_active_panel: %s', ex)

    async def record_action(self, interaction: discord.Interaction,
                            game: MC.MafiaGame, action: str, uid: int):
        p = game.players.get(uid)
        if p is None:
            return await interaction.followup.send('Игрок не найден.', ephemeral=True)
        if action == 'kill':
            winner = game.eliminate(uid, 'Мафия убила ночью')
            await interaction.followup.send(
                f'☠️ {p.name} устранён мафией.', ephemeral=True)
        elif action == 'voteout':
            winner = game.eliminate(uid, 'Исключён голосованием')
            await interaction.followup.send(
                f'🗳️ {p.name} исключён голосованием.', ephemeral=True)
        elif action == 'check':
            is_mafia = game.sheriff_check(uid)
            await interaction.followup.send(
                f'🕵️ Проверка: {p.name} — '
                f'{"🔴 Мафия" if is_mafia else "👤 Мирный"}', ephemeral=True)
            winner = None
        elif action == 'doncheck':
            is_sheriff = game.don_check(uid)
            await interaction.followup.send(
                f'👑 Проверка: {p.name} — '
                f'{"🕵️ Шериф" if is_sheriff else "не шериф"}', ephemeral=True)
            winner = None
        else:
            return
        ref = game.active_panel_ref if hasattr(game, 'active_panel_ref') else None
        if ref is not None:
            msg, view = ref
            view._rebuild()
            try:
                await msg.edit(**view.edit_kwargs())
            except Exception as ex:
                log.debug('mafia: active panel refresh: %s', ex)
        if winner:
            channel = getattr(msg, 'channel', None) if ref is not None else interaction.channel
            try:
                await channel.send(**_win_banner(game))
            except Exception as ex:
                log.warning('mafia: win banner: %s', ex)
            MC.REGISTRY.remove(game.channel_id)
        await self.send_host_summary(game)

    # ── команды ──────────────────────────────────────────────────────
    mafia = app_commands.Group(name='mafia', description='Игра «Мафия» в голосовом канале')

    @mafia.command(name='start', description='Начать новую игру «Мафия»')
    async def start(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message(
                'Команда работает только на сервере.', ephemeral=True)
        if _game_for_channel(interaction.channel_id) is not None:
            return await interaction.response.send_message(
                'В этом канале уже идёт партия — заверши или отмени её '
                '(/mafia cancel), прежде чем начинать новую.', ephemeral=True)
        voice = getattr(interaction.user, 'voice', None)
        vc = getattr(voice, 'channel', None) if voice is not None else None
        if vc is None:
            return await interaction.response.send_message(
                'Зайди в голосовой канал вместе с игроками и вызови '
                'команду ещё раз — бот соберёт всех, кто рядом.',
                ephemeral=True)
        await interaction.response.defer()
        game = MC.MafiaGame(
            MC.REGISTRY.next_id(), interaction.guild.id, interaction.channel_id,
            vc.id, interaction.user.id, interaction.user.display_name)
        for m in vc.members:
            if getattr(m, 'bot', False):
                continue
            game.add_player(m.id, m.display_name)
        MC.REGISTRY.set(interaction.channel_id, game)
        view = SetupPanelView(game, cog=self)
        msg = await interaction.followup.send(**view.edit_kwargs(), wait=True)
        game.panel_message_ref = (msg, view)
        log.info('mafia: игра #%s начата host=%s players=%s',
                game.id, interaction.user.id, game.player_count())

    @mafia.command(name='cancel', description='Отменить текущую партию в этом канале')
    async def cancel(self, interaction: discord.Interaction):
        game = _game_for_channel(interaction.channel_id)
        if game is None:
            return await interaction.response.send_message(
                'В этом канале нет активной партии.', ephemeral=True)
        if not _host_only(game, interaction.user.id):
            return await interaction.response.send_message(
                'Отменить может только ведущий.', ephemeral=True)
        MC.REGISTRY.remove(interaction.channel_id)
        game.phase = MC.PHASE_ENDED
        game.log_event('Игра отменена командой /mafia cancel')
        await interaction.response.send_message(
            f'Игра #{game.id} отменена.', ephemeral=True)
        ref = game.panel_message_ref
        if ref is not None:
            msg, view = ref
            try:
                await msg.edit(view=None, embed=_fallback_embed(
                    f'Игра #{game.id} отменена ведущим.', colour=0x99AAB5))
            except Exception as ex:
                log.debug('mafia: cancel panel edit: %s', ex)

    @mafia.command(name='redeal', description='Заново раздать роли текущему составу')
    async def redeal(self, interaction: discord.Interaction):
        game = _game_for_channel(interaction.channel_id)
        if game is None:
            return await interaction.response.send_message(
                'В этом канале нет активной партии.', ephemeral=True)
        if not _host_only(game, interaction.user.id):
            return await interaction.response.send_message(
                'Только ведущий.', ephemeral=True)
        if game.phase == MC.PHASE_ACTIVE:
            return await interaction.response.send_message(
                'Игра уже началась — состав зафиксирован.', ephemeral=True)
        try:
            game.deal(game.preset_idx)
        except ValueError as ex:
            return await interaction.response.send_message(str(ex), ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self.deliver_roles(game)
        await self.refresh_panel(game)
        await interaction.followup.send(
            f'Роли перераздали — старая раскладка недействительна.',
            ephemeral=True)

    @mafia.command(name='kick', description='Убрать игрока из набора')
    @app_commands.describe(user='Кого убрать')
    async def kick(self, interaction: discord.Interaction, user: discord.Member):
        game = _game_for_channel(interaction.channel_id)
        if game is None:
            return await interaction.response.send_message(
                'В этом канале нет активной партии.', ephemeral=True)
        if not _host_only(game, interaction.user.id):
            return await interaction.response.send_message(
                'Только ведущий.', ephemeral=True)
        if game.phase == MC.PHASE_ACTIVE:
            return await interaction.response.send_message(
                'Игра уже началась — состав зафиксирован.', ephemeral=True)
        if not game.remove_player(user.id):
            return await interaction.response.send_message(
                'Этого игрока и так нет в наборе.', ephemeral=True)
        await interaction.response.send_message(
            f'{user.mention} убран из игры #{game.id}.', ephemeral=True)
        await self.refresh_panel(game)

    @mafia.command(name='add', description='Добавить игрока (должен быть в голосовом канале)')
    @app_commands.describe(user='Кого добавить')
    async def add(self, interaction: discord.Interaction, user: discord.Member):
        game = _game_for_channel(interaction.channel_id)
        if game is None:
            return await interaction.response.send_message(
                'В этом канале нет активной партии.', ephemeral=True)
        if not _host_only(game, interaction.user.id):
            return await interaction.response.send_message(
                'Только ведущий.', ephemeral=True)
        if game.phase == MC.PHASE_ACTIVE:
            return await interaction.response.send_message(
                'Игра уже началась — состав зафиксирован.', ephemeral=True)
        voice = getattr(user, 'voice', None)
        in_voice = getattr(voice, 'channel', None)
        if in_voice is None or in_voice.id != game.voice_channel_id:
            return await interaction.response.send_message(
                f'{user.mention} должен быть в том же голосовом канале.',
                ephemeral=True)
        if not game.add_player(user.id, user.display_name):
            return await interaction.response.send_message(
                'Этот игрок уже в наборе (или это ведущий).', ephemeral=True)
        await interaction.response.send_message(
            f'{user.mention} добавлен в игру #{game.id}.', ephemeral=True)
        await self.refresh_panel(game)

    @mafia.command(name='resend', description='Отправить игроку роль повторно')
    @app_commands.describe(user='Кому переслать (не указан — всем, у кого не открыты ЛС)')
    async def resend(self, interaction: discord.Interaction,
                     user: discord.Member = None):
        game = _game_for_channel(interaction.channel_id)
        if game is None:
            return await interaction.response.send_message(
                'В этом канале нет активной партии.', ephemeral=True)
        if not _host_only(game, interaction.user.id):
            return await interaction.response.send_message(
                'Только ведущий.', ephemeral=True)
        if game.phase not in (MC.PHASE_CONFIRM, MC.PHASE_ACTIVE):
            return await interaction.response.send_message(
                'Роли ещё не разданы.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        targets = ([user.id] if user is not None
                  else [uid for uid, p in game.players.items() if p.dm_ok is False])
        sent = 0
        for uid in targets:
            if await self.resend_role(game, uid):
                sent += 1
        await interaction.followup.send(
            f'Роль переслана {sent}/{len(targets)} игрокам.', ephemeral=True)

    @mafia.command(name='remind', description='Напомнить неподтвердившим о подтверждении')
    async def remind(self, interaction: discord.Interaction):
        game = _game_for_channel(interaction.channel_id)
        if game is None:
            return await interaction.response.send_message(
                'В этом канале нет активной партии.', ephemeral=True)
        if not _host_only(game, interaction.user.id):
            return await interaction.response.send_message(
                'Только ведущий.', ephemeral=True)
        pending = [uid for uid, p in game.players.items()
                  if p.status != MC.STATUS_CONFIRMED]
        await interaction.response.defer(ephemeral=True)
        await self.remind_players(game, pending)
        mentions = ', '.join(f'<@{u}>' for u in pending) or 'никого — все подтвердили'
        await interaction.followup.send(f'Напомнил: {mentions}', ephemeral=True)

    async def _action_command(self, interaction, action, user, verb):
        game = _game_for_channel(interaction.channel_id)
        if game is None:
            return await interaction.response.send_message(
                'В этом канале нет активной партии.', ephemeral=True)
        if not _host_only(game, interaction.user.id):
            return await interaction.response.send_message(
                'Только ведущий.', ephemeral=True)
        if game.phase != MC.PHASE_ACTIVE:
            return await interaction.response.send_message(
                'Игра ещё не началась (или уже закончилась).', ephemeral=True)
        if user.id not in game.players:
            return await interaction.response.send_message(
                'Этот участник не в игре.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self.record_action(interaction, game, action, user.id)

    @mafia.command(name='kill', description='Записать убийство мафии')
    @app_commands.describe(user='Кого убила мафия')
    async def kill(self, interaction: discord.Interaction, user: discord.Member):
        await self._action_command(interaction, 'kill', user, 'убит')

    @mafia.command(name='voteout', description='Записать исключение голосованием')
    @app_commands.describe(user='Кого исключили')
    async def voteout(self, interaction: discord.Interaction, user: discord.Member):
        await self._action_command(interaction, 'voteout', user, 'исключён')

    @mafia.command(name='check', description='Записать проверку шерифа')
    @app_commands.describe(user='Кого проверил шериф')
    async def check(self, interaction: discord.Interaction, user: discord.Member):
        await self._action_command(interaction, 'check', user, 'проверен')

    @mafia.command(name='doncheck', description='Записать проверку дона')
    @app_commands.describe(user='Кого проверил дон')
    async def doncheck(self, interaction: discord.Interaction, user: discord.Member):
        await self._action_command(interaction, 'doncheck', user, 'проверен доном')


async def setup(bot):
    await bot.add_cog(Mafia(bot))
