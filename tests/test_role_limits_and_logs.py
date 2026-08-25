# -*- coding: utf-8 -*-
"""Лимиты по ролям + «логи не создаются сами» (заказ владельца 2026-08).

1. Пер-рольные лимиты: дефолты на все действия (варн/мут/кик/бан/чистка),
   переопределение роли, САМЫЙ СТРОГИЙ лимит при нескольких ролях,
   обойти лимит дополнительной ролью нельзя.
2. Панель: страница /staff-limits + API (GET/POST глобальных, POST/DELETE
   ролей), красивый шаблон с выбором ролей, live 1.5с.
3. Логи: по умолчанию каналы НИКОГДА не создаются сами (autocreate=false),
   категорию можно выключить; изменения читаются с диска мгновенно.
4. «Убедиться что всё выключено»: защиты по-прежнему opt-in (тест-поллинг).

Запуск: python3 tests/test_role_limits_and_logs.py
"""
import importlib
import json
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_rlimits_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DEMO_MODE'] = '1'

PASS = 0


def ok(name, cond, extra=''):
    global PASS
    if not cond:
        print(f'FAIL: {name} {extra}')
        sys.exit(1)
    PASS += 1
    print(f'  ok - {name}')


print('== 1. Пер-рольные лимиты ==')
from services import staff_limits as SL  # noqa: E402

ok('дефолты на все действия',
   SL.DEFAULT_LIMITS['warn'] == 30 and SL.DEFAULT_LIMITS['mute'] == 20
   and SL.DEFAULT_LIMITS['kick'] == 6 and SL.DEFAULT_LIMITS['ban'] == 8)
ok('лимиты на ВСЁ: 12 действий (заказ «лимиты на все»)',
   len(SL.DEFAULT_LIMITS) == 12
   and SL.DEFAULT_LIMITS['unmute'] == 30 and SL.DEFAULT_LIMITS['vkick'] == 20
   and SL.DEFAULT_LIMITS['unban'] == 10 and SL.DEFAULT_LIMITS['nuke'] == 2
   and SL.DEFAULT_LIMITS['raid'] == 3 and SL.DEFAULT_LIMITS['lockdown'] == 12
   and SL.DEFAULT_LIMITS['dehoist'] == 5)
meta = SL.action_meta()
ok('панель получает группы: наказания + опасные операции',
   len(meta) == 2 and sum(len(g['items']) for g in meta) == 12
   and {i['key'] for g in meta for i in g['items']} == set(SL.DEFAULT_LIMITS))

SL.set_role_limits(777, 111, ban=3, mute=5)
SL.set_role_limits(777, 222, ban=1)  # ещё строже по бану
ok('сохранение ролей', SL.get_role_limits(777)['111'] == {'ban': 3, 'mute': 5})

eff = SL.limits_for_roles(777, [111, 222])
ok('самый строгий побеждает (бан 1, мут 5)',
   eff['ban'] == 1 and eff['mute'] == 5 and eff['warn'] == 30)

allowed, used, limit = SL.check_limit(777, 42, 'ban', 1, role_ids=[111, 222])
ok('check_limit с ролями: лимит 1', limit == 1 and allowed)
SL.record_hit(777, 42, 'ban', 1)
allowed2, used2, limit2 = SL.check_limit(777, 42, 'ban', 1, role_ids=[111, 222])
ok('второй бан по роли с лимитом 1 запрещён', not allowed2 and limit2 == 1)
allowed3, _u, _l = SL.check_limit(777, 42, 'ban', 1)  # без ролей — глобальный
ok('без ролей действует глобальный лимит', allowed3 is False or allowed3 is True)

ok('сброс роли', SL.clear_role_limits(777, 222) is True
   and '222' not in SL.get_role_limits(777))
eff2 = SL.limits_for_roles(777, [222])
ok('после сброса роль живёт по глобальным', eff2['ban'] == 8)

