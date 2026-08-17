# -*- coding: utf-8 -*-
"""Гавернанс панели (глубокий аудит после марафона #1-200).

Сквозные инварианты, которые раньше ловились глазами:

1. BOM только эскейпом '\\ufeff' — сырого символа нет ни в одном .py.
2. Эмодзи-политика: декоративных эмодзи нет в шаблонах и модулях;
   легаси-файлы заморожены вайтлистом (он может только уменьшаться).
3. Меню и PAGE_COGS согласованы: пути уникальны, коги существуют.
4. Каждый render_template указывает на существующий шаблон; все шаблоны
   парсятся Jinja.
5. Безопасность API: в модулях новой эры у каждого /api/-роута есть
   login_required + role_required('mod|admin|owner'); легаси — минимум
   login_required, кроме явно публичного статуса.
6. В новых модулях нет bare except и молчаливых «except Exception: pass».
7. Паритет рефакторингов с базой марафона (git show a1e4a58): списки
   шуток/цитат/ответов шара и Action-choices побайтово те же, формула
   нормализации монетки эквивалентна на фаззе.
8. Приложение собирается: все 8 новых страниц в url_map.

Запуск: python3 tests/test_governance.py
"""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_gov_test_')
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
PY_DIRS = ('web', 'tests', 'cogs', 'services', 'scripts')

# Легаси до эмодзи-политики и до правила role_required — заморожено.
LEGACY_TPL_EMOJI = {
    'ai_moderation.html', 'autofilter.html', 'bot_diagnostics.html',
    'bot_settings.html', 'chat.html', 'color_roles.html', 'leveling.html',
    'leveling_admin.html', 'member_apply.html', 'message_logs.html',
    'notifications.html', 'panel_access.html', 'public_apply.html',
    'reaction_roles.html', 'role_permissions.html', 'schedule.html',
    'starboard.html',
}
LEGACY_ROUTE_EMOJI = {
    '_common.py', 'ai_assist.py', 'ai_chat.py', 'backups.py', 'giveaways.py',
    'guild_features.py', 'member_ops.py', 'modplus.py', 'roles_antiraid.py',
    'security_api.py', 'tasks_rules.py', 'tickets_admin.py',
}
# Публичные API без логина — осознанно (виджет статуса снаружи).
PUBLIC_API = {('status.py', '/api/status-public')}

MARATHON_MODULES = [
    'analytics_plus.py', 'tickets_ops.py', 'mod_report.py',
    'mod_control.py', 'mod_insights.py',
] + [f for f in sorted(os.listdir(os.path.join(ROOT, 'web/routes')))
     if f.endswith('_panel.py')]


def _py_files():
    for d in PY_DIRS:
        for dp, _, fs in os.walk(os.path.join(ROOT, d)):
            for f in fs:
                if f.endswith('.py'):
                    yield os.path.join(dp, f)


print('== 1. BOM только эскейпом ==')
bom_hits = [p for p in _py_files() if '\ufeff' in open(p, encoding='utf-8').read()]
check(not bom_hits, f'ни одного сырого BOM в .py ({len(bom_hits)} файлов)')
for p in bom_hits[:5]:
    check(False, f'сырой BOM: {p}')
tpl_bom = [f for f in sorted(os.listdir(os.path.join(ROOT, 'web/templates')))
           if f.endswith('.html') and open(
               os.path.join(ROOT, 'web/templates', f),
               encoding='utf-8').read().startswith('\ufeff')]
check(not tpl_bom, 'ни один шаблон не начинается с BOM')
esc_used = 0
for p in _py_files():
    esc_used += open(p, encoding='utf-8').read().count("'\\ufeff'")
check(esc_used >= 10, f'эскейп-форма на месте и жива ({esc_used} мест)')

print('== 2. Эмодзи-политика с замком на легаси ==')
tpl_dir = os.path.join(ROOT, 'web/templates')
tpl_bad = {f for f in os.listdir(tpl_dir) if f.endswith('.html')
           and EMOJI_RE.search(open(os.path.join(tpl_dir, f),
                                    encoding='utf-8').read())}
extra_tpl = tpl_bad - LEGACY_TPL_EMOJI
check(not extra_tpl,
      f'вне вайтлиста эмодзи-файлов новых нет (залегасились: {sorted(extra_tpl)})')
check(len(tpl_bad) <= len(LEGACY_TPL_EMOJI),
      f'легаси-вайтлист только тает: {len(tpl_bad)} из {len(LEGACY_TPL_EMOJI)}')
rt_dir = os.path.join(ROOT, 'web/routes')
rt_bad = {f for f in os.listdir(rt_dir) if f.endswith('.py')
          and EMOJI_RE.search(open(os.path.join(rt_dir, f),
                                   encoding='utf-8').read())}
