# -*- coding: utf-8 -*-
"""Proof — «демки» к наказаниям: доказательства в одном канале.

Идея: модератор выдал наказание → одной командой прикладывает демку
(/proof). Она падает в канал #-доказательства (создаётся автоматически в
категории «Логи»): кто наказал, кого, за что — и сам скрин/видео прямо в
сообщении. Админ скроллит канал — и видит все доказательства, ничего искать
не надо.

Команды (mod+):
  /proof <юзер> <наказание> <причина> [вложение] [ссылка]
      Прикрепить демку. Вложение перезаливается в канал (ссылки CDN Discord
      протухают — в канале файл живёт вечно). Большие файлы (>8 МБ) не
      перезальются — тогда кидаем ссылку.
  /proofs [юзер]   — все демки (по конкретному юзеру или последние 10).
  /proofdel <№>    — удалить демку (admin+), включая сообщение в канале.

Хранение: data/modproof_{gid}.json — номер, кто/кого/за что, ссылка на
сообщение в канале доказательств.
"""

from logger import get_logger

_log = get_logger("proof_cog")

import io
import json
import os

import discord
from discord import app_commands
from discord.ext import commands

from logger import get_logger
from cogs.mod_plus import _load_json, _save_json, _now

log = get_logger('proof')

GOLD = 0xD4AF37
PURPLE = 0x9B59B6
GREEN = 0x2ECC71
RED = 0xE74C3C

# больше этого размера бот не сможет перезалить файл (лимит Discord без Nitro)
MAX_REUPLOAD_BYTES = 8 * 1024 * 1024

ACTIONS = ('варн', 'мут', 'таймаут', 'кик', 'бан', 'разбан', 'тихий мут')
ACTION_COLORS = {
    'варн': GOLD, 'мут': 0xE67E22, 'таймаут': 0xE67E22, 'кик': 0xE74C3C,
    'бан': RED, 'разбан': GREEN, 'тихий мут': PURPLE,
}
IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')


def _proof_path(gid):
    return f'data/modproof_{gid}.json'


# ════════════════════════ данные (чистые функции для тестов) ═════════════
def proof_add(gid, user_id, user_name, mod_id, mod_name, action, reason, link=None):
    """Добавить демку. Номер присваивается сам (1, 2, 3…). Возвращает запись."""
    path = _proof_path(gid)
    data = _load_json(path, {})
    pid = int(data.get('next') or 1)
    data['next'] = pid + 1
    entry = {
        'id': pid,
        'user_id': int(user_id),
        'user_name': str(user_name),
        'mod_id': int(mod_id),
        'mod_name': str(mod_name),
        'action': (action or '').strip()[:30] or 'наказание',
        'reason': (reason or '').strip()[:900],
        'link': link,
        'url': None,          # появится после постинга в канал (перезалив)
        'msg_id': None,       # сообщение в #-доказательства
        'channel_id': None,
        'set_at': _now().isoformat(),
    }
    items = data.setdefault('items', {})
    items[str(pid)] = entry
    _save_json(path, data)
    return entry


def proof_update(gid, pid, **fields):
    """Точечно обновить поля записи (link, note…). id менять нельзя."""
    path = _proof_path(gid)
    data = _load_json(path, {})
    entry = (data.get('items') or {}).get(str(pid))
    if not entry:
        return None
    entry.update({k: v for k, v in fields.items() if k != 'id'})
    _save_json(path, data)
    return entry


def proof_update_delivery(gid, pid, msg_id, channel_id, url=None):
    """После постинга в канал — прописать сообщение и живую ссылку на файл."""
    path = _proof_path(gid)
    data = _load_json(path, {})
    entry = (data.get('items') or {}).get(str(pid))
    if not entry:
        return None
    entry['msg_id'] = msg_id
    entry['channel_id'] = channel_id
    if url:
        entry['url'] = url
    _save_json(path, data)
    return entry


def proof_list(gid, user_id=None, limit=None):
    """Список демок сервера (свежие первые), опционально по юзеру."""
    data = _load_json(_proof_path(gid), {})
    items = list((data.get('items') or {}).values())
    if user_id is not None:
        items = [e for e in items if e.get('user_id') == int(user_id)]
    items.sort(key=lambda e: int(e.get('id') or 0), reverse=True)
    return items[:limit] if limit else items


def proof_get(gid, pid):
    data = _load_json(_proof_path(gid), {})
    return (data.get('items') or {}).get(str(pid))


