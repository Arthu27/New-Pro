# -*- coding: utf-8 -*-
"""Живой аудит блокировки владельца: никто, кроме owner, не видит и не
открывает меню/страницы/API владельца. Проверяется САМОЙ панелью:
реальный вход (или симулированная унаследованная сессия uye), реальный
рендер сайдбара, реальные GET/POST всех owner- и admin-маршрутов.

Запуск: python3 tests/test_owner_lockdown.py
"""

import os, sys, tempfile, asyncio, threading, json, re
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'owner-pass-123'
os.environ['OWNER_ID'] = '42'
os.environ.pop('DEMO_MODE', None)
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['PANEL_LOGIN_CONFIRM'] = '0'
_TMP = tempfile.mkdtemp(prefix='hakumo_lockdown_')
os.chdir(_TMP)
sys.path.insert(0, '/home/user/New-Pro')
os.makedirs('data', exist_ok=True)
json.dump({'400': 'curator'}, open('data/role_map.json', 'w'))
from types import SimpleNamespace as NS
import web.app as A

def make_member(uid, mod=False, admin=False, role_ids=()):
    perms = NS(administrator=admin, ban_members=mod, kick_members=mod,
               manage_guild=False, manage_messages=False, manage_channels=False)
    return NS(id=uid, bot=False,
              roles=[NS(id=r, name=f'role{r}', members=[], colour=None) for r in role_ids],
              guild_permissions=perms, display_name=f'user{uid}', name=f'user{uid}')

GUILD_MEMBERS = {
    '100': make_member(100, admin=True),
    '200': make_member(200, mod=True),
    '300': make_member(300, mod=False),
    '400': make_member(400, role_ids=[400]),
}
import discord as _discord
_ch = NS(id=1001, name='pravila', position=0, type=_discord.ChannelType.text, category=None,
         topic='', nsfw=False, slowmode_delay=0, bitrate=0, user_limit=0,
         created_at=None, mention='<#1001>', members=[])
guild = NS(id=777, owner_id=42, name='Lockdown', get_member=lambda uid: GUILD_MEMBERS.get(str(uid)),
           members=list(GUILD_MEMBERS.values()), channels=[_ch])
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()
A.bot_instance = NS(guilds=[guild], get_guild=lambda gid: guild if gid == 777 else None,
                    loop=loop, latency=0.05, get_cog=lambda name: None,
                    get_role=lambda rid: NS(id=rid, name=f'role{rid}', members=[], colour=None,
                                            permissions=NS(administrator=False, ban_members=False,
                                                           kick_members=False, manage_guild=False,
                                                           manage_messages=False, manage_channels=False)))
A._resolve_guild_member = lambda g, uid: GUILD_MEMBERS.get(str(uid))
json.dump({
    '100': {'display_name': 'admin100', 'name': 'admin100', 'role': 'admin', 'password': A._hash_pw('pass-admin'), 'registered_at': '2026-01-01'},
    '200': {'display_name': 'mod200', 'name': 'mod200', 'role': 'mod', 'password': A._hash_pw('pass-mod'), 'registered_at': '2026-01-01'},
    '300': {'display_name': 'member300', 'name': 'member300', 'role': 'uye', 'password': A._hash_pw('pass-uye'), 'registered_at': '2026-01-01'},
    '400': {'display_name': 'curator400', 'name': 'curator400', 'role': 'curator', 'password': A._hash_pw('pass-cur'), 'registered_at': '2026-01-01'},
}, open('data/members.json', 'w'))

from services.panel_menu import PAGE_MIN_ROLE, _ROLE_LEVEL, MENU

PASS = FAIL = 0
def check(name, cond, extra=''):
    global PASS, FAIL
    if cond: PASS += 1; print(f'  PASS {name}')
    else: FAIL += 1; print(f'  FAIL {name} {extra}')

# ── сессии всех ролей ─────────────────────────────────────────────────────
sessions = {}
sessions['owner'] = A.app.test_client()
sessions['owner'].post('/login', data={'username': 'owner', 'password': 'owner-pass-123'})
for role, (did, pw) in (('admin', ('100', 'pass-admin')), ('mod', ('200', 'pass-mod')),
                        ('curator', ('400', 'pass-cur'))):
    cc = A.app.test_client()
    r = cc.post('/login', data={'username': did, 'password': pw})
    assert r.status_code == 302, (did, r.status_code)
    sessions[role] = cc
# uye не проходит вход — симулируем унаследованную сессию (как в матрице)
cc = A.app.test_client()
with cc.session_transaction() as ss:
    ss['logged_in'] = True
    ss['role'] = 'uye'
    ss['discord_id'] = '300'
    ss['username'] = 'member300'
    ss['_role_checked'] = A._time.time()
sessions['uye'] = cc

ROLES = ('owner', 'admin', 'curator', 'mod', 'uye')

# ── 1. OWNER-СТРАНИЦЫ: из PAGE_MIN_ROLE и явных min_role ─────────────────
OWNER_PAGES = sorted({p for p, r in PAGE_MIN_ROLE.items() if r == 'owner'} |
                     {p['path'] for g in MENU for p in g['pages'] if p.get('min_role') == 'owner'})