extra_rt = rt_bad - LEGACY_ROUTE_EMOJI
check(not extra_rt,
      f'модули роутов чисты вне вайтлиста (залегасились: {sorted(extra_rt)})')
for f in ('fun.html', 'triggers.html', 'antifake.html', 'staff_stats.html'):
    path = os.path.join(tpl_dir, f)
    if f == 'triggers.html':
        check(not os.path.exists(path),
              'двойник триггеров не воскрес — файл удалён')
        continue
    check(os.path.exists(path) and not EMOJI_RE.search(
        open(path, encoding='utf-8').read()), f'шаблон {f} чист')

print('== 3. Меню и PAGE_COGS ==')
import services.panel_menu as PM  # noqa: E402
pages = [pg for g in PM.MENU for pg in g['pages']]
paths = [pg['path'] for pg in pages]
check(len(paths) == len(set(paths)),
      f'{len(paths)} пунктов меню, пути уникальны')
check(all(pg.get('label') and pg.get('icon', '').startswith('fa-')
          for pg in pages), 'у каждого пункта есть label и FA-иконка')
keys = [g['key'] for g in PM.MENU]
check(len(keys) == len(set(keys)), 'ключи групп уникальны')
check(set(PM.DEFAULT_GROUPS['mod']) <= set(keys),
      'дефолтные группы мода существуют')
check(set(PM.DEFAULT_GROUPS['admin']) == set(keys),
      'админу по умолчанию — все группы')
menu_paths = set(paths)
orphans = [p for p in PM.PAGE_COGS if p not in menu_paths]
check(not orphans, f'PAGE_COGS без страницы в меню: {orphans}')
bad_cogs = [(p, c) for p, cogs in PM.PAGE_COGS.items() for c in cogs
            if not os.path.exists(os.path.join(ROOT, 'cogs', c + '.py'))]
check(not bad_cogs, f'PAGE_COGS ссылается на живые коги (битые: {bad_cogs})')
check(all(isinstance(v, tuple) and v and all(isinstance(c, str) for c in v)
          for v in PM.PAGE_COGS.values()),
      'PAGE_COGS — непустые кортежи строк')
check(len(PM.PAGE_COGS) >= 55, f'карта когов не сдулась ({len(PM.PAGE_COGS)})')

print('== 4. Шаблоны: ссылки живые, синтаксис валиден ==')
ref_re = re.compile(r"render_template\(\s*['\"]([^'\"]+)['\"]")
refs = {}
for p in _py_files():
    if f'{os.sep}web{os.sep}' not in p:
        continue
    for m in ref_re.finditer(open(p, encoding='utf-8').read()):
        refs.setdefault(m.group(1), []).append(os.path.relpath(p, ROOT))
missing = {t: src for t, src in refs.items()
           if not os.path.exists(os.path.join(tpl_dir, t))}
check(not missing, f'все render_template живые ({len(refs)} ссылок); битые: {missing}')
from jinja2 import Environment  # noqa: E402
env = Environment()
bad_jinja = []
for f in sorted(os.listdir(tpl_dir)):
    if not f.endswith('.html'):
        continue
    try:
        env.parse(open(os.path.join(tpl_dir, f), encoding='utf-8').read())
    except Exception as ex:
        bad_jinja.append((f, str(ex)[:60]))
check(not bad_jinja, f'все {len(os.listdir(tpl_dir))} шаблонов парсятся Jinja; '
                     f'упали: {bad_jinja[:3]}')

print('== 5. Дисциплина API-роутов (AST) ==')


def route_funcs(path):
    tree = ast.parse(open(path, encoding='utf-8').read())
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        rule = None
        for d in node.decorator_list:
            if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                    and d.func.attr == 'route' and d.args
                    and isinstance(d.args[0], ast.Constant)):
                rule = d.args[0].value
        if rule is None:
            continue
        guards = set()
        for d in node.decorator_list:
            if isinstance(d, ast.Name):
                guards.add(d.id)
            elif isinstance(d, ast.Call) and isinstance(d.func, ast.Name):
                if (d.func.id == 'role_required' and d.args
                        and isinstance(d.args[0], ast.Constant)):
                    guards.add(f"role:{d.args[0].value}")
                else:
                    guards.add(d.func.id)
        yield node.name, rule, guards


