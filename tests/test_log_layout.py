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
    _person_block, _ping_mod_roles, _role_block, _roles_cell,
    _safe_send, _strip_raw_id, _styled_log_embed, action_log_embed,
    nick_change_log_embed, role_batch_log_embed, role_change_log_embed,
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
        from datetime import datetime, timezone, timedelta
        self.created_at = datetime.now(timezone.utc) - timedelta(days=800)
        self.joined_at = datetime.now(timezone.utc) - timedelta(days=90)


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
tnames = [f.name for f in to.fields]
check('Срок' in tnames, f'срок отдельным столбцом: {tnames}')
tval = next(f.value for f in to.fields if f.name == 'Срок')
check('30 мин' in tval and '<t:' in tval, 'срок: человечески + до какого времени')
check('Профиль' in tnames and 'аккаунт' in next(f.value for f in to.fields if f.name == 'Профиль'),
      'профиль: возраст аккаунта и сколько на сервере')
check(getattr(to, 'author', None) and 'sonya.staff' in str(getattr(to.author, 'name', '')),
      'сверху — кто выдал, с именем человека')

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
proofed = action_log_embed(g, 'ban', user, mod, reason='флуд',
                           proof='https://example.com/a.png', case_id=4)
pnames = [f.name for f in proofed.fields]
check('Доказательство' in pnames and 'открыть запись' in
      next(f.value for f in proofed.fields if f.name == 'Доказательство'),
      'ссылка на доказательство в карточке')
hist_e = action_log_embed(g, 'vmute', user, mod, duration='30 мин')
check(any(f.name == 'История' and 'мутов' in f.value for f in hist_e.fields),
      'история: сколько мутов уже было')
check('rows[:20]' in src or 'rows[:20]' in open(os.path.join(ROOT, 'cogs', 'logs.py'), encoding='utf-8').read(),
      'в эмбед влезает больше 8 столбцов')
lsrc = open(os.path.join(ROOT, 'cogs', 'logs.py'), encoding='utf-8').read()
check('def _duration_cell' in lsrc and 'def _profile_cell' in lsrc
      and 'def _history_cell' in lsrc,
      'срок / профиль / история собраны в столбик')
check('duration=amount' in open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read()
      and 'proof=proof_link' in open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read(),
      '/modpanel передаёт срок и доказательство в лог')
asrc = open(os.path.join(ROOT, 'cogs', 'appeals.py'), encoding='utf-8').read()
check('_styled_log_embed' in asrc and 'Оценка рассмотрения' in asrc
      and '_rate_log_embed' in asrc and '_rate_prompt_embed' in asrc
      and 'class AppealRateSelect' in asrc,
      'отзыв по апелляции — селект-меню + таблица, не сырая строка')

print('== роли пользователя: Выдал / Пользователь / Выданы ==')
dota = _Role(823456789012345670, 'Dota 2')
g._roles[dota.id] = dota
rc = role_change_log_embed(g, user, added=[dota], moderator=mod, dest='rest')
names = [f.name for f in rc.fields]
check('Роли пользователя изменены' in (rc.title or ''),
      'заголовок: «Роли пользователя изменены»')
check(names[:3] == ['Выдал', 'Пользователь', 'Выданы'],
      f'поля как в образце: Выдал / Пользователь / Выданы ({names[:3]})')
check('Профиль' in names, 'профиль тоже в карточке роли')
vals = ' '.join(f.value for f in rc.fields)
check(user.mention in vals and 'GhostBlade' in vals and str(UID) in vals,
      'пользователь столбиком: тег + ник + id')
check(mod.mention in vals and 'sonya.staff' in vals,
      'выдал — человек, не бот')
check(dota.mention in vals and 'Dota 2' in vals,
      'выданная роль — упоминание и имя')
check(all(not f.inline for f in rc.fields), 'роль-лог столбиком, не в кашу')
check(getattr(rc, 'author', None) and 'sonya.staff' in str(getattr(rc.author, 'name', '')),
      'сверху — Выдал с именем человека')
