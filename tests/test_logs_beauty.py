# -*- coding: utf-8 -*-
"""Живучесть кнопок панели + красивые русские логи + /proof убран + @тег в демках.

Проверяем:
- кнопки панели: главная экспортирует inline-обработчики смен («мёртвые»
  кнопки из-за ReferenceError); сплэш гасится страховкой из base.html, а в
  app.js быстрее (650 мс); непойманная JS-ошибка показывает понятный тост;
  версии статики (?v=) — автоматические по mtime файла (свежий код у всех);
- /proof убран из бота (демки теперь через панель), тексты-указатели ведут
  в панель, справка без /proof;
- @тег в демках: /api/proofs/member-search (mod+) находит по нику/имени/ID,
  форма загрузки имеет выпадающий список участников;
- логи Discord: каналы называются красиво и по-русски (🛡・модерация …),
  категория «📚 Логи», войс-логи чинены (была бага с турецким 'ses' — падали
  в «сервер»), старые уродливые имена ('-модерация','-ses') лежат в legacy
  и находятся нормализованным поиском; у категорий вернулись иконки.

Запуск: python3 tests/test_logs_beauty.py
"""
import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_logs_beauty_')
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


# ═══ 1. Кнопки панели: никаких «мёртвых» зон ═════════════════════════════
print('== кнопки: главная/сплэш/ошибки/версии ==')
dash = open(os.path.join(ROOT, 'web', 'templates', 'dashboard.html'),
            encoding='utf-8').read()
check('window.shiftAdd = shiftAdd;' in dash
      and 'window.shiftRemove = shiftRemove;' in dash
      and 'window.shiftTzSave = shiftTzSave;' in dash,
      'главная: inline-обработчики смен экспортированы (кнопки живы)')

base = open(os.path.join(ROOT, 'web', 'templates', 'base.html'),
            encoding='utf-8').read()
check("getElementById('bootSplash')" in base and '2800' in base,
      'base.html: страховка сплэша (гаснет сам за 2,8 с, не душит клики)')
appjs = open(os.path.join(ROOT, 'web', 'static', 'app.js'),
             encoding='utf-8').read()
check("window.addEventListener('error'" in appjs
      and 'обновите страницу' in appjs,
      'app.js: JS-сбой показывает понятный тост вместо «мёртвой кнопки»')
check('}, 650);' in appjs, 'app.js: сплэш гасится быстрее (650 мс)')

# авто-версии статики
app_py = open(os.path.join(ROOT, 'web', 'app.py'), encoding='utf-8').read()
check('def inject_static_versions' in app_py and 'getmtime' in app_py,
      'web/app.py: контекст-процессор авто-версий по mtime')
tmpl_versions = []
for t in ('base.html', 'login.html'):
    b = open(os.path.join(ROOT, 'web', 'templates', t), encoding='utf-8').read()
    tmpl_versions += re.findall(r'/static/[\w.-]+\.(?:js|css)\?v={{ static_v\(', b)
check(len(tmpl_versions) >= 4 and '?v=61' not in base and '?v=117' not in base,
      'шаблоны: ?v= — автоматические (ручных номеров не осталось)')

# ═══ 2. /proof убран, демки — через панель ═══════════════════════════════
print('== /proof убран ==')
cog_src = open(os.path.join(ROOT, 'cogs', 'proof_cog.py'), encoding='utf-8').read()
check("name='proof'" in cog_src, '/proof вернулся: демки грузятся прямо ботом')
check("name='proofs'" in cog_src and "name='proofdel'" in cog_src,
      '/proofs и /proofdel на месте (просмотр и удаление)')
check('«Модерация» → «Доказательства»' in cog_src,
      'тексты-указатели ведут в панель доказательств')
help_src = open(os.path.join(ROOT, 'cogs', 'help.py'), encoding='utf-8').read()
check('/proof @юзер' not in help_src, 'справка: строки /proof нет')
check('панель «Доказательства»' in help_src,
      'справка: вместо /proof — загрузка из панели')

# ═══ 3. @тег в демках: поиск участников ══════════════════════════════════
print('== @поиск участника ==')
modplus_src = open(os.path.join(ROOT, 'web', 'routes', 'modplus.py'),
                   encoding='utf-8').read()
check("/api/proofs/member-search" in modplus_src
      and "ms_search_members" in modplus_src
      and "demo_members_search" in modplus_src,
      'эндпоинт /api/proofs/member-search (mod+, живой и демо режимы)')
html = open(os.path.join(ROOT, 'web', 'templates', 'proofs.html'),
            encoding='utf-8').read()
