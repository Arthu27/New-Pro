# -*- coding: utf-8 -*-
"""Глубокий аудит «идеальности» Hakumo — нет даже мелких проблем.

Запуск:  python3 scripts/check_health.py        (Linux/macOS)
         python scripts\check_health.py         (Windows VDS)

Отличие от соседей:
  check_files.py      — дружба ФАЙЛОВ (порты/хосты/вызовы/маршруты);
  check_connection.py — живое соединение «бот ↔ панель» при работающем боте;
  check_health.py (тут) — «всё идеально» целиком: лимиты Discord, защита
                        каждого роута панели, шаблоны/статика, JSON,
                        зависимости, роли, гигиена git, тесты.

Секции:
  [A] Дружба файлов — прогон scripts/check_files.py (порты/127.0.0.1/вызовы)
  [B] Коги и команды Discord: синтаксис, setup() у каждого когa, НЕТ дублей
      имён, лимиты гильдии (100 слэш / 5 контекстных меню), описания ≤ 100
      символов, имена ≤ 32 и валидны (Discord режет синк из-за таких мелочей)
  [C] Панель: каждый render_template имеет файл, каждый url_for('static')
      имеет файл, роли панели существуют, role_required без опечаток
  [D] Защита роутов: каждый @app.route либо с @login_required, либо в
      осознанном белом списке (логин/health/статус-пейдж/webhook с токеном/
      Discord-OAuth музыка) — новая «дыра» сразу падает проверкой
  [E] JSON: все .json репозитория и data/ парсятся без ошибок
  [F] Зависимости: пакеты из requirements*.txt импортируются; сторонние
      module-level импорты заявлены в requirements (ленивые — опциональны)
  [G] Гигиена git: .env не в git, .gitignore закрывает данные/логи/туннель
  [H] Тесты: все наборы компилируются, количество
  [I] Живая панель (если запущена): /health отвечает 200

Итог: «=== PASS N / FAIL M ===» и код выхода 0/1.
"""
import ast
import importlib.util
import json
import os
import py_compile
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

OK = 0
FAIL = 0
SKIP = 0


def check(ok, msg, fix=''):
    global OK, FAIL
    if ok:
        OK += 1
        print(f'  [OK]   {msg}')
    else:
        FAIL += 1
        print(f'  [FAIL] {msg}')
        if fix:
            print(f'         → {fix}')


def skip(msg):
    global SKIP
    SKIP += 1
    print(f'  [SKIP] {msg}')


def read(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except OSError:
        return ''


def walk_py(folder):
    out = []
    for root, dirs, files in os.walk(folder):
        if '__pycache__' in root:
            continue
        for f in files:
            if f.endswith('.py'):
                out.append(os.path.join(root, f))
    return out


print('=' * 68)
print(' Глубокий аудит Hakumo — «всё идеально, даже мелочи»')
print('=' * 68)

# ── A. Дружба файлов (порты / origin / вызовы / маршруты) ───────────────────
print('\n[A] Дружба файлов (scripts/check_files.py):')
try:
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, 'scripts', 'check_files.py')],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    out = proc.stdout.decode('utf-8', errors='replace')
    m = re.search(r'=== PASS (\d+) / FAIL (\d+) ===', out)
    check(proc.returncode == 0 and m and m.group(2) == '0',
          f'check_files: {m.group(0) if m else "нет итога"}',
          'запусти python scripts/check_files.py и поправь FAIL-строки')
except Exception as _ex:  # noqa: BLE001
    check(False, 'check_files.py запускается', f'ошибка: {_ex}')

# ── B. Коги и лимиты Discord ────────────────────────────────────────────────
print('\n[B] Коги и команды Discord:')
policy_src = read('cogs_policy.py')
cog_files = sorted(f for f in os.listdir('cogs') if f.endswith('.py'))
broken_cogs = []
no_setup = []
for f in cog_files:
    p = os.path.join('cogs', f)
    try:
        py_compile.compile(p, doraise=True)
    except Exception as ex:  # noqa: BLE001
        broken_cogs.append(f'{f}: {ex}')
        continue
    src = read(p)
    if 'async def setup' not in src and f not in policy_src:
        no_setup.append(f)
check(not broken_cogs, f'все {len(cog_files)} когов компилируются',
      '; '.join(broken_cogs[:3]))
check(not no_setup,
      f'у каждого когa есть setup() (кроме исключений политики: {no_setup or "—"})',
      'добавь async def setup(bot) или внеси файл в исключения cogs_policy')

