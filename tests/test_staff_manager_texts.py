# -*- coding: utf-8 -*-
"""Стоп-слова и эмодзи в текстах Staff Manager."""
from __future__ import annotations

import unittest

from services.staff_manager import texts as T


class StaffTextsTests(unittest.TestCase):
    def test_no_stop_words_in_descriptions(self):
        blobs = []
        for d in (T.ACTION_DESC, T.ROLE_DESC, T.BRANCH_DESC, T.REMOVAL_KINDS,
                  T.ACTION_LABELS):
            blobs.extend(str(v) for v in d.values())
        for name in (
            'PANEL_TITLE', 'PANEL_MULTI', 'PANEL_DOUBLE', 'PANEL_QUEUE',
            'ERR_ADMIN_ONLY', 'ERR_OTHER_BRANCH', 'ERR_SELF',
            'CONSENT_BODY', 'REMOVE_DM_BODY',
        ):
            blobs.append(str(getattr(T, name)))
        joined = '\n'.join(blobs).lower()
        for w in T.STOP_IN_DESC:
            self.assertNotIn(
                w.lower(), joined,
                f'стоп-слово «{w}» в UI-текстах Staff Manager')

    def test_role_desc_covers_ladder(self):
        for key in ('master', 'curator', 'assistant', 'admin'):
            self.assertIn(key, T.ROLE_DESC)
            self.assertTrue(T.ROLE_DESC[key].strip())

    def test_every_action_has_label_and_desc(self):
        for key in T.ACTION_LABELS:
            if key == 'request':
                continue
            self.assertIn(key, T.ACTION_DESC)


if __name__ == '__main__':
    unittest.main()
