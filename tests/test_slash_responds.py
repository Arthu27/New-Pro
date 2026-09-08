# -*- coding: utf-8 -*-
"""Команды должны отвечать: Discord даёт 3 секунды, иначе «приложение не отвечает».

Lag 28с на цикле (HEALTH) закрывал окно. Проверяем:
  1) аудит-синк никогда не тянет limit=None (7 дней = сотни страниц HTTP);
  2) первый проход всё равно забирает свежие 100 записей;
  3) повторный проход останавливается на last_id;
  4) /modpanel сразу делает _ack (defer);
  5) снятие изоляции не обходит все каналы, если есть роль бана;
  6) без роли бана overwrite всё равно снимается.

Запуск: python3 tests/test_slash_responds.py
"""
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_slash_ack_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['MAIN_GUILD_ID'] = '777'

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== 1. Исходники: цикл не должен замирать ==')
logs_src = open(os.path.join(ROOT, 'cogs', 'logs.py'), encoding='utf-8').read()
mod_src = open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read()
appeal_src = open(os.path.join(ROOT, 'cogs', 'appeals.py'), encoding='utf-8').read()
afk_src = open(os.path.join(ROOT, 'cogs', 'afk.py'), encoding='utf-8').read()
rep_src = open(os.path.join(ROOT, 'cogs', 'reports.py'), encoding='utf-8').read()
sync = logs_src[logs_src.index('async def _sync_discord_audit_log'):
                logs_src.index('async def on_ready')]
check('audit_logs (limit =None' not in sync and 'audit_logs(limit=None' not in sync,
      'аудит-синк не зовёт audit_logs(limit=None)')
check('limit =100' in sync or 'limit=100' in sync,
      'аудит-синк берёт не больше 100 свежих записей')
mp = mod_src[mod_src.index('async def modpanel'):
             mod_src.index('def _parse_target_id')]
check('await _ack' in mp and mp.find('await _ack') < mp.find('actions_for_member'),
      '/modpanel сразу закрывает 3с-окно Discord (_ack до меню)')
uni = mod_src[mod_src.index('async def _unisolate_member'):
              mod_src.index('def _preflight_reason') if 'def _preflight_reason' in mod_src
              else mod_src.index('# ── Почему Forbidden')]
check("_punish_role (guild ,'ban')" in uni or "_punish_role(guild, 'ban')" in uni,
      'снятие изоляции пропускается, если роль бана сама закрывала каналы')
check('gather' in uni, 'без роли бана снятие изоляции идёт пачкой, не по одной')
ex = mod_src[mod_src.index('async def _execute_mod_action'):
             mod_src.index('async def _ensure_action_acl')]
check(ex.find('await _ack') < ex.find('save_case'),
      'наказание: _ack до записи дела и ролей')
check(ex.find('embed =confirm') < ex.find('send_action_log'),
      'модератору «готово» уходит до лога/ЛС — иначе Discord уже нарисовал отказ')
msub = mod_src[mod_src.index('class ModActionModal'):
               mod_src.index('class ModHelpButton')]
check('thinking=True' in msub and 'await _ack' in msub,
      'модалка наказания: defer thinking=True (type 5, не «не ответило»)')
csub = mod_src[mod_src.index('class _CtxMuteModal'):
               mod_src.index('def _mod_cog_of')]
check(csub.find('await _ack') < csub.find('apply_panel_action')
      and 'thinking=True' in csub,
      'ПКМ-мут: ack до применения, ответ через _respond')
ap = appeal_src[appeal_src.index('class AppealModal'):
                appeal_src.index('class AppealChannelModal')]
check(ap.find('response.defer') < ap.find('_submit_appeal'),
      'модалка апелляции (кнопка в ЛС): defer до карточки (окно 3с)')
af = afk_src[afk_src.index('async def afk'):
             afk_src.index('async def afk') + 1200]
check(af.find('response .defer') < af.find('user .edit')
      or af.find('response.defer') < af.find('user.edit'),
      '/afk: defer до смены ника')
check('guild.ban(int(' not in rep_src,
      'вердикт бана: не guild.ban(int) — нужен Snowflake')

print('== 2. Аудит-синк: cap + first-run + курсор ==')
import discord  # noqa: E402
from config import Config  # noqa: E402
from cogs.logs import Logs, _audit_queue  # noqa: E402

