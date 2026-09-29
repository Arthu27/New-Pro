# -*- coding: utf-8 -*-
"""Proof — «демки» к наказаниям: доказательства в одном канале.

Идея: модератор выдал наказание → демка падает в канал
#-доказательства (создаётся автоматически в категории «Логи»): кто наказал,
кого, за что — и сам скрин/видео прямо в сообщении. Админ скроллит канал —
и видит все доказательства, ничего искать не надо.

Откуда грузятся демки (команды /proof больше нет — заказ владельца
2026-09-04):
  • панель «Доказательства» (из /report вложения убраны 2026-09-05);
  • веб-панель («Модерация» → «Доказательства» → загрузить напрямую);
  • автоматически из /warn и /moderate (вложение перезаливается; ссылки
    CDN Discord протухают — в канале файл живёт вечно).
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

# В выборе НЕТ ни «таймаута», ни «тихого мута»: дубликаты (жалоба владельца
# 2026-09-04). Мут в боте — нативный таймаут Discord, а «тихий мут» для
# метки демки неотличим от обычного мута. В выборе: варн, мут, кик, бан,
# разбан. Старые записи («таймаут», «тихий мут») показываем как «мут» —
# их цвет оставлен в ACTION_COLORS для карточек в Discord.
ACTIONS = ('варн', 'мут', 'кик', 'бан', 'разбан')
ACTION_COLORS = {
    'варн': GOLD, 'мут': 0xE67E22, 'таймаут': 0xE67E22,  # таймаут — старые записи
    'кик': 0xE74C3C,
    'бан': RED, 'разбан': GREEN, 'тихий мут': PURPLE,
}
IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')
VIDEO_EXTS = ('.mp4', '.webm', '.mov', '.m4v', '.mkv', '.avi')

# Локальное хранилище медиа для панели: ссылка CDN Discord протухает,
# а тут файл живёт вечно — панель показывает фото/видео прямо на месте.
MEDIA_DIR = 'data/uploads/proofs'
LOCAL_MEDIA_MAX = 60 * 1024 * 1024  # 60 МБ — потолок для локального сохранения



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

def _media_kind(filename, content_type=None):
    """'image' | 'video' | None — по content-type или расширению."""
    ct = (content_type or '').lower()
    if ct.startswith('image/'):
        return 'image'
    if ct.startswith('video/'):
        return 'video'
    low = (filename or '').lower()
    if low.endswith(IMAGE_EXTS):
        return 'image'
    if low.endswith(VIDEO_EXTS):
        return 'video'
    return None


def _media_safe_name(gid, pid, filename):
    """Строгое имя файла {gid}_{pid}{ext} — никаких путей от пользователя."""
    ext = os.path.splitext(filename or '')[1].lower()
    if ext not in IMAGE_EXTS + VIDEO_EXTS:
        ext = '.bin'
    return f'{int(gid)}_{int(pid)}{ext}'


def proof_save_media(gid, pid, filename, data, content_type=None):
    """Сохранить медиа демки локально. Возвращает описание для записи или None."""
    kind = _media_kind(filename, content_type)
    if not kind or not data:
        return None
    if len(data) > LOCAL_MEDIA_MAX:
        return None
    name = _media_safe_name(gid, pid, filename)
    os.makedirs(MEDIA_DIR, exist_ok=True)
    path = os.path.join(MEDIA_DIR, name)
    with open(path, 'wb') as fp:
        fp.write(data)
    return {
        'file': os.path.join(MEDIA_DIR, name),
        'kind': kind,
        'name': (filename or name)[:120],
        'size': len(data),
        'ctype': content_type or (
            'video/mp4' if kind == 'video' else 'image/png'),
    }


def proof_media_abspath(entry):
    """Абсолютный путь локального медиа, проверенный на выход за MEDIA_DIR."""
    media = (entry or {}).get('media') or {}
    rel = media.get('file')
    if not rel:
        return None
    base = os.path.abspath(MEDIA_DIR)
    full = os.path.abspath(rel)
    if not full.startswith(base + os.sep):
        return None
    return full if os.path.isfile(full) else None


def proof_delete_media(gid, entry):
    """Удалить локальный файл демки (при удалении записи). True, если убрали."""
    full = proof_media_abspath(entry)
    if not full:
        return False
    try:
        os.remove(full)
        return True
    except OSError as _ex:
        _log.debug("proof_delete_media(): подавлено: %s", _ex)
        return False


# ─── Белый список «без демки» ────────────────────────────────────────────────
# Кого бот НЕ просит прикреплять доказательство к наказанию (доверенный
# персонал по ID участника и/или по ID роли). Управляется из панели:
# «Модерация» → «Доказательства» (/proofs) → блок «Белый список».
PROOF_WHITELIST_MAX = 200


def _proof_whitelist_path(gid):
    return f'data/proof_whitelist_{int(gid)}.json'


# Кэш whitelist: ModActionModal.__init__ читает его до send_modal (<3с).
_PROOF_WL_CACHE = {}  # gid -> (wl: dict, mono_ts)
_PROOF_WL_TTL = 45.0


def proof_whitelist(gid):
    """{'users': [...], 'roles': [...]} — кто освобождён от обязательной демки."""
    try:
        key = int(gid or 0)
    except (TypeError, ValueError):
        key = 0
    import time as _time
    now = _time.monotonic()
    hit = _PROOF_WL_CACHE.get(key)
    if hit and (now - hit[1]) < _PROOF_WL_TTL:
        wl = hit[0]
        return {'users': list(wl.get('users') or []),
                'roles': list(wl.get('roles') or [])}
    empty = {'users': [], 'roles': []}
    try:
        data = _load_json(_proof_whitelist_path(key), {})
    except Exception as _ex:
        log.debug(f'[PROOF] whitelist: чтение пропущено: {_ex}')
        _PROOF_WL_CACHE[key] = (empty, now)
        return dict(empty)
    if isinstance(data, dict):
        users = data.get('users')
        roles = data.get('roles')
        result = {
            'users': [int(u) for u in (users if isinstance(users, list) else [])
                      if str(u).isdigit()],
            'roles': [int(r) for r in (roles if isinstance(roles, list) else [])
                      if str(r).isdigit()],
        }
    elif isinstance(data, list):
        # старый плоский формат [ids...] — трактуем как список участников
        result = {'users': [int(u) for u in data if str(u).isdigit()],
                  'roles': []}
    else:
        result = dict(empty)
    _PROOF_WL_CACHE[key] = (result, now)
    return {'users': list(result['users']), 'roles': list(result['roles'])}


def _save_proof_whitelist(gid, wl):
    try:
        key = int(gid or 0)
        _PROOF_WL_CACHE.pop(key, None)
    except (TypeError, ValueError):
        key = gid
    _save_json(_proof_whitelist_path(key),
               {'users': [int(u) for u in wl['users']],
                'roles': [int(r) for r in wl['roles']]})


def proof_whitelist_add(gid, kind, ident):
    """Добавить участника/роль (kind: 'user'|'role'). Отдаёт актуальный список."""
    wl = proof_whitelist(gid)
    key = 'users' if kind == 'user' else 'roles'
    ident = int(ident)
    if ident not in wl[key] and len(wl[key]) < PROOF_WHITELIST_MAX:
        wl[key].append(ident)
        _save_proof_whitelist(gid, wl)
    return wl


def proof_whitelist_remove(gid, kind, ident):
    """Убрать участника/роль из белого списка. Отдаёт актуальный список."""
    wl = proof_whitelist(gid)
    key = 'users' if kind == 'user' else 'roles'
    ident = int(ident)
    if ident in wl[key]:
        wl[key] = [x for x in wl[key] if x != ident]
        _save_proof_whitelist(gid, wl)
    return wl


def proof_is_whitelisted(gid, user_id=None, role_ids=None):
    """Освобождён ли модератор от обязательной демки (сам или через роль)."""
    try:
        wl = proof_whitelist(gid)
        if user_id and int(user_id) in wl['users']:
            return True
        for rid in role_ids or ():
            if int(rid) in wl['roles']:
                return True
    except Exception as _ex:
        log.debug(f'[PROOF] белый список: проверка пропущена: {_ex}')
    return False


# ── Настройка «доказательство обязательно» (панель → «Доказательства») ───
def _proof_cfg_path(gid):
    return f'data/proof_config_{int(gid)}.json'


# Короткий кэш: /modpanel → send_modal должен уложиться в 3с Discord.
# Чтение JSON с диска (Windows Defender) иначе съедает окно.
_PROOF_REQ_CACHE = {}  # gid -> (required: bool, mono_ts)
_PROOF_REQ_TTL = 45.0


def proof_is_required(gid):
    """Обязательна ли демка к наказаниям на сервере.

    По умолчанию — НЕТ (заказ владельца 2026-08-27: ничего не требовать,
    пока сам не включишь в панели → «Доказательства»)."""
    try:
        key = int(gid or 0)
    except (TypeError, ValueError):
        key = 0
    import time as _time
    now = _time.monotonic()
    hit = _PROOF_REQ_CACHE.get(key)
    if hit and (now - hit[1]) < _PROOF_REQ_TTL:
        return bool(hit[0])
    required = False
    try:
        data = _load_json(_proof_cfg_path(key), {})
        if isinstance(data, dict):
            required = bool(data.get('required', False))
    except Exception as _ex:
        log.debug(f'[PROOF] конфиг: чтение пропущено: {_ex}')
        required = False
    _PROOF_REQ_CACHE[key] = (required, now)
    return required


def proof_set_required(gid, on):
    """Переключить требование доказательства из панели. Возвращает итог."""
    try:
        key = int(gid or 0)
        _PROOF_REQ_CACHE.pop(key, None)
        _save_json(_proof_cfg_path(key), {'required': bool(on)})
    except Exception as _ex:
        log.debug(f'[PROOF] конфиг: запись пропущена: {_ex}')
    return proof_is_required(gid)


# ════════════════════════ ког ════════════════════════════════════════════
class ProofCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _proof_channel(self, guild):
        """Канал доказательств: панель → KNOWN (1552088029047423027) → авто."""
        try:
            from services.channel_routes import (
                get_route, KNOWN_CHANNELS, channel_on_guild)
            cid = (get_route(guild.id, 'proof_channel')
                   or KNOWN_CHANNELS.get('proof_channel')
                   or 1552088029047423027)
            if cid:
                ch = channel_on_guild(guild, int(cid))
                if ch is None:
                    getter = getattr(guild, 'get_channel', None)
                    ch = getter(int(cid)) if callable(getter) else None
                if ch is not None:
                    return ch
                log.warning('[PROOF] канал #%s не найден — фолбэк', cid)
        except Exception as _ex:
            _log.debug("_proof_channel(): маршруты: %s", _ex)
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
        e.set_footer(text='Hakumo · Доказательства · листай канал — тут все демки')
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

        Возвращает (ok, entry, note). Общая точка для команд бота и для
        «демка прямо в /warn|/moderate» — одна логика, ноль дубляжа.
        """
        entry = proof_add(guild.id, user.id, str(user),
                          moderator.id, str(moderator), action, reason,
                          link=link or None)
        file = None
        image_inline = False
        note = None
        if attachment is not None:
            size = attachment.size or 0
            too_big = bool(attachment.size) and size > MAX_REUPLOAD_BYTES
            kind = _media_kind(attachment.filename,
                               getattr(attachment, 'content_type', None))
            raw = None
            # читаем файл один раз: и для перезалива в канал, и для панели
            if not too_big or (kind and size <= LOCAL_MEDIA_MAX):
                try:
                    raw = await attachment.read()
                except Exception:
                    raw = None
            # локальная копия для панели — видео/фото смотрятся прямо там,
            # даже если файл тяжёлый и в канал не перезаливается
            if raw is not None and kind and len(raw) <= LOCAL_MEDIA_MAX:
                media = proof_save_media(guild.id, entry['id'], attachment.filename,
                                         raw, getattr(attachment, 'content_type', None))
                if media:
                    proof_update(guild.id, entry['id'], media=media)
                    entry['media'] = media
            if too_big:
                # файл тяжёлый — не перезаливаем, оставляем исходную ссылку
                note = (f'Файл большой ({(attachment.size or 0) // 1024 // 1024} МБ) — не перезалит, '
                        f'ссылка может протухнуть: {attachment.url}')
                if entry.get('media'):
                    note += ' · в панели (/proofs) видео доступно'
                entry['link'] = entry['link'] or attachment.url
            elif raw is not None:
                file = discord.File(io.BytesIO(raw), filename=attachment.filename)
                image_inline = _is_image_name(attachment.filename)
            else:
                note = 'Не смог перезалить вложение — оставил ссылку.'
                entry['link'] = entry['link'] or getattr(attachment, 'url', None)
        if note:
            proof_update(guild.id, entry['id'], link=entry.get('link'), note=note)
        ok = await self._post_proof(guild, entry, file=file,
                                    image_inline=image_inline, note=note)
        return ok, entry, note

    # Команды /proof больше НЕТ (заказ владельца 2026-09-04: «/proof убери
    # вообще»): демки грузятся через панель (из /report вложения убраны)
    # («Доказательства»). Ядро _create_and_post выше осталось — им пользуются
    # /warn, /moderate и прямая загрузка в панели.

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
            e.description = 'Пока пусто. Загрузите первую через панель «Доказательства».'
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
        proof_delete_media(interaction.guild.id, entry)
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
    или ссылка) ЛИБО модератор в белом списке «без демки». Если нет —
    отправляет модератору отказ и возвращает False: наказание БЕЗ
    доказательства не выдаётся ни в каком случае.
    """
    if is_media_attachment(attachment):
        return True
    link = (link or '').strip()
    bad_link = bool(link) and not _is_link(link)
    if link and _is_link(link):
        return True
    # Отключено на сервере в панели («Доказательства» → тумблер): демка не нужна
    gid = getattr(getattr(interaction, 'guild', None), 'id', 0)
    if gid and not proof_is_required(gid):
        return True
    # Белый список (панель → /proofs): доверенным демка не нужна
    mod = getattr(interaction, 'user', None)
    if mod and gid and proof_is_whitelisted(
            gid, user_id=getattr(mod, 'id', 0),
            role_ids=[getattr(r, 'id', 0) for r in getattr(mod, 'roles', []) or []]):
        return True
    _desc = (
        f'Для наказания «**{action_ru}**» нужен скрин или видео нарушения.\n'
        'Прикрепите файл (картинку/видео) или укажите ссылку (https://…) — '
        'без доказательства наказание не выдаётся.'
    )
    if bad_link:
        _desc += ('\n\nВаша строка не похожа на ссылку — нужна ссылка '
                  'вида https://… на скрин/видео.')
    e = discord.Embed(
        color=RED,
        title='Требуется доказательство',
        description=_desc,
    )
    e.set_footer(text='Отключить требование: панель → «Доказательства» (тумблер сверху)')
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


# ═══════════ после наказания: файл → канал → принять/отклонить ═══════════

# «× Отвечаю за Moderator» — silent ping на карточке демки
PROOF_REVIEW_ROLE_ID = 1551524708552278036


def _action_key_ru(action: str) -> str:
    a = (action or '').strip().lower()
    return {
        'warn': 'варн', 'варн': 'варн',
        'timeout': 'мут', 'mute': 'мут', 'mute_chat': 'мут чата',
        'vmute': 'войс-мут', 'войс-мут': 'войс-мут',
        'ban': 'бан', 'апелляция': 'бан', 'кик': 'кик', 'kick': 'кик',
    }.get(a, a or 'наказание')


class ProofFileModal(discord.ui.Modal, title='Доказательство'):
    """Модалка: файл (фото/видео), без ссылок — скорость."""

    def __init__(self, *, guild_id: int, user_id: int, mod_id: int,
                 action: str, reason: str, case_id=None, warn_id=None):
        super().__init__(timeout=180)
        self.guild_id = int(guild_id or 0)
        self.user_id = int(user_id or 0)
        self.mod_id = int(mod_id or 0)
        self.action = action
        self.reason = reason or ''
        self.case_id = case_id
        self.warn_id = warn_id
        self.upload = discord.ui.FileUpload(
            required=True, min_values=1, max_values=4)
        self.add_item(discord.ui.Label(
            text='Фото или видео',
            description='Без ссылок — приложи файл сразу',
            component=self.upload,
        ))

    async def on_submit(self, interaction: discord.Interaction):
        atts = list(self.upload.values or [])
        media = [a for a in atts if is_media_attachment(a)]
        if not media:
            return await interaction.response.send_message(
                'Нужен файл: фото или видео (не ссылка).', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        bot = interaction.client
        guild = interaction.guild or bot.get_guild(self.guild_id)
        if guild is None:
            return await interaction.followup.send(
                'Сервер не найден — демку некуда отправить.', ephemeral=True)
        mod = interaction.user
        user = guild.get_member(self.user_id)
        if user is None:
            try:
                user = await bot.fetch_user(self.user_id)
            except Exception:
                user = None
        if user is None:
            return await interaction.followup.send(
                'Участник не найден.', ephemeral=True)
        try:
            ok, entry = await post_proof_review_card(
                bot, guild, mod, user,
                action=self.action, reason=self.reason,
                attachments=media,
                case_id=self.case_id, warn_id=self.warn_id)
        except Exception as ex:
            log.warning('[PROOF] post review card: %s', ex)
            return await interaction.followup.send(
                f'Не удалось отправить демку: {ex}', ephemeral=True)
        if not ok:
            return await interaction.followup.send(
                'Канал доказательств недоступен (права бота?).', ephemeral=True)
        try:
            from services.v2_layouts import V2_AVAILABLE, black_container
            if V2_AVAILABLE:
                from discord import ui as dui, SeparatorSpacing
                done = dui.LayoutView(timeout=1)
                done.add_item(black_container(
                    dui.TextDisplay(f'# 🤍 Демка #{entry["id"]}'),
                    dui.Separator(spacing=SeparatorSpacing.small),
                    dui.TextDisplay('В канале доказательств · на проверке'),
                ))
                await interaction.followup.send(view=done, ephemeral=True)
            else:
                await interaction.followup.send(
                    f'Демка #{entry["id"]} — на проверке.', ephemeral=True)
        except Exception:
            await interaction.followup.send(
                f'Демка #{entry["id"]} — на проверке.', ephemeral=True)


class ProofOfferSelect(discord.ui.Select):
    """Select после наказания: файл / пропустить — 🤍."""

    def __init__(self, *, guild_id: int, user_id: int, mod_id: int,
                 action: str, reason: str, case_id=None, warn_id=None):
        from services.menu_banners import select_label
        self.guild_id = int(guild_id or 0)
        self.user_id = int(user_id or 0)
        self.mod_id = int(mod_id or 0)
        self.action = action
        self.reason = reason or ''
        self.case_id = case_id
        self.warn_id = warn_id
        super().__init__(
            placeholder='Выберите действие',
            min_values=1, max_values=1,
            options=[
                discord.SelectOption(
                    label=select_label('Прикрепить файл'),
                    value='upload', emoji='🤍'),
                discord.SelectOption(
                    label=select_label('Пропустить'),
                    value='skip', emoji='🤍'),
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        if int(getattr(interaction.user, 'id', 0) or 0) != self.mod_id:
            return await interaction.response.send_message(
                'Это меню только для модератора, кто выдал наказание.',
                ephemeral=True)
        choice = (self.values or [''])[0]
        if choice == 'upload':
            return await interaction.response.send_modal(ProofFileModal(
                guild_id=self.guild_id, user_id=self.user_id,
                mod_id=self.mod_id, action=self.action, reason=self.reason,
                case_id=self.case_id, warn_id=self.warn_id))
        # skip — закрыть меню
        try:
            from services.v2_layouts import V2_AVAILABLE, black_container
            if V2_AVAILABLE:
                from discord import ui as dui, SeparatorSpacing
                done = dui.LayoutView(timeout=1)
                done.add_item(black_container(
                    dui.TextDisplay('# 🤍 Доказательство'),
                    dui.Separator(spacing=SeparatorSpacing.small),
                    dui.TextDisplay('Пропущено · наказание уже выдано'),
                ))
                await interaction.response.edit_message(view=done)
                return
        except Exception:
            pass
        await interaction.response.edit_message(
            content='Пропущено · наказание уже выдано', view=None)


def build_proof_offer_view(*, guild_id: int, user_id: int, mod_id: int,
                           action: str, reason: str, case_id=None,
                           warn_id=None):
    """V2 чёрное меню + select со стикерами; фолбэк — View с select."""
    from services.v2_layouts import V2_AVAILABLE, black_container
    action_ru = _action_key_ru(action)
    sel = ProofOfferSelect(
        guild_id=guild_id, user_id=user_id, mod_id=mod_id,
        action=action, reason=reason, case_id=case_id, warn_id=warn_id)
    if V2_AVAILABLE:
        from discord import ui as dui, SeparatorSpacing
        view = dui.LayoutView(timeout=300)
        row = dui.ActionRow()
        row.add_item(sel)
        view.add_item(black_container(
            dui.TextDisplay('# 🤍 Доказательство'),
            dui.TextDisplay('-# HAKUMO · демка к наказанию'),
            dui.Separator(spacing=SeparatorSpacing.large),
            dui.TextDisplay(
                f'Наказание **{action_ru}** уже выдано.\n'
                'Прикрепи фото или видео **файлом** — необязательно.'),
            dui.Separator(),
            row,
        ))
        return view
    view = discord.ui.View(timeout=300)
    view.add_item(sel)
    return view


class ProofRejectReasonModal(discord.ui.Modal, title='Отклонить демку'):
    reason = discord.ui.TextInput(
        label='Причина отклонения',
        placeholder='Почему демка не подходит / наказание снимаем',
        style=discord.TextStyle.paragraph, max_length=400, required=True)

    def __init__(self, entry_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.entry_id = int(entry_id)
        self.guild_id = int(guild_id)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ok, msg = await _review_proof(
            interaction, self.guild_id, self.entry_id,
            accept=False, reason=str(self.reason.value or ''))
        await interaction.followup.send(msg, ephemeral=True)


class ProofReviewSelect(discord.ui.Select):
    """Select на карточке демки: Принять / Отклонить — 🤍."""

    def __init__(self, entry_id: int = 0, guild_id: int = 0):
        from services.menu_banners import select_label
        self.entry_id = int(entry_id or 0)
        self.guild_id = int(guild_id or 0)
        super().__init__(
            placeholder='Выберите решение',
            custom_id='proof_review_select_v1',
            min_values=1, max_values=1,
            options=[
                discord.SelectOption(
                    label=select_label('Принять'),
                    value='accept', emoji='🤍'),
                discord.SelectOption(
                    label=select_label('Отклонить'),
                    value='reject', emoji='🤍'),
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        gid = self.guild_id or int(getattr(interaction.guild, 'id', 0) or 0)
        eid = self.entry_id or _entry_id_from_message(interaction)
        if not eid:
            return await interaction.response.send_message(
                'Запись демки не найдена.', ephemeral=True)
        choice = (self.values or [''])[0]
        if choice == 'reject':
            return await interaction.response.send_modal(
                ProofRejectReasonModal(eid, gid))
        await interaction.response.defer(ephemeral=True)
        ok, msg = await _review_proof(
            interaction, gid, eid, accept=True, reason='')
        await interaction.followup.send(msg, ephemeral=True)


class ProofReviewView(discord.ui.View):
    """Persistent select на карточке доказательств (фолбэк без LayoutView)."""

    def __init__(self, entry_id: int = 0, guild_id: int = 0):
        super().__init__(timeout=None)
        self.entry_id = int(entry_id or 0)
        self.guild_id = int(guild_id or 0)
        self.add_item(ProofReviewSelect(self.entry_id, self.guild_id))


def _entry_id_from_message(interaction) -> int:
    try:
        mid = int(getattr(interaction.message, 'id', 0) or 0)
        gid = int(getattr(interaction.guild, 'id', 0) or 0)
        for en in proof_list(gid, limit=200):
            if int(en.get('msg_id') or 0) == mid:
                return int(en.get('id') or 0)
    except Exception:
        pass
    return 0


def _can_review_proof(member) -> bool:
    if member is None:
        return False
    try:
        from config import Config
        mid = int(getattr(member, 'id', 0) or 0)
        if mid and mid in Config.all_owner_ids():
            return True
        guild = getattr(member, 'guild', None)
        if guild and mid and int(getattr(guild, 'owner_id', 0) or 0) == mid:
            return True
    except Exception:
        pass
    try:
        ids = {int(getattr(r, 'id', 0) or 0)
               for r in (getattr(member, 'roles', None) or [])}
        return PROOF_REVIEW_ROLE_ID in ids
    except Exception:
        return False


async def _undo_punishment(bot, guild, entry, reviewer, reason: str) -> str:
    """Снять мут / не считать варн при отклонении демки."""
    uid = int(entry.get('user_id') or 0)
    action = _action_key_ru(entry.get('action') or '')
    member = guild.get_member(uid)
    if member is None:
        try:
            member = await guild.fetch_member(uid)
        except Exception:
            member = None
    notes = []
    # варн — снять последний, если совпал
    if action == 'варн' or entry.get('warn_id'):
        try:
            wc = bot.get_cog('warnings')
            if wc is not None and member is not None:
                removed, total = await wc.remove_last_warning(member, reviewer)
                if removed:
                    notes.append(f'варн #{removed.get("id")} снят · осталось {total}')
                else:
                    notes.append('варнов не было')
        except Exception as ex:
            notes.append(f'варн: {ex}')
    # муты
    if action in ('мут', 'мут чата', 'войс-мут') or entry.get('action_key') in (
            'timeout', 'mute_chat', 'vmute'):
        try:
            from services import mute_state
            if member is not None:
                key = entry.get('action_key') or ''
                if key == 'vmute' or action == 'войс-мут':
                    await mute_state.clear_voice_mute(guild, member)
                    notes.append('войс-мут снят')
                else:
                    await mute_state.clear_all_mutes(guild, member)
                    notes.append('мут снят')
        except Exception as ex:
            notes.append(f'мут: {ex}')
    # бан-роль
    if action == 'бан' or entry.get('action_key') == 'ban':
        try:
            from services import punish_roles as PR
            rid = int(PR.role_for(guild.id, 'ban') or 0)
            role = guild.get_role(rid) if rid else None
            if role and member is not None and role in member.roles:
                await member.remove_roles(role, reason=f'демка отклонена: {reason}'[:200])
                notes.append('роль бана снята')
        except Exception as ex:
            notes.append(f'бан: {ex}')
    return ' · '.join(notes) if notes else 'наказание не трогали'


async def _review_proof(interaction, guild_id, entry_id, *, accept: bool,
                        reason: str) -> tuple:
    bot = interaction.client
    guild = interaction.guild or bot.get_guild(int(guild_id or 0))
    if guild is None:
        return False, 'Сервер не найден.'
    reviewer = interaction.user
    try:
        mem = guild.get_member(int(getattr(reviewer, 'id', 0) or 0))
        if mem is not None:
            reviewer = mem
    except Exception:
        pass
    if not _can_review_proof(reviewer):
        return False, f'Только <@&{PROOF_REVIEW_ROLE_ID}> принимает/отклоняет демки.'
    entry = None
    for en in proof_list(guild_id, limit=500):
        if int(en.get('id') or 0) == int(entry_id):
            entry = en
            break
    if not entry:
        return False, f'Демка #{entry_id} не найдена.'
    if entry.get('review_status') in ('accepted', 'rejected'):
        return False, f'Уже решено: {entry.get("review_status")}.'
    status = 'accepted' if accept else 'rejected'
    undo = ''
    if accept:
        proof_update(guild_id, entry_id,
                     review_status=status,
                     reviewed_by=str(getattr(reviewer, 'id', '')),
                     review_reason='')
        reply = 'Демка принята — наказание остаётся.'
    else:
        undo = await _undo_punishment(
            bot, guild, entry, reviewer, reason or 'демка отклонена')
        proof_update(guild_id, entry_id,
                     review_status=status,
                     reviewed_by=str(getattr(reviewer, 'id', '')),
                     review_reason=(reason or '')[:400],
                     undo_note=undo)
        reply = f'Демка отклонена. {undo}'

    # Закрыть карточку как анкету: статус сверху + тело + медиа, без select
    try:
        mid = int(entry.get('msg_id') or 0)
        cid = int(entry.get('channel_id') or 0)
        ch = guild.get_channel(cid) if cid else None
        if ch and mid:
            msg = await ch.fetch_message(mid)
            media_urls = []
            for a in (getattr(msg, 'attachments', None) or []):
                u = getattr(a, 'url', None)
                if u:
                    media_urls.append(u)
            if not media_urls and entry.get('url'):
                media_urls.append(str(entry['url']))
            body = _proof_card_body(entry)
            status_label, note, accent = _proof_decision_note(
                'accept' if accept else 'reject', reviewer,
                extra=undo, reject_reason=reason or '')
            view = ProofReviewDoneView(
                entry_id=entry_id,
                action=entry.get('action') or '',
                body=body,
                status=status_label,
                note=note,
                media_urls=media_urls,
                accent=accent,
            )
            try:
                await msg.edit(view=view, attachments=[])
            except TypeError:
                await msg.edit(view=view)
            except Exception as ex1:
                log.warning('[PROOF] edit decided: %s', ex1)
                try:
                    await msg.edit(view=view)
                except Exception as ex2:
                    log.warning('[PROOF] edit decided retry: %s', ex2)
    except Exception as ex:
        log.warning('[PROOF] close card: %s', ex)
    return True, reply


def _proof_card_body(entry: dict) -> str:
    """Текст карточки демки (как до решения)."""
    uid = entry.get('user_id')
    mention = f'<@{uid}>' if uid else '—'
    mod = entry.get('mod_name') or entry.get('mod_id') or '—'
    action = entry.get('action') or '—'
    reason = entry.get('reason') or '—'
    pid = entry.get('id') or '?'
    lines = [
        f'**Нарушитель** · {mention} (`{uid}`)',
        f'**Модератор** · `{mod}`',
        f'**Наказание** · {action}',
        f'**Причина** · {reason}',
        f'**Дело** · #{pid}',
    ]
    if entry.get('case_id'):
        lines[-1] += f' · case `{entry["case_id"]}`'
    return '\n'.join(lines)


def _proof_decision_note(action: str, reviewer, *, extra: str = '',
                         reject_reason: str = '') -> tuple:
    """(status_label, note, accent) — как у закрытых анкет."""
    from datetime import datetime, timezone
    when = datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')
    who = (
        getattr(reviewer, 'display_name', None)
        or getattr(reviewer, 'global_name', None)
        or getattr(reviewer, 'name', None)
        or str(reviewer)
    )
    ok = action == 'accept'
    status = 'ПРИНЯТО' if ok else 'ОТКЛОНЕНО'
    verb = 'Принял' if ok else 'Отклонил'
    accent = 0x2ECC71 if ok else 0xE74C3C
    note = f'{verb}: {who} · {when}'
    if reject_reason and not ok:
        note += f'\nПричина: {reject_reason[:200]}'
    if extra and not ok:
        note += f'\n{extra[:200]}'
    return status, note, accent


class ProofReviewDoneView(discord.ui.LayoutView):
    """После решения: как закрытая анкета — статус + тело + медиа, без select."""

    def __init__(self, *, entry_id, action: str, body: str, status: str,
                 note: str = '', media_urls=None, accent: int = 0xE74C3C):
        super().__init__(timeout=None)
        from services.v2_layouts import V2_AVAILABLE, black_container
        from discord import SeparatorSpacing
        from discord.components import MediaGalleryItem
        head = f'# 🤍 Демка #{entry_id}'
        if action:
            head = f'{head} · {action}'
        status_line = f'## {status}'
        if note:
            status_line = f'{status_line}\n-# {note}'
        if V2_AVAILABLE:
            from discord import ui as dui
            children = [
                dui.TextDisplay(head[:500]),
                dui.TextDisplay('-# HAKUMO · доказательство'),
                dui.Separator(spacing=SeparatorSpacing.large),
                dui.TextDisplay(status_line[:800]),
                dui.Separator(),
                dui.TextDisplay(str(body)[:3500]),
            ]
            urls = [u for u in (media_urls or []) if u][:10]
            if urls:
                try:
                    children.append(dui.Separator())
                    children.append(dui.MediaGallery(
                        *[MediaGalleryItem(u) for u in urls]))
                except Exception:
                    pass
            self.add_item(black_container(*children, accent=accent))


async def post_proof_review_card(bot, guild, moderator, user, *, action, reason,
                                 attachments, case_id=None, warn_id=None):
    """Карточка в канал доказательств: медиа + принять/отклонить."""
    from services.v2_layouts import V2_AVAILABLE, black_container
    from discord.components import MediaGalleryItem

    action_ru = _action_key_ru(action)
    action_key = {
        'варн': 'warn', 'мут': 'timeout', 'мут чата': 'mute_chat',
        'войс-мут': 'vmute', 'бан': 'ban', 'кик': 'kick',
    }.get(action_ru, str(action or ''))

    cog = bot.get_cog('ProofCog') if bot else None
    if cog is None:
        return False, None

    files = []
    gallery_names = []
    for i, att in enumerate(attachments or []):
        try:
            raw = await att.read()
        except Exception:
            continue
        if not raw:
            continue
        name = getattr(att, 'filename', None) or f'proof_{i}.bin'
        # уникальные имена — иначе Discord схлопнет attachment://
        safe = f'{i}_{name}'
        files.append(discord.File(io.BytesIO(raw), filename=safe))
        gallery_names.append(safe)

    entry = proof_add(
        guild.id, user.id, str(user),
        moderator.id, str(moderator), action_ru, reason, link=None)
    proof_update(
        guild.id, entry['id'],
        review_status='pending',
        action_key=action_key,
        case_id=case_id,
        warn_id=warn_id,
    )
    entry.update({
        'review_status': 'pending',
        'action_key': action_key,
        'case_id': case_id,
        'warn_id': warn_id,
    })

    ch = await cog._proof_channel(guild)
    if ch is None:
        return False, entry

    mention = getattr(user, 'mention', None) or f'<@{user.id}>'
    mod_m = getattr(moderator, 'mention', None) or str(moderator)
    body = (
        f'**Нарушитель** · {mention} (`{user.id}`)\n'
        f'**Модератор** · {mod_m}\n'
        f'**Наказание** · {action_ru}\n'
        f'**Причина** · {(reason or "—")[:500]}\n'
        f'**Дело** · #{entry["id"]}'
        + (f' · case `{case_id}`' if case_id else '')
    )

    # silent ping «отвечаю за мод»
    try:
        await ch.send(
            f'<@&{PROOF_REVIEW_ROLE_ID}>',
            allowed_mentions=discord.AllowedMentions(roles=True),
            flags=discord.MessageFlags(suppress_notifications=True),
        )
    except Exception as ex:
        log.debug('[PROOF] silent ping: %s', ex)

    rev = ProofReviewView(entry['id'], guild.id)
    try:
        if V2_AVAILABLE:
            from discord import ui as dui, SeparatorSpacing
            head = f'# 🤍 Демка #{entry["id"]} · {action_ru}'
            children = [
                dui.TextDisplay(head[:500]),
                dui.TextDisplay('-# HAKUMO · доказательство'),
                dui.Separator(spacing=SeparatorSpacing.large),
                dui.TextDisplay(body[:3500]),
            ]
            if gallery_names:
                items = [MediaGalleryItem(f'attachment://{n}')
                         for n in gallery_names[:10]]
                children.append(dui.Separator())
                children.append(dui.MediaGallery(*items))
            children.append(dui.Separator())
            row = dui.ActionRow()
            row.add_item(ProofReviewSelect(entry['id'], guild.id))
            children.append(row)
            lv = dui.LayoutView(timeout=None)
            lv.add_item(black_container(*children))
            msg = await ch.send(view=lv, files=files or None)
        else:
            e = discord.Embed(
                title=f'Демка #{entry["id"]} · {action_ru}',
                description=body, color=0x000000, timestamp=_now())
            e.set_footer(text='HAKUMO · доказательство')
            if gallery_names and _is_image_name(gallery_names[0]):
                e.set_image(url=f'attachment://{gallery_names[0]}')
            msg = await ch.send(embed=e, files=files or None, view=rev)
    except Exception as ex:
        log.warning('[PROOF] send review card: %s', ex)
        try:
            e = discord.Embed(
                title=f'Демка #{entry["id"]} · {action_ru}',
                description=body, color=0x000000)
            e.set_footer(text='HAKUMO · доказательство')
            msg = await ch.send(embed=e, files=files or None, view=rev)
        except Exception as ex2:
            log.warning('[PROOF] fallback send: %s', ex2)
            return False, entry

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
    return True, entry


async def offer_proof_after_punish(interaction, *, user, action, reason,
                                   case_id=None, warn_id=None):
    """После наказания — эфемерное V2-меню с select (необязательно)."""
    try:
        if interaction is None or user is None:
            return
        guild = interaction.guild
        if guild is None:
            return
        view = build_proof_offer_view(
            guild_id=guild.id,
            user_id=int(getattr(user, 'id', 0) or 0),
            mod_id=int(getattr(interaction.user, 'id', 0) or 0),
            action=action, reason=reason or '',
            case_id=case_id, warn_id=warn_id,
        )
        send = getattr(interaction, 'followup', None)
        if send is not None:
            # V2: без content (Discord 50035). Фолбэк View — короткий текст.
            from services.v2_layouts import V2_AVAILABLE
            kwargs = {'view': view, 'ephemeral': True}
            if not V2_AVAILABLE:
                kwargs['content'] = (
                    f'Доказательство · наказание уже выдано.\n'
                    f'Прикрепи файл или пропусти.')
            await send.send(**kwargs)
    except Exception as ex:
        log.debug('[PROOF] offer after punish: %s', ex)


async def setup(bot):
    await bot.add_cog(ProofCog(bot))
    try:
        bot.add_view(ProofReviewView())
    except Exception as ex:
        log.debug('[PROOF] add_view review: %s', ex)
    log.info('[PROOF] Ког загружен (демки к наказаниям)')
