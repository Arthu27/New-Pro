# -*- coding: utf-8 -*-
"""Апелляции и тег модераторов в /report — жалобы владельца 2026-09-05.

1) «Бот после апелляции не показывает канал апелляции, нету принять/отклонить»:
   карточка обязана прийти в НАСТРОЕННЫЙ канал апелляций С кнопками
   (Принять/Отклонить/Взять в работу) даже если тред создать не дали
   (нет права «Создавать публичные ветки»); канал апелляции открывается
   подавшему, а ЛС говорит ПРАВДУ о том, открылся ли он.
2) «/report модератора не тегает»: тег ставится даже без настроенной роли —
   каноническая роль → role_map → авто-роли с правами модерации.
Запуск: python3 tests/test_appeals_report_fix.py
"""
import asyncio
import json
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(tempfile.mkdtemp(prefix='app_rep_'))
os.makedirs('data', exist_ok=True)
# изолируем SQLite (GuildData/reports_core): иначе пишем в боевой data/bot.db
os.environ['DB_PATH'] = os.path.abspath(os.path.join('data', 'bot.db'))
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
from cogs import appeals as A  # noqa: E402
from cogs import reports as R  # noqa: E402
from services import channel_routes as CR  # noqa: E402

GID = 1484574976580391004
APPEAL_CH = 1544483947705008188  # настроенный канал апелляций (владелец)


class _Perms:
    def __init__(self, **kw):
        d = dict(administrator=False, ban_members=False,
                 moderate_members=False, manage_messages=False,
                 create_public_threads=False, manage_threads=False,
                 mention_everyone=False)
        d.update(kw)
        self.__dict__.update(d)


class _Role:
    def __init__(self, rid, name, perms=None, managed=False):
        self.id = rid
        self.name = name
        self.managed = managed
        self.mention = f'<@&{rid}>'
        self.permissions = perms or _Perms()
        self.is_default = lambda: rid == 0


class _Overwrite:
    def __init__(self, **kw):
        self.kw = kw


class _Channel:
    def __init__(self, cid, name='апелляции', fail_threads=False):
        self.id = cid
        self.name = name
        self.fail_threads = fail_threads
        self.sent = []
        self.threads = []
        self.overwrites = []

    async def create_thread(self, **kw):
        if self.fail_threads:
            raise discord.Forbidden(
                types.SimpleNamespace(status=403, reason='Missing Access'),
                '403 Forbidden (error code: 50001): Missing Access')
        t = _Channel(900000 + len(self.threads), kw.get('name', ''))
        self.threads.append(t)
        return t

    async def send(self, **kw):
        self.sent.append(kw)
        return types.SimpleNamespace(id=1000 + len(self.sent),
                                     jump_url=f'http://j/{len(self.sent)}')

    async def set_permissions(self, user, overwrite=None, **kw):
        self.overwrites.append((user.id, overwrite))


class _Guild:
    def __init__(self, channels, roles):
        self.id = GID
        self.name = 'Hakumo'
        self._channels = {c.id: c for c in channels}
        self.roles = roles
        self.system_channel = None

    def get_channel(self, cid):
        return self._channels.get(int(cid))

    def get_role(self, rid):
        for r in self.roles:
            if r.id == int(rid):
                return r
        return None


class _User:
    def __init__(self, uid, name):
        self.id = uid
        self.name = name
        self.display_name = name
        self.mention = f'<@{uid}>'
        self.bot = False
        self.display_avatar = types.SimpleNamespace(url='http://a/1')
        self.roles = []
        self.guild_permissions = _Perms()
        self.dms = []

    async def send(self, embed=None, **kw):
        self.dms.append(embed)


class _Bot:
    def __init__(self, guild):
        self._g = guild
        self.guilds = [guild]

    def get_guild(self, gid):
        return self._g if int(gid) == GID else None


def _mk(cog, user, guild):
    """Тихий Interaction-заглушку не строим — зовём приватные методы напрямую."""
    return cog, user, guild


# Маршрут «Канал апелляции (бан)» = настроенный канал (владелец)
CR.set_route(GID, 'ban_appeal_channel', APPEAL_CH)
appeal_ch = _Channel(APPEAL_CH)
mod_role = _Role(7001, 'Модератор', _Perms(ban_members=True))
admin_role = _Role(7002, 'Админ', _Perms(administrator=True))
everyone = _Role(0, '@everyone')
guild = _Guild([appeal_ch], [everyone, mod_role, admin_role])
bot = _Bot(guild)
cog = A.Appeals(bot)

