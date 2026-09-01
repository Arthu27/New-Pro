# -*- coding: utf-8 -*-
"""ИИ-настройщик + идеальные нажатия.

ИИ-часть (и панельный AI, и AI в самом Discord-боте идут через
web.ai_helper, поэтому покрываются одним тестом):
- build_setup_faq выдаёт пошаговые гайды по темам (варны, щит, каналы,
  тикеты, антирейд, автороль, экономика и т.д.) с реальными путями панели;
- без распознанной темы — обзор всех направлений настройки;
- компактный путеводитель автоматически попадает в системный промпт LLM
  (build_panel_knowledge);
- офлайн-фолбэк ловит «как настроить X» любой формы (инфинитив «настроить»
  через стем «настро», но не «настроение») и отвечает гайдом, а не общими
  блоками;
- регрессия прощания: «покажи правила» больше не уходит в «До встречи».

Нажатия («пиксели»):
- глобальный CSS: touch-action: manipulation без 300мс-задержки тапа,
  прозрачная tap-подсветка, на тачах кнопки ≥40–44px, шрифт полей 16px;
- базовые размеры иконочных кнопок увеличены (.btn-icon, .pm-ico-btn,
  .mobile-menu, .cmd-modal-close, .ms-del, .rule-del);
- app.js: живые перерисовки не «съедают» нажатия (holdLiveRefresh).

Запуск: python3 tests/test_ai_setup.py
"""
import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_ai_setup_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['DEMO_MODE'] = '1'
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'preview123'
os.environ['MAIN_GUILD_ID'] = '987654321098765432'

PASS = 0
FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


# ═══ 1. Пошаговые гайды настройки ════════════════════════════════════════
print('== build_setup_faq: темы и пути ==')
from web.ai_knowledge import (build_panel_knowledge, build_setup_digest,  # noqa: E402
                              build_setup_faq)

faq_warn = build_setup_faq('как настроить варны')
check('/ladder' in faq_warn and '/mod-settings' in faq_warn,
      'варны: гайд ведёт на /ladder (лестница) и /mod-settings (исключения)')
check('лестница' in faq_warn.lower() and 'по шагам' in faq_warn.lower(),
      'варны: гайд пошаговый и про лестницу наказаний')

faq_guard = build_setup_faq('как настроить щит сервера')
check('/guardian' in faq_guard and '/channel-settings' in faq_guard,
      'щит: гайд ведёт на /guardian и маршрут тревог /channel-settings')
check('бот' in faq_guard.lower() and ' белый список' in faq_guard.lower(),
      'щит: упомянута защита от ботов и белый список')

faq_routes = build_setup_faq('куда падать алертам, как настроить каналы')
check('/channel-settings' in faq_routes and '14' in faq_routes,
      'каналы: гайд про хаб 14 маршрутов')

faq_tickets = build_setup_faq('как настроить тикеты?')
check('/ai-tickets' in faq_tickets,
      'тикеты: гайд ведёт на живые AI-тикеты /ai-tickets')

faq_raid = build_setup_faq('как включить антирейд')
check('/antiraid' in faq_raid and '/antifake' in faq_raid,
      'антирейд: гайд ведёт на /antiraid и /antifake')

# Автороль/экономика/уровни — выключенные и удалённые модули:
# гайдов по ним больше нет (проверка фантомных путей ниже это стережёт).
faq_autorole = build_setup_faq('как сделать роль при входе новичкам')
check('/autorole' not in faq_autorole, 'автороль: удалённый гайд не воскрес')
faq_eco = build_setup_faq('как настроить экономику и магазин')
check('/economy' not in faq_eco and '/shop' not in faq_eco,
      'экономика: удалённые гайды не воскресли')

overview = build_setup_faq('помоги настроить сервер')
check('главные' in overview.lower() and overview.count('▸') >= 10,
      'без темы: обзор направлений настройки (≥10 пунктов)')

# только реальные пути панели в гайдах
sys.path.insert(0, ROOT)
from services.panel_menu import MENU  # noqa: E402
menu_paths = {p['path'] for g in MENU for p in g.get('pages', [])}
used_paths = set(re.findall(r'\(/([a-z0-9_\-]+)\)', ' '.join(
    ' '.join(steps) for _k, _t, steps in
    __import__('web.ai_knowledge', fromlist=['_SETUP_TOPICS'])._SETUP_TOPICS)))
phantom = {p for p in used_paths if '/' + p not in menu_paths}
check(not phantom, f'в гайдах нет несуществующих страниц (фантомы: {sorted(phantom)})')

# ═══ 2. Путеводитель в системном промпте LLM ═════════════════════════════
print('== системный промпт LLM ==')
digest = build_setup_digest()
check('ЕСЛИ СПРАШИВАЮТ' in digest and '/guardian' in digest and
      '/channel-settings' in digest,
      'дайджест: правило «отвечай по шагам» + ключевые страницы')
kb = build_panel_knowledge(compact=True)
check('ЕСЛИ СПРАШИВАЮТ' in kb,
      'дайджест автоматически подключён к build_panel_knowledge')
