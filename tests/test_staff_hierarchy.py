# -*- coding: utf-8 -*-
"""Иерархия персонала — «беспредел» закрыт (владелец, 2026-09-05).

Жалоба: «модер может выдать наказание другому модеру, модер может дать
вообще куратору». Теперь:
  • модератор наказывает ТОЛЬКО участников;
  • куратор — участников и модераторов;
  • администратор — участников, модераторов, кураторов;
  • владелец — всех, кроме владельца бота и владельца сервера;
  • снятия наказаний (unwarn/untimeout/...) — по той же иерархии;
  • боты, владелец сервера, владелец бота, сам себе — нельзя никому из
    персонала (владелец панели — тоже не трогает владельца бота/сервера).
Единая точка правды — services/staff_hierarchy.check: её используют
/modpanel, веб-панель, /warn, /unwarn и массовые действия.
Запуск: python3 tests/test_staff_hierarchy.py
"""
import asyncio
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(tempfile.mkdtemp(prefix='hier_'))
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath(os.path.join('data', 'bot.db'))
# «владелец бота» в тесте = 9900000000000000990 (Config читает .env-окружение)
os.environ.setdefault('OWNER_IDS', '9900000000000000990')
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


from services import staff_hierarchy as SH  # noqa: E402


def perms(**kw):
    d = dict(administrator=False, ban_members=False, kick_members=False,
             manage_messages=False, manage_guild=False, moderate_members=False)
    d.update(kw)
    return types.SimpleNamespace(**d)


class _Role:
    def __init__(self, rid):
        self.id = rid
        self.name = f'role-{rid}'


class _Member:
    def __init__(self, uid, name, *, bot=False, owner_server=False,
                 owner_bot=False, admin=False, modrole=False):
        self.id = uid
        self.name = name
        self.display_name = name
        self.bot = bot
        self.roles = []
        self.guild_permissions = perms(administrator=admin)
        self._owner_server = owner_server
        self._owner_bot = owner_bot
        self._modrole = modrole

    @property
    def is_owner_like(self):
        return self._owner_server or self._owner_bot


class _Guild:
    def __init__(self):
        self.id = 1484574976580391004
        self.owner_id = 1111000000000000111
        self.members = []

    def get_member(self, uid):
        for m in self.members:
            if m.id == uid:
                return m
        return None


guild = _Guild()

mod = _Member(2000000000000000200, 'Модер', modrole=True)
mod2 = _Member(2010000000000000201, 'Модер2', modrole=True)
curator = _Member(2200000000000000220, 'Куратор', modrole=True, admin=False)
curator.guild_permissions = perms(manage_messages=True)
admin = _Member(2300000000000000230, 'Админ', admin=True)
owner_panel = None            # статический вход (owner панели)
owner_server = _Member(1111000000000000111, 'Хозяин сервера')
owner_bot = _Member(9900000000000000990, 'Хозяин бота')
user1 = _Member(3000000000000000300, 'Участник')
bot_member = _Member(4000000000000000400, 'Ботяра', bot=True)
guild.members = [mod, mod2, curator, admin, owner_server, owner_bot,
                 user1, bot_member]

# mod_role-источник указывает на роль модератора
import json
with open('data/reports_%d.json' % guild.id, 'w') as f:
    json.dump({'mod_role_id': '7001'}, f)
mod_role_obj = _Role(7001)
mod.roles.append(mod_role_obj)
mod2.roles.append(mod_role_obj)
curator.roles.append(mod_role_obj)
# админ — по administrator-праву, роль можно не добавлять


SESS = {'mod': 'mod', 'curator': 'curator', 'admin': 'admin'}


def run(actor, target, action='timeout', actor_role=None, session_role=None):
    ok, deny, ar, tr = SH.check(guild, actor, target, action,
                                actor_role=actor_role,
                                session_role=session_role)
    return ok, deny