def proof_remove(gid, pid):
    path = _proof_path(gid)
    data = _load_json(path, {})
    entry = (data.get('items') or {}).pop(str(pid), None)
    if entry is not None:
        _save_json(path, data)
    return entry


def _is_image_name(name) -> bool:
    return (name or '').lower().endswith(IMAGE_EXTS)


def _is_link(text) -> bool:
    return isinstance(text, str) and text.strip().lower().startswith(('http://', 'https://'))


# ════════════════════════ ког ════════════════════════════════════════════
class ProofCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _proof_channel(self, guild):
        """Канал доказательств (автосоздание через систему логов)."""
        try:
            from cogs import logs as _logs
            return await _logs.ensure_log_channel(guild, 'proof')
        except Exception as e:
            log.warning(f'[PROOF] канал доказательств: {e}')
            return None

    def _proof_embed(self, user, entry, extra_note=None):
        color = ACTION_COLORS.get(entry['action'].lower(), PURPLE)
        e = discord.Embed(
            title=f"Демка #{entry['id']} · {entry['action']}",
            color=color,
            timestamp=_now())
        e.add_field(name='Нарушитель', value=f'{user} (`{entry["user_id"]}`)', inline=True)
        e.add_field(name='Модератор', value=f'`{entry["mod_name"]}`', inline=True)
        e.add_field(name='Наказание', value=entry['action'], inline=True)
        e.add_field(name='Причина', value=entry['reason'] or '—', inline=False)
        if entry.get('link'):
            e.add_field(name='Ссылка на демку', value=entry['link'][:900], inline=False)
        if extra_note:
            e.add_field(name='Внимание', value=extra_note, inline=False)
        e.set_footer(text='Aether · Доказательства · листай канал — тут все демки')
        return e

    async def _post_proof(self, guild, entry, file=None, image_inline=False, note=None):
        """Запостить демку в канал и записать msg_id/url в запись."""
        ch = await self._proof_channel(guild)
        if not ch:
            return False
        fake_user = f"<@{entry['user_id']}>"
        e = self._proof_embed(fake_user, entry, extra_note=note)
        if image_inline and file:
            e.set_image(url=f'attachment://{file.filename}')
        try:
            if file:
                msg = await ch.send(embed=e, file=file)
            else:
                msg = await ch.send(embed=e)
        except discord.Forbidden:
            log.warning(f'[PROOF] нет прав писать в #{ch.id}')
            return False
        except Exception as ex:
            log.warning(f'[PROOF] отправка: {ex}')
            return False
        url = None
        atts = getattr(msg, 'attachments', None) or []
        if atts:
            url = getattr(atts[0], 'url', None)
        proof_update_delivery(guild.id, entry['id'], getattr(msg, 'id', None),
                              getattr(ch, 'id', None), url=url)
        entry['msg_id'] = getattr(msg, 'id', None)
        entry['channel_id'] = getattr(ch, 'id', None)
        if url:
            entry['url'] = url
        return True

    # ── /proof ────────────────────────────────────────────────────────────
    async def _create_and_post(self, guild, moderator, user, action, reason,
                               attachment=None, link=None):
        """Ядро: запись → (перезалив вложения) → постинг в канал доказательств.

        Возвращает (ok, entry, note). Общая точка для /proof и для
        «демка прямо в /warn|/moderate» — одна логика, ноль дубляжа.
        """
        entry = proof_add(guild.id, user.id, str(user),
                          moderator.id, str(moderator), action, reason,
                          link=link or None)
        file = None
        image_inline = False
        note = None
        if attachment is not None:
            if attachment.size and attachment.size > MAX_REUPLOAD_BYTES:
                # файл тяжёлый — не перезаливаем, оставляем исходную ссылку
                note = (f'Файл большой ({attachment.size // 1024 // 1024} МБ) — не перезалит, '
                        f'ссылка может протухнуть: {attachment.url}')
                entry['link'] = entry['link'] or attachment.url
            else:
                try:
                    raw = await attachment.read()
                    file = discord.File(io.BytesIO(raw), filename=attachment.filename)
                    image_inline = _is_image_name(attachment.filename)
                except Exception as ex:
                    note = f'Не смог перезалить вложение ({str(ex)[:120]}) — оставил ссылку.'
                    entry['link'] = entry['link'] or getattr(attachment, 'url', None)
        if note:
            proof_update(guild.id, entry['id'], link=entry.get('link'), note=note)
        ok = await self._post_proof(guild, entry, file=file,
                                    image_inline=image_inline, note=note)
        return ok, entry, note

    @app_commands.command(name='proof', description='Прикрепить «демку» к наказанию (скрин/видео/ссылка)')
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(user='Кто наказан',
                           action='Что выдали: варн, мут, таймаут, кик, бан…',
                           reason='За что (коротко)',
                           attachment='Скрин или видео — перезальётся в канал доказательств',
                           link='Или ссылка на демку (ютуб и т.п.)')
    @app_commands.choices(action=[
        app_commands.Choice(name=a, value=a) for a in ACTIONS])
    async def proof(self, interaction: discord.Interaction, user: discord.Member,
                    action: str, reason: str,
                    attachment: discord.Attachment = None, link: str = None):
        link = (link or '').strip()
        # Фото/ссылка больше НЕ обязательны (пожелание владельца): демку можно
        # приложить позже отдельной /proof — карточка фиксируется сразу.
        if link and not _is_link(link):
            await interaction.response.send_message(
                'Ссылка должна начинаться с http:// или https://', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        ok, entry, note = await self._create_and_post(
            interaction.guild, interaction.user, user, action, reason,
            attachment=attachment, link=link or None)
        if not ok:
            await interaction.followup.send(
                'Демку записал, но канал доказательств недоступен '
                '(нет прав на создание каналов?). Дай боту «Управление каналами».',
                ephemeral=True)
            return

        e = discord.Embed(title=f"Демка #{entry['id']} сохранена", color=GREEN,
                          timestamp=_now())
        e.add_field(name='Кто', value=f'{user.mention} (`{user.id}`)', inline=True)
        e.add_field(name='Наказание', value=entry['action'], inline=True)
        e.add_field(name='Куда', value='канал доказательств — админы увидят при прокрутке',
                    inline=True)
        if note:
            e.add_field(name='Внимание', value=note, inline=False)
        if attachment is None and not link:
            e.add_field(name='Без медиа',
                        value='Записал без фото — скрин можно приложить позже: /proof',
                        inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)
        log.info(f"[PROOF] #{entry['id']} {interaction.user} → {user}: {action}")

    # ── /proofs ───────────────────────────────────────────────────────────
    @app_commands.command(name='proofs', description='Все демки сервера (или конкретного юзера)')
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(user='Показать только этого юзера (пусто — последние 10)')
    async def proofs(self, interaction: discord.Interaction, user: discord.Member = None):
        items = proof_list(interaction.guild.id,
                           user_id=user.id if user else None, limit=10)
        total = len(proof_list(interaction.guild.id,
                               user_id=user.id if user else None))
        e = discord.Embed(
            title=f'Демки — {user.display_name}' if user else 'Демки сервера',
            color=PURPLE, timestamp=_now())
        if not items:
            e.description = 'Пока пусто. Первая демка появится после /proof.'
        else:
            lines = []
            ch_id = items[0].get('channel_id')
            for en in items:
                jump = ''
                if en.get('msg_id') and ch_id:
                    jump = (f" · [к сообщению](https://discord.com/channels/"
                            f"{interaction.guild.id}/{ch_id}/{en['msg_id']})")
                lines.append(f"**#{en['id']}** · {en['action']} · <@{en['user_id']}> — "
                             f"{(en['reason'] or '—')[:60]} · `{en['mod_name']}`{jump}")
            e.description = '\n'.join(lines)
            e.set_footer(text=f'Всего демок: {total} · показано {len(items)}')
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ── /proofdel ─────────────────────────────────────────────────────────
    @app_commands.command(name='proofdel', description='Удалить демку по номеру (вместе с сообщением в канале)')
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(number='Номер демки (из /proofs)')
    async def proofdel(self, interaction: discord.Interaction, number: int):
        entry = proof_remove(interaction.guild.id, number)
        if not entry:
            await interaction.response.send_message(
                f'Демки #{number} нет — проверь номер в /proofs.', ephemeral=True)
            return
        # попробуем заодно убрать сообщение из канала доказательств
        msg_deleted = False
        ch_id = entry.get('channel_id')
        if ch_id and entry.get('msg_id'):
            ch = interaction.guild.get_channel(int(ch_id))
            if ch:
                try:
                    msg = await ch.fetch_message(int(entry['msg_id']))
                    await msg.delete()
                    msg_deleted = True
                except Exception as _ex:
                    _log.debug("proofdel(): подавлено: %s", _ex)
        e = discord.Embed(title=f'Демка #{number} удалена', color=RED, timestamp=_now())
        e.add_field(name='Была на', value=f"<@{entry['user_id']}> (`{entry['user_name']}`)",
                    inline=True)
        e.add_field(name='Наказание', value=entry['action'], inline=True)
        e.add_field(name='Запись удалил', value=str(interaction.user), inline=True)
        e.set_footer(text='Сообщение в канале доказательств удалено'
                     if msg_deleted else 'Запись удалена (сообщение в канале уже не найти)')
        await interaction.response.send_message(embed=e, ephemeral=True)
        log.info(f'[PROOF] #{number} удалена ({interaction.user})')


async def try_deliver_proof(bot, guild, moderator, user, action, reason,
                            attachment=None, link=None):
    """Вход из ДРУГИХ когов: /warn, /moderate, prefix-команды — после наказания.

    Возвращает короткую строку-статус для эфемерного ответа модератору
    (или None, если демки не было). Никогда не бросает исключений —
    наказание уже состоялось, демка не должна его ронять.
    """
    if attachment is None and not (link or '').strip():
        return None
    try:
        cog = getattr(bot, 'get_cog', lambda name: None)('ProofCog') if bot else None
        if cog is None:
            return None
        ok, entry, note = await cog._create_and_post(
            guild, moderator, user, action, reason,
            attachment=attachment, link=(link or None))
        if not ok:
            return 'Демку записал, но канал доказательств недоступен (права бота?).'
        txt = f'Демка #{entry["id"]} — в канале доказательств.'
        if note:
            txt += f'\nВнимание: {note[:200]}'
        return txt
    except Exception as e:
        log.warning(f'[PROOF] интеграция с наказанием ({action}): {e}')
        return None


VIDEO_EXTS = ('.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v')


def is_media_attachment(attachment) -> bool:
    """Доказательство — только картинка или видео (не любой файл)."""
    if attachment is None:
        return False
    ct = (getattr(attachment, 'content_type', '') or '').lower()
    if ct.startswith('image/') or ct.startswith('video/'):
        return True
    fn = (getattr(attachment, 'filename', '') or '').lower()
    return fn.endswith(IMAGE_EXTS) or fn.endswith(VIDEO_EXTS)


async def require_proof(interaction, attachment=None, action_ru='наказание', link=None):
    """Обязательное доказательство к наказанию.

    Возвращает True, если доказательство есть (картинка/видео во вложении
    или ссылка). Если нет — отправляет модератору отказ и возвращает False:
    наказание БЕЗ доказательства не выдаётся ни в каком случае.
    """
    if is_media_attachment(attachment) or (link or '').strip():
        return True
    e = discord.Embed(
        color=RED,
        title='Требуется доказательство',
        description=(
            f'Для наказания «**{action_ru}**» нужен скрин или видео нарушения.\n'
            'Прикрепите файл (картинку/видео) или укажите ссылку — '
            'без доказательства наказание не выдаётся.'
        ),
    )
    try:
        await interaction.followup.send(embed=e, ephemeral=True)
    except Exception:
        try:
            await interaction.response.send_message(embed=e, ephemeral=True)
        except Exception as _send_ex:
            log.debug(f"[PROOF] require_proof: ответ не доставлен: {_send_ex}")
    return False


def prefix_has_media(ctx) -> bool:
    """Есть ли картинка/видео во вложениях сообщения префикс-команды."""
    for a in getattr(getattr(ctx, 'message', None), 'attachments', []) or []:
        if is_media_attachment(a):
            return True
    return False


async def deliver_prefix_proof(bot, ctx, member, action_ru, reason):
    """Префикс-команды: первое медиа-вложение — в канал доказательств."""
    try:
        att = None
        for a in getattr(getattr(ctx, 'message', None), 'attachments', []) or []:
            if is_media_attachment(a):
                att = a
                break
        if att is None:
            return None
        return await try_deliver_proof(bot, ctx.guild, ctx.author, member,
                                       action_ru, reason, attachment=att)
    except Exception as _ex:
        log.debug(f"[PROOF] deliver_prefix_proof: {_ex}")
        return None


async def setup(bot):
    await bot.add_cog(ProofCog(bot))
    log.info('[PROOF] Ког загружен (демки к наказаниям)')
