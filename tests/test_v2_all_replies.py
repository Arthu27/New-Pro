#!/usr/bin/env python3
"""Components V2: меню + ответы бота без классических embed-ответов."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        print(f'  PASS: {msg}')
        PASS += 1
    else:
        print(f'  FAIL: {msg}')
        FAIL += 1


print('== v2 helpers ==')
from services.v2_layouts import (  # noqa: E402
    V2_AVAILABLE, notice_from_embed, respond_v2, reply_embed_v2,
    reply_text_v2, send_dm_v2, success_notice_view, build_staff_menu_items,
    build_appeals_menu_items,
)
import discord  # noqa: E402

check(V2_AVAILABLE, 'Components V2 доступны')
check(callable(respond_v2), 'respond_v2')
check(callable(reply_embed_v2), 'reply_embed_v2')
check(callable(reply_text_v2), 'reply_text_v2')
check(callable(send_dm_v2), 'send_dm_v2')

e = discord.Embed(title='Тест', description='## ✅ Готово\nВсё ок', color=0x2ECC71)
e.add_field(name='Поле', value='значение')
v = notice_from_embed(e)
check(v is not None, 'notice_from_embed из success')
check(getattr(v, 'has_components_v2', lambda: False)(), 'LayoutView V2 flag')
plain = ''
try:
    from services.v2_layouts import layout_plain_text
    plain = layout_plain_text(v)
except Exception as ex:
    plain = str(ex)
check('Готово' in plain or 'Всё ок' in plain or 'Поле' in plain,
      f'layout_plain_text содержит контент: {plain[:80]!r}')

sv = success_notice_view('Ок', 'тело')
check(sv is not None and sv.has_components_v2(), 'success_notice_view')

print('== menus LayoutView ==')
from cogs.appeals import AppealMenuView, AppealMenuSelect  # noqa: E402
from cogs.staff_apply import StaffApplyView, RoleSelect  # noqa: E402

av = AppealMenuView()
check(isinstance(av, discord.ui.LayoutView), 'AppealMenuView = LayoutView')
check(av.has_components_v2(), 'AppealMenuView V2')

sv_menu = StaffApplyView(banner_filename='staff_banner.png')
check(isinstance(sv_menu, discord.ui.LayoutView), 'StaffApplyView = LayoutView')
check(sv_menu.has_components_v2(), 'StaffApplyView V2')
check(len(sv_menu.children) >= 1, f'staff children: {len(sv_menu.children)}')

sel = RoleSelect()
items = build_staff_menu_items(
    banner_filename='staff_banner.png', body='тест', role_select=sel)
check(bool(items), 'build_staff_menu_items')

asel = AppealMenuSelect()
aitems = build_appeals_menu_items(
    banner_filename='x.png', body='тест', footer='', menu_select=asel)
check(bool(aitems), 'build_appeals_menu_items')

print('== source contracts ==')
mod_src = open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read()
check('notice_from_embed' in mod_src, 'moderation _respond → V2')
check('reply_embed_v2' in mod_src, 'modpanel ACL → reply_embed_v2')

warn_src = open(os.path.join(ROOT, 'cogs', 'warnings.py'), encoding='utf-8').read()
check('reply_embed_v2' in warn_src, 'warnings → reply_embed_v2')
check('send_dm_v2' in warn_src, 'warnings DM → send_dm_v2')

staff_src = open(os.path.join(ROOT, 'cogs', 'staff_apply.py'), encoding='utf-8').read()
check('class StaffApplyView(discord.ui.LayoutView)' in staff_src,
      'StaffApplyView LayoutView в исходнике')
check('build_staff_menu_items' in staff_src, 'staff panel build_staff_menu_items')
check('respond_v2' in staff_src, 'staff replies respond_v2')

eh_src = open(os.path.join(ROOT, 'error_handler.py'), encoding='utf-8').read()
check('reply_embed_v2' in eh_src, 'error_handler → reply_embed_v2')

app_src = open(os.path.join(ROOT, 'cogs', 'appeals.py'), encoding='utf-8').read()
check('class AppealMenuView(discord.ui.LayoutView)' in app_src,
      'AppealMenuView LayoutView')
check('reply_embed_v2' in app_src or 'reply_text_v2' in app_src,
      'appeals replies V2')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
raise SystemExit(1 if FAIL else 0)
