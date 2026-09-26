# -*- coding: utf-8 -*-
"""Аудит «до буквы»: кодировки, кракозябры, эмодзи, FA-иконки, битые сущности,
сиротские классы, мёртвые ссылки, опечатки, баланс тегов, дубли id."""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = sorted(glob.glob(os.path.join(ROOT, 'web', 'templates', '*.html')))
sys.path.insert(0, ROOT)

from web.app import app as _flask_app  # noqa: E402  (url_map для проверки ссылок)

ok_count = 0
bad_count = 0

# Семантические классы-хуки: используются как JS-селекторы, внешний вид задают
# родительские классы (form-input/details/empty) или inline-стили.
# Семантические классы-хуки: используются как JS-селекторы, внешний вид задают
# родительские классы (form-input/details/empty) или inline-стили.
# page-head-side/chs-optional — структурные обёртки: их рисует родитель
# (.page-head — flex, .chs-guide-steps — список), своего стиля не требуют.
_SEMANTIC_HOOKS = {'pulse-empty', 'sa-open', 'sh-member', 'sh-time', 'shift-manage',
                   'page-head-side', 'chs-optional',
                   'vf-card', 'vf-flow', 'vf-switch'}  # vf-* несут inline-стили
def chk(ok, msg):
    global ok_count, bad_count
    if ok: ok_count += 1
    else: bad_count += 1; print('  ПРОБЛЕМА:', msg)

# 1. Кодировки и кракозябры
MOJIBAKE = re.compile(r'[\ufffd]|Ã[\x80-\xbf]|â€|Ð[\x80-\x9f]|Â[\x80-\x9f]|Ã‚|ï»¿')
EMOJI = re.compile(r'[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]')
_KNOWN_ENT = {'amp','lt','gt','quot','apos','nbsp','hellip','mdash','ndash','laquo','raquo',
               'copy','reg','trade','bull','middot','deg','sect','para','plusmn','times',
               'divide','micro','euro','pound','yen','rarr','larr','uarr','darr','harr',
               'zwj','zwnj','shy'}
BAD_ENT = re.compile(r'&([a-zA-Z]{2,10});')
def _bad_entities(text):
    return [m.group(0) for m in BAD_ENT.finditer(text) if m.group(1) not in _KNOWN_ENT]

for f in TPL:
    raw = open(f, 'rb').read()
    name = os.path.relpath(f, ROOT)
    if raw.startswith(b'\xef\xbb\xbf'):
        chk(False, f'{name}: BOM в начале файла')
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as e:
        chk(False, f'{name}: НЕ UTF-8: {e}')
        continue
    m = MOJIBAKE.search(text)
    if m:
        ctx = text[max(0, m.start()-25):m.end()+25].replace('\n', ' ')
        chk(False, f'{name}: кракозябры: …{ctx}…')
    em = EMOJI.findall(text)
    if em:
        chk(False, f'{name}: эмодзи в шаблоне: {em[:5]}')
    be = _bad_entities(text)
    if be:
        chk(False, f'{name}: битые HTML-сущности: {be[:5]}')
    # CRLF/мусорные пробелы в конце строк
    if '\r' in text:
        chk(False, f'{name}: CRLF (\\r) в файле')
    _tw = len(re.findall(r'[ \t]+$', text, re.M))
    if _tw:
        chk(False, f'{name}: хвостовые пробелы в {_tw} строк')

print(f'[1] Кодировки/кракозябры/эмодзи/сущности: проверено {len(TPL)} шаблонов')

# 2. FA-иконки против вендорного набора
fa_css = open(os.path.join(ROOT, 'web', 'static', 'vendor', 'fontawesome', 'css', 'all.min.css'), encoding='utf-8', errors='replace').read()
fa_known = set(re.findall(r'\.(fa-[a-z0-9-]+):before', fa_css))
used = set()
for f in TPL:
    text = open(f, encoding='utf-8').read()
    for m in re.finditer(r'fa-([a-z0-9-]+)', text):
        if m.group(1) in ('solid', 'regular', 'brands', 'sharp', 'duotone', 'thin', 'light'):
            continue
        used.add('fa-' + m.group(1))