kb2 = build_panel_knowledge(compact=True, full_menu=False)
check('ЕСЛИ СПРАШИВАЮТ' in kb2,
      'дайджест есть и в сверхкомпактной версии')

# ═══ 3. Офлайн-фолбэк: «как настроить» → гайд, а не общий блок ══════════
print('== офлайн-фолбэк _local_moebius_fallback ==')
from web.ai_helper import _local_moebius_fallback  # noqa: E402


def fallback(q):
    return _local_moebius_fallback([{'role': 'user', 'content': q}])[0]


check('/ai-tickets' in fallback('как настроить тикеты?'),
      '«как настроить тикеты» → гайд, а не общий блок тикетов')
check('/mod-settings' in fallback('помоги настроить варны'),
      '«помоги настроить варны» → гайд по лестнице')
check('/guardian' in fallback('как настроить щит сервера'),
      '«как настроить щит сервера» → гайд щита')
check('▸' in fallback('настройка каналов что да как'),
      '«настройка каналов что да как» → гайд по маршрутам')
check('/antiraid' in fallback('как включить антирейд'),
      '«как включить антирейд» → гайд антирейда')
check('▸' in fallback('как настроить'),
      '«как настроить» без темы → обзор направлений')

# отсев ложных срабатываний
check('настройке' not in fallback('сегодня настроение отличное').lower()
      or 'настроен' in fallback('сегодня настроение отличное').lower(),
      '«настроение» не улетает в гайды настройки')
check('У меня всё отлично' in fallback('как дела'),
      '«как дела» — прежний добрый ответ')
check('Панель Hakumo' in fallback('что такое куратор в панели'),
      '«что такое куратор в панели» — FAQ панели (старый блок)')

# ═══ 4. Регрессия прощания: «покажи правила» не «до встречи» ════════════
print('== регрессия: покажи/пока ==')
check('Свод правил' in fallback('покажи правила'),
      '«покажи правила» → правила, а не прощание')
check('До встречи' in fallback('пока'),
      '«пока» — по-прежнему прощание')
check('До встречи' in fallback('пока-пока'),
      '«пока-пока» — прощание')

# ═══ 5. CSS: глобальный комфорт нажатий ══════════════════════════════════
print('== css/ux нажатий ==')
css = open(os.path.join(ROOT, 'web', 'static', 'style.css'), encoding='utf-8').read()
check('html { touch-action: manipulation; }' in css,
      'html: touch-action manipulation (нет 300мс паузы тапа)')
check('body { -webkit-tap-highlight-color: transparent; }' in css,
      'body: прозрачная tap-подсветка (нет «серых пикселей»)')
check('@media (hover: none) and (pointer: coarse)' in css,
      'есть media-блок под тач-устройства')
coarse = css[css.index('@media (hover: none) and (pointer: coarse)'):]
check('.btn { min-height: 42px' in coarse, 'тач: .btn не ниже 42px')
check('.btn-icon { width: 44px; height: 44px; }' in coarse,
      'тач: иконочные кнопки 44px')
check('.pm-ico-btn { width: 42px !important' in coarse,
      'тач: кнопки меню панели 42px (важно поверх inline-стилей)')
check('input, select, textarea { font-size: 16px !important; }' in coarse,
      'тач: шрифт полей 16px против авто-зума iOS')
check('.btn-icon {\n  width: 34px; height: 34px;' in css,
      'база: .btn-icon увеличен 30→34px')
check('.mobile-menu {\n  display: none;\n  width: 38px; height: 38px;' in css,
      'база: .mobile-menu увеличен 34→38px')
check('.cmd-modal-close {\n  position: absolute; top: 14px; right: 14px;\n  width: 34px; height: 34px;' in css,
      'база: крестик модалки 30→34px')

pm = open(os.path.join(ROOT, 'web', 'templates', 'panel_menu.html'),
          encoding='utf-8').read()
check('.pm-ico-btn { width:36px; height:36px;' in pm and 'font-size:12px;' in pm,
      'база: кнопки меню панели 30→36px и крупнее иконка')

ms = open(os.path.join(ROOT, 'web', 'templates', 'mod_settings.html'),
          encoding='utf-8').read()
check('.ms-del{' in ms and 'min-width:34px' in ms and 'min-height:34px' in ms,
      'база: кнопка удаления ступени ≥34px')

re_t = open(os.path.join(ROOT, 'web', 'templates', 'rules_editor.html'),
            encoding='utf-8').read()
check('.rule-del {\n  width: 34px; height: 34px;' in re_t,
      'база: кнопка удаления правила 30→34px')

# ═══ 6. app.js: перерисовки не съедают клики ═════════════════════════════
print('== app.js: holdLiveRefresh ==')
js = open(os.path.join(ROOT, 'web', 'static', 'app.js'), encoding='utf-8').read()
check('var liveHoldUntil = 0;' in js and 'function holdLiveRefresh(ms)' in js,
      'трекер «удержания» живых перерисовок объявлен')
check("addEventListener('pointerdown'" in js and
      "addEventListener('pointerup'" in js,
      'pointerdown/up ставят паузу перерисовкам')
check('if (now < liveHoldUntil) return;' in js,
      'тик live-обновлений пропускается, пока идёт нажатие')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
