# -*- coding: utf-8 -*-
"""LFG-каналы (знакомства / тиммейты): правила как в знакомствах.

На HAKUMO:
  💕・знакомства — эталон (18+, оффтоп/реклама серверов запрещены, всё в ЛС)
  🎯・тиммейты   — тот же режим правил + анти-реклама через auto_filter.ads

Бот без Manage Channels не всегда может править topic/overwrite —
тогда публикуем карточку правил один раз (маркер в data/).
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

RULES_MARKER = 'data/.lfg_teammates_rules.v1'

RULES_TEXT = (
    '## 🎯・тиммейты — правила как в знакомствах\n'
    '• Канал **только** для поиска тиммейтов / пати.\n'
    '• Оффтоп не по поиску — запрещён.\n'
    '• Всё обсуждение — **в ЛС**, не в чате.\n'
    '• **Реклама своих Discord-серверов запрещена** '
    '(«Залетай на наш Discord-сервер», discord.gg и т.п.) — удаляется автоматически.\n'
)


def marker_path() -> Path:
    return Path(os.environ.get('LFG_MARKER') or RULES_MARKER)


def ads_apply_channels() -> list[str]:
    """ID каналов для auto_filter.ads.apply_channels."""
    return [str(DATING_CHANNEL_ID), str(TEAMMATES_CHANNEL_ID)]


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


async def sync_teammates_channel(bot) -> dict:
    """Выровнять #тиммейты под #знакомства + опубликовать правила при нужде.

    Returns dict with keys: topic, overwrite, rules_posted, errors.
    """
    out = {'topic': False, 'overwrite': False, 'rules_posted': False, 'errors': []}
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
    # карточка правил, если topic/overwrite не вышли и маркер ещё не стоит
    marker = marker_path()
    if not marker.exists():
        try:
            import discord
            emb = discord.Embed(color=0xD4AF37, description=RULES_TEXT)
            emb.set_footer(text='Hakumo · правила LFG')
            await ch.send(embed=emb)
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps({
                'channel_id': TEAMMATES_CHANNEL_ID,
                'topic_ok': out['topic'],
                'overwrite_ok': out['overwrite'],
            }, ensure_ascii=False), encoding='utf-8')
            out['rules_posted'] = True
            log.info('lfg: rules card posted in teammates')
        except Exception as e:
            out['errors'].append(f'rules:{type(e).__name__}')
            log.warning('lfg: rules post failed: %s', e)
    return out
