# -*- coding: utf-8 -*-
"""Дубли команд при синке из панели — регресс на НАСТОЯЩЕМ CommandTree.

Баг 2026-08-29 «жму синк в панели — каждая команда по две»:
1. full_sync при падении guild-синка (rate limit и т.п.) «откатывался»
   публикацией ВСЕГО локального дерева глобально — поверх уже лежащих
   гильдовых копий. Итог: одна и та же команда и в глобальном списке,
   и в серверном → в меню «/» дважды.
2. Кнопка /api/bot-settings/sync ждала ответ 10 сек с таймаутом →
   владелец видел «Синк упал», хотя синк шёл → жал кнопку снова →
   rate limit → п.1.
3. Холодный кэш гильдии (get_guild=None) включал «глобальный режим»
   вместо guild-синка — стирал серверные меню.

Здесь проверяем физические payload'ы, уходящие в Discord (HTTP-мок
пишет каждый вызов), на реальном discord.app_commands.CommandTree.

Запуск: python3 tests/test_sync_duplicates.py
"""
import asyncio
import os
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix='hakumo_dupes_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DEMO_MODE'] = '1'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['SECRET_KEY'] = 'test-secret'

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


import discord  # noqa: E402
from discord import AppCommandType, Object  # noqa: E402
from discord.app_commands import ContextMenu, command  # noqa: E402


# ── записывающий HTTP-мок: каждый bulk-upsert попадает в журнал ─────────────
class Recorder:
    def __init__(self):
        self.calls = []          # (scope, guild_id, [имена])
        self.fail_guilds = False

    @staticmethod
    def _ok(app_id, payload):
        # настоящий Discord возвращает команды с id/application_id
        return [dict(p, id=9000 + i, application_id=app_id)
                for i, p in enumerate(payload or [])]

    async def bulk_upsert_global_commands(self, app_id, payload=None):
        names = [p['name'] for p in (payload or [])]
        self.calls.append(('GLOBAL', None, names))
        return self._ok(app_id, payload)

    async def bulk_upsert_guild_commands(self, app_id, guild_id, payload=None):
        if self.fail_guilds:
            raise RuntimeError('429 Too Many Requests (мок: как Discord)')
        names = [p['name'] for p in (payload or [])]
        self.calls.append(('GUILD', guild_id, names))
        return self._ok(app_id, payload)

    def last(self, scope, gid=None):
        for s, g, names in reversed(self.calls):
            if s == scope and g == gid:
                return list(names)
        return []


class Bot:
    """Минимальный клиент discord.py: CommandTree настоящий, HTTP — мок."""

    def __init__(self, cold_cache=False):
        self.application_id = 42
        self.http = Recorder()
        self.loop = None
        self._connection = types.SimpleNamespace(_command_tree=None, _translator=None)
        self.tree = discord.app_commands.CommandTree(self)
        self.cold = cold_cache
        self._guilds = [types.SimpleNamespace(id=777), types.SimpleNamespace(id=888)]

    def get_guild(self, gid):
        if self.cold:
            return None
        return next((g for g in self._guilds if g.id == gid), None)

    @property
    def guilds(self):
        return list(self._guilds)


async def _cb(interaction):
    pass


async def _msg_cb(interaction, message: discord.Message):
    pass


def mk(name, keep_global=False):
    extras = {'keep_global': True} if keep_global else {}
    return command(name=name, description=f'cmd {name}', extras=extras)(_cb)


def build_bot(cold_cache=False):
    bot = Bot(cold_cache=cold_cache)
    tree = bot.tree
    # глобальные (коги без guilds: appeals/diagnostics)
    tree.add_command(mk('апелляция', keep_global=True))
    tree.add_command(mk('update', keep_global=True))
    tree.add_command(ContextMenu(name='Варн за сообщение', callback=_msg_cb,
                                 type=AppCommandType.message))
    # гильдовые (коги с guilds=Config.guild_objects())
    for n in ('modpanel', 'play', 'afk', 'afk-remove', 'ticket-panel'):
        tree.add_command(mk(n), guild=Object(777))
    return bot


