# -*- coding: utf-8 -*-
"""Призыв модераторов из тикета: когда ИИ не справился.

- подписи причин эскалации (TICKET_SUMMON_REASONS / escalation_reason_label);
- конфиг штабного канала (ticket_notify_cfg — punenama ticket-notify-channel);
- build_staff_summon_embed: карточка с полями, футером-привязкой gid:cid;
- mark_summon_claimed: статус «в работе у …» после клика «Взять в работу»;
- StaffSummonView: persistent-кнопка, права _is_staff, вариант «уже занят»;
- _send_staff_summon / _escalate_ticket на фейковом guild (asyncio);
- шаблон настроек тикетов: живое превью-меню призыва.

Запуск: python3 tests/test_ticket_escalate.py
"""
import asyncio
import importlib
import json
import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_escalate_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

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


import discord  # noqa: E402,F401 — нужен когу при импорте
import cogs.ticket as T  # noqa: E402


# ───────────────────────────── Фейки Discord ─────────────────────────────
class FakePerms:
    def __init__(self, manage_guild=False, administrator=False, manage_messages=False):
        self.manage_guild = manage_guild
        self.administrator = administrator
        self.manage_messages = manage_messages


class FakeRole:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name
        self.mention = f'<@&{rid}>'


class FakeMember:
    def __init__(self, mid, name='Member'):
        self.id = mid
        self.name = name
        self.mention = f'<@{mid}>'
        self.roles = []
        self.guild_permissions = FakePerms()
        self.guild = None

    def __str__(self):
        return self.name


class FakeMsg:
    def __init__(self, mid, channel):
        self.id = mid
        self.channel = channel


class FakeChannel:
    def __init__(self, cid, name):
        self.id = cid
        self.name = name
        self.mention = f'<#{cid}>'
        self.guild = None
        self.sent = []

    async def send(self, content=None, embed=None, view=None):
        self.sent.append({'content': content, 'embed': embed, 'view': view})
        return FakeMsg(9000 + len(self.sent), self)


class FakeIcon:
    url = 'https://i.imgur.com/fake-icon.png'


class FakeGuild:
    def __init__(self, gid, name='Сервер'):
        self.id = gid
        self.name = name
        self.icon = None
        self.roles = []
        self.members = {}
        self.channels = {}

    def get_member(self, mid):
        return self.members.get(int(mid))

    def get_channel(self, cid):
        return self.channels.get(int(cid))

    def get_role(self, rid):
        return next((r for r in self.roles if int(r.id) == int(rid)), None)

    async def fetch_channel(self, cid):
        return self.channels.get(int(cid))


# ═══ 1. Причины эскалации ════════════════════════════════════════════════
print('== причины призыва ==')
check(isinstance(T.TICKET_SUMMON_REASONS, dict) and len(T.TICKET_SUMMON_REASONS) >= 10,
      f'реестр причин пополнен ({len(T.TICKET_SUMMON_REASONS)} шт.)')
check(all(isinstance(v, str) and v.strip() for v in T.TICKET_SUMMON_REASONS.values()),
      'у всех причин человекочитаемые подписи')
for key in ('max_messages', 'ai_error', 'talepte_bulundu', 'ban_talebi', 'agir_ihlal',
            'manual', 'другой'):
    check(key in T.TICKET_SUMMON_REASONS, f'причина «{key}» покрыта подписью')
check(T.escalation_reason_label('max_messages') == T.TICKET_SUMMON_REASONS['max_messages'],
      'известная причина → своя подпись')
check(T.escalation_reason_label('unknown_reason') == 'Модераторы получают управление',
      'неизвестная причина → общая фраза')
check(T.escalation_reason_label(None) == 'Модераторы получают управление',
      'пустая причина → общая фраза')

# ═══ 2. Конфиг штабного канала ═══════════════════════════════════════════
print('== ticket_notify_cfg ==')
check(T.ticket_notify_cfg(777) == {}, 'нет файла → пустой конфиг')
with open('data/ticket_notify_777.json', 'w', encoding='utf-8') as fp:
    json.dump({'notify_channel_id': '555', 'mod_role_id': '4242'}, fp)
cfg = T.ticket_notify_cfg(777)
check(cfg.get('notify_channel_id') == '555' and cfg.get('mod_role_id') == '4242',
      'канал и роль читаются из файла настроек')
with open('data/ticket_notify_778.json', 'w', encoding='utf-8') as fp:
    fp.write('{"failed": true')
