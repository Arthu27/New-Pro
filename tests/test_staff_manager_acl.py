# -*- coding: utf-8 -*-
"""Staff Manager ACL + consent + apply_staff_change verify."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.staff_manager import config as CFG
from services.staff_manager.acl import (
    resolve_actor, resolve_target, can_manage_staff, get_allowed_actions,
    get_staff_info,
)
from services.staff_manager.store import (
    ensure_tables, create_consent, get_consent, claim_consent_decision,
    expire_due_consents, claim_action_once, new_action_id,
)
from services.staff_manager import actions as ACT


def _write_cfg(path: str) -> dict:
    raw = {
        'staff_admin_role_id': 9001,
        'owner_ids': [100],
        'common_staff_role_id': 9002,
        'vacation_role_id': 9003,
        'log_channel_id': 1,
        'actions_channel_id': 1,
        'CONSENT_EXPIRE_HOURS': 48,
        'REQUIRE_CONSENT_FOR': ['transfer'],
        'SELFTEST_ROLE_ID': 9004,
        'ROLE_EMOJIS': {'master': '🟢', 'assistant': '🔵', 'curator': '🟣', 'admin': '🔴'},
        'BRANCH_EMOJIS': {'moderators': '🛡️', 'helpers': '🤝'},
        'ladder': [
            {'key': 'master', 'name': 'Master', 'rank': 1},
            {'key': 'curator', 'name': 'Curator', 'rank': 2},
            {'key': 'assistant', 'name': 'Assistent', 'rank': 3},
            {'key': 'admin', 'name': 'Admin', 'rank': 4, 'protected': True},
        ],
        'responsible_can_manage': ['master', 'curator', 'assistant'],
        'branch_admin_can_manage': [],
        'curator_can_manage': [],
        'allow_promotion_requests': True,
        'branches': {
            'moderators': {
                'label': 'Модераторы',
                'color': 1,
                'responsible_role_id': 9100,
                'entry_role_id': 9110,
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
                'entry_role_id': 9210,
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


RESULTS = []


class StaffAclTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls.path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        _write_cfg(cls.path)
        ok, err = CFG.reload_config(cls.path)
        assert ok, err
        # isolated db
        cls._db = tempfile.mkstemp(suffix='.db')[1]
        os.environ['STAFF_MANAGER_TEST_DB'] = cls._db

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls.path)
        except Exception:
            pass
        try:
            os.remove(cls._db)
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
        a = self._actor(10, [9100])
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
        t = self._target(20, [9210, 9213])
        ok, r = can_manage_staff(a, t, 'remove')
        self._check('5 resp remove helper curator', False, ok, r)

    def test_06_resp_transfer_denied(self):
        a = self._actor(10, [9100])
        t = self._target(20, [9110, 9111])
        ok, r = can_manage_staff(a, t, 'transfer', 'master', new_branch='helpers')
        self._check('6 resp transfer', False, ok, r)

    def test_07_curator_manage_denied_request_ok(self):
        a = self._actor(10, [9110, 9113])
        t = self._target(20, [9110, 9111])
        ok1, r1 = can_manage_staff(a, t, 'assign', 'master', new_branch='moderators')
        ok2, r2 = can_manage_staff(a, t, 'assign', 'admin', new_branch='moderators')
        ok3, r3 = can_manage_staff(a, t, 'request')
        self._check('7a curator assign', False, ok1, r1)
        self._check('7b curator Admin', False, ok2, r2)
        self._check('7c curator request', True, ok3, r3)

    def test_08_assistant_master_denied(self):
        for rid, label in ((9112, 'assistant'), (9111, 'master')):
            a = self._actor(10, [9110, rid])
            t = self._target(20, [])
            ok, r = can_manage_staff(a, t, 'assign', 'master', new_branch='moderators')
            self._check(f'8 {label} manage', False, ok, r)

    def test_09_staff_admin_admin_ok(self):
        a = self._actor(10, [9001])
        t = self._target(20, [9110, 9113])
        ok1, r1 = can_manage_staff(a, t, 'assign', 'admin', new_branch='moderators')
        t2 = self._target(21, [9110, 9114])
        ok2, r2 = can_manage_staff(a, t2, 'remove')
        self._check('9a SA→Admin', True, ok1, r1)
        self._check('9b SA remove Admin', True, ok2, r2)

    def test_10_sa_transfer_ok_touch_sa_owner_denied(self):
        a = self._actor(10, [9001])
        t = self._target(20, [9110, 9111])
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

    def test_12_branch_admin_no_rights(self):
        a = self._actor(10, [9110, 9114])
        t = self._target(20, [])
        ok, r = can_manage_staff(a, t, 'assign', 'master', new_branch='moderators')
        self._check('12 branch admin no rights', False, ok, r)

    def test_13_resp_remove_own_curator(self):
        a = self._actor(10, [9100])
        t = self._target(20, [9110, 9113])
        ok, r = can_manage_staff(a, t, 'remove')
        self._check('13 resp remove own curator', True, ok, r)

    def test_14_multi_branch(self):
        a_resp = self._actor(10, [9100])
        a_sa = self._actor(11, [9001])
        t = self._target(20, [9110, 9111, 9210, 9211])
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
        a2 = self._actor(12, [9110, 9113])
        t2 = self._target(20, [9110, 9111])
        al2 = get_allowed_actions(a2, t2)
        self.assertTrue(al2.get('can_request'))
        self.assertFalse(any(
            x in (al2.get('actions') or []) for x in ('assign', 'promote', 'demote')))
        RESULTS.append(('15b curator no manage menu', 'request only',
                        'request' if al2.get('can_request') else 'no', 'OK'))

    def test_16_stale_menu_recheck(self):
        a = self._actor(10, [])
        t = self._target(20, [])
        ok, r = can_manage_staff(a, t, 'assign', 'master', new_branch='moderators')
        self._check('16 stale actor', False, ok, r)

    def test_17_double_claim(self):
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
        ok = 'sync_warn_role' in src and 'fetch_member' in src and 'rollback' in src
        self.assertTrue(ok)
        RESULTS.append(('18 verify+rollback hooks', 'есть',
                        'есть' if ok else 'нет', 'OK' if ok else 'FAIL'))

    def test_19_requires_consent_transfer(self):
        self.assertTrue(CFG.requires_consent('transfer'))
        self.assertFalse(CFG.requires_consent('assign'))
        RESULTS.append(('19 consent for transfer', 'да',
                        'да' if CFG.requires_consent('transfer') else 'нет', 'OK'))

    def test_20_consent_only_target_accepts_once(self):
        ensure_tables()
        c = create_consent(
            guild_id=1, target_id=20, initiator_id=10, action='transfer',
            from_branch='moderators', to_branch='helpers', to_role_key='master',
            reason='t', expire_hours=48,
        )
        self.assertIsNotNone(c)
        # second pending blocked
        c2 = create_consent(
            guild_id=1, target_id=20, initiator_id=10, action='transfer',
            to_branch='helpers', to_role_key='master', reason='t2',
        )
        self.assertIsNone(c2)
        first = claim_consent_decision(c['id'], 'accepted')
        self.assertIsNotNone(first)
        second = claim_consent_decision(c['id'], 'accepted')
        self.assertIsNone(second)
        RESULTS.append(('20 consent once', '1 раз',
                        '1 раз' if first and not second and not c2 else 'FAIL',
                        'OK' if first and not second and not c2 else 'FAIL'))

    def test_21_consent_expired(self):
        ensure_tables()
        c = create_consent(
            guild_id=1, target_id=30, initiator_id=10, action='transfer',
            to_branch='helpers', to_role_key='master', reason='e',
            expire_hours=48,
        )
        # force expire
        from services.staff_manager import store as ST
        ST.update_consent  # noqa
        with ST._LOCK:
            conn = ST._conn()
            try:
                conn.execute(
                    'UPDATE staff_consents SET expires_at=? WHERE id=?',
                    ('2000-01-01T00:00:00+00:00', c['id']),
                )
                conn.commit()
            finally:
                conn.close()
        expired = expire_due_consents()
        ids = {x['id'] for x in expired}
        self.assertIn(c['id'], ids)
        again = claim_consent_decision(c['id'], 'accepted')
        self.assertIsNone(again)
        RESULTS.append(('21 expired consent', 'не принять',
                        'не принять' if again is None else 'принят',
                        'OK' if again is None else 'FAIL'))

    def test_22_get_staff_info_from_roles(self):
        info = get_staff_info(20, [9110, 9111])
        self.assertTrue(info['is_staff'])
        self.assertEqual(info['primary_key'], 'master')
        self.assertEqual(info['primary_branch'], 'moderators')
        RESULTS.append(('22 get_staff_info', 'master/mods',
                        f'{info["primary_key"]}/{info["primary_branch"]}', 'OK'))

    def test_23_apply_forbidden_no_success(self):
        """Forbidden от Discord → ok=False, без записи успеха."""
        async def _run():
            guild = MagicMock()
            guild.id = 1
            bot_role = MagicMock()
            bot_role.position = 5
            bot_role.name = 'Bot'
            bot_member = MagicMock()
            bot_member.top_role = bot_role
            bot_member.guild_permissions.manage_roles = True
            guild.me = bot_member

            def get_role(rid):
                r = MagicMock()
                r.id = rid
                r.name = f'R{rid}'
                r.position = 10  # выше бота
                r.managed = False
                r.__ge__ = lambda self, other: self.position >= other.position
                return r

            guild.get_role = get_role

            actor_m = MagicMock()
            actor_m.id = 10
            actor_m.roles = [MagicMock(id=9001)]
            target_m = MagicMock()
            target_m.id = 20
            target_m.roles = []

            result = await ACT.apply_staff_change(
                guild=guild,
                actor_member=actor_m,
                target_member=target_m,
                action='assign',
                new_role_key='master',
                new_branch='moderators',
                reason='test',
                source='test',
            )
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertFalse(result.ok)
        self.assertIn('ниже', result.reason.lower())
        RESULTS.append(('23 hierarchy reject', 'ошибка',
                        'ошибка' if not result.ok else 'успех',
                        'OK' if not result.ok else 'FAIL'))

    def test_24_apply_verify_fail_no_success(self):
        async def _run():
            guild = MagicMock()
            guild.id = 55
            bot_role = MagicMock()
            bot_role.position = 100
            bot_role.name = 'Bot'
            bot_member = MagicMock()
            bot_member.top_role = bot_role
            bot_member.guild_permissions.manage_roles = True
            guild.me = bot_member

            roles = {}

            def get_role(rid):
                if rid in roles:
                    return roles[rid]
                r = MagicMock()
                r.id = int(rid)
                r.name = f'R{rid}'
                r.position = 10
                r.managed = False
                r.__ge__ = lambda self, other: False
                roles[rid] = r
                return r

            guild.get_role = get_role

            actor_m = MagicMock()
            actor_m.id = 10
            actor_m.roles = [MagicMock(id=9001)]
            target_m = MagicMock()
            target_m.id = 77
            target_m.roles = []
            target_m.add_roles = AsyncMock()
            target_m.remove_roles = AsyncMock()

            # fetch returns member WITHOUT the added roles
            fresh = MagicMock()
            fresh.id = 77
            fresh.roles = []  # verify fail
            fresh.add_roles = AsyncMock()
            fresh.remove_roles = AsyncMock()
            guild.fetch_member = AsyncMock(return_value=fresh)

            result = await ACT.apply_staff_change(
                guild=guild,
                actor_member=actor_m,
                target_member=target_m,
                action='assign',
                new_role_key='master',
                new_branch='moderators',
                reason='verify',
                source='test',
            )
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertFalse(result.ok)
        self.assertIn('не применил', result.reason.lower())
        RESULTS.append(('24 verify fail', 'ошибка+откат',
                        'ошибка' if not result.ok else 'успех',
                        'OK' if not result.ok else 'FAIL'))

    def test_25_no_empty_except_in_actions(self):
        src = open('services/staff_manager/actions.py', encoding='utf-8').read()
        # bare except: pass
        bad = 'except:' in src or 'except Exception:\n            pass' in src
        self.assertFalse(bad)
        RESULTS.append(('25 no empty except', 'чисто',
                        'чисто' if not bad else 'есть',
                        'OK' if not bad else 'FAIL'))

    def test_26_static_no_bypass_add_roles(self):
        """В cog роли меняются только через apply_staff_change (кроме selftest)."""
        src = open('cogs/staff_manager.py', encoding='utf-8').read()
        # add_roles outside selftest / rollback comments
        lines = [ln for ln in src.splitlines()
                 if 'add_roles' in ln and 'selftest' not in ln.lower()
                 and 'staff_selftest' not in ln]
        # should be empty — apply is in actions.py
        self.assertEqual(lines, [])
        RESULTS.append(('26 no bypass add_roles in cog', '0',
                        str(len(lines)), 'OK' if not lines else 'FAIL'))


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(StaffAclTests)
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    print('\n=== ТАБЛИЦА САМОПРОВЕРКИ ===')
    print(f'{"сценарий":<40} {"ожидание":<14} {"получилось":<14} {"статус"}')
    for row in RESULTS:
        print(f'{row[0]:<40} {row[1]:<14} {row[2]:<14} {row[3]}')
    raise SystemExit(0 if res.wasSuccessful() else 1)
