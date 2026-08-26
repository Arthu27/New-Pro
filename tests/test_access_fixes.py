# -*- coding: utf-8 -*-
"""Фиксы «Недостаточно прав»: создатель сервера = владелец панели,
понятные 403, массовые тумблеры команд, диагностика Forbidden у бота.

Запуск: python3 tests/test_access_fixes.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = 0
FAIL = 0


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label}')


def src(rel):
    return open(os.path.join(ROOT, rel), encoding='utf-8').read()


print('== Создатель сервера = владелец панели ==')
app = src('web/app.py')
m = re.search(r'def _get_role_from_discord.*?return \'uye\'\n\n    # 1\.', app, re.S)
owner_shortcut = re.search(r"owner_id.*?return 'owner'", app, re.S)
check(owner_shortcut is not None,
      'создатель сервера получает роль owner автоматически')
check(owner_shortcut and owner_shortcut.start() < app.index('# 1. Ручное сопоставление'),
      'проверка owner_id идёт раньше карты ролей')

print('== Понятные 403 ==')
check('denied=' in app and 'quote_plus' in app,
      'страницы без прав ведут на главную с ?denied=')
check('Создатель сервера получает роль «Владелец» автоматически' in app,
      'ошибка API объясняет, как получить роль')
base = src('web/templates/base.html')
check('denied=' in base and 'toast' in base,
      'на главной показывается человеческий тост вместо голого JSON')

print('== Массовые тумблеры «Команды» ==')
cp = src('web/routes/commands_panel.py')
check('/api/commands/switch-bulk' in cp and "role_required('admin')" in cp,
      'bulk-эндпоинт есть и защищён админом')
csw = src('services/command_switches.py')
check('def set_disabled_bulk' in csw,
      'сервис умеет включать/выключать список команд разом')
cmd = src('web/templates/commands.html')
check('Вкл показанные' in cmd and 'Выкл показанные' in cmd and 'bulkOn' in cmd,
      'кнопки «Вкл/Выкл показанные» на странице (фильтр категории = вся категория разом)')

print('== Бот объясняет Forbidden ==')
mod = src('cogs/moderation.py')
check('_forbidden_reason' in mod and 'Не хватило прав у бота' in mod,
      'вместо «Недостаточно прав» — разбор причины')
check('preflight_reason' in mod and 'У бота не хватит прав' in mod,
      'бот знает ЗАРАНЕЕ, хватит ли прав (preflight до действия)')
check('владелец сервера' in mod and 'top_role' in mod and 'Настройки сервера' in mod,
      'диагностика: иерархия ролей / владелец / право бота — с что делать')

print('== «Права команд»: без выбранных ролей не молчит ==')
rp = src('web/templates/role_permissions.html')
check('needRolesWarn' in rp and 'needRoles' in rp and 'roles-pulse' in rp,
      'кнопки без ролей: баннер-подсказка + пульс колонки ролей вместо тихого тоста')

print('== «Меню панели»: категория включается целиком ==')
pm = src('web/templates/panel_menu.html')
check('toggleGroupAll' in pm and 'pm-cat-switch' in pm,
      'у каждой категории свой включатель (вся категория разом)')
check(pm.count("openGroups[g.key] = true") >= 1 and 'MENU.forEach(function(g){ openGroups[g.key] = true; })' in pm,
      'категории раскрыты после загрузки — видно содержимое')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