async def main():
    from services import sync_filtered as SF
    from services import command_switches as CSW

    # ═══ A. Успешные синки: дублей нет ═════════════════════════════════════
    print('== A. Успешные синки (старт + кнопка в панели + двойной клик) ==')
    bot = build_bot()
    rec = bot.http
    await SF.full_sync(bot)                    # старт бота
    await SF.full_sync(bot)                    # кнопка «Синхронизировать»
    await asyncio.gather(SF.full_sync(bot), SF.full_sync(bot))   # двойной клик
    glob, guild = rec.last('GLOBAL'), rec.last('GUILD', 777)
    check(glob == ['апелляция', 'update'],
          f'глобальный список = только keep_global ({glob})')
    check(set(glob) & set(guild) == set(),
          f'пересечение глобаль∩гильдия пустое — дублей нет ({sorted(set(glob) & set(guild))})')
    check('Варн за сообщение' in guild and 'Варн за сообщение' not in glob,
          'контекстное меню живёт ТОЛЬКО в гильдии (не в двух местах)')
    check(rec.last('GUILD', 888) == [],
          'чужая гильдия 888 очищена от устаревших копий')
    check('modpanel' in guild and 'play' in guild, 'гильдовые команды на месте')

    # ═══ B. Guild-синк падает (rate limit) — откат НЕ плодит дубли ═════════
    print('== B. Guild-синк упал (429) — откат без дублей ==')
    bot2 = build_bot()
    rec2 = bot2.http
    await SF.full_sync(bot2)                   # успешный старт
    ok_guild = rec2.last('GUILD', 777)
    rec2.fail_guilds = True                    # теперь Discord рейт-лимитит
    rec2.calls.clear()
    await SF.full_sync(bot2)                   # владелец жмёт синк в панели
    glob2 = rec2.last('GLOBAL')
    check(glob2 == ['апелляция', 'update'],
          f'после сбоя глобально перепубликован ТОЛЬКО keep_global ({glob2})')
    check('Варн за сообщение' not in glob2,
          'контекстное меню НЕ опубликовано глобально (иначе — дубль в меню)')
    check(set(glob2) & set(ok_guild) == set(),
          'ничего из гильдии не продублировано глобально')
    check(not any(s == 'GUILD' and names for s, g, names in rec2.calls),
          'упавший guild-синк не тронул старые списки серверов')
    # синк ожил — всё самолечится и дублей по-прежнему нет
    rec2.fail_guilds = False
    rec2.calls.clear()
    await SF.full_sync(bot2)
    glob3, guild3 = rec2.last('GLOBAL'), rec2.last('GUILD', 777)
    check(glob3 == ['апелляция', 'update'] and set(glob3) & set(guild3) == set(),
          'после успешного повтора — по-прежнему ноль дублей')

    # ═══ C. Холодный кэш гильдии — guild-режим, а не «глобалка» ════════════
    print('== C. MAIN_GUILD_ID задан, но гильдии нет в кэше ==')
    bot3 = build_bot(cold_cache=True)
    rec3 = bot3.http
    await SF.full_sync(bot3)
    check(rec3.last('GUILD', 777) != [],
          'guild-синк прошёл по Object(id) даже без гильдии в кэше')
    check(rec3.last('GLOBAL') == ['апелляция', 'update'],
          'глобальный список не раздут гильдовыми командами')
    check(set(rec3.last('GLOBAL')) & set(rec3.last('GUILD', 777)) == set(),
          'холодный старт не порождает дублей')

    # ═══ D. Тумблеры на странице «Команды» — без дублей ════════════════════
    print('== D. Выключение/включение команды (тумблер в панели) ==')
    bot4 = build_bot()
    rec4 = bot4.http
    await SF.full_sync(bot4)
    CSW.set_disabled('play', True)
    await SF.full_sync(bot4)
    guild_off = rec4.last('GUILD', 777)
    check('play' not in guild_off, '/play исчез из гильдии после выключения')
    check(set(rec4.last('GLOBAL')) & set(guild_off) == set(), 'дублей нет')
    CSW.set_disabled('play', False)
    await SF.full_sync(bot4)
    guild_on = rec4.last('GUILD', 777)
    check('play' in guild_on, '/play вернулся после включения')
    check(set(rec4.last('GLOBAL')) & set(guild_on) == set(), 'и снова ноль дублей')

    # ═══ E. Кнопка в панели больше не «висит» с таймаутом ══════════════════
    print('== E. Кнопка синка уходит фоном (исходники) ==')
    src_bs = open(os.path.join(ROOT, 'web', 'routes', 'bot_settings.py'),
                  encoding='utf-8').read()
    check('run_coroutine_threadsafe' in src_bs and 'timeout=10' not in src_bs,
          'bot_settings: синк фоном, без ожидания с таймаутом')
    check('_run_async' not in src_bs.split('def api_bot_settings_sync')[1].split('def ')[0]
          if 'def api_bot_settings_sync' in src_bs else False,
          'bot_settings: sync-эндпоинт не блокирует Flask-поток')
    src_sf = open(os.path.join(ROOT, 'services', 'sync_filtered.py'),
                  encoding='utf-8').read()
    check('перепубликуем только keep_global' in src_sf,
          'sync_filtered: откат после сбоя публикует только keep_global')


asyncio.run(main())
print()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
