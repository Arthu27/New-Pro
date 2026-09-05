# -*- coding: utf-8 -*-
"""Очистка в /modpanel: лимит считает ОПЕРАЦИИ, отказ не врёт «исчерпан».

Жалоба 2026-09-05: «очистка сообщений не работает — лимит исчерпан»,
хотя чистить ещё не пробовали. Причина: в квоту «10/день» писали ЧИСЛО
сообщений (модалка default 10, placeholder «например: 25») — used=0 + 25
> 10 давало «Лимит исчерпан … использовано 0, осталось 10».

Контракт теперь:
  • /modpanel проверяет и пишет 1 хит за чистку, сколько бы сообщений
    ни сняли за раз;
  • «исчерпан» только когда остаток = 0.

Запуск: python3 tests/test_modpanel_clear_quota.py
"""
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_clear_quota_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


from services import staff_limits as SL  # noqa: E402

G, MOD = 88001, 77001

print('== 1. Первая чистка при нулевом счётчике разрешена ==')
ok, used, lim = SL.check_limit(G, MOD, 'clear', 1)
check(ok and used == 0 and lim == 10,
      f'amount=1, used=0, limit=10 → можно (used={used} lim={lim})')

print('== 2. 10 операций — 11-я запрещена ==')
for _ in range(10):
    SL.record_hit(G, MOD, 'clear', 1)
ok11, used11, lim11 = SL.check_limit(G, MOD, 'clear', 1)
check((not ok11) and used11 == 10 and lim11 == 10,
      f'11-я чистка запрещена (used={used11}/{lim11})')

print('== 3. Отказ честный ==')
txt0 = SL.limit_deny_text('clear', used=0, limit=10, amount=25)
check('исчерпан' not in txt0.lower(),
      f'used=0 не говорит «исчерпан»: {txt0}')
check('осталось 10' in txt0 and '25' in txt0,
      f'used=0 объясняет «запросили 25, осталось 10»: {txt0}')
txt10 = SL.limit_deny_text('clear', used=10, limit=10, amount=1)
check('исчерпан' in txt10.lower(),
      f'остаток 0 — «исчерпан»: {txt10}')

print('== 4. /modpanel не ставит число сообщений в квоту ==')
src = open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read()
check('_sl_amt =1' in src,
      '/modpanel пишет _sl_amt = 1 (одна операция)')
check("'clear',len (deleted )" not in src and "'clear', len(deleted)" not in src,
      'record_hit clear больше не принимает len(deleted)')
check("'clear',1 )" in src or "'clear', 1)" in src,
      'успешная чистка пишет 1 хит')
check('например: 25' not in src,
      'модалка больше не подсказывает 25 (это сразу било старую квоту 10 сообщ.)')

print('== 5. Панель /purge тоже считает операцию ==')
web = open(os.path.join(ROOT, 'web', 'routes', 'member_ops.py'), encoding='utf-8').read()
check("_panel_limit_deny (bot ,int (guild_id ),_acl_m ,'clear',1)" in web
      or "_panel_limit_deny(bot, int(guild_id), _acl_m, 'clear', 1)" in web.replace(' ', ''),
      'веб-purge проверяет clear с amount=1')
check("_panel_limit_record" in web and "'clear',1" in web.replace(' ', ''),
      'веб-purge записывает 1 хит после успеха')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
