# -*- coding: utf-8 -*-
"""Retention 14 дней + тихий high_memory + мёртвое публичное меню апелляций.

Запуск: python3 tests/test_appeals_retention_repair.py
"""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_retention_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['AUTO_REPAIR_DISCORD_NOTIFY'] = '0'
os.environ['DATA_RETENTION_DAYS'] = '14'

PASS = 0
FAIL = 0
UTC = timezone.utc
NOW = datetime.now(UTC)
GID = 793336829280780331


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


def _run(coro):
    return asyncio.run(coro)


print('== 1. diagnostics: quiet high_memory ==')
from cogs import diagnostics as DIAG  # noqa: E402

check(DIAG.THRESHOLDS['memory_mb']['warn'] == 750, 'warn memory = 750')
check(DIAG.THRESHOLDS['memory_mb']['critical'] == 1100, 'critical memory = 1100')
check(DIAG.REPAIR_ACTIONS['high_memory'] == 'Garbage collect',
      'high_memory action без reload cog')
check(DIAG.REPAIR_COOLDOWN.get('high_memory') == 3600, 'cooldown 1ч')
check(DIAG._discord_notify_enabled() is False, 'Discord notify OFF по умолчанию')
os.environ['AUTO_REPAIR_DISCORD_NOTIFY'] = '1'
check(DIAG._discord_notify_enabled() is True, 'Discord notify ON при =1')
os.environ['AUTO_REPAIR_DISCORD_NOTIFY'] = '0'


print('== 2. data_retention: appeals keep pending, drop old closed ==')
from db import GuildData  # noqa: E402
from services import data_retention as DR  # noqa: E402
from cogs import appeals as AP  # noqa: E402

db = GuildData('appeals')
state = AP.empty_state()
old = NOW - timedelta(days=20)
fresh = NOW - timedelta(days=2)

item_old_closed, _ = AP.create_appeal(state, 1, 'Old', 'старая закрытая', old)
item_old_closed['status'] = 'rejected'
item_old_closed['reviewed_at'] = old.isoformat()

item_pending_old, _ = AP.create_appeal(state, 2, 'Pend', 'висящая старая', old)
# pending остаётся pending

item_fresh, _ = AP.create_appeal(state, 3, 'Fresh', 'свежая закрытая', fresh)
item_fresh['status'] = 'accepted'
item_fresh['reviewed_at'] = fresh.isoformat()

db.set(GID, 'state', state)
dry = DR.purge_appeals(14, dry_run=True)
check(dry['removed'] == 1, f'dry-run removed=1 got {dry}')
applied = DR.purge_appeals(14, dry_run=False)
check(applied['removed'] == 1, f'apply removed=1 got {applied}')
after = db.get(GID, 'state')
ids = {i['id'] for i in after['items']}
check(item_pending_old['id'] in ids, 'pending старая сохранена')
check(item_fresh['id'] in ids, 'свежая accepted сохранена')
check(item_old_closed['id'] not in ids, 'старая rejected удалена')


print('== 3. data_retention: reports.db closed tickets ==')
os.makedirs('data', exist_ok=True)
conn = sqlite3.connect('data/reports.db')
conn.executescript("""
CREATE TABLE IF NOT EXISTS tickets(
    guild TEXT, thread_id TEXT PRIMARY KEY, kind TEXT DEFAULT 'report',
    reporter_id TEXT, accused_id TEXT, witnesses TEXT DEFAULT '[]',
    mode TEXT DEFAULT 'wait', word_id TEXT DEFAULT '',
    verdict TEXT DEFAULT '', created REAL, closed REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS violations(
    id INTEGER PRIMARY KEY AUTOINCREMENT, guild TEXT, user_id TEXT,
    kind TEXT, hours REAL, reason TEXT, thread_id TEXT, created REAL);
CREATE TABLE IF NOT EXISTS archive(
    guild TEXT, thread_id TEXT, blob BLOB, meta TEXT,
    created REAL, PRIMARY KEY(guild, thread_id));
""")
edge_old = (NOW - timedelta(days=30)).timestamp()
edge_new = (NOW - timedelta(days=1)).timestamp()
conn.execute(
    "INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,?)",
    (str(GID), 't_old', 'report', '1', '2', '[]', 'wait', '', 'ban',
     edge_old, edge_old))
conn.execute(
    "INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,?)",
    (str(GID), 't_open', 'report', '1', '3', '[]', 'wait', '', '',
     edge_old, 0))
conn.execute(
    "INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,?)",
    (str(GID), 't_new', 'report', '1', '4', '[]', 'wait', '', 'warn',
     edge_new, edge_new))
