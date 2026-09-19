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
    _member_is_staff, _person_block, _role_block, _roles_cell,
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

print('== столбик человека / канала (weebook v2) ==')
pb = _person_block(user)
check(user.mention in pb and 'ghost.blade' in pb and str(UID) in pb,
      'пользователь: тег + username · id')
check(pb.count('\n') == 1 and pb.startswith('•') and '"' not in pb
      and f'ghost.blade · {UID}' in pb,
      'weebook коротко: две строки, без кавычек')
cb = _channel_block(voice)
check(voice.mention in cb, 'голосовой канал: упоминание')
check('общение' not in cb, 'имя канала не дублируется — mention уже имя')
check(cb.startswith('•') and str(CID) in cb,
      'канал weebook: mention + id')

print('== strip: хвост уходит, столбик id жив ==')
tail = _strip_raw_id(f'**Имя** · <@{UID}> · `{UID}`')
check(f'`{UID}`' not in tail and not tail.rstrip().endswith(str(UID)),
      'хвост `id` в той же строке снимается')
kept = _strip_raw_id(pb)
check(str(UID) in kept, 'отдельная строка id в столбике не съедается')
check(kept.startswith('•'), 'маркер «•» у столбика остаётся')

print('== эмбед weebook: — • заголовок, | поле:, две колонки ==')
e = action_log_embed(g, 'vunmute', user, mod, reason='размут', channel=voice)
check((e.title or '').startswith('— •') and 'включили микрофон' in (e.title or ''),
      'заголовок weebook: «— • …включили микрофон»')
names = [f.name for f in e.fields]
inlines = {f.name: bool(f.inline) for f in e.fields}
check(any('Пользователь' in n for n in names)
      and any('Модератор' in n for n in names)
      and not any('Голосовой канал' in n for n in names)
      and not any(n == 'Канал' or n.endswith('Канал:') for n in names),
      'поля пользователь / модератор, без канала')
check(all(n.startswith('| ') and n.endswith(':') for n in names),
      f'имена полей «| …:»: {names}')
check(inlines.get('| Пользователь:') and inlines.get('| Модератор:'),
      'короткие поля inline (2 колонки weebook)')
vals = ' '.join(f.value for f in e.fields)
check('sonyastaff' in vals and 'Moderation' not in vals
      and str(mod.id) in vals,
      'кто выдал — живой модератор, не бот')
check(e._hakumo_log_meta.get('ping') is True,
      'мут-лог тегает роль модеров (ping=True)')
check(e._hakumo_log_meta.get('style') == 'weebook', 'meta.style=weebook')

ban = action_log_embed(g, 'ban', user, mod, reason='флуд', case_id=12)
check('заблокирован' in (ban.title or '') and (ban.title or '').startswith('— •'),
      'бан: weebook-заголовок')
check(any('Дело' in f.name for f in ban.fields), 'номер дела в карточке')

to = action_log_embed(g, 'timeout', user, mod, extra='Срок: 30 мин')
check('чат и голос' in (to.title or ''), 'таймаут: мут чат и голос')
tnames = [f.name for f in to.fields]
check(any('Срок' in n for n in tnames), f'срок отдельным столбцом: {tnames}')
tval = next(f.value for f in to.fields if 'Срок' in f.name)
check('30 мин' in tval and '<t:' in tval, 'срок: человечески + до какого времени')
check(any('Профиль' in n for n in tnames)
      and 'аккаунт' in next(f.value for f in to.fields if 'Профиль' in f.name),
      'профиль: возраст аккаунта и сколько на сервере')
# weebook без author-строки «Выдал …»
check(not getattr(getattr(to, 'author', None), 'name', None),
      'без author «Выдал …» — чистый weebook')

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

print('== роли в логах тегаются на наказаниях ==')
with open('data/role_map.json', 'w', encoding='utf-8') as fh:
    json.dump({'111': 'mod', '222': 'admin', '333': 'curator'}, fh)
g._roles[111] = _Role(111, 'Модератор')


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
check('<@&111>' in str(kw.get('content') or ''),
      'в сообщении лога есть тег роли модеров')
am = kw.get('allowed_mentions')
check(am is not None and bool(getattr(am, 'roles', None)),
      'пинг ролей разрешён (allowed_mentions)')

print('== фото: имя без id, content не выкидывается ==')
photo = _card_friendly(pb, g)
check(str(UID) not in photo and ('ghost.blade' in photo or 'GhostBlade' in photo),
      'фото-карточка без сырого id')
src = open(os.path.join(ROOT, 'cogs', 'logs.py'), encoding='utf-8').read()
check("pop ('content'" not in src and "pop('content'" not in src,
      'фото-режим не выкидывает content')
