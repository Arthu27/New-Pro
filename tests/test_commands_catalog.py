# -*- coding: utf-8 -*-
"""Каталог команд: AST-реестр всех команд, API панели, красивая страница.

- services/command_registry: скан cogs/*.py собирает все slash/prefix/
  подкоманды с описаниями, алиасами, категориями; кэш по mtime;
- API /api/commands/catalog: mod+, фильтры q/kind/cat, права гостя;
- шаблон commands.html: поиск, чипы разделов, карточки, модалка,
  скелетон, быстрые действия только для исполняемых команд и admin+;
- cogs/help.py: справка показывает ВСЕ разделы (ACL + каталог), без
  дублей логов/AI, select-меню умещается в лимит Discord (25 опций).

Запуск: python3 tests/test_commands_catalog.py
"""
import importlib
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_cmdcat_test_')
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


print('== 1. Реестр команд ==')
from services import command_registry as CR  # noqa: E402

data = CR.catalog(force=True)
check(data['total'] >= 300, f"собрано {data['total']} команд (≥300 всех модулей)")
check(data['slash'] >= 120 and data['prefix'] >= 50,
      f"slash {data['slash']} + prefix {data['prefix']} — оба вида на месте")
check(data['total'] == data['slash'] + data['subs'] + data['prefix'],
      'счётчики сходятся: total = slash + subs + prefix')
check(len(data['categories']) >= 12, f"разделов ≥12 ({len(data['categories'])})")
labels = [c['label'] for c in data['categories']]
for need in ('Модерация', 'Тикеты', 'Музыка', 'Экономика', 'Уровни и карма'):
    check(need in labels, f'раздел «{need}» в каталоге')

names = [c['name'] for c in data['commands']]
check(len(names) == len(set(names)), 'имена команд не дублируются')
for cmd_name in ('play', 'pause', 'queue'):
    hit = next((c for c in data['commands'] if c['name'] == cmd_name
                and c['cat'] == 'music'), None)
    check(hit is not None, f'музыкальная команда {cmd_name} найдена в разделе Музыка')

music = next(c for c in data['commands'] if c['name'] == 'play' and c['cat'] == 'music')
check('игра' in music['desc'].lower() or 'трек' in music['desc'].lower()
      or 'музык' in music['desc'].lower(),
      f"у play русское описание ({music['desc']!r})")
check(music['module'] == 'music_cog.py', 'модуль команды указан')
check('играй' in music['aliases'], f"алиасы подхвачены: {music['aliases']}")

sub = next((c for c in data['commands'] if c['kind'] == 'sub' and c['group']), None)
check(sub is not None and ' ' in sub['name'],
      f"подкоманды групп развёрнуты ('{sub['name'] if sub else '?'}')")

nodesc = sum(1 for c in data['commands'] if c['desc'] == 'Описание скоро появится')
check(nodesc <= int(data['total'] * 0.15),
      f'описания почти у всех (без описания лишь {nodesc})')

exe = {c['bare'] for c in data['commands'] if c['executable']}
check(exe <= set(CR.EXECUTABLE) and exe,  # jail/unjail точно есть
      '«Выполнить» предлагается только командам из серверного белого списка')
check(exe == {c['bare'] for c in data['commands'] if c['bare'] in CR.EXECUTABLE},
      'все подходящие команды помечены исполняемыми')

print('== 2. Кэш реестра ==')
cached = CR.catalog()
check(cached is data, 'повторный вызов берётся из кэша (тот же объект)')

