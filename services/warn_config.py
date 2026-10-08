# -*- coding: utf-8 -*-
"""Конфиг варнов: роль, ветки, ранги, цвета бейджей.

Единая роль warn. Счётчик = COUNT active=1 в SQLite.
Цвета ролей/веток — только тёмная тема панели.
"""
from __future__ import annotations

import os

from logger import get_logger

_log = get_logger('warn_config')

_DEFAULT_WARN_ROLE_ID = 1545468739221327942

# ── ранги (больше = выше). Снять варн может только STRICTLY выше issuer. ──
# role_id → (name, rank). Источник: services.staff_roles + тиры.
RANKS = [
    # ветки (staff line)
    {'role_id': 948969471916249119, 'name': 'Helper', 'rank': 10},
    {'role_id': 803553848396349510, 'name': 'Moderator', 'rank': 10},
    {'role_id': 852634463535759461, 'name': 'Eventsmod', 'rank': 10},
    {'role_id': 1551180629687664670, 'name': 'Broadcaster', 'rank': 10},
    {'role_id': 1553138713532563516, 'name': 'Support', 'rank': 10},
    {'role_id': 1553769624603201546, 'name': 'Close mod', 'rank': 10},
    {'role_id': 1553853968969638058, 'name': 'Creative', 'rank': 10},
    {'role_id': 1552637932907667466, 'name': 'Master', 'rank': 20},
    # кураторы веток
    {'role_id': 1551525681207189504, 'name': 'Curator Helper', 'rank': 30},
    {'role_id': 1551524708552278036, 'name': 'Curator Moderator', 'rank': 30},
    {'role_id': 1551527644326002748, 'name': 'Curator Events', 'rank': 30},
    {'role_id': 1552639452713848912, 'name': 'Curator Broadcaster', 'rank': 30},
    {'role_id': 1553139245735219390, 'name': 'Curator Support', 'rank': 30},
    {'role_id': 1553770122966073384, 'name': 'Curator Close mod', 'rank': 30},
    {'role_id': 1553854011449544825, 'name': 'Curator Creative', 'rank': 30},
    {'role_id': 807030012301541377, 'name': 'Curator', 'rank': 30},
    {'role_id': 1552815174115664013, 'name': 'Assistent', 'rank': 40},
    {'role_id': 1554932049528225842, 'name': 'Staff Assistent', 'rank': 45},
    {'role_id': 1189999426631122964, 'name': 'Administrator', 'rank': 50},
    {'role_id': 1549118975110152263, 'name': 'Staff Admin', 'rank': 55},
]

ROLE_STYLES = {
    948969471916249119: {'label': 'Helper', 'color': '#5dade2', 'icon': 'fa-hands-helping'},
    803553848396349510: {'label': 'Moderator', 'color': '#58d68d', 'icon': 'fa-shield-halved'},
    852634463535759461: {'label': 'Eventsmod', 'color': '#af7ac5', 'icon': 'fa-calendar'},
    1551180629687664670: {'label': 'Broadcaster', 'color': '#f1948a', 'icon': 'fa-tower-broadcast'},
    1553138713532563516: {'label': 'Support', 'color': '#76d7c4', 'icon': 'fa-headset'},
    1553769624603201546: {'label': 'Close mod', 'color': '#85929e', 'icon': 'fa-door-closed'},
    1553853968969638058: {'label': 'Creative', 'color': '#f5b041', 'icon': 'fa-palette'},
    1552637932907667466: {'label': 'Master', 'color': '#45b39d', 'icon': 'fa-star'},
    1551525681207189504: {'label': 'Curator · Helper', 'color': '#5dade2', 'icon': 'fa-user-check'},
    1551524708552278036: {'label': 'Curator · Mod', 'color': '#58d68d', 'icon': 'fa-user-check'},
    1551527644326002748: {'label': 'Curator · Event', 'color': '#af7ac5', 'icon': 'fa-user-check'},
    1552639452713848912: {'label': 'Curator · BC', 'color': '#f1948a', 'icon': 'fa-user-check'},
    1553139245735219390: {'label': 'Curator · Support', 'color': '#76d7c4', 'icon': 'fa-user-check'},
    1553770122966073384: {'label': 'Curator · Close', 'color': '#85929e', 'icon': 'fa-user-check'},
    1553854011449544825: {'label': 'Curator · Creative', 'color': '#f5b041', 'icon': 'fa-user-check'},
    807030012301541377: {'label': 'Curator', 'color': '#aed6f1', 'icon': 'fa-user-tie'},
    1552815174115664013: {'label': 'Assistent', 'color': '#bb8fce', 'icon': 'fa-user-gear'},
    1554932049528225842: {'label': 'Staff Assistent', 'color': '#d2b4de', 'icon': 'fa-user-gear'},
    1189999426631122964: {'label': 'Admin', 'color': '#ec7063', 'icon': 'fa-crown'},
    1549118975110152263: {'label': 'Staff Admin', 'color': '#ff4d3d', 'icon': 'fa-crown'},
}

BRANCH_STYLES = {
    'helper': {'label': 'Helper', 'color': '#5dade2'},
    'moderator': {'label': 'Moderator', 'color': '#58d68d'},
    'event': {'label': 'Eventsmod', 'color': '#af7ac5'},
    'broadcaster': {'label': 'Broadcaster', 'color': '#f1948a'},
    'support': {'label': 'Support', 'color': '#76d7c4'},
    'closemod': {'label': 'Close mod', 'color': '#85929e'},
    'creative': {'label': 'Creative', 'color': '#f5b041'},
}


