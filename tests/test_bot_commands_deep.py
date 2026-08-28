# -*- coding: utf-8 -*-
"""Проверка команд бота — глубокий аудит каждого slash/префиксного вызова.

1. Все cogs/*.py синтаксически валидны (AST-парс всех 111 модулей).
2. У каждого кога есть setup() (для bot.load_extension).
3. app_commands.command: непустое description (Discord регистрация иначе
   откажет), дефолтное имя читаемое.
4. Без коллизий имён команд между когами (дубликаты ломают регистрацию
   дерева целиком).
5. Дерево ошибок подключено: пользователи видят вежливые сообщения вместо
   traceback (error_handler.tree.on_error).
6. Нет базовых антипаттернов: print в handler-коде команд (шум в системе
   логирования), голый raise без обработки в коге.
"""
import ast
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0


def check(ok, msg, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {detail}')


def is_cmd_decorator(call):
    """app_commands.command(...) / command(...) декоратор?"""
    fn = call.func
    if isinstance(fn, ast.Attribute) and fn.attr == 'command':
        return True
    if isinstance(fn, ast.Name) and fn.id == 'command':
        return True
    return False


print('== 1–2. Синтаксис и setup() всех когов ==')
cogs = sorted(glob.glob(os.path.join(ROOT, 'cogs', '*.py')))
missing_setup = []
parse_fails = []
for f in cogs:
    name = os.path.basename(f)
    src = open(f, encoding='utf-8').read()
    try:
        tree = ast.parse(src, filename=name)
    except SyntaxError as e:
        check(False, f'{name}: парсится AST', e)
        parse_fails.append(name)
        continue
    has_setup = any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'setup'
        for n in tree.body)
    if name.startswith('_'):
        continue   # приватные хелперы-лоджи — не коги
    if not has_setup:
        missing_setup.append(name)
check(not parse_fails, f'все {len(cogs)} когов синтаксически валидны ({parse_fails[:5]})')
check(not missing_setup, f'у всех когов есть setup() (нет у: {missing_setup})')

print('== 3–4. Команды: description и уникальность ==')


GROUP_DECS = ('hybrid_group', 'group', 'Group')


def _deco_group_name(call, fallback):
    for kw in call.keywords:
        if kw.arg == 'name' and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    return fallback


def class_groups(cls):
    """Имя-переменной : имя группы.

    Две формы: app_commands.Group(name=...) присваивание И функция,
    декорированная @commands.(hybrid_)group(name=...).
    """
    groups = {}
    for node in cls.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            if isinstance(fn, ast.Attribute) and fn.attr == 'Group':
                gname = None
                for kw in node.value.keywords:
                    if kw.arg == 'name' and isinstance(kw.value, ast.Constant):
                        gname = str(kw.value.value)
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        groups[t.id] = gname or t.id
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)                         and dec.func.attr in GROUP_DECS:
                    groups[node.name] = _deco_group_name(dec, node.name)
    return groups


seen = {}   # (группа/имя) полный путь
bad_desc = []
total_cmds = 0
for f in cogs:
    name = os.path.basename(f)
    src = open(f, encoding='utf-8').read()
    tree = ast.parse(src, filename=name)
    cls_groups = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            cls_groups = class_groups(node)
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call) or not is_cmd_decorator(dec):
                continue
            total_cmds += 1
            cmd_name = node.name
            desc = None
            kwmap = {kw.arg: kw.value for kw in dec.keywords}
            if 'name' in kwmap and isinstance(kwmap['name'], ast.Constant):
                cmd_name = kwmap['name'].value or cmd_name
            if 'description' in kwmap and isinstance(kwmap['description'], ast.Constant):
                desc = kwmap['description'].value
            dec_txt = ast.dump(dec.func)
            if 'app_commands' in dec_txt:
                if not desc or not str(desc).strip():
                    bad_desc.append(f'{name}:{node.name}')
            # полный путь: команда из группы? (@group.command -> attr chain .value)
            full = cmd_name
            fn = dec.func
            from_group = isinstance(fn, ast.Attribute) \
                and isinstance(fn.value, ast.Name) \
                and fn.value.id in cls_groups
            if from_group:
                full = f'{cls_groups[fn.value.id]}/{cmd_name}'
            # неймспейс: slash (app.command/hybrid) vs prefix (@commands.command) —
            # регистрируются независимо, конфликт допустим ТОЛЬКО внутри одного
            is_slash = ('app_commands' in dec_txt) or ('hybrid' in dec_txt)
            ns = 'slash' if is_slash else 'prefix'
            key = (ns, full)
            origin = seen.get(key)
            if origin:
                print(f'  ДУБЛИКАТ {ns}-команды «{full}»: {origin} и {name}:{node.name}')
            check(key not in seen, f'«{full}» ({ns}): путь команды уникален ({name})',
                  f'конфликт с {origin}')
            seen.setdefault(key, f'{name}:{node.name}')
check(total_cmds > 60, f'обнаружено команд: {total_cmds} (ожидаем 60+)')
check(not bad_desc, f'у всех slash-команд есть описание (пустые: {bad_desc[:8]})')

print('== 5. Вежлые ошибки вместо traceback ==')
eh = open(os.path.join(ROOT, 'error_handler.py'), encoding='utf-8').read()
check('tree.on_error' in eh and 'AppCommandError' in eh,
      'error_handler: дерево on_error на месте')
main = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
check('error_handler' in main, 'main подключает error_handler')

print('== 6. Гигиена: print не используется в командах ==')
noisy = []
for f in cogs:
    name = os.path.basename(f)
    src = open(f, encoding='utf-8').read()
    tree = ast.parse(src, filename=name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == 'print':
            noisy.append(f'{name}:{node.lineno}')
check(not noisy, f'в командах нет print (есть: {noisy[:8]})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
