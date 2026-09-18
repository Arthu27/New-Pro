# -*- coding: utf-8 -*-
"""Фирменные меню: баннеры HAKUMO + селекты «🤍 › …».

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
from cogs.moderation import ModPanelView, ModActionSelect, MODPANEL_ACTIONS  # noqa: E402

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
check(MB.select_emoji() == '🤍', 'emoji 🤍')

print('== modpanel payload ==')
view = ModPanelView(None, None, list(MODPANEL_ACTIONS))
embed, banner = view.panel_payload(None)
check(embed.image.url and 'attachment://' in embed.image.url,
      f'embed image attachment: {embed.image.url}')
check(embed.color and embed.color.value == 0x1E1430,
      f'тёмный цвет эмбеда ({embed.color.value:#x})')
check(getattr(embed.author, 'name', None) == 'HAKUMO' or
      (embed.author and embed.author.name == 'HAKUMO'),
      f'author HAKUMO: {embed.author}')
check('Панель модерации' in (embed.title or ''),
      f'title: {embed.title!r}')
check(banner.filename.endswith('.png'), f'file name {banner.filename}')

sel = ModActionSelect(None, allowed=list(MODPANEL_ACTIONS)[:3])
labs = [o.label for o in sel.options]
check(all(l.startswith('›') for l in labs), f'labels › …: {labs}')
check(all(str(o.emoji) == '🤍' or getattr(o.emoji, 'name', None) == '🤍'
          or str(getattr(o.emoji, 'name', o.emoji)) == '🤍'
          for o in sel.options),
      f'emoji 🤍 на опциях: {[o.emoji for o in sel.options]}')

print('== appeals select ==')
from cogs.appeals import AppealMenuSelect  # noqa: E402
asel = AppealMenuSelect()
check(asel.options[0].label.startswith('›'),
      f'appeals label: {asel.options[0].label!r}')
check('апелляц' in asel.placeholder.lower() or 'присоединиться' in asel.placeholder.lower()
      or 'обратиться' in asel.placeholder.lower(),
      f'appeals placeholder: {asel.placeholder!r}')

# сохранить превью в artifacts
art = '/opt/cursor/artifacts'
os.makedirs(art, exist_ok=True)
for kind in ('modpanel', 'appeals'):
    path = os.path.join(art, f'banner-{kind}.png')
    MB.render_menu_banner(kind).save(path)
    check(os.path.isfile(path) and os.path.getsize(path) > 1000,
          f'preview saved {path}')

print('== stickers pack ==')
paths = MB.ensure_sticker_pack(os.path.join(_TMP, 'stickers'))
check(len(paths) >= 6, f'stickers generated: {len(paths)}')
check(all(os.path.getsize(p) > 500 for p in paths), 'stickers non-empty')
st = MB.render_sticker('warn', 128)
check(st.size == (128, 128), 'warn sticker 128x128')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
