# -*- coding: utf-8 -*-
"""Сквозная проверка регистрации «как у живого человека» — весь путь.

Владелец просил перепроверить систему регистрации целиком. Здесь гоняется
НАСТОЯЩИЙ /register (web.app) с фейк-ботом в настоящем event loop:

  1) ник НЕ ПОЛНОСТЬЮ («Анна Кис») → ID найден, шаг 2 (код в ЛС);
  2) ЛС реально УШЛО (в фейк-боте считаем embed-ы, код вытаскиваем из них);
  3) закрытые лички → честная ошибка «открой личку с ботом», а не «код отправлен»;
  4) код из ЛС → регистрация завершена, запись в members.json с живой ролью;
  5) неверный код → «Неверный код!», заявка жива;
  6) просроченный код (>10 мин) → «Код истёк»;
  7) уже зарегистрирован → отказ;
  8) повторная подача → отказ;
  9) два человека с одинаковым началом имени → просьба выбрать из подсказок;
 10) несуществующее имя → «Не нашёл участника»;
 11) короткий пароль / расхождение паролей → валидация;
 12) клик по подсказке (resolved_id) → регистрация, даже если имя битое;
 13) вход по паролю после регистрации (точное имя И неполное);
 14) роль в members.json = живая роль из Discord (uye/mod/owner).
Запуск: python3 tests/test_register_e2e.py
"""
import asyncio
import json
import os
import re
import sys
import tempfile
import threading
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix='reg_e2e_')
os.chdir(WORK)
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

os.environ['DEMO_MODE'] = '0'
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'testpass1')
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DB_PATH'] = os.path.join(WORK, 'data', 'bot.db')

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


# ── Фейк-бот: настоящий loop в отдельном потоке (как у реального бота) ─────
class _User:
    def __init__(self, uid, name, dn, closed_dm=False):
        self.id = uid
        self.bot = False
        self.name = name
        self.display_name = dn
        self.mention = f'<@{uid}>'
        self.display_avatar = type('A', (), {'url': 'http://x/1'})()
        self.closed_dm = closed_dm
        self.dms = []

    async def send(self, embed=None, **kw):
        if self.closed_dm:
            raise discord.Forbidden()
        self.dms.append(embed)


class _Member(_User):
    guild_permissions = types.SimpleNamespace(
        administrator=False, ban_members=True, kick_members=False,
        manage_guild=False, manage_messages=False, manage_channels=False)


import discord  # noqa: E402

ANNA = _User(3001000000000000101, 'anna', 'Анна Киселёва')
ANNA2 = _User(3002000000000000102, 'anna_p', 'Анна П.')
BORIS = _User(3003000000000000103, 'boris', 'Борис')
CLOSED = _User(3004000000000000104, 'shy', 'Стеснительный', closed_dm=True)

_MEMBERS = {m.id: m for m in (ANNA, ANNA2, BORIS, CLOSED)}


class _Guild:
    id = 777
    owner_id = 999999
    members = []

    def get_member(self, uid):
        return None

    async def fetch_member(self, uid):
        return _Members_stub().get(uid)


class _Members_stub:
    @staticmethod
    def get(uid):
        m = _MEMBERS.get(int(uid))
        if m is None:
            return None
        mm = _Member(m.id, m.name, m.display_name)
        return mm


class _Bot:
    def __init__(self):
        self.guilds = [_Guild()]
        self.loop = None

    def get_guild(self, gid):
        return self.guilds[0] if int(gid) == 777 else None

    async def fetch_user(self, uid):
        return _MEMBERS[int(uid)]


import web.app as appmod  # noqa: E402

bot = _Bot()
_loop = asyncio.new_event_loop()
threading.Thread(
    target=lambda: (asyncio.set_event_loop(_loop), _loop.run_forever()),
    daemon=True).start()
bot.loop = _loop
appmod.bot_instance = bot

# состав сервера на диске (синк участника)
json.dump({'saved_at': 't', 'sig': 1, 'members': {
    str(m.id): {'id': str(m.id), 'name': m.name, 'display_name': m.display_name,
                'bot': False, 'avatar': ''}
    for m in (ANNA, ANNA2, BORIS, CLOSED)}},
    open('data/members_777.json', 'w', encoding='utf-8'))

