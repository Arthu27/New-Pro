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
        self.fail_first = 0      # упасть ровно столько РАЗ (сетевая моргнула)
        self.fail_global = False      # глобальная очистка всегда падает
        self.fail_first_global = 0    # глобальная очистка падает N раз подряд

    @staticmethod
    def _ok(app_id, payload):
        # настоящий Discord возвращает команды с id/application_id — и с
        # description даже у контекстных меню (пустой строкой). discord.py
        # после upsert парсит ответ AppCommand(data=...) и требует эти поля:
        # без этого синк «падал» уже ПОСЛЕ доставки команд в Discord.
        out = []
        for i, p in enumerate(payload or []):
            d = dict(p, id=9000 + i, application_id=app_id)
            d.setdefault('description', '')
            d.setdefault('type', 1)
            out.append(d)
        return out

    async def bulk_upsert_global_commands(self, app_id, payload=None):
        if self.fail_global:
            raise RuntimeError('429 (мок: глобальный рейт-лимит)')
        if self.fail_first_global > 0:
            self.fail_first_global -= 1
            raise RuntimeError('EOFError: сеть моргнула (мок: разовый сбой)')
        names = [p['name'] for p in (payload or [])]
        self.calls.append(('GLOBAL', None, names))
        return self._ok(app_id, payload)

    async def bulk_upsert_guild_commands(self, app_id, guild_id, payload=None):
        if self.fail_guilds:
            raise RuntimeError('429 Too Many Requests (мок: как Discord)')
        if self.fail_first > 0:
            self.fail_first -= 1
            raise RuntimeError('EOFError: замерзание event-loop (мок: разовый сбой)')
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
    # Контекстное меню НЕ в белом списке боевых команд — в Discord не публикуется.
    tree.add_command(ContextMenu(name='Варн за сообщение', callback=_msg_cb,
                                 type=AppCommandType.message))
    # гильдовые (коги с guilds=Config.guild_objects()):
    #   боевые (modpanel, afk, report) — публикуются;
    #   служебные/вырезанные (play, afk-remove, ticket-panel) — снимаются с публикации.
    for n in ('modpanel', 'play', 'afk', 'report', 'afk-remove', 'ticket-panel'):
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
    # Глобально живут keep_global команды из белого списка (работают в ЛС):
    # апелляция и update. Остальное — только гильдовое.
    check(set(glob) == {'апелляция', 'update'},
          f'глобальный список = keep_global из белого списка ({glob})')
    check(set(glob) <= set(SF.PUBLIC_COMMAND_WHITELIST),
          'глобально нет команд вне белого списка')
    check(set(glob) & set(guild) == set(),
          f'пересечение глобаль∩гильдия пустое — дублей нет ({sorted(set(glob) & set(guild))})')
    # Белый список: в Discord публикуются ТОЛЬКО шесть боевых команд.
    # Служебные/вырезанные (play, afk-remove, ticket-panel) и контекстные
    # меню в боевом составе не публикуются вовсе.
    _wl = set(SF.PUBLIC_COMMAND_WHITELIST)
    check(set(guild) <= _wl,
          f'в гильдии только команды белого списка, лишних нет ({sorted(set(guild) - _wl)})')
    check({'modpanel', 'afk', 'report'} <= set(guild),
          f'боевые гильдовые команды на месте ({guild})')
    for _hidden in ('play', 'afk-remove', 'ticket-panel', 'Варн за сообщение'):
        check(_hidden not in guild and _hidden not in glob,
              f'«{_hidden}» не публикуется в Discord (не в белом списке)')
    check(rec.last('GUILD', 888) == [],
          'чужая гильдия 888 очищена от устаревших копий')

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
    # Тумблер проверяем на БОЕВОЙ команде из белого списка (/report):
    # небоевые вроде play и так не публикуются, их выключение не показательно.
    CSW.set_disabled('report', True)
    await SF.full_sync(bot4)
    guild_off = rec4.last('GUILD', 777)
    check('report' not in guild_off, '/report исчез из гильдии после выключения')
    check(set(rec4.last('GLOBAL')) & set(guild_off) == set(), 'дублей нет')
    CSW.set_disabled('report', False)
    await SF.full_sync(bot4)
    guild_on = rec4.last('GUILD', 777)
    check('report' in guild_on, '/report вернулся после включения')
    check(set(rec4.last('GLOBAL')) & set(guild_on) == set(), 'и снова ноль дублей')
    # небоевые команды не публикуются ни при каком положении тумблера
    check('play' not in guild_on and 'ticket-panel' not in guild_on,
          'служебные/вырезанные команды не попадают в Discord (белый список)')

    # ═══ F. Разовый сбой — ретрай доводит команды до сервера ═══════════════
    print('== F. Сеть моргнула один раз — ретрай спасает синк ==')
    bot5 = build_bot()
    rec5 = bot5.http
    await SF.full_sync(bot5)                # успешный старт
    rec5.fail_first = 1                     # первый guild-вызов падает
    rec5.calls.clear()
    await SF.full_sync(bot5)                # владелец снова жмёт синк
    guild5 = rec5.last('GUILD', 777)
    check(guild5 != [], 'после разового сбоя РЕТРАЙ доставил команды на сервер '
                        '(иначе — старое меню из 33 команд)')
    check(rec5.calls.count(('GUILD', 777, guild5)) == 1,
          'вторая попытка записана ровно один раз (третья не понадобилась)')
    check(set(rec5.last('GLOBAL')) & set(guild5) == set(), 'дублей нет')

    # полный отказ сети: sync_last.json называет сервер, которому не доехало
    rec5.fail_guilds = True
    await SF.full_sync(bot5)
    import json as _json  # noqa: F811 (используется и секцией G)
    with open(os.path.join(os.getcwd(), 'data', 'sync_last.json'),
              encoding='utf-8') as fh:
        sync_last = _json.load(fh)
    check(sync_last.get('failed_guilds') == [777],
          f'sync_last.json называет упавший сервер ({sync_last.get("failed_guilds")})')
    check(sync_last.get('mode') == 'guilds' and sync_last.get('targets') == [777],
          'режим и цели записаны как раньше (обратная совместимость)')

    # ═══ G. Глобальная очистка падает — ретраи спасают, откат честный ════
    print('== G. Глобальная очистка: разовый сбой и полный отказ ==')
    bot6 = build_bot()
    rec6 = bot6.http
    rec6.fail_first_global = 1             # первый GLOBAL-вызов падает
    await SF.full_sync(bot6)
    check(rec6.last('GUILD', 777) != [],
          'разовый сбой глобальной очистки пережит РЕТРАЕМ — синк дошёл до серверов')
    check(rec6.last('GLOBAL') == ['апелляция', 'update'],
          'и глобальный список в итоге опубликован (keep_global)')
    check(set(rec6.last('GLOBAL')) & set(rec6.last('GUILD', 777)) == set(),
          'дублей нет')

    bot7 = build_bot()
    rec7 = bot7.http
    rec7.fail_global = True                # Discord рейт-лимитит всё
    rec7.calls.clear()
    await SF.full_sync(bot7)
    check(not any(s_ == 'GUILD' for s_, g_, n_ in rec7.calls),
          'полный отказ очистки → guild-синки не тронуты (дублей не будет)')
    with open(os.path.join(os.getcwd(), 'data', 'sync_last.json'),
              encoding='utf-8') as fh:
        sync_last7 = _json.load(fh)
    check(sync_last7.get('mode') == 'failed-global-clear',
          f'режим честно записан: failed-global-clear ({sync_last7.get("mode")})')
    check(bool(sync_last7.get('error')),
          f'причина сбоя записана в sync_last.json ({sync_last7.get("error")})')

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
