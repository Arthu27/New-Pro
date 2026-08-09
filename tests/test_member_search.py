# -*- coding: utf-8 -*-
"""Тесты хелперов поиска участников: нормализация запроса, релевантный скоринг,
пайлоады и нормализаторы записей варнов/кейсов.

Запуск:  python3 tests/test_member_search.py
"""
import os, sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs('data', exist_ok=True)
sys.path.insert(0, _REPO)

PASS = 0; FAIL = 0

def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1; print(f'  PASS: {msg}')
    else:
        FAIL += 1; print(f'  FAIL: {msg}')


print('== Поиск участников — хелперы ==')

from web.routes_extra import (
    ms_normalize_query, ms_member_match, ms_search_members,
    ms_member_payload, ms_normalize_warn, ms_normalize_case,
)


class FakeAvatar:
    url = 'https://cdn.discordapp.com/avatars/1/a.png'


class FakeMember:
    def __init__(self, mid, name, display=None, nick=None, status='online', bot=False, global_name=None):
        self.id = mid
        self.name = name
        self._display = display if display is not None else (nick or name)
        self.nick = nick
        self.status = status
        self.bot = bot
        self.global_name = global_name
        self.display_avatar = FakeAvatar()

    @property
    def display_name(self):
        return self._display


# ── нормализация запроса ────────────────────────────────────────────────────
check(ms_normalize_query('  ToPrAk  ') == 'toprak', 'запрос: пробелы и регистр чистятся')
check(ms_normalize_query('<@123456789>') == '123456789', 'запрос: упоминание <@id> -> id')
check(ms_normalize_query('<@!123456789>') == '123456789', 'запрос: упоминание <@!id> -> id')
check(ms_normalize_query('@ivan') == 'ivan', 'запрос: ведущая @ срезается')
check(ms_normalize_query(None) == '', 'запрос: None -> пустая строка')
check(ms_normalize_query('') == '', 'запрос: пустая строка -> пустая строка')
check(ms_normalize_query(123) == '123', 'запрос: число -> строка')

# ── скоринг совпадения ──────────────────────────────────────────────────────
m1 = FakeMember(9001, 'toprak', nick='Toprak')
m2 = FakeMember(9002, 'topra', nick='Top')
m3 = FakeMember(9003, 'irina', nick='Просто Топрак')
bot1 = FakeMember(9004, 'bot.helper', bot=True)

check(ms_member_match('', m1) == 0, 'скоринг: пустой запрос -> 0')
check(ms_member_match('9001', m1) == 500, 'скоринг: точный ID -> 500')
check(ms_member_match('900', m1) == 200, 'скоринг: начало ID -> 200')
check(ms_member_match('toprak', m1) == 400, 'скоринг: точное имя -> 400')
check(ms_member_match('top', m1) == 150, 'скоринг: начало ника -> 150')
check(ms_member_match('pra', m2) == 100, 'скоринг: вхождение подстроки -> 100')
check(ms_member_match('просто топрак', m3) == 400, 'скоринг: русский ник, точное -> 400')
check(ms_member_match('топрак', m3) == 100, 'скоринг: русский ник, вхождение -> 100')
check(ms_member_match('xyz', m1) == 0, 'скоринг: несовпадение -> 0')
check(ms_member_match('bot', bot1) == 150, 'скоринг: имя бота тоже ищется')

# ── поиск с сортировкой ─────────────────────────────────────────────────────
members = [m2, m3, m1, bot1]
res = ms_search_members(members, 'toprak')
check(len(res) == 1 and res[0] is m1, 'поиск: точное имя находится')
res = ms_search_members(members, 'top')
check(len(res) == 2 and res[0] is m2, 'поиск: старт с самого релевантного ника')
res = ms_search_members(members, 'топ')
check(len(res) == 1 and res[0] is m3, 'поиск: кириллический ник находится')
res = ms_search_members(members, '<@9002>')
check(len(res) == 1 and res[0] is m2, 'поиск: упоминание находит участника')
res = ms_search_members(members, '9004')
check(len(res) == 1 and res[0] is bot1, 'поиск: по ID находит бота')
check(ms_search_members(members, '') == [], 'поиск: пустой запрос -> пусто')
check(len(ms_search_members(members, 'top', limit=2)) == 2, 'поиск: лимит соблюдается')
check(ms_search_members(None, 'top') == [], 'поиск: None-список не падает')

# ── пайлоад карточки ────────────────────────────────────────────────────────
p = ms_member_payload(m1)
check(p['id'] == '9001' and p['name'] == 'toprak', 'пайлоад: id и name')
check(p['display_name'] == 'Toprak' and p['nickname'] == 'Toprak', 'пайлоад: display_name и nick')
check(p['status'] == 'online' and p['is_bot'] is False, 'пайлоад: статус и флаг бота')
check(p['avatar'].startswith('https://'), 'пайлоад: аватар-URL')

class NoAvatar:
    id = 777; name = 'nula'; display_name = 'Nula'; nick = None
    status = 'offline'; bot = False; global_name = None; display_avatar = None
check(ms_member_payload(NoAvatar())['avatar'] is None, 'пайлоад: без аватара -> None')

# ── нормализация варнов ─────────────────────────────────────────────────────
w = ms_normalize_warn({'id': 2, 'reason': 'флуд', 'mod': 'ivan', 'timestamp': '2026-08-01T10:00:00'}, 1)
check(w['id'] == 2 and w['reason'] == 'флуд' and w['mod'] == 'ivan', 'варн: полные данные')
w = ms_normalize_warn({}, 5)
check(w['id'] == 5 and w['reason'] == '—' and w['timestamp'] == '', 'варн: пустой -> умолчания')
w = ms_normalize_warn('старое текстовое предупреждение', 3)
check(w['id'] == 3 and 'старое' in w['reason'], 'варн: строка -> reason')

# ── нормализация кейсов ─────────────────────────────────────────────────────
c = ms_normalize_case({'action': 'BAN', 'reason': 'рейд', 'mod_id': 42, 'timestamp': '2026-08-02T00:00:00'}, 1)
check(c['action'] == 'BAN' and c['mod'] == '42' and c['reason'] == 'рейд', 'кейс: полные данные')
c = ms_normalize_case({'type': 'mute'}, 7)
check(c['id'] == 7 and c['action'] == 'mute' and c['reason'] == '—', 'кейс: type как action, умолчания')
c = ms_normalize_case('просто строка', 4)
check(c['id'] == 4 and c['action'] == '?' and 'строка' in c['reason'], 'кейс: строка -> reason')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