async def main():
    print('== 1. Матрица: кто кого наказывает ==')
    ok, _ = run(mod, user1)
    check(ok, 'модератор → участник: можно')
    ok, deny = run(mod, mod2)
    check(not ok and 'персонал' in deny,
          'модератор → модератор: НЕЛЬЗЯ (беспредел закрыт)', f'→ {deny}')
    ok, deny = run(mod, curator)
    check(not ok, 'модератор → куратор: НЕЛЬЗЯ')
    ok, deny = run(mod, admin)
    check(not ok, 'модератор → администратор: НЕЛЬЗЯ')
    ok, _ = run(curator, user1, session_role='curator')
    check(ok, 'куратор → участник: можно')
    ok, _ = run(curator, mod, session_role='curator')
    check(ok, 'куратор → модератор: можно')
    ok, deny = run(curator, curator, session_role='curator')
    check(not ok, 'куратор → куратор: НЕЛЬЗЯ')
    ok, _ = run(admin, user1, session_role='admin')
    check(ok, 'админ → участник: можно')
    ok, _ = run(admin, curator, session_role='admin')
    check(ok, 'админ → куратор: можно')
    ok, deny = run(admin, admin, session_role='admin')
    check(not ok, 'админ → админ: НЕЛЬЗЯ')
    ok, _ = run(owner_panel, admin, session_role='owner')
    check(ok, 'владелец панели → админ: можно')

    print('== 2. Вне юрисдикции ==')
    ok, deny = run(mod, owner_server, session_role='mod')
    check(not ok and 'владелец сервера' in deny,
          'владелец сервера: никому, кроме владельца панели', f'→ {deny}')
    ok, deny = run(mod, owner_bot)
    check(not ok and 'владелец бота' in deny,
          'владелец бота: никому, кроме владельца панели')
    ok, deny = run(admin, owner_server, session_role='admin')
    check(not ok, 'админ → владелец сервера: НЕЛЬЗЯ')
    ok, _ = run(owner_panel, owner_server, session_role='owner')
    check(ok, 'владелец панели → владелец сервера: можно (по заказу «владелец без лимит — все»)')
    ok, deny = run(mod, bot_member)
    check(not ok and 'ботов' in deny.lower(), 'ботов наказывать нельзя')
    ok, deny = run(mod, mod, action='timeout', session_role='mod')
    # actor==target: mod наказывает сам себя (id совпадают)
    check(not ok and 'Себя' in deny, 'себе наказание не выдаётся')

    print('== 3. Снятия наказаний — по той же иерархии ==')
    ok, deny = run(mod, curator, action='unwarn', session_role='mod')
    check(not ok, 'модер НЕ снимает варны куратору')
    ok, deny = run(mod, mod2, action='untimeout', session_role='mod')
    check(not ok, 'модер НЕ снимает муты модератору (иначе снимали бы друг другу)')
    ok, _ = run(curator, mod, action='unwarn', session_role='curator')
    check(ok, 'куратор снимает варн модератору: можно')

    print('== 4. Панельная роль из Discord: цель определяется сам ==')
    tr = SH.target_panel_role(guild, user1)
    check(tr == 'uye', 'участник без ролей/прав → uye')
    tr = SH.target_panel_role(guild, admin)
    check(tr == 'admin', 'Discord-администратор → admin (цель)')
    tr = SH.target_panel_role(guild, mod)
    check(tr == 'mod', 'обладатель модер-роли → mod (цель)')
    ar = SH.actor_panel_role(guild, None)
    check(ar == 'owner', 'статический вход (None) — владелец панели')

    print('== 5. Отказ — человекочитаемый ==')
    ok, deny = run(mod, curator, action='мут', session_role='mod')
    check('куратор' in deny and 'Иерархия' in deny,
          'в отказе видно, кто перед ним и как устроена иерархия')

    print('== 6. Встроено во все точки ==')
    import web.routes.panel_punish as PP
    check('staff_hierarchy' in open(os.path.join(ROOT, 'web/routes/panel_punish.py'),
                                    encoding='utf-8').read(),
          'карточка участника (веб-панель) проверяет иерархию')
    mod_src = open(os.path.join(ROOT, 'cogs/moderation.py'), encoding='utf-8').read()
    check('/modpanel' in mod_src and 'staff_hierarchy' in mod_src,
          '/modpanel и единый путь apply_panel_action проверяют иерархию')
    w_src = open(os.path.join(ROOT, 'cogs/warnings.py'), encoding='utf-8').read()
    check(w_src.count('staff_hierarchy') >= 2,
          '/warn и /unwarn проверяют иерархию')
    mo_src = open(os.path.join(ROOT, 'web/routes/member_ops.py'),
                  encoding='utf-8').read()
    check(mo_src.count('staff_hierarchy') >= 3,
          'массовые мут/кик/бан пропускают персонал (не трогают его)')

    print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
    sys.exit(1 if FAIL else 0)

asyncio.run(main())