# JS-конкатенации 'fa-' + имя
for js in glob.glob(os.path.join(ROOT, 'web', 'static', '*.js')) + list(glob.glob(os.path.join(ROOT, 'web', 'templates', '*.html'))):
    text = open(js, encoding='utf-8').read()
    for m in re.finditer(r"fa-([a-z0-9-]+)", text):
        if m.group(1) in ('solid', 'regular', 'brands', 'sharp', 'duotone', 'thin', 'light'):
            continue
        used.add('fa-' + m.group(1))
unknown = sorted(u for u in used if u not in fa_known and not u.endswith('-') and u not in ('fa-spin', 'fa-pulse', 'fa-fade', 'fa-beat', 'fa-flip', 'fa-border', 'fa-stack', 'fa-inverse', 'fa-ul', 'fa-li', 'fa-fw', 'fa-2xs', 'fa-xs', 'fa-sm', 'fa-lg', 'fa-xl', 'fa-2xl', 'fa-1x', 'fa-2x', 'fa-3x', 'fa-4x', 'fa-5x', 'fa-6x', 'fa-7x', 'fa-8x', 'fa-9x', 'fa-10x', 'fa-rotate-90', 'fa-rotate-180', 'fa-rotate-270', 'fa-flip-horizontal', 'fa-flip-vertical', 'fa-flip-both', 'fa-bounce', 'fa-shake'))
chk(not unknown, f'иконки, которых нет в FA-вендоре: {unknown[:10]} (всего {len(unknown)})')
print(f'[2] FA-иконки: использовано {len(used)}, неизвестных {len(unknown)}')

# 3. Сиротские классы: class="..." в шаблонах vs style.css + inline <style>
# Все CSS панели, а не только style.css: часть классов (карточка участника)
# живёт в отдельных файлах — иначе аудит зовёт их сиротами напрасно.
css_known = set()
for css_file in glob.glob(os.path.join(ROOT, 'web', 'static', '**', '*.css'), recursive=True):
    css_known |= set(re.findall(r'\.([a-zA-Z][a-zA-Z0-9_-]*)',
                                open(css_file, encoding='utf-8', errors='replace').read()))
tpl_scripts = []
for f in TPL:
    text = open(f, encoding='utf-8').read()
    for inline in re.findall(r'<style[^>]*>(.*?)</style>', text, re.S):
        css_known |= set(re.findall(r'\.([a-zA-Z][a-zA-Z0-9_-]*)', inline))
    tpl_scripts += re.findall(r'<script[^>]*>(.*?)</script>', text, re.S)
used_classes = set()
for f in TPL:
    text = open(f, encoding='utf-8').read()
    for m in re.finditer(r'class="([^"]+)"', text):
        val = m.group(1)
        if '${' in val or "'" in val:
            continue  # JS-конкатенация — не статичный класс
        val = re.sub(r'\{[{%][^}]*[%}]\}', ' ', val)  # вырезать Jinja-условия
        for c in val.split():
            if c.startswith('fa-') or c.endswith('-'):
                continue  # иконки — шаг [2]; концы JS-конкатенаций — не классы
            if c in _SEMANTIC_HOOKS:
                continue  # хуки-селекторы: стиль у родителя/inline, у класса лишь роль метки
            used_classes.add(c)
js_known = set()
for js in glob.glob(os.path.join(ROOT, 'web', 'static', '**', '*.js'), recursive=True):
    js_known |= set(re.findall(r'\.([a-zA-Z][a-zA-Z0-9_-]*)', open(js, encoding='utf-8', errors='replace').read()))
# Класс, к которому шаблон сам обращается как к селектору (.apTpl в closest()), —
# это хук разметки, а не сирота: стиль ему и не положен.
for chunk in tpl_scripts:
    js_known |= set(re.findall(r'\.([a-zA-Z][a-zA-Z0-9_-]*)', chunk))