# имена/описания/дубли — по всем когам и сервисам
names = {}
bad_desc, bad_name, ctx_menus = [], [], []
for p in walk_py('cogs') + walk_py('services') + ['main.py']:
    src = read(p)
    for m in re.finditer(
            r"@app_commands\s*\.?\s*command\s*\(\s*name\s*=\s*['\"]([^'\"]+)['\"]"
            r"\s*,\s*description\s*=\s*['\"]([^'\"]+)['\"]", src):
        name, desc = m.group(1), m.group(2)
        names.setdefault(name, []).append(os.path.basename(p))
        if len(desc) > 100:
            bad_desc.append(f'{name}: {len(desc)} символов ({os.path.basename(p)})')
        if not re.match(r'^[-_\w]{1,32}$', name):
            bad_name.append(f'{name} ({os.path.basename(p)})')
    for m in re.finditer(r"@app_commands\s*\.?\s*context_menu\s*\(\s*name\s*=\s*['\"]([^'\"]+)['\"]", src):
        ctx_menus.append(m.group(1))
        if len(m.group(1)) > 32:
            bad_name.append(f'контекст-меню {m.group(1)!r} длиннее 32 символов')
dups = {k: v for k, v in names.items() if len(v) > 1}
check(not dups, f'дублей имён команд нет ({len(names)} уникальных определений)',
      str(dups))
# В Discord уезжает НЕ всё определённое, а боевой белый список (slash_budget
# вычищает дерево при загрузке). Лимит гильдии — про итоговое меню.
try:
    sys.path.insert(0, ROOT)
    import slash_budget  # noqa: E402
    keep = set(slash_budget.KEEP_SLASH)
except Exception:  # noqa: BLE001
    keep = set()
check(len(keep) <= 100,
      f'боевое слеш-меню = KEEP_SLASH: {len(keep)} ≤ 100 (лимит гильдии Discord)')
dead_keep = sorted(n for n in keep if n not in names)
check(not dead_keep,
      'каждое имя из KEEP_SLASH реально определено в коде (белый список не протух)',
      f'мёртвые имена: {dead_keep}')
check(len(ctx_menus) <= 5, f'контекстных меню {len(ctx_menus)} ≤ 5 (лимит гильдии)')
check(not bad_desc, f'описания всех команд ≤ 100 символов (Discord режет синк)',
      '; '.join(bad_desc[:5]))
check(not bad_name, 'имена команд валидны (1-32, [-_\\w])', '; '.join(bad_name[:5]))

# ── C. Панель: шаблоны, статика, роли ───────────────────────────────────────
print('\n[C] Панель: шаблоны/статика/роли:')
missing_tpl, missing_static = [], []
for p in walk_py('web'):
    src = read(p)
    for m in re.finditer(r"render_template\s*\(\s*['\"]([^'\"]+)['\"]", src):
        tpl = m.group(1)
        if not tpl.startswith('/') and not os.path.isfile(
                os.path.join('web', 'templates', tpl)):
            missing_tpl.append(f'{tpl} ({os.path.basename(p)})')
check(not missing_tpl, 'все render_template указывают на существующие шаблоны',
      '; '.join(missing_tpl[:5]))