async def main():
    user = _User(555, 'Обвинённый Вася')

    print('== 1. Апелляция из канала: карточка в НАСТРОЕННОМ канале, кнопки есть ==')
    # треды создать не дали (нет «Создавать публичные ветки») — как у владельца
    appeal_ch.fail_threads = True
    item, err = await cog._submit_channel_appeal(user, guild, 'Прошу разбан')
    check(err is None, 'апелляция создана без ошибок', f'→ {err}')
    check(len(appeal_ch.sent) == 1 and not appeal_ch.threads,
          'карточка легла прямо в канал апелляций (тред создать не дали)')
    view = (appeal_ch.sent[0] or {}).get('view')
    ids = [b.custom_id for b in view.children] if view else []
    check(any(str(i).startswith('appeal:accept:') for i in ids)
          and any(str(i).startswith('appeal:reject:') for i in ids)
          and any(str(i).startswith('appeal:claim:') for i in ids),
          'на карточке есть Принять / Отклонить / Взять в работу', f'→ {ids}')
    check(item.get('message_id'), 'запись апелляции знает ID карточки')
    check(len(appeal_ch.overwrites) == 1
          and appeal_ch.overwrites[0][0] == 555,
          'канал апелляции ОТКРЫТ подавшему после подачи')

    print('== 2. Треды разрешены → карточка в треде настроенного канала ==')
    appeal_ch2 = _Channel(APPEAL_CH)
    guild2 = _Guild([appeal_ch2], [everyone, mod_role])
    cog2 = A.Appeals(_Bot(guild2))
    item2, err2 = await cog2._submit_channel_appeal(
        _User(556, 'Петя'), guild2, 'Верните доступ')
    check(err2 is None and len(appeal_ch2.threads) == 1,
          'тред в настроенном канале создан')
    t0 = appeal_ch2.threads[0]
    check(len(t0.sent) == 1 and t0.sent[0].get('view') is not None,
          'кнопки есть и в треде')

    print('== 3. ЛС подавшему говорит ПРАВДУ про канал ==')
    class _DmUser(_User):
        def __init__(self):
            super().__init__(557, 'Сява')
            self.dms = []

        async def send(self, embed=None, **kw):
            self.dms.append(embed)
    du = _DmUser()
    appeal_ch3 = _Channel(APPEAL_CH, fail_threads=True)
    guild3 = _Guild([appeal_ch3], [everyone, mod_role])
    cog3 = A.Appeals(_Bot(guild3))
    await cog3._submit_channel_appeal(du, guild3, 'Прошу разбан, всё было не так')
    check(len(du.dms) == 1 and 'открыт для вас' in (du.dms[0].description or ''),
          'канал открылся — ЛС говорит «открыт»')
    # а теперь канал.route снят → открыть не удалось → честный текст
    CR.set_route(GID, 'ban_appeal_channel', 0)
    du2 = _DmUser()
    appeal_ch4 = _Channel(APPEAL_CH, fail_threads=True)
    guild4 = _Guild([appeal_ch4], [everyone, mod_role])
    cog4 = A.Appeals(_Bot(guild4))
    await cog4._submit_channel_appeal(du2, guild4, 'Прошу разбан, всё было не так')
    check('открыть не получилось' in (du2.dms[0].description or ''),
          'канал НЕ открылся — ЛС честно говорит об этом')
    CR.set_route(GID, 'ban_appeal_channel', APPEAL_CH)

    print('== 4. /report тегает модераторов: каноническая роль ==')
    import tempfile as _tf
    with open(f'data/reports_{GID}.json', 'w', encoding='utf-8') as f:
        json.dump({'mod_role_id': '7001'}, f)
    roles = R._mod_ping_roles(guild)
    check(mod_role in roles, 'тег: каноническая роль модераторов найдена')

    print('== 5. Без настроенной роли: role_map и авто-роли с правами ==')
    os.remove(f'data/reports_{GID}.json')
    for legacy in (f'data/ticket_notify_{GID}.json',
                   f'data/ticket_permissions_{GID}.json',
                   'data/staff_roles.json'):
        if os.path.exists(legacy):
            os.remove(legacy)
    with open('data/role_map.json', 'w', encoding='utf-8') as f:
        json.dump({'7002': 'admin'}, f)
    roles = R._mod_ping_roles(guild)
    check(admin_role in roles, 'тег: роль из role_map.json подхвачена')
    check(mod_role in roles, 'тег: авто-роль с ban_members подхвачена')
    check(len(roles) <= 3 and everyone not in roles,
          'тег: максимум 3 роли, @everyone не тегается')

    print('== 6. Совсем нет ролей модерации → карточка уходит, панель предупреждена ==')
    guild_bare = _Guild([_Channel(1312434963941167134)],
                        [_Role(0, '@everyone'), _Role(8001, 'Цветная', managed=True)])
    with open('data/role_map.json', 'w', encoding='utf-8') as f:
        json.dump({}, f)
    roles = R._mod_ping_roles(guild_bare)
    check(roles == [], 'кандидатов нет — не выдумываем')

    print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
