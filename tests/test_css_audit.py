# -*- coding: utf-8 -*-
"""Аудит CSS-здоровья панели.

Проверки (статические):
1. Баланс скобок и комментариев в style.css.
2. Баланс скобок в каждом <style>-блоке шаблонов.
3. CSS-переменные: каждая var(--x) в style.css определена или задаётся из JS
   (setProperty) — класс багов «--ease не определён → анимация мертва».
4. То же для всех шаблонов: переменные из собственных <style>, style.css
   или JS-подстановки.
5. Дубликаты @keyframes внутри одного шаблона (тихие конфликты анимаций).
6. Все /static/-ассеты, на которые ссылаются шаблоны, существуют на диске;
   все шрифты fonts.css и webfonts Font Awesome — на месте.
7. Разумный порог !important (предохранитель от взрывного роста перебивок).
8. Цвета палитры не изменены: индиго/фиолет/циан на своих местах в :root
   (светлая и тёмная темы).
9. Гостевая зона остаётся чёрной: welcome/login/register/status/apply
   объявляют #05060a.

Запуск: python3 tests/test_css_audit.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


CSS = open(os.path.join(ROOT, 'web', 'static', 'style.css'), encoding='utf-8').read()
APPJS = open(os.path.join(ROOT, 'web', 'static', 'app.js'), encoding='utf-8').read()

TPL = {}
for _f in sorted(os.listdir(os.path.join(ROOT, 'web', 'templates'))):
    if _f.endswith('.html'):
        TPL[_f] = open(os.path.join(ROOT, 'web', 'templates', _f), encoding='utf-8').read()

# имена переменных, которые задаёт JS через style.setProperty
JS_SET_VARS = set(re.findall(r"setProperty\(\s*['\"]--([a-z0-9-]+)['\"]", APPJS))
for _src in TPL.values():
    JS_SET_VARS |= set(re.findall(r"setProperty\(\s*['\"]--([a-z0-9-]+)['\"]", _src))

print('== 1. style.css: скобки и комментарии ==')
check(CSS.count('{') == CSS.count('}'),
      f'скобки сбалансированы ({CSS.count("{")} пар)')
check(CSS.count('/*') == CSS.count('*/'),
      f'комментарии сбалансированы ({CSS.count("/*")} пар)')

print('== 2. <style>-блоки шаблонов сбалансированы ==')
_bad = []
for f, src in TPL.items():
    for i, block in enumerate(re.findall(r'<style[^>]*>(.*?)</style>', src, re.S)):
        if block.count('{') != block.count('}'):
            _bad.append(f'{f}#{i}')
check(not _bad, f'все style-блоки сбалансированы ({_bad[:4]})')

print('== 3. Переменные style.css: определены или задаются из JS ==')
_used = set(re.findall(r'var\(--([a-z0-9-]+)', CSS))
_defined = set(re.findall(r'--([a-z0-9-]+)\s*:', CSS))
_missing = sorted(_used - _defined - JS_SET_VARS)
check(not _missing, f'все {len(_used)} использованных переменных определены ({_missing[:5]})')

print('== 4. Переменные шаблонов: определены или из JS ==')
_css_vars = set(re.findall(r'--([a-z0-9-]+)\s*:', CSS))
# auth-страницы (login/register) грузят auth.css — его переменные тоже живые
_auth_css_path = os.path.join(ROOT, 'web', 'static', 'auth.css')
if os.path.exists(_auth_css_path):
    _css_vars |= set(re.findall(r'--([a-z0-9-]+)\s*:',
                                open(_auth_css_path, encoding='utf-8').read()))
_bad = []
for f, src in TPL.items():
    own = set(re.findall(r'--([a-z0-9-]+)\s*:', src))
    used = set(re.findall(r'var\(--([a-z0-9-]+)', src))
    missing = used - own - _css_vars - JS_SET_VARS
    if missing:
        _bad.append(f'{f}: {sorted(missing)}')
check(not _bad, f'во всех {len(TPL)} шаблонах переменные определены ({_bad[:4]})')

print('== 5. Дубликаты @keyframes в шаблоне ==')
_bad = []
for f, src in TPL.items():
    kfs = re.findall(r'@keyframes\s+([\w-]+)', src)
    dups = sorted({k for k in kfs if kfs.count(k) > 1})
    if dups:
        _bad.append(f'{f}: {dups}')
check(not _bad, f'дублей keyframes нет ({_bad[:4]})')

print('== 6. Ассеты существуют на диске ==')
_bad = []
for f, src in TPL.items():
    for m in re.finditer(r'(?:src|href)\s*=\s*["\'](/static/[^"\'?]+)', src):
        p = m.group(1)
        disk = os.path.join(ROOT, 'web', p.lstrip('/'))
        if not os.path.exists(disk):
            _bad.append(f'{f}: {p}')
check(not _bad, f'все /static/-ассеты на месте ({_bad[:4]})')

_fonts = open(os.path.join(ROOT, 'web', 'static', 'vendor', 'fonts', 'fonts.css'), encoding='utf-8').read()
_bad = [u for u in re.findall(r"url\('(/static/[^']+)'\)", _fonts)
        if not os.path.exists(os.path.join(ROOT, 'web', u.lstrip('/')))]
check(not _bad, f'все шрифты fonts.css на месте ({_bad[:4]})')

_fa = open(os.path.join(ROOT, 'web', 'static', 'vendor', 'fontawesome', 'css', 'all.min.css'),
           encoding='utf-8').read()
_bad = [u for u in re.findall(r'url\((\.\./webfonts/[^)]+)\)', _fa)
        if not os.path.exists(os.path.join(ROOT, 'web', 'static', 'vendor', 'fontawesome', u[3:]))]
check(not _bad, f'webfonts Font Awesome на месте (woff2 + ttf-фолбэки) ({_bad[:4]})')

print('== 7. Порог !important ==')
check(CSS.count('!important') <= 80,
      f'style.css: !important x{CSS.count("!important")} (порог 80)')
_bad = [(f, src.count('!important')) for f, src in TPL.items() if src.count('!important') > 60]
check(not _bad, f'шаблоны в пределах порога !important ({_bad[:3]})')

print('== 8. Палитра не изменена ==')
check('--ac: #4f46e5' in CSS and '--ok: #16a34a' in CSS and '--err: #dc2626' in CSS,
      'светлая тема: индиго/зелёный/красный на месте')
check('--ac: #818cf8' in CSS,
      'тёмная тема: индиго на месте')
check('#7c3aed' in CSS and '#22d3ee' in CSS,
      'фиолет и циан палитры на месте')

print('== 9. Гостевая зона чёрная ==')
_bad = []
for f in ('welcome.html', 'login.html', 'register.html', 'status_public.html', 'public_apply.html'):
    src = TPL.get(f, '')
    if '#05060a' not in src:
        _bad.append(f)
check(not _bad, f'все гостевые страницы на чёрном #05060a ({_bad})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
