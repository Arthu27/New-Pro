# -*- coding: utf-8 -*-
"""Фирменные меню: gold-neon стикеры + Components V2 /modpanel (селект).

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
from services import menu_emojis as ME  # noqa: E402
from services import v2_layouts as V2  # noqa: E402
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


print('== stickers white neon files ==')
for key in ME.STICKER_KEYS:
    p = ME.sticker_path(key)
    check(p and os.path.getsize(p) > 500, f'sticker {key}')

print('== menu_banners ==')
for kind in ('modpanel', 'appeals'):
    img = MB.render_menu_banner(kind)
    check(img.size == (MB.W, MB.H), f'{kind} size')
check(MB.select_label('Варн').startswith('›'), 'select_label')
check(MB.select_emoji() == '🤍' or MB.select_emoji() is not None, 'select_emoji')

print('== emoji_for_action fallbacks ==')
check(ME.emoji_for_action('warn') == '⚠️', f"warn {ME.emoji_for_action('warn')!r}")
check(ME.emoji_for_action('ban') == '⛔', 'ban')
check(ME.emoji_for_action('clear') == '🧹', 'clear')
check(ME.ACTION_STICKER['warn'] == 'warn', 'map warn')
check(ME.ACTION_STICKER['unwarn'] == 'helper', 'map unwarn')

print('== modpanel V2 + select stickers ==')
check(V2.v2_available(), 'V2')
view = ModPanelView(None, None, list(MODPANEL_ACTIONS))
check(view.has_components_v2(), 'LayoutView')
check(view.action_select is not None, 'action_select')
check(len(view.action_select.options) == len(MODPANEL_ACTIONS), 'options count')
labs = [o.label for o in view.action_select.options]
check(all(l.startswith('›') for l in labs), f'labels › {labs[:3]}')
# без кнопок на главной
check(not getattr(view, 'action_buttons', None), 'без кнопок')
emojis = [str(o.emoji) for o in view.action_select.options]
check(len(set(emojis)) >= 4, f'разные эмодзи {emojis}')
check(all(e != '🤍' for e in emojis), f'не все 🤍: {emojis}')
# каждый select в своём чёрном Container
accents = []
for child in view.children:
    ac = getattr(child, 'accent_colour', None) or getattr(child, 'accent_color', None)
    if ac is not None:
        accents.append(int(ac.value) if hasattr(ac, 'value') else int(ac))
check(len(view.children) >= 3, f'раздельные блоки: {len(view.children)}')
check(accents and all(a == 0 for a in accents), f'accent чёрный: {accents}')
# баннер + без дубля «Панель модерации / HAKUMO» в тексте
from services.v2_layouts import SHOW_MENU_BANNER  # noqa: E402
check(SHOW_MENU_BANNER is True, 'баннер включён')
texts = []
for child in view.children:
    for k in list(getattr(child, 'children', []) or []):
        c = getattr(k, 'content', None)
        if c:
            texts.append(c)
joined = '\n'.join(texts)
check('Участник' in joined and 'Действие' in joined, 'подписи блоков')
check(joined.count('# Панель модерации') == 0 and 'HAKUMO' not in joined,
      f'без дубля заголовка: {joined!r}')
check(any(
    type(k).__name__ == 'MediaGallery'
    for child in view.children
    for k in list(getattr(child, 'children', []) or [])
), 'есть MediaGallery')
# footer без дубля
g = type('G', (), {'name': 'HAKUMO'})()
check(view._footer_text(g) == 'модерация', f"footer hakumo={view._footer_text(g)!r}")
g2 = type('G', (), {'name': 'My Server'})()
check(view._footer_text(g2) == 'My Server · модерация',
      f"footer other={view._footer_text(g2)!r}")
check(view._banner_file is not None, 'banner file attached')

print('== appeals ==')
from cogs.appeals import AppealMenuSelect, AppealMenuView  # noqa: E402
asel = AppealMenuSelect()
check(asel.options[0].label.startswith('›'), 'appeals label')
av = AppealMenuView()
check(av.has_components_v2(), 'appeals LayoutView')
av_acc = []
for child in av.children:
    ac = getattr(child, 'accent_colour', None) or getattr(child, 'accent_color', None)
    if ac is not None:
        av_acc.append(int(ac.value) if hasattr(ac, 'value') else int(ac))
check(av_acc and all(a == 0 for a in av_acc), f'appeals accent чёрный: {av_acc}')
check(len(av.children) >= 1, f'appeals блоки: {len(av.children)}')
check(MB.H == 420, f'баннер полный размер H={MB.H}')

art = '/opt/cursor/artifacts'
os.makedirs(art, exist_ok=True)
MB.render_menu_banner('modpanel').save(os.path.join(art, 'banner-modpanel.png'))
check(True, 'preview banner')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
