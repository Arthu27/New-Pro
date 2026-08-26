# -*- coding: utf-8 -*-
"""Тесты тихого мута (ghost mute): cogs/mod_plus.py + панель /api/ghost.

Запуск: python3 tests/test_ghost_mute.py
"""
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

# временная рабочая директория — data/* не мусорит в репо
_TMP = tempfile.mkdtemp(prefix='hakumo_ghost_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord

from cogs.mod_plus import (ModPlus, _ghost_path, _sticky_path, _save_json,
                           ghost_add, ghost_remove, ghost_entries, ghost_entry_active,
                           parse_ghost_duration, GHOST_LOG_INTERVAL)

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


# ─── фейки ─────────────────────────────────────────────────────────────
class FakeAvatar:
    url = 'http://x/av.png'


class FakePerms:
    def __init__(self, manage_messages=False):
        self.manage_messages = manage_messages


class FakeUser:
    def __init__(self, uid, name, bot=False, manage_messages=False):
        self.id = uid
        self.display_name = name
        self.name = name
        self.bot = bot
        self.mention = f'<@{uid}>'
        self.display_avatar = FakeAvatar()
        self.guild_permissions = FakePerms(manage_messages)

    def __str__(self):
        return f'{self.name}#{self.id % 10000:04d}'


class FakeMessage:
    _next = 7000

    def __init__(self, content='', author=None, channel=None, guild=None,
                 attachments=(), fail_delete=False):
        FakeMessage._next += 1
        self.id = FakeMessage._next
        self.content = content
        self.author = author
        self.channel = channel
        self.guild = guild
        self.attachments = list(attachments)
        self.deleted = False
        self._fail_delete = fail_delete

    async def delete(self):
        if self._fail_delete:
            class _R:  # минимальный HTTP-response для discord.Forbidden
                status = 403
                reason = 'Forbidden'
            raise discord.Forbidden(_R(), 'no perms')
        self.deleted = True


class FakeTextChannel:
    def __init__(self, cid, name, guild=None):
        self.id = cid
        self.name = name
        self.mention = f'<#{cid}>'
        self.guild = guild
        self.sent = []

    async def send(self, content=None, embed=None, **kw):
        self.sent.append((content, embed, kw))
        return None


class FakeGuild:
    def __init__(self):
        self.id = 777
        self.name = 'GhostHall'
        self.owner_id = 9999
        self.text_channels = [FakeTextChannel(200, 'общий', self)]
        self.members = {}

    def get_member(self, uid):
        return self.members.get(uid)


class FakeResp:
    def __init__(self):
        self.sent = []

    async def send_message(self, content=None, embed=None, ephemeral=False):
        self.sent.append((content, embed))

    async def send(self, content=None, embed=None, ephemeral=False):
        self.sent.append((content, embed))

    async def defer(self, ephemeral=False):
        pass


class FakeInter:
    def __init__(self, guild, user, channel=None):
        self.guild = guild
        self.user = user
        self.channel = channel or (guild.text_channels[0] if guild else None)
        self.response = FakeResp()
        self.followup = FakeResp()


GUILD = FakeGuild()
CH = GUILD.text_channels[0]
MOD = FakeUser(5001, 'Mod', manage_messages=True)
GHOST = FakeUser(5050, 'Spammer')
OWNER = FakeUser(9999, 'Boss')
BOTUSER = FakeUser(5051, 'Robo', bot=True)
for m in (MOD, GHOST, OWNER, BOTUSER):
    GUILD.members[m.id] = m

# ═══ 1. МОДУЛЬНЫЕ ХЕЛПЕРЫ ════════════════════════════════════════════════
print('== модуль: ghost_add / ghost_entries / ghost_remove ==')
check(ghost_entries(GUILD.id) == {}, 'изначально призраков нет')

future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
e = ghost_add(GUILD.id, GHOST.id, 'флудил', by='Mod#5001', until=future)
check(e['reason'] == 'флудил' and e['until'] == future and e['suppressed'] == 0,
      'ghost_add: запись с причиной, сроком и счётчиком')
check(os.path.isfile(_ghost_path(GUILD.id)), 'ghost_add: json на диске')
check(str(GHOST.id) in ghost_entries(GUILD.id), 'ghost_entries видит призрака')

check(ghost_entry_active({'until': None}) is True, 'active: until=None → бессрочно активен')
check(ghost_entry_active({'until': future}) is True, 'active: срок впереди → активен')
past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
check(ghost_entry_active({'until': past}) is False, 'active: срок позади → истёк')
check(ghost_entry_active({'until': 'мусор'}) is True, 'active: кривая дата → на всякий случай активен')

# ленивая чистка истёкших
ghost_add(GUILD.id, 6060, 'старый', by='x', until=past)
data = ghost_entries(GUILD.id)
check('6060' not in data and str(GHOST.id) in data,
      'ghost_entries: истёкшие снимаются лениво, живые остаются')

rem = ghost_remove(GUILD.id, GHOST.id)
check(rem is not None and rem['reason'] == 'флудил', 'ghost_remove: вернул запись')
check(ghost_remove(GUILD.id, GHOST.id) is None, 'ghost_remove: повторно — None')
check(str(GHOST.id) not in ghost_entries(GUILD.id), 'ghost_remove: записи больше нет')

print('== модуль: parse_ghost_duration ==')
check(parse_ghost_duration('30м')[0] == 1800, '30м = 1800 сек')
check(parse_ghost_duration('2ч')[0] == 7200, '2ч = 7200 сек')
check(parse_ghost_duration('1д 12ч')[0] == 129600, '1д 12ч = 129600 сек')
check(parse_ghost_duration('')[0] is None and parse_ghost_duration('')[1] is None,
      'пусто = бессрочно без ошибки')
check(parse_ghost_duration('abra')[1] is not None, 'мусор → понятная ошибка')
check(parse_ghost_duration('200д')[1] is not None, '200 дней → зажато лимитом')

# ═══ 2. СЛУШАТЕЛЬ on_message ═════════════════════════════════════════════
print('== слушатель: призрак/обычный/истёкший ==')
from cogs import logs as _logs_mod  # noqa: E402

log_channel = FakeTextChannel(201, 'мод-лог', GUILD)
_safe_calls = []


async def fake_ensure(guild, category='сервер'):
    return log_channel


async def fake_safe_send(ch, **kw):
    _safe_calls.append((ch, kw))
    return True


_logs_mod.ensure_log_channel = fake_ensure
_logs_mod._safe_send = fake_safe_send


class FakeBot:
    guilds = [GUILD]

    def get_cog(self, name):
        return None

    def get_guild(self, gid):
        return GUILD if gid == GUILD.id else None


cog = ModPlus(FakeBot())

msg = FakeMessage('куплю гифт дёшево', author=GHOST, channel=CH, guild=GUILD)
run(cog.on_message(msg))
check(msg.deleted is False, 'обычный участник: сообщение НЕ тронуто')

ghost_add(GUILD.id, GHOST.id, 'тест-слушатель', by='tests')
msg2 = FakeMessage('всем привет, я спамер', author=GHOST, channel=CH, guild=GUILD)
run(cog.on_message(msg2))
check(msg2.deleted is True, 'призрак: сообщение мгновенно удалено')
check(len(_safe_calls) == 1, 'призрак: мод-лог получил отчёт с карточкой')

msg3 = FakeMessage('меня кто-нибудь читает??', author=GHOST, channel=CH, guild=GUILD)
run(cog.on_message(msg3))
check(msg3.deleted is True, 'призрак: второе сообщение тоже удалено')
check(len(_safe_calls) == 1, 'но мод-лог НЕ заспамлен — троттлинг интервала')

cnt = json.load(open(_ghost_path(GUILD.id), encoding='utf-8'))[str(GHOST.id)]['suppressed']
check(cnt == 1, 'счётчик подавленных на диске (порциями: 1-е сохранили)')
msg4 = FakeMessage('ещё сообщение', author=GHOST, channel=CH, guild=GUILD)
run(cog.on_message(msg4))
check(json.load(open(_ghost_path(GUILD.id), encoding='utf-8'))[str(GHOST.id)]['suppressed'] == 1,
      'счётчик в файле порциями — не переписываем на каждое сообщение')

# форс-time: сбрасываем троттлинг — следующий отчёт пройдёт и покажет суммарное число
cog._ghost_last_log[(GUILD.id, GHOST.id)] = 0
msg5 = FakeMessage('пятый', author=GHOST, channel=CH, guild=GUILD)
run(cog.on_message(msg5))
check(len(_safe_calls) == 2, 'после интервала новый отчёт в мод-лог')

# боты — под защитой
msg_bot = FakeMessage('я легальный бот', author=BOTUSER, channel=CH, guild=GUILD)
run(cog.on_message(msg_bot))
check(msg_bot.deleted is False, 'ботов слушатель не трогает')

# истёкший срок — ленивый авто-съём, сообщение проходит
ghost_add(GUILD.id, GHOST.id, 'просрочился', by='tests', until=past)
msg6 = FakeMessage('я снова видимый!', author=GHOST, channel=CH, guild=GUILD)
run(cog.on_message(msg6))
check(msg6.deleted is False, 'срок вышел: сообщение пропущено')
check(str(GHOST.id) not in ghost_entries(GUILD.id), 'срок вышел: ленивый авто-съём из списка')

# нет прав на удаление — слушатель не падает и не спамит варнингами
ghost_add(GUILD.id, GHOST.id, 'через тесты', by='tests')
bad = FakeMessage('опа', author=GHOST, channel=CH, guild=GUILD, fail_delete=True)
run(cog.on_message(bad))
warns = len(cog._ghost_perm_warn)
bad2 = FakeMessage('опа2', author=GHOST, channel=CH, guild=GUILD, fail_delete=True)
run(cog.on_message(bad2))
check(warns == 1 and len(cog._ghost_perm_warn) == 1, 'нет прав → один варнинг, без падения')

# липкое на сообщение призрака не реагирует
_save_json(_sticky_path(GUILD.id), {str(CH.id): {'text': 'Правила!', 'msg_id': None,
                                                 'author_id': 1, 'set_at': 'x'}})
ch_sent_before = len(CH.sent)
msg7 = FakeMessage('призрачный флуд', author=GHOST, channel=CH, guild=GUILD)
run(cog.on_message(msg7))
check(msg7.deleted is True and len(CH.sent) == ch_sent_before,
      'призрак поглощён ДО липкого: репоста в ответ нет')
os.remove(_sticky_path(GUILD.id))

# ═══ 3. КОМАНДЫ ═══════════════════════════════════════════════════════════
print('== /ghostmute /ghostunmute /ghostlist ==')
ghost_remove(GUILD.id, GHOST.id)
cog._notify_mod_log = lambda *a, **k: None  # в командах свой лог — заглушка


async def _noop_notify(self, guild, embed):
    return None


cog._notify_mod_log = _noop_notify.__get__(cog, ModPlus)

inter = FakeInter(GUILD, MOD)
run(ModPlus.ghostmute.callback(cog, inter, user=GHOST, duration=None, reason='тестись'))
d = json.load(open(_ghost_path(GUILD.id), encoding='utf-8'))
check(str(GHOST.id) in d and d[str(GHOST.id)]['until'] is None,
      'ghostmute: бессрочный записан')
check(inter.response.sent and inter.response.sent[-1][1] is not None,
      'ghostmute: эмбед-подтверждение')

inter2 = FakeInter(GUILD, MOD)
run(ModPlus.ghostmute.callback(cog, inter2, user=GHOST, duration='2ч', reason='повтор'))
d = json.load(open(_ghost_path(GUILD.id), encoding='utf-8'))
check(d[str(GHOST.id)]['until'] is not None, 'ghostmute: срок из «2ч» записан')

inter3 = FakeInter(GUILD, MOD)
run(ModPlus.ghostmute.callback(cog, inter3, user=GHOST, duration='мусор'))
check('не понял' in (inter3.response.sent[-1][0] or '').lower()
      or '⚠️' in (inter3.response.sent[-1][0] or ''),
      'ghostmute: кривое время → внятная ошибка, запись не тронута')

inter4 = FakeInter(GUILD, MOD)
run(ModPlus.ghostmute.callback(cog, inter4, user=BOTUSER))
check('бот' in (inter4.response.sent[-1][0] or '').lower(), 'ghostmute: бота нельзя')

inter5 = FakeInter(GUILD, GHOST)
run(ModPlus.ghostmute.callback(cog, inter5, user=GHOST))
check('себя' in (inter5.response.sent[-1][0] or '').lower(), 'ghostmute: себя нельзя')

inter6 = FakeInter(GUILD, MOD)
run(ModPlus.ghostmute.callback(cog, inter6, user=OWNER))
check('владел' in (inter6.response.sent[-1][0] or '').lower(), 'ghostmute: владельца нельзя')

inter7 = FakeInter(GUILD, GHOST)  # цель — MOD, вызывающий — обычный юзер (иначе отказ «себя»)
run(ModPlus.ghostmute.callback(cog, inter7, user=MOD))
check('модератор' in (inter7.response.sent[-1][0] or '').lower(), 'ghostmute: модера нельзя')

# unmute
inter8 = FakeInter(GUILD, MOD)
run(ModPlus.ghostunmute.callback(cog, inter8, user=GHOST))
check(str(GHOST.id) not in json.load(open(_ghost_path(GUILD.id), encoding='utf-8')),
      'ghostunmute: запись снята')
check(inter8.response.sent[-1][1] is not None, 'ghostunmute: эмбед-подтверждение')

inter9 = FakeInter(GUILD, MOD)
run(ModPlus.ghostunmute.callback(cog, inter9, user=GHOST))
check('не был' in (inter9.response.sent[-1][0] or '').lower(),
      'ghostunmute: повторно — аккуратный отказ')

# ghostlist
ghost_add(GUILD.id, GHOST.id, 'в списке', by='tests', until=future)
inter10 = FakeInter(GUILD, MOD)
run(ModPlus.ghostlist.callback(cog, inter10))
emb = inter10.response.sent[-1][1]
check(emb.description and 'Spammer' in emb.description and 'до ' in emb.description,
      'ghostlist: показывает призрака со сроком')
ghost_add(GUILD.id, 6061, 'ушёл с сервера', by='tests')  # этого ID нет в members
inter11 = FakeInter(GUILD, MOD)
run(ModPlus.ghostlist.callback(cog, inter11))
check('ID `6061`' in (inter11.response.sent[-1][1].description or ''),
      'ghostlist: ушедший с сервера показан по ID')

# ═══ 4. ПАНЕЛЬ ════════════════════════════════════════════════════════════
print('== панель: /api/ghost ==')
from web.app import app as _flask_app, set_bot_instance  # noqa: E402
set_bot_instance(FakeBot())
client = _flask_app.test_client()


def login_as(role):
    # discord_id специально НЕ ставим: login_required перечитывал бы роль
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'PanelGhost'
        s['role'] = role


r = client.get('/api/ghost')
check(r.status_code in (302, 401, 403), f'API без логина закрыто ({r.status_code})')

login_as('uye')
r = client.get('/api/ghost')
check(r.status_code == 403, f'uye не пускают ({r.status_code})')

login_as('mod')
r = client.get('/api/ghost')
d = r.get_json()
check(r.status_code == 200 and d.get('success') is True, 'mod: список отдаётся')
names = [i['name'] for i in d['items']]
check(any('Spammer' in n for n in names), 'mod: в списке наш призрак с именем')

r = client.post('/api/ghost', json={'user_id': 'не-id'})
check(r.status_code == 400, 'POST: мусорный ID → 400')
r = client.post('/api/ghost', json={'user_id': '424242'})
check(r.status_code == 404, 'POST: нет на сервере → 404')
r = client.post('/api/ghost', json={'user_id': str(BOTUSER.id)})
check(r.status_code == 400, 'POST: бота → 400')
r = client.post('/api/ghost', json={'user_id': str(OWNER.id)})
check(r.status_code == 400, 'POST: владельца → 400')
r = client.post('/api/ghost', json={'user_id': str(MOD.id)})
check(r.status_code == 400, 'POST: модератора → 400')
r = client.post('/api/ghost', json={'user_id': str(GHOST.id), 'duration': 'абракадабра'})
check(r.status_code == 400, 'POST: кривая длительность → 400')

r = client.post('/api/ghost', json={'user_id': str(GHOST.id), 'duration': '30м',
                                    'reason': 'панельный тест'})
d = r.get_json()
check(d.get('success') is True, 'POST: призрак создан из панели')
rec = json.load(open(_ghost_path(GUILD.id), encoding='utf-8'))[str(GHOST.id)]
check(rec['by'] == 'панель:PanelGhost' and rec['until'] is not None,
      'POST: записаны автор-панель и срок')

r = client.delete('/api/ghost', json={'user_id': 'не-id'})
check(r.status_code == 400, 'DELETE: мусор → 400')
r = client.delete('/api/ghost', json={'user_id': str(OWNER.id)})
check(r.status_code == 404, 'DELETE: не-призрак → 404')
r = client.delete('/api/ghost', json={'user_id': str(GHOST.id)})
d = r.get_json()
check(d.get('success') is True and 'suppressed' in d, 'DELETE: снят, отдали счётчик')
check(str(GHOST.id) not in json.load(open(_ghost_path(GUILD.id), encoding='utf-8')),
      'DELETE: записи нет на диске')

r = client.get('/mod-tools')
page = r.get_data(as_text=True)
check(r.status_code == 200 and 'Тихий мут' in page and '/api/ghost' in page,
      'страница /mod-tools содержит карточку тихого мута')

# ─── финал ───────────────────────────────────────────────────────────────
import shutil  # noqa: E402
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
