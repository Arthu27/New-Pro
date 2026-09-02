# -*- coding: utf-8 -*-
"""Тесты раунда B аудита: утечки sqlite, осиротевшие страницы, .env.example.

Запуск: python3 tests/test_housekeeping.py
"""
import os
import re
import sys
import glob
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_housekeep_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


# ═══ 1. db.py: соединение закрывается даже при ошибке ════════════════════
print('== db: нет утечек соединений ==')
from db import GuildData, UserData  # noqa: E402


class FaultyConn:
    """Конн, у которого execute всегда падает (database is locked)."""
    def __init__(self):
        self.closed = False

    def execute(self, *a, **k):
        raise RuntimeError('database is locked')

    def commit(self):
        pass

    def close(self):
        self.closed = True


def leak_probe(store, method, *args):
    fc = FaultyConn()
    store._conn = lambda: fc
    crashed = False
    try:
        getattr(store, method)(*args)
    except Exception:
        crashed = True
    return crashed, fc.closed


g = GuildData('leak_g')
u = UserData('leak_u')
cr, cl = leak_probe(g, 'get', 1, 'k');            check(cr and cl, 'GuildData.get: ошибка прокинута, conn закрыт')
cr, cl = leak_probe(g, 'get_all', 1);             check(cr and cl, 'GuildData.get_all: conn закрыт при ошибке')
cr, cl = leak_probe(g, 'get_all_keys', 1);        check(cr and cl, 'GuildData.get_all_keys: conn закрыт при ошибке')
cr, cl = leak_probe(g, 'count', 1);               check(cr and cl, 'GuildData.count: conn закрыт при ошибке')
cr, cl = leak_probe(u, 'get', 1);                 check(cr and cl, 'UserData.get: conn закрыт при ошибке')
cr, cl = leak_probe(u, 'get_all');                check(cr and cl, 'UserData.get_all: conn закрыт при ошибке')
cr, cl = leak_probe(GuildData('leak_g2'), '_ensure_table'); check(cr and cl, 'GuildData._ensure_table: conn закрыт при ошибке')
cr, cl = leak_probe(UserData('leak_u2'), '_ensure_table');  check(cr and cl, 'UserData._ensure_table: conn закрыт при ошибке')

# штатная работа после правок
g2 = GuildData('ok_g')
check(g2.set(7, 'k', {'x': 1}) and g2.get(7, 'k')['x'] == 1, 'GuildData: set/get roundtrip работает')
check(g2.count(7) == 1 and g2.get_all_keys(7) == ['k'], 'GuildData: count/keys работают')
check(g2.delete(7, 'k') and not g2.exists(7, 'k'), 'GuildData: delete/exists работают')
u2 = UserData('ok_u')
u2.set(5, {'balance': 900})
check(u2.get(5)['balance'] == 900 and u2.get_top('balance')[0]['user_id'] == 5, 'UserData: get/get_top работают')

# ═══ 2. Осиротевшие страницы ═════════════════════════════════════════════
print('== панель: сироты подключены, мёртвые удалены ==')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
check(not os.path.exists(os.path.join(ROOT, 'web/templates/users_new.html')),
      'users_new.html удалён')
check(not os.path.exists(os.path.join(ROOT, 'web/templates/base_new.html')),
      'base_new.html удалён')
tpl_all = ' '.join(open(f, encoding='utf-8').read()
                   for f in glob.glob(os.path.join(ROOT, 'web/templates/*.html')))
check('base_new.html' not in tpl_all and 'users_new' not in tpl_all,
      'ни один шаблон не ссылается на удалённые')

menu_src = open(os.path.join(ROOT, 'services/panel_menu.py'), encoding='utf-8').read()
# Про-аналитика удалена вместе с тикетами (она целиком читала
# data/ai_tickets_*.json) — следим, чтобы не вернулась в меню.
check("'/advanced-analytics'" not in menu_src, 'меню: Про-аналитики больше нет (тикеты удалены)')
check("'Тикеты'" not in menu_src, 'меню: раздела «Тикеты» больше нет')
check("'/reports-queue'" in menu_src, 'меню: очередь репортов подключена')
check("'/theme-settings'" in menu_src, 'меню: Тема панели подключена')

from web.app import app as _flask_app, set_bot_instance  # noqa: E402


class FakeGuild:
    def __init__(self, gid):
        self.id = gid


class FakeBot:
    guilds = [FakeGuild(1)]
    latency = 0.01
    users = []

    def is_closed(self):
        return False


set_bot_instance(FakeBot())
client = _flask_app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'HK'
    s['role'] = 'owner'

for p in ('/theme-settings', '/reports-queue'):
    r = client.get(p)
    page = r.get_data(as_text=True)
    check(r.status_code == 200 and '{%' not in page,
          f'{p}: рендерится (200, чистый Jinja)')

