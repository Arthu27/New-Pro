# -*- coding: utf-8 -*-
"""Матрица «роль × страница»: весь GET-роутинг панели × все роли.

Источник ожиданий — AST-парсинг декораторов (@login_required/@role_required).
Гость/uye/mod/admin/owner проходят по каждому GET-эндпоинту; проверяем
«закрыто ровно тогда, когда надо, и открыто, когда можно».

Запуск: python3 tests/test_role_matrix.py
"""
import ast
import glob
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_matrix_test_')
os.chdir(_TMP)
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


# ═══ 1. AST-карта декораторов ═══════════════════════════════════════════
print('== карта декораторов ==')


def scan(path):
    tree = ast.parse(open(path, encoding='utf-8').read())
    out = {}

    def visit(body):
        for st in body:
            if isinstance(st, ast.FunctionDef):
                route = login = None
                role = None
                for d in st.decorator_list:
                    u = ast.unparse(d)
                    if 'route' in u:
                        route = u
                    if u.strip() == 'login_required':
                        login = True
                    if 'role_required' in u:
                        role = u.split('role_required')[1].strip("() '\" ")
                if route:
                    out[st.name] = {'login': bool(login), 'role': role}
                visit(st.body)
    visit(tree.body)
    return out


DECOS = {}
for f in [os.path.join(ROOT, 'web', 'app.py')] + glob.glob(os.path.join(ROOT, 'web', 'routes', '*.py')):
    DECOS.update(scan(f))
check(len(DECOS) >= 370, f'распарсено {len(DECOS)} эндпоинтов (≥370)')

# Публичные эндпоинты — вечный whitelist: всё без @login_required обязано
# быть ОСОЗНАННО публичным (auth-флоу, статус, заявка). Новый эндпоинт без
# декоратора уронит этот тест → решение принимает человек.
PUBLIC = {
    'index', 'welcome_page', 'login', 'logout', 'register',
    'api_forgot_password', 'api_reset_password', 'api_discord_login',
    'api_discord_check', 'api_check_member', 'api_login_suggest',
    'api_public_apply', 'api_public_guilds', 'public_apply',
    'api_status_public', 'status_public_page', 'api_voice_command',
    'favicon', 'health_check', 'static',
    # Discord Activity музыки снесена вместе с фичей музыки (2026-09-01)
    # PagerDuty → Discord: сервер-сервер вебхук с токеном в URL (без сессии)
    'hook_pagerduty',
}
public_actual = {k for k, v in DECOS.items() if not v['login']} | {'static'}
check(public_actual == PUBLIC,
      f'публичные эндпоинты ровно по whitelist (лишние: '
      f'{sorted(public_actual - PUBLIC) or "—"}; пропали: '
      f'{sorted(PUBLIC - public_actual) or "—"})')

# ═══ 2. Стенд: фейк-бот + сессии ролей ══════════════════════════════════
import web.app as wa  # noqa: E402

ROLES = wa.ROLES
check(ROLES.get('uye', 0) < ROLES['mod'] < ROLES['curator'] < ROLES['admin'] < ROLES['owner'],
      f'лестница ролей uye<mod<curator<admin<owner ({ROLES})')
check('curator' in ROLES and 'curator' in wa.ROLE_LABELS
      and wa.ROLE_LABELS['curator'] == 'Куратор',
      'куратор есть в ROLES и в русских подписях (Куратор)')


class FakeGuild:
    def __init__(self, gid):
        self.id = gid
        self.name = 'Матрица'
        self.icon = None
        self.member_count = 0
        self.members = []
        self.channels = []
        self.text_channels = []
        self.roles = []

    def get_member(self, _id):
        return None

    def get_channel(self, _id):
        return None

    def get_role(self, _id):
        return None


class FakeBot:
    guilds = [FakeGuild(1)]
    latency = 0.01
    users = []

    def is_closed(self):
        return False

    def is_ready(self):
        return True

    def get_cog(self, _name):
        return None

    def get_guild(self, _id):
        return None

    def get_user(self, _id):
        return None


wa.set_bot_instance(FakeBot())
app = wa.app

