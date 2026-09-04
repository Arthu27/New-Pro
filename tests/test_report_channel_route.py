# -*- coding: utf-8 -*-
"""Канал вызовов модератора (/report) — заказ владельца 2026-09-05.

Раньше: /report не находил канал → пытался СОЗДАТЬ закрытый канал → без
права «Управление каналами» падал с «Не удалось подготовить канал
модерации». Теперь цепочка: конфиг панели → имя «модерация» → маршрут
«Маршруты каналов» → канал владельца по умолчанию (1312434963941167134)
→ только в самом крайнем случае создание.

Проверяем, что /report находит канал ВЕЗДЕ и право «Управление
каналами» нигде не нужно.
Запуск: python3 tests/test_report_channel_route.py
"""
import asyncio
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(tempfile.mkdtemp(prefix='rep_ch_'))
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
from services import channel_routes as CR  # noqa: E402
from services import reports_core as RC  # noqa: E402

OWNER_CH_ID = R.DEFAULT_REPORT_CHANNEL_ID
check(OWNER_CH_ID == 1312434963941167134,
      'канал репортов по умолчанию = 1312434963941167134 (заказ владельца)')

GID = 1484574976580391004  # основной сервер владельца


def make_guild(channels_by_id, name_hit=None):
    """Фейк-гильдия: get_channel по словарю; создание канала ЗАПРЕЩЕНО."""
    created = []

    class _Ch:
        def __init__(self, cid):
            self.id = cid
            self.name = f'канал-{cid}'

    class _G:
        id = GID
        default_role = None
        me = None
        text_channels = [_Ch(c) for c in channels_by_id] + (
            [type('N', (), {'id': 1, 'name': name_hit})] if name_hit else [])

        def get_channel(self, cid):
            return _Ch(cid) if cid in channels_by_id else None

        def create_text_channel(self, *a, **kw):
            created.append(a)
            raise discord.Forbidden()

    return _G(), created


class _NoRole:
    pass


async def main():
    # 1. Ничего не настроено, но канал владельца существует → /report работает
    guild, created = make_guild({OWNER_CH_ID})
    ch, created_flag = await R._ensure_mod_channel(guild, None)
    check(ch is not None and ch.id == OWNER_CH_ID,
          'репорты идут в канал владельца 1312434963941167134 (по умолчанию)')
    check(not created_flag and not created,
          'канал НЕ создаётся — «Управление каналами» не нужно')

    # 2. Маршрут из «Маршрутов каналов» перекрывает умолчание
    CR.set_route(GID, 'report_channel', 555000111222333444)
    guild, _ = make_guild({OWNER_CH_ID, 555000111222333444})
    ch, _ = await R._ensure_mod_channel(guild, None)
    check(ch.id == 555000111222333444,
          'маршрут из панели «Маршруты каналов» приоритетнее умолчания')
    CR.set_route(GID, 'report_channel', 0)  # очистили — снова умолчание

    # 3. Настройка репортов (конфиг) сильнее всех
    RC.save_cfg(GID, dict(RC.load_cfg(GID), channel_id='777000111222333444'))
    guild, _ = make_guild({OWNER_CH_ID, 777000111222333444})
    ch, _ = await R._ensure_mod_channel(guild, None)
    check(ch.id == 777000111222333444, 'конфиг репортов (панель) приоритетнее всех')
    RC.save_cfg(GID, dict(RC.load_cfg(GID), channel_id=''))

    # 4. Нет ни одного известного ID, но есть канал с именем «модерация»
    guild, created = make_guild(set(), name_hit='модерация')
    ch, _ = await R._ensure_mod_channel(guild, None)
    check(ch is not None and ch.name == 'модерация',
          'фоллбэк по имени «модерация» сохранён')

    # 5. Крайний случай: нет ничего → создание запрещено → честный (None, False)
    guild, created = make_guild(set())
    ch, created_flag = await R._ensure_mod_channel(guild, None)
    check(ch is None and created_flag is False and created,
          'совсем нет каналов и прав → отказ без падения (создание пыталосься)')

    # 6. Хаб «Маршруты каналов» знает новый маршрут
    spec = CR.spec_for('report_channel')
    check(spec is not None and spec.get('step') == 2,
          'в «Маршрутах каналов» есть «Канал вызовов модератора (/report)» (шаг 2)')
    check('1312434963941167134' in (spec.get('create_hint') or '')
          + (spec.get('empty') or ''),
          'в описании маршрута указан канал владельца')

    # 7. Панельный адаптер подключён (чтение/запись из хаба)
    import importlib
    cs = importlib.import_module('web.routes.channel_settings')
    get_fn, set_fn = cs.ADAPTERS['report_channel']
    check(get_fn(GID, 'report_channel') == 0 and callable(set_fn),
          'адаптер хаба читает/пишет маршрут report_channel')

    # 8. Текст ошибки при полном провале подсказывает, где чинить
    import inspect
    src = inspect.getsource(R)
    check('Маршруты каналов' in src and 'Управление каналами' in src,
          'текст ошибки объясняет админу, что настроить')

    # 9. Спека в хабе не сломала остальные шаги (уникальность и порядок)
    steps = [s.get('step') for s in CR.ROUTE_SPECS if s.get('step') is not None]
    check(len(steps) == len(set(steps)), 'номера шагов в хабе уникальны')

asyncio.run(main())
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
