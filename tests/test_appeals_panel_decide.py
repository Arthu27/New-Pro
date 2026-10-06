# -*- coding: utf-8 -*-
"""Апелляции: принять / отклонить / чёрный список (панель + Discord)."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import os

_TMP = tempfile.mkdtemp(prefix='hakumo_ap_decide_')
os.chdir(_TMP)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')

PASS = FAIL = 0
UTC = timezone.utc
NOW = datetime(2026, 10, 4, 20, 0, 0, tzinfo=UTC)


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== source: panel + discord blacklist ==')
app = (ROOT / 'web' / 'app.py').read_text(encoding='utf-8')
cog = (ROOT / 'cogs' / 'appeals.py').read_text(encoding='utf-8')
tpl = (ROOT / 'web' / 'templates' / 'appeals.html').read_text(encoding='utf-8')
base = (ROOT / 'web' / 'templates' / 'base.html').read_text(encoding='utf-8')

check('def api_appeals_decide' in app, 'panel decide API')
check("_panel_appeal_side_effects" in app, 'side effects helper')
check('blacklist_appeal_user' in cog and 'is_appeal_blacklisted' in cog,
      'blacklist helpers')
check("value='blacklist'" in cog, 'discord select has blacklist')
check('data-act="accept"' in tpl and 'data-act="reject"' in tpl
      and 'data-act="blacklist"' in tpl, 'UI buttons')
check('?v=23' in base, 'css bump')

print('== runtime: blacklist blocks create ==')
from cogs import appeals as ap

st = ap.empty_state()
it, err = ap.create_appeal(st, 42, 'BanMe', 'прошу разбанить, это ошибка', NOW)
check(it is not None and err is None, 'create ok')
ap.resolve_appeal(st, it['id'], False, 'Mod', NOW, reply='нет')
ap.blacklist_appeal_user(st, 42, by='Mod', reason='апелляция #1', now=NOW)
check(ap.is_appeal_blacklisted(st, 42), 'flagged blacklisted')
again, err2 = ap.create_appeal(
    st, 42, 'BanMe', 'ещё одна попытка после ЧС, длинный текст',
    NOW)
check(again is None and 'чёрном списке' in (err2 or ''),
      'blacklisted cannot re-appeal', err2)

print(f'\n{PASS} passed, {FAIL} failed')
raise SystemExit(1 if FAIL else 0)
