# -*- coding: utf-8 -*-
"""Сбор демки после мута + V2-карточка одобрить/отклонить в канале доказательств.

Заказ владельца 2026-09-24:
  • наказание (мут) выдаётся сразу;
  • модератор кидает в чат фото/видео (несколько);
  • карточка уходит вебхуком Components V2 в канал доказательств;
  • select: Одобрить (мут остаётся) / Отклонить (мут снимается + unmute-лимит).
"""
from __future__ import annotations

import asyncio
import io
import os
from typing import Any

import discord

from logger import get_logger
from cogs.proof_cog import (
    is_media_attachment, proof_add, proof_update, proof_update_delivery,
    proof_save_media, _media_kind, LOCAL_MEDIA_MAX, MAX_REUPLOAD_BYTES,
)
from services.proof_review import (
    MUTE_PROOF_ACTIONS, COLLECT_TIMEOUT_SEC, COLLECT_MAX_FILES, DONE_WORDS,
    action_label, undo_mute, reviewer_may_decide, consume_unmute_limit,
)

log = get_logger('proof_flow')

WEBHOOK_NAME = 'Доказательства Hakumo'
HOOK_USERNAME = '📸 Доказательства'
ACCENT_PENDING = 0xE67E22
ACCENT_OK = 0x2ECC71
ACCENT_NO = 0xE74C3C

# (guild_id, mod_id) -> session dict
_COLLECTING: dict[tuple, dict] = {}


def _session_key(guild_id, mod_id):
    return (int(guild_id), int(mod_id))


def is_collecting(guild_id, mod_id) -> bool:
    return _session_key(guild_id, mod_id) in _COLLECTING


async def resolve_proof_channel(guild):
    """Канал доказательств: route / KNOWN 1552… / лог-фолбэк."""
    try:
        from services.channel_routes import resolve_route, channel_on_guild
        cid = resolve_route(guild.id, 'proof_channel', guild)
        if cid:
            ch = channel_on_guild(guild, cid) or guild.get_channel(cid)
            if ch is not None:
                return ch
    except Exception as _ex:
        log.debug('resolve_proof_channel route: %s', _ex)
    try:
        from cogs import logs as _logs
        return await _logs.ensure_log_channel(guild, 'proof')
    except Exception as _ex:
        log.warning('resolve_proof_channel fallback: %s', _ex)
        return None


async def _proof_webhook(channel):
    fetch = getattr(channel, 'webhooks', None)
    if fetch is None:
        return None
    try:
        hooks = await fetch()
    except Exception as _ex:
        log.debug('proof webhooks: %s', _ex)
        return None
    me_id = getattr(getattr(channel, 'guild', None), 'me', None)
    me_id = getattr(me_id, 'id', None)
    for h in hooks or ():
        try:
            if me_id is None or h.user is None or h.user.id == me_id:
                if (h.name or '').startswith('Доказательства') or h.name == WEBHOOK_NAME:
                    return h
        except Exception:
            continue
    for h in hooks or ():
        try:
            if me_id is None or h.user is None or h.user.id == me_id:
                return h
        except Exception:
            continue
    create = getattr(channel, 'create_webhook', None)
    if create is None:
        return None
    try:
        return await create(name=WEBHOOK_NAME)
    except Exception as _ex:
        log.debug('proof create_webhook: %s', _ex)
        return None


def _hook_avatar(guild):
    try:
        return guild.icon.url if guild.icon else None
    except Exception:
        return None


def _safe_filename(name: str, idx: int) -> str:
    base = os.path.basename(name or f'file{idx}')
    base = base.replace(' ', '_')[:80] or f'file{idx}'
    # unique prefix so MediaGallery attachment:// names don't collide
    return f'p{idx}_{base}'


class ProofReviewSelect(discord.ui.Select):
    """Select: Одобрить / Отклонить."""

    def __init__(self, proof_id: int):
        options = [
            discord.SelectOption(
                label='Одобрить', value='approve',
                description='Демка ок — наказание остаётся', emoji='✅'),
            discord.SelectOption(
                label='Отклонить', value='reject',
                description='Снять мут (спишется размут)', emoji='❌'),
        ]
        super().__init__(
            placeholder='Решение по демке…',
            min_values=1, max_values=1,
            options=options,
            custom_id=f'proofrev:sel:{int(proof_id)}',
        )
        self.proof_id = int(proof_id)

    async def callback(self, interaction: discord.Interaction):
        await handle_review_decision(
            interaction, self.proof_id, self.values[0])


