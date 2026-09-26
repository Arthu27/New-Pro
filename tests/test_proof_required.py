# -*- coding: utf-8 -*-
"""Обязательное доказательство к наказаниям + справка с фильтром по правам.

Проверяем:
1. is_media_attachment: доказательство — только картинка/видео.
2. require_proof: без доказательства наказание НЕ выдаётся (False + отказ);
   с картинкой/видео/ссылкой — можно (True).
3. prefix_has_media: вложения сообщения префикс-команды.
4. build_help_embed: команды скрываются из справки, если у роли нет
   классического разрешения на действие (ban/tempban/… пропадают без «Бан»).

Запуск: python3 tests/test_proof_required.py
"""
import asyncio, os, sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.makedirs('data', exist_ok=True)

import config
config.Config.DB_PATH = os.path.abspath('data/bot.db')

from services.permission_acl import (save_acl, save_action_acl,
                                     set_action_rule, set_rule,
                                     all_categories)
from cogs.proof_cog import is_media_attachment, require_proof, prefix_has_media
from cogs.help import build_help_embed

PASS = 0; FAIL = 0
def check(ok, msg):
    global PASS, FAIL
    if ok: PASS += 1; print(f'  PASS: {msg}')
    else: FAIL += 1; print(f'  FAIL: {msg}')

# ── фейки ──
class Att:
    def __init__(self, content_type=None, filename=''):
        self.content_type = content_type
        self.filename = filename

class FakeFollowup:
    def __init__(self): self.sent = []
    async def send(self, *a, **k): self.sent.append(k)
class FakeResponse:
    def __init__(self): self.msgs = []
    async def send_message(self, *a, **k): self.msgs.append(k)
class FakeInteraction:
    def __init__(self):
        self.followup = FakeFollowup()
        self.response = FakeResponse()

class Role:
    def __init__(self, rid): self.id = rid
class Perms:
    def __init__(self, administrator=False): self.administrator = administrator
class Member:
    def __init__(self, roles=(), administrator=False, bot=False):
        self.roles = [Role(r) for r in roles]
        self.guild_permissions = Perms(administrator)
        self.bot = bot

GID = 424242
save_acl(GID, {})
save_action_acl(GID, {})

from cogs.proof_cog import proof_is_required, proof_set_required
check(proof_is_required(GID) is False,
      'по умолчанию доказательства НЕ требуются (включается в панели)')
proof_set_required(GID, True)  # строгий режим — явно включаем

print('== is_media_attachment ==')
check(is_media_attachment(None) is False, 'пустое вложение — не доказательство')
check(is_media_attachment(Att(content_type='image/png')) is True, 'image/* — доказательство')
check(is_media_attachment(Att(content_type='video/mp4')) is True, 'video/* — доказательство')
check(is_media_attachment(Att(content_type='application/pdf')) is False, 'pdf — не доказательство')
check(is_media_attachment(Att(filename='shot.png')) is True, 'расширение .png — доказательство')
check(is_media_attachment(Att(filename='clip.mp4')) is True, 'расширение .mp4 — доказательство')
check(is_media_attachment(Att(filename='virus.exe')) is False, '.exe — не доказательство')

print('== require_proof ==')
loop = asyncio.new_event_loop()

# без доказательства → отказ
inter = FakeInteraction()
ok = loop.run_until_complete(require_proof(inter, attachment=None, action_ru='бан'))
check(ok is False, 'без доказательства require_proof -> False (наказание НЕ выдаётся)')
check(bool(inter.followup.sent) or bool(inter.response.msgs),
      'модератору отправлен отказ')

# картинка → можно
inter2 = FakeInteraction()
ok2 = loop.run_until_complete(require_proof(inter2, attachment=Att(content_type='image/png'), action_ru='бан'))
check(ok2 is True, 'с картинкой require_proof -> True')

# не-медиа файл → отказ
inter3 = FakeInteraction()
ok3 = loop.run_until_complete(require_proof(inter3, attachment=Att(filename='file.pdf'), action_ru='бан'))
check(ok3 is False, 'pdf вместо скрина -> отказ (False)')

# ссылка → можно
inter4 = FakeInteraction()
ok4 = loop.run_until_complete(require_proof(inter4, attachment=None, action_ru='бан', link='https://imgur.com/x.png'))
check(ok4 is True, 'с ссылкой require_proof -> True')

print('== prefix_has_media ==')
class FakeMsg:
    def __init__(self, atts): self.attachments = atts
class FakeCtx:
    def __init__(self, atts): self.message = FakeMsg(atts)
check(prefix_has_media(FakeCtx([Att(content_type='image/png')])) is True, 'префикс: картинка во вложении')
check(prefix_has_media(FakeCtx([Att(content_type='application/pdf')])) is False, 'префикс: pdf не считается')
check(prefix_has_media(FakeCtx([])) is False, 'префикс: без вложений')

print('== build_help_embed: фильтр по классическим разрешениям (строгая модель) ==')
# Проверяем на ЖИВОЙ команде из каталога: ban/tempban/warn — это действия
# внутри /modpanel, отдельных таких команд у бота нет, и проверка на них
# проходила «ни о чём» (имени просто не было в справке).
_cmd = next(iter(all_categories().get('Модерация', [])), 'modpanel')
set_rule(GID, _cmd, ['1'])          # доступ только роли 1
e = build_help_embed(category_id=None, member=Member(roles=[1]), guild_id=GID)
text_all = ''.join(f.value for f in e.fields)
check('`%s`' % _cmd in text_all, f'с правом на команду {_cmd} она видна в справке')

# отдаём право другой роли -> у роли 1 команда пропадает из справки
set_rule(GID, _cmd, ['555'])
e2 = build_help_embed(category_id=None, member=Member(roles=[1]), guild_id=GID)
text_deny = ''.join(f.value for f in e2.fields)
check('`%s`' % _cmd not in text_deny, f'без права команда {_cmd} скрыта из справки')
# у роли с доступом — видно
e3 = build_help_embed(category_id=None, member=Member(roles=[555]), guild_id=GID)
text_allow = ''.join(f.value for f in e3.fields)
check('`%s`' % _cmd in text_allow, f'с ролями на {_cmd} команда снова в справке')
# правило на одну команду не задевает соседнюю из другого раздела
_other = next((c for k, v in all_categories().items() if k != 'Модерация'
               for c in v), 'afk')
check('`%s`' % _other in text_allow,
      f'соседняя команда {_other} правилом на {_cmd} не задета')
save_acl(GID, {})

# одна категория
e4 = build_help_embed(category_id='Тикеты', member=Member(roles=[1]), guild_id=GID)
titles4 = [f.name for f in e4.fields]
check(all('Тикеты' in t for t in titles4) and len(titles4) > 0,
      'фильтр по категории: только «Тикеты»')

set_action_rule(GID, 'ban', [])
os.system('rm -rf data')
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