known = css_known | js_known | {'fas', 'far', 'fab', 'fa-solid', 'fa-regular', 'fa-brands'}
orphans = sorted(c for c in used_classes if c not in known)
chk(not orphans, f'классы без определения: {orphans[:15]} (всего {len(orphans)})')
print(f'[3] Классы: использовано {len(used_classes)}, сирот {len(orphans)}')

# 4. Мёртвые внутренние ссылки href="..." (без внешних и #)
rules = sorted(set(re.findall(r'rule\s*=\s*[\'"]([^\'"]+)', open(os.path.join(ROOT, 'web', 'app.py'), encoding='utf-8').read())))
routes = set()
for f in glob.glob(os.path.join(ROOT, 'web', '**', '*.py'), recursive=True):
    src = open(f, encoding='utf-8').read()
    routes |= set(re.findall(r"route\s*\(\s*['\"]([^'\"]+)", src))
# проверяем статичные href (не fetch, не /api/, не /static/, не #, не http, не {{ )
dead = []
for f in TPL:
    text = open(f, encoding='utf-8').read()
    for m in re.finditer(r'href="([^"]+)"', text):
        h = m.group(1)
        if '${' in h or "' +" in h or '$' in h or '(' in h or '^' in h:
            continue  # JS-конкатенация / regex
        if h.startswith(('#', 'http', '{{', '/static/', '/api/', 'mailto:')):
            continue
        if h.endswith('.css') or h.endswith('.js') or h.endswith('.ico') or h.endswith('.png'):
            continue
        if h in ('/', ''):
            continue
        base = h.split('?')[0].split('#')[0]
        if base not in routes and base.rstrip('/') not in routes:
            # Flask strict_slashes=False + url_map — проверим через приложение
            with _flask_app.test_request_context():
                adapter = _flask_app.url_map.bind('localhost')
                try:
                    adapter.match(base, method='GET')
                except Exception:
                    dead.append(f'{os.path.relpath(f, ROOT)} → {h}')
chk(not dead, f'мёртвые href: {dead[:10]}')
print(f'[4] Ссылки: мёртвых {len(dead)}')

# 5. Опечатки в русском тексте (частотные)
TYPOS = [('пожалуста', 'пожалуйста'), ('вообщем', 'в общем'), ('ихний', 'их'),
         ('евоный', 'его'), ('ложить', 'класть'), ('покласть', 'положить'),
         ('будующий', 'будущий'), ('извени', 'извини'), ('придти', 'прийти'),
         ('одеть роль', 'выдать роль'), ('экспортнуть', 'экспортировать'),
         ('залогиниться', 'войти'), ('сохронить', 'сохранить'), ('отправлё', 'отправлено'),
         ('обновления данных', 'обновление данных')]
def _typo_rx(bad):
    """Опечатка как целое слово: «ложить» ловим, а «приложить»/«положить» — нет.

    Приставочные глаголы с «-ложить» правильные, поэтому слева требуем границу
    слова; справа не ограничиваем — часть опечаток задана основой («отправлё»).
    Фразы из двух слов ищем простым вхождением.
    """
    if ' ' in bad:
        return re.compile(re.escape(bad))
    return re.compile(r'(?<![а-яёa-z-])' + re.escape(bad))


_TYPO_RX = [(bad, good, _typo_rx(bad)) for bad, good in TYPOS]
typo_found = []
for f in TPL + glob.glob(os.path.join(ROOT, 'web', 'routes', '*.py')) + glob.glob(os.path.join(ROOT, 'web', 'routes', 'api', '*.py')):
    text = open(f, encoding='utf-8').read().lower()
    for bad, good, rx in _TYPO_RX:
        if rx.search(text):
            typo_found.append(f'{os.path.relpath(f, ROOT)}: «{bad}» → «{good}»')
chk(not typo_found, f'опечатки: {typo_found[:8]}')
print(f'[5] Опечатки: найдено {len(typo_found)}')

