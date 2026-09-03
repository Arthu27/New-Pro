# -*- coding: utf-8 -*-
"""Аудит доступности и структурной валидности панели.

Проверки (статические + рендер через Flask test_client):
1. Каждый <img> в шаблонах имеет атрибут alt (даже пустой — декоративные).
2. Каждый <input> имеет доступное имя: aria-label / placeholder / title /
   aria-labelledby / <label for=...> / оборачивающий <label>.
3. Каждая <button> имеет имя: текст внутри, aria-label или title.
4. Ссылки: target="_blank" обязан иметь rel="noopener"; href="javascript:" запрещён.
5. Устаревшие теги (marquee/blink/font/center/bgsound) отсутствуют.
6. У каждой самостоятельной страницы (свой <html>) есть lang="ru" и <title>.
7. Баланс тегов отрендеренного HTML всех страниц меню + гостевых страниц
   (парсер стека с правилами HTML5 для необязательных закрывающих тегов).
8. prefers-reduced-motion: guard-правила в style.css и проверка в app.js
   не выпилены (tripwire).

Запуск: python3 tests/test_a11y_audit.py
"""
import os
import re
import sys
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ['MAIN_GUILD_ID'] = '777'

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


TPL_DIR = os.path.join(ROOT, 'web', 'templates')
_tpls = sorted(f for f in os.listdir(TPL_DIR) if f.endswith('.html'))


def _strip_scripts(s):
    return re.sub(r'<script[\s\S]*?</script>', '', s, flags=re.I)


# ─── 1. img alt ──────────────────────────────────────────────────────────────
print('== 1. У всех <img> есть alt ==')
_bad = []
for f in _tpls:
    src = _strip_scripts(open(os.path.join(TPL_DIR, f), encoding='utf-8').read())
    for t in re.findall(r'<img\b[^>]*>', src, flags=re.I | re.S):
        if not re.search(r'\balt\s*=', t, re.I):
            _bad.append(f'{f}: {t[:60]}')
check(not _bad, f'{len(_tpls)} шаблонов, img без alt: {len(_bad)} ({_bad[:3]})')

# ─── 2. input: доступное имя ─────────────────────────────────────────────────
print('== 2. У каждого <input> есть доступное имя ==')
_SKIP_TYPES = ('hidden', 'submit', 'button', 'reset', 'image')
_bad = []
for f in _tpls:
    body = _strip_scripts(open(os.path.join(TPL_DIR, f), encoding='utf-8').read())
    labels = set(re.findall(r'<label\b[^>]*for\s*=\s*["\']([^"\']+)["\']', body, re.I))
    for t in re.findall(r'<input\b[^>]*>', body, flags=re.I | re.S):
        tm = re.search(r'type\s*=\s*["\']([^"\']+)', t, re.I)
        if tm and tm.group(1).lower() in _SKIP_TYPES:
            continue
        if re.search(r'\b(aria-label|placeholder|aria-labelledby|title)\s*=', t, re.I):
            continue
        idm = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', t, re.I)
        if idm and idm.group(1) in labels:
            continue
        idx = body.find(t)
        before = body[:idx]
        opens = len(re.findall(r'<label\b', before, re.I)) - len(re.findall(r'</label>', before, re.I))
        if opens > 0:  # оборачивающий <label>
            continue
        _bad.append(f'{f}: {t[:60]}')
check(not _bad, f'{len(_tpls)} шаблонов, input без имени: {len(_bad)} ({_bad[:3]})')

# ─── 3. button: доступное имя ────────────────────────────────────────────────
print('== 3. У каждой <button> есть имя ==')
_bad = []
for f in _tpls:
    body = _strip_scripts(open(os.path.join(TPL_DIR, f), encoding='utf-8').read())
    for m in re.finditer(r'<button\b[^>]*>([\s\S]*?)</button>', body, re.I):
        tag_open, inner = m.group(0).split('>', 1)[0] + '>', m.group(1)
        if re.search(r'\b(aria-label|title)\s*=', tag_open, re.I):
            continue
        txt = re.sub(r'<[^>]+>', '', inner).strip()
        if not txt:
            _bad.append(f'{f}: {tag_open[:70]}')
