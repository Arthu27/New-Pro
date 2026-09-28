# -*- coding: utf-8 -*-
"""Love Room — slash /love-room-panel + кнопки (только на love-room клиенте)."""
from __future__ import annotations

import asyncio
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from logger import get_logger
from services import love_room_store as store
from services import love_room_ui as ui

log = get_logger('love_room')

BLACK = 0x000000
_pending_delete: dict[int, float] = {}  # channel_id → due_ts
_delete_tasks: dict[int, asyncio.Task] = {}


def _mention(uid: int) -> str:
    return f'<@{int(uid)}>'


def _is_host(interaction: discord.Interaction) -> bool:
    member = interaction.user
    if isinstance(member, discord.Member):
        return store.member_has_host_acl(member)
    # fallback: fetch member
    guild = interaction.guild
    if guild is None:
        return False
    m = guild.get_member(int(interaction.user.id))
    return store.member_has_host_acl(m) if m else False


async def _deny(interaction: discord.Interaction, text: str = None):
    msg = text or 'Нужна роль **Ведущий** (или admin / host roles).'
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


class PartnerSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(
            custom_id='love_room:partner',
            placeholder='Партнёр для love room…',
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if not _is_host(interaction):
            return await _deny(interaction)
        users = list(self.values or [])
        if not users:
            return await interaction.response.send_message(
                'Выбери партнёра.', ephemeral=True)
        partner = users[0]
        view: LoveRoomPanelView = self.view  # type: ignore
        view.selected_partner_id = int(partner.id)
        await interaction.response.send_message(
            f'Партнёр: {_mention(partner.id)}. Жми **Создать love room**.',
            ephemeral=True)


class StageTargetSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(
            custom_id='love_room:stage_target',
            placeholder='Участник трибуны…',
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if not _is_host(interaction):
            return await _deny(interaction)
        users = list(self.values or [])
        if not users:
            return await interaction.response.send_message(
                'Выбери участника.', ephemeral=True)
        view: LoveRoomPanelView = self.view  # type: ignore
        view.stage_target_id = int(users[0].id)
        await interaction.response.send_message(
            f'Цель трибуны: {_mention(users[0].id)}.', ephemeral=True)


class LoveRoomPanelView(discord.ui.LayoutView):
    """V2 LayoutView с селектами и кнопками; timeout=None для persistence."""

    def __init__(self, bot: commands.Bot | None = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.selected_partner_id: Optional[int] = None
        self.stage_target_id: Optional[int] = None
        self._build()

    def _build(self):
        cfg = store.load_love_room_cfg()
        gid = store.cfg_int(cfg, 'guild_id')
        rooms = store.load_rooms(gid).get('rooms') or {}
        cat_ok = store.cfg_int(cfg, 'category_id') > 0
        body = ui.panel_body_md(room_count=len(rooms), category_ok=cat_ok)
        banner_name = None
        try:
            _, banner_name = ui.love_banner_file()
        except Exception:
            banner_name = None

        # Classic ActionRow children for persistence custom_ids
        pair_select = PartnerSelect()
        stage_select = StageTargetSelect()

        create_btn = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label='Создать love room',
            custom_id='love_room:create',
            emoji=ui.sticker('love_enter'),
        )
        create_btn.callback = self._on_create  # type: ignore

        close_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label='Закрыть комнату пары',
            custom_id='love_room:close',
            emoji=ui.sticker('love_close'),
        )
        close_btn.callback = self._on_close  # type: ignore

        raise_btn = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label='Поднять',
            custom_id='love_room:raise',
            emoji=ui.sticker('love_raise'),
        )
        raise_btn.callback = self._on_raise  # type: ignore

        lower_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label='Опустить',
            custom_id='love_room:lower',
            emoji=ui.sticker('love_lower'),
        )
        lower_btn.callback = self._on_lower  # type: ignore

        # Prefer V2 containers when available
        try:
            from services.v2_layouts import V2_AVAILABLE, black_container
            from discord import ui as _ui
            from discord import SeparatorSpacing
            if V2_AVAILABLE:
                head = [
                    _ui.TextDisplay('# Love Room\n-# HAKUMO · войти в love room'),
                    _ui.Separator(spacing=SeparatorSpacing.large),
                    _ui.TextDisplay(body[:3900]),
                ]
                self.add_item(black_container(*head, accent=BLACK))
                pair_row = discord.ui.ActionRow()
                pair_row.add_item(pair_select)
                self.add_item(black_container(
                    _ui.TextDisplay('**Пара**'),
                    pair_row,
                    accent=BLACK,
                ))
                act_row = discord.ui.ActionRow()
                act_row.add_item(create_btn)
                act_row.add_item(close_btn)
                self.add_item(black_container(
                    _ui.TextDisplay('**Действия**'),
                    act_row,
                    accent=BLACK,
                ))
                st_row = discord.ui.ActionRow()
                st_row.add_item(stage_select)
                self.add_item(black_container(
                    _ui.TextDisplay('**Трибуна · цель**'),
                    st_row,
                    accent=BLACK,
                ))
                st_btn = discord.ui.ActionRow()
                st_btn.add_item(raise_btn)
                st_btn.add_item(lower_btn)
                self.add_item(black_container(
                    _ui.TextDisplay('**Поднять / Опустить**\n-# Stage suppress'),
                    st_btn,
                    accent=BLACK,
                ))
                return
        except Exception as ex:
            log.debug('V2 panel build fallback: %s', ex)

        # Classic view fallback
        self.clear_items()
        # LayoutView may not support classic — use View subclass path via cog
        raise RuntimeError('V2 unavailable — use ClassicLoveRoomView')

    async def _on_create(self, interaction: discord.Interaction):
        await create_love_room(interaction, partner_id=self.selected_partner_id)

    async def _on_close(self, interaction: discord.Interaction):
        await close_pair_room(interaction, partner_id=self.selected_partner_id)

    async def _on_raise(self, interaction: discord.Interaction):
        await stage_set_suppress(interaction, suppress=False,
                                 target_id=self.stage_target_id)

    async def _on_lower(self, interaction: discord.Interaction):
        await stage_set_suppress(interaction, suppress=True,
                                 target_id=self.stage_target_id)