for f in os.listdir('web/templates'):
    if not f.endswith('.html'):
        continue
    src = read(os.path.join('web', 'templates', f))
    for m in re.finditer(
            r"url_for\s*\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"]+)['\"]", src):
        rel = m.group(1)
        if not os.path.isfile(os.path.join('web', 'static', rel)):
            missing_static.append(f'{rel} ({f})')
check(not missing_static, 'все url_for(static) указывают на существующие файлы',
      '; '.join(missing_static[:5]))

app_src = read('web/app.py')
rm = re.search(r"ROLES\s*=\s*\{([^}]+)\}", app_src)
roles = set(re.findall(r"['\"](\w+)['\"]\s*:", rm.group(1))) if rm else set()
check(bool(roles), f'роли панели определены: {", ".join(sorted(roles))}')
bad_roles = []
for p in walk_py('web'):
    src = read(p)
    for m in re.finditer(r"role_required\s*\(\s*['\"](\w+)['\"]", src):
        if roles and m.group(1) not in roles:
            bad_roles.append(f'{m.group(1)} ({os.path.basename(p)})')
check(not bad_roles, 'role_required без опечаток в именах ролей',
      '; '.join(bad_roles[:5]))

# ── D. Защита роутов панели ─────────────────────────────────────────────────
print('\n[D] Защита роутов (каждый @app.route под контролем):')
# Осознанно открытые: свои механизмы аутентификации или публичные по смыслу.
PUBLIC_EXACT = {
    '/login', '/logout', '/health', '/demo-login',           # вход и пульс
    '/status', '/api/status-public',                         # публичный статус-пейдж
    '/favicon.ico', '/welcome', '/',                         # визитка и главная
    '/register', '/apply', '/api/public/check-member',       # самостоятельная
                                                              # регистрация/заявки
    '/api/public/guilds', '/api/public/apply',               # публичная анкета
    '/api/login/suggest', '/api/discord-check',              # подсказки логина и
                                                              # публичная проверка Discord
    '/api/discord-login',                                    # вход по PIN (своя auth)
    '/api/voice-command',                                    # голос: свой shared-secret
    '/api/forgot-password', '/api/reset-password',           # восстановление доступа
}
PUBLIC_PREFIX = ('/static/', '/hooks/')                      # статика; webhook-токены
# Discord Activity музыки снесена вместе с фичей (2026-09-01) — публичных
# Bearer/OAuth-маршрутов не осталось.
PUBLIC_RE = re.compile(r'(?!)')
unprotected = []
for p in walk_py('web'):
    src = read(p)
    lines = src.split('\n')
    for i, line in enumerate(lines):
        m = re.search(r"@\s*app\s*\.\s*route\s*\(\s*['\"]([^'\"]+)['\"]", line)
        if not m:
            continue
        path = m.group(1)
        # блок декораторов: вниз до def (обычный порядок) и вверх по декораторам
        block = []
        j = i
        while j < len(lines) and j < i + 12:
            block.append(lines[j])
            if re.match(r"\s*(async\s+)?def\s+\w+", lines[j]):
                break
            j += 1
        k = i - 1
        while k >= 0 and lines[k].strip().startswith('@'):
            block.append(lines[k])
            k -= 1
        blob = '\n'.join(block)
        if 'login_required' in blob:
            continue
        if path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIX) or PUBLIC_RE.match(path):
            continue
        unprotected.append(f'{path} ({os.path.basename(p)})')
check(not unprotected,
      'каждый роут защищён @login_required (или осознанно публичный)',
      '; '.join(unprotected[:6]))

# ── E. JSON-файлы ────────────────────────────────────────────────────────────
print('\n[E] JSON-файлы:')
bad_json = []
checked_json = 0
for folder in ('.', 'data', 'config'):
    if not os.path.isdir(folder):
        continue
    for f in os.listdir(folder):
        p = os.path.join(folder, f)
        if not f.endswith('.json') or not os.path.isfile(p):
            continue
        checked_json += 1
        try:
            json.load(open(p, encoding='utf-8'))
        except Exception as ex:  # noqa: BLE001
            bad_json.append(f'{p}: {str(ex)[:60]}')
check(not bad_json, f'все {checked_json} JSON-файлов валидны',
      '; '.join(bad_json[:5]))

# ── F. Зависимости ───────────────────────────────────────────────────────────
print('\n[F] Зависимости:')
req_pkgs = set()
for rf in ('requirements.txt', 'requirements-panel.txt', 'requirements-test.txt'):
    if os.path.isfile(rf):
        for line in read(rf).split('\n'):
            line = line.split('#')[0].strip()
            if line:
                req_pkgs.add(re.split(r'[<>=!\[~]', line)[0].strip().lower())
IMPORT_TO_PKG = {'discord': 'discord.py', 'PIL': 'Pillow', 'dotenv': 'python-dotenv',
                 'flask_session': 'flask-session',
                 'deep_translator': 'deep-translator', 'faster_whisper': 'faster-whisper'}
# import-имя для проверки установки (обратное соответствие)
PKG_TO_IMPORT = {'discord.py': 'discord', 'pillow': 'PIL', 'python-dotenv': 'dotenv',
                 'flask-session': 'flask_session',
                 'deep-translator': 'deep_translator', 'faster-whisper': 'faster_whisper',
                 'pynacl': 'nacl', 'discord-ext-voice-recv': 'discord.ext.voice_recv',
                 'pyyaml': 'yaml', 'psutil': 'psutil',
                 # pip-имя со строчной, import-имя с заглавной — как у Pillow
                 'fonttools': 'fontTools'}
not_installed = []
for pkg in sorted(req_pkgs):
    top = PKG_TO_IMPORT.get(pkg, pkg.replace('-', '_'))
    try:
        if importlib.util.find_spec(top) is None:
            not_installed.append(f'{pkg} (import {top})')
    except Exception:  # noqa: BLE001
        pass