check(not _bad, f'{len(_tpls)} шаблонов, кнопок без имени: {len(_bad)} ({_bad[:3]})')

# ─── 4. ссылки ───────────────────────────────────────────────────────────────
print('== 4. target=_blank → rel=noopener; javascript: запрещён ==')
_bad = []
for f in _tpls:
    body = _strip_scripts(open(os.path.join(TPL_DIR, f), encoding='utf-8').read())
    for t in re.findall(r'<a\b[^>]*>', body, flags=re.I | re.S):
        if 'target="_blank"' in t.lower() and not re.search(r'\brel\s*=\s*["\'][^"\']*noopener', t, re.I):
            _bad.append(f'{f}: {t[:70]}')
        if re.search(r'\bhref\s*=\s*["\']javascript:', t, re.I):
            _bad.append(f'{f}: javascript: {t[:70]}')
check(not _bad, f'{len(_tpls)} шаблонов, нарушений ссылок: {len(_bad)} ({_bad[:3]})')

# ─── 5. устаревшие теги ──────────────────────────────────────────────────────
print('== 5. Устаревших тегов нет ==')
_bad = []
for f in _tpls:
    body = _strip_scripts(open(os.path.join(TPL_DIR, f), encoding='utf-8').read())
    for m in re.finditer(r'<\s*(marquee|blink|bgsound|font|center)\b', body, re.I):
        _bad.append(f'{f}: <{m.group(1)}>')
check(not _bad, f'{len(_tpls)} шаблонов, устаревших тегов: {len(_bad)} ({_bad[:3]})')

# ─── 6. lang и title у самостоятельных страниц ───────────────────────────────
print('== 6. Самостоятельные страницы: lang="ru" + <title> ==')
_bad = []
for f in _tpls:
    src = open(os.path.join(TPL_DIR, f), encoding='utf-8').read()
    if '<html' not in src.lower():
        continue
    if not re.search(r'<html[^>]*\blang\s*=\s*["\']ru["\']', src, re.I):
        _bad.append(f'{f}: нет lang="ru"')
    if not re.search(r'<title\b[^>]*>[^<]+</title>', src, re.I):
        _bad.append(f'{f}: нет <title>')
check(not _bad, f'страниц с <html> без lang/title: {len(_bad)} ({_bad[:3]})')

# ─── 7. баланс тегов отрендеренных страниц ───────────────────────────────────
print('== 7. Баланс тегов на всех отрендеренных страницах ==')
import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()

with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'owner'
    s['selected_guild'] = '777'

from services.panel_menu import MENU  # noqa: E402

menu_paths = set()


def _walk(node):
    if isinstance(node, dict):
        if node.get('path'):
            menu_paths.add(node['path'])
        for v in node.values():
            _walk(v)
    elif isinstance(node, list):
        for v in node:
            _walk(v)


_walk(MENU)
paths = sorted(menu_paths) + ['/welcome', '/login', '/register', '/status', '/apply', '/mod-kiosk']

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
        'param', 'source', 'track', 'wbr'}
# тег → множество тегов, которые он неявно закрывает (правила HTML5)
CLOSES = {
    'li': {'li'}, 'dt': {'dt', 'dd'}, 'dd': {'dt', 'dd'}, 'p': {'p'},
    'option': {'option'}, 'optgroup': {'option', 'optgroup'}, 'rt': {'rt'}, 'rp': {'rp'},
    'thead': {'thead', 'tbody', 'tfoot'}, 'tbody': {'thead', 'tbody', 'tfoot'},
    'tfoot': {'thead', 'tbody', 'tfoot'}, 'tr': {'tr'}, 'td': {'td', 'th'}, 'th': {'td', 'th'},
}


