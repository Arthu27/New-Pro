# -*- coding: utf-8 -*-
"""/report тегает только модеров — и тег реально прилетает.

Жалоба владельца: команда «отправляет да, но не тегает» (имя роли в чате
без пуша) и попутно зовёт кураторов/админов.

Запуск: python3 tests/test_report_mod_ping.py
"""
import asyncio
import json
import os
import sys
import tempfile
from types import SimpleNamespace as NS

os.environ['DB_PATH'] = os.path.join(tempfile.mkdtemp(prefix='rp_db_'), 'bot.db')
os.chdir(tempfile.mkdtemp(prefix='rp_ws_'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.makedirs('data', exist_ok=True)

from cogs import reports as R  # noqa: E402

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


class Role:
    def __init__(self, rid, name, mentionable=True, members=None, managed=False):
        self.id = rid
        self.name = name
        self.mention = f'<@&{rid}>'
        self.mentionable = mentionable
        self.members = members or []
        self.managed = managed
        self.is_default = lambda: False
        self.edits = []

    async def edit(self, **kw):
        self.edits.append(kw)
        if 'mentionable' in kw:
            self.mentionable = kw['mentionable']


class Member:
    def __init__(self, uid, name, bot=False):
        self.id = uid
        self.name = name
        self.mention = f'<@{uid}>'
        self.bot = bot


class Ch:
    def __init__(self):
        self.sent = []
        self.guild = None

    async def send(self, **kw):
        self.sent.append(dict(kw))
        return NS(id=1)


mod = Role(11, 'Модер')
cur = Role(22, 'Куратор')
adm = Role(33, 'Админ')
guild = NS(id=777, get_role=lambda rid: {11: mod, 22: cur, 33: adm}.get(int(rid)),
           roles=[mod, cur, adm])
json.dump({'mod_role_id': '11'}, open('data/reports_777.json', 'w', encoding='utf-8'))
json.dump({'11': 'mod', '22': 'curator', '33': 'admin'},
          open('data/role_map.json', 'w', encoding='utf-8'))

print('== 1. Только модеры ==')
got = R._mod_ping_roles(guild)
check(got == [mod], 'канон + role_map «mod» → одна роль модераторов',
      f'→ {[r.name for r in got]}')
check(cur not in got and adm not in got, 'куратор и админ не в теге')

print('== 2. role_map curator/admin без канона — тишина, не чужие роли ==')
os.remove('data/reports_777.json')
for p in ('data/ticket_notify_777.json', 'data/ticket_permissions_777.json',
          'data/staff_roles.json'):
    if os.path.exists(p):
        os.remove(p)
json.dump({'22': 'curator', '33': 'admin'},
          open('data/role_map.json', 'w', encoding='utf-8'))
got = R._mod_ping_roles(guild)
check(got == [], 'без роли модераторов никого не тегаем',
      f'→ {[r.name for r in got]}')

print('== 3. Живой тег: mentionable=False → edit + restore ==')
json.dump({'mod_role_id': '11'}, open('data/reports_777.json', 'w', encoding='utf-8'))
json.dump({'11': 'mod'}, open('data/role_map.json', 'w', encoding='utf-8'))
silent = Role(11, 'Модер', mentionable=False)
silent_guild = NS(id=777, me=None,
                  get_role=lambda rid: silent if int(rid) == 11 else None,
                  roles=[silent])
ch = Ch()
ch.guild = silent_guild
asyncio.get_event_loop().run_until_complete(
    R._deliver_mod_ping(ch, [silent], content=silent.mention, embed=NS(title='x')))
check(len(ch.sent) == 1, 'сообщение ушло')
check(any(e.get('mentionable') is True for e in silent.edits)
      and any(e.get('mentionable') is False for e in silent.edits),
      'роль на секунду сделали упоминаемой и вернули',
      f'→ {silent.edits}')
am = ch.sent[0].get('allowed_mentions')
check(am is not None and silent in list(getattr(am, 'roles', []) or []),
      'AllowedMentions указывает именно роль модеров')

print('== 4. Если роль нельзя сделать упоминаемой — тегаем самих модеров ==')
class Locked(Role):
    async def edit(self, **kw):
        raise RuntimeError('нет права')


alice = Member(101, 'Алиса')
bob = Member(102, 'Боб')
botm = Member(103, 'Бот', bot=True)
locked = Locked(11, 'Модер', mentionable=False, members=[alice, bob, botm])
ch2 = Ch()
asyncio.get_event_loop().run_until_complete(
    R._deliver_mod_ping(ch2, [locked], content=locked.mention))
txt = ch2.sent[0].get('content') or ''
check('<@101>' in txt and '<@102>' in txt, 'фолбэк: тег участников-модеров',
      f'→ {txt!r}')
check('<@103>' not in txt, 'ботов не тегаем')
am2 = ch2.sent[0].get('allowed_mentions')
check(alice in list(getattr(am2, 'users', []) or [])
      and bob in list(getattr(am2, 'users', []) or []),
      'AllowedMentions.users — живые модеры, пуш прилетит')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