check(not not_installed, f'все {len(req_pkgs)} пакетов requirements* импортируются',
      '; '.join(not_installed[:5]) + ' → pip install -r requirements.txt')

# module-level сторонние импорты должны быть заявлены
stdlib = set(getattr(sys, 'stdlib_module_names', ()))
local_mods = {f[:-3] for root, dirs, files in os.walk('.')
              if '__pycache__' not in root
              for f in files if f.endswith('.py')}
local_mods |= {'cogs', 'services', 'web', 'tests', 'scripts'}
unlisted_module_level = []
for p in walk_py('cogs') + walk_py('services') + walk_py('web') + ['main.py', 'config.py',
                                                                   'db.py', 'logger.py']:
    try:
        tree = ast.parse(read(p))
    except SyntaxError:
        continue
    tops = set()
    for node in tree.body:            # только уровень модуля = обязательные
        if isinstance(node, ast.Import):
            tops |= {a.name.split('.')[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            tops.add(node.module.split('.')[0])
    for t in tops:
        if t in stdlib or t in local_mods or t.startswith('_'):
            continue
        pkg = IMPORT_TO_PKG.get(t, t).lower()
        if pkg in req_pkgs:
            continue
        if t == 'werkzeug' and 'flask' in req_pkgs:
            continue                    # ставится вместе с Flask
        unlisted_module_level.append(f'{t} ({os.path.basename(p)})')
check(not unlisted_module_level,
      'module-level импорты заявлены в requirements (ленивые — опциональны)',
      '; '.join(unlisted_module_level[:6]))

# ── G. Гигиена git ───────────────────────────────────────────────────────────
print('\n[G] Гигиена git:')
gitignore = read('.gitignore')
for needle in ('.env', 'data/', 'logs/', 'cloudflared', 'tunnel-creds.json'):
    check(needle in gitignore, f'.gitignore закрывает {needle}')
try:
    tracked = subprocess.run(['git', 'ls-files'], cwd=ROOT,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=30).stdout.decode('utf-8', errors='replace')
    tracked_files = set(tracked.split('\n'))
    check('.env' not in tracked_files, 'секретный .env НЕ закоммичен')
    check('scripts/tunnel-creds.json' not in tracked_files,
          'ключ туннеля (tunnel-creds.json) НЕ закоммичен')
except Exception as _ex:  # noqa: BLE001
    skip(f'git-проверки (нет репозитория?): {_ex}')

# ── H. Тесты ─────────────────────────────────────────────────────────────────
print('\n[H] Тесты:')
test_files = sorted(f for f in os.listdir('tests')
                    if f.startswith('test_') and f.endswith('.py'))
broken_tests = []
for f in test_files:
    try:
        py_compile.compile(os.path.join('tests', f), doraise=True)
    except Exception as ex:  # noqa: BLE001
        broken_tests.append(f'{f}: {str(ex)[:60]}')
check(not broken_tests, f'все {len(test_files)} тестовых наборов компилируются',
      '; '.join(broken_tests[:3]))
check(len(test_files) >= 100, f'регрессия на месте: {len(test_files)} наборов')

# ── I. Живая панель (если запущена) ──────────────────────────────────────────
print('\n[I] Живая панель:')
try:
    import urllib.request
    port = 5001
    for key in ('PANEL_PORT', 'PORT'):
        raw = os.environ.get(key, '')
        if not raw:
            try:
                with open('.env', encoding='utf-8') as fh:
                    for line in fh:
                        if line.strip().startswith(key + '='):
                            raw = line.split('=', 1)[1].strip()
                            break
            except OSError:
                raw = ''
        if raw:
            try:
                port = int(str(raw).split('#')[0].strip())
                break
            except ValueError:
                continue
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3) as r:
            check(r.status == 200, f'панель жива: /health на порту {port} → 200')
    except Exception:
        skip(f'панель не запущена на порту {port} (статический аудит без неё)')
except Exception as _ex:  # noqa: BLE001
    skip(f'живая проверка: {_ex}')

# ── Итог ─────────────────────────────────────────────────────────────────────
print()
print('=' * 68)
print(f' ИТОГ: PASS {OK} / FAIL {FAIL}' + (f' / SKIP {SKIP}' if SKIP else ''))
print('=' * 68)
print('=== PASS %d / FAIL %d ===' % (OK, FAIL))
sys.exit(1 if FAIL else 0)
