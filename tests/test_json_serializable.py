#!/usr/bin/env python3
"""Ничего несериализуемого не должно попадать в JSON.

Повод — боевая ошибка владельца:
    App command error in update: Object of type set is not JSON serializable
    when serializing dict item 'rel'
`verify_zip` отдаёт `rel` множеством, а `save_pending` писал его в
data/.update_pending.json как есть. Проверка, которая тогда «прошла»,
передавала в функцию выдуманную строку вместо настоящего множества — то есть
не проверяла ничего.

Здесь два слоя:
1. Статический: AST-обход всех боевых .py — множество/представление словаря,
   присвоенное в функции, не должно попадать в её json.dump/dumps.
2. runtime: json временно заменяется строгим (множества, dict-view, bytes —
   ошибка), и на настоящих данных прогоняются реальные писатели JSON из
   пути обновления.

Запуск: python3 tests/test_json_serializable.py
"""
import ast
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SKIP_DIRS = {'.venv', 'venv', 'node_modules', '.git', '__pycache__',
             'tests', '.arena', 'dist', '.mypy_cache', '.pytest_cache'}
VIEW_METHODS = {'keys', 'values', 'items'}
SET_CALLS = {'set', 'frozenset'}

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


# ─── 1. Статический обход ──────────────────────────────────────────────────
def _py_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith('.py'):
                yield os.path.join(dirpath, fn)


def _is_setish(node):
    if isinstance(node, (ast.SetComp, ast.Set)):
        return True
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name) and f.id in SET_CALLS:
            return True
        if (isinstance(f, ast.Attribute) and f.attr in VIEW_METHODS
                and isinstance(f.value, ast.Name)):
            return True
    return False


def _setish_names(func):
    names = set()
    for node in ast.walk(func):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            val = getattr(node, 'value', None)
            if val is None or not _is_setish(val):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(t.id for t in targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AugAssign) and _is_setish(node.value):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
    return names


def _json_calls(func):
    return [n for n in ast.walk(func)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in ('dump', 'dumps')
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == 'json']


def _names_in(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


print('== 1. AST: локальное множество не уходит в json ==')
_scanned = 0
_syntax = []
_hits = []
for path in _py_files():
    try:
        src = io.open(path, encoding='utf-8').read()
    except OSError:
        continue
    try:
        tree = ast.parse(src)
    except SyntaxError as ex:
        _syntax.append(f'{os.path.relpath(path, ROOT)}: {ex}')
        continue
    _scanned += 1
    for func in [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        bad = _setish_names(func)
        if not bad:
            continue
        for call in _json_calls(func):
            crossed = bad & _names_in(call)
            if crossed:
                _hits.append('%s:%d %s' % (os.path.relpath(path, ROOT),
                                           call.lineno, sorted(crossed)))
check(not _syntax, f'все .py разбираются (ошибок синтаксиса: {len(_syntax)}) {_syntax[:2]}')
check(_scanned > 150, f'просканировано боевых .py: {_scanned}')
check(not _hits, f'множество не пишется в json напрямую: {len(_hits)} {_hits[:3]}')

# ─── 2. Строгий json + настоящие данные ───────────────────────────────────
print('== 2. Строгий json на реальных писателях ==')
_BAD_TYPES = (set, frozenset, bytes, bytearray, memoryview)
_VIEWS = (type({}.keys()), type({}.values()), type({}.items()))
_real_dumps, _real_dump = json.dumps, json.dump


def _scan(obj, path='корень', depth=0):
    if depth > 80:
        return
    if isinstance(obj, _BAD_TYPES):
        raise TypeError(f'несериализуемо: {type(obj).__name__} по пути {path}')
    if isinstance(obj, _VIEWS):
        raise TypeError(f'несериализуемо: dict-view по пути {path}')
    if isinstance(obj, dict):
        for k, v in obj.items():
            _scan(v, f'{path}.{k}', depth + 1)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _scan(v, f'{path}[{i}]', depth + 1)


def _strict_dumps(obj, *a, **kw):
    _scan(obj)
    return _real_dumps(obj, *a, **kw)


def _strict_dump(obj, fp, *a, **kw):
    _scan(obj)
    return _real_dump(obj, fp, *a, **kw)


json.dumps, json.dump = _strict_dumps, _strict_dump
try:
    from services import self_update as SU  # noqa: E402

    # 2.1 сама провокация: строгий json обязан её поймать
    try:
        json.dumps({'rel': {1, 2}})
        check(False, 'строгий json ловит множество')
    except TypeError:
        check(True, 'строгий json ловит множество')

    # 2.2 НАСТОЯЩАЯ цепочка обновления: verify_zip отдаёт rel множеством
    work = tempfile.mkdtemp(prefix='json_guard_')
    src_zip = os.path.join(work, 'src.zip')
    with zipfile.ZipFile(src_zip, 'w') as z:
        z.writestr('repo-x/main.py', 'NEW MAIN\n')
        z.writestr('repo-x/config.py', 'NEW CONFIG\n')
        z.writestr('repo-x/web/app.py', 'NEW APP\n')
        z.writestr('repo-x/cogs/fresh.py', '# new\n')
    ok, err, meta = SU.verify_zip(src_zip)
    check(ok, f'verify_zip принял архив ({err})')
    _names, root, rel = meta
    check(isinstance(rel, set), f'rel — множество ({type(rel).__name__})')

    try:
        ok2, err2 = SU.save_pending(work, src_zip, root, rel, 'deadbeef', 'main')
        check(ok2, f'save_pending пережил множество rel под строгим json ({err2})')
    except TypeError as ex:
        check(False, f'save_pending упал на сериализации: {ex}')

    z2, root2, rel2 = SU.load_pending(work)
    check(bool(z2) and root2 == root and rel2 == rel,
          'load_pending вернул тот же корень и то же множество')

    # 2.3 остальные писатели пути обновления
    try:
        SU.note_applied_sha(work, 'deadbeef')
        check(True, 'note_applied_sha пишет без несериализуемого')
    except TypeError as ex:
        check(False, f'note_applied_sha: {ex}')

    SU.clear_pending(work)
    shutil.rmtree(work, ignore_errors=True)
finally:
    json.dumps, json.dump = _real_dumps, _real_dump

check(json.dumps({'a': [1, 2]}) == '{"a": [1, 2]}',
      'обычный json восстановлен после проверки')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