check(T.ticket_notify_cfg(778) == {}, 'битый JSON → пустой конфиг, без падения')
with open('data/ticket_notify_779.json', 'w', encoding='utf-8') as fp:
    json.dump(['список', 'не', 'словарь'], fp)
check(T.ticket_notify_cfg(779) == {}, 'не-словарь → пустой конфиг')
check(T.SUPPORT_ROLE_NAME == 'Поддержка', 'резервная роль поддержки — «Поддержка»')

# ═══ 3. Хелперы текста ═══════════════════════════════════════════════════
print('== обрезка текста ==')
check(T._clip_text('  слова   через  пробелы  ') == 'слова через пробелы',
      'пробелы схлопываются')
long_txt = 'очень ' * 60
check(len(T._clip_text(long_txt, 40)) == 40 and T._clip_text(long_txt, 40).endswith('…'),
      'длинный текст обрезан с многоточием')
state0 = {'history': [
    {'role': 'assistant', 'content': 'здравствуйте'},
    {'role': 'user', 'content': 'мне нужен модератор'},
    {'role': 'assistant', 'content': 'секунду'},
]}
check(T._last_user_phrase(state0) == 'мне нужен модератор',
      'берётся последняя фраза клиента')
check(T._last_user_phrase({'history': []}) == '' and T._last_user_phrase({}) == '',
      'без истории фразы нет')
dirty = {'history': [{'role': 'user'}, 'мусор', {'role': 'user', 'content': 'ok'}]}
check(T._last_user_phrase(dirty) == 'ok', 'битые записи истории отброшены')

# ═══ 4. Карточка призыва ═════════════════════════════════════════════════
print('== карточка призыва ==')
guild = FakeGuild(777000000000000001)
guild.icon = FakeIcon()
owner = FakeMember(100001, 'Клиент')
guild.members[100001] = owner
ticketch = FakeChannel(777000000000000555, 'ticket-0001')
state = {
    'user_id': '100001',
    'ai_message_count': 4,
    'detected_category': 'техническая проблема',
    'history': [{'role': 'user', 'content': 'бот не отвечает, почините'}],
}
e = T.build_staff_summon_embed(guild=guild, channel=ticketch, state=state, reason='max_messages')
fname = dict((f.name, f.value) for f in e.fields)
check(e.title == 'Призыв модераторов: нужна помощь в тикете', 'заголовок карточки')
check(int(e.color) == T.SUMMON_COLOR, 'цвет «ждёт модератора»')
check('Тикет' in fname and ticketch.mention in fname['Тикет'], 'поле «Тикет» с mention-ссылкой')
check(fname.get('Причина') == T.TICKET_SUMMON_REASONS['max_messages'],
      'поле «Причина» с подписью лимита ИИ')
check(fname.get('Переписка с ИИ') == '4 сообщений', 'счётчик переписки с ИИ')
check('Клиент' in fname and owner.mention in fname['Клиент'], 'клиент с упоминанием')
check(fname.get('Тема') == 'техническая проблема', 'тема тикета')
check('бот не отвечает' in fname.get('Последняя фраза клиента', ''), 'последняя фраза клиента')
check(fname.get('Статус') == 'Ожидает модератора', 'статус ожидания на старте')
foot = e.footer.text or ''
m = re.match(r'призыв:(\d+):(\d+) · Aether', foot)
check(bool(m) and m.group(1) == str(guild.id) and m.group(2) == str(ticketch.id),
      f'футер-привязка gid:cid ({foot})')
check(e.thumbnail and 'icon' in str(e.thumbnail.url), 'иконка сервера в миниатюре')

no_state = T.build_staff_summon_embed(guild=guild, channel=ticketch, state={}, reason='другой')
fn2 = [f.name for f in no_state.fields]
check('Клиент' not in fn2 and 'Последняя фраза клиента' not in fn2 and 'Тема' not in fn2,
      'пустой state → карточка без лишних полей')
check(any(f.name == 'Статус' for f in no_state.fields), 'статус есть даже без клиента')

# ═══ 5. «Взять в работу» ═════════════════════════════════════════════════
print('== закрепление за модератором ==')
claimer = FakeMember(4242001, 'МодКатя')
orig_fields = len(e.fields)
e2 = T.mark_summon_claimed(e, claimer)
check(e2 is not None and e2 is not e, 'возвращается копия, не тот же объект')
check(int(e2.color) == T.SUMMON_CLAIMED_COLOR, 'цвет переключился на «в работе»')
status_val = dict((f.name, f.value) for f in e2.fields).get('Статус', '')
check(status_val.startswith(f'В работе у {claimer.mention}'), f'статус закреплён: {status_val}')
check(len(e.fields) == orig_fields and
      dict((f.name, f.value) for f in e.fields).get('Статус') == 'Ожидает модератора',
      'исходная карточка не повреждена')
