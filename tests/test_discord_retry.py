# -*- coding: utf-8 -*-
"""Ретраи Discord 503.

Запуск: python3 tests/test_discord_retry.py
"""
import asyncio
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_retry_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services.discord_retry import call, friendly_api_error, _is_retryable  # noqa: E402

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


class Fake503(Exception):
    pass


# emulate DiscordServerError-like via message
class Boom(Exception):
    def __init__(self, msg):
        self.status = 503
        super().__init__(msg)


async def main():
    print('== retryable detection ==')
    check(_is_retryable(Boom('503 Service Unavailable: upstream connect')),
          '503 retryable')
    check(not _is_retryable(ValueError('nope')), 'ValueError not retryable')
    check('Discord' in friendly_api_error(Boom('upstream connect error')),
          'friendly message')

    print('== call retries then ok ==')
    state = {'n': 0}

    async def flaky():
        state['n'] += 1
        if state['n'] < 3:
            raise Boom('503 upstream connect error')
        return 'ok'

    got = await call(flaky, attempts=3, delays=(0.01, 0.01, 0.01))
    check(got == 'ok' and state['n'] == 3, f'retried to success n={state["n"]}')

    print('== call gives up ==')
    state['n'] = 0

    async def always():
        state['n'] += 1
        raise Boom('503 connection termination')

    try:
        await call(always, attempts=2, delays=(0.01, 0.01))
        check(False, 'should raise')
    except Boom:
        check(state['n'] == 2, f'gave up after 2 (n={state["n"]})')

    print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
    return 1 if FAIL else 0


sys.exit(asyncio.run(main()))
