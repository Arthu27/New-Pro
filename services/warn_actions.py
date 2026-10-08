# -*- coding: utf-8 -*-
"""Единая бизнес-логика варнов для Discord и веб-панели.

issue_warn / remove_warn / remove_all_warns / sync — без дублирования.
source: 'discord' | 'web'
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from logger import get_logger

_log = get_logger('warn_actions')


def _target_branch(member) -> Optional[str]:
    try:
        from services.warn_acl import branches_of
        br = branches_of(member)
        return sorted(br)[0] if br else None
    except Exception:
        return None


def can_remove_warn(actor, warn_row, guild=None) -> Tuple[bool, str]:
    """Снять варн может только тот, чей ранг СТРОГО выше ранга выдавшего.

    Равный ранг — нельзя. Owner — можно всё.
    ISSUER_CAN_REMOVE_OWN_WARN — опционально свой варн.
    Для стафф-цели дополнительно проверка ветки (куратор/админ своей).
    """
    if actor is None or not warn_row:
        return False, 'Нет исполнителя или записи'
    try:
        from services.warn_config import (
            member_rank_snapshot, issuer_can_remove_own, role_style)
        from services.warn_acl import _is_bot_owner, is_staff_target, manual_warn_check
    except Exception as ex:
        return False, f'Конфиг: {ex}'

    if _is_bot_owner(actor):
        return True, ''

    actor_id = int(getattr(actor, 'id', 0) or 0)
    issuer_id = int(
        warn_row.get('issuer_id')
        or warn_row.get('moderator_id')
        or 0)
    snap_rank = int(warn_row.get('issuer_rank') or 0)
    snap_role = warn_row.get('issuer_role_id')

    # текущий ранг выдающего (если на сервере) vs снимок — берём max
    effective_issuer_rank = snap_rank
    issuer_label = role_style(snap_role).get('label') or 'модератор'
    if guild is not None and issuer_id:
        issuer_m = guild.get_member(issuer_id)
        if issuer_m is not None:
            cur_rank, cur_rid, cur_name = member_rank_snapshot(issuer_m)
            if cur_rank > effective_issuer_rank:
                effective_issuer_rank = cur_rank
                issuer_label = cur_name or issuer_label
                snap_role = cur_rid or snap_role

    actor_rank, _arid, actor_name = member_rank_snapshot(actor)

    if issuer_can_remove_own() and actor_id and actor_id == issuer_id:
        return True, ''

    if actor_id and actor_id == issuer_id and not issuer_can_remove_own():
        return False, 'Свой варн снять нельзя (ISSUER_CAN_REMOVE_OWN_WARN=0)'

    if actor_rank <= effective_issuer_rank:
        return False, (
            f'Этот варн выдал {issuer_label}. '
            f'Снять его может только тот, кто выше по рангу '
            f'(ваш ранг: {actor_name}).'
        )

    # ветка стаффа
    try:
        if guild is not None and int(warn_row.get('is_staff_target') or 0):
            uid = int(warn_row.get('user_id') or 0)
            target = guild.get_member(uid) if uid else None
            if target is not None and is_staff_target(guild, target):
                ok, deny = manual_warn_check(guild, actor, target)
                if not ok:
                    return False, deny or 'Нет права на стафф этой ветки'
    except Exception as ex:
        _log.debug('can_remove branch: %s', ex)

    return True, ''


async def issue_warn(
    guild,
    target,
    actor,
    *,
    reason: str | None = None,
    reason_code: str | None = None,
    reason_type: str | None = None,
    detail: str | None = None,
    source: str = 'discord',
    check_acl: bool = True,
    apply_auto_punish: bool = True,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Выдать варн.

    Возвращает (ok, message, payload|None).
    payload: {warn_id, total, row, is_staff, dm_ok}
    """
    from services import warn_store as WS
    from services.warn_role import sync_warn_role, is_staff_member
    from services.warn_config import format_branches
    from services import warn_reasons as WR
    from services import warn_dm as WDM

    if guild is None or target is None or actor is None:
        return False, 'Нет гильдии / цели / исполнителя', None

    try:
        if int(getattr(actor, 'id', 0)) == int(getattr(target, 'id', 0)):
            return False, 'Себе варн выдать нельзя.', None
    except Exception:
        pass

    if check_acl:
        try:
            from services.warn_acl import manual_warn_check
            ok, deny = manual_warn_check(guild, actor, target)
            if not ok:
                return False, deny or 'Нет права на варн', None
        except Exception as ex:
            _log.debug('issue_warn acl: %s', ex)

    is_staff = is_staff_member(guild, target)
    rtype = (reason_type or ('staff' if is_staff else 'member')).strip()
    if rtype not in ('member', 'staff'):
        rtype = 'staff' if is_staff else 'member'

    # Собираем текст причины
    code = (reason_code or '').strip() or None
    detail_txt = (detail or '').strip()
    if code:
        reason_txt = WR.format_reason(rtype, code, detail_txt or (reason or ''))
    else:
        reason_txt = (reason or detail_txt or 'Не указана').strip()

    if not detail_txt and not code and not (reason or '').strip():
        return False, 'Укажите причину (выбор + текст).', None

    # Для стаффа/участника свободный текст обязателен в UI;
    # если пришёл только code — допускаем (автофильтр).
    branch = _target_branch(target) if is_staff else None

    from services.warn_config import member_rank_snapshot
    issuer_rank, issuer_role_id, _issuer_name = member_rank_snapshot(actor)

    row = WS.add_warn(
        guild.id, target.id, getattr(actor, 'id', 0) or 0,
        reason_txt,
        is_staff_target=is_staff,
        branch=branch,
        reason_type=rtype,
        reason_code=code,
        source=source or 'discord',
        issuer_rank=issuer_rank,
        issuer_role_id=issuer_role_id,
    )
    warn_id = int(row['id'])
    total = WS.count_active(guild.id, target.id)
    try:
        WS.mirror_json(guild.id, target.id)
    except Exception:
        pass

    try:
        await sync_warn_role(target)
    except Exception as e:
        _log.warning('sync после варна: %s', e)

    try:
        from services.mute_progression import reset_on_warn
        reset_on_warn(guild.id, target.id)
    except Exception:
        pass

    try:
        from services.staff_limits import record_hit
        record_hit(guild.id, getattr(actor, 'id', 0) or 0, 'warn', 1)
    except Exception:
        pass

    # Лог-канал
    br_label = format_branches({branch}) if branch else None
    src_label = 'Web panel' if source == 'web' else 'Discord'
    try:
        from cogs.logs import send_action_log
        extra = f'#{warn_id} · всего {total} · {rtype}'
        if br_label:
            extra += f' · ветка {br_label}'
        extra += f' · источник: {src_label} · {getattr(actor, "display_name", actor)}'
        await send_action_log(
            guild, 'warn', target, actor,
            reason=reason_txt, extra=extra)
    except Exception as ex:
        _log.debug('issue_warn log: %s', ex)

    # DM
    dm_ok = False
    try:
        if is_staff:
            embed = WDM.build_staff_warn_dm(
                guild, actor, reason=reason_txt, warn_id=warn_id,
                active_count=total, branch=br_label,
                role_label=WDM.staff_role_label(target))
        else:
            embed = WDM.build_member_warn_dm(
                guild, actor, reason=reason_txt, warn_id=warn_id,
                active_count=total)
        dm_ok = await WDM.send_warn_dm(
            target, embed, guild=guild,
            log_channel_hint=f'warn #{warn_id} ({src_label})')
    except Exception as ex:
        _log.debug('issue_warn dm: %s', ex)

    punish = None
    if apply_auto_punish and not is_staff:
        try:
            # авто-наказания остаются в cogs.warnings — вызываем если есть
            from discord.ext import commands as _cmds  # noqa: F401
            # без hard dep на cog instance — опционально снаружи
        except Exception:
            pass

    try:
        import asyncio
        from services.warn_board import schedule_board_refresh
        asyncio.create_task(schedule_board_refresh(guild))
    except Exception as ex:
        _log.debug('issue_warn board: %s', ex)

    payload = {
        'warn_id': warn_id,
        'total': total,
        'row': row,
        'is_staff': is_staff,
        'dm_ok': dm_ok,
        'reason': reason_txt,
        'reason_type': rtype,
        'reason_code': code,
    }
    return True, f'Варн #{warn_id} выдан (всего: {total})', payload


