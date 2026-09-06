# -*- coding: utf-8 -*-
"""Карточки наказаний: столбик, пинг модеров, не бот в «кто выдал».

Запуск: python3 tests/test_log_layout.py
"""
import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_log_layout_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'

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


from cogs import logs as LOGS  # noqa: E402
from cogs.logs import (  # noqa: E402
    _actor_person, _card_friendly, _channel_block, _is_our_bot,
    _person_block, _ping_mod_roles, _safe_send, _strip_raw_id,
    _styled_log_embed, action_log_embed,
)


class _Mem:
    def __init__(self, uid, name, nick=None, bot=False):
        self.id = uid
        self.name = name
        self.display_name = nick or name
        self.global_name = nick or name
        self.mention = f'<@{uid}>'
        self.bot = bot
        self.display_avatar = SimpleNamespace(url='http://x/av.png')


class _Ch:
    def __init__(self, cid, name):
        self.id = cid
        self.name = name
        self.mention = f'<#{cid}>'


class _Role:
    def __init__(self, rid, name='Модератор'):
        self.id = rid
        self.name = name
        self.mention = f'<@&{rid}>'
        self.managed = False

    def is_default(self):
        return False


class _Guild:
    def __init__(self):
        self.id = 777
        self.name = 'Hakumo'
        self.icon = None
        self.me = _Mem(999, 'Hakumo', bot=True)
        self._roles = {_Role.rid if False else 111: _Role(111)}

    def get_member(self, mid):
        return None

    def get_role(self, rid):
        return self._roles.get(int(rid)) if rid else None

    def get_channel(self, cid):
        return None


UID = 523456789012345678
CID = 423456789012345678
user = _Mem(UID, 'ghost.blade', nick='GhostBlade')
mod = _Mem(623456789012345679, 'sonyastaff', nick='sonya.staff')
bot = _Mem(999, 'Hakumo', nick='Moderation', bot=True)
voice = _Ch(CID, 'общение')
g = _Guild()

print('== столбик человека / канала ==')
pb = _person_block(user)
check(user.mention in pb and 'GhostBlade' in pb and str(UID) in pb,
      'пользователь: тег + ник + id')
check(pb.count('\n') >= 2 and pb.startswith('>') and '"GhostBlade"' in pb,
      'пользователь столбиком-таблицей с кавычками')
cb = _channel_block(voice)
check(voice.mention in cb and 'общение' in cb and str(CID) in cb,
      'голосовой канал: упоминание + имя + id')
check(cb.startswith('>') and '"общение"' in cb,
      'канал тоже цитатой и в кавычках')

print('== strip: хвост уходит, столбик id жив ==')
tail = _strip_raw_id(f'**Имя** · <@{UID}> · `{UID}`')
check(f'`{UID}`' not in tail and tail.rstrip().endswith('>')
      and not tail.rstrip().endswith(str(UID)),
      'хвост `id` в той же строке снимается')
kept = _strip_raw_id(pb)
check(str(UID) in kept, 'отдельная строка id в столбике не съедается')
check(kept.startswith('>'), 'полоска цитаты у столбика остаётся')

print('== эмбед не мешает поля в одну строку ==')
e = action_log_embed(g, 'vunmute', user, mod, reason='размут', channel=voice)
check('включили микрофон' in (e.title or ''),
      'заголовок: «Пользователю включили микрофон»')
names = [f.name for f in e.fields]
inlines = {f.name: bool(f.inline) for f in e.fields}
check('Пользователь' in names and 'Модератор' in names
      and 'Голосовой канал' in names,
      'поля пользователь / модератор / канал')
check(not inlines.get('Пользователь') and not inlines.get('Модератор')
      and not inlines.get('Голосовой канал'),
      'поля столбиком, не «Участник | Модератор»')
vals = ' '.join(f.value for f in e.fields)
check('sonya.staff' in vals and 'Moderation' not in vals
      and str(mod.id) in vals,
      'кто выдал — живой модератор, не бот')
check(e._hakumo_log_meta.get('ping') is True, 'мут-лог тегает роль модеров')

ban = action_log_embed(g, 'ban', user, mod, reason='флуд', case_id=12)
check('заблокирован' in (ban.title or '') and not ban.fields[0].inline
      and not ban.fields[1].inline,
      'бан тоже столбиком')
check(any(f.name == 'Дело' for f in ban.fields), 'номер дела в карточке')