# 6. Баланс Jinja-тегов и скобок шаблонов
for f in TPL:
    text = open(f, encoding='utf-8').read()
    _no_style = re.sub(r'<style>.*?</style>', '', text, flags=re.S)
    _no_script = re.sub(r'<script>.*?</script>', '', _no_style, flags=re.S)
    opens = len(re.findall(r'{%', _no_script))
    closes = len(re.findall(r'%}', _no_script))
    chk(opens == closes, f'{os.path.relpath(f, ROOT)}: {{% баланс {opens}/{closes}')
    for tag in ('div', 'section', 'form', 'table', 'ul', 'select', 'button', 'a', 'span', 'details'):
        o = len(re.findall(rf'<{tag}[\s>]', text))
        c = len(re.findall(rf'</{tag}>', text))
        if o != c:
            # самозакрывающиеся и пустые теги могут давать ложные срабатывания; смотрим только грубый перекос
            if abs(o - c) > 3:
                chk(False, f'{os.path.relpath(f, ROOT)}: тег <{tag}> {o} открыто / {c} закрыто')
print('[6] Баланс тегов: проверено')

# 7. Дубли id в каждом шаблоне
for f in TPL:
    text = open(f, encoding='utf-8').read()
    _ids = []
    for line in text.split('\n'):
        if "+= '" in line or "' +" in line or "'+" in line or "+'" in line or "'<" in line:
            continue  # JS-сборка строки — в DOM попадает одна копия
        for i in re.findall(r'id="([^"]+)"', line):
            if '${' not in i:
                _ids.append(i)
    ids = _ids
    dup = sorted({i for i in ids if ids.count(i) > 1})
    chk(not dup, f'{os.path.relpath(f, ROOT)}: дубли id: {dup[:5]}')
print('[7] Дубли id: проверено')

# 8. Неопределённые плейсхолдеры Jinja (переменные вне {{ }} — пропускаем, это динамика)
# но проверим: все {% extends/base %} ссылаются на существующие файлы
for f in TPL:
    text = open(f, encoding='utf-8').read()
    m = re.search(r'{%\s*extends\s+"([^"]+)"\s*%}', text)
    if m and not os.path.exists(os.path.join(ROOT, 'web', 'templates', m.group(1))):
        chk(False, f'{os.path.relpath(f, ROOT)}: extends на несуществующий {m.group(1)}')
    for inc in re.finditer(r'{%\s*include\s+"([^"]+)"\s*%}', text):
        if not os.path.exists(os.path.join(ROOT, 'web', 'templates', inc.group(1))):
            chk(False, f'{os.path.relpath(f, ROOT)}: include на несуществующий {inc.group(1)}')
titles = {}
for f in TPL:
    text = open(f, encoding='utf-8').read()
    m = re.search(r'{%\s*block title\s*%}([^{]+){%\s*endblock\s*%}', text)
    if m:
        t = m.group(1).strip()
        titles.setdefault(t, []).append(os.path.relpath(f, ROOT))
for t, files in titles.items():
    if len(files) > 1 and t:
        chk(False, f'одинаковый title «{t}» у: {files[:3]}')
print('[8] extends/include/title: проверено')

# 9. НОВОЕ: двойные пробелы в видимых заголовках (page_title/eyebrow/lead)
_dsp = 0
for f in TPL:
    text = open(f, encoding='utf-8').read()
    for tag in ('h1', 'h2', 'h3'):
        for m in re.finditer(rf'<{tag}[^>]*>([^<]{{2,}})</{tag}>', text):
            if '  ' in m.group(1):
                _dsp += 1
                if _dsp <= 5:
                    chk(False, f'{os.path.relpath(f, ROOT)}: двойной пробел в <{tag}> «{m.group(1).strip()[:50]}»')
print(f'[9] Двойные пробелы в заголовках: {_dsp}')

print(f'\n=== АУДИТ «ДО БУКВЫ»: {ok_count} проверок ок, {bad_count} проблем ===')
sys.exit(1 if bad_count else 0)