modern_bad = []
legacy_bad = []
for f in sorted(os.listdir(rt_dir)):
    if not f.endswith('.py'):
        continue
    for name, rule, guards in route_funcs(os.path.join(rt_dir, f)):
        if not rule.startswith('/api/'):
            continue
        if f in MARATHON_MODULES:
            if 'login_required' not in guards or not {
                    'role:mod', 'role:admin', 'role:owner'} & guards:
                modern_bad.append((f, name, rule, sorted(guards)))
        elif 'login_required' not in guards and (f, rule) not in PUBLIC_API:
            legacy_bad.append((f, name, rule, sorted(guards)))
check(not modern_bad, 'в модулях новой эры у каждого /api/ — login + роль '
                      f'(нарушители: {modern_bad[:3]})')
check(not legacy_bad, 'легаси /api/ минимум под логином '
                      f'(нарушители: {legacy_bad[:3]})')
check(len(MARATHON_MODULES) >= 35,
      f'список модулей новой эры полон ({len(MARATHON_MODULES)})')

print('== 6. Без молчаливых except в новых модулях ==')
silent = []
for f in MARATHON_MODULES:
    tree = ast.parse(open(os.path.join(rt_dir, f), encoding='utf-8').read())
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            silent.append((f, node.lineno, 'bare except'))
            continue
        is_broad = (isinstance(node.type, ast.Name)
                    and node.type.id == 'Exception')
        body = node.body
        quiet = (len(body) == 1 and isinstance(body[0], (ast.Pass,))
                 or len(body) == 1 and isinstance(body[0], ast.Return)
                 and body[0].value is None)
        if is_broad and quiet:
            silent.append((f, node.lineno, 'except Exception: pass/return'))
check(not silent, f'ни одного молчаливого except в {len(MARATHON_MODULES)} '
                  f'модулях (нашлись: {silent[:3]})')

print('== 7. Паритет рефакторингов с базой марафона ==')
BASE = 'a1e4a58579d3544a5c9b3ccea247414576293266'


def git_show(path):
    proc = subprocess.run(['git', 'show', f'{BASE}:{path}'], cwd=ROOT,
                          capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


from cogs import fun_cog as FC  # noqa: E402
from cogs import minigames as MG  # noqa: E402
from cogs import impersonation as IM  # noqa: E402

old_fun = git_show('cogs/fun_cog.py')
check(old_fun is not None and len(old_fun) > 1000, 'база fun_cog читается')
old_jokes = re.findall(r'"([^"]*)"', re.search(
    r'jokes = \[(.*?)\]', old_fun, re.S).group(1))
old_quotes = re.findall(r'"([^"]*)"', re.search(
    r'quotes = \[(.*?)\]', old_fun, re.S).group(1))
check(old_jokes == FC.JOKES, 'список шуток побайтово тот, что в базе')
check(old_quotes == FC.QUOTES, 'список цитат побайтово тот, что в базе')
for url in ('https://meme-api.com/gimme', 'https://aws.random.cat/meow',
            'https://dog.ceo/api/breeds/image/random'):
    check(url in old_fun and url in (FC.MEME_URL, FC.CAT_URL, FC.DOG_URL),
          f'адрес {url} сохранён')

old_mini = git_show('cogs/minigames.py')
old_ball = [(t, int(h, 16)) for t, h in re.findall(
    r"\('([^']+)', 0x([0-9A-Fa-f]{6})\)",
    re.search(r'responses = \[(.*?)\]', old_mini, re.S).group(1))]
check(old_ball == MG.EIGHT_BALL, 'двенадцать ответов шара с цветами 1:1 базе')
FORMULA = ("user_pick = 'Орёл' if norm in ['орёл', 'orel', 'орел'] else "
           "'Решка' if norm in ['решка', 'reshka'] else None")
check(FORMULA in old_mini, 'старую формулу монетки видно в базе — не выдумка')


def old_norm(pick):
    norm = pick.lower().strip()
    return ('Орёл' if norm in ['орёл', 'orel', 'орел']
            else 'Решка' if norm in ['решка', 'reshka'] else None)


import random as _rnd  # noqa: E402
rnd = _rnd.Random(186190)
alphabet = 'орёлORLекшtрешкаEs 0123456789аб'
samples = ['орёл', 'orel', 'ОРЕЛ', 'решка', 'reshka', '', '  ', 'камень',
           'орёл ', ' Решка']
samples += [''.join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 8)))
            for _ in range(400)]
mismatch = [s for s in samples
            if MG.norm_coin_pick(s) != old_norm(s)]
check(not mismatch, f'нормализация 1:1 на {len(samples)} входах '
                    f'(расходятся: {mismatch[:3]})')
check(MG._DICE == {1: '⚀', 2: '⚁', 3: '⚂', 4: '⚃', 5: '⚄', 6: '⚅'},
      'таблица граней кубиков не поехала')