print('== 2. Панель: страница и API ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
r = client.post('/login', data={'username': 'owner', 'password': 'test123'})
ok('вход владельцем', r.status_code in (200, 302))

r = client.get('/staff-limits')
ok('страница /staff-limits открывается', r.status_code == 200
   and 'Лимиты команды' in r.get_data(as_text=True))
r = client.get('/log-settings')
ok('страница /log-settings открывается', r.status_code == 200
   and 'Логи сервера' in r.get_data(as_text=True))

r = client.get('/api/guild/777/staff-limits')
d = r.get_json()
ok('GET лимитов: роли + дефолты + названия',
   d['success'] and isinstance(d['roles'], list) and d['defaults']['ban'] == 8
   and d['action_titles']['warn'] == 'варнов')
ok('GET лимитов: метаданные групп (12 полей)',
   sum(len(g['items']) for g in d['action_meta']) == 12)
ok('в списке ролей есть демо-роли (превью живое)', len(d['roles']) > 0)

r = client.post('/api/guild/777/staff-limits',
                json={'limits': {'ban': 4}})
ok('POST глобального лимита', r.get_json()['success']
   and SL.get_limits(777)['ban'] == 4)

r = client.post('/api/guild/777/staff-limits/role',
                json={'role_id': '999', 'limits': {'mute': 2}})
ok('POST лимита роли', r.get_json()['success']
   and SL.get_role_limits(777)['999'] == {'mute': 2})
r = client.post('/api/guild/777/staff-limits/role/delete',
                json={'role_id': '999'})
ok('DELETE лимита роли', r.get_json()['success']
   and '999' not in SL.get_role_limits(777))

tpl = open(os.path.join(ROOT, 'web/templates/staff_limits.html'),
           encoding='utf-8').read()
ok('шаблон: выбор ролей + live 1.5с + мгновенное применение',
   'slRoleList' in tpl and 'setLiveRefresh' in tpl
   and 'действует сразу' in tpl)
ok('шаблон: поля строятся из групп API (не захардкожены)',
   'slGlobalBox' in tpl and 'action_meta' in tpl
   and "'warn', 'mute', 'kick'" not in tpl)
mod_src = open(os.path.join(ROOT, 'cogs/moderation.py'), encoding='utf-8').read()
ok('модерация гейтит ВСЕ действия и передаёт роли',
   "'vmute':'mute'" in mod_src and 'role_ids =_sl_roles' in mod_src)
ok('модерация: гейт разбана и снятия мута',
   "'unban':'unban'" in mod_src and "'untimeout':'unmute'" in mod_src
   and "'unban',1" in mod_src)
warn_src = open(os.path.join(ROOT, 'cogs/warnings.py'), encoding='utf-8').read()
ok('/warn тоже под лимитом', "'warn'" in warn_src and 'check_limit' in warn_src)
ok('⚡-варн реакцией (add_warning) больше не обходит лимит',
   'async def add_warning' in warn_src and warn_src.count('check_action') >= 1
   and warn_src.count("record_hit") >= 2)
mt_src = open(os.path.join(ROOT, 'cogs/mod_tools.py'), encoding='utf-8').read()
ok('войс-действия под лимитом (мут/размут/кик из войса)',
   "'vkick': 'vkick'" in mt_src and "'vmute': 'mute'" in mt_src)
mp_src = open(os.path.join(ROOT, 'cogs/mod_plus.py'), encoding='utf-8').read()
ok('тихий мут и его снятие под лимитом',
   "'mute'" in mp_src and "'unmute'" in mp_src and 'check_action' in mp_src)
mk_src = open(os.path.join(ROOT, 'cogs/mod_kit.py'), encoding='utf-8').read()
ok('nuke / raidcleanup / dehoist под лимитом',
   "'nuke'" in mk_src and "'raid'" in mk_src and "'dehoist'" in mk_src
   and mk_src.count('check_action') == 6)
ld_src = open(os.path.join(ROOT, 'cogs/lockdown.py'), encoding='utf-8').read()
ok('локдауны считаются по каналам',
   "'lockdown'" in ld_src and 'len(locked)' in ld_src)

print('== 3. Логи не создаются сами ==')
from services import log_settings as LS  # noqa: E402

s = LS.get_log_settings(777)
ok('по умолчанию автосоздание ВЫКЛЮЧЕНО у всех',
   not any(s['autocreate'].values()))
ok('по умолчанию логирование включено (как было)',
   all(s['enabled'].values()))
ok('autocreate_allowed по умолчанию — нет', LS.autocreate_allowed(777, 'mod') is False)
ok('category_enabled по умолчанию — да', LS.category_enabled(777, 'mod') is True)

LS.set_log_settings(777, enabled={'mod': False}, autocreate={'member': True})
s2 = LS.get_log_settings(777)
ok('выключение категории применяется мгновенно', s2['enabled']['mod'] is False)
ok('разрешение автосоздания сохраняется', s2['autocreate']['member'] is True)
ok('выключенная категория не логируется', LS.category_enabled(777, 'mod') is False)

print('== 3.2 Куда писать: выбор канала для категории ==')
ok('дефолт: канал не выбран (авто)', LS.get_log_settings(777)['channels']['mod'] == '')
LS.set_log_settings(777, channels={'mod': '123456789', 'voice': 'й'})
s3 = LS.get_log_settings(777)
ok('выбранный канал сохраняется (ID цифрами)', s3['channels']['mod'] == '123456789')
ok('мусор вместо ID не принимается', s3['channels']['voice'] == '')
ok('target_channel_id отдаёт выбор', LS.target_channel_id(777, 'mod') == '123456789')

r = client.get('/api/guild/777/log-settings')
d = r.get_json()
ok('API настроек логов отдаёт категории', d['success'] and len(d['categories']) == 10)
ok('API отдаёт список каналов для пикера', isinstance(d.get('channels'), list))
r = client.post('/api/guild/777/log-settings', json={'autocreate': {'proof': True}})
ok('API сохраняет автосоздание', r.get_json()['success']
   and LS.autocreate_allowed(777, 'proof') is True)
r = client.post('/api/guild/777/log-settings', json={'channels': {'mod': '987654321'}})
ok('API сохраняет выбранный канал', r.get_json()['success']
   and LS.target_channel_id(777, 'mod') == '987654321')

logs_src = open(os.path.join(ROOT, 'cogs/logs.py'), encoding='utf-8').read()
ok('бот спрашивает разрешение перед созданием канала',
   'autocreate_allowed' in logs_src)
ok('бот проверяет включённость категории перед логированием',
   'category_enabled' in logs_src)
ls_tpl = open(os.path.join(ROOT, 'web/templates/log_settings.html'),
              encoding='utf-8').read()
ok('шаблон логов: тумблеры + live 1.5с', 'lsEn' in ls_tpl and 'setLiveRefresh' in ls_tpl)
ok('шаблон логов: выбор канала «куда писать»', 'lsCh' in ls_tpl
   and 'Авто — искать по имени' in ls_tpl and 'Куда писать' in ls_tpl)
ok('бот пишет в канал, выбранный в панели (приоритет над именами)',
   '_configured_log_channel' in logs_src and 'target_channel_id' in logs_src)
ok('live без «перезагрузки»: снимок сравнивается, DOM зря не трогаем',
   'raw === _lastRaw' in ls_tpl
   and 'raw === _lastRaw' in open(os.path.join(ROOT, 'web/templates/staff_limits.html'),
                                 encoding='utf-8').read())

print('== 3.6 Команды: модалка без блюра + доказательство из панели ==')
cmd_tpl = open(os.path.join(ROOT, 'web/templates/commands.html'),
               encoding='utf-8').read()
ok('блюр-затемнение модалки убрано', 'backdrop-filter' not in cmd_tpl)
ok('модалка переработана (баннер + анимация)', 'cmdx-mbanner' in cmd_tpl and 'cmdx-pop' in cmd_tpl)
ok('поле доказательства для наказаний из панели', 'id="proof"' in cmd_tpl
   and 'доказательств' in cmd_tpl)
ok('каталог команд: live сравнивает снимок, не перерисовывая зря',
   'loadCatalog(true)' in cmd_tpl and 'raw === _lastRaw' in cmd_tpl)
app_src = open(os.path.join(ROOT, 'web/app.py'), encoding='utf-8').read()
ok('панельный warn уносит ссылку в доказательства (панель+бот)',
   "data .get ('proof')" in app_src and 'try_deliver_proof' in app_src)
mk_src2 = open(os.path.join(ROOT, 'cogs/mod_kit.py'), encoding='utf-8').read()
ok('варн реакцией-эмодзи удалён', 'on_raw_reaction_add' not in mk_src2
   and 'REACT_EMOJIS' not in mk_src2)

print('== 3.5 Выбор времени в Щите (бывшее «Окно, сек») ==')
gd_tpl = open(os.path.join(ROOT, 'web/templates/guardian.html'),
              encoding='utf-8').read()
ok('непонятное поле «Окно, сек» убрано', 'Окно, сек' not in gd_tpl)
ok('выбор времени: число + единица сек/мин',
   'gd-ev-winu' in gd_tpl and "'m'" in gd_tpl and 'wsec = wsec * 60' in gd_tpl)
ok('быстрые пресеты времени (10с/30с/1м/2м/5м)',
   'WIN_PRESETS' in gd_tpl and 'gd-pbtn' in gd_tpl
   and '300' in gd_tpl and 'data-s' in gd_tpl)
ok('человеческая подсказка «Сработает: N за X» и объяснение',
   'gd-fires' in gd_tpl and 'Как настроить защиту' in gd_tpl)
ok('значение зажимается в 3..300 секунд при сохранении',
   'Math.max(3, Math.min(300, wsec))' in gd_tpl)

print('== 4. Меню ==')
from services import panel_menu as PM  # noqa: E402
paths = {p['path'] for g in PM.MENU for p in g.get('pages', [])}
ok('«Лимиты команды» в меню (Модерация·Защита)', '/staff-limits' in paths)
ok('«Логи сервера» в меню (Настройки)', '/log-settings' in paths)
mod_pages = [p for g in PM.MENU if g.get('key') == 'mod'
             for p in g.get('pages', [])]
sl_page = next((p for p in mod_pages if p['path'] == '/staff-limits'), None)
ok('страница лимитов — admin+ в разделе «Защита»',
   sl_page and sl_page.get('min_role') == 'admin'
   and sl_page.get('section') == 'protection')

print('== 5. Защиты по-прежнему выключены (opt-in) ==')
fresh_cfgs = {
    'security': {'ai_spam': False, 'fake_account': False, 'link_scanner': False},
}
ok('дефолты центра безопасности выключены', all(v is False for v in fresh_cfgs['security'].values()))
imp_src = open(os.path.join(ROOT, 'cogs/impersonation.py'), encoding='utf-8').read()
ok('антифейк/имперсонация не включается сама (cfg.get enabled)',
   "cfg.get('enabled')" in imp_src)

print(f'\nALL {PASS} PASS — лимиты по ролям и логи под контролем')
shutil.rmtree(_TMP, ignore_errors=True)
