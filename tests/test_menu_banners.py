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
for kind in ('modpanel', 'appeals', 'staff', 'events'):
    img = MB.render_menu_banner(kind)
    check(img.size == (MB.W, MB.H), f'{kind} size')
check(MB.select_label('Варн').startswith('›'), 'select_label')
check(MB.select_emoji() == '🤍' or MB.select_emoji() is not None, 'select_emoji')

print('== banner pills без дублей headline/Hakumo ==')
import re as _re
for kind, preset in MB.PRESETS.items():
    h = preset['headline'].casefold()
    p = preset['pill'].casefold()
    root = _re.sub(r'[^а-яa-z]', '', h)[:6]
    pill_letters = _re.sub(r'[^а-яa-z]', '', p)
    check(not (root and root in pill_letters),
          f'{kind}: pill без корня «{root}» ({preset["pill"]!r})')
    check('hakumo' not in p or kind == 'modpanel',
          f'{kind}: pill без Hakumo ({preset["pill"]!r})')
    if kind == 'modpanel':
        check('hakumo' in p and 'панель' not in p,
              f'modpanel pill · Hakumo без «панель»: {preset["pill"]!r}')
    check('панель модерации' not in p, f'{kind}: нет «панель модерации»')
check(MB.PRESETS['modpanel']['pill'] == 'контроль и порядок · Hakumo',
      'modpanel pill = контроль и порядок · Hakumo')

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
    c = getattr(child, 'content', None)
    if c:
        texts.append(c)
    for k in list(getattr(child, 'children', []) or []):
        c = getattr(k, 'content', None)
        if c:
            texts.append(c)
joined = '\n'.join(texts)
check('Участник' in joined and 'Действие' in joined, 'подписи блоков')
check('Выберите участника и действие ниже.' in joined,
      f'инструкция под баннером: {joined!r}')
check('Участник:' not in joined and 'можно выбрать' not in joined
      and 'селекты ниже' not in joined and 'лимитах' not in joined
      and 'Порядок любой' not in joined
      and 'порядок любой' not in joined.lower(),
      f'без лишнего статуса: {joined!r}')
check('**Участник**' in joined and '**Действие**' in joined
      and joined.count('-#') == 0,
      f'подписи блоков без футера: {joined!r}')
check(joined.count('# Панель модерации') == 0 and 'HAKUMO' not in joined,
      f'без дубля заголовка: {joined!r}')
check('-# модерация' not in joined, 'без футера модерация')
# MediaGallery full-bleed — верхний уровень LayoutView (не внутри Container)
check(any(type(child).__name__ == 'MediaGallery' for child in view.children)
      or any(type(k).__name__ == 'MediaGallery'
             for child in view.children
             for k in list(getattr(child, 'children', []) or [])),
      'есть MediaGallery full-bleed')
# после выбора участника — краткий статус с mention, без «Участник:»
view.selected_uid = '424242424242424242'
view._rebuild(None)
st_texts = []
for child in view.children:
    c = getattr(child, 'content', None)
    if c:
        st_texts.append(c)
    for k in list(getattr(child, 'children', []) or []):
        c = getattr(k, 'content', None)
        if c:
            st_texts.append(c)
st_joined = '\n'.join(st_texts)
check('Участник:' not in st_joined and '<@424242424242424242>' in st_joined,
      f'после выбора краткий статус: {st_joined!r}')
check('v11' in (view._banner_name or ''),
      f'banner filename v11 cache-bust: {view._banner_name!r}')
# footer helper без дубля (для embed-фолбека)
g = type('G', (), {'name': 'HAKUMO'})()
check(view._footer_text(g) == 'модерация', f"footer hakumo={view._footer_text(g)!r}")
g2 = type('G', (), {'name': 'My Server'})()
check(view._footer_text(g2) == 'My Server · модерация',
      f"footer other={view._footer_text(g2)!r}")
check(view._banner_file is not None, 'banner file attached')
# gallery + status + участник + действие
check(len(view.children) == 4, f'блоки: gallery+status+2 selects: {len(view.children)}')

print('== empty select placeholders (нет дубля с заголовком блока) ==')
check(getattr(view.target_select, 'placeholder', None) in ('', None),
      f'target placeholder empty: {getattr(view.target_select, "placeholder", None)!r}')
check(getattr(view.action_select, 'placeholder', None) in ('', None),
      f'action placeholder empty: {getattr(view.action_select, "placeholder", None)!r}')
from cogs.appeals import AppealMenuSelect  # noqa: E402
from cogs.staff_apply import RoleSelect  # noqa: E402
check(getattr(AppealMenuSelect(), 'placeholder', None) in ('', None),
      'appeals select empty')
check(getattr(RoleSelect(), 'placeholder', None) in ('', None),
      'staff select empty')
check('-# подать апелляцию' not in joined and '-# кого' not in joined.lower(),
      'без subtitle-дублей в modpanel текстах')

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
# appeals fallback: без subtitle-дубля
av_texts = []
for child in av.children:
    for k in list(getattr(child, 'children', []) or []):
        c = getattr(k, 'content', None)
        if c:
            av_texts.append(c)
av_joined = '\n'.join(av_texts)
check('-# подать апелляцию' not in av_joined,
      f'appeals без subtitle: {av_joined!r}')
check(MB.H == 420, f'баннер полный размер H={MB.H}')

art = '/opt/cursor/artifacts'
os.makedirs(art, exist_ok=True)
for kind in ('modpanel', 'appeals', 'staff', 'events'):
    MB.render_menu_banner(kind).save(os.path.join(art, f'banner-{kind}.png'))
check(True, 'preview banners')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
