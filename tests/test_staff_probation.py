# -*- coding: utf-8 -*-
"""Испытательный срок: старт, лимиты, авто из бандла."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from services.staff_manager import config as CFG
from services.staff_manager.probation import (
    maybe_start_after_promote, start_probation, end_probation,
)
from services.staff_manager.store import active_probation_for, ensure_tables


def _write_cfg(path: str):
    raw = {
        'staff_admin_role_id': 9001,
        'owner_ids': [100],
        'common_staff_role_id': 9002,
        'vacation_role_id': 9003,
        'ROLE_EMOJIS': {
            'master': '⚔️', 'curator': '🌂',
            'assistant': '🦋', 'admin': '🦋',
        },
        'PROBATION_PRESETS': [
            {'key': '7d', 'label': '7 дней', 'days': 7},
        ],
        'ROLE_BUNDLES': {
            'master': {
                'add_roles': [], 'remove_roles': [],
                'requires': {}, 'probation_days': 7,
            },
            'curator': {
                'add_roles': [], 'remove_roles': [],
                'requires': {'not_on_probation': True},
                'probation_days': 0,
            },
        },
        'ladder': [
            {'key': 'master', 'name': 'Master', 'rank': 1},
            {'key': 'curator', 'name': 'Curator', 'rank': 2},
            {'key': 'assistant', 'name': 'Assistent', 'rank': 3},
            {'key': 'admin', 'name': 'Admin', 'rank': 4, 'protected': True},
        ],
        'responsible_can_manage': ['master', 'curator', 'assistant'],
        'branches': {
            'helpers': {
                'label': 'Хелперы',
                'responsible_role_id': 9200,
                'entry_role_id': 9210,
                'roles': {
                    'master': 9211, 'curator': 9213,
                    'assistant': 9212, 'admin': 9214,
                },
            },
        },
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(raw, f)


class ProbationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg_path = os.path.join(self.tmp.name, 'sm.json')
        self.db_path = os.path.join(self.tmp.name, 't.db')
        _write_cfg(self.cfg_path)
        CFG.CONFIG_PATH = self.cfg_path
        os.environ['STAFF_MANAGER_CONFIG'] = self.cfg_path
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

    def _member(self, uid, roles):
        m = MagicMock()
        m.id = uid
        m.roles = [MagicMock(id=r) for r in roles]
        m.guild = MagicMock(id=1)
        return m

    def test_start_and_active(self):
        actor = self._member(100, [9001])
        target = self._member(55, [9211, 9210, 9002])
        with patch('services.staff_manager.store._db_path', return_value=self.db_path), \
             patch('services.staff_manager.probation.record_action'):
            ok, why, row = start_probation(
                guild_id=1, actor_member=actor, target_member=target,
                days=7, reason='test')
            self.assertTrue(ok, why)
            self.assertEqual(row['days'], 7)
            active = active_probation_for(1, 55)
            self.assertIsNotNone(active)
            ok2, why2, _ = start_probation(
                guild_id=1, actor_member=actor, target_member=target,
                days=3, reason='again')
            self.assertFalse(ok2)

    def test_end_early(self):
        actor = self._member(100, [9001])
        target = self._member(55, [9211, 9210, 9002])
        with patch('services.staff_manager.store._db_path', return_value=self.db_path), \
             patch('services.staff_manager.probation.record_action'):
            start_probation(
                guild_id=1, actor_member=actor, target_member=target, days=7)
            ok, why = end_probation(
                guild_id=1, actor_id=100, user_id=55, end_kind='early')
            self.assertTrue(ok, why)
            self.assertIsNone(active_probation_for(1, 55))

    def test_auto_from_bundle(self):
        actor = self._member(100, [9001])
        target = self._member(55, [9211, 9210, 9002])
        with patch('services.staff_manager.store._db_path', return_value=self.db_path), \
             patch('services.staff_manager.probation.record_action'):
            row = maybe_start_after_promote(
                guild_id=1, actor_member=actor, target_member=target,
                new_role_key='master', branch='helpers')
            self.assertIsNotNone(row)
            self.assertEqual(int(row['days']), 7)


if __name__ == '__main__':
    unittest.main()