NOW = datetime.now(timezone.utc)
CALLS = []


class _Entries:
    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        async def gen():
            for r in self._rows:
                yield r
        return gen()


def _entry(eid, hours_ago=1):
    return SimpleNamespace(
        id=eid, action=discord.AuditLogAction.ban, reason='тест',
        created_at=NOW - timedelta(hours=hours_ago),
        target=SimpleNamespace(id=5, name='t', display_name='T'),
        user=SimpleNamespace(id=6, display_name='Mod'),
        changes=SimpleNamespace(after=SimpleNamespace()),
    )


rows = [_entry(30), _entry(20), _entry(10)]


def _audit_logs(**kw):
    CALLS.append(kw)
    return _Entries(rows)


g = SimpleNamespace(id=777, name='G', audit_logs=_audit_logs)
bot = SimpleNamespace(guilds=[g])
cog = Logs(bot)
_prev = Config.MAIN_GUILD_ID
for f in ('data/discord_audit_cache.json', 'data/audit_seen.json', 'data/audit_log.json'):
    if os.path.exists(f):
        os.remove(f)
try:
    Config.MAIN_GUILD_ID = 777
    CALLS.clear()
    asyncio.run(cog._sync_discord_audit_log())
    _audit_queue.join()
    check(CALLS and CALLS[0].get('limit') == 100,
          f'первый проход: limit=100, не None ({CALLS})')
    with open('data/audit_seen.json', encoding='utf-8') as fh:
        seen = json.load(fh)
    check(seen.get('777') == '30', f'курсор = самый свежий id ({seen})')
    with open('data/discord_audit_cache.json', encoding='utf-8') as fh:
        cache = json.load(fh)
    check(len(cache.get('777') or []) == 3,
          f'первый проход забрал все 3 записи ({len((cache.get("777") or []))})')

    CALLS.clear()
    asyncio.run(cog._sync_discord_audit_log())
    check(CALLS and CALLS[0].get('limit') == 100,
          'повтор тоже с limit=100')
    with open('data/discord_audit_cache.json', encoding='utf-8') as fh:
        cache2 = json.load(fh)
    check(len(cache2.get('777') or []) == 3,
          'повтор не дублирует записи старше курсора')
finally:
    Config.MAIN_GUILD_ID = _prev

print('== 3. Кэш дел: запись на диск сразу видна ==')
from cogs import logs as LOGS  # noqa: E402
from datetime import datetime as _dt

g2 = SimpleNamespace(id=777, get_member=lambda mid: None)
os.makedirs('data', exist_ok=True)
LOGS._JSON_FILE_CACHE.clear()
check(LOGS._latest_case(g2, 42, actions=('ban',), window=90) is None,
      'без файла дел — None')
with open('data/mod_data.json', 'w', encoding='utf-8') as fh:
    json.dump({'cases': {'777': [{
        'id': 7, 'action': 'ban', 'user_id': '42',
        'mod_id': 9, 'mod_name': 'sonya', 'reason': 'флуд',
        'timestamp': _dt.now(timezone.utc).isoformat(),
    }]}}, fh)
c = LOGS._latest_case(g2, 42, actions=('ban',), window=90)
check(c is not None and c.get('reason') == 'флуд',
      'после записи файла кэш видит новое дело (mtime)')

print('== 4. Изоляция: роль бана vs обход каналов ==')
from cogs.moderation import Moderation  # noqa: E402


class _Ch:
    def __init__(self, cid):
        self.id = cid
        self.n = 0

    async def set_permissions(self, user, overwrite=None):
        self.n += 1
        self.last = overwrite


class _G:
    id = 777
    channels = None
    threads = []


mod = object.__new__(Moderation)
g3 = _G()
g3.channels = [_Ch(1), _Ch(2), _Ch(3)]
mod._punish_role = lambda guild, kind: SimpleNamespace(id=1, name='ban')
asyncio.run(mod._unisolate_member(g3, object()))
check(all(c.n == 0 for c in g3.channels),
      'роль бана есть — каналы не трогаем')

mod._punish_role = lambda guild, kind: None
g4 = _G()
g4.channels = [_Ch(1), _Ch(2)]
asyncio.run(mod._unisolate_member(g4, object()))
check(all(c.n == 1 and c.last is None for c in g4.channels),
      'роли бана нет — overwrite снимается на всех каналах')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
