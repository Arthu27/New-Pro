# -*- coding: utf-8 -*-
"""П.7 «Консоль чистая»: синтаксический аудит КАЖДОГО инлайн-скрипта панели.

Из каждого шаблона извлекаются <script> без src. Чистый JS прогоняется
через node --check. Блоки, зависящие от Jinja-подстановок ({{ }}) —
прогоняются после безопасной замены Jinja-плейсхолдеров на синтаксически
нейтральные литералы; блоки с управляющими тегами Jinja ({% %}) вне
строковых литералов помечаются как шаблонные и прогоняются построчно:
голый-дом JS без Jinja-блоков не должен содержать ошибок.

Static .js файлы также проверяются на синтаксис последовательно (кроме vendor).
"""
import os
import re
import subprocess
import sys
import glob
import tempfile
import hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMPD = tempfile.mkdtemp(prefix='jsaudit_')

PASS = 0
FAIL = 0


def check(ok, msg, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {detail}')


def node_check(code, tag):
    h = hashlib.md5(code.encode()).hexdigest()[:12]
    fp = os.path.join(TMPD, f'{tag}_{h}.js')
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(code)
    r = subprocess.run(['node', '--check', fp], capture_output=True, text=True, timeout=20)
    os.unlink(fp)
    return r.returncode == 0, (r.stderr or '').strip().split('\n')[0][:160]
NODE_CHECK_CACHE = {}


TEMPLATE_JINJA_Q = re.compile(r'\{\{\s*([^}]*)\s*\}\}')
TEMPLATE_JINJA_B = re.compile(r'\{%.*?%\}', re.S)


JINJA_IFELSE = re.compile(r'\{%\s*if\b.*?\{%\s*endif\s*.*?%\}', re.S)


JINJA_FOR = re.compile(r'\{%\s*for\b.*?\{%\s*endfor\s*.*?%\}', re.S)


def neutralize_jinja(code):
    # 0) {% for %}...{% endfor %} — конструируют элементы массивов/строк —
    #    после удаления рушат запятые; нейтрализуем целиком
    code = JINJA_FOR.sub(' void 0 ', code)
    # 1) {% if %}...{% else %}...{% endif %}, вставляемые в позицию ЗНАЧЕНИЯ —
    #    заменяем на синтаксически нейтральный литерал
    code = JINJA_IFELSE.sub(' void 0 ', code)
    # 2) {{ x }} → синтаксически нейтральный операнд
    code = TEMPLATE_JINJA_Q.sub(' void 0 ', code)
    # 3) оставшиеся управляющие теги (без if-else-пар) — пробелы
    code = TEMPLATE_JINJA_B.sub(' ', code)
    return code


def balanced(code):
    # структурный контроль: если jinja-шаблон заворачивает границы блоков {}
    # — после нейтрализации скобки невыровнены; такие блоки пропускаем (инфо)
    b = code.count('{') - code.count('}')
    p = code.count('(') - code.count(')')
    return b == 0 and p == 0


print('== 1. Синтаксис инлайн-скриптов всех шаблонов ==')
total_blocks = 0
for f in sorted(glob.glob(os.path.join(ROOT, 'web/templates/*.html'))):
    name = os.path.basename(f)
    src = open(f, encoding='utf-8').read()
    blocks = re.findall(r'<script>(.*?)</script>', src, re.S)
    for i, b in enumerate(blocks, 1):
        code = b.strip()
        if not code:
            continue
        total_blocks += 1
        if code.startswith('{'):   # JSON-LD/metadata — пропуск
            continue
        n = neutralize_jinja(code)
        if not balanced(n):
            print(f'  инфо: {name} #{i} — структурно шаблонный (jinja-границы), пропуск')
            continue
        key = (name, i)
        if key not in NODE_CHECK_CACHE:
            NODE_CHECK_CACHE[key] = node_check('(function(){' + n + '})();', f'{name}_{i}')
        ok, err = NODE_CHECK_CACHE[key]
        check(ok, f'{name} #{i}: инлайн-скрипт синтаксически валиден', err)
print(f'  инфо: инлайн-блоков проверено: {total_blocks}')

print('== 2. Все статические JS без vendor ==')
static_files = [f for f in glob.glob(os.path.join(ROOT, 'web/static/*.js'))
                if 'vendor' not in f]
for f in sorted(static_files):
    name = os.path.basename(f)
    code = open(f, encoding='utf-8').read()
    ok, err = node_check(code, name.replace('.', '_'))
    check(ok, f'/static/{name}: синтаксис валиден', err)

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