gone = role_change_log_embed(g, user, removed=[dota], moderator=mod)
check('Сняты' in [f.name for f in gone.fields] and 'Выданы' not in [f.name for f in gone.fields],
      'снятие роли — поле «Сняты», без «Выданы»')
ban_e = role_change_log_embed(g, user, added=[dota], moderator=mod,
                             dest='ban', reason='флуд в общем')
bn = [f.name for f in ban_e.fields]
check('заблокирован' in (ban_e.title or ''),
      'роль бана: заголовок «Пользователь заблокирован», не «роль ban»')
check('Причина' in bn and 'Выданы' not in bn,
      'роль бана: причина на виду, без «Выданы: ban»')
check('флуд в общем' in next(f.value for f in ban_e.fields if f.name == 'Причина'),
      'за что забанили — в карточке')
unban_e = role_change_log_embed(g, user, removed=[dota], moderator=mod, dest='ban')
check('снята' in (unban_e.title or '').lower() or 'Блокировка' in (unban_e.title or ''),
      'снятие роли бана: «Блокировка снята»')
lsrc2 = open(os.path.join(ROOT, 'cogs', 'logs.py'), encoding='utf-8').read()
check('_PUNISH_ROLE_TITLES' in lsrc2 and '_is_our_bot' in lsrc2
      and 'за что' in lsrc2,
      'роль бана от бота не дублирует карточку панели')
empty_ban = role_change_log_embed(g, user, added=[dota], moderator=mod, dest='ban')
eval_ = next(f.value for f in empty_ban.fields if f.name == 'Причина')
check('не указана' in eval_ and '"не указана"' not in eval_,
      'пустая причина бана — без кавычек, не «роль ban»')
check('send_action_log' in open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read()
      and 'срок наказания истёк' in open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read(),
      'снятие бана и истечение роли — той же карточкой, не тонкой строкой')
check('_clean_reason' in lsrc2 and 'На сервере сейчас' in lsrc2,
      'вход без «#N», причина чистится от заглушек')
tval2 = next(f.value for f in to.fields if f.name == 'Срок')
check('30 мин' in tval2 and '"30 мин"' not in tval2,
      'срок без кавычек — это не имя')
pval = next(f.value for f in to.fields if f.name == 'Профиль')
check('аккаунт' in pval and '"аккаунт' not in pval,
      'профиль без кавычек')
check('def _change_cell' in lsrc2 and 'def _verify_ru' in lsrc2
      and 'Скрытый пинг' in lsrc2,
      'диффы столбиком, пинг по-русски, без True/False')
batch = role_batch_log_embed(g, [
    {'user': user, 'added': [dota], 'removed': [], 'user_name': 'GhostBlade'},
    {'user': mod, 'added': [], 'removed': [dota], 'user_name': 'sonya.staff'},
], dest='rest', moderator=mod)
check('2 участников' in (batch.title or ''), 'пачка ролей — сводка, не спам')
nick = nick_change_log_embed(g, user, 'кип', 'Кипарис', moderator=mod)
nn = [f.name for f in nick.fields]
check(nn[:4] == ['Выдал', 'Пользователь', 'Было', 'Стало'],
      f'ник: выдал / пользователь / было / стало ({nn[:4]})')
check('кип' in ' '.join(f.value for f in nick.fields)
      and 'Кипарис' in ' '.join(f.value for f in nick.fields),
      'старый и новый ник видны')
rb = _role_block(dota)
check(dota.mention in rb and 'Dota 2' in rb and str(dota.id) in rb,
      'роль столбиком как человек: тег + имя + id')
check(_roles_cell([dota, dota]).count(dota.mention) == 1,
      'дубль одной роли не рисуем дважды')
lsrc = open(os.path.join(ROOT, 'cogs', 'logs.py'), encoding='utf-8').read()
check('def role_change_log_embed' in lsrc and 'Выданы' in lsrc
      and 'Роли пользователя изменены' in lsrc,
      'карточка ролей: Выдал / Пользователь / Выданы')
check('rows[:20]' in lsrc, 'в эмбед влезает больше полей — карточка полная')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
