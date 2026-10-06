# -*- coding: utf-8 -*-
"""Профиль участника: таблицы людей + нормальный поиск."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== member page tables + search ==')
app = (ROOT / 'web' / 'app.py').read_text(encoding='utf-8')
tpl = (ROOT / 'web' / 'templates' / 'member.html').read_text(encoding='utf-8')
partial = (ROOT / 'web' / 'templates' / '_profiles_table.html').read_text(encoding='utf-8')
css = (ROOT / 'web' / 'static' / 'panel.css').read_text(encoding='utf-8')
base = (ROOT / 'web' / 'templates' / 'base.html').read_text(encoding='utf-8')

check('def _users_directory(' in app, '_users_directory helper')
check('staff_rows' in app and 'punished_rows' in app and 'people_rows' in app,
      'member() passes people tables')
check("limit=24" in app or "request.args.get('limit')" in app, 'search API accepts limit')
check("'role_label'" in app and 'api_users_search' in app, 'search returns role_label')

check('id="mlive"' in tpl and 'mlive-body' in tpl, 'live results table')
check('id="mstaff"' in tpl and 'id="mpunished"' in tpl and 'id="mpeople"' in tpl,
      'staff / punished / people sections')
check('_profiles_table.html' in tpl, 'reuses profiles table partial')
check('ArrowDown' in tpl and 'ArrowUp' in tpl, 'keyboard navigation')
check('/api/users/search?q=' in tpl and 'limit=24' in tpl, 'live Discord search')
check('filterTables' in tpl, 'local table filter while typing')

check('profiles-table' in partial and 'data-find=' in partial, 'partial has searchable rows')
check('sq-table' in partial and 'sq-stat' in partial, 'square table markup')
check('sq-wrap' in css and 'border-radius: 4px' in css, 'square table styles')
check('panel.css' in base and ('?v=22' in base or '?v=23' in base), 'CSS cache bump')

print(f'\n{PASS} passed, {FAIL} failed')
raise SystemExit(1 if FAIL else 0)
