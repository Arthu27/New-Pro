"""Состояния мута — единая непротиворечивая модель.

В сервере одновременно существуют три независимых механизма заглушения:

* нативный Discord-таймаут (``member.timeout(until)``) — глушит И чат, И голос
  одним состоянием Discord;
* роль чат-мута (``punish_roles.role_for(gid, 'mute')``) — глушит чат через
  права роли;
* роль войс-мута (``punish_roles.role_for(gid, 'vmute')``) — глушит только
  микрофон (плюс нативный server-mute в канале).

Проблема: если у участника висит войс-мут, а сверху дают таймаут (или
наоборот), на нём остаются ДВА ограничения сразу, и снятие одного не снимает
другое. Здесь — единые хелперы: перед наложением мута всегда очищаем
противоположное состояние, чтобы на участнике был ровно один тип мута.

Все функции безопасно вызывать «вслепую»: нет роли / прав / состояния —
тихо пропускают (лог на уровне debug).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


async def _remove_role(guild, user, role_id: int) -> None:
    """Снять роль по id (если она есть у участника) и почистить журнал сроков."""
    try:
        if not role_id:
            return
        role = guild.get_role(int(role_id))
        if role is None:
            return
        if not any(getattr(r, "id", 0) == int(role_id) for r in getattr(user, "roles", []) or []):
            return
        await user.remove_roles(role, reason="снятие пересекающегося мута")
        try:
            from services import punish_roles as PR
            PR.clear(guild.id, user.id, int(role_id))
        except Exception as _e:  # журнал не критичен
            log.debug("mute_state: clear temps role=%s: %s", role_id, _e)
    except Exception as _e:
        log.debug("mute_state: не снял роль %s: %s", role_id, _e)


async def clear_voice_mute(guild, user) -> None:
    """Снять ЛЮБОЕ голосовое заглушение: роль войс-мута и нативный server-mute.

    Зовётся перед чат-мутом/таймаутом, чтобы не оставался второй (голосовой) мут.
    """
    try:
        from services import punish_roles as PR
        await _remove_role(guild, user, PR.role_for(guild.id, "vmute"))
    except Exception as _e:
        log.debug("mute_state: vmute-роль: %s", _e)
    try:
        voice = getattr(user, "voice", None)
        if voice is not None and getattr(voice, "mute", False):
            await user.edit(mute=False)
    except Exception as _e:
        log.debug("mute_state: server-mute: %s", _e)


async def clear_chat_mute(guild, user) -> None:
    """Снять ЛЮБОЕ чат-заглушение: роль чат-мута и нативный таймаут.

    Зовётся перед войс-мутом, чтобы не оставался второй (чат) мут.
    """
    try:
        from services import punish_roles as PR
        await _remove_role(guild, user, PR.role_for(guild.id, "mute"))
    except Exception as _e:
        log.debug("mute_state: mute-роль: %s", _e)
    try:
        if getattr(user, "timed_out_until", None):
            await user.timeout(None, reason="снятие пересекающегося таймаута")
    except Exception as _e:
        log.debug("mute_state: timeout: %s", _e)


async def clear_all_mutes(guild, user) -> None:
    """Снять и чат-, и голосовой мут разом (для untimeout/снятия всех мер)."""
    await clear_chat_mute(guild, user)
    await clear_voice_mute(guild, user)
