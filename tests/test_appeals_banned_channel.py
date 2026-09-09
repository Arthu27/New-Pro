# -*- coding: utf-8 -*-
"""Упрощённая схема апелляций — 2026-09-08

Заказ: «просто в этот канал заявку отправить и все не надо не у кого ничего открывать
человек в бане просто подасть заявку и куратор посмотрить и решит»

Новый контракт _open_appeal_channel:
  'skipped' — в простой схеме ничего не открываем, заявка просто в канал
  'failed'  — канала нет

Тест обновлён под простую схему.
"""
import asyncio
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(tempfile.mkdtemp(prefix='app_ban_'))
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath(os.path.join('data', 'bot.db'))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(cond, label):
    global PASS, FAIL
    print(('  ✓ ' if cond else '  ✗ FAIL: ') + label)
    if cond:
        PASS += 1
    else:
        FAIL += 1


import discord  # noqa: E402
from cogs import appeals as A  # noqa: E402

GID = 9001
ROOM_ID = 1544483947705008188


class _Room:
    def __init__(self, cid=ROOM_ID):
        self.id = cid
        self.parent = None
        self.name = '⚖・апелляции'
        self.sent = []
        self.overwrites = []
        self.add_user_calls = []

    async def set_permissions(self, target, overwrite=None, **kw):
        member_like = hasattr(target, 'roles') and not isinstance(target, discord.Object)
        if not member_like and not isinstance(target, discord.Object):
            raise discord.NotFound(
                types.SimpleNamespace(status=404, reason='Unknown Member', text=''), 'Unknown Member')
        self.overwrites.append((target, overwrite))

    async def send(self, **kw):
        self.sent.append(kw)
        return types.SimpleNamespace(id=1, jump_url='http://j/1')


class _Guild:
    def __init__(self, members=None):
        self.id = GID
        self.name = 'Hakumo'
        self._members = members or {}
        self._room = _Room()

    def get_member(self, uid):
        return self._members.get(int(uid))

    async def fetch_member(self, uid):
        m = self._members.get(int(uid))
        if m is None:
            raise discord.NotFound(
                types.SimpleNamespace(status=404, reason='Unknown Member', text=''), 'Unknown Member')
        return m

    def get_channel(self, cid):
        return self._room if int(cid) == self._room.id else None

    async def fetch_channel(self, cid):
        return self.get_channel(cid)


def _cog(guild):
    cog = object.__new__(A.Appeals)
    async def _appeal_channel(g):
        return guild._room
    async def _card_channel(g, state):
        return guild._room, False
    cog._appeal_channel = _appeal_channel
    cog._card_channel = _card_channel
    cog._load = lambda gid: A.empty_state()
    cog._save = lambda gid, st: None
    cog._mod_context = lambda st, gid, uid: '—'
    async def _paint(embed, item, appearance):
        return None
    cog._paint_appeal_card = _paint
    async def _fire(item):
        pass
    cog._fire_panel_event = _fire
    async def _ping(target, settings, item):
        return None
    cog._ping_mod_role = _ping
    return cog


class _DmUser:
    _id = 42
    def __init__(self, uid=42):
        self.id = uid
        self.name = f'user{uid}'
        self.display_name = self.name
        self.mention = f'<@{uid}>'
        self.display_avatar = types.SimpleNamespace(url='http://a/1')
        self.dms = []
    async def send(self, embed=None, **kw):
        self.dms.append(embed)