check('id="pf-member"' in html and 'pf-member-list' in html
      and 'pf-pick' in html,
      'форма загрузки: поле @поиска с выпадающим списком')
check('type="hidden" id="pf-uid"' in html and 'type="hidden" id="pf-uname"' in html,
      'форма: выбранный участник пишется в скрытые поля')

from web.app import app as flask_app  # noqa: E402
client = flask_app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'tag-T'
    s['role'] = 'mod'
r = client.get('/api/proofs/member-search?q=ae')
d = r.get_json()
check(r.status_code == 200 and d.get('success') is True,
      f'поиск доступен модератору ({r.status_code})')
r2 = client.get('/api/proofs/member-search?q=x')
check(r2.status_code == 400, 'меньше 2 символов — понятная 400')
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'tag-U'
    s['role'] = 'uye'
r3 = client.get('/api/proofs/member-search?q=ae')
check(r3.status_code == 403, 'обычному участнику поиск закрыт (403)')

# ═══ 4. Логи Discord: красивые русские названия ══════════════════════════
print('== логи: названия каналов ==')
import cogs.logs as L  # noqa: E402

check(L.LOG_CATEGORY_NAME == '📚 Логи', 'категория — «📚 Логи»')
pretty = {'модерация': '🛡・модерация', 'участники': '👋・участники',
          'сообщения': '💬・сообщения', 'сервер': '📋・сервер',
          'доказательства': '📸・доказательства', 'голос': '🔊・голос'}
for key, want in pretty.items():
    check(L.LOG_CHANNELS.get(key) == want, f'{key}: {want}')
check(L.LOG_CHANNELS.get('ses') == '🔊・голос', 'legacy-alias ses → 🔊・голос')
check(L.log_category_display('voice') == '🔊・голос',
      'войс-логи идут в 🔊・голос (бага «ses → сервер» убита)')
check(L.log_category_display('ses') == '🔊・голос', 'display(ses) = голос')
check(all('-' not in v[:2] for v in pretty.values()),
      'ни один новый канал не начинается с уродливого «-»')
leg = L.LEGACY_CHANNEL_NAMES
check('-модерация' in leg.get('🛡・модерация', [])
      and '-ses' in leg.get('🔊・голос', [])
      and '-доказательства' in leg.get('📸・доказательства', []),
      'старые уродливые имена живут в legacy (находятся, не теряются)')
check(L.LOG_CATEGORY_LEGACY and ' Логи' in L.LOG_CATEGORY_LEGACY,
      'старая категория « Логи» известна (миграция переименует)')
check(L._LOG_META.get('proof', ('',))[0] == '📸',
      'иконка демок в мета — фотоаппарат')
cats = L.CATEGORIES
check(cats['mod']['emoji'] and cats['voice']['emoji'] and cats['proof']['emoji'],
      'иконки категорий логов вернулись (были пустые)')


# поиск legacy-канала нормализацией (старый -модерация всё ещё находится)
class _Ch:
    def __init__(self, name):
        self.name = name


class _G:
    def __init__(self):
        self.text_channels = [_Ch('-модерация'), _Ch('-ses'), _Ch('-доказательства')]


g = _G()
check(L.find_log_channel(g, 'mod').name == '-модерация',
      'старый канал -модерация находится (будет переименован при записи)')
check(L.find_log_channel(g, 'voice').name == '-ses',
      'старый канал -ses находится для войса')
i = L.find_log_channel(g, 'proof')
check(i is not None and i.name == '-доказательства',
      'старый канал -доказательства находится для демок')


# ═══ 8. «+ ступень»: пустое поле подсвечивается, а не молчит ═══════════════
print('== mod-settings: пустое поле «Варнов» подсвечивается ==')
_ms = open(os.path.join(ROOT, 'web/templates/mod_settings.html'), encoding='utf-8').read()
check('countInp.focus();' in _ms and 'var(--err-soft)' in _ms,
      'msAddStep: пустое поле фокусируется и подсвечивается')
check('Сначала впишите число варнов' in _ms, 'msAddStep: тост объясняет, что заполнить')

# ═══ 9. Сидер сбрасывает демо-витрину «всё включено» ═══════════════════════
print('== сидер: состояния модулей сбрасываются ==')
_seed = open(os.path.join(ROOT, 'scripts/seed_demo_panel.py'), encoding='utf-8').read()
check('demo_cog_states.json' in _seed and "_f.write('{}\\n')" in _seed,
      'сидер: пересев сбрасывает toggle-состояния модулей (файл очищается)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
