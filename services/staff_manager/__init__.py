# -*- coding: utf-8 -*-
"""Staff Manager: единая лестница ролей, изоляция веток, ACL, согласия.

Публичный API:
  load_config / validate_config / get_config
  can_manage_staff / get_allowed_actions / get_staff_info
  apply_staff_change
  consent helpers / ensure_tables
"""
from services.staff_manager.config import (
    load_config, get_config, validate_config, ConfigError,
    build_indexes, reload_config, ladder_by_key, branch_of_role,
    requires_consent, role_emoji, branch_emoji,
)
from services.staff_manager.acl import (
    can_manage_staff, get_allowed_actions, get_staff_info,
    ActorContext, TargetContext, resolve_actor, resolve_target,
)
from services.staff_manager.actions import (
    apply_staff_change, StaffChangeResult,
)
from services.staff_manager.store import (
    ensure_tables, record_action, list_actions, claim_action_once,
    create_consent, get_consent, claim_consent_decision, update_consent,
    list_consents, expire_due_consents, pending_consent_for,
)
from services.staff_manager import emojis as staff_emojis  # noqa: F401

__all__ = [
    'load_config', 'get_config', 'validate_config', 'ConfigError',
    'build_indexes', 'reload_config', 'ladder_by_key', 'branch_of_role',
    'requires_consent', 'role_emoji', 'branch_emoji',
    'can_manage_staff', 'get_allowed_actions', 'get_staff_info',
    'ActorContext', 'TargetContext', 'resolve_actor', 'resolve_target',
    'apply_staff_change', 'StaffChangeResult',
    'ensure_tables', 'record_action', 'list_actions', 'claim_action_once',
    'create_consent', 'get_consent', 'claim_consent_decision', 'update_consent',
    'list_consents', 'expire_due_consents', 'pending_consent_for',
]
