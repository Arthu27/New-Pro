# -*- coding: utf-8 -*-
"""Баг «Список действий: свежие события показываются как 4 часа назад».

Причина: продюсеры пишут метки UTC двумя форматами — naive
(cogs/logs.py: now(timezone.utc).replace(tzinfo=None)) и aware ('+00:00').
Браузер читает naive-строку как ЛОКАЛЬНОЕ время → сдвиг на размер пояса
(у владельца +4 часа). Фикс: web.app._ts_to_utc_iso нормализует метки
в ISO со смещением на точках отдачи (/api/logs, /api/warnings).

Запуск: python3 tests/test_log_timestamps.py
"""
import datetime
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_ts_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['PANEL_PASSWORD'] = 'TsTest!2026'

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


UTC = datetime.timezone.utc

# ═══ 1. Юнит: _ts_to_utc_iso ═══════════════════════════════════════════
print('== _ts_to_utc_iso: naive/aware/Z/мусор ==')
import web.app as wa  # noqa: E402

f = wa._ts_to_utc_iso

fresh_naive = datetime.datetime.now(UTC).replace(tzinfo=None, microsecond=0).isoformat()
out = f(fresh_naive)
check(out.endswith('+00:00'), 'naive-метка → ISO с +00:00')
check(datetime.datetime.fromisoformat(out)
      == datetime.datetime.fromisoformat(fresh_naive).replace(tzinfo=UTC),
      '_ts_to_utc_iso не сдвигает мгновение (naive = UTC)')

aware = datetime.datetime(2026, 8, 13, 4, 0, 0, tzinfo=UTC).isoformat()
check(datetime.datetime.fromisoformat(f(aware)) == datetime.datetime(2026, 8, 13, 4, 0, 0, tzinfo=UTC),
      'aware UTC проходит без сдвига')

out5 = f('2026-08-13T09:00:00+05:00')
check(datetime.datetime.fromisoformat(out5) == datetime.datetime(2026, 8, 13, 4, 0, 0, tzinfo=UTC),
      'aware +05:00 корректно конвертируется в UTC (мгновение то же)')

outz = f('2026-08-13T04:00:00Z')
check(outz.endswith('+00:00') and datetime.datetime.fromisoformat(outz)
      == datetime.datetime(2026, 8, 13, 4, 0, 0, tzinfo=UTC),
      'Z-суффикс понимается')

outsp = f('2026-08-13 04:00:00')
check(outsp.endswith('+00:00'), 'пробел вместо T — тоже ISO, не падает')

check(f('') == '' and f(None) == '', 'пустые/None → пустая строка, без падений')
check(f('какая-то чушь') == 'какая-то чушь', 'мусорная строка → как есть (не падает)')

# ═══ 2. /api/logs: метки нормализованы на точке отдачи ═════════════════
print('== /api/logs: свежее событие ≠ «4 часа назад» ==')
now = datetime.datetime.now(UTC).replace(microsecond=0)
fresh = now.replace(tzinfo=None).isoformat()                      # naive UTC (как пишет logs.py)
old_naive = (now - datetime.timedelta(hours=2)).replace(tzinfo=None).isoformat()
old_aware = (now - datetime.timedelta(hours=1)).isoformat()       # aware UTC
os.makedirs('data', exist_ok=True)
json.dump({'42': [
    {'action': 'Ban', 'user_name': 'Nagibator', 'mod_name': 'admin',
     'reason': 'спам', 'timestamp': old_naive},
    {'action': 'Kick', 'user_name': 'Vredina', 'mod_name': 'admin',
     'reason': 'капс', 'timestamp': old_aware},
    {'action': 'Mute', 'user_name': 'Fresh', 'mod_name': 'admin',
     'reason': 'флуд', 'timestamp': fresh},
    {'action': 'Test', 'user_name': 'X', 'mod_name': '?',
     'reason': '', 'timestamp': 'странный формат'},
]}, open('data/audit_log.json', 'w', encoding='utf-8'), ensure_ascii=False)

client = wa.app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'modden'
    s['role'] = 'mod'

r = client.get('/api/logs')
check(r.status_code == 200, f'/api/logs → 200 (получено {r.status_code})')
events = r.get_json()
check(isinstance(events, list) and len(events) >= 4, f'события вернулись ({len(events)} шт)')

by_action = {e['action']: e for e in events}
mute = by_action['Mute']
check(mute['timestamp'].endswith('+00:00'), 'мьюту выдана метка со смещением +00:00')
parsed = datetime.datetime.fromisoformat(mute['timestamp'])
delta = abs((datetime.datetime.now(UTC) - parsed).total_seconds())
check(delta < 10, f'главный регресс: свежее событие отстаёт на {delta:.1f}с, а не на 4 часа')

ban = by_action['Ban']
check(ban['timestamp'].endswith('+00:00'), 'naive-метка бана тоже нормализована')
kick = by_action['Kick']
check(kick['timestamp'].endswith('+00:00') and abs(
    (datetime.datetime.fromisoformat(kick['timestamp'])
     - (now - datetime.timedelta(hours=1))).total_seconds()) < 2,
    'aware-метка кика не съехала')
check(by_action['Test']['timestamp'] == 'странный формат',
      'мусорная метка не роняет отдачу и доезжает как есть')

instants = [datetime.datetime.fromisoformat(e['timestamp'])
            for e in events if e['timestamp'].endswith('+00:00')]
check(instants == sorted(instants, reverse=True),
      'сортировка по мгновению (новые сверху), а не по сырой строке')
check(events[0]['action'] == 'Mute', 'свежее событие — первым в списке')

# ═══ 3. /api/warnings: та же болезнь, та же прививка ═══════════════════
print('== /api/warnings ==')
json.dump({'123456789012345678': {'987654321098765432': [
    {'reason': 'мат', 'mod': 'admin', 'timestamp': fresh},
]}}, open('data/warnings.json', 'w', encoding='utf-8'), ensure_ascii=False)

r = client.get('/api/warnings')
warns = r.get_json()
check(r.status_code == 200 and isinstance(warns, list) and len(warns) == 1,
      f'/api/warnings → 200, 1 варн (получено {r.status_code}, {len(warns) if isinstance(warns, list) else "—"})')
w = warns[0]
check(w['timestamp'].endswith('+00:00'), 'варну выдана метка со смещением')
delta = abs((datetime.datetime.now(UTC)
             - datetime.datetime.fromisoformat(w['timestamp'])).total_seconds())
check(delta < 10, f'варн свежий по мгновению ({delta:.1f}с), без 4-часового сдвига')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
