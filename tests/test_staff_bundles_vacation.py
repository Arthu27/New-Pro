# -*- coding: utf-8 -*-
"""ROLE_BUNDLES, actor snapshot, vacation-as-staff, separate views."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.staff_manager import config as CFG
from services.staff_manager.acl import (
    get_staff_info, resolve_actor, resolve_target, can_manage_staff,
)
from services.staff_manager.bundles import (
    compute_bundle_delta, format_actor_label, format_role_label,
    format_transition, get_promotion_requirements, get_role_bundle,
)
from services.staff_manager import actions as ACT
from services.staff_manager.store import (
    ensure_tables, record_action, list_actions, create_vacation,
    active_vacation_for, list_actions_filtered,
)


def _write_cfg(path: str) -> dict:
    raw = {
        'staff_admin_role_id': 9001,
        'owner_ids': [100],
        'common_staff_role_id': 9002,
        'vacation_role_id': 9003,
        'never_strip_role_ids': [9999],
        'ROLE_EMOJIS': {
            'master': '⚔️', 'curator': '🌂',
            'assistant': '🦋', 'admin': '🦋',
        },
        'BRANCH_EMOJIS': {'moderators': '🛡️', 'helpers': '🤝'},
        'ROLE_BUNDLES': {
            'master': {
                'add_roles': [], 'remove_roles': [],
                'requires': {'min_days_in_role': 0, 'max_active_warns': 99},
            },
            'curator': {
                'add_roles': [], 'remove_roles': [],
                'requires': {
                    'min_days_in_role': 14, 'max_active_warns': 0,
                    'not_on_probation': True, 'not_on_vacation': True,
                },
            },
            'admin': {
                'add_roles': [], 'remove_roles': [],
                'requires': {
                    'min_days_in_role': 14, 'max_active_warns': 0,
                    'not_on_vacation': True,
                },
            },
        },
        'VACATION_AUTO_APPROVE_UP_TO_DAYS': 7,
        'VACATION_MAX_DAYS_SELF': 30,
        'ladder': [
            {'key': 'master', 'name': 'Master', 'rank': 1},
            {'key': 'curator', 'name': 'Curator', 'rank': 2},
            {'key': 'assistant', 'name': 'Assistent', 'rank': 3},
            {'key': 'admin', 'name': 'Admin', 'rank': 4, 'protected': True},
        ],
        'responsible_can_manage': ['master', 'curator', 'assistant'],
        'allow_promotion_requests': True,
        'branches': {
            'moderators': {
                'label': 'Модераторы',
                'responsible_role_id': 9100,
                'entry_role_id': 9110,
                'role_bundles': {
                    'admin': {'add_roles': [9100], 'remove_roles': []},
                },
                'roles': {
                    'master': 9111, 'curator': 9113,
                    'assistant': 9112, 'admin': 9114,
                },
            },
            'helpers': {
                'label': 'Хелперы',
                'responsible_role_id': 9200,
                'entry_role_id': 9210,
                'role_bundles': {
                    'admin': {'add_roles': [9200], 'remove_roles': []},
                },
                'roles': {
                    'master': 9211, 'curator': 9213,
                    'assistant': 9212, 'admin': 9214,
                },
            },
        },
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(raw, f)
    return raw


class BundlesVacationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg_path = os.path.join(self.tmp.name, 'sm.json')
        self.db_path = os.path.join(self.tmp.name, 't.db')
        _write_cfg(self.cfg_path)
        os.environ['STAFF_MANAGER_CONFIG'] = self.cfg_path
        CFG.CONFIG_PATH = self.cfg_path
        CFG._CFG = None
        CFG._INDEX = None
        CFG._ENABLED = False
        ok, err = CFG.reload_config(self.cfg_path)
        self.assertTrue(ok, err)
        with patch('services.staff_manager.store._db_path', return_value=self.db_path):
            ensure_tables()

    def tearDown(self):
        CFG._CFG = None
        CFG._INDEX = None
        CFG._ENABLED = False
        self.tmp.cleanup()

    def test_role_emoji_same_for_assistant_admin_but_label_has_name(self):
        a = format_role_label('assistant')
        b = format_role_label('admin')
        self.assertIn('🦋', a)
        self.assertIn('Assistent', a)
        self.assertIn('🦋', b)
        self.assertIn('Admin', b)
        self.assertNotEqual(a, b)

    def test_format_transition_and_actor(self):
        t = format_transition('curator', 'assistant')
        self.assertIn('🌂', t)
        self.assertIn('🦋', t)
        self.assertIn('→', t)
        lab = format_actor_label('Иван', 'admin')
        self.assertTrue(lab.startswith('🦋'))
        self.assertIn('Иван', lab)

    def test_branch_bundle_admin_adds_responsible(self):
        b = get_role_bundle('admin', 'helpers')
        self.assertIn(9200, b['add_roles'])
        b2 = get_role_bundle('admin', 'moderators')
        self.assertIn(9100, b2['add_roles'])

    def test_bundle_delta_promote_to_admin(self):
        add, rem = compute_bundle_delta(
            old_key='curator', new_key='admin', branch='helpers',
            current_role_ids={9213, 9210},
        )
        self.assertIn(9200, add)

    def test_bundle_delta_demote_removes_extras(self):
        add, rem = compute_bundle_delta(
            old_key='admin', new_key='curator', branch='helpers',
            current_role_ids={9214, 9210, 9200},
        )
        self.assertIn(9200, rem)

    def test_promotion_requirements_list_missing(self):
        ok, missing = get_promotion_requirements(
            'curator', days_in_role=2, active_warns=1, on_vacation=True)
        self.assertFalse(ok)
        self.assertTrue(any('времени' in m for m in missing))
        self.assertTrue(any('варн' in m.lower() for m in missing))
        self.assertTrue(any('отпуск' in m.lower() for m in missing))

    def test_actor_snapshot_persists(self):
        with patch('services.staff_manager.store._db_path', return_value=self.db_path):
            aid = record_action(
                guild_id=1, actor_id=100, target_id=200, action='promote',
                branch='helpers', old_key='curator', new_key='admin',
                actor_role_key='curator', actor_branch='helpers', ok=True,
            )
            rows = list_actions(1, 200, limit=5)
            self.assertEqual(rows[0]['id'], aid)
            self.assertEqual(rows[0].get('actor_role_key'), 'curator')
            # после «повышения» исполнителя снимок не меняется
            self.assertEqual(rows[0].get('actor_role_key'), 'curator')

    def test_vacation_keeps_staff_flag(self):
        with patch('services.staff_manager.store._db_path', return_value=self.db_path):
            create_vacation(
                guild_id=1, user_id=55, branch='helpers',
                role_snapshot={'roles': [], 'role_key': 'curator', 'rank': 2},
                rank_snapshot=2,
                start_at='2026-01-01T00:00:00+00:00',
                end_at='2026-01-10T00:00:00+00:00',
                status='active', requested_by=55, approved_by=100,
            )
            # без ladder-ролей, но с active vacation
            info = get_staff_info(55, role_ids=[9003], guild_id=1)
            self.assertTrue(info['is_staff'])
            self.assertTrue(info['on_vacation'])
            self.assertEqual(info.get('primary_key'), 'curator')
            self.assertEqual(info.get('primary_branch'), 'helpers')

    def test_self_vacation_allowed(self):
        actor = resolve_actor(55, [9111, 9110, 9002])
        target = resolve_target(55, [9111, 9110, 9002])
        ok, why = can_manage_staff(actor, target, 'vacation')
        self.assertTrue(ok, why)

    def test_apply_promote_adds_bundle_role(self):
        async def _run():
            guild = MagicMock()
            guild.id = 1
            roles = {}
            for rid, name in (
                (9211, 'Master'), (9213, 'Curator'), (9212, 'Asst'),
                (9214, 'Admin'), (9210, 'Helper'), (9200, 'Resp'),
                (9002, 'Staff'),
            ):
                r = MagicMock()
                r.id = rid
                r.name = name
                r.managed = False
                r.position = 10
                r.__ge__ = lambda self, other: self.position >= getattr(
                    other, 'position', 0)
                roles[rid] = r
            guild.get_role = lambda rid: roles.get(int(rid))
            me = MagicMock()
            me.guild_permissions.manage_roles = True
            top = MagicMock()
            top.position = 100
            me.top_role = top
            guild.me = me

            actor_m = MagicMock()
            actor_m.id = 100
            actor_m.roles = [MagicMock(id=9001)]

            target_m = MagicMock()
            target_m.id = 200
            # curator + entry helpers
            target_m.roles = [roles[9213], roles[9210], roles[9002]]

            async def _add(*rs, reason=''):
                have = {r.id for r in target_m.roles}
                for r in rs:
                    if r.id not in have:
                        target_m.roles.append(r)

            async def _rem(*rs, reason=''):
                ids = {r.id for r in rs}
                target_m.roles = [r for r in target_m.roles if r.id not in ids]

            target_m.add_roles = _add
            target_m.remove_roles = _rem

            async def _fetch(uid):
                m = MagicMock()
                m.id = uid
                m.roles = list(target_m.roles)
                m.guild = guild
                return m

            guild.fetch_member = _fetch

            with patch('services.staff_manager.store._db_path', return_value=self.db_path), \
                 patch('services.staff_manager.actions.claim_action_once', return_value=True), \
                 patch('services.staff_manager.actions.record_action'), \
                 patch('services.staff_manager.actions.upsert_staff_profile'), \
                 patch('services.warn_role.sync_warn_role', new_callable=AsyncMock):
                res = await ACT.apply_staff_change(
                    guild=guild, actor_member=actor_m, target_member=target_m,
                    action='promote', new_role_key='admin', new_branch='helpers',
                    reason='test', skip_acl=True,
                )
            self.assertTrue(res.ok, res.reason)
            self.assertIn(9214, res.added)  # admin
            self.assertIn(9200, res.added)  # Отвечаю за Helper
            self.assertIn(9213, res.removed)  # curator off

        asyncio.get_event_loop().run_until_complete(_run())

    def test_apply_vacation_strips_staff_keeps_never(self):
        async def _run():
            guild = MagicMock()
            guild.id = 1
            roles = {}
            for rid, name in (
                (9111, 'Master'), (9110, 'Mod'), (9002, 'Staff'),
                (9003, 'Vac'), (9999, 'Crown'),
            ):
                r = MagicMock()
                r.id = rid
                r.name = name
                r.managed = False
                r.position = 10
                r.__ge__ = lambda self, other: self.position >= getattr(
                    other, 'position', 0)
                roles[rid] = r
            guild.get_role = lambda rid: roles.get(int(rid))
            me = MagicMock()
            me.guild_permissions.manage_roles = True
            top = MagicMock()
            top.position = 100
            me.top_role = top
            guild.me = me

            actor_m = MagicMock()
            actor_m.id = 100
            actor_m.roles = [MagicMock(id=9001)]

            target_m = MagicMock()
            target_m.id = 200
            target_m.roles = [roles[9111], roles[9110], roles[9002], roles[9999]]

            async def _add(*rs, reason=''):
                have = {r.id for r in target_m.roles}
                for r in rs:
                    if r.id not in have:
                        target_m.roles.append(r)

            async def _rem(*rs, reason=''):
                ids = {r.id for r in rs}
                target_m.roles = [r for r in target_m.roles if r.id not in ids]

            target_m.add_roles = _add
            target_m.remove_roles = _rem

            async def _fetch(uid):
                m = MagicMock()
                m.id = uid
                m.roles = list(target_m.roles)
                m.guild = guild
                return m

            guild.fetch_member = _fetch

            with patch('services.staff_manager.store._db_path', return_value=self.db_path), \
                 patch('services.staff_manager.actions.claim_action_once', return_value=True), \
                 patch('services.staff_manager.actions.record_action'), \
                 patch('services.staff_manager.actions.upsert_staff_profile'), \
                 patch('services.warn_role.sync_warn_role', new_callable=AsyncMock):
                res = await ACT.apply_staff_change(
                    guild=guild, actor_member=actor_m, target_member=target_m,
                    action='vacation', reason='rest', skip_acl=True,
                )
            self.assertTrue(res.ok, res.reason)
            self.assertIn(9003, res.added)
            self.assertIn(9111, res.removed)
            self.assertIn(9110, res.removed)
            self.assertNotIn(9999, res.removed)  # never strip
            have = {r.id for r in target_m.roles}
            self.assertIn(9999, have)
            self.assertIn(9003, have)

        asyncio.get_event_loop().run_until_complete(_run())

    def test_no_universal_view_builder(self):
        import services.staff_manager.views as V
        # отдельные функции, не один build_all
        self.assertTrue(hasattr(V, 'build_profile_view'))
        self.assertTrue(hasattr(V, 'build_history_view'))
        self.assertTrue(hasattr(V, 'build_promotion_view'))
        self.assertTrue(hasattr(V, 'build_vacation_view'))
        self.assertTrue(hasattr(V, 'build_transfer_view'))
        self.assertTrue(hasattr(V, 'build_removal_view'))
        self.assertFalse(hasattr(V, 'build_all_screens'))
        self.assertFalse(hasattr(V, 'build_generic_panel'))

    def test_history_filter_helper(self):
        with patch('services.staff_manager.store._db_path', return_value=self.db_path):
            record_action(
                guild_id=1, actor_id=1, target_id=2, action='promote',
                branch='helpers', actor_role_key='admin', ok=True)
            record_action(
                guild_id=1, actor_id=1, target_id=2, action='demote',
                branch='helpers', actor_role_key='admin', ok=False)
            rows = list_actions_filtered(
                1, target_id=2, action='promote', limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['action'], 'promote')


if __name__ == '__main__':
    unittest.main()
