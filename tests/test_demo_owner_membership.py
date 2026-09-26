# -*- coding: utf-8 -*-
"""Владелец панели виден среди участников демо-сервера.

Жалоба владельца (2026-09): «в панель я зашёл как owner, хотя его даже
нет на сервере». Причины:
  * в демо-составе людей (DEMO_MEMBERS) не было записи владельца — поиск,
    @-пикеры, подсказки имён и списки «команды» его не показывали;
  * список /api/guild/<id>/members в демо падал в jsonify([]): у фейкового
    участника не было атрибутов discord.Member (discriminator и др.), из-за
    чего «на сервере не было вообще никого» при живом счётчике.

Ожидание: запись владельца (id 7 = owner_id сервера) есть в DEMO_MEMBERS,
а демо-состав сервера отдаётся целиком и начинается с владельца.

Запуск: python3 tests/test_demo_owner_membership.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PASS = 0
FAIL = 0


def check(cond, label, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


def _demo_members():
    """Открыть демо-процесс как scripts/demo_panel.py (бот-заглушка)."""
    import scripts.demo_panel  # noqa: F401  (ставит FakeBot и USERS)
    import web.app as wapp
    client = wapp.app.test_client()
    with client.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = 'owner'
        s['role'] = 'owner'
    r = client.get('/api/guild/4242/members')
    return r


print('== web/routes/_common.py: владелец в демо-составе людей ==')
from web.routes._common import DEMO_MEMBERS  # noqa: E402

owner = next((m for m in DEMO_MEMBERS if str(m.get('id')) == '7'), None)
check(owner is not None,
      'в DEMO_MEMBERS есть запись владельца (id 7 — owner_id сервера)')
if owner:
    check(owner.get('display_name') == 'Владелец'
          and 'Владелец' in [r.get('name') for r in owner.get('roles') or []],
          'владелец назван «Владелец» и несёт роль «Владелец»',
          f'→ {owner.get("display_name")!r} / роли: '
          f'{[r.get("name") for r in owner.get("roles") or []]}')
check(any(str(m.get('id')) == '1001' and m.get('name') == 'sonya.staff'
          for m in DEMO_MEMBERS),
      'прежние демо-участники (sonya.staff) на месте')
check(len(DEMO_MEMBERS) >= 10, f'демо-состав не похудел ({len(DEMO_MEMBERS)})')

print('== Демо-сервер: /api/guild/4242/members отдаёт состав с владельцем ==')
r = _demo_members()
d = r.get_json() if r.is_json else None
check(r.status_code == 200 and isinstance(d, list) and len(d) >= 10,
      f'список участников не пуст и не падает (получено '
      f'{len(d) if isinstance(d, list) else "?"})',
      f'→ статус {r.status_code}')
if isinstance(d, list) and d:
    first = d[0]
    check(str(first.get('id')) == '7'
          and (first.get('display_name') == 'Владелец'),
          'владелец — первый в списке участников сервера',
          f'→ {first.get("id")} {first.get("display_name")}')
    check(any(str(m.get('id')) == '1001' for m in d),
          'остальные демо-участники тоже в списке')
    ids = [str(m.get('id')) for m in d]
    check(ids == [str(m.get('id')) for m in DEMO_MEMBERS],
          'состав сервера = демо-состав людей (один источник)')

print()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