check('_is_our_bot' in src and 'if not _is_our_bot' in src,
      'логи mute/timeout/ban пропускают, если актор — наш бот')
check('send_action_log' in open(os.path.join(ROOT, 'cogs', 'moderation.py'),
                                encoding='utf-8').read(),
      '/modpanel пишет карточку через send_action_log')
wsrc = open(os.path.join(ROOT, 'cogs', 'warnings.py'), encoding='utf-8').read()
check('send_action_log' in wsrc and '## Авто-наказание' not in wsrc,
      'варны тоже через единую карточку')

print('== weebook: короткие поля inline, длинные — нет ==')
stack = _styled_log_embed(g, 'mute', 'Пользователю выключили микрофон',
                          fields=[('Пользователь', pb),
                                  ('Модератор', _person_block(mod)),
                                  ('Голосовой канал', cb)])
check(all(f.name.startswith('| ') for f in stack.fields),
      'все имена полей в стиле «| …:»')
check(any(f.inline for f in stack.fields),
      'короткие поля — две колонки (inline)')
reason = action_log_embed(g, 'ban', user, mod, reason='флуд')
rval = next((f.value for f in reason.fields if 'Причина' in f.name), '')
check('флуд' in rval and rval.strip().startswith('•'),
      'причина маркером «•», без кавычек')
proofed = action_log_embed(g, 'ban', user, mod, reason='флуд',
                           proof='https://example.com/a.png', case_id=4)
pnames = [f.name for f in proofed.fields]
check(any('Доказательство' in n for n in pnames) and 'открыть запись' in
      next(f.value for f in proofed.fields if 'Доказательство' in f.name),
      'ссылка на доказательство в карточке')
hist_e = action_log_embed(g, 'vmute', user, mod, duration='30 мин')
check(any('История' in f.name and 'мутов' in f.value for f in hist_e.fields),
      'история: сколько мутов уже было')
check('rows[:20]' in src or 'rows[:20]' in open(os.path.join(ROOT, 'cogs', 'logs.py'), encoding='utf-8').read(),
      'в эмбед влезает больше 8 столбцов')
lsrc = open(os.path.join(ROOT, 'cogs', 'logs.py'), encoding='utf-8').read()
check('def _duration_cell' in lsrc and 'def _profile_cell' in lsrc
      and 'def _history_cell' in lsrc,
      'срок / профиль / история собраны в столбик')
check('_weebook_title' in lsrc and '_weebook_field_name' in lsrc,
      'хелперы weebook на месте')
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
check('Роли пользователя изменены' in (rc.title or '')
      and (rc.title or '').startswith('— •'),
      'заголовок weebook: «— • Роли пользователя изменены»')
check(any('Выдал' in n for n in names)
      and any('Пользователь' in n for n in names)
      and any('Выданы' in n for n in names),
      f'поля Выдал / Пользователь / Выданы ({names[:3]})')
check(any('Профиль' in n for n in names), 'профиль тоже в карточке роли')
vals = ' '.join(f.value for f in rc.fields)
check(user.mention in vals and 'ghost.blade' in vals and str(UID) in vals
      and f'ghost.blade · {UID}' in vals,
      'пользователь коротко: тег + username · id')
check(mod.mention in vals and 'sonyastaff' in vals,
      'выдал — человек, не бот')
check(dota.mention in vals and 'Dota 2' in vals,
      'выданная роль — упоминание и имя')
check(any(f.inline for f in rc.fields), 'короткие поля inline (weebook)')
check(not getattr(getattr(rc, 'author', None), 'name', None),
      'без author — чистый weebook')
gone = role_change_log_embed(g, user, removed=[dota], moderator=mod)
gnames = [f.name for f in gone.fields]
check(any('Сняты' in n for n in gnames) and not any('Выданы' in n for n in gnames),
      'снятие роли — поле «Сняты», без «Выданы»')
ban_e = role_change_log_embed(g, user, added=[dota], moderator=mod,
                             dest='ban', reason='флуд в общем')
bn = [f.name for f in ban_e.fields]
check('заблокирован' in (ban_e.title or ''),
      'роль бана: заголовок «Пользователь заблокирован», не «роль ban»')
check(any('Причина' in n for n in bn) and not any('Выданы' in n for n in bn),
      'роль бана: причина на виду, без «Выданы: ban»')
check('флуд в общем' in next(f.value for f in ban_e.fields if 'Причина' in f.name),
      'за что забанили — в карточке')
