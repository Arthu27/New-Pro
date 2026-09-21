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

print('== banner process cache ==')
import time as _time
MB._BYTES_CACHE.clear()
t0 = _time.perf_counter()
raw1 = MB.menu_banner_bytes('modpanel')
cold_ms = (_time.perf_counter() - t0) * 1000
t0 = _time.perf_counter()
raw2 = MB.menu_banner_bytes('modpanel')
hot_ms = (_time.perf_counter() - t0) * 1000
check(raw1 == raw2 and len(raw1) > 1000, f'кэш байтов одинаковый ({len(raw1)})')
check(hot_ms < 50, f'горячий баннер <50ms (было {hot_ms:.1f}ms, cold {cold_ms:.0f}ms)')
check('modpanel' in MB._BYTES_CACHE, 'kind в _BYTES_CACHE')
MB.warm_menu_banners(('appeals',))
check('appeals' in MB._BYTES_CACHE, 'warm_menu_banners заполняет кэш')

print('== emoji_for_action fallbacks ==')
from services.menu_emojis import emoji_for_action, schedule_ensure_menu_emojis  # noqa: E402
check(callable(schedule_ensure_menu_emojis), 'schedule_ensure_menu_emojis есть')
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
check('**Участник**' in joined and '**Действие**' in joined,
      'заголовки блоков Участник / Действие')
check('кого наказать' not in joined and 'что сделать' not in joined,
      f'без дублей подсказок в TextDisplay: {joined!r}')
check('Выберите участника и действие ниже.' in joined,
      f'инструкция под баннером: {joined!r}')
check('SPEED OK' in joined or 'build ' in joined,
      f'метка SPEED/build в шапке (проверка деплоя): {joined!r}')
check('Порядок любой' not in joined and 'порядок любой' not in joined.lower()
      and 'в любом порядке' not in joined.lower(),
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
check('v15' in (view._banner_name or ''),
      f'banner filename v15: {view._banner_name!r}')
g = type('G', (), {'name': 'HAKUMO'})()
check(view._footer_text(g) == '',
      f"footer выключен: {view._footer_text(g)!r}")
g2 = type('G', (), {'name': 'My Server'})()
check(view._footer_text(g2) == '',
      f"footer other выключен: {view._footer_text(g2)!r}")
check(view._banner_file is not None, 'banner file attached')

print('== select refresh: ACK first, no banner re-upload ==')
import asyncio as _aio


class _Att:
    filename = 'hakumo_modpanel_banner_v15.png'


class _RMsg:
    def __init__(self):
        self.attachments = [_Att()]
        self.edits = []

    async def edit(self, **kw):
        self.edits.append(kw)


class _RResp:
    def __init__(self):
        self.done = False
        self.defers = []

    def is_done(self):
        return self.done

    async def defer(self, **kw):
        self.defers.append(kw)
        self.done = True

    async def edit_message(self, **kw):
        self.done = True
        raise AssertionError('edit_message не должен вызываться после defer')


class _RInter:
    def __init__(self):
        self.guild = None
        self.response = _RResp()
        self.message = _RMsg()
        self.edits = []

    async def edit_original_response(self, **kw):
        self.edits.append(kw)


view2 = ModPanelView(cog=None, member=None, allowed=list(MODPANEL_ACTIONS)[:3])
view2.selected_uid = '111'
ri = _RInter()
_aio.run(view2.refresh(ri))
check(bool(ri.response.defers), 'refresh сначала defer (ACK <3с)')
check(bool(ri.edits), 'после ACK — edit_original_response')
atts = (ri.edits[-1].get('attachments') if ri.edits else None) or []
check(atts and all(getattr(a, 'filename', None) for a in atts),
      'attachments = keep старого баннера (не discord.File)')
check(not any(type(a).__name__ == 'File' for a in atts),
      'нет повторного File-upload баннера')
check('участник <@111>' in _collect_texts(view2),
      'статус обновился после выбора')

# ModTargetSelect больше не зовёт refresh — только defer
src_mod = open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read()
mts = src_mod[src_mod.index('class ModTargetSelect'):
              src_mod.index('class ModPanelView')]
check('await view.refresh' not in mts,
      'ModTargetSelect: без refresh (только ACK) — фикс таймаута участника')

print('== select placeholders ==')
check((getattr(view.target_select, 'placeholder', None) or '') == '',
      f'target placeholder пустой: {getattr(view.target_select, "placeholder", None)!r}')
check((getattr(view.action_select, 'placeholder', None) or '') == '',
      f'action placeholder пустой: {getattr(view.action_select, "placeholder", None)!r}')

# V2, не синий эмбед
check(view.has_components_v2(), 'LayoutView V2')
src = open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read()
check("await _respond(interaction, view=view" in src
      or "await _respond(interaction, view=view," in src,
      'команда шлёт V2 view, не синий embed')
check('0x5865F2' not in src or 'panel_embed' in src,
      'нет синего blurple как основного цвета панели')
check('Участник и действие — в любом порядке.' not in src,
      'нет старого текста «в любом порядке»')

print('== appeals helpers ==')
from cogs.appeals import AppealMenuSelect, AppealMenuView  # noqa: E402
from services.v2_layouts import build_appeals_menu_items, V2_AVAILABLE  # noqa: E402
asel = AppealMenuSelect()
check(bool(asel.options), f'appeals select options: {len(asel.options)}')
av = AppealMenuView()
check(len(av.children) >= 1, f'appeals блоки: {len(av.children)}')
if V2_AVAILABLE:
    items = build_appeals_menu_items(
        banner_filename='x.png', body='тест', footer='', menu_select=asel)
    check(bool(items), 'build_appeals_menu_items доступен')
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