class ClassicLoveRoomView(discord.ui.View):
    """Фолбек без LayoutView + persistent custom_ids."""

    def __init__(self):
        super().__init__(timeout=None)
        self.selected_partner_id: Optional[int] = None
        self.stage_target_id: Optional[int] = None
        self.add_item(PartnerSelect())
        self.add_item(StageTargetSelect())

    @discord.ui.button(label='Создать love room', style=discord.ButtonStyle.success,
                       custom_id='love_room:create', emoji='🚪')
    async def create_btn(self, interaction: discord.Interaction,
                         button: discord.ui.Button):
        await create_love_room(interaction, partner_id=self.selected_partner_id)

    @discord.ui.button(label='Закрыть комнату', style=discord.ButtonStyle.secondary,
                       custom_id='love_room:close', emoji='✖️')
    async def close_btn(self, interaction: discord.Interaction,
                        button: discord.ui.Button):
        await close_pair_room(interaction, partner_id=self.selected_partner_id)

    @discord.ui.button(label='Поднять', style=discord.ButtonStyle.primary,
                       custom_id='love_room:raise', emoji='⬆️')
    async def raise_btn(self, interaction: discord.Interaction,
                        button: discord.ui.Button):
        await stage_set_suppress(interaction, suppress=False,
                                 target_id=self.stage_target_id)

    @discord.ui.button(label='Опустить', style=discord.ButtonStyle.secondary,
                       custom_id='love_room:lower', emoji='⬇️')
    async def lower_btn(self, interaction: discord.Interaction,
                        button: discord.ui.Button):
        await stage_set_suppress(interaction, suppress=True,
                                 target_id=self.stage_target_id)


def build_panel_view(bot=None):
    try:
        from services.v2_layouts import V2_AVAILABLE
        if V2_AVAILABLE:
            return LoveRoomPanelView(bot)
    except Exception:
        pass
    return ClassicLoveRoomView()