unban_e = role_change_log_embed(g, user, removed=[dota], moderator=mod, dest='ban')
check('снята' in (unban_e.title or '').lower() or 'Блокировка' in (unban_e.title or ''),
      'снятие роли бана: «Блокировка снята»')
lsrc2 = open(os.path.join(ROOT, 'cogs', 'logs.py'), encoding='utf-8').read()
check('_PUNISH_ROLE_TITLES' in lsrc2 and '_is_our_bot' in lsrc2
      and 'за что' in lsrc2,
      'роль бана от бота не дублирует карточку панели')
empty_ban = role_change_log_embed(g, user, added=[dota], moderator=mod, dest='ban')
eval_ = next(f.value for f in empty_ban.fields if 'Причина' in f.name)
check('не указана' in eval_ and '"не указана"' not in eval_,
      'пустая причина бана — без кавычек, не «роль ban»')
check('send_action_log' in open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read()
      and 'срок наказания истёк' in open(os.path.join(ROOT, 'cogs', 'moderation.py'), encoding='utf-8').read(),
      'снятие бана и истечение роли — той же карточкой, не тонкой строкой')
check('_clean_reason' in lsrc2 and 'На сервере сейчас' in lsrc2,
      'вход без «#N», причина чистится от заглушек')
tval2 = next(f.value for f in to.fields if 'Срок' in f.name)
check('30 мин' in tval2 and '"30 мин"' not in tval2,
      'срок без кавычек — это не имя')
pval = next(f.value for f in to.fields if 'Профиль' in f.name)
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
check(any('Выдал' in n for n in nn) and any('Пользователь' in n for n in nn)
      and any('Было' in n for n in nn) and any('Стало' in n for n in nn),
      f'ник: выдал / пользователь / было / стало ({nn[:4]})')
check('кип' in ' '.join(f.value for f in nick.fields)
      and 'Кипарис' in ' '.join(f.value for f in nick.fields),
      'старый и новый ник видны')
rb = _role_block(dota)
check(dota.mention in rb and 'Dota 2' in rb and str(dota.id) in rb
      and f'Dota 2 · {dota.id}' in rb,
      'роль коротко: тег + имя · id')
check(_roles_cell([dota, dota]).count(dota.mention) == 1,
      'дубль одной роли не рисуем дважды')
lsrc = open(os.path.join(ROOT, 'cogs', 'logs.py'), encoding='utf-8').read()
check('def role_change_log_embed' in lsrc and 'Выданы' in lsrc
      and 'Роли пользователя изменены' in lsrc,
      'карточка ролей: Выдал / Пользователь / Выданы')
check('rows[:20]' in lsrc, 'в эмбед влезает больше полей — карточка полная')

print('== weebook: админ вышел из войса ==')
admin = _Mem(987430047889637426, 'legacy.noper', nick='Discipline')
admin.guild_permissions = SimpleNamespace(
    administrator=True, manage_guild=True, kick_members=True,
    ban_members=True, moderate_members=True)
admin.roles = []
admin.guild = g
vch = _Ch(1550577089252565093, '.')
check(_member_is_staff(admin), 'админ с правами — staff для войса')
check(not _member_is_staff(user), 'обычный участник — не staff')
voice_leave = _styled_log_embed(
    g, 'voice', 'Администратор вышел из голосового канала',
    fields=[
        ('Администратор', _person_block(admin)),
        ('Голосовой канал', _channel_block(vch)),
    ],
    thumbnail=str(admin.display_avatar.url),
)
check((voice_leave.title or '') == '— • Администратор вышел из голосового канала',
      'заголовок weebook как в референсе')
vn = [f.name for f in voice_leave.fields]
check(vn == ['| Администратор:', '| Голосовой канал:'],
      f'две колонки Администратор / Голосовой канал: {vn}')
check(all(f.inline for f in voice_leave.fields),
      'оба поля inline — две колонки weebook')
vv = ' '.join(f.value for f in voice_leave.fields)
check(admin.mention in vv and 'legacy.noper' in vv
      and str(admin.id) in vv and f'legacy.noper · {admin.id}' in vv,
      'админ коротко: mention + username · id')
check(vch.mention in vv and str(vch.id) in vv,
      'канал: mention + id')
check(not getattr(getattr(voice_leave, 'author', None), 'name', None),
      'войс-лог без author')
check(voice_leave._hakumo_log_meta.get('style') == 'weebook',
      'meta.style=weebook для войса')
check('Администратор вышел из голосового канала' in lsrc
      and 'Голосовой канал' in lsrc
      and 'def _member_is_staff' in lsrc,
      'войс-слушатель шлёт weebook-заголовок для стаффа')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