print(f'\n═══ 1. OWNER-страницы ({len(OWNER_PAGES)}) ═══')
for path in OWNER_PAGES:
    for role in ROLES:
        r = sessions[role].get(path, follow_redirects=False)
        ok = (r.status_code in (302, 403, 404, 405)) if role != 'owner' else (r.status_code in (200, 302, 404))
        check(f'{path} [{role}] → {r.status_code}', ok, 'владелец не прошёл' if role == 'owner' else 'ПРОПУСТИЛ НЕ-ВЛАДЕЛЬЦА')

# ── 2. OWNER-API: все маршруты с role_required("owner") ──────────────────
OWNER_APIS = [
    ('GET', '/api/panel-menu'), ('GET', '/api/panel-menu/layout'),
    ('GET', '/api/login-log'),
    ('POST', '/api/panel-menu'), ('POST', '/api/panel-menu/layout'),
    ('POST', '/api/leave-guild'), ('POST', '/api/bot/restart'),
    ('POST', '/api/bot/gc'), ('POST', '/api/bot/memory-profile'),
    ('GET', '/api/bot/memory-profile'),
]
print(f'\n═══ 2. OWNER-API ({len(OWNER_APIS)}) ═══')
for method, path in OWNER_APIS:
    for role in ROLES:
        r = sessions[role].open(path, method=method, follow_redirects=False,
                                json={} if method == 'POST' else None)
        # 405 = метод не разрешён самим маршрутом — тоже отказ, не пропуск
        ok = (r.status_code in (302, 403, 404, 405)) if role != 'owner' else True
        check(f'{method} {path} [{role}] → {r.status_code}', ok, 'ПРОПУСТИЛ НЕ-ВЛАДЕЛЬЦА')

# ── 3. САЙДБАР: ни одной owner-ссылки у не-владельца ─────────────────────
print('\n═══ 3. Сайдбар (HTML /api/panel/sidebar) ═══')
for role in ROLES:
    r = sessions[role].get('/api/panel/sidebar?path=/')
    html = r.get_data(as_text=True)
    links = set(re.findall(r'href="(/[^"?#]+)', html))
    leaked = sorted(p for p in links if PAGE_MIN_ROLE.get(p) == 'owner'
                    or p in {pp['path'] for g in MENU for pp in g['pages'] if pp.get('min_role') == 'owner'})
    if role == 'owner':
        owned = [p for p in OWNER_PAGES if p in links]
        check(f'владелец видит свои страницы ({len(owned)} из {len(OWNER_PAGES)})', len(owned) >= 3, f'видно {owned}')
    else:
        check(f'сайдбар [{role}]: 0 owner-ссылок', not leaked, f'УТЕЧКА: {leaked}')

# ── 4. ПОИСК ПО МЕНЮ: owner-страницы не находятся не-владельцем ─────────
print('\n═══ 4. Поиск по меню (/api/ux/search) ═══')
for role in ROLES:
    try:
        r = sessions[role].get('/api/ux/search?q=настро')
        body = r.get_json(silent=True) or {}
        items = json.dumps(body, ensure_ascii=False)
    except Exception:
        r = sessions[role].get('/api/ux/search?q=settings')
        body = r.get_json(silent=True) or {}
        items = json.dumps(body, ensure_ascii=False)
    if role == 'owner':
        continue
    leaked = [p for p in OWNER_PAGES if p in items]
    check(f'поиск [{role}]: owner-страниц не найти', not leaked, f'УТЕЧКА: {leaked}')

# ── 5. ADMIN-СТРАНИЦЫ: mod/curator/uye не проходят ───────────────────────
ADMIN_PAGES = sorted({p for p, r in PAGE_MIN_ROLE.items() if r == 'admin'} |
                     {p['path'] for g in MENU for p in g['pages'] if p.get('min_role') == 'admin'})
print(f'\n═══ 5. ADMIN-страницы vs mod/curator/uye ({len(ADMIN_PAGES)}) ═══')
for path in ADMIN_PAGES:
    for role in ('curator', 'mod', 'uye'):
        r = sessions[role].get(path, follow_redirects=False)
        check(f'{path} [{role}] → {r.status_code}', r.status_code in (302, 403, 404, 405), 'ПРОПУСТИЛ')

# ── 6. БЕЗ-РОЛИ маршруты: uye не должен видеть чужие данные ─────────────
print('\n═══ 6. Login-only API под сессией uye ═══')
for path in ('/api/stats', '/api/guilds', '/api/build-info', '/api/tunnel-url',
             '/api/notifications/poll', '/api/activity-feed', '/api/my-notifications',
             '/announcements', '/theme-settings'):
    r = sessions['uye'].get(path, follow_redirects=False)
    # uye либо пущен на «свою» страницу (200), либо отвергнут (302/403) —
    # главное не 500 и не штабные данные без фильтра
    check(f'{path} [uye] → {r.status_code}', r.status_code in (200, 302, 403), 'падает/странно')

print(f'\n════ БЛОКИРОВКА ВЛАДЕЛЬЦА: PASS {PASS} / FAIL {FAIL} ════')
sys.exit(1 if FAIL else 0)