GET_RULES = []
for r in app.url_map.iter_rules():
    if 'GET' not in r.methods or '<' in str(r.rule):
        continue
    GET_RULES.append((str(r.rule), r.endpoint))
GET_RULES.sort()
check(len(GET_RULES) >= 130, f'GET-эндпоинтов без параметров: {len(GET_RULES)} (≥130)')


def make_client(role):
    c = app.test_client()
    if role is not None:
        with c.session_transaction() as s:
            s['logged_in'] = True
            s['username'] = 'MTX'
            s['role'] = role
    return c


# /logout, /login, /register — flow-страницы: редиректят по своей логике
# от роли (logout ещё и убивает сессию). Отдельно: клиент НЕ переиспользуем,
# чтобы проба /logout не разлогинивала остальные замеры.
FLOW_PATHS = {'/logout', '/login', '/register'}


def probe(role, path):
    try:
        r = make_client(role).get(path)
        loc = r.headers.get('Location', '') or ''
        to_login = r.status_code in (301, 302, 308) and 'login' in loc
        denied = r.status_code in (301, 302, 308) and 'denied=' in loc
        return r.status_code, (to_login or denied or r.status_code in (401, 403))
    except Exception:
        return 599, False


# ═══ 3. Прогон матрицы ══════════════════════════════════════════════════
print('== матрица роль × страница ==')
guest_block_viol = []   # закрытые должны редиректить на логин
guest_public_viol = []  # публичные должны открываться
denied_viol = {r: [] for r in ROLES}    # роль ниже порога, но впустило
allowed_viol = {r: [] for r in ROLES}   # роль ≥ порога, но не впустило

# Discord Activity музыки удалена вместе с фичей (2026-09-01) — Bearer-эндпойнтов
# не осталось; гоняем через сессионную матрицу все GET-правила.
BEARER_GET = set()

for path, ep in GET_RULES:
    info = DECOS.get(ep, {'login': False, 'role': None})
    if path in BEARER_GET:
        continue
    st, to_login = probe(None, path)
    if info['login']:
        if not to_login:
            guest_block_viol.append((path, st))
    elif ep in PUBLIC:
        if st >= 400:
            guest_public_viol.append((path, st))
    if path in FLOW_PATHS:
        continue
    need = ROLES.get(info['role']) if info['role'] else None
    for role in ROLES:
        st, to_login = probe(role, path)
        blocked = to_login  # login/denied/403/401 — всё «закрыто»
        if need is None:
            ok = not blocked            # просто авторизация — любой роли впускает
        elif ROLES[role] >= need:
            ok = not blocked            # уровня хватает
        else:
            ok = blocked                # уровня не хватает — ОБЯЗАНО закрыть
        if not ok:
            (denied_viol if (need is not None and ROLES[role] < need)
             else allowed_viol)[role].append((path, st))

check(not guest_block_viol, f'гость: все {sum(1 for _, e in GET_RULES if DECOS.get(e, {}).get("login"))} '
                            f'закрытых GET редиректят на логин ({guest_block_viol[:4] or "ок"})')
check(not guest_public_viol, f'гость: публичные GET открываются (<400) ({guest_public_viol[:4] or "ок"})')

for role in ('uye', 'mod', 'admin'):
    v = denied_viol[role]
    check(not v, f'{role}: ни один закрытый раздел не впустил ({v[:4] or "ок"})')
for role in ('uye', 'mod', 'admin', 'owner'):
    v = allowed_viol[role]
    check(not v, f'{role:5s}: всё разрешённое открылось без блока ({v[:4] or "ок"})')

# ═══ 4. Отказ API — JSON, а не HTML ═════════════════════════════════════
print('== API-отказы — JSON ==')
c = make_client('mod')
r = c.get('/api/role-permissions/777')  # owner-level API (role_required('owner'))
d = r.get_json(silent=True)
check(r.status_code == 403 and isinstance(d, dict) and 'error' in d,
      'недостаточный уровень: API → 403 с {"error"} в JSON')

r = make_client('uye').get('/api/cogs')
d = r.get_json(silent=True)
check(r.status_code == 403 and isinstance(d, dict), 'uye на /api/cogs → 403 JSON')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