check(T.mark_summon_claimed(None, claimer) is None, 'None-embed не роняет функцию')
bare = discord.Embed(title='мини')
e3 = T.mark_summon_claimed(bare, claimer)
check(any(f.name == 'Статус' for f in e3.fields), 'статус добавляется, если его не было')

# ═══ 6. Вьюха призыва ════════════════════════════════════════════════════
print('== StaffSummonView ==')
view = T.StaffSummonView()
check(view.timeout is None, 'вьюха persistent (без timeout)')
btn = view.children[0]
check(btn.custom_id == 'ticket_staff_claim_btn', 'custom_id кнопки постоянный')
check(btn.label == 'Взять в работу' and not btn.disabled, 'кнопка активна с подписью')
check(int(btn.style) == int(discord.ButtonStyle.success), 'зелёный стиль кнопки')
busy = T.StaffSummonView(claimed_by='МодКатя')
check(busy.children[0].disabled and busy.children[0].label.startswith('В работе:'),
      'вариант «уже взят» блокирует повторный клик')

with open('data/ticket_notify_777.json', 'w', encoding='utf-8') as fp:
    json.dump({'notify_channel_id': '555', 'mod_role_id': '4242'}, fp)
g777 = FakeGuild(777)
staff_g = FakeMember(1, 'G'); staff_g.guild_permissions = FakePerms(manage_guild=True)
staff_a = FakeMember(2, 'A'); staff_a.guild_permissions = FakePerms(administrator=True)
staff_m = FakeMember(3, 'M'); staff_m.guild_permissions = FakePerms(manage_messages=True)
by_role = FakeMember(4, 'R'); by_role.guild = g777; by_role.roles = [FakeRole(4242, 'Опекуны')]
by_name = FakeMember(5, 'N'); by_name.guild = FakeGuild(999999)
by_name.roles = [FakeRole(300001, T.SUPPORT_ROLE_NAME)]
pleb = FakeMember(6, 'P'); pleb.guild = g777
check(view._is_staff(staff_g) and view._is_staff(staff_a) and view._is_staff(staff_m),
      'права manage_guild/administrator/manage_messages считаются персоналом')
check(view._is_staff(by_role), 'роль из mod_role_id настроек тоже персонал')
check(view._is_staff(by_name), 'роль «Поддержка» по имени тоже персонал')
check(not view._is_staff(pleb), 'обычный участник — не персонал')
ghost = FakeMember(7, 'G2'); ghost.guild_permissions = FakePerms()  # guild=None
check(not view._is_staff(ghost), 'участник без гильдии не ломает проверку')

# ═══ 7. Async: отправка призыва и эскалация ══════════════════════════════
print('== эскалация (async) ==')
mod_ch = FakeChannel(555, 'штаб-комната')
guild2 = FakeGuild(777)
guild2.channels[555] = mod_ch
guild2.roles.append(FakeRole(4242, 'Модерация'))
ticketch2 = FakeChannel(1234001, 'ticket-0007')
ticketch2.guild = guild2
cog = object.__new__(T.Ticket)  # без __init__ (он вешает views на бота)
cog.bot = None

st = {'user_id': '100001', 'ai_message_count': 2, 'history': [], 'staff_notified': False}
ok = asyncio.run(cog._send_staff_summon(ticketch2, st, 'ai_error'))
check(ok is True, 'призыв по конфигу доставлен')
check(len(mod_ch.sent) == 1, 'сообщение приземлилось в штабной канал')
msg0 = mod_ch.sent[0]
check(isinstance(msg0['view'], T.StaffSummonView), 'кнопка «Взять в работу» прикреплена')
check(msg0['content'] == '<@&4242>', 'пинг роли модераторов из настроек')
check(msg0['embed'].footer.text.startswith('призыв:777:1234001'), 'футер с привязкой к тикету')
check(st.get('summon_channel_id') == '555' and st.get('summon_message_id') == str(9000 + 1),
      'id карточки призыва сохранены в состоянии тикета')