class ProofReviewView(discord.ui.LayoutView):
    """Persistent V2-карточка проверки демки."""

    def __init__(self, *, proof_id: int, title: str = '', body: str = '',
                 footer: str = '', media_filenames=None, media_urls=None,
                 accent: int = None, resolved: bool = False,
                 status_line: str = None):
        super().__init__(timeout=None)
        self.proof_id = int(proof_id)
        self._title = title or f'Демка #{proof_id}'
        self._body = body or ''
        self._footer = footer or ''
        self._media = list(media_filenames or [])
        self._urls = list(media_urls or [])
        self._accent = accent if accent is not None else ACCENT_PENDING
        self._resolved = bool(resolved)
        self._status = status_line
        self._select = ProofReviewSelect(self.proof_id)
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        from services.v2_layouts import V2_AVAILABLE, build_proof_review_items
        body = self._body
        if self._status:
            body = f'{body}\n\n{self._status}' if body else self._status
        if V2_AVAILABLE:
            items = build_proof_review_items(
                title=self._title,
                body=body,
                footer=self._footer,
                media_filenames=self._media if not self._urls else None,
                media_urls=self._urls or None,
                select=None if self._resolved else self._select,
                accent=self._accent,
            )
            for it in (items or []):
                self.add_item(it)
            return
        if not self._resolved:
            self.add_item(self._select)

    def apply_resolved(self, *, status_line: str, accent: int):
        self._resolved = True
        self._status = status_line
        self._accent = accent
        self._rebuild()


def _card_body(entry: dict) -> str:
    uid = entry.get('user_id')
    mid = entry.get('mod_id')
    reason = (entry.get('reason') or '—')[:400]
    mute = entry.get('mute_action') or ''
    case = entry.get('case_id') or '—'
    lines = [
        f"**Нарушитель** · <@{uid}> (`{uid}`)",
        f"**Модератор** · <@{mid}> · `{entry.get('mod_name') or '—'}`",
        f"**Наказание** · {action_label(mute) if mute else entry.get('action')}",
        f"**Дело** · #{case}",
        f"**Причина**\n{reason}",
    ]
    n = len(entry.get('media_files') or entry.get('media_list') or [])
    if n:
        lines.append(f"**Файлов** · {n}")
    return '\n'.join(lines)


