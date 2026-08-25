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


print('== 1. Реестр команд (LEAN — боевой состав по умолчанию) ==')
from services import command_registry as CR  # noqa: E402

data = CR.catalog(force=True)
check(data['total'] == 25, f"lean: собрано {data['total']} живых команд (после чистки — 25)")
check(data['slash'] == 13 and data['prefix'] == 12,
      f"lean: slash {data['slash']} + prefix {data['prefix']} — оба вида на месте")
check(data['total'] == data['slash'] + data['subs'] + data['prefix'],
      'счётчики сходятся: total = slash + subs + prefix')
check(len(data['categories']) >= 6, f"lean: разделов ≥6 ({len(data['categories'])})")
labels = [c['label'] for c in data['categories']]
for need in ('Модерация', 'Тикеты', 'Музыка',
             'Логи и аудит', 'Система'):
    check(need in labels, f'lean: раздел «{need}» в каталоге')
check('Голосовые' not in labels,
      'lean: голосовая статистика удалена владельцем — раздела нет')
check('Экономика' not in labels and 'Уровни и карма' not in labels,
      'lean: спящие системы (экономика/уровни) честно не показываются')
mods = data.get('modules') or {}
check(mods.get('enabled') == 29 and mods.get('sleeping') == 75,  # +activity_stats (без команд)
      f"lean: модулей включено {mods.get('enabled')}, спит {mods.get('sleeping')}")

print('== 1.1. Реестр в BOT_FULL (полный состав) ==')
os.environ['BOT_FULL'] = '1'
full = CR.catalog(force=True)
check(full['total'] >= 250, f"full: собрано {full['total']} команд (≥250)")
full_labels = [c['label'] for c in full['categories']]
for need in ('Экономика', 'Уровни и карма', 'Игры и развлечения'):
    check(need in full_labels, f'full: раздел «{need}» вернулся')
os.environ.pop('BOT_FULL', None)
data = CR.catalog(force=True)

names = [c['name'] for c in data['commands']]
check(len(names) == len(set(names)), 'имена команд не дублируются')
# музыка — боевой модуль: её команды обязаны быть и в lean-каталоге
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

sub = next((c for c in full['commands'] if c['kind'] == 'sub' and c['group']), None)
check(sub is not None and ' ' in sub['name'],
      f"подкоманды групп развёрнуты (в full: '{sub['name'] if sub else '?'}')")
check(not any(c['kind'] == 'sub' for c in data['commands']),
      'lean: групповые подкоманды вычищены из боевого меню')

nodesc = sum(1 for c in data['commands'] if c['desc'] == 'Описание скоро появится')
check(nodesc <= int(data['total'] * 0.15),
      f'описания почти у всех (без описания лишь {nodesc})')

exe = {c['bare'] for c in data['commands'] if c['executable']}
check(exe <= set(CR.EXECUTABLE),  # после чистки whitelist-команды спят — кнопка просто скрыта
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
check(d['total'] == data['total'] and d['shown'] == d['total']
      and len(d['commands']) == d['total'],
      'без фильтров отдаётся весь lean-каталог (как в боте)')
check(d['slash'] > 0 and d['prefix'] > 0, 'счётчики типов в ответе')
check(d.get('modules', {}).get('enabled') == 29
      and d['modules']['sleeping'] == 75,
      'в ответе — счётчик модулей (29 включено / 75 спит)')

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
            'stTotal', 'stSlash', 'stPrefix', 'stCats', 'cmdModal',
            'cmdxModules', 'stModOn', 'stModOff'):
    check(f'id="{fid}"' in tpl, f'контрол {fid} на месте')
check('/cog-manager' in tpl and 'BOT_FULL' in tpl and 'EXTRA_COGS' in tpl,
      'честная подсказка: модули спят, способ разбудить указан')
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

print('== 5. /help показывает все ЖИВЫЕ разделы ==')
import cogs.help as HP  # noqa: E402
ov = HP.build_help_embed()
field_names = ' | '.join(f.name for f in ov.fields)
for need in ('Музыка', 'Система',
             'Модерация', 'Тикеты'):
    check(need in field_names, f'/help overview содержит раздел «{need}»')
check('Голосовые' not in field_names,
      'голосовая статистика удалена из /help (команд нет — раздела нет)')
help_src = open(os.path.join(ROOT, 'cogs', 'help.py'), encoding='utf-8').read()
check('HELP_ENABLED = False' in help_src
      and help_src.count('if not HELP_ENABLED') == 2,
      '!help и /help временно выключены владельцем (флаг HELP_ENABLED)')
check('Экономика' not in field_names and 'Уровни и карма' not in field_names,
      'спящие разделы (экономика/уровни) из /help убраны')
check('Логи и аудит' not in field_names and 'AI ' not in field_names,
      'нет дублей пересекающихся с ACL разделов (Логи и аудит / AI)')
# в полном составе спящие разделы возвращаются
os.environ['BOT_FULL'] = '1'
ov_full = HP.build_help_embed()
check('Экономика' in ' | '.join(f.name for f in ov_full.fields),
      'BOT_FULL=1: раздел «Экономика» вернулся в /help')
os.environ.pop('BOT_FULL', None)
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