print('== 3. API каталога ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


os.environ['DEMO_MODE'] = '0'
try:
    guest = client.get('/api/commands/catalog')
finally:
    os.environ['DEMO_MODE'] = '1'
check(guest.status_code in (302, 401, 403), 'гостю каталог закрыт')

login('uye')
check(client.get('/api/commands/catalog').status_code == 403,
      'uye не читает каталог (mod+)')

login('mod')
r = client.get('/api/commands/catalog')
d = r.get_json()
check(r.status_code == 200 and d['success'], 'мод читает каталог')
check(d['total'] >= 300 and d['shown'] == d['total'] and len(d['commands']) == d['total'],
      'без фильтров отдаётся всё')
check(d['slash'] > 0 and d['prefix'] > 0, 'счётчики типов в ответе')

r = client.get('/api/commands/catalog?q=play')
d = r.get_json()
check(all('play' in c['name'] or 'play' in c['desc'].lower()
          or any('play' in a for a in c['aliases']) for c in d['commands']),
      f'поиск q=play — только релевантные ({d["shown"]} шт)')
r = client.get('/api/commands/catalog?cat=music')
d = r.get_json()
check(d['commands'] and all(c['cat'] == 'music' for c in d['commands']),
      'фильтр по разделу music')
r = client.get('/api/commands/catalog?kind=slash')
d = r.get_json()
check(all(c['kind'] in ('slash', 'sub') for c in d['commands']),
      'фильтр kind=slash включает подкоманды групп')
r = client.get('/api/commands/catalog?kind=prefix&cat=music')
d = r.get_json()
check(d['commands'] and all(c['kind'] == 'prefix' and c['cat'] == 'music'
                            for c in d['commands']),
      'двойной фильтр kind+cat')

print('== 4. Шаблон страницы ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'commands.html'),
           encoding='utf-8').read()
for fid in ('cmdxQ', 'cmdxKind', 'cmdxCats', 'cmdxGrid', 'cmdxCount',
            'stTotal', 'stSlash', 'stPrefix', 'stCats', 'cmdModal'):
    check(f'id="{fid}"' in tpl, f'контрол {fid} на месте')
check('/api/commands/catalog' in tpl, 'каталог подключён')
check("role=\"button\"" in tpl and 'tabindex="0"' in tpl,
      'карточки доступны с клавиатуры')
check('aria-label' in tpl and 'cmdx-skel' in tpl,
      'a11y-подписи и скелетон загрузки')
check('CAN_EDIT' in tpl and 'c.executable' in tpl,
      'быстрые действия ограничены исполняемыми командами')
check('/api/execute-command' in tpl, 'выполнение команд подключено')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
EMOJI = re.compile(r'[\U0001F000-\U0001FAFF☀-➿⬀-⯿⏩-⏿]')
check(not EMOJI.search(tpl), 'в шаблоне нет эмодзи')
ext = open(os.path.join(ROOT, 'web', 'routes_extra.py'), encoding='utf-8').read()
check('commands_panel' in ext, 'модуль commands_panel зарегистрирован')
old_fragments = ('{ cmd: \'ban\', icon' in tpl and 'fa-user-times' in tpl)
check(not old_fragments, 'старый хардкод из 13 команд убран — каталог живой')

print('== 5. /help показывает все разделы ==')
import cogs.help as HP  # noqa: E402
ov = HP.build_help_embed()
field_names = ' | '.join(f.name for f in ov.fields)
for need in ('Музыка', 'Экономика', 'Уровни и карма', 'Голосовые', 'Модерация', 'Тикеты'):
    check(need in field_names, f'/help overview содержит раздел «{need}»')
check('Логи и аудит' not in field_names and 'AI ' not in field_names,
      'нет дублей пересекающихся с ACL разделов (Логи и аудит / AI)')
# select-меню Discord: максимум 25 опций
n_opts = 1 + len(HP._all_category_labels())
check(n_opts <= 25, f'select-меню умещается в лимит Discord ({n_opts} ≤ 25)')
e_music = HP.build_help_embed(category_id='Музыка')
check('Музыка' in e_music.title and 'команд' in (e_music.description or ''),
      'страница раздела «Музыка» собирается')
# ACL-фильтрация ядра не сломана
e_mod = HP.build_help_embed(category_id='Модерация')
mod_text = ' '.join(f.value for f in e_mod.fields)
check('`ban`' in mod_text and '`tempban`' in mod_text,
      'мод-ядро справки прежнее (ban/tempban на месте)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