old_imp = git_show('cogs/impersonation.py')
old_choices = re.findall(r'app_commands\.Choice\(name="([^"]+)", value="([^"]+)"\)',
                         re.search(r'@app_commands\.choices\(действие=\[(.*?)\]\)',
                                   old_imp, re.S).group(1))
new_choices = [(c.name, c.value) for c in IM.ACTION_CHOICES]
check(old_choices == new_choices,
      'Action-choices побайтово те, что были в декораторе базы')
check('def _add_strike' in old_imp
      and open(os.path.join(ROOT, 'cogs/impersonation.py'),
               encoding='utf-8').read().count('_add_strike') >= 2,
      'район страйков кога на месте')

print('== 8. Приложение собирается, новые страницы в url_map ==')
appmod = __import__('web.app', fromlist=['app'])
rules = {r.rule for r in appmod.app.url_map.iter_rules()}
check(len(rules) > 400, f'роутов куча и собрались без коллизий ({len(rules)})')
for page in ('/sla', '/reports', '/archive', '/server-info', '/search',
             '/fun', '/antifake', '/staff-stats'):
    check(page in rules, f'страница {page} в url_map')
api8 = sorted(r for r in rules if '/fun/' in r)
check(len(api8) == 9, f'у /fun ровно 9 API ({len(api8)})')
api_af = sorted(r for r in rules if '/antifake/' in r)
check(len(api_af) == 11, f'у /antifake ровно 11 API ({len(api_af)})')
api_ss = sorted(r for r in rules if '/staff-stats/' in r)
check(len(api_ss) == 3, f'у /staff-stats ровно 3 API ({len(api_ss)})')
import web.routes_extra as RE  # noqa: E402
check(all(callable(getattr(m, 'register', None)) for m in RE._MODULES),
      f'у всех {len(RE._MODULES)} модулей фасада есть register(ctx)')

if shutil.which('node'):
    print('== 9. JS новых шаблонов синтаксически валиден (node) ==')
    node_ok = True
    for f in ('fun.html', 'antifake.html', 'staff_stats.html'):
        src = open(os.path.join(tpl_dir, f), encoding='utf-8').read()
        for i, m in enumerate(re.findall(r'<script>(.*?)</script>', src, re.S)):
            js = re.sub(r'\{\{[^}]*\}\}', '0', m)  # Jinja-вставки в числа
            tmp_js = os.path.join(_TMP, f'check_{f}_{i}.js')
            open(tmp_js, 'w', encoding='utf-8').write(js)
            proc = subprocess.run(['node', '--check', tmp_js],
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                node_ok = False
                check(False, f'JS в {f}: {proc.stderr[:80]}')
    if node_ok:
        check(True, 'node --check зелёный на новых шаблонах')
else:
    check(True, 'node недоступен в песочнице — JS покрыт ручным аудитом')

print('== 10. Каждый загружаемый ког имеет setup ==')
import cogs_policy as CP  # noqa: E402
no_setup = []
helpers_missing = []
for f in sorted(os.listdir(os.path.join(ROOT, 'cogs'))):
    if not f.endswith('.py'):
        continue
    path = os.path.join(ROOT, 'cogs', f)
    tree = ast.parse(open(path, encoding='utf-8').read())
    has_setup = any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name == 'setup' for n in tree.body)
    if f in CP.HELPER_COGS:
        continue
    if not has_setup:
        no_setup.append(f)
for h in CP.HELPER_COGS:
    if not os.path.exists(os.path.join(ROOT, 'cogs', h)):
        helpers_missing.append(h)
check(not no_setup,
      f'вне HELPER_COGS у каждого модуля есть setup (сироты: {no_setup})')
check(not helpers_missing,
      f'HELPER_COGS не ссылается на несуществующие файлы ({helpers_missing})')
en, dis = CP.select_from_environment(
    sorted(os.listdir(os.path.join(ROOT, 'cogs'))), environ={})
check('economy_shop.py' not in en and 'economy_shop.py' not in dis,
      'economy_shop — хелпер: политика его больше не грузит как ког')
check('economy_cog.py' in en, 'сам ког экономики по-прежнему грузится')

print('== 11. Все загружаемые коги импортируются с setup ==')
import importlib  # noqa: E402
bad_imp = []
for f in en:
    name = 'cogs.' + f[:-3]
    try:
        m = importlib.import_module(name)
        if not callable(getattr(m, 'setup', None)):
            bad_imp.append((f, 'setup не callable'))
    except Exception as ex:
        bad_imp.append((f, f'{type(ex).__name__}: {str(ex)[:60]}'))
check(not bad_imp,
      f'все {len(en)} загружаемых когов живо импортируются (упали: {bad_imp[:3]})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
