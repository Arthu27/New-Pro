# -*- coding: utf-8 -*-
"""UX-пикеры ID и мелкий UX (идеи #91-95).

web/static/pickers.js: хелперы datalist-подсказок, статус-чипов, поиска
по спискам, копирования ID, Ctrl+S. Контракты живых списков
/api/guild/<gid>/channels и /roles (список vs dict с error — по этому
пикер отличает «бот офлайн»). Подключение в шаблонах новых страниц.

Запуск: python3 tests/test_ux_pickers.py
"""
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_ux_test_')
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


EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')

print('== 1. pickers.js: хелперы и чистота ==')
js = open(os.path.join(ROOT, 'web/static/pickers.js'), encoding='utf-8').read()
for fn in ('window.pickerLoad', 'window.pickerExtractId', 'window.attachIdPicker',
           'window.attachListFilter', 'window.bindCopyId', 'window.bindCtrlS'):
    check(fn in js, f'хелпер {fn} на месте')
check("'/api/guild/' + gid + '/channels'" in js
      and "'/api/guild/' + gid + '/roles'" in js, 'живые эндпоинты в хелпере')
check('Array.isArray(d)' in js and 'd.channels' in js,
      'различение списка и dict-ошибки (онлайн-флаг)')
check(('(' + chr(92) + 'd{5,24})') in js and (chr(92) * 2 + 'd{5,24}') not in js,
      'вытаскивание цифр из <#123> (одиночный слэш — живая регулярка)')
check(not EMOJI_RE.search(js), 'в хелпере нет эмодзи')
css = open(os.path.join(ROOT, 'web/static/style.css'), encoding='utf-8').read()
check('.picker-chip.ok' in css and '.picker-chip.bad' in css
      and '[data-copy-id]' in css, 'стили чипов и копирования в style.css')

print('== 2. Контракты живых списков (FakeBot) ==')
import discord  # noqa: E402

appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def _channel(cid, name, ctype, position):
    return SimpleNamespace(id=cid, name=name, type=ctype, position=position,
                           category=None, topic='', nsfw=False,
                           slowmode_delay=0, bitrate=64000, user_limit=0,
                           members=[], created_at=datetime(2026, 1, 1),
                           mention=f'<#{cid}>')


_GUILD = SimpleNamespace(
    id=777, name='Тестхейм',
    channels=[
        _channel(30, 'общий', discord.ChannelType.text, 1),
        _channel(10, 'хаб', discord.ChannelType.category, 0),
        _channel(20, 'голосовой', discord.ChannelType.voice, 0),
    ],
    roles=[
        SimpleNamespace(id=1, name='@everyone', color=0, members=list(range(99))),
        SimpleNamespace(id=2, name='Модеры', color=0, members=list(range(9))),
        SimpleNamespace(id=3, name='Админы', color=0, members=list(range(3))),
    ])


class _FakeBot:
    guilds = [_GUILD]

    def get_guild(self, gid):
        return _GUILD if gid == 777 else None


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


appmod.set_bot_instance(None)
login('mod')
offline = client.get('/api/guild/777/channels').get_json()
check(isinstance(offline, dict) and offline.get('error')
      and offline.get('channels') == [],
      'офлайн-каналы — dict с error и пустым channels (пикер ловит)')
check(client.get('/api/guild/777/roles').get_json() == [],
      'офлайн-роли — пустой список')

appmod.set_bot_instance(_FakeBot())
ch = client.get('/api/guild/777/channels').get_json()
check(isinstance(ch, list) and len(ch) == 3, 'онлайн-каналы — голый список')
check([c['id'] for c in ch] == ['10', '20', '30'],
      'сортировка (category_pos, position): хаб и голос (-1,0) по исходному порядку, общий (-1,1) позже')
check({c['type'] for c in ch} == {'category', 'text', 'voice'},
      'типы в словарных словах пикера')
ro = client.get('/api/guild/777/roles').get_json()
check(isinstance(ro, list) and [r['name'] for r in ro] == ['Модеры', 'Админы'],
      '@everyone пропущен, сортировка по числу участников')

print('== 3. Подключение в шаблонах ==')
j2c = open(os.path.join(ROOT, 'web/templates/j2c.html'), encoding='utf-8').read()
an = open(os.path.join(ROOT, 'web/templates/anime_daily.html'), encoding='utf-8').read()
bd = open(os.path.join(ROOT, 'web/templates/birthdays.html'), encoding='utf-8').read()
so = open(os.path.join(ROOT, 'web/templates/social.html'), encoding='utf-8').read()
for name, tpl in (('j2c', j2c), ('anime', an), ('birthdays', bd), ('social', so)):
    check('/static/pickers.js' in tpl, f'{name}: хелпер подключён')
    check(not EMOJI_RE.search(tpl), f'{name}: эмодзи не появились')
