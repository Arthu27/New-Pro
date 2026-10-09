# -*- coding: utf-8 -*-
"""Staff Manager: единая лестница ролей, изоляция веток, ACL.

Публичный API:
  load_config / validate_config / get_config
  can_manage_staff / get_allowed_actions
  apply_staff_change / describe_member
  build_indexes
"""
from services.staff_manager.config import (
    load_config, get_config, validate_config, ConfigError,
    build_indexes, reload_config, ladder_by_key, branch_of_role,
)
from services.staff_manager.acl import (
    can_manage_staff, get_allowed_actions, ActorContext, TargetContext,
    resolve_actor, resolve_target,
)
from services.staff_manager.actions import (
    apply_staff_change, StaffChangeResult,
)
from services.staff_manager.store import (
    ensure_tables, record_action, list_actions, claim_action_once,
)

__all__ = [
    'load_config', 'get_config', 'validate_config', 'ConfigError',
    'build_indexes', 'reload_config', 'ladder_by_key', 'branch_of_role',
    'can_manage_staff', 'get_allowed_actions',
    'ActorContext', 'TargetContext', 'resolve_actor', 'resolve_target',
    'apply_staff_change', 'StaffChangeResult',
    'ensure_tables', 'record_action', 'list_actions', 'claim_action_once',
]
