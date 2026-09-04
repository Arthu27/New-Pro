# -*- coding: utf-8 -*-
"""Кнопка «Открыть разбор» на карточке /report: ветка создаётся честно.

Жалоба владельца 2026-09-05: модератор жмёт «Открыть разбор» — бот отвечает
«Не удалось создать ветку: 403 Forbidden (error code: 50001): Missing Access».
Причина: у бота нет права «Создавать публичные ветки» в канале репортов.
Теперь бот заранее проверяет своё право и говорит, ЧТО выдать, а при
Forbidden показывает то же человеческое сообщение (не сырой 403).
Запуск: python3 tests/test_report_thread_perms.py
"""
import asyncio
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(tempfile.mkdtemp(prefix='rep_th_'))
os.makedirs('data', exist_ok=True)
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


import discord  # noqa: E402
from cogs import reports as R  # noqa: E402
from services import reports_core as RC  # noqa: E402


def perms(**kw):
    base = dict(administrator=False, create_public_threads=True,
                manage_threads=False, manage_messages=True,
                send_messages=True, view_channel=True)
    base.update(kw)
    return types.SimpleNamespace(**base)


class _Thread:
    def __init__(self, tid):
        self.id = tid
        self.mention = f'<#{tid}>'
        self.sent = []
        self.users = []

    async def add_user(self, m):
        self.users.append(m)

    async def send(self, content=None, view=None, **kw):
        self.sent.append((content, view))


class _Msg:
    def __init__(self, mid, fail=False):
        self.id = mid
        self.fail = fail
        self.threads = []

    async def create_thread(self, **kw):
        if self.fail:
            raise discord.Forbidden(
                types.SimpleNamespace(status=403, reason='Missing Access'),
                '403 Forbidden (error code: 50001): Missing Access')
        t = _Thread(424242)
        self.threads.append(t)
        return t


class _Forbidden(discord.ClientException):
    """Заглушка: discord.Forbidden требует response — эмулируем 403."""

    def __init__(self):
        super().__init__('403 Forbidden (error code: 50001): Missing Access')




class _Resp:
    def __init__(self):
        self.calls = []

    async def send_message(self, *a, **kw):
        self.calls.append(('send_message', a, kw))

    async def edit_message(self, *a, **kw):
        self.calls.append(('edit_message', a, kw))

    async def defer(self, *a, **kw):
        self.calls.append(('defer', a, kw))


class _Follow:
    def __init__(self):
        self.calls = []

    async def send(self, msg=None, **kw):
        self.calls.append(msg)


class _Me:
    pass


class _Channel:
    def __init__(self, p):
        self._p = p

    def permissions_for(self, member):
        return self._p


class _Guild:
    def __init__(self, me, members=None):
        self.me = me
        self._members = members or {}

    def get_member(self, uid):
        return self._members.get(int(uid))

    async def fetch_member(self, uid):
        m = self._members.get(int(uid))
        if m is None:
            raise _Forbidden()
        return m


class _User:
    def __init__(self, uid, name, mod=False):
        self.id = uid
        self.name = name
        self.mention = f'<@{uid}>'
        self.bot = False
        self.display_name = name
        self.guild_permissions = perms(create_public_threads=mod,
                                       manage_messages=mod)
        self.roles = []


def make_interaction(channel_perms, msg, members=None):
    me = _Me()
    return types.SimpleNamespace(
        guild=_Guild(me, members), guild_id=1484574976580391004,
        user=_User(200, 'Модератор', mod=True),
        channel=_Channel(channel_perms), message=msg,
        response=_Resp(), followup=_Follow())


async def main():
    # Честная запись вызова в бумагах (для _card_state)
    RC.ticket_create(1484574976580391004, 777001, '111', '222',
                     kind='card')

    view = R.ReportCardView()

    print('== 1. Права на ветки ЕСТЬ → ветка создаётся ==')
    mod = _User(200, 'Модератор', mod=True)
    rep_u, acc_u = _User(111, 'Жаловавшийся'), _User(222, 'Обвинённый')
    inter = make_interaction(perms(), _Msg(777001), {111: rep_u, 222: acc_u})
    await R.ReportCardView.open_thread(view, inter, view.open_thread)
    msg = inter.message
    check(len(msg.threads) == 1, 'ветка разбора создана')
    check(len(msg.threads[0].sent) == 1,
          'в ветку отправлена панель модерации')
    check(len(inter.followup.calls) == 1 and 'создана' in inter.followup.calls[0],
          'модератору подтверждение со ссылкой на ветку')
    check(set(msg.threads[0].users) == {rep_u, acc_u},
          'жаловавшийся и обвинённый добавлены в ветку')
    check(RC.ticket_get(777001) is None
          and (RC.ticket_get(424242) or {}).get('reporter_id') == '111',
          'тикет переозначен: панель в ветке найдёт его по ID ветки')

    print('== 2. Права НЕ выданы → честное указание, что включить ==')
    inter2 = make_interaction(perms(create_public_threads=False), _Msg(777002))
    await R.ReportCardView.open_thread(view, inter2, view.open_thread)
    got = inter2.followup.calls[0] if inter2.followup.calls else ''
    check('Создавать публичные ветки' in got and 'Права доступа' in got,
          'бот говорит: включи «Создавать публичные ветки» в правах канала')
    check('error code' not in got and '403' not in got,
          'никаких сырых «403 Forbidden (error code: 50001)»')
    check(len(inter2.message.threads) == 0, 'ветка не пыталась создаться')

    print('== 3. Права проверены, но Discord всё равно 403 → то же сообщение ==')
    m3 = _Msg(777003, fail=True)
    inter3 = make_interaction(perms(), m3)
    # подменяем Forbidden, который бросит фейк, на клиентское исключение:
    await R.ReportCardView.open_thread(view, inter3, view.open_thread)
    got3 = inter3.followup.calls[0] if inter3.followup.calls else ''
    check('Создавать публичные ветки' in got3,
          'при Forbidden — человеческая подсказка, не «Не удалось создать ветку»')

    print('== 4. Неожиданная ошибка → прежний честный текст с деталью ==')
    class _Boom(_Msg):
        async def create_thread(self, **kw):
            raise ValueError('ветки выключены на сервере')
    inter4 = make_interaction(perms(), _Boom(777004))
    await R.ReportCardView.open_thread(view, inter4, view.open_thread)
    got4 = inter4.followup.calls[0] if inter4.followup.calls else ''
    check('Не удалось создать ветку' in got4 and 'ветки выключены' in got4,
          'иные ошибки показываются с причиной (диагностика не потеряна)')

    print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
