# -*- coding: utf-8 -*-
"""Бот всегда честно говорит, когда прав не хватает — по-русски и без дублей.

Сценарии: у юзера нет Discord-прав / у бота нет прав / ACL уже ответил
(без второго сообщения) / проверка не пройдена молча.
Запуск: python3 tests/test_bot_denials.py
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(tempfile.mkdtemp(prefix='hakumo_denial_'))

PASS = 0
FAIL = 0


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label}')


import discord
from discord import app_commands
import error_handler as EH


class FakeResponse:
    def __init__(self):
        self.done_flag = False
        self.sent = []

    def is_done(self):
        return self.done_flag

    async def send_message(self, content=None, embed=None, ephemeral=False):
        self.done_flag = True
        self.sent.append(embed)


class FakeFollowup:
    def __init__(self, resp):
        self._r = resp

    async def send(self, content=None, embed=None, ephemeral=False):
        self._r.sent.append(embed)


class FakeInteraction:
    def __init__(self):
        self.response = FakeResponse()
        self.followup = FakeFollowup(self.response)
        self.command = None


async def main():
    h = EH.ErrorHandler.__new__(EH.ErrorHandler)

    it = FakeInteraction()
    await h.handle_app_command_error(
        it, app_commands.MissingPermissions(['ban_members', 'manage_messages']))
    e = it.response.sent[0]
    check(e is not None and 'Бан участников' in e.description
          and 'Управление сообщениями' in e.description,
          'юзеру: каких прав не хватает — по-русски')
    check('Настройки сервера' in e.description, 'юзеру: подсказка, кто и где выдаёт')

    it2 = FakeInteraction()
    await h.handle_app_command_error(
        it2, app_commands.BotMissingPermissions(['manage_webhooks']))
    e2 = it2.response.sent[0]
    check('Управление вебхуками' in e2.description, 'боту: права по-русски')

    it3 = FakeInteraction()
    it3.response.done_flag = True  # проверка доступа уже сама ответила
    await h.handle_app_command_error(it3, app_commands.CheckFailure())
    check(not it3.response.sent, 'ACL ответил сам — второго сообщения нет')

    it4 = FakeInteraction()
    await h.handle_app_command_error(it4, app_commands.CheckFailure())
    e4 = it4.response.sent[0]
    check('Права команд' in e4.description,
          'проверка не пройдена молча — бот объясняет, где настраивается доступ')


asyncio.run(main())

print('== ACL-сообщения main.py: без эмодзи, с именем команды ==')
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'main.py'), encoding='utf-8').read()
check('Недостаточно прав: команда /' in src, 'slash-отказ: имя команды + куда идти')
check('У вас нет доступа к команде ' in src, 'prefix-отказ: имя команды')
check('🚫' not in src and '⏸' not in src, 'классические эмодзи убраны')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