async def create_love_room(interaction: discord.Interaction,
                           partner_id: Optional[int] = None):
    if not _is_host(interaction):
        return await _deny(interaction)
    guild = interaction.guild
    if guild is None:
        return await _deny(interaction, 'Только на сервере.')

    cfg = store.load_love_room_cfg()
    cat_id = store.cfg_int(cfg, 'category_id')
    if not cat_id:
        return await _deny(
            interaction,
            'Категория не задана: поставь `LOVE_ROOM_CATEGORY_ID` / '
            '`config/love_room.json` → category_id.')

    host = interaction.user
    # Partner: select → or second user in same voice with host
    pid = int(partner_id or 0)
    if not pid:
        # try discover partner from host voice
        member = guild.get_member(int(host.id))
        vc = getattr(getattr(member, 'voice', None), 'channel', None)
        if vc is not None:
            humans = [m for m in vc.members
                      if not getattr(m, 'bot', False) and int(m.id) != int(host.id)]
            if len(humans) == 1:
                pid = int(humans[0].id)
    if not pid:
        return await _deny(interaction,
                           'Выбери партнёра в селекте (или встань вдвоём в войс).')

    if int(pid) == int(host.id):
        return await _deny(interaction, 'Нельзя создать комнату только с собой.')

    left = store.cooldown_remaining(guild.id, int(host.id))
    if left > 0:
        return await _deny(interaction, f'Кулдаун: ещё {left:.0f}с.')

    for uid in (int(host.id), pid):
        if store.find_room_for_user(guild.id, uid):
            return await _deny(interaction,
                               f'{_mention(uid)} уже в love room.')

    if not store.try_acquire_pair_lock(int(host.id), pid):
        return await _deny(interaction, 'Уже создаём комнату для этой пары…')

    await interaction.response.defer(ephemeral=True)
    try:
        category = guild.get_channel(cat_id)
        if category is None:
            try:
                category = await guild.fetch_channel(cat_id)
            except Exception as ex:
                return await interaction.followup.send(
                    f'Категория `{cat_id}` не найдена: {ex}', ephemeral=True)
        if not isinstance(category, discord.CategoryChannel):
            return await interaction.followup.send(
                'LOVE_ROOM_CATEGORY_ID должен быть категорией.', ephemeral=True)

        data = store.load_rooms(guild.id)
        used = store.used_hearts_from_rooms(
            data.get('rooms') or {}, cfg.get('name_prefix') or 'love room')
        # also scan live category children
        for ch in category.voice_channels:
            if store.is_love_room_name(ch.name, cfg.get('name_prefix')):
                parts = ch.name.split()
                if parts:
                    used.add(parts[-1])
        heart = store.pick_heart(used, cfg.get('heart_emojis'))
        name = store.room_name(cfg.get('name_prefix') or 'love room', heart)
        limit = int(cfg.get('user_limit') or 2)

        try:
            channel = await guild.create_voice_channel(
                name=name,
                category=category,
                user_limit=limit,
                reason=f'love room by {host.id}',
            )
        except discord.Forbidden:
            return await interaction.followup.send(
                'Нет права **Manage Channels** у Love Room бота.', ephemeral=True)
        except Exception as ex:
            return await interaction.followup.send(
                f'Не создал канал: {ex}', ephemeral=True)

        store.register_room(
            guild.id,
            channel_id=channel.id,
            name=name,
            users=[int(host.id), pid],
            created_by=int(host.id),
        )
        store.set_cooldown(guild.id, int(host.id))

        moved = []
        errors = []
        for uid in (int(host.id), pid):
            member = guild.get_member(uid)
            if member is None:
                try:
                    member = await guild.fetch_member(uid)
                except Exception as ex:
                    errors.append(f'<@{uid}>: {ex}')
                    continue
            try:
                await member.move_to(channel, reason='love room')
                moved.append(uid)
            except discord.Forbidden:
                errors.append(f'<@{uid}>: нет Move Members')
            except Exception as ex:
                errors.append(f'<@{uid}>: {ex}')

        msg = (
            f'💕 **{name}** создан: {channel.mention}\n'
            f'Пара: {_mention(host.id)} + {_mention(pid)}\n'
            f'Перенесены: {", ".join(_mention(u) for u in moved) or "—"}'
        )
        if errors:
            msg += '\n⚠️ ' + '; '.join(errors)
        await interaction.followup.send(msg, ephemeral=True)
        log.info('love room created ch=%s pair=%s:%s by=%s',
                 channel.id, host.id, pid, host.id)
    finally:
        store.release_pair_lock(int(host.id), pid)