to = action_log_embed(g, 'timeout', user, mod, extra='Срок: 30 мин')
check('чат и голос' in (to.title or ''), 'таймаут: мут чат и голос')

print('== бот в аудите не считается модератором ==')
check(_is_our_bot(g, (g.me.display_name, g.me.id, None, True)),
      '_is_our_bot ловит нашего бота из аудита')
check(not _is_our_bot(g, (mod.display_name, mod.id, 'ок', False)),
      'живой модератор — не бот')
sys_line = _actor_person((g.me.display_name, g.me.id, None, True),
                         guild=g, target_id=UID, actions=('vmute',))
check('система' in sys_line and 'Moderation' not in sys_line,
      'без дела в журнале — «система», не имя бота')

os.makedirs('data', exist_ok=True)
with open('data/mod_data.json', 'w', encoding='utf-8') as fh:
    json.dump({'cases': {'777': [{
        'id': 1, 'action': 'vmute', 'user_id': str(UID),
        'mod_id': mod.id, 'mod_name': 'sonya.staff',
        'timestamp': __import__('datetime').datetime.now(
            __import__('datetime').timezone.utc).isoformat(),
    }]}}, fh)
real = _actor_person((g.me.display_name, g.me.id, None, True),
                     guild=g, target_id=UID, actions=('vmute',))
check('sonya.staff' in real and 'Hakumo' not in real,
      'если мутил бот из панели — в логе человек из дела')

print('== пинг роли модераторов ==')
with open('data/role_map.json', 'w', encoding='utf-8') as fh:
    json.dump({'111': 'mod', '222': 'admin', '333': 'curator'}, fh)
roles = _ping_mod_roles(g)
check(len(roles) == 1 and roles[0].id == 111,
      'тегаем только роль модератора, не куратора/админа')


class _Sent:
    def __init__(self):
        self.guild = g
        self.name = 'муты'
        self.sent = []

    async def send(self, **kw):
        self.sent.append(kw)


ch = _Sent()
asyncio.run(_safe_send(ch, embed=e))
kw = ch.sent[-1] if ch.sent else {}
check('content' in kw and '<@&111>' in str(kw.get('content')),
      'в сообщении тег роли модераторов')
am = kw.get('allowed_mentions')
check(am is not None and getattr(am, 'everyone', True) is False,
      'пинг ролей без @everyone')

print('== фото: имя без id, content не выкидывается ==')
photo = _card_friendly(pb, g)
check(str(UID) not in photo and 'GhostBlade' in photo,
      'фото-карточка без сырого id')
src = open(os.path.join(ROOT, 'cogs', 'logs.py'), encoding='utf-8').read()
check("pop ('content'" not in src and "pop('content'" not in src,
      'фото-режим не выкидывает content (пинг жив)')
check('_is_our_bot' in src and 'if not _is_our_bot' in src,
      'логи mute/timeout/ban пропускают, если актор — наш бот')
check('send_action_log' in open(os.path.join(ROOT, 'cogs', 'moderation.py'),
                                encoding='utf-8').read(),
      '/modpanel пишет карточку через send_action_log')
wsrc = open(os.path.join(ROOT, 'cogs', 'warnings.py'), encoding='utf-8').read()
check('send_action_log' in wsrc and '## Авто-наказание' not in wsrc,
      'варны тоже через единую карточку')

print('== смешанный inline выключен для наказаний ==')
stack = _styled_log_embed(g, 'mute', 'Пользователю выключили микрофон',
                          fields=[('Пользователь', pb),
                                  ('Модератор', _person_block(mod)),
                                  ('Голосовой канал', cb)])
check(all(not f.inline for f in stack.fields),
      'все поля столбиком, как таблица')
reason = action_log_embed(g, 'ban', user, mod, reason='флуд')
rval = next((f.value for f in reason.fields if f.name == 'Причина'), '')
check('"' in rval and 'флуд' in rval, 'причина в кавычках')
asrc = open(os.path.join(ROOT, 'cogs', 'appeals.py'), encoding='utf-8').read()
check('_styled_log_embed' in asrc and 'Оценка рассмотрения' in asrc
      and '_rate_log_embed' in asrc and '_rate_prompt_embed' in asrc
      and 'class AppealRateSelect' in asrc,
      'отзыв по апелляции — селект-меню + таблица, не сырая строка')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
