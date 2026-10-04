# -*- coding: utf-8 -*-
"""Панель: разварн / размут / разбан рядом с варном / мутом / баном."""
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


print('== panel lift actions ==')
app = (ROOT / 'web' / 'app.py').read_text(encoding='utf-8')
tpl = (ROOT / 'web' / 'templates' / '_punish.html').read_text(encoding='utf-8')
mem = (ROOT / 'web' / 'templates' / 'member.html').read_text(encoding='utf-8')
base = (ROOT / 'web' / 'templates' / 'base.html').read_text(encoding='utf-8')

check("'unwarn'" in app and "'unmute'" in app and "'unban'" in app,
      'actions in ROLE_PUNISH / api')
check("_LIFT_ACTIONS" in app, 'lift set')
check("'Разварн'" in app and "'Размут'" in app and "'Разбан'" in app,
      'RU labels')
check("action == 'unwarn'" in app or "action == 'unwarn'" in app.replace('"', "'"),
      'api handles unwarn')
check("action == 'unmute'" in app, 'api handles unmute')
check("action == 'unban'" in app, 'api handles unban')
check('remove_last_warning' in app, 'unwarn uses warnings cog')
check('clear_all_mutes' in app, 'unmute clears mute roles')
check('_unban_role' in app, 'unban clears ban role')

check('unwarn' in tpl and 'unmute' in tpl and 'unban' in tpl, 'punish dialog lift seg')
check('isLift' in tpl and "textContent = lift ? 'Снять'" in tpl, 'dialog switches to Снять')
check("a in ('unwarn','unmute','unban')" in mem or "unwarn','unmute','unban" in mem,
      'member profile lift buttons')
check('?v=25' in base, 'css bump')

print(f'\n{PASS} passed, {FAIL} failed')
raise SystemExit(1 if FAIL else 0)