async def handle_review_decision(interaction: discord.Interaction,
                                 proof_id: int, decision: str):
    """Одобрить / отклонить из select."""
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(
            'Только на сервере.', ephemeral=True)
        return
    if not reviewer_may_decide(guild.id, interaction.user):
        await interaction.response.send_message(
            'Решать по демкам могут модераторы (unmute/mute).', ephemeral=True)
        return
    from cogs.proof_cog import proof_get, proof_update as _pu
    entry = proof_get(guild.id, proof_id)
    if not entry:
        await interaction.response.send_message(
            f'Демка #{proof_id} не найдена.', ephemeral=True)
        return
    status = (entry.get('review_status') or 'pending_review')
    if status in ('approved', 'rejected'):
        await interaction.response.send_message(
            'Эта демка уже решена.', ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    if decision == 'approve':
        _pu(guild.id, proof_id,
            review_status='approved',
            reviewed_by=int(interaction.user.id),
            reviewed_name=str(interaction.user),
            reviewed_at=__import__('datetime').datetime.utcnow().isoformat())
        status_line = f'✅ **Одобрено** — {interaction.user.mention}\nМут остаётся.'
        accent = ACCENT_OK
        note = 'Демка одобрена — наказание остаётся.'
    else:
        # Отклонить = снять мут + списать unmute у отклонившего
        ok_lim, deny = consume_unmute_limit(guild, interaction.user)
        if not ok_lim:
            await interaction.followup.send(deny, ephemeral=True)
            return
        member = guild.get_member(int(entry.get('user_id') or 0))
        if member is None:
            try:
                member = await guild.fetch_member(int(entry['user_id']))
            except Exception:
                member = None
        undo_txt = 'участник не на сервере'
        if member is not None:
            try:
                undo_txt = await undo_mute(
                    guild, member, entry.get('mute_action') or 'timeout')
            except Exception as _ex:
                log.warning('undo mute: %s', _ex)
                undo_txt = f'не удалось снять мут: {_ex}'
        _pu(guild.id, proof_id,
            review_status='rejected',
            reviewed_by=int(interaction.user.id),
            reviewed_name=str(interaction.user),
            reviewed_at=__import__('datetime').datetime.utcnow().isoformat(),
            undo_result=undo_txt)
        status_line = (
            f'❌ **Отклонено** — {interaction.user.mention}\n'
            f'Наказание снято: {undo_txt}\n'
            f'-# списан 1 размут у {interaction.user.mention}')
        accent = ACCENT_NO
        note = f'Демка отклонена — {undo_txt}.'

    # обновить карточку (URL из сообщения / записи)
    media_urls = list(entry.get('media_urls') or [])
    if not media_urls and interaction.message is not None:
        media_urls = [
            getattr(a, 'url', None)
            for a in (getattr(interaction.message, 'attachments', None) or [])
            if getattr(a, 'url', None)
        ]
    view = ProofReviewView(
        proof_id=proof_id,
        title=f"Демка #{proof_id} · {entry.get('action') or 'мут'}",
        body=_card_body(entry),
        footer='Hakumo · проверка доказательств',
        media_urls=media_urls,
        accent=accent,
        resolved=True,
        status_line=status_line,
    )
    try:
        await interaction.message.edit(view=view)
    except Exception as _ex:
        log.debug('review edit: %s', _ex)
    await interaction.followup.send(note, ephemeral=True)


# ─── сборы медиа после мута ───────────────────────────────────────────────

class ProofCollectView(discord.ui.LayoutView):
    """Меню после мута: скинь файлы → Готово / Отмена.

    «Время вышло» в общий чат НЕ пишем — только ЛС модератору
    (заказ 2026-09-24).
    """

    def __init__(self, *, bot, session_key, moderator_id, target_mention,
                 mute_label, minutes_left, file_count=0, expired=False,
                 status_line=None):
        super().__init__(timeout=None)
        self.bot = bot
        self.session_key = session_key
        self.moderator_id = int(moderator_id)
        self._target = target_mention
        self._mute = mute_label
        self._mins = minutes_left
        self._n = file_count
        self._expired = expired
        self._status = status_line
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        from services.v2_layouts import V2_AVAILABLE, black_container
        if not V2_AVAILABLE:
            return
        from discord import ui as _ui
        if self._expired:
            # Закрыто (готово/отмена) — коротко, без «время вышло»
            body = self._status or 'Закрыто.'
            self.add_item(black_container(
                _ui.TextDisplay(f'-# HAKUMO · доказательства\n\n{body}'),
                accent=0x99AAB5,
            ))
            return
        body = (
            f'# 📎 Доказательство\n'
            f'-# HAKUMO · после мута\n\n'
            f'**{self._mute}** · {self._target}\n'
            f'Скинь сюда **фото или видео** прямо файлами '
            f'(можно несколько сообщений).\n'
            f'Файлов: **{self._n}/{COLLECT_MAX_FILES}** · '
            f'осталось ~**{self._mins}** мин.\n'
            f'-# без ссылок — только вложения'
        )
        if self._status:
            body = f'{body}\n\n{self._status}'
        done = discord.ui.Button(
            label='Готово', style=discord.ButtonStyle.success,
            emoji='✅', custom_id=f'proofcol:done:{self.moderator_id}')
        cancel = discord.ui.Button(
            label='Отмена', style=discord.ButtonStyle.secondary,
            emoji='✖️', custom_id=f'proofcol:cancel:{self.moderator_id}')
        done.callback = self._on_done
        cancel.callback = self._on_cancel
        row = _ui.ActionRow()
        row.add_item(done)
        row.add_item(cancel)
        self.add_item(black_container(
            _ui.TextDisplay(body),
            _ui.Separator(),
            row,
            accent=ACCENT_PENDING,
        ))

    async def _mod_only(self, interaction) -> bool:
        if int(getattr(interaction.user, 'id', 0)) != self.moderator_id:
            await interaction.response.send_message(
                'Это меню другого модератора.', ephemeral=True)
            return False
        return True

    async def _on_done(self, interaction: discord.Interaction):
        if not await self._mod_only(interaction):
            return
        await interaction.response.defer()
        sess = _COLLECTING.get(self.session_key)
        if not sess:
            await interaction.followup.send(
                'Сессия уже закрыта.', ephemeral=True)
            return
        files = list(sess.get('files') or [])
        if not files:
            await interaction.followup.send(
                'Сначала прикрепи фото или видео в этот канал.',
                ephemeral=True)
            return
        task = sess.get('task')
        if task and not task.done():
            task.cancel()
        _COLLECTING.pop(self.session_key, None)
        guild = interaction.guild
        mod = interaction.user
        try:
            self._expired = True
            self._status = f'✅ **Отправлено на проверку** — {len(files)} файл(ов)'
            self._n = len(files)
            self._rebuild()
            await interaction.message.edit(view=self)
        except Exception as _ex:
            log.debug('collect done edit: %s', _ex)
        await _finalize_collection(self.bot, guild, mod, sess, files)

    async def _on_cancel(self, interaction: discord.Interaction):
        if not await self._mod_only(interaction):
            return
        await interaction.response.defer()
        sess = _COLLECTING.pop(self.session_key, None)
        if sess and sess.get('task') and not sess['task'].done():
            sess['task'].cancel()
        self._expired = True
        self._status = f'✖️ **Отменено** — {interaction.user.mention}'
        self._rebuild()
        try:
            await interaction.message.edit(view=self)
        except Exception as _ex:
            log.debug('collect cancel edit: %s', _ex)


async def start_proof_collection(*, bot, guild, channel, moderator, target,
                                 mute_action: str, reason: str, case_id=0,
                                 notify_interaction=None):
    """После успешного мута: публичное меню + сбор фото/видео файлами."""
    if mute_action not in MUTE_PROOF_ACTIONS:
        return
    if guild is None or moderator is None or target is None or channel is None:
        return
    key = _session_key(guild.id, moderator.id)
    if key in _COLLECTING:
        old = _COLLECTING[key]
        if old.get('task') and not old['task'].done():
            return

    session = {
        'guild_id': guild.id,
        'channel_id': getattr(channel, 'id', None),
        'mod_id': moderator.id,
        'target_id': int(getattr(target, 'id', 0) or 0),
        'target_name': str(getattr(target, 'display_name', None) or target),
        'mute_action': mute_action,
        'reason': (reason or '')[:900],
        'case_id': int(case_id or 0),
        'files': [],
        'started': asyncio.get_event_loop().time(),
        'task': None,
        'menu_msg_id': None,
    }
    _COLLECTING[key] = session

    mins = max(1, COLLECT_TIMEOUT_SEC // 60)
    view = ProofCollectView(
        bot=bot,
        session_key=key,
        moderator_id=moderator.id,
        target_mention=getattr(target, 'mention', str(target)),
        mute_label=action_label(mute_action),
        minutes_left=mins,
        file_count=0,
    )
    menu_msg = None
    try:
        menu_msg = await channel.send(
            content=f'{moderator.mention}',
            view=view,
        )
        session['menu_msg_id'] = getattr(menu_msg, 'id', None)
    except Exception as _ex:
        log.warning('proof collect menu: %s', _ex)
        try:
            if notify_interaction is not None:
                await notify_interaction.followup.send(
                    f'Скинь фото/видео демки сюда, потом нажми **Готово** '
                    f'(~{mins} мин).', ephemeral=True)
        except Exception:
            pass

    async def _timeout_watch():
        try:
            await asyncio.sleep(COLLECT_TIMEOUT_SEC)
            sess = _COLLECTING.get(key)
            if not sess:
                return
            files = list(sess.get('files') or [])
            _COLLECTING.pop(key, None)
            if files:
                await _finalize_collection(bot, guild, moderator, sess, files)
                return
            # Время вышло — публичное меню убираем; пишет ТОЛЬКО модератору
            mid = sess.get('menu_msg_id')
            if mid and channel is not None:
                try:
                    msg = await channel.fetch_message(int(mid))
                    await msg.delete()
                except Exception as _ex:
                    log.debug('timeout delete menu: %s', _ex)
                    try:
                        msg = await channel.fetch_message(int(mid))
                        await msg.edit(content='·', view=None)
                    except Exception:
                        pass
            try:
                note = (
                    f'⏰ **Время вышло** — демка к муту '
                    f'<@{sess["target_id"]}> не загружена.\n'
                    f'Наказание **остаётся**. Можно скинуть файлы позже '
                    f'в панели «Доказательства».'
                )
                await moderator.send(note)
            except Exception as _ex:
                log.debug('timeout DM mod: %s', _ex)
                try:
                    if notify_interaction is not None:
                        await notify_interaction.followup.send(
                            note, ephemeral=True)
                except Exception:
                    pass
        except asyncio.CancelledError:
            return
        except Exception as _ex:
            log.warning('proof timeout watch: %s', _ex)

    session['task'] = asyncio.create_task(_timeout_watch())


async def _refresh_collect_menu(channel, sess):
    """Обновить счётчик файлов на публичном меню."""
    mid = sess.get('menu_msg_id')
    bot = sess.get('_bot')
    if not mid or channel is None or bot is None:
        return
    try:
        left = max(1, int(
            (COLLECT_TIMEOUT_SEC - (
                asyncio.get_event_loop().time() - sess.get('started', 0)
            )) // 60))
        view = ProofCollectView(
            bot=bot,
            session_key=_session_key(sess['guild_id'], sess['mod_id']),
            moderator_id=sess['mod_id'],
            target_mention=f'<@{sess["target_id"]}>',
            mute_label=action_label(sess.get('mute_action') or ''),
            minutes_left=left,
            file_count=len(sess.get('files') or []),
        )
        msg = await channel.fetch_message(int(mid))
        await msg.edit(view=view)
    except Exception as _ex:
        log.debug('refresh collect menu: %s', _ex)


async def on_moderator_message(bot, message: discord.Message) -> bool:
    """Обработать сообщение модератора во время сбора. True = съели событие."""
    if message.author.bot or message.guild is None:
        return False
    key = _session_key(message.guild.id, message.author.id)
    sess = _COLLECTING.get(key)
    if not sess:
        return False
    sess['_bot'] = bot
    if sess.get('channel_id') and message.channel.id != sess['channel_id']:
        try:
            from services.channel_routes import resolve_route
            pc = resolve_route(message.guild.id, 'proof_channel', message.guild)
            if not (pc and message.channel.id == int(pc)):
                return False
        except Exception:
            return False

    content = (message.content or '').strip().lower()
    media = [a for a in (message.attachments or []) if is_media_attachment(a)]

    if media:
        for att in media:
            if len(sess['files']) >= COLLECT_MAX_FILES:
                break
            try:
                raw = await att.read()
            except Exception as _ex:
                log.debug('att read: %s', _ex)
                continue
            if not raw:
                continue
            if len(raw) > LOCAL_MEDIA_MAX:
                try:
                    await message.reply(
                        f'Файл `{att.filename}` слишком большой — пропущен.',
                        delete_after=20)
                except Exception:
                    pass
                continue
            fname = _safe_filename(att.filename, len(sess['files']) + 1)
            sess['files'].append({
                'filename': fname,
                'data': raw,
                'content_type': getattr(att, 'content_type', None),
                'orig_name': att.filename,
            })
        n = len(sess['files'])
        try:
            await message.add_reaction('📎' if n < COLLECT_MAX_FILES else '✅')
        except Exception:
            pass
        await _refresh_collect_menu(message.channel, sess)
        if n >= COLLECT_MAX_FILES or content in DONE_WORDS:
            return await _finish_session(bot, message, key, sess)
        return True

    if content in DONE_WORDS:
        return await _finish_session(bot, message, key, sess)

    if content in ('отмена', 'cancel', 'стоп'):
        task = sess.get('task')
        if task:
            task.cancel()
        _COLLECTING.pop(key, None)
        mid = sess.get('menu_msg_id')
        if mid:
            try:
                msg = await message.channel.fetch_message(int(mid))
                expired = ProofCollectView(
                    bot=bot, session_key=key,
                    moderator_id=sess['mod_id'],
                    target_mention=f'<@{sess["target_id"]}>',
                    mute_label=action_label(sess.get('mute_action') or ''),
                    minutes_left=0, expired=True,
                    status_line=f'✖️ **Отменено** — {message.author.mention}')
                await msg.edit(content=None, view=expired)
            except Exception:
                pass
        return True

    return False


async def _finish_session(bot, message, key, sess) -> bool:
    files = list(sess.get('files') or [])
    task = sess.get('task')
    if task and not task.done():
        task.cancel()
    _COLLECTING.pop(key, None)
    if not files:
        try:
            await message.reply(
                'Пока нет фото/видео — скинь файл или `отмена`.',
                delete_after=20)
        except Exception:
            pass
        # вернуть сессию пустой? нет — пусть начнут заново через новый мут
        return True
    guild = message.guild
    mod = message.author
    try:
        await message.reply(
            f'Отправляю **{len(files)}** файл(ов) на проверку…',
            delete_after=15)
    except Exception:
        pass
    await _finalize_collection(bot, guild, mod, sess, files)
    return True


async def _finalize_collection(bot, guild, moderator, sess: dict, files: list):
    """Запись + V2 webhook-карточка с select."""
    target_id = int(sess.get('target_id') or 0)
    mute_action = sess.get('mute_action') or 'timeout'
    reason = sess.get('reason') or ''
    case_id = int(sess.get('case_id') or 0)
    target_name = sess.get('target_name') or str(target_id)

    entry = proof_add(
        guild.id, target_id, target_name,
        moderator.id, str(moderator),
        action_label(mute_action), reason)
    media_list = []
    discord_files = []
    for i, f in enumerate(files):
        raw = f.get('data') or b''
        fname = f.get('filename') or f'file{i}.bin'
        kind = _media_kind(fname, f.get('content_type'))
        if kind and raw:
            media = proof_save_media(
                guild.id, entry['id'], fname, raw, f.get('content_type'))
            if media:
                media['filename'] = fname
                media_list.append(media)
        if raw and len(raw) <= MAX_REUPLOAD_BYTES:
            discord_files.append(discord.File(io.BytesIO(raw), filename=fname))
        elif raw:
            # всё равно пробуем — Discord nitro / boost
            try:
                discord_files.append(
                    discord.File(io.BytesIO(raw), filename=fname))
            except Exception:
                pass

    proof_update(
        guild.id, entry['id'],
        mute_action=mute_action,
        case_id=case_id,
        review_status='pending_review',
        media_list=media_list,
        media=media_list[0] if media_list else None,
    )
    entry = {**entry, 'mute_action': mute_action, 'case_id': case_id,
             'media_list': media_list, 'review_status': 'pending_review'}

    ch = await resolve_proof_channel(guild)
    if ch is None:
        log.warning('proof finalize: нет канала доказательств')
        return

    media_names = [f.filename for f in discord_files][:10]
    view = ProofReviewView(
        proof_id=entry['id'],
        title=f"Демка #{entry['id']} · на проверку",
        body=_card_body(entry),
        footer='Hakumo · одобри или отклони в меню ниже',
        media_filenames=media_names,
        accent=ACCENT_PENDING,
    )

    wh = await _proof_webhook(ch)
    msg = None
    send_kw: dict[str, Any] = {'view': view, 'wait': True}
    if discord_files:
        send_kw['files'] = discord_files
    try:
        if wh is not None:
            msg = await wh.send(
                username=HOOK_USERNAME,
                avatar_url=_hook_avatar(guild),
                **send_kw)
        else:
            msg = await ch.send(**{k: v for k, v in send_kw.items()
                                   if k != 'wait'})
    except Exception as _ex:
        log.warning('proof review post: %s', _ex)
        # фолбек без файлов
        try:
            msg = await ch.send(view=view)
        except Exception as _ex2:
            log.warning('proof review fallback: %s', _ex2)
            return

    if msg is not None:
        urls = [
            getattr(a, 'url', None)
            for a in (getattr(msg, 'attachments', None) or [])
            if getattr(a, 'url', None)
        ]
        proof_update_delivery(
            guild.id, entry['id'],
            getattr(msg, 'id', None), getattr(ch, 'id', None),
            url=(urls[0] if urls else None))
        proof_update(guild.id, entry['id'],
                     review_msg_id=getattr(msg, 'id', None),
                     review_channel_id=getattr(ch, 'id', None),
                     media_urls=urls)
        try:
            bot.add_view(ProofReviewView(proof_id=entry['id']),
                         message_id=getattr(msg, 'id', None))
        except TypeError:
            bot.add_view(ProofReviewView(proof_id=entry['id']))
        except Exception as _ex:
            log.debug('add_view proof: %s', _ex)
    log.info('[PROOF] review #%s → #%s (%s files)',
             entry['id'], getattr(ch, 'id', '?'), len(files))


def register_pending_views(bot):
    """После рестарта: зарегистрировать select для pending_review."""
    try:
        import glob as _glob
        from cogs.proof_cog import _load_json, _proof_path
        for path in _glob.glob('data/modproof_*.json'):
            data = _load_json(path, {})
            for ent in (data.get('items') or {}).values():
                if not isinstance(ent, dict):
                    continue
                if (ent.get('review_status') or '') != 'pending_review':
                    continue
                pid = int(ent.get('id') or 0)
                if not pid:
                    continue
                try:
                    bot.add_view(ProofReviewView(proof_id=pid))
                except Exception as _ex:
                    log.debug('register view #%s: %s', pid, _ex)
    except Exception as _ex:
        log.debug('register_pending_views: %s', _ex)
