# -*- coding: utf-8 -*-
"""Раздел «Роли»: управление ролями и цветные роли работают по-настоящему.

Что нашёл подробный разбор раздела (обе страницы: /roles, /color-roles):

1. Селект «Выберите сервер...» на /roles не заполнял НИКТО — ни шаблон,
   ни app.js. Пункт был единственным, переключить сервер было нельзя.
2. Удаление роли отвечало «успех» даже когда роль не удалилась (её не
   нашлось у бота), а на нечисловом id падало 500-м с трейсбеком.
3. Публикация цветных ролей рапортовала «Опубликовано цветов: N», даже
   если роли в Discord создать не удалось (право «Управлять ролями»).
4. Селект «Модератор» в Про-аналитике не заполнялся ничем, хотя бэкенд
   параметр moderator понимает, а «Роли за наказания» показывали один
   пункт «— не выдавать —»: guild_roles() не знала демо-состава, который
   отдают /api/roles и все остальные пикеры.

Запуск:  .venv/bin/python tests/test_roles_category.py
"""
import asyncio
import json
import os
import sys
import threading
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DEMO_MODE', '1')
os.environ.setdefault('MAIN_GUILD_ID', '987654321098765432')

PASS = FAIL = 0
GID = '987654321098765432'


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


def _backup(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return f.read()


def _restore(path, text):
    if text is None:
        if os.path.exists(path):
            os.remove(path)
    else:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)


import discord  # noqa: E402
import web.app as appmod  # noqa: E402
from web.app import app  # noqa: E402
from web.routes import mod_settings  # noqa: E402
from services import live_bus  # noqa: E402

client = app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'
    s['selected_guild'] = GID


def _forbidden():
    resp = types.SimpleNamespace(
        status=403, reason='Forbidden',
        request=types.SimpleNamespace(headers={}))
    return discord.Forbidden(resp, 'Missing Permissions')


class _FakeRole:
    def __init__(self, rid, name='Обычная роль', managed=False, default=False,
                 exc=None):
        self.id = rid
        self.name = name
        self.managed = managed
        self._default = default
        self._exc = exc
        self.deleted = False

    def is_default(self):
        return self._default

    async def delete(self, reason=None):
        if self._exc is not None:
            raise self._exc
        self.deleted = True


class _FakeGuild:
    def __init__(self, gid, roles):
        self.id = gid
        self.roles = roles

    def get_role(self, rid):
        for r in self.roles:
            if int(r.id) == int(rid):
                return r
        return None


class _FakeBot:
    """Кэш гильдий пуст (get_guild промахивается) — как в бою на старте."""

    def __init__(self, guilds, loop):
        self.guilds = guilds
        self.loop = loop

    def get_guild(self, gid):
        return None


_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()

_saved_bot = appmod.bot_instance


def use_bot(roles, gid=GID):
    guild = _FakeGuild(int(gid), roles)
    appmod.bot_instance = _FakeBot([guild], _loop)
    return guild


print('== 1. Удаление роли: нечисловой id не роняет панель ==')
use_bot([_FakeRole(111)])
r = client.post(f'/api/guild/{GID}/roles/не-число/delete')
check(r.status_code == 400, f'нечисловой id роли -> 400 (было 500), код {r.status_code}')
check('Неверный ID роли' in (r.get_json() or {}).get('error', ''),
      f'текст ошибки внятный: {(r.get_json() or {}).get("error")!r}')
r = client.post('/api/guild/не-сервер/roles/111/delete')
check(r.status_code in (400, 404) and (r.get_json() or {}).get('error'),
      f'нечисловой id сервера -> {r.status_code} с внятным текстом '
      f'(500 с трейсбеком больше нет): {(r.get_json() or {}).get("error")!r}')

print('== 2. Удаление роли: «успех» только если роль правда удалена ==')
use_bot([_FakeRole(111)])
r = client.post(f'/api/guild/{GID}/roles/999/delete')
body = r.get_json() or {}
check(r.status_code == 404, f'роли нет на сервере -> 404 (было 200 «успех»), код {r.status_code}')
check(not body.get('success'), 'в ответе нет success: панель не напишет «Роль удалена»')
check('не найдена' in body.get('error', '').lower(),
      f'текст: {body.get("error")!r}')

print('== 3. Удаление роли: @everyone и интеграционные роли ==')
every = _FakeRole(int(GID), default=True)
use_bot([every, _FakeRole(111)])
r = client.post(f'/api/guild/{GID}/roles/{GID}/delete')
check(r.status_code == 400, f'@everyone -> 400, код {r.status_code}')
check('everyone' in (r.get_json() or {}).get('error', ''),
      f'текст: {(r.get_json() or {}).get("error")!r}')

managed = _FakeRole(222, managed=True)
use_bot([_FakeRole(111), managed])
r = client.post(f'/api/guild/{GID}/roles/222/delete')
check(r.status_code == 403, f'роль интеграции -> 403, код {r.status_code}')
check('интеграция' in (r.get_json() or {}).get('error', ''),
      f'текст: {(r.get_json() or {}).get("error")!r}')
check(not managed.deleted, 'роль интеграции не тронута')

