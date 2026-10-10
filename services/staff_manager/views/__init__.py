# -*- coding: utf-8 -*-
"""Отдельные билдеры экранов Staff Manager (не универсальный шаблон)."""
from services.staff_manager.views.profile import build_profile_view
from services.staff_manager.views.history import build_history_view
from services.staff_manager.views.promotion import build_promotion_view
from services.staff_manager.views.vacation import build_vacation_view
from services.staff_manager.views.transfer import build_transfer_view
from services.staff_manager.views.removal import build_removal_view
from services.staff_manager.views.roster import build_roster_view
from services.staff_manager.views.requests import build_requests_view
from services.staff_manager.views.consent import build_consent_view

__all__ = [
    'build_profile_view', 'build_history_view', 'build_promotion_view',
    'build_vacation_view', 'build_transfer_view', 'build_removal_view',
    'build_roster_view', 'build_requests_view', 'build_consent_view',
]
