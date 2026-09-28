# -*- coding: utf-8 -*-
"""Сид роли «Ведущий» (broadcasters / love-room host).

Резолв: VEDUSHIY_ROLE_ID → известный Broadcaster → имя «Ведущий» /
алиасы ведущий|vedushiy|broadcaster.

Discord-права (документируем; API-правка только при VEDUSHIY_FORCE_PERMS=1):
  • Move Members
  • Mute Members
  • Deafen Members
Stage «Поднять/Опустить» = Member.edit(suppress=False/True) — не modpanel.

НЕ выдаёт action_acl ban/kick/mute/timeout (без punish ACL).
Идемпотентно: маркер data/.vedushiy_role.v<N>.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from logger import get_logger

_log = get_logger('vedushiy_role_seed')

SEED_VERSION = 1
MARKER = f'data/.vedushiy_role.v{SEED_VERSION}'
_DEMO_GUILD = 987654321098765432

# Известный Broadcaster grant (staff-apply history) — алиас, не обязателен.
KNOWN_BROADCASTER_ROLE_ID = 1551180629687664670

ROLE_NAME = 'Ведущий'
NAME_ALIASES = (
    'ведущий',
    'vedushiy',
    'broadcaster',
    'broadcasters',
    ROLE_NAME.lower(),
)

# Discord permission bits for voice/stage host (no Manage Guild / Ban / Kick).
VOICE_HOST_PERMS = (
    'move_members',
    'mute_members',
    'deafen_members',
)


def _truthy(val: str | None) -> bool:
    return str(val or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _main_guild_id(override=None) -> Optional[int]:
    try:
        gid = int(override or 0)
    except (TypeError, ValueError):
        gid = 0
    if not gid:
        try:
            from config import Config
            gid = int(getattr(Config, 'MAIN_GUILD_ID', 0) or 0)
        except Exception:
            gid = 0
    if not gid:
        try:
            gid = int((os.environ.get('LOVE_ROOM_GUILD_ID')
                       or os.environ.get('MAIN_GUILD_ID') or 0) or 0)
        except (TypeError, ValueError):
            gid = 0
    if gid and gid != _DEMO_GUILD:
        return gid
    return None


def env_vedushiy_role_id() -> int:
    for key in ('VEDUSHIY_ROLE_ID', 'HOST_ROLE_ID'):
        raw = (os.environ.get(key) or '').strip()
        if not raw or raw in ('0', 'none', 'None'):
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return 0


def resolve_vedushiy_role_id(guild=None, override_id: int | None = None) -> int:
    """Найти ID роли Ведущий: env → override → known → имя на гильдии."""
    rid = int(override_id or 0) or env_vedushiy_role_id()
    if rid:
        return rid
    if guild is not None:
        found = find_vedushiy_role(guild)
        if found is not None:
            try:
                return int(found.id)
            except Exception:
                pass
    return int(KNOWN_BROADCASTER_ROLE_ID or 0)


def _norm_name(name: str) -> str:
    return (name or '').strip().lower().replace('ё', 'е')


def find_vedushiy_role(guild) -> Any:
    """discord.Role | None — по точному имени / алиасу."""
    if guild is None:
        return None
    roles = list(getattr(guild, 'roles', None) or [])
    wanted = {_norm_name(a) for a in NAME_ALIASES}
    wanted.add(_norm_name(ROLE_NAME))
    # точное совпадение имени «Ведущий» первым
    for r in roles:
        if _norm_name(getattr(r, 'name', '')) == _norm_name(ROLE_NAME):
            return r
    for r in roles:
        if _norm_name(getattr(r, 'name', '')) in wanted:
            return r
    # по известному ID
    for rid in (env_vedushiy_role_id(), KNOWN_BROADCASTER_ROLE_ID):
        if not rid:
            continue
        for r in roles:
            try:
                if int(getattr(r, 'id', 0) or 0) == int(rid):
                    return r
            except (TypeError, ValueError):
                continue
    return None


def build_voice_host_permissions():
    """discord.Permissions с Move/Mute/Deafen Members."""
    import discord
    kwargs = {k: True for k in VOICE_HOST_PERMS}
    return discord.Permissions(**kwargs)


def should_force_perms() -> bool:
    return _truthy(os.environ.get('VEDUSHIY_FORCE_PERMS'))


def documented_discord_perms() -> tuple[str, ...]:
    """Человекочитаемые Discord-права (для доков / логов)."""
    return (
        'Move Members',
        'Mute Members',
        'Deafen Members',
    )


async def maybe_force_discord_perms(role) -> dict:
    """Опционально дописать voice-host bits в роль (VEDUSHIY_FORCE_PERMS=1)."""
    report = {'edited': False, 'reason': '', 'perms': list(VOICE_HOST_PERMS)}
    if role is None:
        report['reason'] = 'no role'
        return report
    if not should_force_perms():
        report['reason'] = 'VEDUSHIY_FORCE_PERMS off — document only'
        return report
    try:
        import discord
        cur = role.permissions
        updated = discord.Permissions(cur.value)
        changed = False
        for bit in VOICE_HOST_PERMS:
            if not getattr(updated, bit, False):
                setattr(updated, bit, True)
                changed = True
        if not changed:
            report['reason'] = 'already has voice host perms'
            return report
        await role.edit(permissions=updated, reason='vedushiy_role_seed force perms')
        report['edited'] = True
        report['reason'] = 'ok'
        _log.info('vedushiy force_perms: role=%s +%s',
                  getattr(role, 'id', '?'), VOICE_HOST_PERMS)
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('vedushiy force_perms: %s', ex)
    return report


def apply_vedushiy_role_seed(force: bool = False, guild_id=None,
                             guild=None) -> dict:
    """Зафиксировать роль Ведущий. Без action_acl / role_map punish tiers.

    Возвращает отчёт. При наличии guild объекта — резолв по имени.
    """
    report = {
        'applied': False,
        'reason': '',
        'guild_id': 0,
        'role_id': 0,
        'role_name': ROLE_NAME,
        'aliases': list(NAME_ALIASES),
        'discord_perms': list(documented_discord_perms()),
        'force_perms': should_force_perms(),
        'punish_acl': False,  # явно: не трогаем
        'marker': MARKER,
    }
    try:
        if _truthy(os.environ.get('DEMO_MODE')):
            report['reason'] = 'demo mode'
            return report
        if not force and os.path.exists(MARKER):
            # всё равно освежим role_id из env/guild для отчёта
            rid = resolve_vedushiy_role_id(guild=guild)
            report['role_id'] = rid
            report['reason'] = f'already applied (v{SEED_VERSION})'
            return report

        gid = _main_guild_id(guild_id or getattr(guild, 'id', None))
        if not gid:
            report['reason'] = 'no MAIN_GUILD_ID / LOVE_ROOM_GUILD_ID'
            return report
        report['guild_id'] = gid

        rid = resolve_vedushiy_role_id(guild=guild)
        report['role_id'] = rid
        if not rid:
            report['reason'] = 'role not found — create «Ведущий» or set VEDUSHIY_ROLE_ID'
            return report

        # Намеренно НЕ трогаем permission_acl / action_acl / role_map.
        report['punish_acl'] = False

        try:
            os.makedirs('data', exist_ok=True)
            with open(MARKER, 'w', encoding='utf-8') as fh:
                fh.write(f'ok role_id={rid}\n')
        except OSError as ex:
            _log.debug('vedushiy marker: %s', ex)

        report['applied'] = True
        report['reason'] = 'ok'
        _log.info(
            'vedushiy_role_seed v%s: guild=%s role=%s force_perms=%s '
            '(no punish ACL; Discord perms: %s)',
            SEED_VERSION, gid, rid, report['force_perms'],
            ', '.join(report['discord_perms']))
    except Exception as ex:
        report['reason'] = f'error: {ex}'
        _log.warning('apply_vedushiy_role_seed: %s', ex)
    return report


async def apply_vedushiy_on_ready(guild) -> dict:
    """on_ready: сид + опциональный force_perms."""
    report = apply_vedushiy_role_seed(guild=guild,
                                     guild_id=getattr(guild, 'id', None))
    role = find_vedushiy_role(guild) if guild is not None else None
    if role is not None:
        report['role_id'] = int(getattr(role, 'id', 0) or report.get('role_id') or 0)
        report['force_perms_result'] = await maybe_force_discord_perms(role)
    else:
        report['force_perms_result'] = {'edited': False, 'reason': 'role missing'}
    return report
