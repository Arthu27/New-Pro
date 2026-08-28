# -*- coding: utf-8 -*-
"""Тесты: /case (карточка нарушителя) + публичная /status страница.

Запуск: python3 tests/test_case_status.py
"""
import asyncio
import io
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta

_TMP = tempfile.mkdtemp(prefix='hakumo_case_status_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs import mod_case as mc  # noqa: E402

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


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ═══ 1. collect_case — агрегатор ═════════════════════════════════════════
print('== collect_case ==')
NOW = datetime.now(timezone.utc)
warns = [
    {'id': 1, 'reason': 'флуд', 'mod': 'M', 'timestamp': (NOW - timedelta(days=3)).isoformat()},
    {'id': 2, 'reason': 'капс', 'mod': 'M', 'timestamp': (NOW - timedelta(days=1)).isoformat()},
]
cases = [
    {'id': 1, 'user_id': '55', 'action': 'ban', 'reason': 'рейд',
     'timestamp': (NOW - timedelta(days=2)).isoformat()},
    {'id': 2, 'user_id': '99', 'action': 'warn', 'reason': 'чужой',  # другой юзер — отфильтруется
     'timestamp': NOW.isoformat()},
]
proofs = [
    {'id': 1, 'user_id': 55, 'action': 'варн', 'reason': 'спам', 'set_at': '2026-08-10T12:00:00'},
    {'id': 2, 'user_id': 55, 'action': 'бан', 'reason': 'реклама', 'set_at': '2026-08-11T12:00:00'},
    {'id': 3, 'user_id': 77, 'action': 'варн', 'reason': 'чужая', 'set_at': '2026-08-12T12:00:00'},
]
ghost = {'until': (NOW + timedelta(hours=5)).isoformat()}
d = mc.collect_case(55, 'Хулиган', warns=warns, cases=cases, notes=[{'note': 'n'}],
                    proofs=proofs, ghost=ghost,
                    timed_out_until=NOW + timedelta(hours=2),
                    joined_at=NOW - timedelta(days=30), created_at=NOW - timedelta(days=200))
check(d['warns_n'] == 2 and d['cases_n'] == 1, 'агрегатор: варны/кейсы (чужой кейс отфильтрован)')
check(d['proofs_n'] == 2 and d['notes_n'] == 1, 'агрегатор: демки/заметки (чужая демка отфильтрована)')
check(d['score'] == 100 - 2 * 12 - 25, f'агрегатор: скор по формуле warnings (есть {d["score"]})')
check(d['ghost_active'] and d['ghost_until'] != '—', 'агрегатор: тихий мут активен + срок')
check(d['timed_out'] and d['timeout_until'] != '—', 'агрегатор: таймаут активен')
check(d['joined'] != '—' and d['created'] != '—', 'агрегатор: даты на сервере/создания')
check(len(d['last_warns']) == 2 and d['last_warns'][0]['date'].count('.') == 2,
      'агрегатор: последние варны с датами дд.мм.гггг')
check(d['last_proofs'][0]['extra'] == 'бан', 'агрегатор: демки со свежей сверху + действие')
d2 = mc.collect_case(1, 'Чистя', warns=[], cases=[], proofs=[])
check(d2['score'] == 100 and not d2['ghost_active'] and not d2['timed_out']
      and d2['last_warns'] == [] and d2['last_proofs'] == [],
      'агрегатор: чистый юзер — 100 очков, без статусов')

# ═══ 2. render_case_card — PNG ═══════════════════════════════════════════
print('== render_case_card ==')
check(mc._PIL_OK, 'Pillow доступен')
buf = mc.render_case_card(d)
raw = buf.getvalue()
check(raw[:4] == b'\x89PNG' and len(raw) > 20000, f'рендер: валидный PNG ({len(raw)//1024} КБ)')
from PIL import Image  # noqa: E402
im = Image.open(io.BytesIO(raw))
check(im.size == (1200, 830), 'рендер: холст 1200×830')
av = Image.new('RGB', (128, 128), (200, 60, 60))
buf2 = mc.render_case_card(d2, avatar_img=av)
check(buf2.getvalue()[:4] == b'\x89PNG', 'рендер: с аватаром и пустым досье тоже ок')

# ═══ 3. /case — колбэк ═══════════════════════════════════════════════════
print('== /case callback ==')
# сиды данных: зеркало варнов + advanced_mod + демки
os.makedirs('data', exist_ok=True)
with open('data/warnings.json', 'w', encoding='utf-8') as f:
    json.dump({'777': {'55': warns}}, f)
with open('data/mod_advanced_data.json', 'w', encoding='utf-8') as f:
    json.dump({'case': {'777': cases}, 'notes': {'777': {'55': [{'note': 'следить', 'mod': 'M'}]}},
               'watchlist': {}}, f)
from cogs.proof_cog import proof_add  # noqa: E402
proof_add(777, 55, 'Хулиган', 1, 'Мод', 'варн', 'флуд в чате', link='https://x')


class Resp:
    def __init__(self):
        self.sent = []
        self.defer_kw = None

    async def defer(self, **kw):
        self.defer_kw = kw

    async def send(self, **kw):
        self.sent.append(kw)

    async def send_message(self, **kw):
        self.sent.append(kw)


class Av:
    async def read(self):
        b = io.BytesIO()
        Image.new('RGB', (32, 32), (60, 120, 200)).save(b, format='PNG')
        return b.getvalue()


class Member:
    id = 55
    display_name = 'Хулиган'
    bot = False
    display_avatar = Av()
    timed_out_until = NOW + timedelta(hours=1)
    joined_at = NOW - timedelta(days=10)
    created_at = NOW - timedelta(days=100)


class Guild:
    id = 777
    name = 'G'


class Inter:
    def __init__(self):
        self.guild = Guild()
        self.response = Resp()
        self.followup = Resp()
        self.user = Member()


class Bot:
    user = None

    def get_cog(self, name):
        return None  # warnings-кога нет → проверяем JSON-фолбэк


cog = mc.ModCase(Bot())
inter = Inter()
run(mc.ModCase.case.callback(cog, inter, Member(), public=False))
check(inter.response.defer_kw == {'ephemeral': True}, '/case: defer ephemeral по умолчанию')
check(inter.followup.sent and 'file' in inter.followup.sent[0],
      '/case: прислал файл-карточку')
fobj = inter.followup.sent[0]['file']
check(getattr(fobj, 'filename', '') == 'case_55.png', '/case: имя файла с ID юзера')
inter2 = Inter()
run(mc.ModCase.case.callback(cog, inter2, Member(), public=True))
check(inter2.response.defer_kw == {'ephemeral': False}, '/case public=True → видно всем')

# ═══ 4. Публичная статус-страница ════════════════════════════════════════
print('== /status ==')
from web.app import app as _flask_app, set_bot_instance  # noqa: E402
from error_handler import ErrorHandler  # noqa: E402


class G:
    id = 1


class DemoBot:
    def __init__(self):
        self.guilds = [G(), G()]
        self.latency = 0.083
        self.users = [1, 2, 3, 4, 5]
        self.error_handler = ErrorHandler(self)

    def is_closed(self):
        return False


set_bot_instance(DemoBot())
client = _flask_app.test_client()

r = client.get('/status')  # без логина
page = r.get_data(as_text=True)
check(r.status_code == 200, '/status доступна без логина (200)')
check('sidebar' not in page and 'navbar' not in page, '/status: автономная (без каркаса панели)')
for marker in ('id="hero"', 'st-state', 'm-ping', 'm-uptime', 'm-guilds',
               '/api/status-public', 'setInterval'):
    if marker in page:
        PASS += 1
    else:
        FAIL += 1
        print(f'  FAIL: нет маркера {marker}')
print('  PASS: маркеры статус-страницы на месте (7)')

r = client.get('/api/status-public')
d = r.get_json()
check(r.status_code == 200 and d.get('ok') is True, 'API: 200 и ok без логина')
check(d['online'] is True and d['latency_ms'] == 83 and d['guilds'] == 2,
      'API: живые данные (онлайн, пинг, сервера)')
check(d['users_cached'] == 5 and 'uptime_human' in d and 'updated' in d,
      'API: кэш юзеров, аптайм, метка времени')
leak = json.dumps(d)
check('token' not in leak.lower() and 'secret' not in leak.lower()
      and '127.0.0' not in leak and str(G().id) not in [str(d.get('guild_id', ''))],
      'API: никаких секретов/внутренностей в публичном ответе')


class DeadBot:
    guilds = []
    latency = float('nan')

    def is_closed(self):
        return True


set_bot_instance(DeadBot())
d = client.get('/api/status-public').get_json()
check(d['online'] is False and d['latency_ms'] == 0 and d['guilds'] == 0,
      'API: офлайн-бот отдаёт корректные нули')
set_bot_instance(DemoBot())

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
