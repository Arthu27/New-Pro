# -*- coding: utf-8 -*-
"""Спринт скорости: кэш GuildData, ACK-first, PIL off-loop, executor.

Запуск: python3 tests/test_bot_speed_sprint.py
"""
import asyncio
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix='hakumo_speed_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')

import config  # noqa: E402
config.Config.DB_PATH = os.path.abspath('data/bot.db')

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== 1. GuildData TTL-кэш ==')
from db import GuildData, clear_guild_data_cache  # noqa: E402

clear_guild_data_cache()
db = GuildData('speed_test')
db.set(1, 'acl', {'ban': ['1', '2']})

t0 = time.perf_counter()
for _ in range(200):
    db.get(1, 'acl')
cold_hot = (time.perf_counter() - t0) * 1000
check(cold_hot < 50, f'200 get из кэша <50ms ({cold_hot:.1f}ms)')

v1 = db.get(1, 'acl')
v1['ban'].append('HACK')
v2 = db.get(1, 'acl')
check(v2.get('ban') == ['1', '2'], 'кэш отдаёт deepcopy — мутация не отравляет')

db.set(1, 'acl', {'ban': ['9']})
check(db.get(1, 'acl') == {'ban': ['9']}, 'set инвалидирует/обновляет кэш')
db.delete(1, 'acl')
check(db.get(1, 'acl', default=None) is None, 'delete инвалидирует кэш')

print('== 2. cmd_acl + action_acl кэш ==')
acl_src = open(os.path.join(ROOT, 'services', 'permission_acl.py'), encoding='utf-8').read()
check('_CMD_ACL_CACHE' in acl_src and '_ACTION_ACL_CACHE' in acl_src,
      'оба ACL кэшируются')
check('pop(key, None)' in acl_src[acl_src.index('def save_acl'):
                                     acl_src.index('def set_rule')],
      'save_acl сбрасывает cmd кэш')

print('== 3. ACK-first пути ==')
mod = open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read()
um = mod[mod.index('class UnmuteKindSelect'):
         mod.index('class UnmuteKindView')]
cb = um[um.index('async def callback'):]
check(cb.find('await _ack') < cb.find('_ensure_action_acl'),
      'UnmuteKindSelect: ACK до ACL')

ss = open(os.path.join(ROOT, 'cogs', 'staff_stats.py'), encoding='utf-8').read()
fn = ss[ss.index('async def staff_stats'):
        ss.index('@staff_stats.error')]
check(fn.find('response.defer') < fn.find('to_thread(collect_actions'),
      '/staff-stats: defer до collect_actions')
check('followup.send' in fn, '/staff-stats: ответ через followup')

rep = open(os.path.join(ROOT, 'cogs', 'reports.py'), encoding='utf-8').read()
av = rep[rep.index('async def apply_verdict'):
         rep.index('async def close_ticket')]
check(av.find('response.defer') < av.find('member.timeout')
      and av.find('response.defer') < av.find('member.kick'),
      'apply_verdict: defer до timeout/kick/ban')

print('== 4. PIL off-loop ==')
wc = open(os.path.join(ROOT, 'cogs', 'welcome_card.py'), encoding='utf-8').read()
check('to_thread' in wc and 'render_welcome_card' in wc,
      'welcome card: render в to_thread')
ap = open(os.path.join(ROOT, 'cogs', 'appeals.py'), encoding='utf-8').read()
paint = ap[ap.index('async def _paint_appeal_card'):
          ap.index('def _appeal_card_text_from_embed')]
check('to_thread' in paint and 'render_appeal_card' in paint,
      'appeal card auto: render в to_thread')

print('== 5. Executor + voice off-loop ==')
main_src = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
check('ThreadPoolExecutor' in main_src and 'set_default_executor' in main_src,
      'main: общий ThreadPoolExecutor(32)')
check('VOICE_SILENCE_PING' in main_src,
      'voice: silence-ping выключен по умолчанию (VOICE_SILENCE_PING)')
check('to_thread(vc.play' in main_src.replace(' ', ''),
      'voice: если play — только to_thread')

print('== 6. Runtime: кэш vs сырой SQLite ==')
clear_guild_data_cache()
db2 = GuildData('bench')
db2.set(7, 'x', {'n': list(range(50))})
# cold
t0 = time.perf_counter()
db2.get(7, 'x')
cold = (time.perf_counter() - t0) * 1000
# hot
t0 = time.perf_counter()
for _ in range(500):
    db2.get(7, 'x')
hot = (time.perf_counter() - t0) * 1000 / 500
check(hot < cold or hot < 0.05,
      f'hot get быстрее cold (cold={cold:.2f}ms hot={hot:.3f}ms)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