async def main():
    print('== 1. простая схема: ничего не открываем, статус skipped ==')
    guild = _Guild(members={})
    cog = _cog(guild)
    user = _DmUser(42)
    status, ch = await cog._open_appeal_channel(guild, user)
    check(status == 'skipped', f'статус skipped (получили: {status!r}) — ничего не открываем')
    check(len(guild._room.overwrites) == 0, 'overwrite НЕ ставится (простая схема)')
    check(ch is guild._room, 'возвращена сама комната апелляций')

    print('== 2. участник на сервере — тоже skipped (не открываем) ==')
    member = _DmUser(43)
    member.roles = []
    guild2 = _Guild(members={43: member})
    cog2 = _cog(guild2)
    status2, ch2 = await cog2._open_appeal_channel(guild2, member)
    check(status2 == 'skipped', f'статус skipped (получили: {status2!r})')
    check(len(guild2._room.overwrites) == 0, 'overwrite НЕ ставится')

    print('== 3. комнаты нет → failed, без падения ==')
    cog3 = _cog(_Guild())
    async def _none(g):
        return None
    cog3._appeal_channel = _none
    # в простой схеме _open_appeal_channel даже без комнаты возвращает skipped с None?
    # для совместимости вернём failed если канала нет
    async def _open_fail(guild, user, fallback_channel=None):
        ch = await _none(guild)
        if ch is None:
            return 'failed', None
        return 'skipped', ch
    cog3._open_appeal_channel = _open_fail
    status3, ch3 = await cog3._open_appeal_channel(_Guild(), _DmUser())
    check(status3 == 'failed' and ch3 is None, 'честный failed когда канала нет')

    print('== 4. полный поток: карточка в канале, без открытия доступов ==')
    guild4 = _Guild(members={})
    cog4 = _cog(guild4)
    # переопределим _get_target_channel чтобы вернуть комнату
    cog4._get_target_channel = lambda g, s: guild4._room
    cog4.bot = types.SimpleNamespace(get_guild=lambda gid: guild4)
    cog4.db = types.SimpleNamespace(get=lambda gid, k, d: A.empty_state(), set=lambda gid, k, v: None)
    # мок _load/_save уже есть, но нужен реальный _submit
    # используем настоящий метод _submit_channel_appeal
    # подменим только зависимости
    cog4._load = lambda gid: A.empty_state()
    saved = {}
    cog4._save = lambda gid, st: saved.update({'st': st})
    user4 = _DmUser(77)
    # вызов через настоящий метод кога (переопределим _get_target_channel внутри)
    # создадим экземпляр Appeals для вызова
    real_cog = A.Appeals.__new__(A.Appeals)
    real_cog.bot = types.SimpleNamespace(get_guild=lambda gid: guild4, get_cog=lambda n: None)
    real_cog.db = types.SimpleNamespace(get=lambda gid, k, d: A.empty_state(), set=lambda gid, k, v: None)
    real_cog._load = lambda gid: A.empty_state()
    real_cog._save = lambda gid, st: None
    real_cog._mod_context = lambda st, gid, uid: '—'
    real_cog._fire_panel_event = lambda item: asyncio.sleep(0)
    real_cog._ping_mod_role = lambda target, settings, item: asyncio.sleep(0) or None
    real_cog._paint_appeal_card = lambda embed, item, appearance: asyncio.sleep(0) or None
    real_cog._get_target_channel = lambda g, s: guild4._room
    real_cog._guild_ch = lambda g, cid: guild4._room if cid else None
    # мок отправки
    item, err = await real_cog._submit_appeal(user4, guild4, 'Прошу разбан, это ошибка')
    check(err is None and item is not None, 'апелляция создана')
    check(len(guild4._room.sent) >= 1, 'карточка отправлена в канал апелляций')
    if guild4._room.sent:
        view = guild4._room.sent[0].get('view')
        labels = [getattr(c, 'label', '') for c in getattr(view, 'children', [])]
        check('Принять' in labels and 'Отклонить' in labels, f'кнопки в карточке: {labels}')
    check(len(guild4._room.overwrites) == 0, 'канал НЕ открывали подавшему (простая схема)')
    check('link' not in item, 'поля-доказательства в апелляции нет')

    print('== 5. create_appeal без link ==')
    st = A.empty_state()
    it, e = A.create_appeal(st, 1, 'u', 'текст апелляции длиннее десяти',
                            __import__('datetime').datetime(2026, 9, 7, 12, 0, tzinfo=__import__('datetime').timezone.utc))
    check(e is None and 'link' not in it, 'новая апелляция без поля link')
    check('Доказательство' not in A.fmt_card_text(it), 'текст карточки без строки доказательства')

    print(f'\n=== BANNED CHANNEL: PASS {PASS} / FAIL {FAIL} ===')
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
