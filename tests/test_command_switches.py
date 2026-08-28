# -*- coding: utf-8 -*-
"""Вкл/выкл команд владельцем из панели (заказ 2026-08-25).

Проверяем: хранилище (нормализация, сохранение), пометку «off» в каталоге,
API панели (GET/POST, права), применение к дереву бота (парковка
slash-команд), чеки в main.py, ярлык в «Настройках» и то, что удалённый
владельцем лог-канал больше не воссоздаётся.

Запуск: python3 tests/test_command_switches.py
"""
import importlib
import json
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_cmdsw_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'owner'
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


print('== 1. Хранилище переключателей ==')
from services import command_switches as CSW  # noqa: E402

check(CSW.disabled_set() == set(), 'по умолчанию ничего не выключено')
check(CSW.is_disabled('Ban') is False, 'is_disabled на чистом старте')
CSW.set_disabled('modpanel', True)
CSW.set_disabled('Тикет_Панель', True)      # регистр и подчёркивания нормализуются
check(CSW.is_disabled('ModPanel') and CSW.is_disabled('тикет-панель'),
      'нормализация: регистр и _/- эквивалентны')
saved = json.load(open('data/command_switches.json', encoding='utf-8'))
check(saved['disabled'] == ['modpanel', 'тикет-панель'],
      'файл хранит нормализованный список')
CSW.set_disabled('modpanel', False)
check(not CSW.is_disabled('modpanel') and CSW.is_disabled('тикет-панель'),
      'обратное включение работает')

print('== 2. Каталог помечает выключенные (мимо кэша) ==')
from services import command_registry as CR  # noqa: E402

cat = CR.catalog(force=True)
names = [c['name'] for c in cat['commands']]
check(all(c.get('off') is False for c in cat['commands']),
      'у всех команд есть флаг off (True/False)')
CSW.set_disabled(names[0], True)
cat2 = CR.catalog(force=True)                 # кэш не должен скрывать переключения
first = next(c for c in cat2['commands'] if c['name'] == names[0])
check(first.get('off') is True, 'выключенная команда помечена off')
check(cat2.get('disabled') == 1, 'счётчик «выключено» в каталоге')
CSW.set_disabled(names[0], False)
check(CSW.disabled_set() == {'тикет-панель'}, 'тестовая команда включена обратно')

print('== 3. API панели ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'

r = client.get('/api/commands/switches')
d = r.get_json()
check(r.status_code == 200 and d['success'] and 'тикет-панель' in d['disabled'],
      'GET switches отдаёт выключенные')

r = client.post('/api/commands/switch', json={'name': names[1], 'disabled': True})
d = r.get_json()
check(r.status_code == 200 and d['success'] and d['disabled'] is True,
      'POST switch выключает команду')
check(CSW.is_disabled(names[1]), 'выключение дошло до хранилища')
r = client.get('/api/commands/catalog')
d = r.get_json()
off_names = [c['name'] for c in d['commands'] if c.get('off')]
check(names[1] in off_names and d.get('disabled') >= 1,
      'каталог живо показывает выключенные со счётчиком')
r = client.post('/api/commands/switch', json={'name': names[1], 'disabled': False})
check(r.get_json()['success'] and not CSW.is_disabled(names[1]),
      'POST switch включает обратно')

client2 = appmod.app.test_client()
with client2.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'mod'
    s['role'] = 'mod'
r = client2.post('/api/commands/switch', json={'name': 'ban', 'disabled': True})
check(r.status_code == 403, 'модератор не может выключать команды (admin+)')
r = client.post('/api/commands/switch', json={'name': '', 'disabled': True})
check(r.status_code == 400, 'пустое имя — 400')

print('== 4. Бот: чеки и парковка slash-команд ==')
main_src = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
check(main_src.count('command_switches') >= 3,
      'main.py: prefix-чек, slash-чек и стартовое применение переключателей')
check('выключена владельцем' in main_src,
      'бот отвечает человеческой фразой, а не молчанием')


class _FakeCmd:
    def __init__(self, name):
        self.name = name
        self.qualified_name = name


class _FakeTree:
    def __init__(self, cmds):
        self._cmds = list(cmds)

    def get_commands(self):
        return list(self._cmds)

    def remove_command(self, name, type=None):
        self._cmds = [c for c in self._cmds if c.name != name]

    def add_command(self, cmd):
        self._cmds.append(cmd)


class _FakeBot:
    pass


CSW.set_disabled('ghost', True)
bot = _FakeBot()
bot.tree = _FakeTree([_FakeCmd('keep'), _FakeCmd('ghost')])
hidden, restored = CSW.apply_to_bot(bot)
check(hidden == ['ghost'] and [c.name for c in bot.tree.get_commands()] == ['keep'],
      'выключенная команда исчезает из дерева (меню Discord)')
hidden2, restored2 = CSW.apply_to_bot(bot)
check(hidden2 == [] and restored2 == [], 'повторное применение ничего не ломает')
CSW.set_disabled('ghost', False)
hidden3, restored3 = CSW.apply_to_bot(bot)
check(restored3 == ['ghost'] and len(bot.tree.get_commands()) == 2,
      'обратное включение возвращает команду в дерево (из парковки)')
CSW.set_disabled('ghost', False)
CSW.set_disabled('тикет-панель', False)
check(CSW.disabled_set() == set(), 'хранилище чистое после теста')

print('== 5. Меню, страница и логи-каналы ==')
from services import panel_menu as PM  # noqa: E402

st = next(g for g in PM.MENU if g['key'] == 'settings')
check(any(p['path'] == '/command-switches' and 'вкл' in p['label'].lower() for p in st['pages']),
      'в «Настройках» есть ярлык «Команды вкл/выкл»')
tpl = open(os.path.join(ROOT, 'web/templates/commands.html'), encoding='utf-8').read()
check('toggleSwitch' in tpl and 'cmdx-power' in tpl and '/api/commands/switch' in tpl,
      'карточки команд несут кнопку питания с подписью, клик дёргает API')
check('cmdx-switch' not in tpl, 'старые безымянные тумблеры-пилюли убраны')
check('is-off' in tpl and 'выключена' in tpl,
      'выключенная карточка приглушена и помечена')

# Удалённый владельцем лог-канал больше не воссоздаётся
from services import log_settings as LSET  # noqa: E402

GID = 999
LSET.set_log_settings(GID, autocreate={'mod': True})
LSET.autocreate_note(GID, 'mod', 555)
check(LSET.autocreate_is_dead(GID, 'mod', lambda cid: False) is True,
      'пропавший автосозданный канал помечает категорию мёртвой')
check(LSET.autocreate_is_dead(GID, 'mod', lambda cid: True) is True,
      'маркер мёртвой категории живёт и без проверки канала')
check(LSET.autocreate_is_dead(GID, 'message', lambda cid: False) is False,
      'чужая категория не задета')
LSET.autocreate_forget(GID, 'mod')
check(LSET.autocreate_is_dead(GID, 'mod', lambda cid: False) is False,
      'явная настройка в панели снимает маркер')
logs_src = open(os.path.join(ROOT, 'cogs/logs.py'), encoding='utf-8').read()
check('autocreate_is_dead' in logs_src and 'autocreate_note' in logs_src,
      'бот проверяет мёртвые категории перед автосозданием')
check('document.hidden' in open(os.path.join(ROOT, 'web/static/app.js'),
                                encoding='utf-8').read(),
      'фоновая вкладка не опрашивает сервер (тише туннель)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