check("kind: 'voice'" in j2c and "kind: 'category'" in j2c,
      'j2c: лобби — голосовой, категория — категория')
check('id="j2LobbyStatus"' in j2c and 'id="j2CategoryStatus"' in j2c,
      'j2c: статус-слоты у полей')
check("kind: 'text'" in an and "kind: 'role'" in an
      and 'id="anChannelStatus"' in an and 'id="anRoleStatus"' in an,
      'anime: канал текстовый, роль — роль, статусы у полей')
check("kind: 'text'" in bd and "kind: 'role'" in bd
      and 'id="bdSetChannelStatus"' in bd and 'id="bdSetRoleStatus"' in bd,
      'birthdays: пикеры канала и роли со статусами')

print('== 4. Поиск по спискам ==')
check('id="j2RoomSearch"' in j2c and "attachListFilter(document.getElementById('j2RoomSearch'), 'j2Rooms', '.j2-row')" in j2c,
      'j2c: поиск по комнатам')
check('id="bdSearch"' in bd and "'bdList', '.bd-row'" in bd,
      'birthdays: поиск по календарю')
check('id="soEventSearch"' in so and 'id="soMatchSearch"' in so
      and "'soEvents', '.so-row'" in so and "'soMatches', '.so-row'" in so,
      'social: поиск по событиям и поискам')

print('== 5. Копирование ID и Ctrl+S ==')
check(j2c.count('data-copy-id') >= 2 and 'bindCopyId(document)' in j2c,
      'j2c: копирование канала и владельца')
check('bindCopyId(document)' in so, 'social: копирование подключено')
check('bindCtrlS(j2Save)' in j2c, 'j2c: Ctrl+S сохраняет')
check('bindCtrlS(function () { anSave(false); })' in an, 'anime: Ctrl+S сохраняет')
check('bindCtrlS(bdSaveSettings)' in bd, 'birthdays: Ctrl+S сохраняет')
check('ctrlKey' in js and 'preventDefault()' in js,
      'Ctrl+S не отправляет страницу')

print('== 6. Выбор без ручного ID (интерактивные пикеры везде) ==')

# 6.1 — хелперы в pickers.js
check('window.attachSelectPicker' in js and 'window.attachMemberPicker' in js,
      'в pickers.js есть attachSelectPicker и attachMemberPicker')
sel_fn = js[js.index('window.attachSelectPicker'):]
sel_fn = sel_fn[:sel_fn.index('window.attachMemberPicker')]
mem_fn = js[js.index('window.attachMemberPicker'):]
check('pickerLoad' in sel_fn and 'noneLabel' in sel_fn,
      'select-пикер: источник pickerLoad + none-вариант')
check('ранее выбрано (удалено с сервера)' in sel_fn,
      'select-пикер: устаревшее значение показывается явно, не теряется молча')
check('dispatchEvent' not in sel_fn,
      'select-пикер НЕ диспатчит change (легаси-автосейвы не срабатывают при заполнении)')
check('opts.value' in sel_fn, 'select-пикер: явное начальное значение (opts.value)')
check('datalist' in mem_fn and 'member-card/suggest' in mem_fn,
      'member-пикер: datalist + живой suggest участников')
check('setTimeout' in mem_fn and '250' in mem_fn, 'member-пикер: debounce 250 мс')
check('pickerExtractId' in mem_fn, 'member-пикер: нормализация значения через pickerExtractId')


def tpl(name):
    return open(os.path.join(ROOT, 'web/templates', name), encoding='utf-8').read()


# 6.2 — каналы/роли стали <select>
SELECT_FIELDS = (
    ('anime_daily.html', ('anChannel', 'anRole')),
    ('birthdays.html', ('bdSetChannel', 'bdSetRole')),
    ('j2c.html', ('j2Lobby', 'j2Category')),
    ('leaderboards.html', ('lbSendCh',)),
    ('meetings.html', ('mtRoleInp',)),
    ('antiraid.html', ('alert_channel_id',)),
    ('automation.html', ('ml-channel', 'ns-channel')),
    ('ticket_settings.html', ('notify-channel-id', 'rules-channel-id',
                              'owner-role-id', 'admin-role-id', 'mod-role-id')),
)
for fname, ids in SELECT_FIELDS:
    t = tpl(fname)
    for fid in ids:
        check(re.search(r'<select[^>]*id="%s"' % re.escape(fid), t) is not None,
              f'{fname}: #{fid} — <select>')
    check('/static/pickers.js' in t and 'attachSelectPicker' in t,
          f'{fname}: pickers.js подключён и attachSelectPicker вызван')

