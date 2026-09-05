# -*- coding: utf-8 -*-
"""Регистрация/вход: Discord ID, тег <@id>, ник — без Flask.
Запуск: python3 tests/test_register_lookup.py
"""
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_reg_lookup_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


src = open(os.path.join(ROOT, 'web/app.py'), encoding='utf-8').read()
a = src.find('def _extract_discord_snowflake')
b = src.find('\ndef _resolve_nick_anywhere')
assert a > 0 and b > a, 'не нашёл хелперы регистрации в web/app.py'
ns = {'re': re, 'json': __import__('json')}
exec(src[a:b], ns)
extract = ns['_extract_discord_snowflake']
resolve = ns['_resolve_member_key']

SID = '987430047889637426'

print('== 1. Snowflake из ID / тега ==')
check(extract(SID) == SID, 'голый Discord ID')
check(extract(f'<@{SID}>') == SID, 'тег <@id>')
check(extract(f'<@!{SID}>') == SID, 'тег <@!id> (никнейм)')
check(extract(f'привет <@{SID}>!') == SID, 'тег внутри фразы')
check(extract('@alex') is None, 'ник без цифр — не snowflake')
check(extract('12345') is None, 'короткое число — не snowflake')

print('== 2. Ключ в members.json по нику / ID / тегу ==')
members = {
    SID: {'display_name': 'Ваня', 'name': 'vanya', 'username': 'vanya'},
    '3002': {'display_name': 'Анна', 'name': 'anna'},
}
check(resolve(members, SID) == SID, 'логин = ID')
check(resolve(members, f'<@{SID}>') == SID, 'логин = тег себя')
check(resolve(members, 'Ваня') == SID, 'логин = display_name')
check(resolve(members, '@vanya') == SID, 'логин = @username')
check(resolve(members, 'VANYA') == SID, 'без учёта регистра')
check(resolve(members, 'никого') is None, 'неизвестный ник → None')

print('== 3. Регистрация использует те же хелперы ==')
check('_extract_discord_snowflake (discord_id )' in src
      or '_extract_discord_snowflake(discord_id)' in src.replace(' ', ''),
      'POST /register вытаскивает ID из тега')
check('_resolve_nick_anywhere' in src and 'member_store' in src,
      'ник ищется и в составе на диске')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
