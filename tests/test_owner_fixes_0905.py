# -*- coding: utf-8 -*-
"""Четыре багрепорта владельца (2026-09-05) — фикс и поведение.

1. «Создать доступ (регистрация) не работает: не находит человека под таким
   именем» — ник→ID теперь падает не только на живом кэше discord.py
   (который пуст, пока бот не прогрелся / intents.members выключен), но и
   на полном составе сервера с диска (services/member_store).
2. «Канал апелляции должно быть видно только после подачи апелляции в ЛС
   бота» — изоляция (бан) закрывает ВСЕ каналы, включая канал апелляции;
   канал открывает только подача апелляции.
3. «Бот не отправляет в канал, куда я указал» — карточки апелляций из ЛС
   падают в маршрут владельца «Канал апелляции (бан)»
   (Панель → Каналы и маршруты), а не в системный канал.
4. «Отзыв (помогли/не помогли) — куда он идёт? его просто нет» — отзыв
   публикуется в канал/тред апелляции (и по-прежнему сводится в панель).
5. «В бане не написано, что вы получили бан» — ЛС о бане называется баном.

Запуск: python3 tests/test_owner_fixes_0905.py
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix='owner_fixes_0905_')
os.chdir(_TMP)
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

os.environ['DEMO_MODE'] = '1'
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


def src_of(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


# ── 1. Регистрация: ник резолвится по составу с диска ──────────────────────
print('== 1. Регистрация: «не находит человека под таким именем» ==')
import web.app as appmod  # noqa: E402

# состав сервера на диске: bot прогрел member_store, живой кэш ПУСТ
store_dir = os.path.join('data', 'members_777.json')
with open(store_dir, 'w', encoding='utf-8') as f:
    json.dump({'saved_at': '2026-09-05T00:00:00', 'sig': 1,
               'members': {
                   '3001': {'id': '3001', 'name': 'vanya', 'display_name': 'Ваня',
                            'bot': False, 'avatar': ''},
                   '3002': {'id': '3002', 'name': 'anna', 'display_name': 'Анна',
                            'bot': False, 'avatar': ''},
               }}, f)

# подмена _panel_guild: живого кэша нет (None) — только диск
appmod._panel_guild_orig = getattr(appmod, '_panel_guild_orig', appmod._panel_guild)
appmod._panel_guild = lambda: None
try:
    r = appmod._resolve_nick_anywhere('Ваня')
    check(r == '3001', f'ник «Ваня» найден в составе на диске: {r}')
    r2 = appmod._resolve_nick_anywhere('@vanya')
    check(r2 == '3001', f'ник с @ и латиницей тоже находится: {r2}')
    check(appmod._resolve_nick_anywhere('никого-такого') is None,
          'неизвестный ник честно даёт None')
finally:
    appmod._panel_guild = appmod._panel_guild_orig

check('_resolve_nick_anywhere' in src_of('web/app.py')
      and 'member_store' in src_of('web/app.py'),
      'register использует общий хелпер с составом с диска')

# ── 2. Бан закрывает ВСЁ; канал апелляции открывает подача ─────────────────
print('== 2. Канал апелляции виден только после подачи апелляции ==')
m_src = src_of('cogs/moderation.py')
check('allow =discord .PermissionOverwrite' not in m_src
      and 'заказ владельца 2026-09-05' in m_src,
      'изоляция больше не открывает канал апелляции сама')
a_src = src_of('cogs/appeals.py')
check("ban_appeal_channel" in a_src and 'открываем автору ТОЛЬКО теперь' in a_src,
      'подача апелляции в ЛС открывает автору канал апелляции')

# _isolate_member: закрывает ВСЕ каналы, включая канал апелляции
import asyncio  # noqa: E402


class _Ch:
    def __init__(self, cid):
        self.id = cid

    async def set_permissions(self, user, overwrite=None):
        self.last = overwrite


class _Guild:
    id = 777
    channels = [_Ch(1), _Ch(2), _Ch(3)]


class _ModStub:
    from cogs.moderation import Moderation as _M
    _isolate_member = _M._isolate_member


from cogs.moderation import Moderation  # noqa: E402

_g = _Guild()
_iso, closed = asyncio.get_event_loop().run_until_complete(
    Moderation._isolate_member(object.__new__(Moderation), _g, object(), _g.channels[1]))
check(closed == 3 and all(getattr(c, 'last', None) is not None for c in _g.channels),
      f'изоляция закрывает все каналы, включая канал апелляции (закрыто: {closed})')

# ── 3. Карточка апелляции летит в канал владельца ──────────────────────────
print('== 3. Бот шлёт апелляции в указанный владельцем канал ==')
sys.path.insert(0, ROOT)


class _RouteFake:
    calls = []

    @staticmethod
    def get_route(gid, key):
        _RouteFake.calls.append((gid, key))
        return 1545468739221327942


class _Chan:
    def __init__(self, cid):
        self.id = cid


class _Guild2:
    id = 777
    system_channel = None

    def __init__(self):
        self._chans = {1545468739221327942: _Chan(1545468739221327942),
                       42: _Chan(42)}

    def get_channel(self, cid):
        return self._chans.get(cid)


import cogs.appeals as ap  # noqa: E402


class _AppealsStub(ap.Appeals):
    def __init__(self):
        pass  # без бота/БД — _log_channel их не трогает


route_mod = 'services.channel_routes'
import importlib  # noqa: E402
real_rr = importlib.import_module(route_mod)
real_get = real_rr.get_route
real_rr.get_route = _RouteFake.get_route
try:
    st = ap.Appeals.__new__(_AppealsStub)
    ch = st._log_channel(_Guild2(), {'log_channel_id': 0})
    check(getattr(ch, 'id', None) == 1545468739221327942
          and (777, 'ban_appeal_channel') in _RouteFake.calls,
          'без /апелляции настройка карточки идут в «Канал апелляции (бан)» из панели')
    _RouteFake.calls.clear()
    real_rr.get_route = lambda gid, key: 0
    ch2 = st._log_channel(_Guild2(), {'log_channel_id': 42})
    check(getattr(ch2, 'id', None) == 42,
          'канал из /апелляции настройка приоритетнее маршрута')
finally:
    real_rr.get_route = real_get

# ── 4. Отзыв «помогли/не помогли» уходит в канал апелляции ─────────────────
print('== 4. Отзыв об апелляции имеет видимое место назначения ==')
check('оценил ' in a_src and 'thread_id' in a_src,
      'отзыв публикуется в тред/канал карточки апелляции')
check('в канале апелляций ' in a_src and 'панели' in a_src,
      'человеку в ЛС говорят, куда ушла его оценка')

# ── 5. ЛС о бане: «вам выдан бан», а не «закрыты каналы» ───────────────────
print('== 5. Текст ЛС при бане ==')
e_src = src_of('cogs/embed_utils.py')
check('Вам выдан бан' in e_src and 'выдали бан (блокировку)' in e_src,
      'ЛС о бане прямо говорит про бан/блокировку')
check('/апелляция' in e_src and 'после подачи' in e_src,
      'в ЛС сказано: апелляция — в ЛС боту, канал откроется после подачи')

print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