# 6.3 — выбор участников
MEMBER_FIELDS = (
    ('leaderboards.html', 'lbRankInp'),
    ('antiraid.html', 'wl-input'),
    ('mod_settings.html', 'msWlIn'),
    ('antifake.html', 'afTestUid'),
    ('karma.html', 'kmFilter'),
    ('ladder.html', 'ldUser'),
    ('mod_control.html', 'mcAmnestyId'),
    ('mod_insights.html', 'miDossierId'),
    ('mod_schedule.html', 'msUserId'),
    ('temp_moderation.html', 'newUser'),
    ('replay.html', 'rpUser'),
    ('dashboard.html', 'notif-discord-id'),
    ('member_profile.html', 'search'),
    ('proofs.html', 'pf-wl-id'),
    ('mod_tools.html', 'ghost-user'),
)
for fname, fid in MEMBER_FIELDS:
    t = tpl(fname)
    check(attach_ok := ('attachMemberPicker' in t and fid in t and '/static/pickers.js' in t),
          f'{fname}: #{fid} — member-пикер подключён')

t = tpl('member_profile.html')
check('attachSearchPicker()' in t and 'function attachSearchPicker' in t,
      'member_profile: пикер перепривязывается при смене сервера')
t = tpl('proofs.html')
check('<select id="pf-wl-role"' in t and 'attachSelectPicker' in t
      and "$('pf-wl-id').style.display" in t,
      'proofs: белый список — участник из подсказок / роль из списка (переключатель)')

# 6.4 — роль/лог-канал Tag Jail через живые списки
t = tpl('tagjail.html')
check("t: 'role_sel'" in t and "t: 'channel_sel'" in t
      and 'data-live="jail_role_id"' in t and 'data-live="log_channel_id"' in t,
      'tagjail: jail-роль и лог-канал — живые select')
check('/static/pickers.js' in t and 'attachSelectPicker' in t,
      'tagjail: pickers.js подключён')
rt = open(os.path.join(ROOT, 'web/routes/tagjail.py'), encoding='utf-8').read()
check("'gid': str(guild.id)" in rt, 'tagjail API: gid отдаётся пикеру')
check('int(v or 0)' in rt, 'tagjail API: пустой select = 0 (выкл), без ошибок парсинга')

# 6.5 — роуты прокидывают guild_id для пикеров
au = open(os.path.join(ROOT, 'web/routes/automation.py'), encoding='utf-8').read()
check('guild_id=ctx.active_guild_id()' in au, 'automation route: guild_id в контексте')
pg = open(os.path.join(ROOT, 'web/routes/pages.py'), encoding='utf-8').read()
check("render_template ('temp_moderation.html'" in pg and re.search(r"temp_moderation\.html'.*guild_id", pg) is not None,
      'pages route: temp_moderation получает guild_id')
mp = open(os.path.join(ROOT, 'web/routes/modplus.py'), encoding='utf-8').read()
check("render_template ('proofs.html'" in mp and 'main_guild_id' in mp,
      'modplus route: proofs получает main_guild_id')

# 6.6 — ручного ввода ID в конвертированных шаблонах не осталось
BAD = re.compile(r'placeholder="[^"]*(?:ID участника|ID канала|ID роли|ID сервера|ID для|ID \(|начните.*ID)[^"]*"')
LEFTOVER = []
for fname in ('anime_daily.html', 'birthdays.html', 'j2c.html', 'leaderboards.html',
              'meetings.html', 'antiraid.html', 'automation.html', 'mod_settings.html',
              'tagjail.html', 'ticket_settings.html', 'temp_moderation.html', 'proofs.html',
              'antifake.html', 'karma.html', 'ladder.html', 'mod_control.html',
              'mod_insights.html', 'mod_schedule.html', 'replay.html', 'dashboard.html',
              'member_profile.html'):
    if BAD.search(tpl(fname)):
        LEFTOVER.append(fname)
check(not LEFTOVER, f"ни одного placeholder'а с ручным ID ({LEFTOVER or 'чисто'})")

t = tpl('antiraid.html')
check("el.id === 'alert_channel_id'" in t and "el.tagName === 'INPUT' && el.id === 'alert_channel_id'" not in t,
      'antiraid: заливка конфига переведена с INPUT-гварда на id (select)')
check('ensureChannelPicker' in t, 'antiraid: защита от гонки «конфиг раньше каналов»')
t = tpl('automation.html')
check('nsEnsurePicker' in t and "var GID = {{ guild_id | tojson }};" in t,
      'automation: nsEnsurePicker + GID из контекста')
t = tpl('j2c.html')
check('>Канал-лобби<' in t, 'j2c: подпись поля без «ID»')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