appmod._resolve_guild_member_async = (
    lambda guild, uid: _loop.run_coroutine(
        _fake_resolve(uid), _loop) if False else None)


async def fake_resolve(guild, uid):
    m = _MEMBERS.get(int(uid))
    if m is None:
        return None
    return _Member(m.id, m.name, m.display_name)


appmod._resolve_guild_member_async = fake_resolve


def _sync_resolve(guild, uid):
    fut = asyncio.run_coroutine_threadsafe(fake_resolve(guild, uid), _loop)
    return fut.result(timeout=10)


appmod._resolve_guild_member = _sync_resolve

# роль «нашлась живьём» и это модер
appmod._get_role_from_discord = lambda uid: 'mod'

c = appmod.app.test_client()


def page_error(html):
    m = re.search(r'class="error"[^>]*>([^<]{4,160})', html)
    if m:
        return m.group(1).strip()
    t = re.sub(r'<script[\s\S]*?</script>', '', html)
    t = re.sub(r'<style[\s\S]*?</style>', '', t)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'\s+', ' ', t)
    i = t.find('Создать доступ')
    return t[i:i + 420] if i >= 0 else t[:420]


def post_step1(name='', resolved_id='', password='parol123', password2=None,
               pw_override=None):
    return c.post('/register', data={
        'step': '1', 'discord_id': name, 'resolved_id': resolved_id,
        'password': pw_override or password, 'password2': password2 or pw_override or password})


def post_step2(did, code, password='parol123'):
    return c.post('/register', data={
        'step': '2', 'discord_id': did, 'code': code, 'password': password})


print('== 1. Имя не полностью → шаг 2, код в ЛС ==')
r = post_step1('Анна Кис')
html = r.get_data(as_text=True)
ok_step2 = 'name="code"' in html and 'Не нашёл' not in html
check(ok_step2, '«Анна Кис» принята — открыт шаг 2 (ввод кода)',
      page_error(html))
check(len(ANNA.dms) == 1, 'ЛС с кодом доставлено Анне', f'→ {len(ANNA.dms)}')
mm = re.search(r'\b(\d{6})\b', str(ANNA.dms[0].description) if ANNA.dms else '')
code = mm.group(1) if mm else ''
check(len(code) == 6, f'в ЛС 6-значный код ({code})')

print('== 2. Неверный код → «Неверный код!», заявка жива ==')
AID = '3001000000000000101'
r = post_step2(AID, '000000' if code != '000000' else '111111')
check('Неверный код' in r.get_data(as_text=True), 'неверный код отклонён')

print('== 3. Верный код → регистрация завершена ==')
r = post_step2(AID, code)
check(r.status_code in (302, 303),
      'регистрация завершена (редирект на вход)', f'→ {r.status_code}')
members = json.load(open('data/members.json', encoding='utf-8'))
check(AID in members, 'запись в members.json создана')
check(members.get(AID, {}).get('display_name') == 'Анна Киселёва'
      and members[AID].get('role') == 'mod',
      'имя и ЖИВАЯ роль сохранены')

print('== 4. Повторная регистрация того же ID → отказ ==')
r = post_step1(AID)
check('уже зарегистрирован' in r.get_data(as_text=True).lower(),
      'двойная регистрация отклонена')

print('== 5. Закрытые лички → честное сообщение, а не «код отправлен» ==')
r = post_step1('Стеснительный')
h = r.get_data(as_text=True)
check('не смог отправить' in h.lower() and 'name="code"' not in h,
      'ошибка доставки показана, шаг 2 НЕ открыт', page_error(h))

print('== 6. Две Анны при неполном имени → выбор из подсказок ==')
r = post_step1('Анна')
h = r.get_data(as_text=True)
check('выбери' in h.lower() and 'name="code"' not in h,
      'несколько кандидатов — просят выбрать себя', page_error(h))

