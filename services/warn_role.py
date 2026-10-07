# -*- coding: utf-8 -*-
"""Синхронизация Discord-роли warn с БД.

Правила:
  • не стафф + active > 0 → роль warn должна быть;
  • active == 0 → роли быть не должно;
  • стафф → роли warn быть не должно НИКОГДА (снять, если есть).

Одна функция sync_warn_role(member) — вызывается после выдачи/снятия,
на старте бота, on_member_join, on_member_update.
"""
from __future__ import annotations

from logger import get_logger

_log = get_logger('warn_role')


def is_staff_member(guild, member) -> bool:
    """Стафф = роль ветки набора или mapped helper+ (как warn_acl)."""
    if member is None:
        return False
    try:
        from services.warn_acl import _is_staff_target
        return bool(_is_staff_target(guild, member))
    except Exception as _ex:
        _log.debug('is_staff_member: %s', _ex)
        return False


def _has_role(member, role_id: int) -> bool:
    if not role_id:
        return False
    for r in (getattr(member, 'roles', None) or []):
        if getattr(r, 'id', None) == role_id:
            return True
    return False


async def sync_warn_role(member) -> str:
    """Привести роль warn к правильному состоянию.

    Возвращает краткий статус: 'ok' | 'added' | 'removed' | 'skip' | 'error:…'
    Никогда не бросает наружу — бот не должен падать.
    """
    if member is None:
        return 'skip'
    guild = getattr(member, 'guild', None)
    if guild is None:
        return 'skip'
    try:
        from services.warn_config import warn_role_id
        from services import warn_store as WS

        rid = int(warn_role_id() or 0)
        if not rid:
            return 'skip'

        role = guild.get_role(rid)
        if role is None:
            _log.warning(
                'sync_warn_role: роль warn %s не найдена на guild=%s',
                rid, getattr(guild, 'id', '?'))
            return 'error:role_missing'

        staff = is_staff_member(guild, member)
        active = WS.count_active(guild.id, member.id)
        has = _has_role(member, rid)

        # Стафф — роли warn быть не должно никогда
        if staff:
            if has:
                try:
                    await member.remove_roles(
                        role, reason='Warn sync: стафф не получает роль warn')
                    _log.info(
                        'sync_warn_role: снята с стаффа %s (%s)',
                        getattr(member, 'id', '?'), active)
                    return 'removed'
                except Exception as e:
                    _log.warning('sync_warn_role remove staff: %s', e)
                    return f'error:{e}'
            return 'ok'

        # Обычный участник
        if active > 0 and not has:
            try:
                await member.add_roles(
                    role, reason=f'Warn sync: активных варнов {active}')
                _log.info(
                    'sync_warn_role: выдана %s → %s (варнов=%s)',
                    role.name, getattr(member, 'id', '?'), active)
                return 'added'
            except Exception as e:
                _log.warning('sync_warn_role add: %s', e)
                return f'error:{e}'

        if active <= 0 and has:
            try:
                await member.remove_roles(
                    role, reason='Warn sync: активных варнов нет')
                _log.info(
                    'sync_warn_role: снята с %s (варнов=0)',
                    getattr(member, 'id', '?'))
                return 'removed'
            except Exception as e:
                _log.warning('sync_warn_role remove: %s', e)
                return f'error:{e}'

        return 'ok'
    except Exception as e:
        _log.warning('sync_warn_role: %s', e)
        return f'error:{e}'


async def sync_guild_active_warns(guild) -> int:
    """При старте: синхронизировать всех с active-варнами (+ стафф с ролью)."""
    if guild is None:
        return 0
    n = 0
    try:
        from services import warn_store as WS
        from services.warn_config import warn_role_id

        uids = set(WS.list_active_user_ids(guild.id))
        rid = int(warn_role_id() or 0)
        # плюс те, у кого вручную висит роль warn
        if rid:
            role = guild.get_role(rid)
            if role is not None:
                for m in getattr(role, 'members', []) or []:
                    try:
                        uids.add(int(m.id))
                    except Exception:
                        pass

        for uid in uids:
            member = guild.get_member(uid)
            if member is None:
                continue
            try:
                await sync_warn_role(member)
                n += 1
            except Exception as e:
                _log.debug('sync_guild member %s: %s', uid, e)
    except Exception as e:
        _log.warning('sync_guild_active_warns: %s', e)
    return n
