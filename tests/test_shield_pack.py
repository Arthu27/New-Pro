# -*- coding: utf-8 -*-
"""Щит сервера «по максимуму» (заказ владельца): пробуждение защиты + центр.

Проверяем:
1. Статика: security/anti_alt/impersonation/ai_moderation в боевом LEAN-составе,
   tag_jail продолжает спать; дефолты у всех систем щита — ВКЛ.
2. Статика: у ai_moderation жёсткий страж «кик → бан» (кик отключён владельцем).
3. Статика: у панели есть shield_statuses/toggle_shield, в overview — shields,
   у страницы — блок #scShields; каталог честно режется до KEEP_SLASH;
   WEB_BEHIND_PROXY включает ProxyFix (панель за доменом/туннелем).
4. Поведение: toggle_shield реально пишет хранилища всех четырёх систем и
   shield_statuses это видит.
5. E2E (DEMO): POST /security-center/toggle feature=anti_alt и overview.

Запуск: python3 tests/test_shield_pack.py
"""
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_shield_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DEMO_MODE'] = '1'

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


GID = 777

# ─── 1. Состав и дефолты систем щита ───────────────────────────────────────
print('== 1. Состав LEAN и дефолты щита ==')
import cogs_policy  # noqa: E402

for needed in ('security.py', 'anti_alt.py', 'impersonation.py', 'ai_moderation.py'):
    check(needed in cogs_policy.MOD_LEAN_COGS, f'LEAN: {needed} в боевом составе')
check('tag_jail.py' not in cogs_policy.MOD_LEAN_COGS, 'tag_jail по-прежнему спит')

from cogs import anti_alt, impersonation, security  # noqa: E402
check(bool(anti_alt.DEFAULT_SETTINGS.get('enabled')) is False, 'анти-альт: с завода ВЫКЛ (opt-in)')
check(bool(impersonation.DEFAULT_CFG.get('enabled')) is False, 'антифейк: с завода ВЫКЛ (opt-in)')
check(all(not security._CFG_DEFAULT.get(k) for k in ('ai_spam', 'fake_account', 'link_scanner')),
      'security: все три контура с завода ВЫКЛ (opt-in)')

# ─── 2. Кик отключён и в ИИ-модерации ──────────────────────────────────────
print('== 2. Политика «без кика» ==')
aim_src = open(os.path.join(ROOT, 'cogs', 'ai_moderation.py'), encoding='utf-8').read()
check('if action =="kick":' in aim_src and 'action ="ban"' in aim_src,
      'ai_moderation: страж «кик → бан» на месте')

# ─── 3. Центр безопасности ─────────────────────────────────────────────────
print('== 3. Страница «Центр безопасности» ==')
sp = open(os.path.join(ROOT, 'web', 'routes', 'security_panel.py'), encoding='utf-8').read()
check('def shield_statuses' in sp and 'def toggle_shield' in sp, 'есть shield_statuses/toggle_shield')
check("'shields': shield_statuses(gid)" in sp, 'overview отдаёт shields')
check('toggle_shield(gid, feat' in sp, 'тогл endpoint умеет соседние системы')
st = open(os.path.join(ROOT, 'web', 'templates', 'security.html'), encoding='utf-8').read()
check('id="scShields"' in st and 'd.shields' in st, 'шаблон рисует карточки щита')
cr = open(os.path.join(ROOT, 'services', 'command_registry.py'), encoding='utf-8').read()
check('KEEP_SLASH' in cr and "c['kind'] == 'prefix'" in cr,
      'каталог панели честно совпадает с боевым slash-меню')
app_src = open(os.path.join(ROOT, 'web', 'app.py'), encoding='utf-8').read()
check('WEB_BEHIND_PROXY' in app_src and 'ProxyFix' in app_src,
      'режим панели за доменом (ProxyFix) есть')

# ─── 4. Тумблеры реально пишут хранилища ───────────────────────────────────
print('== 4. Тумблеры щита — поведение ==')
from web.routes.security_panel import shield_statuses, toggle_shield  # noqa: E402

initial = {s['key']: s['enabled'] for s in shield_statuses(GID)}
check(set(initial) == {'anti_alt', 'antifake', 'ai_moderation', 'auto_filter'},
      f'щитов ровно 4: {sorted(initial)}')
check(not any(initial.values()), 'на пустом хранилище все щиты на паузе (дефолты ВЫКЛ — opt-in)')

for key in ('anti_alt', 'antifake', 'ai_moderation', 'auto_filter'):
    ok, err = toggle_shield(GID, key, False)
    check(ok, f'{key}: пауза поставлена (err={err!r})')
    now = {s['key']: s['enabled'] for s in shield_statuses(GID)}
    check(now[key] is False, f'{key}: статус видит паузу')
    ok, err = toggle_shield(GID, key, True)
    check(ok and {s['key']: s['enabled'] for s in shield_statuses(GID)}[key] is True,
          f'{key}: запуск вернул активность')

ok, err = toggle_shield(GID, 'unknown_shield', True)
check(ok is False and err, f'неизвестная система вежливо отклонена: {err!r}')

# ─── 5. E2E: тогл и сводка через панель ────────────────────────────────────
print('== 5. E2E (демо) ==')
import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'owner'
    s['selected_guild'] = '777'

r = client.get('/api/guild/777/security-center/overview')
d = r.get_json(silent=True) or {}
check(r.status_code == 200 and d.get('success') is True, f'overview жив (HTTP {r.status_code})')
check(isinstance(d.get('shields'), list) and len(d['shields']) == 4,
      f"overview: 4 карточки щита ({len(d.get('shields') or [])})")

r = client.post('/api/guild/777/security-center/toggle',
                json={'feature': 'anti_alt', 'enabled': False})
d = r.get_json(silent=True) or {}
check(r.status_code == 200 and d.get('success') is True, f'E2E тогл anti_alt: {d}')
now = {s2['key']: s2['enabled'] for s2 in shield_statuses(GID)}
check(now['anti_alt'] is False, 'E2E: пауза реально записалась')
client.post('/api/guild/777/security-center/toggle',
            json={'feature': 'anti_alt', 'enabled': True})
check({s2['key']: s2['enabled'] for s2 in shield_statuses(GID)}['anti_alt'] is True,
      'E2E: запуск вернул активность')

# соседние настройки обычного контура не сломались
r = client.post('/api/guild/777/security-center/toggle',
                json={'feature': 'link_scanner', 'enabled': True})
d = r.get_json(silent=True) or {}
check(r.status_code == 200 and d.get('success') is True, 'старый тогл (link_scanner) жив')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
