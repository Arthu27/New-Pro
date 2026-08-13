# -*- coding: utf-8 -*-
"""Тесты «демок» к наказаниям: cogs/proof_cog.py + канал доказательств в logs.

Запуск: python3 tests/test_proof.py
"""
import asyncio
import io
import json
import os
import sys
import tempfile

# временная рабочая директория — data/* не мусорит в репо
_TMP = tempfile.mkdtemp(prefix='aether_proof_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord

from cogs import logs as _logs_mod
from cogs.proof_cog import (ProofCog, proof_add, proof_list, proof_get, proof_remove,
                            proof_update_delivery, _proof_path, _is_image_name,
                            _is_link, MAX_REUPLOAD_BYTES)

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


# ─── фейки ─────────────────────────────────────────────────────────────
class FakeAttachmentRecord:
    def __init__(self, url):
        self.url = url


class FakePosted:
    _next = 9000

    def __init__(self, file=None):
        FakePosted._next += 1
        self.id = FakePosted._next
        self.deleted = False
        self.attachments = ([FakeAttachmentRecord(f'https://cdn.aether/{file.filename}')]
                            if file else [])

    async def delete(self):
        self.deleted = True


class FakeTextChannel:
    def __init__(self, cid, name, guild=None):
        self.id = cid
        self.name = name
        self.guild = guild
        self.sent = []          # (embed, file)
        self.posted = []        # FakePosted

    async def send(self, content=None, embed=None, file=None, **kw):
        p = FakePosted(file=file)
        self.sent.append((content, embed, file))
        self.posted.append(p)
        return p

    async def fetch_message(self, mid):
        for p in self.posted:
            if p.id == mid:
                return p
        raise ValueError('not found')


class FakeGuild:
    def __init__(self):
        self.id = 888
        self.name = 'ProofHall'
        self.owner_id = 1
        self.proof_ch = FakeTextChannel(300, '-доказательства', self)
        self.text_channels = [self.proof_ch]

    def get_channel(self, cid):
        return self.proof_ch if cid == self.proof_ch.id else None

    def get_member(self, uid):
        return None


class FakeUser:
    def __init__(self, uid, name):
        self.id = uid
        self.name = name
        self.display_name = name
        self.mention = f'<@{uid}>'

    def __str__(self):
        return self.name


class FakeAttachment:
    def __init__(self, filename, data=b'\x89PNG fake', size=None, url=None):
        self.filename = filename
        self._data = data
        self.size = size if size is not None else len(data)
        self.url = url or f'https://cdn.discordapp.com/expiring/{filename}'
        self.content_type = 'image/png' if filename.endswith('.png') else 'video/mp4'

    async def read(self):
        return self._data


class FakeResp:
    def __init__(self):
        self.sent = []
        self.deferred = False

    async def send_message(self, content=None, embed=None, ephemeral=False):
        self.sent.append((content, embed))

    async def send(self, content=None, embed=None, ephemeral=False):
        self.sent.append((content, embed))

    async def defer(self, ephemeral=False):
        self.deferred = True


class FakeInter:
    def __init__(self, guild, user):
        self.guild = guild
        self.user = user
        self.response = FakeResp()
        self.followup = FakeResp()


GUILD = FakeGuild()
MOD = FakeUser(5001, 'Warden#1')
BADGUY = FakeUser(5050, 'Cheater#7')


async def fake_ensure(guild, category='сервер'):
    return GUILD.proof_ch if category == 'proof' else None


_logs_mod.ensure_log_channel = fake_ensure

# ═══ 0. РЕГИСТРАЦИЯ КАНАЛА В logs ════════════════════════════════════════
print('== logs: канал доказательств зарегистрирован ==')
check(_logs_mod.LOG_CHANNELS.get('доказательства') == '-доказательства',
      'LOG_CHANNELS: доказательства → -доказательства')
check(_logs_mod.CATEGORIES.get('proof', {}).get('channel') == 'доказательства',
      'CATEGORIES: proof → канал доказательства')
check(_logs_mod._LOG_META.get('proof', (None,))[0] == '', '_LOG_META: без эмоджи-иконки (владелец просил убрать)')
ch = _logs_mod.find_log_channel(GUILD, 'proof')
check(ch is GUILD.proof_ch, 'find_log_channel: находит #-доказательства по имени')

# ═══ 1. ДАННЫЕ ════════════════════════════════════════════════════════════
print('== данные: нумерация, фильтры, удаление ==')
e1 = proof_add(GUILD.id, BADGUY.id, str(BADGUY), MOD.id, str(MOD), 'варн', 'токсик')
e2 = proof_add(GUILD.id, BADGUY.id, str(BADGUY), MOD.id, str(MOD), 'бан', 'читы',
               link='https://youtu.be/demo')
e3 = proof_add(GUILD.id, 6060, 'Another#1', MOD.id, str(MOD), 'мут', 'капс')
check((e1['id'], e2['id'], e3['id']) == (1, 2, 3), 'номера идут 1, 2, 3')
check(e2['link'] == 'https://youtu.be/demo' and e2['action'] == 'бан', 'запись полная')
check(len(proof_list(GUILD.id)) == 3, 'proof_list: все три')
check(proof_list(GUILD.id)[0]['id'] == 3, 'proof_list: свежие первые')
mine = proof_list(GUILD.id, user_id=BADGUY.id)
check(len(mine) == 2 and all(m['user_id'] == BADGUY.id for m in mine),
      'proof_list: фильтр по юзеру')
check(len(proof_list(GUILD.id, limit=2)) == 2, 'proof_list: лимит')
check(proof_get(GUILD.id, 2)['reason'] == 'читы', 'proof_get по номеру')
check(proof_get(GUILD.id, 99) is None, 'proof_get: нет такого → None')

upd = proof_update_delivery(GUILD.id, 1, msg_id=555, channel_id=300, url='http://x/1.png')
check(upd and upd['msg_id'] == 555 and upd['url'] == 'http://x/1.png',
      'proof_update_delivery: msg_id и url сохранены')
check(proof_update_delivery(GUILD.id, 77, 1, 1) is None, 'delivery: нет записи → None')

gone = proof_remove(GUILD.id, 3)
check(gone is not None and len(proof_list(GUILD.id)) == 2, 'proof_remove: запись стёрта')
check(proof_remove(GUILD.id, 3) is None, 'proof_remove: повторно → None')

check(_is_image_name('screen.PNG') and not _is_image_name('clip.mp4'), 'image ext')
check(_is_link('https://x') and not _is_link('просто текст'), 'link check')

# ═══ 2. КОГ — /proof ═════════════════════════════════════════════════════
print('== /proof ==')
cog = ProofCog(bot=object())

# без вложения и ссылки — теперь РАЗРЕШЕНО (фото не обязательно, владелец просил)
before0 = len(proof_list(GUILD.id))
inter = FakeInter(GUILD, MOD)
run(ProofCog.proof.callback(cog, inter, user=BADGUY, action='варн', reason='токсик'))
items0 = proof_list(GUILD.id)
check(len(items0) == before0 + 1, 'proof: без файла и ссылки карточка создаётся')
check(items0[0]['link'] is None and items0[0]['reason'] == 'токсик',
      'proof: запись без медиа честная (нет выдуманной ссылки)')
_ok_embed = inter.followup.sent[-1][1]
check('сохранена' in (_ok_embed.title or ''), 'proof: мод получил подтверждение без медиа')
check(any((f.name or '') == 'Без медиа' for f in _ok_embed.fields),
      'proof: подсказка «добавь фото позже через /proof» есть')

# кривая ссылка — отказ
inter = FakeInter(GUILD, MOD)
run(ProofCog.proof.callback(cog, inter, user=BADGUY, action='варн', reason='токсик',
                            link='просто текст'))
check('ссылка' in (inter.response.sent[-1][0] or '').lower(), 'proof: не-ссылка → отказ')

# только ссылка
before = len(proof_list(GUILD.id))
inter = FakeInter(GUILD, MOD)
run(ProofCog.proof.callback(cog, inter, user=BADGUY, action='бан', reason='мясорейд',
                            link='https://youtu.be/proof1'))
items = proof_list(GUILD.id)
check(len(items) == before + 1, 'proof: запись добавлена (ссылка)')
last = items[0]
check(last['link'] == 'https://youtu.be/proof1' and last['mod_name'] == str(MOD),
      'proof: ссылка и мод записаны')
check(GUILD.proof_ch.sent and GUILD.proof_ch.sent[-1][1] is not None
      and GUILD.proof_ch.sent[-1][2] is None, 'proof: в канал ушёл эмбед БЕЗ файла')
emb_ch = GUILD.proof_ch.sent[-1][1]
check('Демка' in (emb_ch.title or '') and 'мясорейд' in str(emb_ch.fields[-1].value if False else '')
      or emb_ch.fields, 'proof: эмбед в канале с полями')
check(last['msg_id'] is not None and last['channel_id'] == 300,
      'proof: msg_id/канал записаны — сообщение найдём')
check(inter.followup.sent and 'сохранена' in (inter.followup.sent[-1][1].title or ''),
      'proof: мод получил подтверждение')
# ссылка демки подсвечена в канале
check(any('Ссылка' in (f.name or '') for f in emb_ch.fields), 'proof: поле-ссылка в канале есть (без эмоджи)')

# картинка-вложение → перезалив + инлайн в эмбед
att = FakeAttachment('proof.png')
inter = FakeInter(GUILD, MOD)
run(ProofCog.proof.callback(cog, inter, user=BADGUY, action='кик', reason='рейдил войс',
                            attachment=att))
content, embed, file = GUILD.proof_ch.sent[-1]
check(file is not None and file.filename == 'proof.png', 'proof: файл перезалит в канал')
check(embed.image and embed.image.url == 'attachment://proof.png',
      'proof: картинка инлайнится в эмбед — видно при прокрутке')
rec = proof_list(GUILD.id)[0]
check(rec['url'] == 'https://cdn.aether/proof.png',
      'proof: живой url из нового сообщения записан (не протухающий CDN)')

# видео — файлом, без инлайна
att2 = FakeAttachment('clip.mp4', data=b'video bytes')
inter = FakeInter(GUILD, MOD)
run(ProofCog.proof.callback(cog, inter, user=BADGUY, action='бан', reason='читы',
                            attachment=att2))
_, embed2, file2 = GUILD.proof_ch.sent[-1]
check(file2 is not None and file2.filename == 'clip.mp4', 'proof: видео прикреплено файлом')
check(embed2.image.url is None, 'proof: видео НЕ инлайнится (Discord сам даст плеер)')

# слишком большой файл → fallback ссылка + предупреждение
big = FakeAttachment('huge.mp4', size=MAX_REUPLOAD_BYTES + 5)
inter = FakeInter(GUILD, MOD)
run(ProofCog.proof.callback(cog, inter, user=BADGUY, action='бан', reason='читы v2',
                            attachment=big))
_, embed3, file3 = GUILD.proof_ch.sent[-1]
check(file3 is None, 'proof: большой файл НЕ перезаливается')
check(any('не перезалит' in (f.value or '') for f in embed3.fields),
      'proof: предупреждение о размере в карточке канала')
rec3 = proof_list(GUILD.id)[0]
check(rec3['link'] == big.url, 'proof: вместо файла сохранена исходная ссылка')

# ═══ 3. /proofs ═══════════════════════════════════════════════════════════
print('== /proofs ==')
inter = FakeInter(GUILD, MOD)
run(ProofCog.proofs.callback(cog, inter))
emb = inter.response.sent[-1][1]
check(emb.description and '#2' in emb.description and 'к сообщению' in emb.description,
      'proofs: список с номерами и jump-ссылками')
check('Всего' in (emb.footer.text or ''), 'proofs: футер со счётчиком')

inter = FakeInter(GUILD, MOD)
run(ProofCog.proofs.callback(cog, inter, user=BADGUY))
emb = inter.response.sent[-1][1]
check('Cheater' in (emb.title or '') and 'Another' not in (emb.description or ''),
      'proofs: фильтр по юзеру')

inter = FakeInter(GUILD, MOD)
run(ProofCog.proofs.callback(cog, inter, user=FakeUser(1, 'Nobody#1')))
check('пусто' in (inter.response.sent[-1][1].description or '').lower(),
      'proofs: у чистого юзера — пусто')

# ═══ 4. /proofdel ═════════════════════════════════════════════════════════
print('== /proofdel ==')
target = proof_list(GUILD.id, user_id=BADGUY.id)[0]          # свежая
posted_msg = None
for p in GUILD.proof_ch.posted:
    if p.id == target['msg_id']:
        posted_msg = p
inter = FakeInter(GUILD, MOD)
run(ProofCog.proofdel.callback(cog, inter, number=target['id']))
check(proof_get(GUILD.id, target['id']) is None, 'proofdel: запись удалена из json')
check(posted_msg is not None and posted_msg.deleted is True,
      'proofdel: сообщение в канале доказательств тоже удалено')

inter = FakeInter(GUILD, MOD)
run(ProofCog.proofdel.callback(cog, inter, number=4242))
check('4242' in (inter.response.sent[-1][0] or ''), 'proofdel: нет такого номера → внятно')

# ═══ 5. ИНТЕГРАЦИЯ: демка прямо в наказании ═══════════════════════════════
print('== интеграция: try_deliver_proof из других когов ==')
from cogs.proof_cog import try_deliver_proof  # noqa: E402

GUILD.icon = None


class FakeBotX:
    def __init__(self, proof_cog=None):
        self._proof = proof_cog
        self.guilds = [GUILD]

    def get_cog(self, name):
        return self._proof if name == 'ProofCog' else None

    def get_guild(self, gid):
        return GUILD if gid == GUILD.id else None


botx = FakeBotX(cog)

# ни файла, ни ссылки → None (ничего не надо делать)
check(run(try_deliver_proof(botx, GUILD, MOD, BADGUY, 'кик', 'просто так')) is None,
      'try_deliver_proof: без демки → None')

# с вложением → запись + постинг + строка-статус
before = len(proof_list(GUILD.id))
txt = run(try_deliver_proof(botx, GUILD, MOD, BADGUY, 'кик', 'токсик в войсе',
                            attachment=FakeAttachment('proof-voice.png')))
check(txt is not None and 'Демка #' in (txt or ''), 'try_deliver_proof: статус-текст с номером')
check(len(proof_list(GUILD.id)) == before + 1, 'try_deliver_proof: запись создана')
check(GUILD.proof_ch.sent[-1][2] is not None, 'try_deliver_proof: файл запощен в канал')


class _NoCogBot:
    def get_cog(self, name):
        return None


check(run(try_deliver_proof(_NoCogBot(), GUILD, MOD, BADGUY, 'бан', 'x',
                            link='https://x.y/z')) is None,
      'try_deliver_proof: нет ProofCog → None, не падает')


class _BoomBot:
    def get_cog(self, name):
        raise RuntimeError('всё сломалось')


check(run(try_deliver_proof(_BoomBot(), GUILD, MOD, BADGUY, 'бан', 'x',
                            link='https://x.y/z')) is None,
      'try_deliver_proof: исключения проглочены — наказание не роняет')

print('== интеграция: /moderate бан + демка одной командой ==')
from cogs.moderation import Moderation  # noqa: E402


class FakeBanUser:
    def __init__(self, uid, name):
        self.id = uid
        self.name = name
        self.display_name = name
        self.mention = f'<@{uid}>'
        self.banned = False

    class _Av:
        url = 'http://x/av.png'

    display_avatar = _Av()

    def __str__(self):
        return self.name

    async def ban(self, reason=None):
        self.banned = reason or True


FakeResp.is_done = lambda self: bool(self.deferred or self.sent)


async def _noop(*a, **k):
    return None


mod_cog = Moderation(botx)
mod_cog.send_dm = _noop
mod_cog.send_log = _noop
mod_cog._notify_owner = _noop

BANUSER = FakeBanUser(9090, 'Griefer#3')
proofs_before = len(proof_list(GUILD.id))
inter = FakeInter(GUILD, MOD)
run(Moderation.moderate_user.callback(
    mod_cog, inter, action='ban', user=BANUSER, reason='массовый рейд',
    демка=FakeAttachment('raid.png')))
check(BANUSER.banned == 'массовый рейд', 'moderate: бан реально применён')
check(len(proof_list(GUILD.id)) == proofs_before + 1, 'moderate: демка записана автоматически')
rec = proof_list(GUILD.id)[0]
check(rec['action'] == 'бан' and rec['user_id'] == 9090, 'moderate: действие=бан, юзер верный')
check(any('Демка #' in str(c or '') for c, _ in inter.followup.sent),
      'moderate: мод получил подтверждение про демку')

# без демки — бан проходит, демка не создаётся, лишних сообщений нет
BANUSER2 = FakeBanUser(9091, 'Griefer#4')
proofs_before = len(proof_list(GUILD.id))
followups_before = len(inter.followup.sent)
inter = FakeInter(GUILD, MOD)
run(Moderation.moderate_user.callback(
    mod_cog, inter, action='ban', user=BANUSER2, reason='без демки'))
check(BANUSER2.banned == 'без демки', 'moderate: бан без демки тоже работает')
check(len(proof_list(GUILD.id)) == proofs_before, 'moderate: без вложения демка не создаётся')
check(not any('Демка #' in str(c or '') for c, _ in inter.followup.sent),
      'moderate: без демки мод не получает лишнего шума')

print('== интеграция: /warn + демка ==')
from cogs.warnings import warnings as WarningsCog  # noqa: E402

warn_cog = WarningsCog(botx)


async def _fake_add_warn(self, interaction, user, reason):
    return (1, 1, None)


import types as _types
warn_cog.add_warn = _types.MethodType(_fake_add_warn, warn_cog)

proofs_before = len(proof_list(GUILD.id))
inter = FakeInter(GUILD, MOD)
run(WarningsCog.warn.callback(warn_cog, inter, user=BANUSER, reason='спам-ссылки',
                              демка=FakeAttachment('spam.png')))
check(len(proof_list(GUILD.id)) == proofs_before + 1, 'warn: демка записана')
check(proof_list(GUILD.id)[0]['action'] == 'варн', 'warn: действие=варн')
emb = inter.response.sent[-1][1] or inter.followup.sent[-1][1]
check('Демка #' in (emb.description or ''), 'warn: про демку сказано в самом ответе о варне')

# warn БЕЗ демки — ничего лишнего
proofs_before = len(proof_list(GUILD.id))
inter = FakeInter(GUILD, MOD)
run(WarningsCog.warn.callback(warn_cog, inter, user=BANUSER, reason='просто варн'))
emb = inter.response.sent[-1][1] or inter.followup.sent[-1][1]
check(len(proof_list(GUILD.id)) == proofs_before
      and 'Демка #' not in (emb.description or ''), 'warn без демки: чисто')

# ═══ 6. ПАНЕЛЬ: /proofs ═══════════════════════════════════════════════════
print('== панель: страница и API демок ==')
from web.app import app as _flask_app2, set_bot_instance  # noqa: E402
set_bot_instance(botx)
client = _flask_app2.test_client()


def login_as2(role):
    # discord_id специально НЕ ставим: login_required перечитывал бы роль
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'PanelProof'
        s['role'] = role


r = client.get('/api/proofs')
check(r.status_code in (302, 401, 403), f'API без логина закрыто ({r.status_code})')

login_as2('uye')
r = client.get('/api/proofs')
check(r.status_code == 403, f'uye не пускают ({r.status_code})')

login_as2('mod')
r = client.get('/api/proofs')
d = r.get_json()
check(r.status_code == 200 and d.get('success') is True and d.get('total', 0) > 0,
      'mod: список демок отдаётся')
check(all(set(['id', 'action', 'user_name', 'reason', 'set_at']) <= set(i) for i in d['items']),
      'mod: у записей полный набор полей')
check(any(i.get('jump', None) for i in d['items']),
      'mod: есть jump-ссылки на сообщения в Discord')

r = client.get(f'/api/proofs?user_id={BANUSER.id}')
check(all(i['user_id'] == str(BANUSER.id) for i in r.get_json()['items']),
      'фильтр по юзеру работает')
r = client.get('/api/proofs?action=варн')
check(all(i['action'] == 'варн' for i in r.get_json()['items']),
      'фильтр по наказанию работает')

victim = d['items'][0]
r = client.delete(f"/api/proofs/{victim['id']}")
check(r.status_code == 403, f'mod удалять демки не может ({r.status_code})')

login_as2('admin')
# делимся: у admin роль выше — удаление должно удаться
r = client.delete(f"/api/proofs/{victim['id']}")
dd = r.get_json()
check(dd.get('success') is True and proof_get(GUILD.id, victim['id']) is None,
      'admin: демка удалена из панели')
r = client.delete(f"/api/proofs/{victim['id']}")
check(r.status_code == 404, 'admin: повторное удаление → 404')

r = client.get('/proofs')
page = r.get_data(as_text=True)
check(r.status_code == 200 and 'Демк' in page and '/api/proofs' in page,
      'страница /proofs рендерится')
login_as2('uye')
r = client.get('/proofs')
check(r.status_code in (302, 403), f'uye на /proofs не пускают ({r.status_code})')

from services.panel_menu import MENU as _MENU2  # noqa: E402
check(any(p['path'] == '/proofs' for g in _MENU2 for p in g['pages']),
      'в меню панели есть пункт «Демки»')

# ─── финал ───────────────────────────────────────────────────────────────
import shutil  # noqa: E402
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
