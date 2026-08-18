# -*- coding: utf-8 -*-
"""Регрессия индивидуального PRO-прохода центра объявлений."""
import os
import re
import shutil
import subprocess
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_announcements_pro_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['PANEL_PASSWORD'] = 'AnnouncementsProTest!2026'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DB_PATH'] = os.path.join(_TMP, 'announcements-pro.db')

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


path = os.path.join(ROOT, 'web', 'templates', 'announcements.html')
source = open(path, encoding='utf-8').read()

print('== 1. Полноценный центр объявлений ==')
for marker, label in [
    ('class="ann-command"', 'командная панель'),
    ('id="annSearch"', 'живой поиск'),
    ('class="ann-summary"', 'сводка статусов'),
    ('data-ann-filter="delivered"', 'фильтр Discord'),
    ('data-ann-filter="panel"', 'фильтр панели'),
    ('data-ann-filter="failed"', 'фильтр ошибок'),
    ('id="annResultMeta"', 'счётчик результатов'),
    ('id="annHealthRing"', 'визуальный индекс доставки'),
    ('data-ann-view="timeline"', 'переключатель карточки/хронология'),
    ('ann-featured-label', 'акцент на последней публикации'),
    ('function updateHealth', 'динамическая оценка качества доставки'),
    ('id="annInspector" role="dialog"', 'детальная карточка публикации'),
    ('id="annInspectorReuse"', 'повторное использование контента'),
    ('data-open-ann', 'явный переход к деталям'),
    ('function filteredAnnouncements', 'единая фильтрация истории'),
]:
    check(marker in source, f'реализовано: {label}')

print('== 2. Композитор и предпросмотр ==')
for marker, label in [
    ('id="annModal" role="dialog"', 'доступный редактор'),
    ('id="annForm"', 'форма публикации'),
    ('name="annDelivery" value="panel"', 'публикация только в панель'),
    ('name="annDelivery" value="discord"', 'доставка в Discord'),
    ('id="annPreviewTitle"', 'предпросмотр заголовка'),
    ('id="annPreviewMessage"', 'предпросмотр сообщения'),
    ('data-ann-preset="maintenance"', 'профессиональные заготовки'),
    ('data-ann-format="bold"', 'Markdown-панель форматирования'),
    ('id="annPreviewTarget"', 'живой предпросмотр назначения'),
    ('function formatMessage', 'редактор выделенного текста'),
    ("fetch('/api/send-announcement'", 'отправка через существующий API'),
    ("fetchJSON('/api/guilds')", 'загрузка серверов'),
    ("'/channels'", 'загрузка доступных каналов'),
]:
    check(marker in source, f'реализовано: {label}')

print('== 3. Надёжность и доступность ==')
for marker, label in [
    ('lastFingerprint', 'live-refresh без лишнего DOM-render'),
    ('loadInFlight', 'защита от параллельных загрузок'),
    ('qualitySetLoading', 'состояния отправки и retry'),
    ("event.key === 'Escape'", 'закрытие редактора с клавиатуры'),
    ("event.key !== 'Tab'", 'focus trap диалога'),
    ("event.key === 'Enter'", 'быстрая публикация Ctrl+Enter'),
    ("localStorage.setItem('ann_history_view'", 'выбранный вид истории запоминается'),
    ('aria-live="polite"', 'озвучивание результатов'),
    ('data-copy-ann', 'копирование объявления'),
    ('data-expand', 'раскрытие длинного сообщения'),
    ('announcementFromCard', 'точный выбор записи даже без legacy-id'),
    ("$('annInspector').classList.contains('open')", 'live-refresh не сбивает просмотр деталей'),
    ('@media(max-width:680px)', 'мобильная компоновка'),
    ('prefers-reduced-motion', 'уважение системной анимации'),
]:
    check(marker in source, f'реализовано: {label}')

