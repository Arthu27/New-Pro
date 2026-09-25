# -*- coding: utf-8 -*-
"""LFG-каналы (знакомства / тиммейты): правила как в знакомствах.

На HAKUMO:
  💕・знакомства — эталон (18+, оффтоп/реклама серверов запрещены, всё в ЛС)
  🎯・тиммейты   — тот же режим правил + анти-реклама через auto_filter.ads

Правила — Components V2 (чёрный контейнер), только лично нарушителю в ЛС,
не в общий чат.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from logger import get_logger

log = get_logger('lfg_channels')

# HAKUMO main guild
MAIN_GUILD_ID = 793336829280780331
DATING_CHANNEL_ID = 1312430207067623456   # 💕・знакомства
TEAMMATES_CHANNEL_ID = 1312552287360516207  # 🎯・тиммейты

LFG_CHANNEL_IDS = (DATING_CHANNEL_ID, TEAMMATES_CHANNEL_ID)

TEAMMATES_TOPIC = (
    'канал для поиска тиммейтов, оффтоп не по поиску запрещён, '
    'все обсуждается в лс, реклама своих серверов запрещена.'
)

# v2: публичную карточку больше не постим; маркер = topic/overwrite sync
RULES_MARKER = 'data/.lfg_teammates_rules.v2'
# старый публичный embed — снести при синке
LEGACY_RULES_MARKER = 'data/.lfg_teammates_rules.v1'

RULES_BODY_TEAMMATES = (
    '• Канал **только** для поиска тиммейтов / пати.\n'
    '• Оффтоп не по поиску — запрещён.\n'
    '• Всё обсуждение — **в ЛС**, не в чате.\n'
    '• **Реклама своих Discord-серверов запрещена** '
    '(«Залетай на наш Discord-сервер», discord.gg и т.п.) — '
    'удаляется автоматически.'
)

RULES_BODY_DATING = (
    '• Канал **строго 18+**, только поиск общения / отношений.\n'
    '• Оффтоп не по поиску — запрещён.\n'
    '• Всё обсуждение — **в ЛС**, не в чате.\n'
    '• **Реклама своих Discord-серверов запрещена** '
    '(«Залетай на наш Discord-сервер», discord.gg и т.п.) — '
    'удаляется автоматически.'
)

RULES_TITLE = {
    'teammates': '🎯・тиммейты — правила',
    'dating': '💕・знакомства — правила',
}


def marker_path() -> Path:
    return Path(os.environ.get('LFG_MARKER') or RULES_MARKER)


def ads_apply_channels() -> list[str]:
    """ID каналов для auto_filter.ads.apply_channels."""
    return [str(DATING_CHANNEL_ID), str(TEAMMATES_CHANNEL_ID)]


def channel_kind(channel_id) -> str:
    """teammates | dating | ''."""
    cid = str(channel_id or '')
    if cid == str(TEAMMATES_CHANNEL_ID):
        return 'teammates'
    if cid == str(DATING_CHANNEL_ID):
        return 'dating'
    return ''


def build_lfg_rules_view(*, kind: str = 'teammates'):
    """V2 чёрная карточка правил LFG (LayoutView) или None."""
    try:
        from services.v2_layouts import V2_AVAILABLE, notice_layout_view
    except Exception:
        return None
    if not V2_AVAILABLE:
        return None
    kind = kind if kind in RULES_TITLE else 'teammates'
    body = RULES_BODY_DATING if kind == 'dating' else RULES_BODY_TEAMMATES
    return notice_layout_view(
        title=RULES_TITLE[kind],
        body=body,
        footer='Hakumo · правила LFG',
        accent=0x000000,
        brand='HAKUMO',
        timeout=None,
    )


def build_lfg_rules_embed(*, kind: str = 'teammates'):
    """Фолбек-эмбед, если V2 недоступен."""
    import discord
    kind = kind if kind in RULES_TITLE else 'teammates'
    body = RULES_BODY_DATING if kind == 'dating' else RULES_BODY_TEAMMATES
    e = discord.Embed(color=0x000000)
    e.description = f'## {RULES_TITLE[kind]}\n{body}'
    e.set_footer(text='Hakumo · правила LFG')
    return e


async def send_rules_private(user, *, kind: str = 'teammates',
                             channel_id=None) -> bool:
    """Показать правила только этому пользователю (ЛС).

    Ephemeral в Discord возможен только на interaction — для автофильтра
    это ЛС. Возвращает True, если ушло.
    """
    if channel_id:
        k = channel_kind(channel_id)
        if k:
            kind = k
    view = build_lfg_rules_view(kind=kind)
    embed = build_lfg_rules_embed(kind=kind)
    try:
        if view is not None:
            await user.send(view=view)
        else:
            await user.send(embed=embed)
        return True
    except Exception as e:
        log.info('lfg: private rules DM failed for %s: %s',
                 getattr(user, 'id', '?'), e)
        return False


def ensure_autofilter_ads(gid: int = MAIN_GUILD_ID) -> dict:
    """Один раз включить ads на знакомствах + тиммейтах; далее не форсим."""
    from cogs import auto_filter as AF
    seed = Path('data/.lfg_ads_seed.v1')
    cfg = AF.load_config(gid)
    ads = cfg.setdefault('ads', {})
    wanted = ads_apply_channels()
    # Первичный сид: включаем фильтр и сужаем к LFG-каналам.
    if not seed.exists():
        cfg['enabled'] = True
        ads['enabled'] = True
        ads['action'] = 'delete'
        ads['builtin'] = True
        ads['phrases'] = list(ads.get('phrases') or [])
        ads['apply_channels'] = wanted
        AF.save_config(gid, cfg)
        try:
            seed.parent.mkdir(parents=True, exist_ok=True)
            seed.write_text(
                json.dumps({'guild_id': gid, 'channels': wanted}, ensure_ascii=False),
                encoding='utf-8',
            )
        except Exception as e:
            log.warning('lfg: seed marker write failed: %s', e)
        log.info('lfg: autofilter ads seeded for guild %s → %s', gid, wanted)
        return cfg
    # Уже сидили: только дописываем LFG-каналы в apply_channels, если список есть.
    cur = [str(x) for x in (ads.get('apply_channels') or [])]
    if cur:
        merged = list(dict.fromkeys(cur + wanted))
        if merged != cur:
            ads['apply_channels'] = merged
            AF.save_config(gid, cfg)
            log.info('lfg: ads apply_channels merged → %s', merged)
    return cfg


async def _purge_legacy_public_rules(ch) -> int:
    """Снести старую публичную карточку правил (embed / v1)."""
    removed = 0
    bot_user = getattr(ch.guild, 'me', None)
    bot_id = getattr(bot_user, 'id', None)
    try:
        async for msg in ch.history(limit=40):
            if bot_id and getattr(msg.author, 'id', None) != bot_id:
                continue
            text = (msg.content or '')
            desc = ''
            if msg.embeds:
                desc = str(getattr(msg.embeds[0], 'description', '') or '')
            blob = (text + '\n' + desc).lower()
            if 'правила как в знакомствах' in blob or 'правила lfg' in blob \
                    or 'реклама своих discord' in blob:
                try:
                    await msg.delete()
                    removed += 1
                except Exception:
                    pass
    except Exception as e:
        log.debug('lfg: purge legacy: %s', e)
    return removed


async def sync_teammates_channel(bot) -> dict:
    """Выровнять #тиммейты под #знакомства. Правила — только в ЛС (V2).

    Returns dict with keys: topic, overwrite, legacy_purged, errors.
    """
    out = {
        'topic': False, 'overwrite': False, 'legacy_purged': 0,
        'rules_posted': False, 'errors': [],
    }
    guild = bot.get_guild(MAIN_GUILD_ID)
    if guild is None:
        out['errors'].append('guild_missing')
        return out
    ch = guild.get_channel(TEAMMATES_CHANNEL_ID)
    if ch is None:
        out['errors'].append('channel_missing')
        return out
    me = guild.me
    # topic
    try:
        if (ch.topic or '').strip() != TEAMMATES_TOPIC:
            await ch.edit(topic=TEAMMATES_TOPIC, reason='LFG: как в знакомствах')
        out['topic'] = True
    except Exception as e:
        out['errors'].append(f'topic:{type(e).__name__}')
        log.warning('lfg: topic edit failed: %s', e)
    # manage_messages for bot (как member overwrite на знакомствах)
    if me is not None:
        try:
            perms = ch.permissions_for(me)
            if not perms.manage_messages:
                await ch.set_permissions(
                    me, manage_messages=True,
                    reason='LFG: удаление рекламы серверов',
                )
            out['overwrite'] = True
        except Exception as e:
            out['errors'].append(f'overwrite:{type(e).__name__}')
            log.warning('lfg: overwrite failed: %s', e)

    # убрать публичный embed v1 (один раз)
    marker = marker_path()
    legacy = Path(LEGACY_RULES_MARKER)
    if legacy.exists() or not marker.exists():
        try:
            out['legacy_purged'] = await _purge_legacy_public_rules(ch)
        except Exception as e:
            out['errors'].append(f'purge:{type(e).__name__}')
            log.warning('lfg: purge failed: %s', e)
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps({
                'channel_id': TEAMMATES_CHANNEL_ID,
                'topic_ok': out['topic'],
                'overwrite_ok': out['overwrite'],
                'private_v2': True,
                'legacy_purged': out['legacy_purged'],
            }, ensure_ascii=False), encoding='utf-8')
            if legacy.exists():
                try:
                    legacy.unlink()
                except Exception:
                    pass
            log.info('lfg: private V2 rules mode (purged=%s)', out['legacy_purged'])
        except Exception as e:
            out['errors'].append(f'marker:{type(e).__name__}')
            log.warning('lfg: marker write failed: %s', e)
    return out
