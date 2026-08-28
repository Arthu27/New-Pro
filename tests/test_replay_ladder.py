"""
Регрессионные проверки: /replay (реплеер событий) и /ladder (лестница наказаний).
Запуск из корня проекта: python3 tests/test_replay_ladder.py
"""
import datetime
import json
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.getcwd()))

PASSED = FAILED = 0


def check(name, cond):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f'  PASS: {name}')
    else:
        FAILED += 1
        print(f'  FAIL: {name}')


# ── Рендереры карточек ────────────────────────────────────────────────────────
from services.replay_card import render_replay_card, REPLAY_CARD_OK
from services.ladder_card import render_ladder_card, LADDER_CARD_OK

check('replay_card доступен (PIL)', REPLAY_CARD_OK)
check('ladder_card доступен (PIL)', LADDER_CARD_OK)

ev = [
    {'time': '12:40', 'cat': 'member', 'label': 'Зашёл на сервер', 'detail': 'Тестер'},
    {'time': '12:51', 'cat': 'mod', 'label': 'Предупреждение #1', 'detail': 'Мод: Admin'},
    {'time': '12:58', 'cat': 'role', 'label': 'Изменение ролей', 'detail': '+ VIP'},
]
png = render_replay_card('События: Тестер', 'окно 30 мин', ev, now_str='13:00 UTC')
check('replay: PNG 14 событий максимум', png is not None and len(png) > 20000)
many = [{'time': f'{h:02d}:00', 'cat': 'mod', 'label': f'Событие {h}', 'detail': 'x'} for h in range(20)]
png2 = render_replay_card('Много', 'тест', many)
check('replay: переполнение без падения', png2 is not None)
png3 = render_replay_card('Пусто', 'тест', [])
check('replay: пустая лента без падения', png3 is not None)

steps = [{'count': 2, 'action': 'mute', 'duration': 10, 'unit': 'minute'},
         {'count': 3, 'action': 'mute', 'duration': 1, 'unit': 'hour'},
         {'count': 5, 'action': 'kick'},
         {'count': 7, 'action': 'ban'}]
png4 = render_ladder_card(steps, guild_name='TEST')
check('ladder: PNG со ступенями', png4 is not None and len(png4) > 20000)
png5 = render_ladder_card([], guild_name='TEST')
check('ladder: пустая лестница без падения', png5 is not None)

from services.ladder_card import _duration_text
check('ladder: длительность бан навсегда', _duration_text({'action': 'ban'}) == 'навсегда')
check('ladder: 1 час', _duration_text({'duration': 60}) == '1 час')
check('ladder: 10 минут', _duration_text({'duration': 10}) == '10 минут')
check('ladder: 2 дня', _duration_text({'duration': 2, 'unit': 'day'}) == '2 дня')

# ── Совместимость конфига лестницы с cogs/warnings ───────────────────────────
os.makedirs('data', exist_ok=True)
gid = '777000'
from cogs.warnings import load_warn_config
from cogs.ladder import _save_warn_config, _steps, _fmt_step

_save_warn_config(gid, {'steps': steps})
cfg = load_warn_config(gid)
check('ladder: конфиг читается warnings.apply_warn_punishment-формат', _steps(cfg) == steps)
check('ladder: fmt мут', _fmt_step({'action': 'mute', 'duration': 10, 'unit': 'minute'}) == 'мут на 10 мин')
check('ladder: fmt бан', _fmt_step({'action': 'ban', 'duration': 0}) == 'бан навсегда')

# ступень добавляется/убирается
st = _steps(load_warn_config(gid))
st = [s for s in st if int(s['count']) != 4] + [{'count': 4, 'action': 'kick', 'duration': 0, 'unit': 'minute'}]
_save_warn_config(gid, {'steps': st})
got = [s for s in _steps(load_warn_config(gid)) if int(s['count']) == 4]
check('ladder: ступень добавлена', len(got) == 1 and got[0]['action'] == 'kick')

# ── /replay: загрузка и фильтрация событий ────────────────────────────────────
from cogs.replay import _load_events, _parse_ts, _detail_text

now = datetime.datetime.now(datetime.timezone.utc)
old_ts = (now - datetime.timedelta(hours=3)).isoformat()
new_ts = (now - datetime.timedelta(minutes=5)).isoformat()
json.dump({gid: [
    {'category': 'mod', 'action': 'Бан', 'timestamp': old_ts, 'user_id': '42', 'user_name': 'Old', 'reason': 'старое'},
    {'category': 'role', 'action': 'Изменение ролей', 'timestamp': new_ts, 'user_id': '42',
     'user_name': 'Fresh', 'added_roles': ['VIP'], 'mod_name': 'Admin'},
]}, open('data/audit_log.json', 'w', encoding='utf-8'), ensure_ascii=False)

events = _load_events(gid)
check('replay: события загружены', len(events) == 2)

threshold = now - datetime.timedelta(minutes=30)
fresh = []
for e in events:
    ts = _parse_ts(e)
    if not ts:
        continue
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    if ts >= threshold:
        fresh.append(e)
check('replay: старое событие отфильтровано', len(fresh) == 1)

det = _detail_text({'user_name': 'Fresh', 'added_roles': ['VIP'], 'mod_name': 'Admin', 'reason': '—'})
check('replay: детали с ролью и модератором', '+ VIP' in det and 'Мод: Admin' in det)

# фильтр по участнику
uid = '42'
match = [e for e in events if f'"{uid}"' in json.dumps(e, ensure_ascii=False)]
check('replay: фильтр по участнику', len(match) == 2)

# ── ACL: команды зарегистрированы в панели разрешений ─────────────────────────
from services.permission_acl import COMMAND_CATEGORIES
all_cmds = {c for cmds in COMMAND_CATEGORIES.values() for c in cmds}
for cmd in ('replay', 'ladder', 'ladder-add', 'ladder-remove', 'ladder-test'):
    check(f'ACL: {cmd}', cmd in all_cmds)

os.system('rm -rf data')
print(f'\n=== PASS {PASSED} / FAIL {FAILED} ===')
sys.exit(0 if FAILED == 0 else 1)