# без конфига и лог-канала на фейке → честный False, без падения
os.remove('data/ticket_notify_777.json')
modless = FakeGuild(5550001)  # без каналов/категорий — ensure_log_channel не выстрелит
orphan = FakeChannel(1234002, 'ticket-0008')
orphan.guild = modless
st2 = {'user_id': '9', 'history': [], 'ai_message_count': 0, 'staff_notified': False}
bad_ok = asyncio.run(cog._send_staff_summon(orphan, st2, 'ai_error'))
check(bad_ok is False, 'без настройки канала и без лог-канала → False (тихо, без падения)')

# полная эскалация: embed в тикет + призыв в штаб + пинг роли + сохранение state
with open('data/ticket_notify_777.json', 'w', encoding='utf-8') as fp:
    json.dump({'notify_channel_id': '555', 'mod_role_id': '4242'}, fp)
guild3 = FakeGuild(777)
mod_ch3 = FakeChannel(555, 'штаб-комната-2')
guild3.channels[555] = mod_ch3
guild3.roles.append(FakeRole(4242, T.SUPPORT_ROLE_NAME))
ticketch4 = FakeChannel(1234009, 'ticket-0009')
ticketch4.guild = guild3
st4 = {'user_id': '100001', 'ai_message_count': 9, 'history': [
    {'role': 'user', 'content': 'тут полный тупик'}], 'staff_notified': False}
asyncio.run(cog._escalate_ticket(ticketch4, st4, 'max_messages'))
check(st4['staff_notified'] is True and st4['status'] == 'escalated',
      'тикет помечен «передан модераторам»')
check(st4.get('escalated_at'), 'время эскалации записано')
sent_embeds = [s['embed'] for s in ticketch4.sent if s['embed'] is not None]
check(any('Передано модератору' in (x.description or '') for x in sent_embeds),
      'клиенту в тикет ушло «Передано модератору»')
check(len(mod_ch3.sent) == 1, 'штаб получил карточку призыва из эскалации')
role_pings = [s['content'] for s in ticketch4.sent if s['content']]
check(any('<@&4242>' in (c or '') for c in role_pings), 'в тикете пинганута роль поддержки')
p = f'data/ai_tickets_777.json'
check(os.path.exists(p), 'состояние тикета сохранено на диск')
with open(p, encoding='utf-8') as fp:
    saved = json.load(fp)
check(saved.get('1234009', {}).get('status') == 'escalated',
      'в файле статус escalated по ключу канала')

# повторная эскалация не спамит
before_t = len(ticketch4.sent)
before_m = len(mod_ch3.sent)
asyncio.run(cog._escalate_ticket(ticketch4, st4, 'max_messages'))
check(len(ticketch4.sent) == before_t and len(mod_ch3.sent) == before_m,
      'повторная эскалация не дублирует сообщения')

# ═══ 8. Склейка в исходнике ══════════════════════════════════════════════
print('== склейка в code ==')
src = open(os.path.join(ROOT, 'cogs', 'ticket.py'), encoding='utf-8').read()
flat = re.sub(r'\s+', '', src)
check('add_view(StaffSummonView())' in flat, 'постоянная вьюха зарегистрирована у бота')
check('awaitself._send_staff_summon(channel,state,reason)' in flat,
      '_escalate_ticket вызывает призыв штаба')
check("state['summon_message_id']" in flat and "state['summon_channel_id']" in flat,
      'id карточки призыва бэкапятся в state')
check('reason_text=TICKET_SUMMON_REASONS' in flat,
      'embed в тикете делит тот же реестр причин')
check(flat.index('classStaffSummonView') < flat.index('classTicket(commands.Cog)'),
      'вьюха объявлена до кога')

ta = open(os.path.join(ROOT, 'web', 'routes', 'tickets_admin.py'), encoding='utf-8').read()
check('/api/guild/<guild_id>/ticket-notify-channel' in re.sub(r'\s+', '', ta),
      'API настройки штабного канала на месте')

# ═══ 9. Шаблон настроек тикетов ══════════════════════════════════════════
print('== шаблон: меню призыва ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'ticket_settings.html'), encoding='utf-8').read()
check('Меню призыва модераторов' in tpl, 'заголовок блока-превью')
check('summon-preview' in tpl, 'карточка превью призыва смонтирована')
check('sp-claim' in tpl and 'Взять в работу' in tpl, 'пример кнопки «Взять в работу»')
check('notify-channel-id' in tpl and 'mod-role-id' in tpl, 'поля канала и роли на месте')
check('Призыв модераторов: нужна помощь в тикете' in tpl,
      'превью повторяет заголовок живой карточки (embed title в коде выше)')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов в шаблоне')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
