# -*- coding: utf-8 -*-
"""Фирменные меню: баннеры HAKUMO + Components V2 /modpanel (кнопки).

Запуск: python3 tests/test_menu_banners.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_menus_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services import menu_banners as MB  # noqa: E402
from services import v2_layouts as V2  # noqa: E402
from cogs.moderation import (  # noqa: E402
    ModPanelView, ModActionSelect, ModActionButton, MODPANEL_ACTIONS,
    MODPANEL_EMOJI)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== menu_banners render ==')
for kind in ('modpanel', 'appeals', 'staff'):
    img = MB.render_menu_banner(kind)
    check(img.size == (MB.W, MB.H), f'{kind}: размер {img.size}')
    raw = MB.menu_banner_bytes(kind)
    check(raw[:8] == b'\x89PNG\r\n\x1a\n', f'{kind}: валидный PNG ({len(raw)} bytes)')
    bio, name = MB.menu_banner_file(kind)
    check(name.endswith('.png') and bio.getvalue()[:4] == b'\x89PNG',
          f'{kind}: file payload {name}')

check(MB.select_label('Варн').startswith('›'),
      f"select_label: {MB.select_label('Варн')!r}")
check(MB.select_emoji() == '🤍', 'emoji 🤍 default')

print('== modpanel Components V2 + buttons ==')
check(V2.v2_available(), 'V2 доступны')
view = ModPanelView(None, None, list(MODPANEL_ACTIONS))
check(view.has_components_v2(), 'LayoutView V2')
box = view.children[0]
check(type(box).__name__ == 'Container', 'Container')
btns = [c for c in view.action_buttons]
check(len(btns) == len(MODPANEL_ACTIONS),
      f'кнопок {len(btns)} == действий {len(MODPANEL_ACTIONS)}')
check(all(isinstance(b, ModActionButton) for b in btns), 'тип ModActionButton')
check(any(b.action == 'warn' for b in btns), 'есть Варн')
check(any(b.action == 'ban' for b in btns), 'есть Бан')
# разные эмодзи, не все 🤍
emojis = {str(b.emoji) for b in btns if b.emoji}
check(len(emojis) >= 4, f'разные эмодзи: {emojis}')
check('🤍' not in emojis, f'без одинакового 🤍: {emojis}')
check(any(type(c).__name__ == 'MediaGallery' for c in box.children),
      'MediaGallery')
texts = [getattr(c, 'content', '') for c in box.children
         if type(c).__name__ == 'TextDisplay']
check(any('Действие' in t for t in texts), f'секция Действие: {texts}')

# mute submenu select still works
sel = ModActionSelect(None, allowed=list(MODPANEL_ACTIONS)[:3])
check(len(sel.options) == 3, 'подменю-селект жив')
check(all(o.emoji and str(o.emoji) != '🤍' for o in sel.options),
      f'подменю эмодзи: {[o.emoji for o in sel.options]}')

print('== appeals select ==')
from cogs.appeals import AppealMenuSelect  # noqa: E402
asel = AppealMenuSelect()
check(asel.options[0].label.startswith('›'),
      f'appeals label: {asel.options[0].label!r}')

art = '/opt/cursor/artifacts'
os.makedirs(art, exist_ok=True)
for kind in ('modpanel', 'appeals'):
    path = os.path.join(art, f'banner-{kind}.png')
    MB.render_menu_banner(kind).save(path)
    check(os.path.isfile(path) and os.path.getsize(path) > 1000,
          f'preview saved {path}')

print('== stickers ==')
paths = MB.ensure_sticker_pack(os.path.join(_TMP, 'stickers'))
check(len(paths) >= 6, f'stickers {len(paths)}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
