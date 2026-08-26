# -*- coding: utf-8 -*-
"""Личная /modpanel, тумблер «демка обязательна», умная модалка и нормальные ID.

Запуск: python3 tests/test_modpanel_ux.py
"""
import asyncio
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_modpanel_ux_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['DEMO_MODE'] = '1'
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'preview123'
os.environ['MAIN_GUILD_ID'] = '987654321098765432'

import discord  # noqa: E402

from cogs.proof_cog import (proof_is_required, proof_set_required,
                            require_proof)  # noqa: E402
from cogs.moderation import Moderation, ModActionModal, ModActionSelect  # noqa: E402
from cogs.mod_tools import ReasonModal  # noqa: E402

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


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class FakeUser:
    def __init__(self, uid, name, display=None, gname=None, roles=()):
        self.id = uid
        self.name = name
        self.display_name = display or name
        self.global_name = gname
        self.roles = list(roles)
        self.bot = False
        self.mention = f'<@{uid}>'

    def __str__(self):
        return self.name


class FakeGuild:
    def __init__(self, gid=777, members=()):
        self.id = gid
        self.name = 'TestHall'
        self.icon = None
        self.members = list(members)


class FakeResp:
    def __init__(self):
        self.sent = []
        self.deferred = None

    async def send_message(self, content=None, embed=None, ephemeral=False, **kw):
        self.sent.append({'content': content, 'embed': embed, 'ephemeral': ephemeral})

    async def send(self, content=None, embed=None, ephemeral=False, **kw):
        await self.send_message(content=content, embed=embed, ephemeral=ephemeral)

    async def defer(self, ephemeral=False):
        self.deferred = ephemeral

    def is_done(self):
        return bool(self.sent) or self.deferred is not None


class FakeInter:
    def __init__(self, guild, user):
        self.guild = guild
        self.user = user
        self.response = FakeResp()
        self.followup = FakeResp()


class FakeBot:
    def get_cog(self, name):
        return None


GID = 9876543210
MOD = FakeUser(5001, 'warden')
GUILD = FakeGuild(GID, [MOD])

cog = Moderation(FakeBot())

# ═══ 1. Переключатель «демка обязательна» ═════════════════════════════════
print('== тумблер «демка обязательна» ==')
check(proof_is_required(GID) is True, 'по умолчанию требование включено')
check(proof_set_required(GID, False) is False, 'выключение сохранилось')
check(proof_is_required(GID) is False, 'после выключения чтение даёт False')
check(proof_set_required(GID, True) is True, 'включение обратно работает')
check(proof_is_required(GID) is True, 'после включения чтение даёт True')

# require_proof уважает выключатель
inter = FakeInter(GUILD, MOD)
proof_set_required(GID, True)
check(run(require_proof(inter, action_ru='бан')) is False,
      'вкл: без демки наказание блокируется')
_emb = inter.followup.sent[-1]['embed'] if inter.followup.sent else None
check(_emb is not None and 'Доказательства' in (_emb.footer.text or ''),
      'отказ подсказывает, где выключить требование (панель)')

inter2 = FakeInter(GUILD, MOD)
proof_set_required(GID, False)
check(run(require_proof(inter2, action_ru='бан')) is True,
      'выкл: наказание проходит без демки')
check(not inter2.followup.sent and not inter2.response.sent,
      'выкл: никаких отказов в лицо модератору')
check(run(require_proof(FakeInter(GUILD, MOD), action_ru='бан', link='https://x/p.png')) is True,
      'выкл: валидная ссылка тоже проходит')
proof_set_required(GID, True)

# кривая ссылка не считается доказательством
inter3 = FakeInter(GUILD, MOD)
check(run(require_proof(inter3, action_ru='кик', link='просто слова')) is False,
      'не-ссылка («просто слова») не засчитывается за демку')
_emb3 = inter3.followup.sent[-1]['embed']
check('не похожа на ссылку' in (_emb3.description or ''),
      'отказ честно говорит, что ссылка кривая')

# ═══ 2. /modpanel — личная панель ═════════════════════════════════════════
print('== /modpanel — видит только вызвавший ==')
inter4 = FakeInter(GUILD, MOD)
run(Moderation.modpanel.callback(cog, inter4))
sent = inter4.response.sent[-1]
check(sent['ephemeral'] is True, 'панель модерации отправляется ephemeral (личная)')
check('видите только вы' in (sent['embed'].footer.text or ''),
      'футер честно говорит «видите только вы»')

# ═══ 3. Модалка: поля строго под действие ═════════════════════════════════
print('== модалка: поля под действие ==')


def fields(modal):
    return {it.label for it in modal.children}


proof_set_required(GID, True)
m_clear = ModActionModal(cog, 'clear', guild=GUILD)
check('Цель (@ник, точное имя или ID)' not in fields(m_clear),
      'очистка: поля «Цель» нет (не к кому применять)')
check('Сколько сообщений удалить?' in fields(m_clear),
      'очистка: спрашивает только «сколько удалить»')