conn.execute(
    "INSERT INTO violations (guild,user_id,kind,hours,reason,thread_id,created) "
    "VALUES (?,?,?,?,?,?,?)",
    (str(GID), '2', 'warn', 0, 'spam', 't_old', edge_old))
conn.commit()
conn.close()
rep = DR.purge_reports_db(14, dry_run=False)
check(rep['tickets'] == 1, f'closed old ticket deleted: {rep}')
check(rep['violations'] == 1, f'old violation deleted: {rep}')
conn = sqlite3.connect('data/reports.db')
left = {r[0] for r in conn.execute('SELECT thread_id FROM tickets').fetchall()}
conn.close()
check(left == {'t_open', 't_new'}, f'open+new remain: {left}')


print('== 4. publish_appeal_menu dead + scan marker ==')
from cogs.appeals import Appeals, MENU_CUSTOM_ID  # noqa: E402

cog = Appeals.__new__(Appeals)
cog.bot = SimpleNamespace(get_channel=lambda cid: None)
cog.db = GuildData('appeals')

# marker detection
class _Emb:
    def __init__(self, title='', description=''):
        self.title = title
        self.description = description


class _Comp:
    def __init__(self, custom_id=''):
        self.custom_id = custom_id
        self.children = []


class _Row:
    def __init__(self, *kids):
        self.children = list(kids)


class _Msg:
    def __init__(self, title=None, custom_id=None, author_id=1, webhook_id=None):
        self.embeds = [_Emb(title=title)] if title else []
        self.components = [_Row(_Comp(custom_id))] if custom_id else []
        self.author = SimpleNamespace(id=author_id, bot=True)
        self.webhook_id = webhook_id
        self.guild = SimpleNamespace(me=SimpleNamespace(id=author_id))
        self.deleted = False

    async def delete(self):
        self.deleted = True


m1 = _Msg(title='⚖ Апелляции на наказания', author_id=99)
check(Appeals._msg_looks_like_appeal_menu(m1), 'title marker detected')
m2 = _Msg(custom_id=MENU_CUSTOM_ID, author_id=99)
check(Appeals._msg_looks_like_appeal_menu(m2), 'custom_id marker detected')
m3 = _Msg(title='Апелляция #12 — новая', author_id=99)
check(not Appeals._msg_looks_like_appeal_menu(m3), 'обычная карточка не меню')

ok, info = _run(cog.publish_appeal_menu(
    SimpleNamespace(id=1, guild=SimpleNamespace(id=GID, get_channel=lambda c: None))))
check(ok is False and 'ЛС' in info, f'publish отказал: {info}')


print('== 5. run_retention summary ==')
# seed temp_history + audit
os.makedirs('data', exist_ok=True)
with open('data/temp_history.json', 'w', encoding='utf-8') as f:
    json.dump([
        {'ts': time.time() - 40 * 86400, 'action': 'mute', 'guild_id': str(GID)},
        {'ts': time.time() - 2 * 86400, 'action': 'mute', 'guild_id': str(GID)},
    ], f)
with open('data/audit_log.json', 'w', encoding='utf-8') as f:
    json.dump({
        str(GID): [
            {'action': 'Мут', 'timestamp': (NOW - timedelta(days=40)).isoformat()},
            {'action': 'Бан', 'timestamp': (NOW - timedelta(days=1)).isoformat()},
        ]
    }, f)
full = DR.run_retention(dry_run=False)
check(full['days'] == 14, f'days=14 got {full["days"]}')
check(full['parts']['temp_history']['removed'] == 1, 'temp_history purged')
check(full['parts']['audit_log']['removed'] == 1, 'audit_log purged')


print('== 6. no yellow title publish left in source ==')
src = open(os.path.join(ROOT, 'cogs', 'appeals.py'), encoding='utf-8').read()
# title string may remain only as detection marker / comments, not as Embed(title=)
import re
embeds = re.findall(r"Embed\(\s*title\s*=\s*['\"][^'\"]*Апелляции на наказания", src)
check(len(embeds) == 0, 'нет Embed(title=…Апелляции на наказания)')
check('_ensure_appeal_menu' in src and '_purge_appeal_menu' in src,
      'ensure → purge path exists')
check('run_retention' in src, 'retention wired in appeals cog')
check('Garbage collect + reload heaviest cog' not in open(
    os.path.join(ROOT, 'cogs', 'diagnostics.py'), encoding='utf-8').read(),
      'старый текст reload heaviest мёртв')


print()
print(f'Result: {PASS} passed, {FAIL} failed')
sys.exit(0 if FAIL == 0 else 1)