async def remove_warn(
    guild,
    target,
    actor,
    *,
    warn_id: int | None = None,
    removed_reason: str | None = None,
    source: str = 'discord',
    check_acl: bool = True,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Снять один варн (по id или последний активный)."""
    from services import warn_store as WS
    from services.warn_role import sync_warn_role, is_staff_member
    from services import warn_dm as WDM
    from services.warn_config import format_branches

    if guild is None or target is None or actor is None:
        return False, 'Нет гильдии / цели / исполнителя', None

    try:
        if int(getattr(actor, 'id', 0)) == int(getattr(target, 'id', 0)):
            return False, 'Себе варн снять нельзя.', None
    except Exception:
        pass

    # найти запись до снятия — для can_remove_warn
    pending = None
    if warn_id:
        pending = WS.get_warn(int(warn_id))
        if not pending or not pending.get('active'):
            return False, 'Варн не найден или уже снят', None
        if int(pending.get('user_id') or 0) != int(target.id):
            return False, 'Варн принадлежит другому пользователю', None
    else:
        active = WS.list_warns(guild.id, target.id, active_only=True, limit=1)
        pending = active[0] if active else None
        if not pending:
            return False, 'Активных варнов нет', None

    if check_acl:
        ok, deny = can_remove_warn(actor, pending, guild=guild)
        if not ok:
            return False, deny or 'Нет права снять варн', None

    removed = WS.deactivate_warn(
        int(pending['id']), getattr(actor, 'id', 0) or 0,
        removed_reason=removed_reason)

    if not removed:
        return False, 'Активных варнов нет', None

    total = WS.count_active(guild.id, target.id)
    try:
        WS.mirror_json(guild.id, target.id)
    except Exception:
        pass
    try:
        await sync_warn_role(target)
    except Exception as e:
        _log.warning('sync после unwarn: %s', e)

    src_label = 'Web panel' if source == 'web' else 'Discord'
    try:
        from cogs.logs import send_action_log
        await send_action_log(
            guild, 'unwarn', target, actor,
            reason=removed.get('reason', 'Не указана'),
            extra=(
                f'Снято #{removed.get("id")} · осталось {total} · '
                f'источник: {src_label} · '
                f'{getattr(actor, "display_name", actor)}'
                + (f' · {removed_reason}' if removed_reason else '')))
    except Exception as ex:
        _log.debug('remove_warn log: %s', ex)

    is_staff = bool(removed.get('is_staff_target')) or is_staff_member(guild, target)
    branch = removed.get('branch')
    br_label = format_branches({branch}) if branch else None
    dm_ok = False
    try:
        if is_staff:
            embed = WDM.build_staff_unwarn_dm(
                guild, actor, reason=removed.get('reason', '—'),
                warn_id=int(removed['id']), active_count=total,
                branch=br_label, removed_reason=removed_reason)
        else:
            embed = WDM.build_member_unwarn_dm(
                guild, actor, reason=removed.get('reason', '—'),
                warn_id=int(removed['id']), active_count=total,
                removed_reason=removed_reason)
        dm_ok = await WDM.send_warn_dm(
            target, embed, guild=guild,
            log_channel_hint=f'unwarn #{removed["id"]} ({src_label})')
    except Exception as ex:
        _log.debug('remove_warn dm: %s', ex)

    try:
        import asyncio
        from services.warn_board import schedule_board_refresh
        asyncio.create_task(schedule_board_refresh(guild))
    except Exception as ex:
        _log.debug('remove_warn board: %s', ex)

    return True, f'Снято #{removed["id"]} · осталось {total}', {
        'removed': removed, 'total': total, 'dm_ok': dm_ok, 'is_staff': is_staff,
    }


async def remove_all_warns(
    guild, target, actor, *,
    removed_reason: str | None = None,
    source: str = 'discord',
    check_acl: bool = True,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Снимает только те варны, на которые есть право. Остальные пропускает."""
    from services import warn_store as WS
    from services.warn_role import sync_warn_role

    active = WS.list_warns(guild.id, target.id, active_only=True)
    if not active:
        return False, 'Активных варнов нет', None
    removed_rows = []
    skipped = 0
    last_err = None
    for w in active:
        if check_acl:
            ok_acl, deny = can_remove_warn(actor, w, guild=guild)
            if not ok_acl:
                skipped += 1
                last_err = deny
                continue
        ok, msg, payload = await remove_warn(
            guild, target, actor, warn_id=int(w['id']),
            removed_reason=removed_reason, source=source,
            check_acl=False)
        if ok and payload:
            removed_rows.append(payload.get('removed'))
        else:
            skipped += 1
            last_err = msg
    try:
        await sync_warn_role(target)
    except Exception:
        pass
    if not removed_rows:
        return False, last_err or 'Нечего снимать (нет прав)', None
    total = WS.count_active(guild.id, target.id)
    msg = f'Снято {len(removed_rows)}, осталось {total}'
    if skipped:
        msg += f', пропущено {skipped}'
    return True, msg, {
        'removed': removed_rows, 'total': total, 'skipped': skipped,
    }


async def panel_unban(
    guild, user_id: int, actor, *,
    reason: str | None = None,
    source: str = 'web',
) -> Tuple[bool, str]:
    """Разбан через веб/общую логику."""
    if guild is None or not user_id:
        return False, 'Нет гильдии или user_id'
    # права
    try:
        from services.warn_config import unban_allowed_role_ids
        allowed = unban_allowed_role_ids()
        if allowed:
            have = {
                int(getattr(r, 'id', 0) or 0)
                for r in (getattr(actor, 'roles', None) or [])}
            if not (have & set(allowed)):
                from services.warn_acl import _is_bot_owner
                if not _is_bot_owner(actor):
                    return False, 'Нет роли для разбана (UNBAN_PANEL_ROLE_IDS)'
        else:
            from services.permission_acl import check_action as _acl
            from services.warn_acl import _is_bot_owner
            if not _is_bot_owner(actor) and not _acl(guild.id, actor, 'unban'):
                return False, 'Нет права на разбан'
    except Exception as ex:
        _log.debug('panel_unban acl: %s', ex)

    reason_txt = (
        f'{reason or "Разбан"} · '
        f'{"Web panel" if source == "web" else "Discord"}: '
        f'{getattr(actor, "display_name", actor)}'
    )[:512]
    try:
        user = None
        try:
            bans = [b async for b in guild.bans(limit=None)]
        except TypeError:
            # старый API
            bans = await guild.bans()
        except Exception:
            bans = []
        for b in bans:
            u = getattr(b, 'user', b)
            if int(getattr(u, 'id', 0) or 0) == int(user_id):
                user = u
                break
        if user is None:
            # попробуем Object.Object
            import discord
            try:
                await guild.unban(
                    discord.Object(id=int(user_id)), reason=reason_txt)
                return True, 'Разбан выполнен'
            except discord.NotFound:
                return False, 'Пользователь не в бане / уже разбанен'
            except discord.Forbidden:
                return False, 'У бота нет прав на разбан'
        await guild.unban(user, reason=reason_txt)
        try:
            from cogs.logs import send_action_log
            await send_action_log(
                guild, 'unban', user, actor,
                reason=reason_txt,
                extra=f'источник: {"Web panel" if source == "web" else "Discord"}')
        except Exception:
            pass
        return True, 'Разбан выполнен'
    except Exception as ex:
        name = type(ex).__name__
        if 'NotFound' in name:
            return False, 'Пользователь не в бане / уже разбанен'
        if 'Forbidden' in name:
            return False, 'У бота нет прав на разбан'
        _log.warning('panel_unban: %s', ex)
        return False, f'Ошибка разбана: {ex}'
