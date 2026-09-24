# -*- coding: utf-8 -*-
"""Проверка демок после мута: данные и снятие наказания.

Поток (заказ владельца 2026-09-24):
  1) мут выдаётся сразу;
  2) модератор кидает фото/видео в чат (можно несколько);
  3) карточка уходит в канал доказательств (V2 + select);
  4) «Одобрить» — мут остаётся; «Отклонить» — мут снимается,
     у отклонившего списывается лимит unmute.
"""
from __future__ import annotations

from logger import get_logger

_log = get_logger('proof_review')

# Действия /modpanel, после которых требуется демка в чат.
MUTE_PROOF_ACTIONS = frozenset({'timeout', 'mute_chat', 'vmute'})

ACTION_LABEL = {
    'timeout': 'Мут (чат + войс)',
    'mute_chat': 'Мут чата',
    'vmute': 'Войс-мут',
    'ban': 'Бан',
}

COLLECT_TIMEOUT_SEC = 5 * 60
COLLECT_MAX_FILES = 8
DONE_WORDS = frozenset({
    'готово', 'готов', 'done', '+', 'ок', 'ok', 'всё', 'все', 'finish',
})


def action_label(action: str) -> str:
    return ACTION_LABEL.get(action, action or 'мут')


async def undo_mute(guild, member, mute_action: str) -> str:
    """Снять мут по исходному виду. Возвращает короткий текст результата."""
    from services import mute_state
    kind = (mute_action or 'timeout').strip()
    if kind == 'mute_chat':
        await mute_state.clear_chat_mute(guild, member)
        return 'чат-мут снят'
    if kind == 'vmute':
        await mute_state.clear_voice_mute(guild, member)
        return 'войс-мут снят'
    await mute_state.clear_all_mutes(guild, member)
    return 'мут снят (чат и войс)'


def reviewer_may_decide(guild_id, member) -> bool:
    """Кто может одобрить/отклонить демку: unmute ACL или mapped mod+."""
    try:
        from services.permission_acl import check_action
        if check_action(guild_id, member, 'unmute'):
            return True
        if check_action(guild_id, member, 'mute'):
            return True
    except Exception as _ex:
        _log.debug('reviewer acl: %s', _ex)
    try:
        from services.staff_hierarchy import best_mapped_tier, RANK
        tier = best_mapped_tier(member)
        return RANK.get(tier, -1) >= RANK.get('mod', 2)
    except Exception as _ex:
        _log.debug('reviewer tier: %s', _ex)
    return False


def consume_unmute_limit(guild, reviewer) -> tuple:
    """Списать unmute у отклонившего. (ok, deny_text|None)."""
    try:
        from services.staff_limits import check_action, record_hit
        ok, deny = check_action(guild, reviewer, 'unmute')
        if not ok:
            return False, deny or 'Лимит размутов на сегодня исчерпан.'
        record_hit(guild.id, reviewer.id, 'unmute', 1)
        return True, None
    except Exception as _ex:
        _log.debug('unmute limit: %s', _ex)
        return True, None
