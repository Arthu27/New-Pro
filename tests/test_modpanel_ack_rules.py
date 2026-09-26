# -*- coding: utf-8 -*-
"""Модпанель: правила в варне везде + rebuild не убивает ActionSelect.
Запуск: python3 tests/test_modpanel_ack_rules.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_mp_ack_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== 1. Правила по действию ==')
from services import mod_reasons as MR  # noqa: E402

warn_n = len(MR.select_options_data('warn'))
ban_n = len(MR.select_options_data('ban'))
mute_n = len(MR.select_options_data('timeout'))
check(warn_n == 9, f'warn options={warn_n}')
check(ban_n == 5, f'ban options={ban_n}')
check(mute_n == 5, f'mute options={mute_n}')
check(all(MR.allows(c, 'warn') for c in MR.codes()), 'все коды допускают warn')

print('== 2. Helpers в moderation ==')
src = open(os.path.join(ROOT, 'cogs/moderation.py'), encoding='utf-8').read()
check('def _rule_select_options' in src, '_rule_select_options есть')
check('class _CtxWarnModal' in src, 'ПКМ Варн с правилами')
check("name='⚠️ Варн'" in src or 'name="⚠️ Варн"' in src, 'context menu Варн')
check('rebuild_selects=False' in src, 'member select не убивает ActionSelect')
check('refresh_target=True' in src, 'UserSelect обновляется отдельно')
check('def _relayout' in src, '_relayout есть')
# open: embeds=[] без отдельного embed= (discord.py Cannot mix)
idx = src.find('edit_kw = {')
chunk = src[idx:idx + 220] if idx >= 0 else ''
check("'embeds': []" in chunk and "'embed': None" not in chunk,
      'modpanel open: только embeds=[] (без mix embed)')
check("'attachments': []" in chunk or 'public_banner_url' in src,
      'баннер по HTTPS / без обязательного attachment')

print('== 3. Relayout сохраняет action_select ==')
# Лёгкий stub без discord gateway
import types  # noqa: E402

# Подгружаем moderation — нужен discord
from cogs import moderation as MOD  # noqa: E402


class _FakeMember:
    def __init__(self, uid=1):
        self.id = uid
        self.roles = []
        self.guild = None
        self.display_name = 'm'


class _FakeCog:
    pass


# ModPanelView требует discord LayoutView — создаём минимально
try:
    cog = _FakeCog()
    member = _FakeMember(42)
    # allowed list as MODPANEL_ACTIONS subset
    allowed = [a for a in MOD.MODPANEL_ACTIONS if a[0] in ('warn', 'ban', 'mute')]
    view = MOD.ModPanelView(cog, member, allowed)
    a1 = view.action_select
    t1 = view.target_select
    view.selected_uid = '99'
    view._relayout(None, refresh_target=True)
    check(view.action_select is a1, 'ActionSelect тот же объект после relayout')
    check(view.target_select is not t1, 'UserSelect новый после refresh_target')
    view._rebuild(None)
    check(view.action_select is not a1, 'полный rebuild даёт новый ActionSelect')
except Exception as ex:
    check(False, f'relayout sim: {ex}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