print('== 4. Старые контракты доставки сохранены ==')
for marker in ('ann-chip', 'data-retry', '/api/announcements/retry',
               'redelivered_by', 'deliver_error', 'setInterval'):
    check(marker in source, f'контракт {marker} на месте')

print('== 5. Наглядное demo-preview ==')
demo = open(os.path.join(ROOT, 'scripts', 'demo_panel.py'), encoding='utf-8').read()
check("announcements_path = 'data/announcements.json'" in demo,
      'демо засеивает историю объявлений только при пустом файле')
check("'delivered': True" in demo and "'deliver_error': 'Missing Access" in demo,
      'в демо представлены успешная и проблемная доставки')
check("DEMO_USERNAME = 'owner'" in demo and "DEMO_PASSWORD = '123321'" in demo,
      'demo-preview использует запрошенную отдельную учётную запись')
check("@app.route('/demo-login')" in demo and "return redirect('/login')" in demo,
      'старый preview-адрес перенаправляет на обычную форму без создания сессии')
check("request.path == '/login'" in demo and "request.method == 'POST'" in demo and
      'response.status_code in (301, 302, 303, 307, 308)' in demo,
      'резервная сессия включается только после успешной проверки пароля')
check("SESSION_COOKIE_SAMESITE'] = 'None'" in demo and
      "SESSION_COOKIE_SECURE'] = True" in demo and
      "SESSION_COOKIE_PARTITIONED'] = True" in demo,
      'partitioned-сессия demo-preview сохраняется внутри HTTPS iframe Arena')
check('@app.before_request' in demo and '_demo_authorized' in demo and
      'restore_demo_session' in demo,
      'server-side fallback сохраняет вход при полной блокировке iframe-cookie')
check("_demo_requested_page.pop(key, '/announcements')" in demo,
      'после demo-входа открывается запрошенный рабочий раздел, а не Welcome-экран')
check("request.path == '/logout'" in demo and '_demo_authorized.pop' in demo,
      'выход очищает резервную demo-сессию')

print('== 6. Синтаксис и ролевой HTTP-рендер ==')
from jinja2 import Environment  # noqa: E402
try:
    Environment().parse(source)
    jinja_ok = True
except Exception as exc:
    jinja_ok = False
    print('  JINJA:', exc)
check(jinja_ok, 'шаблон проходит Jinja parse')

scripts = re.findall(r'<script>(.*?)</script>', source, re.S)
js = scripts[-1] if scripts else ''
js = re.sub(r"\{\{\s*'true'\s*if\s*can_manage\s*else\s*'false'\s*\}\}",
            'true', js)
js_path = os.path.join(_TMP, 'announcements-inline.js')
open(js_path, 'w', encoding='utf-8').write(js)
node = subprocess.run(['node', '--check', js_path], capture_output=True,
                      text=True, timeout=30)
check(bool(scripts) and node.returncode == 0,
      f'inline JS проходит node --check ({node.stderr.strip() or "OK"})')

import web.app as webapp  # noqa: E402
client = webapp.app.test_client()


def login(role):
    with client.session_transaction() as session:
        session.clear()
        session['logged_in'] = True
        session['username'] = 'AnnTester'
        session['role'] = role


login('mod')
managed = client.get('/announcements')
managed_html = managed.get_data(as_text=True)
check(managed.status_code == 200 and 'id="annCreate"' in managed_html,
      'персонал видит кнопку нового объявления')
check('id="annModal"' in managed_html and 'CAN_MANAGE = true' in managed_html,
      'персонал получает композитор')

login('uye')
member = client.get('/announcements')
member_html = member.get_data(as_text=True)
check(member.status_code == 200 and 'id="annCreate"' not in member_html,
      'участник видит чистую ленту без создания')
check('id="annModal"' not in member_html and 'CAN_MANAGE = false' in member_html,
      'композитор не попадает роли uye')
check('app.js' in member_html and 'style.css' in member_html, 'глобальный shell сохранён')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