check(not any('Доказательство' in f for f in fields(m_clear)),
      'очистка: доказательство НЕ спрашивается (было лишним)')

m_unban = ModActionModal(cog, 'unban', guild=GUILD)
check('Цель (@ник, точное имя или ID)' in fields(m_unban)
      and not any('Доказательство' in f for f in fields(m_unban))
      and not any('На сколько минут?' == f for f in fields(m_unban)),
      'разбан: только цель + причина, без демки и минут')

m_ban = ModActionModal(cog, 'ban', guild=GUILD)
check(any('Доказательство' in f and 'ссылка' in f for f in fields(m_ban)),
      'бан (вкл. требование): поле демки есть и обязательно')
proof_item = [it for it in m_ban.children if 'Доказательство' in it.label][0]
check(proof_item.required is True, 'бан: поле демки обязательное')

m_kick = ModActionModal(cog, 'kick', guild=GUILD)
check('На сколько минут?' not in fields(m_kick),
      'кик: минуты не спрашиваются (бессмысленны)')

m_vmute = ModActionModal(cog, 'vmute', guild=GUILD)
check('На сколько минут?' in fields(m_vmute), 'войс-мут: минуты спрашиваются')

# при выключенном требовании поле демки исчезает из модалок
proof_set_required(GID, False)
m_ban2 = ModActionModal(cog, 'ban', guild=GUILD)
check(not any('Доказательство' in f for f in fields(m_ban2)),
      'тумблер выкл: у бана поле демки пропадает')
rm_off = ReasonModal('Кик из войса: X', None, require_proof=True, guild=GUILD)
check(not hasattr(rm_off, 'proof'),
      'тумблер выкл: ReasonModal (ПКМ-кик из войса) без поля демки')
proof_set_required(GID, True)
rm_on = ReasonModal('Кик из войса: X', None, require_proof=True, guild=GUILD)
check(hasattr(rm_on, 'proof') and rm_on.proof.required is True,
      'тумблер вкл: ReasonModal снова требует демку')

# ═══ 4. Поиск цели: @упоминание, точный ник, ID ═══════════════════════════
print('== поиск цели по @нику/имени/ID ==')
NEO = FakeUser(900000000000000001, 'Neo', display='Neo The Chosen', gname='Neon')
TRIN = FakeUser(900000000000000002, 'Trinity')
GUILD2 = FakeGuild(GID, [MOD, NEO, TRIN])

u, uid = cog._resolve_member(GUILD2, '<@900000000000000001>')
check(u is NEO and uid == NEO.id, 'упоминание <@id> находит участника')
u, uid = cog._resolve_member(GUILD2, '900000000000000002')
check(u is TRIN and uid == TRIN.id, 'голый ID находит участника')
u, uid = cog._resolve_member(GUILD2, '@neo')
check(u is NEO, 'ник с @ находит по username (без регистра)')
u, uid = cog._resolve_member(GUILD2, 'neo the chosen')
check(u is NEO, 'отображаемое имя тоже работает')
u, uid = cog._resolve_member(GUILD2, 'neon')
check(u is NEO, 'global_name тоже ловится')
u, uid = cog._resolve_member(GUILD2, 'Smith')
check(u is None and uid is None, 'неизвестный ник → (None, None), не мусор')
u, uid = cog._resolve_member(GUILD2, 'n')
check(u is None, '1 символ — слишком коротко, не угадываем')
u, uid = cog._resolve_member(GUILD2, '')
check(u is None and uid is None, 'пустая строка → (None, None)')

# неоднозначность не навредит
NEO2 = FakeUser(900000000000000003, 'neo', gname='Neo')
GUILD3 = FakeGuild(GID, [NEO, NEO2])
u, uid = cog._resolve_member(GUILD3, 'neo')
check(u is None and uid is None, 'двое с одинаковым ником → честный None (мод уточнит)')

# ═══ 5. Панель: API тумблера ═══════════════════════════════════════════════
print('== панель: /api/proof-required ==')
from web.app import app as _flask_app  # noqa: E402
client = _flask_app.test_client()

with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'UyeGuy'
    s['role'] = 'uye'
r = client.get('/api/proof-required')
check(r.status_code == 403, 'uye (без прав модератора) к тумблеру не подпускают')


def login(username, role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = username
        s['role'] = role
    return client


mod = login('owner', 'mod')
r = mod.get('/api/proof-required')
check(r.status_code == 200 and r.get_json().get('required') is True,
      'mod видит положение тумблера (GET)')
r = mod.post('/api/proof-required', json={'required': False})
check(r.status_code == 403, 'mod НЕ может переключать (только admin+)')

adm = login('owner', 'admin')
r = adm.post('/api/proof-required', json={'required': False})
j = r.get_json()
check(r.status_code == 200 and j.get('success') and j.get('required') is False,
      'admin выключил требование (POST)')
r = adm.get('/api/proof-required')
check(r.get_json().get('required') is False, 'положение сохранилось (GET после POST)')
r = adm.post('/api/proof-required', json={'required': True})
check(r.get_json().get('required') is True, 'admin включил обратно')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
