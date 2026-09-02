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

_TMP = tempfile.mkdtemp(prefix='hakumo_cmdcat_test_')
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
# Заказ владельца: боевое слеш-меню — минимум команд. Тикет-система снята
# 2026-08-31, её роль выполняет /report (жалоба карточкой в канал модерации).
# Музыка (/play) снята 2026-09-01 — бот модерационный.
# В меню: modpanel, апелляция, update, afk, report, my-violations.
# Сетап-команды убраны в панель, /afk-remove удалён (AFK спадает авто).
check(data['total'] == 6, f"lean: собрано {data['total']} живых команд (ровно 6)")
check(data['slash'] == 6 and data['prefix'] == 0,
      f"lean: слеш {data['slash']}, префиксных {data['prefix']} — «!»-команд больше нет")
for gone in ('verify-setup', 'report-setup', 'report-settings', 'afk-remove'):
    check(gone not in [c['name'] for c in data.get('commands', [])],
          f'{gone} убран из боевого меню (настройка в панели/авто)')
check(data['total'] == data['slash'] + data['subs'] + data['prefix'],
      'счётчики сходятся: total = slash + subs + prefix')
labels = [c['label'] for c in data['categories']]
for need in ('Модерация', 'Система'):
    check(need in labels, f'lean: раздел «{need}» в каталоге')
check('Музыка' not in labels, 'lean: раздел «Музыка» убран (музыка снята с эксплуатации 2026-09-01)')
check('Тикеты' not in labels, 'lean: раздел «Тикеты» убран (тикет-система снята, жалобы — /report)')
check('Логи и аудит' not in labels,
      'логи остаются вне панельного каталога (заказ «как можно меньше»)')
check('Голосовые' not in labels,
      'lean: голосовая статистика удалена владельцем — раздела нет')
check('Экономика' not in labels and 'Уровни и карма' not in labels,
      'lean: спящие системы (экономика/уровни) честно не показываются')
mods = data.get('modules') or {}
# 30: в лёгком профиле 30 файлов модулей. Событийные коги без команд
# (panel_live, member_store_sync) считаются модулями наравне с остальными.
check(mods.get('enabled') == 30 and mods.get('sleeping') == 7,
      f"lean: модулей включено {mods.get('enabled')}, спит {mods.get('sleeping')} (ожидание 30/7)")

print('== 1.1. Выключенные разделы физически удалены ==')
# Экономика/уровни/игры больше не «спящие» — их файлы удалены с диска,
# поэтому их нет в каталоге ни в каком режиме.
import glob as _glob
for gone_cog in ('cogs/economy_cog.py', 'cogs/level_cog.py',
                 'cogs/fun_cog.py', 'cogs/minigames.py', 'cogs/giveaway.py'):
    check(not os.path.exists(gone_cog), f'файл {gone_cog} удалён')
data = CR.catalog(force=True)

names = [c['name'] for c in data['commands']]
check(len(names) == len(set(names)), 'имена команд не дублируются')
# Музыка снята с эксплуатации (2026-09-01): /play и прочих музыкальных команд
# в боевом каталоге больше нет (music_cog/voice_commands в RETIRED_COGS).
for gone in ('play', 'pause', 'resume', 'skip', 'queue', 'nowplaying',
             'leave', 'musicpanel'):
    check(next((c for c in data['commands'] if c['name'] == gone
                and c['cat'] == 'music'), None) is None,
          f'музыкальная команда {gone} убрана из боевого меню (музыка снята)')

# Lean-профиль: слеш-меню курируемое и минимальное (~7 команд), групповые
# подкоманды вычищены — в каталоге только корневые слеш-команды.
sub = [c for c in data['commands'] if c['kind'] == 'sub' and c.get('group')]
check(len(sub) == 0,
      'lean: групповые подкоманды вычищены из боевого меню')
check(data['slash'] <= 12,
      f'lean: слеш-меню курируемое и короткое ({data["slash"]} команд)')

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
check(d['slash'] > 0 and d['prefix'] == 0,
      'счётчики типов в ответе: слеш есть, префиксных — ноль')
check(d.get('modules', {}).get('enabled') == 30
      and d['modules']['sleeping'] == 7,
      'в ответе — счётчик модулей (30 включено / 7 спит)')

r = client.get('/api/commands/catalog?q=report')
d = r.get_json()
check(all('report' in c['name'] or 'жалоб' in c['desc'].lower()
          or any('report' in a for a in c['aliases']) for c in d['commands']),
      f'поиск q=report — только релевантные ({d["shown"]} шт)')
r = client.get('/api/commands/catalog?cat=music')
d = r.get_json()
check(not d['commands'], 'фильтр по разделу music пуст — музыка снята с эксплуатации')
r = client.get('/api/commands/catalog?kind=slash')
d = r.get_json()
check(all(c['kind'] in ('slash', 'sub') for c in d['commands']),
      'фильтр kind=slash включает подкоманды групп')
r = client.get('/api/commands/catalog?kind=slash&cat=mod')
d = r.get_json()
check(all(c['kind'] in ('slash', 'sub') and c['cat'] == 'mod'
          for c in d['commands']),
      'двойной фильтр kind=slash+cat=mod отдаёт модерацию')

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
for need in ('Система', 'Модерация', 'Жалобы'):
    check(need in field_names, f'/help overview содержит раздел «{need}»')
check('Музыка' not in field_names,
      'раздел «Музыка» убран из /help (музыка снята с эксплуатации 2026-09-01)')
check('Голосовые' not in field_names,
      'голосовая статистика удалена из /help (команд нет — раздела нет)')
help_src = open(os.path.join(ROOT, 'cogs', 'help.py'), encoding='utf-8').read()
check('HELP_ENABLED = False' in help_src
      and help_src.count('if not HELP_ENABLED') == 1
      and '@commands.command' not in help_src,
      '/help за флагом HELP_ENABLED, префиксного !help больше нет')
check('Экономика' not in field_names and 'Уровни и карма' not in field_names,
      'спящие разделы (экономика/уровни) из /help убраны')
check('Логи и аудит' not in field_names and 'AI ' not in field_names,
      'нет дублей пересекающихся с ACL разделов (Логи и аудит / AI)')
# Выключенные разделы (экономика/уровни) физически удалены: их нет
# в /help даже в полном составе — возвращать нечего.
check('Экономика' not in field_names and 'Уровни и карма' not in field_names
      and 'Игры и развлечения' not in field_names,
      '/help не показывает удалённые разделы (экономика/уровни/игры)')
# select-меню Discord: максимум 25 опций
n_opts = 1 + len(HP._all_category_labels())
check(n_opts <= 25, f'select-меню умещается в лимит Discord ({n_opts} ≤ 25)')
e_music = HP.build_help_embed(category_id='Музыка')
_mdesc = e_music.description or ''
# Раздел присутствует в навигации, но без единой живой команды: «**0** команд»
# и ни одной команды (`/...`) в теле.
check('**0**' in _mdesc
      and not any('/play' in (f.value or '') for f in e_music.fields),
      'раздел «Музыка» в справке пуст — живых команд нет (музыка снята)')
# ACL-фильтрация ядра не сломана
e_mod = HP.build_help_embed(category_id='Модерация')
mod_text = ' '.join(f.value for f in e_mod.fields)
check('`ban`' in mod_text and '`tempban`' in mod_text,
      'мод-ядро справки прежнее (ban/tempban на месте)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