class _Balancer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        tl = tag.lower()
        if tl in VOID:
            return
        if tl in CLOSES:
            while self.stack and self.stack[-1] in CLOSES[tl]:
                self.stack.pop()
        self.stack.append(tl)

    def handle_endtag(self, tag):
        tl = tag.lower()
        if tl in VOID:
            return
        if self.stack and self.stack[-1] == tl:
            self.stack.pop()
        elif tl in self.stack:
            self.errors.append(f'неправильная вложенность </{tl}>')
            while self.stack:
                top = self.stack.pop()
                if top == tl:
                    break
        else:
            self.errors.append(f'лишний </{tl}>')


_bad = []
_ok = 0
for path in paths:
    r = client.get(path)
    if r.status_code != 200:
        _bad.append(f'{path} → {r.status_code}')
        continue
    b = _Balancer()
    b.feed(r.get_data(as_text=True))
    leftover = [t for t in b.stack if t not in ('html', 'body')]
    if leftover:
        b.errors.append(f'незакрытые теги: {", ".join(leftover)}')
    if b.errors:
        _bad.append(f'{path}: {"; ".join(b.errors[:3])}')
    else:
        _ok += 1
check(not _bad, f'{_ok}/{len(paths)} страниц с чистым балансом тегов ({_bad[:3]})')

# ─── 8. prefers-reduced-motion tripwire ───────────────────────────────────────
print('== 8. prefers-reduced-motion: guard-правила живы ==')
css = open(os.path.join(ROOT, 'web', 'static', 'style.css'), encoding='utf-8').read()
guards = len(re.findall(r'@media\s*\(prefers-reduced-motion:\s*reduce\)', css))
check(guards >= 20, f'style.css: {guards} guard-блоков (порог 20)')
appjs = open(os.path.join(ROOT, 'web', 'static', 'app.js'), encoding='utf-8').read()
check('prefers-reduced-motion' in appjs or 'reducedMotion' in appjs,
      'app.js учитывает reduced-motion')


# ─── 9. Ориентир <main> на каждой самостоятельной странице ──────────────────
# Lighthouse/axe: «landmark-one-main» — без <main> читалкам экрана не за что
# зацепиться. Заказ владельца: «проверишь каждую комнату панель везде».
print('== 9. Ориентир <main> на самостоятельных страницах ==')
_bad = []
for f in _tpls:
    src = open(os.path.join(TPL_DIR, f), encoding='utf-8').read()
    if '<html' not in src.lower():
        continue
    n_open = len(re.findall(r'<main[\s>]', src, re.I))
    n_close = len(re.findall(r'</main\s*>', src, re.I))
    if n_open == 0:
        _bad.append(f'{f}: нет <main>')
    elif n_open != n_close:
        _bad.append(f'{f}: <main> {n_open} vs </main> {n_close}')
check(not _bad, f'страниц без <main>: {len(_bad)} ({_bad[:3]})')

# ─── 10. Контраст текста: WCAG AA 4.5:1 ─────────────────────────────────────
# axe «color-contrast»: футер лендинга рисовался --text3 #5f6880 по #05060a —
# 3,64:1, мелкий текст не читался. Та же переменная была в пяти шаблонах.
print('== 10. Контраст текста WCAG AA ==')

def _lum(hexcol):
    h = hexcol.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    ch = []
    for k in (0, 2, 4):
        c = int(h[k:k + 2], 16) / 255.0
        ch.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]

def _ratio(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

_bad = []
_checked = 0
for f in _tpls:
    src = open(os.path.join(TPL_DIR, f), encoding='utf-8').read()
    m_bg = re.search(r'--bg\s*:\s*(#[0-9a-fA-F]{3,6})', src)
    if not m_bg:
        continue
    bg = m_bg.group(1)
    for var in ('--text', '--text2', '--text3'):
        m = re.search(re.escape(var) + r'\s*:\s*(#[0-9a-fA-F]{3,6})', src)
        if not m:
            continue
        _checked += 1
        r = _ratio(m.group(1), bg)
        if r < 4.5:
            _bad.append('%s %s %s на %s = %.2f:1' % (f, var, m.group(1), bg, r))
check(not _bad, f'пар текст/фон проверено {_checked}, ниже 4.5:1 — {len(_bad)} ({_bad[:3]})')
check(_checked >= 10, f'проверили {_checked} пар — выборка не вырожденная')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
