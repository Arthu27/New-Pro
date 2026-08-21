# -*- coding: utf-8 -*-
"""Аудит связей панели: каждая ссылка, каждый fetch и каждый обработчик
должны куда-то вести.

Проверки (статические, без сети):
1. Литеральные fetch-URL из шаблонов → существующий роут Flask.
2. Конкатенированные префиксы API ('/api/x/' + gid) → роут с таким началом.
3. Функции в inline-обработчиках (onclick/onchange/…) объявлены —
   в самом шаблоне или в клиентском ките app.js.
4. Внутренние href → существующий роут (query-часть отбрасывается).
5. form action → существующий роут.
6. Jinja-блоки {% %} и {%- -%} сбалансированы во всех шаблонах.
7. У каждого шаблона есть charset, lang и title.
8. Дубликаты id в разметке (содержимое <script>/<style> не учитываем —
   JS-шаблоны форм создают поля динамически и в DOM не дублируются).
9. Вызовы getElementById('x') в скриптах шаблона: id существует в разметке
   этого шаблона или создаётся динамически (встречается в JS-строках
   шаблона либо в динамической разметке app.js).

Запуск: python3 tests/test_link_audit.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('PANEL_USER', 'audit')
os.environ.setdefault('PANEL_PASSWORD', 'audit')

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


import web.app as appmod  # noqa: E402

ROUTES = [r.rule for r in appmod.app.url_map.iter_rules()]


def route_patterns():
    out = []
    for rule in ROUTES:
        pat = re.escape(rule)
        # re.escape не экранирует <>, поэтому заменяем их напрямую
        pat = re.sub(r'<[a-z_]+>', '[^/]+', pat)
        out.append((rule, re.compile('^' + pat + '$')))
    return out


_PATS = route_patterns()


def route_exists(url):
    for rule, rx in _PATS:
        if rx.match(url):
            return rule
    return None


TPL = {}
for _f in sorted(os.listdir(os.path.join(ROOT, 'web', 'templates'))):
    if _f.endswith('.html'):
        TPL[_f] = open(os.path.join(ROOT, 'web', 'templates', _f), encoding='utf-8').read()

APPJS = open(os.path.join(ROOT, 'web', 'static', 'app.js'), encoding='utf-8').read()


def strip_query(url):
    return url.split('?')[0]


print('== 1. Литеральные fetch-URL → роуты ==')
_missing = []
for f, src in TPL.items():
    # URL заканчивается кавычкой, за которой идёт ) или , — конкатенации
    # вида '/api/guild/' + gid проверяются отдельно в секции 2.
    for m in re.finditer(r"fetch(?:CachedJSON)?\(\s*['\"]([^'\"]+)['\"]\s*[),]", src):
        url = m.group(1)
        if url.startswith(('http', 'data:')) or '{' in url:
            continue
        if route_exists(strip_query(url)) is None:
            _missing.append(f'{f}: {url}')
check(not _missing, f'все fetch ведут в существующие роуты ({_missing[:3]}{"…" if len(_missing) > 3 else ""})')

print('== 2. Конкатенированные API-префиксы → роуты ==')
_missing = []
for f, src in TPL.items():
    for m in re.finditer(r"['\"](/[a-z0-9_\-/.]*)['\"]\s*\+", src):
        pref = m.group(1)
        if not pref.startswith('/api'):
            continue
        if pref.endswith('/'):
            pref = pref.rstrip('/')
        if not any(r.startswith(pref) for r in ROUTES):
            _missing.append(f'{f}: {pref}+…')
check(not _missing, f'все API-префиксы имеют роуты ({_missing[:3]}{"…" if len(_missing) > 3 else ""})')

print('== 3. Inline-обработчики → объявленные функции ==')
KIT_FUNCS = set(re.findall(r'window\.([A-Za-z_$][\w$]*)\s*=', APPJS))
KIT_DECL = set(re.findall(r'function\s+([A-Za-z_$][\w$]*)\s*\(', APPJS))
JS_SKIP = {
    'if', 'for', 'while', 'return', 'typeof', 'JSON', 'String', 'Number',
    'parseInt', 'parseFloat', 'Math', 'Date', 'Array', 'Object',
    'setTimeout', 'setInterval', 'encodeURIComponent', 'document', 'window',
    'alert', 'confirm', 'event', 'this', 'close', 'open', 'parent', 'top',
    'isNaN', 'Boolean', 'RegExp', 'Intl', 'clearTimeout', 'getElementById',
    'click', 'replace', 'remove', 'writeText', 'focus', 'blur', 'select',
    'submit', 'reset', 'showSuggest', 'esc', 'encodeURI', 'stopPropagation',
    'preventDefault', 'setAttribute', 'getAttribute', 'parseInt', 'toString',
    'toLocaleString', 'concat', 'map', 'filter', 'join', 'slice', 'split',
}
_missing, _checked = [], 0
for f, src in TPL.items():
    tf = set(re.findall(r'function\s+([A-Za-z_$][\w$]*)\s*\(', src))
    tf |= set(re.findall(r'window\.([A-Za-z_$][\w$]*)\s*=', src))
    tf |= set(re.findall(r'(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function|\()', src))
    for m in re.finditer(r'on(?:click|change|input|submit|focus|blur|keyup|keydown)\s*=\s*"([^"]*)"', src):
        for cm in re.finditer(r'([A-Za-z_$][\w$]*)\s*\(', m.group(1)):
            name = cm.group(1)
            if name in JS_SKIP:
                continue
            _checked += 1
            if name in tf or name in KIT_FUNCS or name in KIT_DECL:
                continue
            _missing.append(f'{f}: {name}()')
check(not _missing, f'{_checked} вызовов проверено, все функции существуют ({_missing[:3]})')

print('== 4. Внутренние href → роуты ==')
_missing = []
for f, src in TPL.items():
    for m in re.finditer(r'href\s*=\s*["\'](/[^"\'#\s]+)', src):
        u = m.group(1)
        if u.startswith(('/static', '/api')) or '{{' in u or '{%' in u:
            continue
        if re.search(r'[\+\'\"${}]', u):
            continue
        if route_exists(strip_query(u)) is None:
            _missing.append(f'{f}: {u}')
check(not _missing, f'все href ведут в существующие роуты ({_missing[:3]})')

print('== 5. form action → роуты ==')
_missing = []
for f, src in TPL.items():
    for m in re.finditer(r'<form[^>]*action\s*=\s*["\']([^"\']+)["\']', src):
        a = m.group(1)
        if a.startswith('http') or '{{' in a:
            continue
        if route_exists(strip_query(a)) is None:
            _missing.append(f'{f}: {a}')
check(not _missing, f'все form action ведут в существующие роуты ({_missing[:3]})')

print('== 6. Баланс Jinja-блоков ==')
def _jinja_pairs(src):
    """Парный подсчёт {% ... %}: каждый открывающий находит свой закрывающий.
    Одиночные '%}' из CSS (напр. width:100%}) не считаются."""
    pairs, i = 0, 0
    while True:
        op = src.find('{%', i)
        if op == -1:
            break
        cl = src.find('%}', op + 2)
        if cl == -1:
            return pairs, True   # есть незакрытый
        pairs += 1
        i = cl + 2
    # хвостовые '%}' без открывающего — тоже дисбаланс
    tail = src.count('%}', i) if i else 0
    return pairs, tail > 0

_bad = []
for f, src in TPL.items():
    pairs, broken = _jinja_pairs(src)
    if broken:
        _bad.append(f)
check(not _bad, f'Jinja-блоки сбалансированы во всех {len(TPL)} шаблонах ({_bad[:3]})')

print('== 7. charset / lang / title ==')
_bad = []
for f, src in TPL.items():
    # шаблоны-расширения наследуют шапку из base.html
    if '{% extends' in src:
        continue
    if '<meta charset' not in src:
        _bad.append(f'{f}: нет charset')
    if 'lang="' not in src and "lang='" not in src:
        _bad.append(f'{f}: нет lang')
    if '<title>' not in src:
        _bad.append(f'{f}: нет title')
_base = TPL.get('base.html', '')
check('<meta charset' in _base and 'lang="' in _base and '<title>' in _base,
      'base.html несёт charset/lang/title')
check(not _bad, f'у самостоятельных шаблонов charset/lang/title ({_bad[:3]})')

print('== 8. Дубликаты id в разметке ==')
_bad = []
for f, src in TPL.items():
    markup = re.sub(r'<script>.*?</script>', '', src, flags=re.S)
    markup = re.sub(r'<style>.*?</style>', '', markup, flags=re.S)
    ids = re.findall(r'id\s*=\s*"([^"]+)"', markup)
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        _bad.append(f'{f}: {dups}')
check(not _bad, f'дублей id в разметке нет ({_bad[:3]})')

print('== 9. getElementById → существующие id ==')
# динамические id, которые создаёт сам app.js
KIT_CREATED_IDS = set(re.findall(r"id\s*=\s*['\"]([A-Za-z0-9_\-]+)['\"]", APPJS))
_bad = []
for f, src in TPL.items():
    markup = re.sub(r'<script>.*?</script>', '', src, flags=re.S)
    markup = re.sub(r'<style>.*?</style>', '', markup, flags=re.S)
    markup_ids = set(re.findall(r'id\s*=\s*"([^"]+)"', markup))
    # id, создаваемые в JS самого шаблона (шаблонные строки/конкатенации)
    js_ids = set(re.findall(r"id\s*=\s*[\"']([A-Za-z0-9_\-]+)[\"']", src))
    known = markup_ids | js_ids | KIT_CREATED_IDS | {'', 'regError'}
    for m in re.finditer(r"getElementById\(\s*['\"]([^'\"]+)['\"]\s*\)", src):
        gid = m.group(1)
        if gid in known:
            continue
        # осознанная проверка совместимости: if (getElementById('X')) …
        if re.search(r"if\s*\(\s*document\.getElementById\(['\"]" + re.escape(gid) + r"['\"]\)", src):
            continue
        _bad.append(f'{f}: getElementById({gid!r})')
check(not _bad, f'все getElementById находят свои id ({_bad[:5]})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
