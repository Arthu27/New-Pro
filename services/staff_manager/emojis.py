# -*- coding: utf-8 -*-
"""Эмодзи Staff Manager: иконки Discord-ролей → application emoji."""
from __future__ import annotations

import re
from typing import Dict, Optional

from logger import get_logger
from services.staff_manager.config import get_config, get_index
from services.staff_manager.store import get_emoji_cache, save_emoji_cache

_log = get_logger('staff_manager.emojis')

# runtime: key -> PartialEmoji-compatible string <:name:id>
_RUNTIME: Dict[str, str] = {}


def _safe_name(prefix: str, key: str) -> str:
    raw = f'{prefix}_{key}'.lower()
    raw = re.sub(r'[^a-z0-9_]', '', raw)
    return raw[:32] or f'{prefix}_x'


def emoji_str(kind: str, key: str, fallback: str = '•') -> str:
    k = f'{kind}:{key}'
    if k in _RUNTIME:
        return _RUNTIME[k]
    return fallback or '•'


def _is_safe_unicode_emoji(s: str) -> bool:
    """Discord отвергает часть символов (✦ ✧ •) как emoji.name на кнопках/select."""
    if not s or len(s) > 8:
        return False
    bad = {'•', '✦', '✧', '·', '—', '-', '>', '<'}
    if s in bad:
        return False
    try:
        import unicodedata
        return any(
            unicodedata.category(ch) in ('So', 'Sk') or ord(ch) > 0x1F000
            for ch in s
        )
    except Exception:
        return False


def partial_emoji(kind: str, key: str, fallback: str | None = None):
    """discord.PartialEmoji или unicode/None для SelectOption."""
    import discord
    s = emoji_str(kind, key, fallback or '')
    if not s or s == '•':
        # fallback unicode (ROLE_EMOJIS) — только если Discord примет
        fb = fallback or ''
        if fb and _is_safe_unicode_emoji(fb):
            return fb
        return None
    if s.startswith('<') and ':' in s:
        try:
            return discord.PartialEmoji.from_str(s)
        except Exception:
            return None
    if _is_safe_unicode_emoji(s):
        return s
    return None


async def ensure_role_emojis(bot, guild) -> Dict[str, str]:
    """Скачать role.icon и создать/найти application emoji sm_*."""
    cfg = get_config() or {}
    idx = get_index() or {}
    out: Dict[str, str] = {}

    # ladder keys → role_id (берём из любой ветки)
    ladder_rids: Dict[str, int] = {}
    for b in (cfg.get('branches') or {}).values():
        for k, rid in (b.get('roles') or {}).items():
            rid = int(rid or 0)
            if rid and k not in ladder_rids:
                ladder_rids[k] = rid

    # branch → entry role
    branch_rids: Dict[str, int] = {}
    for bkey, b in (cfg.get('branches') or {}).items():
        rid = int(b.get('entry_role_id') or 0)
        if rid:
            branch_rids[bkey] = rid

    try:
        app_emojis = {e.name: e for e in await bot.fetch_application_emojis()}
    except Exception as ex:
        _log.error('fetch_application_emojis: %s', ex)
        app_emojis = {}

    async def _one(kind: str, key: str, role_id: int, fallback: str) -> str:
        cache_key = f'{kind}:{key}'
        cached = get_emoji_cache(guild.id, kind, key)
        if cached and cached.startswith('<'):
            _RUNTIME[cache_key] = cached
            out[cache_key] = cached
            return cached

        role = guild.get_role(int(role_id))
        name = _safe_name('sm' if kind == 'role' else 'smb', key)
        # reuse existing
        if name in app_emojis:
            em = app_emojis[name]
            s = str(em)
            save_emoji_cache(guild.id, kind, key, s, 'app_existing')
            _RUNTIME[cache_key] = s
            out[cache_key] = s
            _log.info('emoji %s = %s (existing)', cache_key, s)
            return s

        # create from role icon
        if role is not None and getattr(role, 'icon', None):
            try:
                data = await role.icon.read()
                em = await bot.create_application_emoji(name=name, image=data)
                app_emojis[name] = em
                s = str(em)
                save_emoji_cache(guild.id, kind, key, s, 'role_icon')
                _RUNTIME[cache_key] = s
                out[cache_key] = s
                _log.info('emoji %s = %s (created from role icon)', cache_key, s)
                return s
            except Exception as ex:
                _log.warning('create emoji %s from role %s: %s', name, role_id, ex)

        # unicode / config fallback
        s = fallback or '•'
        save_emoji_cache(guild.id, kind, key, s, 'fallback')
        _RUNTIME[cache_key] = s
        out[cache_key] = s
        return s

    role_fb = cfg.get('role_emojis') or {}
    for key, rid in ladder_rids.items():
        await _one('role', key, rid, role_fb.get(key) or '•')

    branch_fb = cfg.get('branch_emojis') or {}
    # prefer existing hakumo branch emojis if no role icon needed
    branch_alias = {
        'moderators': 'hakumo_w2_moderator',
        'helpers': 'hakumo_w2_helper',
        'event': 'hakumo_w4_eventsmod',
        'broadcaster': 'hakumo_w4_broadcaster',
        'support': 'hakumo_w2_staff',
        'closemod': 'hakumo_w2_moderator',
        'creative': 'hakumo_w2_heart',
    }
    for bkey, rid in branch_rids.items():
        alias = branch_alias.get(bkey)
        if alias and alias in app_emojis:
            s = str(app_emojis[alias])
            save_emoji_cache(guild.id, 'branch', bkey, s, 'app_alias')
            _RUNTIME[f'branch:{bkey}'] = s
            out[f'branch:{bkey}'] = s
            continue
        await _one('branch', bkey, rid, branch_fb.get(bkey) or '•')

    return out


def action_emoji(action: str):
    mapping = {
        'assign': 'hakumo_w2_staff',
        'promote': 'hakumo_w4_accept',
        'demote': 'hakumo_w2_reject',
        'remove': 'hakumo_w2_ban',
        'transfer': 'hakumo_w2_claim',
        'probation': 'hakumo_w2_warn',
        'vacation': 'hakumo_w2_heart',
        'history': 'hakumo_w2_elist',
        'request': 'hakumo_w2_signup',
        'self_leave': 'hakumo_w2_finish',
    }
    name = mapping.get(action)
    if not name:
        return None
    # look up from runtime app cache if we stored full strings
    for k, v in _RUNTIME.items():
        if name in v:
            return v
    # construct if we know common ids from server — leave None, filled at boot
    return _RUNTIME.get(f'action:{action}')


async def ensure_action_emojis(bot) -> None:
    try:
        app = {e.name: e for e in await bot.fetch_application_emojis()}
    except Exception:
        return
    mapping = {
        'assign': 'hakumo_w2_staff',
        'promote': 'hakumo_w4_accept',
        'demote': 'hakumo_w2_reject',
        'remove': 'hakumo_w2_ban',
        'transfer': 'hakumo_w2_claim',
        'probation': 'hakumo_w2_warn',
        'vacation': 'hakumo_w2_heart',
        'history': 'hakumo_w2_elist',
        'request': 'hakumo_w2_signup',
        'self_leave': 'hakumo_w2_finish',
    }
    for act, name in mapping.items():
        em = app.get(name)
        if em:
            _RUNTIME[f'action:{act}'] = str(em)
