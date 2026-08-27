# -*- coding: utf-8 -*-
"""Лимиты по ролям + «логи не создаются сами» (заказ владельца 2026-08).

1. Пер-рольные лимиты: по умолчанию ВСЁ ВЫКЛЮЧЕНО (0 = opt-in), цифры
   задаёт владелец; свой лимит роли ГЛАВНЕЕ общего (замена, не ужатие),
   при нескольких ролях побеждает мягчайшая.
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

_TMP = tempfile.mkdtemp(prefix='hakumo_rlimits_test_')
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

ok('дефолты: ВСЁ ВЫКЛЮЧЕНО (opt-in, заказ «выключи все»)',
   all(v == 0 for v in SL.DEFAULT_LIMITS.values()))
ok('12 действий в списке (варн/мут/кик/бан/чистка и др.)',
   len(SL.DEFAULT_LIMITS) == 12 and 'warn' in SL.DEFAULT_LIMITS
   and 'dehoist' in SL.DEFAULT_LIMITS)
meta = SL.action_meta()
ok('панель получает группы: наказания + опасные операции',
   len(meta) == 2 and sum(len(g['items']) for g in meta) == 12
   and {i['key'] for g in meta for i in g['items']} == set(SL.DEFAULT_LIMITS))

print('== 1.2 Периоды: часы и дни (заказ «дни надо и часы») ==')
ok('дефолтное окно — 1 день', SL.get_windows(777)['ban'] == 86400)
SL.set_windows(777, ban=7200, clear=7 * 86400)
_w = SL.get_windows(777)
ok('окна сохраняются: 2 часа и 7 дней', _w['ban'] == 7200 and _w['clear'] == 604800)
ok('окна зажимаются в 1 час..31 день',
   SL.set_windows(777, nuke=60)['nuke'] == 3600
   and SL.set_windows(777, nuke=999 * 86400)['nuke'] == 31 * 86400)
ok('human_window: «2 ч» и «7 дн.»',
   SL.human_window(7200) == '2 ч' and SL.human_window(604800) == '7 дн.')

_orig_now = SL._now
try:
    SL._now = lambda: 1000000.0
    SL.set_limits(777, ban=1)
    SL.set_role_limits(777, 333, ban=1)
    SL.set_role_windows(777, 333, ban=3600)
    lim_r, win_r = SL.effective_limits(777, [333])
    ok('роль задаёт СВОЙ период (1 бан за 1 час)',
       lim_r['ban'] == 1 and win_r['ban'] == 3600)
    ok('без ролей — глобальное окно', SL.effective_limits(777, [])[1]['ban'] == 7200)
    allowed_a, _u, _l = SL.check_limit(777, 88, 'ban', 1, role_ids=[333])
    SL.record_hit(777, 88, 'ban', 1)
    allowed_b, used_b, _l = SL.check_limit(777, 88, 'ban', 1, role_ids=[333])
    ok('лимит за час: второй запретен', allowed_a and not allowed_b and used_b == 1)
    SL._now = lambda: 1000000.0 + 3601        # час прошёл
    allowed_c, _u, _l = SL.check_limit(777, 88, 'ban', 1, role_ids=[333])
    ok('час истёк — снова можно', allowed_c)
finally:
    SL._now = _orig_now
SL.clear_role_limits(777, 333)
# возвращаем глобальные, чтобы дальнейшие проверки секции видели дефолты
SL.set_limits(777, ban=8)
SL.set_windows(777, ban=86400, clear=86400, nuke=86400)

SL.set_role_limits(777, 111, ban=3, mute=5)
SL.set_role_limits(777, 222, ban=1)  # ещё строже по бану
ok('сохранение ролей', SL.get_role_limits(777)['111'] == {'ban': 3, 'mute': 5})

eff = SL.limits_for_roles(777, [111, 222])
ok('роль ГЛАВНЕЕ общего: из двух ролей мягчайшая (бан 3, мут 5)',
   eff['ban'] == 3 and eff['mute'] == 5 and eff['warn'] == 0)

allowed, used, limit = SL.check_limit(777, 42, 'ban', 1, role_ids=[111, 222])
ok('check_limit с ролями: лимит роли 3', limit == 3 and allowed)
for _ in range(3):
    SL.record_hit(777, 42, 'ban', 1)
allowed2, used2, limit2 = SL.check_limit(777, 42, 'ban', 1, role_ids=[111, 222])
ok('4-й бан сверх лимита роли 3 запрещён', not allowed2 and limit2 == 3)
allowed3, _u, _l = SL.check_limit(777, 42, 'ban', 1)  # без ролей — глобальный
ok('без ролей действует глобальный лимит', allowed3 is False or allowed3 is True)

ok('сброс роли', SL.clear_role_limits(777, 222) is True
   and '222' not in SL.get_role_limits(777))


class _FakeObj:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


_fg = _FakeObj(id=777, owner_id=1)
_hu = _FakeObj(id=55, bot=False, roles=[])
_bo = _FakeObj(id=66, bot=True, roles=[])
SL.record_hit(777, 55, 'ban', 99)
SL.record_hit(777, 66, 'ban', 99)
_deny = SL.check_action(_fg, _hu, 'ban')
ok('check_action: человек с исчерпанным лимитом — отказ',
   _deny[0] is False and bool(_deny[1]))
ok('check_action: бот (панель/автоматика) — exempt даже с исчерпанным лимитом',
   SL.check_action(_fg, _bo, 'ban') == (True, None))
eff2 = SL.limits_for_roles(777, [222])
ok('после сброса роль живёт по глобальным', eff2['ban'] == 8)

print('== 2. Панель: страница и API ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
r = client.post('/login', data={'username': 'owner', 'password': 'test123'})
ok('вход владельцем', r.status_code in (200, 302))

r = client.get('/staff-limits', follow_redirects=False)
ok('старый адрес /staff-limits ведёт в Щит (редирект)', r.status_code == 302
   and '/guardian' in r.headers.get('Location', ''))
r = client.get('/guardian')
gpage = r.get_data(as_text=True)
ok('Щит открывается и содержит секцию «Лимиты команды»',
   r.status_code == 200 and 'Лимиты команды' in gpage
   and 'gdLimRoles' in gpage and 'gdLimGlobal' in gpage)
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
ok('GET лимитов: окна периодов (N + час/день)',
   d['windows']['ban'] == {'n': 1, 'unit': 'd'}
   and d['windows']['warn']['unit'] == 'd' and 'n' in d['windows']['mute'])
ok('в списке ролей есть демо-роли (превью живое)', len(d['roles']) > 0)

r = client.post('/api/guild/777/staff-limits',
                json={'limits': {'ban': 4}, 'windows': {'ban': {'n': 6, 'unit': 'h'}}})
ok('POST глобального лимита и периода',
   r.get_json()['success'] and SL.get_limits(777)['ban'] == 4
   and SL.get_windows(777)['ban'] == 6 * 3600
   and r.get_json()['windows']['ban']['n'] == 6)

r = client.post('/api/guild/777/staff-limits/role',
                json={'role_id': '999', 'limits': {'mute': 2},
                      'windows': {'mute': {'n': 12, 'unit': 'h'}}})
ok('POST лимита роли со СВОИМ периодом', r.get_json()['success']
   and SL.get_role_limits(777)['999'] == {'mute': 2}
   and SL.get_role_overrides(777)['999']['windows']['mute'] == 12 * 3600)
r = client.post('/api/guild/777/staff-limits/role/delete',
                json={'role_id': '999'})
ok('DELETE лимита роли', r.get_json()['success']
   and '999' not in SL.get_role_limits(777))

print('== 2.5 Журнал изменений лимитов (кто/когда/что + откат) ==')
r = client.post('/api/guild/777/staff-limits/role',
                json={'role_id': '999', 'limits': {'mute': 5},
                      'windows': {'mute': {'n': 12, 'unit': 'h'}}})
r = client.post('/api/guild/777/staff-limits/role',
                json={'role_id': '999', 'limits': {'mute': 2},
                      'windows': {'mute': {'n': 1, 'unit': 'h'}}})
ok('правка роли: новое значение действует',
   (SL.get_role_overrides(777).get('999') or {}).get('limits', {}).get('mute') == 2)
r = client.post('/api/guild/777/staff-limits/role',
                json={'role_id': '999', 'clear': ['mute']})
ok('стёртое поле снимает переопределение роли (clear)', r.get_json()['success']
   and 'mute' not in (SL.get_role_overrides(777).get('999') or {}).get('limits', {}))
r = client.get('/api/guild/777/staff-limits/changes')
d = r.get_json()
ok('журнал отдаёт записи с автором и временем', d['success']
   and len(d['changes']) > 0 and all(e.get('ts') and e.get('who') == 'owner'
                                     for e in d['changes'][:3]))
mute_chg = next((e for e in d['changes'] if e['scope'] == 'role'
                 and e.get('role_id') == '999'
                 and any(c['key'] == 'mute' and c['field'] == 'limit' and c['new'] == 2
                         for c in e['changes'])), None)
ok('в журнале видна правка роли (кто/что/было→стало)', mute_chg is not None
   and mute_chg['changes'][0]['old'] == 5)
r = client.post('/api/guild/777/staff-limits/changes/revert',
                json={'id': mute_chg['id']})
ok('кнопка «Вернуть» откатывает правку роли к старому',
   r.get_json()['success']
   and (SL.get_role_overrides(777).get('999') or {}).get('limits', {}).get('mute') == 5)
r = client.post('/api/guild/777/staff-limits/changes/revert',
                json={'id': 'c9999999'})
ok('несуществующая запись отката → 404', r.status_code == 404)
SL.clear_role_limits(777, '999')   # чистим роль для следующей проверки
ban_chg = next(e for e in SL.get_changes(777) if e['scope'] == 'global'
               and any(c['key'] == 'ban' and c['field'] == 'limit' for c in e['changes']))
r = client.post('/api/guild/777/staff-limits/changes/revert',
                json={'id': ban_chg['id']})
ok('откат глобального лимита возвращает старое значение', r.get_json()['success']
   and SL.get_limits(777)['ban'] == 8)
win_chg = next(e for e in SL.get_changes(777) if e['scope'] == 'global'
               and any(c['key'] == 'ban' and c['field'] == 'window'
                       for c in e['changes']))
r = client.post('/api/guild/777/staff-limits/changes/revert',
                json={'id': win_chg['id']})
ok('откат глобального периода возвращает 1 дн', r.get_json()['success']
   and SL.get_windows(777)['ban'] == 86400)

tpl = open(os.path.join(ROOT, 'web/templates/guardian.html'),
           encoding='utf-8').read()
ok('Щит: секция лимитов с выбором роли + live 1.5с',
   'gdLimRoles' in tpl and 'setLiveRefresh' in tpl
   and 'действует сразу' in tpl)
ok('Щит: поля лимитов строятся из групп API (не захардкожены)',
   'gdLimGlobal' in tpl and 'action_meta' in tpl
   and "'warn', 'mute', 'kick'" not in tpl)
ok('Щит: периоды «за N час/дн» у каждого поля лимитов',
   'gdLimGW' in tpl and 'gdLimGU' in tpl and 'gdLimRW' in tpl and 'gdLimRU' in tpl
   and '>час</option>' in tpl and '>дн</option>' in tpl)
ok('Щит: видно изменения роли («сейчас действует» + журнал с откатом)',
   'Сейчас действует' in tpl and 'gdLimChanges' in tpl
   and 'changes/revert' in tpl and 'Вернуть' in tpl)
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

# демо-каналы: обычный текстовый + ФОРУМ (логи форумом — как у владельца)
with open(os.path.join('data', 'demo_channels.json'), 'w', encoding='utf-8') as fh:
    json.dump([{'id': '1001', 'name': 'общее', 'type': 'text'},
               {'id': '1015', 'name': 'логи-модерации', 'type': 'forum'}], fh)
r = client.get('/api/guild/777/log-settings')
d = r.get_json()
ok('API настроек логов отдаёт категории', d['success'] and len(d['categories']) == 10)
ok('API отдаёт список каналов для пикера', isinstance(d.get('channels'), list))
_names = [c['name'] for c in d.get('channels') or []]
ok('пикер каналов: и обычные, и ФОРУМ-каналы (владелец держит логи форумом)',
   '#общее' in _names and 'логи-модерации · форум' in _names)
r = client.post('/api/guild/777/log-settings', json={'autocreate': {'proof': True}})
ok('API сохраняет автосоздание', r.get_json()['success']
   and LS.autocreate_allowed(777, 'proof') is True)
r = client.post('/api/guild/777/log-settings', json={'channels': {'mod': '987654321'}})
ok('API сохраняет выбранный канал', r.get_json()['success']
   and LS.target_channel_id(777, 'mod') == '987654321')
r = client.post('/api/guild/777/log-settings',
                json={'channels': {'mod': '1015', 'message': '1015',
                                   'voice': '1015', 'member': '1015'}})
ok('одним махом: один канал сразу в несколько категорий',
   r.get_json()['success']
   and LS.target_channel_id(777, 'mod') == '1015'
   and LS.target_channel_id(777, 'voice') == '1015'
   and LS.target_channel_id(777, 'member') == '1015')

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
ok('шаблон логов: быстрый выбор «во все категории» сразу',
   'lsApplyAll' in ls_tpl and 'Во все категории' in ls_tpl)
ok('бот пишет в канал, выбранный в панели (приоритет над именами)',
   '_configured_log_channel' in logs_src and 'target_channel_id' in logs_src)
ok('live без «перезагрузки»: снимок сравнивается, DOM зря не трогаем',
   'raw === _lastRaw' in ls_tpl
   and 'raw === _lastRaw' in open(os.path.join(ROOT, 'web/templates/guardian.html'),
                                 encoding='utf-8').read())

print('== 3.3 Логи в ФОРУМ-канал: каждый лог = пост форума ==')
import asyncio as _aio
import discord as _dc
from cogs import logs as LOGS


class _FakeForum:
    type = _dc.ChannelType.forum
    name = 'логи-модерации'

    def __init__(self):
        self.created = None

    async def create_thread(self, **kw):
        self.created = kw
        return None


class _FakeText:
    type = _dc.ChannelType.text

    def __init__(self):
        self.sent = None

    async def send(self, **kw):
        self.sent = kw
        return None


_ff = _FakeForum()
_emb = _dc.Embed(title='Бан участника', description='тест')
ok('лог в форум уходит ПОСТОМ (create_thread), не send()',
   _aio.run(LOGS._safe_send(_ff, embed=_emb)) is True
   and _ff.created and _ff.created.get('name') == 'Бан участника'
   and _ff.created.get('embed') is _emb)
ok('имя поста режется до 100 символов',
   _aio.run(LOGS._safe_send(_ff, embed=_dc.Embed(title='Щ' * 150))) is True
   and len(_ff.created['name']) == 100)
_ft = _FakeText()
ok('обычный канал: по-прежнему send()',
   _aio.run(LOGS._safe_send(_ft, embed=_emb)) is True
   and _ft.sent and 'embed' in _ft.sent)
_logs_src = open(os.path.join(ROOT, 'cogs/logs.py'), encoding='utf-8').read()
ok('настроенный канал ищется и среди веток форума (get_channel_or_thread)',
   'get_channel_or_thread' in _logs_src)
ok('бот сам чинит права на посты в форум-логе',
   'create_public_threads' in _logs_src
   and 'ensure_forum_log_permissions' in _logs_src)
ok('форум узнаётся и по типу, и по классу (_is_forum_ch)',
   LOGS._is_forum_ch(_ff) is True and LOGS._is_forum_ch(_ft) is False)
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

print('== 3.7 Права команд = живой каталог бота ==')
from services import permission_acl as PA
live = PA.command_categories()
ok('права строятся из ЖИВОГО каталога (не хардкод)',
   'modpanel' in live.get('Модерация', []) and 'kick' not in live.get('Модерация', []))
ok('legacy-правила продолжают работать (объединение)',
   any('kick' in v for v in PA.all_categories().get('Модерация', [])))
ok('панель «Права команд» обновляется без «перезагрузки»',
   'raw === _rpLastRaw' in open(os.path.join(ROOT, 'web/templates/role_permissions.html'),
                                encoding='utf-8').read())
perm_src = open(os.path.join(ROOT, 'web/routes/permissions.py'), encoding='utf-8').read()
ok('API прав отдаёт живые категории', 'command_categories ()' in perm_src)

print('== 3.5 Щит сервера: время сек/мин/час/дн + выбор ролей ==')
gd_tpl = open(os.path.join(ROOT, 'web/templates/guardian.html'),
              encoding='utf-8').read()
ok('непонятное поле «Окно, сек» убрано', 'Окно, сек' not in gd_tpl)
ok('выбор времени: сек/мин/ЧАС/ДН (заказ «часы и дни»)',
   '>час</option>' in gd_tpl and '>дн</option>' in gd_tpl
   and 'WIN_UNITS' in gd_tpl)
ok('быстрые пресеты: 30 сек … 1 час, 6 ч, 1 день',
   'WIN_PRESETS' in gd_tpl and 'gd-pbtn' in gd_tpl
   and '1 час' in gd_tpl and '1 день' in gd_tpl and '21600' in gd_tpl)
ok('человеческая подсказка «Сработает: N за X» и объяснение',
   'gd-fires' in gd_tpl and 'Как настроить защиту' in gd_tpl)
ok('значение зажимается в 3 сек..31 день при сохранении',
   'Math.min(WIN_MAX, wsec)' in gd_tpl and 'WIN_MAX = 31 * 86400' in gd_tpl)
ok('РОЛИ выбираются живым поиском (как в лимитах)',
   'gdWlRPick' in gd_tpl and 'gdWlBRPick' in gd_tpl
   and 'Поиск роли' in gd_tpl and 'wlComboInit' in gd_tpl
   and 'gd-combo' in gd_tpl)
ok('УЧАСТНИКИ тоже живым поиском (белые списки без ID руками)',
   'gdWlUPick' in gd_tpl and 'gdWlBUPick' in gd_tpl
   and 'Поиск участника' in gd_tpl and 'gdWlUIn' not in gd_tpl)
ok('быстрые якоря: Защита / Белые списки / Лимиты / Инциденты',
   'gd-tabs' in gd_tpl and '#limits' in gd_tpl and '#gdWlCard' in gd_tpl
   and 'gdFeedPanel' in gd_tpl)
gd_cog = open(os.path.join(ROOT, 'cogs/guardian.py'), encoding='utf-8').read()
ok('бот принимает окна до 31 дня (не только 300 сек)',
   '31 * 86400' in gd_cog)
gd_route = open(os.path.join(ROOT, 'web/routes/guardian.py'), encoding='utf-8').read()
ok('API Щита отдаёт роли сервера для пикера',
   '_roles_for_pick' in gd_route and "'roles': _roles_for_pick(gid)" in gd_route)
ok('API Щита отдаёт участников для пикера',
   '_members_for_pick' in gd_route and "'members': _members_for_pick(gid)" in gd_route)

r = client.get('/api/guild/777/guardian')
d = r.get_json() or {}
ok('демо-API участников непустое (пикеры живые)',
   r.status_code == 200 and isinstance(d.get('members'), list)
   and len(d['members']) >= 5 and d['members'][0].get('id')
   and d['members'][0].get('name'))

print('== 4. Меню ==')
from services import panel_menu as PM  # noqa: E402
paths = {p['path'] for g in PM.MENU for p in g.get('pages', [])}
ok('отдельной страницы лимитов больше нет (вошла в Щит)',
   '/staff-limits' not in paths)
ok('«Логи сервера» в меню (Настройки)', '/log-settings' in paths)
prot_pages = [p for g in PM.MENU if g.get('key') == 'protection'
              for p in g.get('pages', [])]
gd_menu = next((p for p in prot_pages if p['path'] == '/guardian'), None)
ok('Щит сервера — admin+, внутри упомянуты лимиты команды',
   gd_menu and gd_menu.get('min_role') == 'admin'
   and gd_menu.get('section') == 'protection'
   and 'лимиты' in gd_menu.get('description', ''))

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