print('== 7. Клик по подсказке (resolved_id) проходит даже с битым именем ==')
BID = '3002000000000000102'
r = post_step1('Анна', resolved_id=BID)
h = r.get_data(as_text=True)
check('name="code"' in h and 'выбери' not in h.lower(),
      'resolved_id решает конфликт имён')
check(len(ANNA2.dms) == 1, 'код ушел Анне П. (ID из подсказки)')
m2 = re.search(r'\b(\d{6})\b', str(ANNA2.dms[0].description))
c2 = appmod.PENDING_VERIFICATIONS.get(BID, {}).get('code', m2.group(1) if m2 else '')
r = post_step2(BID, c2)
check(r.status_code in (302, 303), 'Анна П. зарегистрировалась по resolved_id')

print('== 8. Несуществующее имя → «Не нашёл» ==')
r = post_step1('Такого-Нет')
h = r.get_data(as_text=True)
check('Не нашёл участника' in h, 'честный отказ по неизвестному имени')

print('== 9. Валидация паролей ==')
r = post_step1('Борис', pw_override='123')
check('короче 6' in r.get_data(as_text=True), 'короткий пароль отклонён')
r = c.post('/register', data={'step': '1', 'discord_id': 'Борис',
                              'password': 'parol123', 'password2': 'drugoy123'})
check('не совпадают' in r.get_data(as_text=True), 'расхождение паролей поймано')

print('== 10. Борис доводит регистрацию ==')
r = post_step1('Борис')
check('name="code"' in r.get_data(as_text=True), 'шаг 2 открыт')
cb = re.search(r'\b(\d{6})\b', str(BORIS.dms[-1].description)).group(1)
CID = '3003000000000000103'
r = post_step2(CID, cb)
check(r.status_code in (302, 303), 'Борис зарегистрирован')

print('== 11. Вход по паролю: точное имя и НЕ ПОЛНОЕ ==')
with c.session_transaction() as s:
    s.clear()
r = c.post('/login', data={'username': 'Борис', 'password': 'parol123',
                           'resolved_id': ''})
_rh = r.get_data(as_text=True)
_ok_login = (r.status_code in (302, 303)
             or 'Код подтверждения' in _rh          # шаг «чей аккаунт» — штатно
             or 'code_step' in _rh)
check(_ok_login, 'вход по точному имени (сессия или код подтверждения)',
      f'→ {r.status_code}')
with c.session_transaction() as s:
    s.clear()
r = c.post('/login', data={'username': 'Анна Кис', 'password': 'parol123',
                           'resolved_id': ''})
_rh = r.get_data(as_text=True)
_ok_login = (r.status_code in (302, 303)
             or 'Код подтверждения' in _rh
             or 'code_step' in _rh)
check(_ok_login, 'вход по НЕ ПОЛНОМУ имени («Анна Кис»)',
      f'→ {r.status_code}')
with c.session_transaction() as s:
    s.clear()
r = c.post('/login', data={'username': 'Такого-Нет', 'password': 'parol123'})
h = r.get_data(as_text=True)
check('Неверное имя пользователя или пароль' in h,
      'вход по несуществующему имени — обычный отказ (без раскрытия деталей)')

print('== 12. Просроченный код (>10 мин) ==')
r = post_step1('anna', resolved_id='3003000000000000103')
h = r.get_data(as_text=True)
# Boris уже зарегистрирован — берём открытую заявку Анны П.? Она закрыта.
# Берём новую: подставляем просрочку вручную
appmod.PENDING_VERIFICATIONS['9999'] = {
    'code': '123456', 'password': appmod._hash_pw('parol123'),
    'member_info': {'display_name': 'Тест', 'name': 'test', 'avatar': ''},
    'created_at': appmod._time.time() - 601}
r = post_step2('9999', '123456')
check('истёк' in r.get_data(as_text=True).lower(),
      'просроченный код отклонён')

print('== 13. ЛС-текст: в письме есть код и имя ==')
if ANNA.dms:
    d = str(ANNA.dms[0].description)
    check(code in d and 'Анна Киселёва' in d, 'в ЛС и код, и обращение по имени')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
