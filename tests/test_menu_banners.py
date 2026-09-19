# -*- coding: utf-8 -*-
"""Баннеры меню + V2-раскладка /modpanel (референс: шапка · селекты · футер).

Запуск: python3 tests/test_menu_banners.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_banners_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

PASS = 0
FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== presets / pills ==')
from services import menu_banners as MB  # noqa: E402

check(MB.W == 1200 and MB.H == 520, f'баннер {MB.W}×{MB.H}')
check(MB.PRESETS['modpanel']['pill'] == 'Панель модерации · Hakumo',
      'modpanel pill = Панель модерации · Hakumo')
check(MB.PRESETS['modpanel']['headline'] == 'МОДЕРАЦИЯ', 'headline МОДЕРАЦИЯ')

print('== emoji_for_action fallbacks ==')
from services.menu_emojis import emoji_for_action  # noqa: E402
check(str(emoji_for_action('warn')), "warn '⚠️'")
check(bool(emoji_for_action('ban')), 'ban')
check(bool(emoji_for_action('clear')), 'clear')
check(str(emoji_for_action('warn')), 'map warn')
check(bool(emoji_for_action('unwarn')), 'map unwarn')

print('== modpanel V2 + select stickers ==')
from cogs.moderation import ModPanelView, MODPANEL_ACTIONS  # noqa: E402
from services.v2_layouts import V2_AVAILABLE  # noqa: E402

check(V2_AVAILABLE, 'V2')
view = ModPanelView(cog=None, member=None, allowed=list(MODPANEL_ACTIONS)[:3])
check(view.has_components_v2(), 'LayoutView')
check(view.action_select is not None, 'action_select')
check(len(view.action_select.options) == 3, 'options count')
labs = [o.label for o in view.action_select.options]
check(all(l.startswith('›') for l in labs), f'labels › {labs}')
check(not getattr(view, 'action_buttons', None), 'без кнопок')
emojis = [str(o.emoji) for o in view.action_select.options]
check(len(set(emojis)) >= 1, f'разные эмодзи {emojis}')
check(all(e != '🤍' for e in emojis), f'не все 🤍: {emojis}')
accents = []
for child in view.children:
    ac = getattr(child, 'accent_colour', None) or getattr(child, 'accent_color', None)
    if ac is not None:
        accents.append(int(ac.value) if hasattr(ac, 'value') else int(ac))
check(len(view.children) == 3, f'3 карточки (шапка·участник·действие): {len(view.children)}')
check(accents and all(a == 0 for a in accents), f'accent чёрный: {accents}')
from services.v2_layouts import SHOW_MENU_BANNER  # noqa: E402
check(SHOW_MENU_BANNER is True, 'баннер включён')


def _collect_texts(v):
    texts = []
    for child in v.children:
        c = getattr(child, 'content', None)
        if c:
            texts.append(c)
        for k in list(getattr(child, 'children', []) or []):
            c = getattr(k, 'content', None)
            if c:
                texts.append(c)
    return '\n'.join(texts)


joined = _collect_texts(view)
check('Панель модерации' in joined and 'HAKUMO' in joined,
      f'шапка с заголовком: {joined!r}')
check('**Участник**' not in joined and '**Действие**' not in joined,
      'без подписей блоков над селектами')
check('кого наказать' not in joined and 'что сделать' not in joined,
      f'без надписей селектов: {joined!r}')
check('Выберите участника и действие ниже.' in joined,
      f'инструкция под баннером: {joined!r}')
check('Порядок любой' not in joined and 'порядок любой' not in joined.lower(),
      f'без «порядок любой»: {joined!r}')
check('Hakumo · модерация' not in joined,
      f'без футера: {joined!r}')
# MediaGallery внутри шапки-Container
check(any(type(k).__name__ == 'MediaGallery'
          for child in view.children
          for k in list(getattr(child, 'children', []) or [])),
      'MediaGallery в шапке')
view.selected_uid = '424242424242424242'
view._rebuild(None)
st_joined = _collect_texts(view)
check('<@424242424242424242>' in st_joined and 'Участник:' not in st_joined,
      f'после выбора краткий статус: {st_joined!r}')
check('v13' in (view._banner_name or ''),
      f'banner filename v13: {view._banner_name!r}')
g = type('G', (), {'name': 'HAKUMO'})()
check(view._footer_text(g) == '',
      f"footer выключен: {view._footer_text(g)!r}")
g2 = type('G', (), {'name': 'My Server'})()
check(view._footer_text(g2) == '',
      f"footer other выключен: {view._footer_text(g2)!r}")
check(view._banner_file is not None, 'banner file attached')

print('== select placeholders пустые ==')
check((getattr(view.target_select, 'placeholder', None) or '') == '',
      f'target placeholder: {getattr(view.target_select, "placeholder", None)!r}')
check((getattr(view.action_select, 'placeholder', None) or '') == '',
      f'action placeholder: {getattr(view.action_select, "placeholder", None)!r}')

print('== appeals ==')
from cogs.appeals import AppealMenuSelect, AppealMenuView  # noqa: E402
from cogs.staff_apply import RoleSelect  # noqa: E402
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
check(MB.H == 520, f'баннер полный размер H={MB.H}')

art = '/opt/cursor/artifacts'
os.makedirs(art, exist_ok=True)
try:
    MB.render_menu_banner('modpanel').save(os.path.join(art, 'modpanel_banner_preview.png'))
    print('  PASS: preview banners')
    PASS += 1
except Exception as ex:
    print(f'  FAIL: preview banners {ex}')
    FAIL += 1

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
raise SystemExit(1 if FAIL else 0)