async def close_pair_room(interaction: discord.Interaction,
                          partner_id: Optional[int] = None):
    if not _is_host(interaction):
        return await _deny(interaction)
    guild = interaction.guild
    if guild is None:
        return await _deny(interaction, 'Только на сервере.')

    meta = store.find_room_for_user(guild.id, int(interaction.user.id))
    if meta is None and partner_id:
        meta = store.find_room_for_user(guild.id, int(partner_id))
    if meta is None:
        # try voice channel of host
        member = guild.get_member(int(interaction.user.id))
        vc = getattr(getattr(member, 'voice', None), 'channel', None)
        if vc is not None:
            meta = store.find_room_by_channel(guild.id, vc.id)
    if meta is None:
        return await _deny(interaction, 'Активная love room не найдена.')

    cid = int(meta.get('channel_id') or 0)
    await interaction.response.defer(ephemeral=True)
    ch = guild.get_channel(cid)
    if ch is None:
        store.unregister_room(guild.id, cid)
        return await interaction.followup.send('Комната уже удалена.', ephemeral=True)
    try:
        await ch.delete(reason=f'love room close by {interaction.user.id}')
    except Exception as ex:
        return await interaction.followup.send(f'Не удалил: {ex}', ephemeral=True)
    store.unregister_room(guild.id, cid)
    await interaction.followup.send(f'Закрыто: **{meta.get("name") or cid}**.',
                                    ephemeral=True)


async def stage_set_suppress(interaction: discord.Interaction, *,
                             suppress: bool,
                             target_id: Optional[int] = None):
    """Поднять (suppress=False) / Опустить (suppress=True) на Stage."""
    if not _is_host(interaction):
        return await _deny(interaction)
    guild = interaction.guild
    if guild is None:
        return await _deny(interaction, 'Только на сервере.')

    tid = int(target_id or 0)
    if not tid:
        return await _deny(interaction, 'Выбери участника трибуны в селекте.')

    member = guild.get_member(tid)
    if member is None:
        try:
            member = await guild.fetch_member(tid)
        except Exception as ex:
            return await _deny(interaction, f'Участник не найден: {ex}')

    voice = getattr(member, 'voice', None)
    ch = getattr(voice, 'channel', None)
    if ch is None or not isinstance(ch, discord.StageChannel):
        cfg = store.load_love_room_cfg()
        src = store.cfg_int(cfg, 'source_stage_channel_id')
        hint = f' (ожидался Stage `{src}`)' if src else ''
        return await _deny(
            interaction,
            f'{_mention(tid)} не на трибуне (Stage Channel){hint}.')

    label = 'Поднять' if not suppress else 'Опустить'
    try:
        await member.edit(suppress=suppress, reason=f'love room {label}')
    except discord.Forbidden:
        return await _deny(
            interaction,
            'Нет прав Stage/Mute у бота или роли Ведущий для suppress.')
    except Exception as ex:
        return await _deny(interaction, f'{label}: {ex}')

    if interaction.response.is_done():
        await interaction.followup.send(
            f'{label}: {_mention(tid)} на {ch.mention}.', ephemeral=True)
    else:
        await interaction.response.send_message(
            f'{label}: {_mention(tid)} на {ch.mention}.', ephemeral=True)


async def schedule_empty_delete(bot, guild: discord.Guild, channel: discord.VoiceChannel):
    """Debounced delete when love room has no humans."""
    cfg = store.load_love_room_cfg()
    delay = float(cfg.get('empty_delete_debounce_sec') or 1.5)
    cid = int(channel.id)
    _pending_delete[cid] = time.time() + delay

    async def _go():
        await asyncio.sleep(delay)
        due = _pending_delete.get(cid)
        if due is None or time.time() < due - 0.05:
            return
        ch = guild.get_channel(cid)
        if ch is None or not isinstance(ch, discord.VoiceChannel):
            store.unregister_room(guild.id, cid)
            _pending_delete.pop(cid, None)
            return
        humans = [m for m in ch.members if not getattr(m, 'bot', False)]
        if not store.should_delete_empty(len(humans)):
            _pending_delete.pop(cid, None)
            return
        try:
            await ch.delete(reason='love room empty')
            log.info('love room deleted empty ch=%s', cid)
        except Exception as ex:
            log.warning('love room delete %s: %s', cid, ex)
        store.unregister_room(guild.id, cid)
        _pending_delete.pop(cid, None)

    old = _delete_tasks.get(cid)
    if old and not old.done():
        old.cancel()
    _delete_tasks[cid] = asyncio.create_task(_go(), name=f'love-del-{cid}')


