# -*- coding: utf-8 -*-
"""Staff Manager ACL: матрица прав + self-check таблица."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

# bootstrap config before imports that read get_config
from services.staff_manager import config as CFG
from services.staff_manager.acl import (
    resolve_actor, resolve_target, can_manage_staff, get_allowed_actions,
)


def _write_cfg(path: str) -> dict:
    raw = {
        'staff_admin_role_id': 9001,
        'owner_ids': [100],
        'common_staff_role_id': 9002,
        'log_channel_id': 1,
        'actions_channel_id': 1,
        'ladder': [
            {'key': 'master', 'name': 'Master', 'rank': 1},
            {'key': 'assistant', 'name': 'Assistant', 'rank': 2},
            {'key': 'curator', 'name': 'Curator', 'rank': 3},
            {'key': 'admin', 'name': 'Admin', 'rank': 4, 'protected': True},
        ],
        'responsible_can_manage': ['master', 'assistant', 'curator'],
        'branch_admin_can_manage': [],
        'curator_can_manage': [],
        'allow_promotion_requests': True,
        'branches': {
            'moderators': {
                'label': 'Модераторы',
                'color': 1,
                'responsible_role_id': 9100,
                'roles': {
                    'master': 9111,
                    'assistant': 9112,
                    'curator': 9113,
                    'admin': 9114,
                },
            },
            'helpers': {
                'label': 'Хелперы',
                'color': 2,
                'responsible_role_id': 9200,
                'roles': {
                    'master': 9211,
                    'assistant': 9212,
                    'curator': 9213,
                    'admin': 9214,
                },
            },
        },
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(raw, f)
    return raw


class StaffAclTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls.path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        _write_cfg(cls.path)
        ok, err = CFG.reload_config(cls.path)
        assert ok, err

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls.path)
        except Exception:
            pass

    def _actor(self, uid, roles):
        return resolve_actor(uid, roles)

    def _target(self, uid, roles):
        return resolve_target(uid, roles)

    def _check(self, name, ok_expected, actual_ok, reason=''):
        self.assertEqual(
            bool(actual_ok), bool(ok_expected),
            f'{name}: expected {ok_expected} got {actual_ok} ({reason})')
        RESULTS.append((name, 'РАЗРЕШЕНО' if ok_expected else 'ОТКАЗ',
                        'РАЗРЕШЕНО' if actual_ok else 'ОТКАЗ',
                        'OK' if bool(actual_ok) == bool(ok_expected) else 'FAIL'))

    def test_01_resp_assign_master_mods(self):
        a = self._actor(10, [9100])  # responsible mods
        t = self._target(20, [])
        ok, r = can_manage_staff(a, t, 'assign', 'master', new_branch='moderators')
        self._check('1 resp→Master mods', True, ok, r)

    def test_02_resp_assign_curator_mods(self):
        a = self._actor(10, [9100])
        t = self._target(20, [])
        ok, r = can_manage_staff(a, t, 'assign', 'curator', new_branch='moderators')
        self._check('2 resp→Curator mods', True, ok, r)

    def test_03_resp_assign_admin_denied(self):
        a = self._actor(10, [9100])
        t = self._target(20, [])
        ok, r = can_manage_staff(a, t, 'assign', 'admin', new_branch='moderators')
        self._check('3 resp→Admin', False, ok, r)

    def test_04_resp_master_helpers_denied(self):
        a = self._actor(10, [9100])
        t = self._target(20, [])
        ok, r = can_manage_staff(a, t, 'assign', 'master', new_branch='helpers')
        self._check('4 resp→Master helpers', False, ok, r)

    def test_05_resp_remove_helper_curator_denied(self):
        a = self._actor(10, [9100])
        t = self._target(20, [9213])  # helpers curator
        ok, r = can_manage_staff(a, t, 'remove')
        self._check('5 resp remove helper curator', False, ok, r)

    def test_06_resp_transfer_denied(self):
        a = self._actor(10, [9100])
        t = self._target(20, [9111])
        ok, r = can_manage_staff(a, t, 'transfer', 'master', new_branch='helpers')
        self._check('6 resp transfer', False, ok, r)

    def test_07_curator_manage_denied_request_ok(self):
        a = self._actor(10, [9113])  # mods curator
        t = self._target(20, [9111])
        ok1, r1 = can_manage_staff(a, t, 'assign', 'master', new_branch='moderators')
        ok2, r2 = can_manage_staff(a, t, 'assign', 'admin', new_branch='moderators')
        ok3, r3 = can_manage_staff(a, t, 'request')
        self._check('7a curator assign', False, ok1, r1)
        self._check('7b curator Admin', False, ok2, r2)
        self._check('7c curator request', True, ok3, r3)

    def test_08_assistant_master_denied(self):
        for rid, label in ((9112, 'assistant'), (9111, 'master')):
            a = self._actor(10, [rid])
            t = self._target(20, [])
            ok, r = can_manage_staff(a, t, 'assign', 'master', new_branch='moderators')
            self._check(f'8 {label} manage', False, ok, r)

    def test_09_staff_admin_admin_ok(self):
        a = self._actor(10, [9001])
        t = self._target(20, [9113])
        ok1, r1 = can_manage_staff(a, t, 'assign', 'admin', new_branch='moderators')
        t2 = self._target(21, [9114])
        ok2, r2 = can_manage_staff(a, t2, 'remove')
        self._check('9a SA→Admin', True, ok1, r1)
        self._check('9b SA remove Admin', True, ok2, r2)

    def test_10_sa_transfer_ok_touch_sa_owner_denied(self):
        a = self._actor(10, [9001])
        t = self._target(20, [9111])
        ok1, r1 = can_manage_staff(a, t, 'transfer', 'master', new_branch='helpers')
        t_sa = self._target(11, [9001])
        ok2, r2 = can_manage_staff(a, t_sa, 'remove')
        t_own = self._target(100, [])
        ok3, r3 = can_manage_staff(a, t_own, 'remove')
        self._check('10a SA transfer', True, ok1, r1)
        self._check('10b SA→SA', False, ok2, r2)
        self._check('10c SA→owner', False, ok3, r3)

    def test_11_self_denied(self):
        a = self._actor(10, [9100])
        t = self._target(10, [])
        ok, r = can_manage_staff(a, t, 'assign', 'master', new_branch='moderators')
        self._check('11 self', False, ok, r)

    def test_12_rank_ge_denied_for_non_resp(self):
        # curator with somehow manage rights empty — already denied
        # simulate branch_admin with manage list empty: denied
        a = self._actor(10, [9114])  # branch admin, no manage list
        t = self._target(20, [])
        ok, r = can_manage_staff(a, t, 'assign', 'master', new_branch='moderators')
        self._check('12 branch admin no rights', False, ok, r)

    def test_13_equal_rank_target(self):
        # responsible can manage curator of own branch (in list)
        a = self._actor(10, [9100])
        t = self._target(20, [9113])
        ok, r = can_manage_staff(a, t, 'remove')
        self._check('13 resp remove own curator', True, ok, r)

    def test_14_multi_branch(self):
        a_resp = self._actor(10, [9100])
        a_sa = self._actor(11, [9001])
        t = self._target(20, [9111, 9211])  # both branches
        ok1, r1 = can_manage_staff(a_resp, t, 'remove')
        ok2, r2 = can_manage_staff(a_sa, t, 'remove')
        self._check('14a multi resp', False, ok1, r1)
        self._check('14b multi SA', True, ok2, r2)
        self.assertIn('ALERT', r2)

    def test_15_select_roles_no_admin_for_resp(self):
        a = self._actor(10, [9100])
        t = self._target(20, [])
        allowed = get_allowed_actions(a, t)
        keys = [r['key'] for r in allowed['roles']]
        self.assertNotIn('admin', keys)
        RESULTS.append(('15 resp roles no Admin', 'нет Admin',
                        'нет Admin' if 'admin' not in keys else 'есть Admin',
                        'OK' if 'admin' not in keys else 'FAIL'))
        # curator: no manage UI roles
        a2 = self._actor(12, [9113])
        t2 = self._target(20, [9111])
        al2 = get_allowed_actions(a2, t2)
        self.assertTrue(al2.get('can_request'))
        self.assertFalse(any(
            x in (al2.get('actions') or []) for x in ('assign', 'promote', 'demote')))
        RESULTS.append(('15b curator no manage menu', 'request only',
                        'request' if al2.get('can_request') else 'no',
                        'OK'))

    def test_16_stale_menu_recheck(self):
        # actor was responsible, then roles empty → deny
        a = self._actor(10, [])  # lost responsible
        t = self._target(20, [])
        ok, r = can_manage_staff(a, t, 'assign', 'master', new_branch='moderators')
        self._check('16 stale actor', False, ok, r)

    def test_17_double_claim(self):
        from services.staff_manager.store import claim_action_once, ensure_tables, new_action_id
        ensure_tables()
        aid = new_action_id()
        first = claim_action_once(1, 20, aid)
        second = claim_action_once(1, 20, aid)
        self.assertTrue(first)
        self.assertFalse(second)
        RESULTS.append(('17 double confirm', '1 раз',
                        '1 раз' if first and not second else 'дубль',
                        'OK' if first and not second else 'FAIL'))

    def test_18_warn_sync_hooks_present(self):
        src = open('services/staff_manager/actions.py', encoding='utf-8').read()
        ok = 'sync_warn_role' in src and 'upsert_member' in src
        self.assertTrue(ok)
        RESULTS.append(('18 warn/cache sync hooks', 'есть',
                        'есть' if ok else 'нет', 'OK' if ok else 'FAIL'))


RESULTS = []


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(StaffAclTests)
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    print('\n=== ТАБЛИЦА САМОПРОВЕРКИ ===')
    print(f'{"сценарий":<40} {"ожидание":<14} {"получилось":<14} {"статус"}')
    for row in RESULTS:
        print(f'{row[0]:<40} {row[1]:<14} {row[2]:<14} {row[3]}')
    raise SystemExit(0 if res.wasSuccessful() else 1)