# ═══ 3. .env.example покрывает все ключи кода ════════════════════════════
print('== .env.example: полное покрытие ==')
pats = [
    re.compile(r"os\s*\.\s*getenv\s*\(\s*['\"]([A-Z0-9_]+)['\"]"),
    re.compile(r"os\s*\.\s*environ\s*\.\s*get\s*\(\s*['\"]([A-Z0-9_]+)['\"]"),
    re.compile(r"_env_(?:int|str|bool|float|list)\s*\(\s*['\"]([A-Z0-9_]+)['\"]"),
    re.compile(r"env_(?:int|str|bool)\s*\(\s*['\"]([A-Z0-9_]+)['\"]"),
]
code_keys = set()
for f in (glob.glob(os.path.join(ROOT, '*.py')) + glob.glob(os.path.join(ROOT, 'cogs/*.py'))
          + glob.glob(os.path.join(ROOT, 'services/*.py')) + glob.glob(os.path.join(ROOT, 'web/*.py'))):
    src = open(f, encoding='utf-8').read()
    for p in pats:
        code_keys |= set(p.findall(src))
example = open(os.path.join(ROOT, '.env.example'), encoding='utf-8').read()
example_keys = set(re.findall(r'^#?\s*([A-Z0-9_]+)=', example, re.M))
missing = sorted(code_keys - example_keys)
check(not missing, f'.env.example покрывает все {len(code_keys)} ключей ({missing or "ок"})')
for group in ('5. AI-ПРОВАЙДЕРЫ', '6. ЛОГИРОВАНИЕ', '7. ВЕБ-ПАНЕЛЬ', '8. КАНАЛЫ', '9. ПРОЧЕЕ'):
    check(group in example, f'.env.example: секция «{group}» на месте')

# ═══ 4. Линт: ноль молчаливых except в проекте ═══════════════════════════
print('== гигиена: silent except lint ==')
import ast  # noqa: E402

silent_left = []
for f in (glob.glob(os.path.join(ROOT, 'cogs/*.py')) + glob.glob(os.path.join(ROOT, 'services/*.py'))
          + glob.glob(os.path.join(ROOT, 'web/**/*.py'), recursive=True)
          + [os.path.join(ROOT, 'error_handler.py'),
             os.path.join(ROOT, 'json_store.py'),
             os.path.join(ROOT, 'main.py')]):
    try:
        tree = ast.parse(open(f, encoding='utf-8').read())
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        body = [b for b in node.body
                if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant)
                        and isinstance(b.value.value, str))]
        if len(body) == 1 and isinstance(body[0], (ast.Pass, ast.Continue)):
            silent_left.append(f'{os.path.basename(f)}:{node.lineno}')
check(not silent_left, f'ни одного молчаливого except (pass/continue) в коде '
                       f'({silent_left[:3] if silent_left else "все подписаны логом"})')

# ═══ 5. Гигиена корня: никаких мусорных txt/md (архив в docs/devnotes) ═══
print('== гигиена корня ==')
_ROOT_ALLOWED_DOCS = {'README.md', 'requirements.txt', 'requirements-test.txt',
                      'requirements-panel.txt'}
junk = sorted(f for f in os.listdir(ROOT)
              if os.path.isfile(os.path.join(ROOT, f))
              and os.path.splitext(f)[1].lower() in ('.md', '.txt')
              and f not in _ROOT_ALLOWED_DOCS)
check(not junk, f'корень чист: только README.md и requirements*.txt '
                f'({junk[:3] if junk else "мусор в docs/devnotes/"})')
check(os.path.isdir(os.path.join(ROOT, 'docs', 'devnotes')), 'docs/devnotes/ существует')
archived = len([f for f in os.listdir(os.path.join(ROOT, 'docs', 'devnotes'))
                if os.path.splitext(f)[1].lower() in ('.md', '.txt')])
check(archived >= 20, f'в архиве заметок {archived} файлов (19 исторических + README-индекс)')

# ═══ 6. Русские сообщения без обрубков и турецких склонений ═════════════
# Регресс продакшн-логов: '[Companion] DM отправл — user DM\'leri закрыт.'
print('== сообщения: никаких «отправл» и турецких вкраплений ==')
_msg_files = (glob.glob(os.path.join(ROOT, 'cogs/*.py'))
              + glob.glob(os.path.join(ROOT, 'services/*.py'))
              + glob.glob(os.path.join(ROOT, 'web/**/*.py'), recursive=True)
              + glob.glob(os.path.join(ROOT, '*.py')))
# «отправл» законно только с продолжением е/ё/я/ю (отправлено, отправляет,
# отправлю…); иначе это обрубленное слово.
_TRUNCATED = []
_TURKISH = []
_TURK_NEEDLES = ("\\'e DM", "\\'a DM", "DM'lere", "DM'leri")
for f in _msg_files:
    src = open(f, encoding='utf-8').read()
    for m in re.finditer('отправл', src):
        nxt = src[m.end():m.end() + 1]
        if nxt not in 'еёяюЕЁЯЮ':
            _TRUNCATED.append(f'{os.path.basename(f)}:{src[:m.start()].count(chr(10)) + 1}')
    for _n in _TURK_NEEDLES:
        if _n in src:
            _TURKISH.append(f'{os.path.basename(f)}:{_n!r}')
check(not _TRUNCATED, f'нет обрубленных «отправл» ({_TRUNCATED[:3] or "чисто"})')
check(not _TURKISH, f'нет турецких склонений в русских строках ({_TURKISH[:3] or "чисто"})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