print('== 4. Удаление роли: отказ Discord -> внятная 403, не 500 ==')
blocked = _FakeRole(333, exc=_forbidden())
use_bot([_FakeRole(111), blocked])
r = client.post(f'/api/guild/{GID}/roles/333/delete')
check(r.status_code == 403, f'Discord запретил -> 403, код {r.status_code}')
check('иерархии' in (r.get_json() or {}).get('error', ''),
      f'текст: {(r.get_json() or {}).get("error")!r}')

print('== 5. Удаление роли: успех доходит до Discord и шлёт живое событие ==')
good = _FakeRole(444)
use_bot([_FakeRole(111), good])
got = []
_q, _unsub = live_bus.subscribe([f'g{GID}:roles', 'roles'])
r = client.post(f'/api/guild/{GID}/roles/444/delete')
try:
    got.append(_q.get(timeout=2))
except Exception:
    pass
_unsub()
check(r.status_code == 200 and (r.get_json() or {}).get('success'),
      f'успех, код {r.status_code}')
check(good.deleted, 'role.delete() действительно вызван')
check(bool(got), f'опубликован топик roles для открытых вкладок: {got}')

print('== 6. Создание роли: имя длиннее 100 символов отклоняем сами ==')
appmod.bot_instance = None
r = client.post(f'/api/guild/{GID}/roles/create',
                json={'name': 'ы' * 101, 'color': '#4f46e5'})
check(r.status_code == 400, f'длинное имя -> 400, код {r.status_code}')
check('100' in (r.get_json() or {}).get('error', ''),
      f'текст: {(r.get_json() or {}).get("error")!r}')

print('== 7. Роли для селектов: демо-состав там, где /api/roles его отдаёт ==')
appmod.bot_instance = None
live = mod_settings.guild_roles(GID)
check(len(live) > 0, f'демо-режим: ролей {len(live)} (было 0 — селект мёртв)')
check(all(r.get('id') and r.get('name') for r in live),
      'у каждой роли есть id и имя')

_saved_demo = appmod._demo_mode
appmod._demo_mode = lambda: False
try:
    boj = mod_settings.guild_roles('793336829280780331')
    check(boj == [], f'боевой режим без бота: пустой список (демо-роли не подсовываем), {boj}')
finally:
    appmod._demo_mode = _saved_demo

print('== 8. «Роли за наказания» показывают список ролей и честный баннер ==')
d = client.get(f'/api/guild/{GID}/role-settings').get_json() or {}
check(d.get('roles_count', 0) > 0, f'ролей в ответе {d.get("roles_count")} (было 0)')
check(d.get('roles_from_demo') is True,
      'помечено, что показан демо-набор (баннер не врёт про «список недоступен»)')
check(len(d.get('levels', [])) >= 0 and d.get('success'), 'ответ успешный')

print('== 9. Про-аналитика: фильтр «Модератор» есть из чего собрать ==')
tk = 'data/ai_tickets_probe_roles.json'
tk_bk = _backup(tk)
with open(tk, 'w', encoding='utf-8') as f:
    json.dump({'1': {'created_at': '2026-08-30T10:00:00+00:00', 'status': 'closed',
                     'category': 'Жалоба', 'closed_by': 'ivan.mod'},
               '2': {'created_at': '2026-08-31T10:00:00+00:00', 'status': 'closed',
                     'category': 'Вопрос', 'closed_by': 'olga.mod'},
               '3': {'created_at': '2026-08-31T11:00:00+00:00', 'status': 'open',
                     'category': 'Вопрос', 'closed_by': ''}}, f)
d = client.get('/api/analytics/advanced?period=365').get_json() or {}
mods = d.get('moderators') or []
check('ivan.mod' in mods and 'olga.mod' in mods,
      f'в ответе список модераторов {mods} (раньше поля не было — селект пустой)')
check('' not in mods, 'пустые closed_by в список не попали')
_restore(tk, tk_bk)

print('== 10. Публикация цветных ролей: кривой id канала не проходит ==')
use_bot([])
r = client.post(f'/api/guild/{GID}/color-roles/publish',
                json={'channel_id': 'не-число', 'colors': [{'name': 'Красный', 'hex': '#ff0000'}]})
check(r.status_code == 400, f'нечисловой канал -> 400, код {r.status_code}')
check('канала' in (r.get_json() or {}).get('error', ''),
      f'текст: {(r.get_json() or {}).get("error")!r}')

appmod.bot_instance = None
_saved_demo2 = appmod._demo_mode
appmod._demo_mode = lambda: False
try:
    r = client.post(f'/api/guild/{GID}/color-roles/publish',
                    json={'channel_id': '123456789012345678',
                          'colors': [{'name': 'Красный', 'hex': '#ff0000'}]})
    check(r.status_code == 503, f'бот офлайн в бою -> 503 (было 200), код {r.status_code}')
finally:
    appmod._demo_mode = _saved_demo2

print('== 11. Название раздела одно на всё меню ==')
from services.panel_menu import MENU  # noqa: E402
label = [p['label'] for g in MENU for p in g['pages'] if p['path'] == '/color-roles']
check(label == ['Цветные роли'],
      f'в сайдбаре «Цветные роли» (как на странице и в Discord), было {label}')

appmod.bot_instance = _saved_bot
_loop.call_soon_threadsafe(_loop.stop)

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