async def startup_sweep(bot: commands.Bot) -> dict:
    """Удалить пустые love room*; перепривязать непустые к реестру."""
    report = {'scanned': 0, 'deleted': 0, 'kept': 0, 'errors': []}
    cfg = store.load_love_room_cfg()
    cat_id = store.cfg_int(cfg, 'category_id')
    prefix = cfg.get('name_prefix') or 'love room'
    if not cat_id:
        report['errors'].append('category_id=0 — sweep skipped')
        return report
    for guild in list(bot.guilds):
        cat = guild.get_channel(cat_id)
        if cat is None or not isinstance(cat, discord.CategoryChannel):
            continue
        for ch in list(cat.voice_channels):
            if not store.is_love_room_name(ch.name, prefix):
                continue
            report['scanned'] += 1
            humans = [m for m in ch.members if not getattr(m, 'bot', False)]
            if store.should_delete_empty(len(humans)):
                try:
                    await ch.delete(reason='love room startup sweep empty')
                    store.unregister_room(guild.id, ch.id)
                    report['deleted'] += 1
                except Exception as ex:
                    report['errors'].append(str(ex))
            else:
                meta = store.find_room_by_channel(guild.id, ch.id)
                if meta is None:
                    store.register_room(
                        guild.id,
                        channel_id=ch.id,
                        name=ch.name,
                        users=[int(m.id) for m in humans[:2]],
                        created_by=0,
                    )
                report['kept'] += 1
    return report


class LoveRoom(commands.Cog, name='love_room'):
    """Панель Love Room + voice cleanup."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name='love-room-panel',
        description='Опубликовать панель Love Room (Ведущий / admin)')
    async def love_room_panel(self, interaction: discord.Interaction):
        if not _is_host(interaction):
            return await _deny(interaction)
        guild = interaction.guild
        if guild is None:
            return await _deny(interaction, 'Только на сервере.')

        cfg = store.load_love_room_cfg()
        rooms = store.load_rooms(guild.id).get('rooms') or {}
        cat_ok = store.cfg_int(cfg, 'category_id') > 0
        body = ui.panel_body_md(room_count=len(rooms), category_ok=cat_ok)

        await interaction.response.defer(ephemeral=True)
        view = build_panel_view(self.bot)
        file, banner_name = ui.love_banner_file()
        kwargs = {'view': view}
        if file is not None:
            kwargs['file'] = file
        # V2 LayoutView sends as components; classic needs embed
        if isinstance(view, discord.ui.LayoutView):
            channel = interaction.channel
            try:
                await channel.send(**kwargs)
            except Exception as ex:
                # fallback embed + classic view
                log.warning('V2 panel send failed: %s', ex)
                classic = ClassicLoveRoomView()
                emb = ui.panel_embed(body=body, room_count=len(rooms))
                await channel.send(embed=emb, view=classic)
        else:
            emb = ui.panel_embed(body=body, room_count=len(rooms))
            await interaction.channel.send(embed=emb, view=view, **(
                {'file': file} if file else {}))
        await interaction.followup.send('Панель Love Room опубликована.', ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member is None or getattr(member, 'bot', False):
            return
        guild = member.guild
        cfg = store.load_love_room_cfg()
        prefix = cfg.get('name_prefix') or 'love room'

        for ch in (getattr(before, 'channel', None), getattr(after, 'channel', None)):
            if ch is None or not isinstance(ch, discord.VoiceChannel):
                continue
            if not store.is_love_room_name(ch.name, prefix):
                # still check registry
                if not store.find_room_by_channel(guild.id, ch.id):
                    continue
            humans = [m for m in ch.members if not getattr(m, 'bot', False)]
            if store.should_delete_empty(len(humans)):
                await schedule_empty_delete(self.bot, guild, ch)
            else:
                # cancel pending delete if someone rejoined
                cid = int(ch.id)
                _pending_delete.pop(cid, None)
                t = _delete_tasks.pop(cid, None)
                if t and not t.done():
                    t.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(LoveRoom(bot))
    try:
        bot.add_view(ClassicLoveRoomView())
    except Exception:
        pass
