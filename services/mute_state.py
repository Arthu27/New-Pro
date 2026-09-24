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


def active_mute_kinds(guild, member) -> set:
    """Какие муты сейчас активны у участника: {'mute','vmute','timeout'}.

    Смотрим роли, нативный таймаут и журнал temps (срок ещё не вышел).
    """
    kinds = set()
    if member is None or guild is None:
        return kinds
    try:
        from services import punish_roles as PR
        import time as _t
        mute_id = int(PR.role_for(guild.id, 'mute') or 0)
        vmute_id = int(PR.role_for(guild.id, 'vmute') or 0)
        have = {int(getattr(r, 'id', 0) or 0)
                for r in (getattr(member, 'roles', None) or [])}
        if mute_id and mute_id in have:
            kinds.add('mute')
        if vmute_id and vmute_id in have:
            kinds.add('vmute')
        temps = PR.temps_for(guild.id, getattr(member, 'id', 0) or 0)
        now = _t.time()
        if mute_id and float(temps.get(mute_id) or 0) > now:
            kinds.add('mute')
        if vmute_id and float(temps.get(vmute_id) or 0) > now:
            kinds.add('vmute')
    except Exception as _e:
        log.debug('active_mute_kinds roles/temps: %s', _e)
    try:
        until = getattr(member, 'timed_out_until', None)
        if until is not None:
            kinds.add('timeout')
    except Exception:
        pass
    return kinds


def already_muted_deny(action: str, active: set) -> str | None:
    """Текст отказа, если повторный/параллельный мут тому же человеку."""
    if not active:
        return None
    action = str(action or '')
    labels = {
        'mute': 'чат-мут',
        'vmute': 'войс-мут',
        'timeout': 'таймаут',
    }
    active_txt = ', '.join(labels.get(k, k) for k in sorted(active))
    # любой новый мут, если уже есть хоть один вид
    if action in ('timeout', 'mute_chat', 'vmute'):
        return (
            f'Участник уже в муте ({active_txt}). '
            f'Сначала снимите текущий мут — повторно двум модерам '
            f'на одного человека нельзя.'
        )
    return None


# Сериализация мута на (guild, user) — два модера не гонят clear+add параллельно
_MUTE_LOCKS: dict = {}


def mute_apply_lock(guild_id, user_id):
    """asyncio.Lock на пару гильдия+цель."""
    import asyncio
    key = (int(guild_id or 0), int(user_id or 0))
    lock = _MUTE_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _MUTE_LOCKS[key] = lock
    return lock
