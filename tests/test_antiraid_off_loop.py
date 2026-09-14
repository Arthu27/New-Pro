# -*- coding: utf-8 -*-
"""Антирейд не морозит Discord: диск config_watcher в to_thread.

Инцидент 2026-09-13: EVENT-LOOP ЗАВИСАНИЕ 38.7с — СТЕК ВИНОВНИКА:
  antiraid.config_watcher → GuildAntiraidConfig.reload → os.path.exists
На Windows/антивирусе sync exists/open на main-потоке рвал шлюз Discord
(обрывов gateway: 118). Watcher и listeners должны уводить диск в поток.

Запуск: python3 tests/test_antiraid_off_loop.py
"""
import ast
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_antiraid_off_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


SRC = open(os.path.join(ROOT, 'cogs', 'antiraid.py'), encoding='utf-8').read()

print('== 1. config_watcher не зовёт reload/listdir на loop ==')
# тело async-метода config_watcher
a = SRC.find('async def config_watcher')
b = SRC.find('@config_watcher.before_loop')
body = SRC[a:b]
check('asyncio.to_thread' in body and '_reload_pass_sync' in body,
      'config_watcher уводит диск в to_thread(_reload_pass_sync)')
check('.reload()' not in body,
      'в async config_watcher нет прямого .reload()')
check('os.listdir' not in body,
      'в async config_watcher нет os.listdir')

print('== 2. sync-проход содержит disk I/O ==')
check('def _reload_pass_sync' in SRC, '_reload_pass_sync есть')
sync_a = SRC.find('def _reload_pass_sync')
sync_b = SRC.find('@tasks.loop', sync_a)
sync_body = SRC[sync_a:sync_b]
check('.reload()' in sync_body and 'os.listdir' in sync_body,
      '_reload_pass_sync делает reload + listdir (в потоке)')

print('== 3. listeners читают/пишут через async-обёртки ==')
for name in ('on_member_join', 'on_member_update', 'on_bulk_message_delete'):
    ia = SRC.find(f'async def {name}')
    ib = SRC.find('\n    @commands.Cog.listener()', ia + 1)
    if ib < 0:
        ib = SRC.find('\nasync def setup', ia)
    chunk = SRC[ia:ib]
    check('await self._aget_config' in chunk,
          f'{name}: _aget_config (не sync get_config)')
    if 'add_event' in chunk or '_aadd_event' in chunk:
        check('await self._aadd_event' in chunk and 'cfg.add_event(' not in chunk,
              f'{name}: _aadd_event вместо sync add_event')

print('== 4. AST: to_thread рядом с _reload_pass_sync ==')
tree = ast.parse(SRC)
found = False
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        func = node.func
        # asyncio.to_thread(self._reload_pass_sync)
        if isinstance(func, ast.Attribute) and func.attr == 'to_thread':
            if node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.Attribute) and arg0.attr == '_reload_pass_sync':
                    found = True
check(found, 'AST: asyncio.to_thread(self._reload_pass_sync)')

print('== 5. runtime: reload_pass не падает на пустом data/ ==')
from cogs.antiraid import AntiRaid  # noqa: E402


class _Bot:
    pass


cog = AntiRaid.__new__(AntiRaid)
cog.bot = _Bot()
cog.configs = {}
cog.join_tracker = {}
cog._reload_pass_sync()
check(True, '_reload_pass_sync на пустом data/ отрабатывает')

# файл гильдии подхватывается
open('data/antiraid_424242.json', 'w', encoding='utf-8').write(
    '{"join_raid": true, "join_threshold": 3}')
cog._reload_pass_sync()
check(424242 in cog.configs, 'новый antiraid_<gid>.json подхватывается')
check(cog.configs[424242].data.get('join_raid') is True,
      'конфиг прочитан с диска')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