def warn_role_id() -> int:
    raw = (os.getenv('WARN_ROLE_ID') or '').strip()
    if raw:
        try:
            return int(raw)
        except (TypeError, ValueError):
            _log.warning('WARN_ROLE_ID=%r не число — дефолт', raw)
    try:
        from config import Config
        return int(getattr(Config, 'WARN_ROLE_ID', 0) or _DEFAULT_WARN_ROLE_ID)
    except Exception:
        return _DEFAULT_WARN_ROLE_ID


def warn_duration_days() -> int:
    """Срок действия варна в днях (WARN_DURATION_DAYS, по умолчанию 7)."""
    raw = (os.getenv('WARN_DURATION_DAYS') or '').strip()
    if raw:
        try:
            return max(1, min(365, int(raw)))
        except (TypeError, ValueError):
            _log.warning('WARN_DURATION_DAYS=%r не число — 7', raw)
    try:
        from config import Config
        return max(1, int(getattr(Config, 'WARN_DURATION_DAYS', 7) or 7))
    except Exception:
        return 7


def warn_expire_loop_minutes() -> float:
    """Интервал фоновой проверки истечения (1–5 мин)."""
    raw = (os.getenv('WARN_EXPIRE_LOOP_MINUTES') or '2').strip()
    try:
        return max(1.0, min(5.0, float(raw)))
    except (TypeError, ValueError):
        return 2.0


def panel_cache_ttl_sec() -> float:
    """TTL оперативного кэша панели (сек)."""
    raw = (os.getenv('PANEL_CACHE_TTL') or '45').strip()
    try:
        return max(5.0, min(300.0, float(raw)))
    except (TypeError, ValueError):
        return 45.0


def issuer_can_remove_own() -> bool:
    raw = (os.getenv('ISSUER_CAN_REMOVE_OWN_WARN') or '0').strip().lower()
    return raw in ('1', 'true', 'yes', 'on')


def ranks_list() -> list:
    return list(RANKS)


def role_style(role_id) -> dict:
    try:
        rid = int(role_id or 0)
    except (TypeError, ValueError):
        return {'label': '—', 'color': '#7f8798', 'icon': 'fa-user'}
    st = ROLE_STYLES.get(rid)
    if st:
        return dict(st)
    return {'label': str(rid), 'color': '#7f8798', 'icon': 'fa-user'}


def branch_style(branch: str | None) -> dict:
    b = (branch or '').strip()
    st = BRANCH_STYLES.get(b)
    if st:
        return dict(st)
    return {'label': b or '—', 'color': '#7f8798'}


def branch_labels() -> dict:
    return {k: v['label'] for k, v in BRANCH_STYLES.items()}


def branch_grant_roles() -> dict:
    out = {}
    try:
        from services.staff_roles import KNOWN_GRANT_BY_KIND
        for kind, rid in (KNOWN_GRANT_BY_KIND or {}).items():
            try:
                out[str(kind)] = int(rid)
            except (TypeError, ValueError):
                continue
    except Exception as _ex:
        _log.debug('branch_grant_roles: %s', _ex)
    return out


def branch_curator_roles() -> dict:
    out = {}
    try:
        from services.staff_roles import KNOWN_CURATOR_BY_KIND
        for kind, rid in (KNOWN_CURATOR_BY_KIND or {}).items():
            try:
                out[str(kind)] = int(rid)
            except (TypeError, ValueError):
                continue
    except Exception as _ex:
        _log.debug('branch_curator_roles: %s', _ex)
    return out


def format_branches(kinds) -> str:
    labels = branch_labels()
    names = [labels.get(k, k) for k in sorted(kinds or [])]
    return ', '.join(names) if names else '—'


def staff_warn_review_threshold() -> int:
    raw = (os.getenv('STAFF_WARN_REVIEW_THRESHOLD') or '').strip()
    if raw:
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            pass
    return 3


def unban_allowed_role_ids() -> list:
    raw = (os.getenv('UNBAN_PANEL_ROLE_IDS') or '').strip()
    out = []
    if not raw:
        return out
    for part in raw.replace(';', ',').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except (TypeError, ValueError):
            continue
    return out


def appeal_hint_member() -> str:
    return (
        os.getenv('WARN_APPEAL_HINT_MEMBER')
        or 'Обжаловать можно через /appeal или обращение к модерации.'
    ).strip()


def appeal_hint_staff() -> str:
    return (
        os.getenv('WARN_APPEAL_HINT_STAFF')
        or 'Обжаловать — у куратора своей ветки или у администрации.'
    ).strip()


def member_rank_snapshot(member) -> tuple[int, int | None, str]:
    """Вернуть (rank, top_role_id, rank_name) по RANKS.

    rank=0 — обычный участник / неизвестно.
    """
    if member is None:
        return 0, None, 'участник'
    try:
        from config import Config
        if int(getattr(member, 'id', 0) or 0) in Config.all_owner_ids():
            return 100, None, 'владелец'
    except Exception:
        pass
    have = set()
    for r in (getattr(member, 'roles', None) or []):
        try:
            have.add(int(getattr(r, 'id', 0) or 0))
        except (TypeError, ValueError):
            continue
    best = 0
    best_rid = None
    best_name = 'участник'
    for row in RANKS:
        rid = int(row['role_id'])
        if rid in have and int(row['rank']) >= best:
            best = int(row['rank'])
            best_rid = rid
            best_name = str(row['name'])
    return best, best_rid, best_name


def styles_public_dict() -> dict:
    """Для фронта: role_id(str) → style, branch → style."""
    roles = {str(k): v for k, v in ROLE_STYLES.items()}
    return {'roles': roles, 'branches': dict(BRANCH_STYLES)}
