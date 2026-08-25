# -*- coding: utf-8 -*-
"""Тесты json_store: кеш по (mtime/size), атомарная запись, делегаты в когах.

Запуск: python3 tests/test_json_store.py
"""
import io
import json
import os
import sys
import tempfile
import threading

_TMP = tempfile.mkdtemp(prefix='aether_jsonstore_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


import json_store  # noqa: E402
from json_store import load_json, save_json, invalidate, clear_cache, cache_stats  # noqa: E402

T = os.path.join(_TMP, 't.json')

# ═══ 1. load_json — базовое поведение ══════════════════════════════════
print('== load_json: база ==')
clear_cache()

d = load_json('nope.json', {})
check(d == {}, 'несуществующий файл → дефолт {}')
l = load_json('nope.json', [1, 2], log=None)
check(l == [1, 2], 'дефолт-список возвращается как есть')
n = load_json('nope.json')
check(n is None, 'без дефолта → None')

# битый JSON
with open(T, 'w', encoding='utf-8') as f:
    f.write('{битый json,,,')
clear_cache()
check(load_json(T, {'safe': True}) == {'safe': True}, 'битый JSON → дефолт, без исключения')

# тип не совпал с дефолтом
with open(T, 'w', encoding='utf-8') as f:
    json.dump([1, 2, 3], f)
clear_cache()
check(load_json(T, {}) == {}, 'список в файле + дефолт-dict → дефолт (type-check)')

# falsy-контент → дефолт (семантика старого `json.load(f) or default`)
with open(T, 'w', encoding='utf-8') as f:
    f.write('{}')
clear_cache()
check(load_json(T, {'x': 1}) == {'x': 1}, 'пустой {} в файле → дефолт (or-default семантика)')

# скаляр в файле
with open(T, 'w', encoding='utf-8') as f:
    f.write('5')
clear_cache()
check(load_json(T, {}) == {}, 'скаляр в файле → дефолт')

# ═══ 2. save_json — запись, атомарность ════════════════════════════════
print('== save_json: запись и атомарность ==')
nested = os.path.join(_TMP, 'sub', 'dir', 'data.json')
ok = save_json(nested, {'ключ': 'значение', 'n': 7})
check(ok is True, 'save_json → True')
check(os.path.exists(nested), 'директории созданы, файл на месте')
check(not os.path.exists(nested + '.tmp'), 'никаких .tmp-хвостов после записи')
raw = io.open(nested, encoding='utf-8').read()
check('ключ' in raw, 'ensure_ascii=False: кириллица читается в файле')
check('\n  "n"' in raw, 'indent=2 по умолчанию (pretty)')

compact = os.path.join(_TMP, 'compact.json')
save_json(compact, {'a': 1}, indent=None)
check('\n' not in io.open(compact, encoding='utf-8').read().strip(), 'indent=None → компактная строка')

# запись в невозможный путь: родитель — обычный файл
blocker = os.path.join(_TMP, 'blocker')
io.open(blocker, 'w').close()
bad = save_json(os.path.join(blocker, 'x.json'), {'a': 1})
check(bad is False, 'запись в тупиковый путь → False, без исключения')

# ═══ 3. Кеш: попадания, инвалидация, изоляция ══════════════════════════
print('== кеш: диск не трогаем повторно ==')
c = os.path.join(_TMP, 'cached.json')
save_json(c, {'v': 1})

calls = {'n': 0}


def counting_open(*a, **k):
    calls['n'] += 1
    return _real_open(*a, **k)


_real_open = open
json_store.open = counting_open  # модульный global затеняет builtin внутри json_store
try:
    for _ in range(5):
        load_json(c)
finally:
    del json_store.open
check(calls['n'] == 0, 'пять чтений подряд — ни одного open(): кеш по (mtime,size)')

# внешняя перезапись другим размером → кеш подхватывает
with open(c, 'w', encoding='utf-8') as f:
    json.dump({'v': 2, 'extra': 'длинный хвост меняет размер'}, f)
check(load_json(c).get('v') == 2, 'перезапись «со стороны» (другой размер) → свежие данные')

# тот же размер + invalidate → тоже свежие данные
same_size_a = os.path.join(_TMP, 'same.json')
save_json(same_size_a, {'k': 1})
with open(same_size_a, 'w', encoding='utf-8') as f:
    json.dump({'k': 9}, f)  # тот же размер, может совпасть и mtime
load_json(same_size_a)  # может вернуть старое из кеша — это окей
invalidate(same_size_a)
check(load_json(same_size_a).get('k') == 9, 'invalidate() принудительно перечитывает')

# изоляция: мутация результата не портит кеш
m1 = load_json(c)
m1['v'] = 999
check(load_json(c).get('v') == 2, 'мутация возвращённого dict не портит кеш (deepcopy)')

st = cache_stats()
check(st['entries'] >= 3 and c in st['paths'], 'cache_stats видит записи')
clear_cache()
check(cache_stats()['entries'] == 0, 'clear_cache очищает')

# save сам обновляет кеш: чтение после save — попадание
s2 = os.path.join(_TMP, 'saved.json')
save_json(s2, {'a': 'b'})
check(cache_stats()['entries'] >= 1, 'save_json сразу кладёт запись в кеш')

# ═══ 4. Потокобезопасность ═════════════════════════════════════════════
print('== потоки ==')
tp = os.path.join(_TMP, 'threads.json')
save_json(tp, {'x': 1})
errs = []


def worker():
    try:
        for _ in range(25):
            if load_json(tp).get('x') != 1:
                errs.append('bad value')
    except Exception as e:  # noqa: BLE001
        errs.append(str(e))


ths = [threading.Thread(target=worker) for _ in range(8)]
[t.start() for t in ths]
[t.join() for t in ths]
check(not errs, f'8 потоков × 25 чтений — без ошибок ({errs[:1] if errs else "ок"})')

# ═══ 5. Интеграция: коги делегируют в json_store ═══════════════════════
print('== коги на общем сторе ==')
import cogs.mod_kit as mk  # noqa: E402

mk._save_json('data/modkit_jsprobe.json', {'4242': ['111']})
check(mk._load_json('data/modkit_jsprobe.json', {}) == {'4242': ['111']},
      'mod_kit: сохранение через общий json_store')
data = json.load(open('data/modkit_jsprobe.json', encoding='utf-8'))
check(data['4242'] == ['111'], 'mod_kit: файл записан как есть')

import cogs.mod_plus as mp  # noqa: E402

p = mp._ghost_path(777)
check(mp._load_json(p, {}) == {}, 'mod_plus: пустой ghost → дефолт')
check(mp._save_json(p, {'5': {'until': None}}) is True, 'mod_plus: _save_json → True')
check(mp._load_json(p, {}).get('5', {}).get('until') is None, 'mod_plus: roundtrip данные совпали')

import cogs.health as hc  # noqa: E402

h0 = hc._load_health(31337)
check(set(('channel_messages', 'hourly', 'daily', 'spam_count')).issubset(h0),
      'health: дефолт со всеми ключами')
h0['spam_count'] = 3
hc._save_health(31337, h0)
check(hc._load_health(31337)['spam_count'] == 3, 'health: save → load (на каждое сообщение — из кеша)')
hc._load_health(31337)
check(any('health_31337' in x for x in cache_stats()['paths']), 'health-файл живёт в кеше json_store')

import cogs.autorole_level as arl  # noqa: E402

_inst = arl.AutoRoleLevel.__new__(arl.AutoRoleLevel)  # без __init__ — методам нужен только файл
_inst._save_xp(555, {'10': {'xp': 42}})
check(_inst._load_xp(555)['10']['xp'] == 42, 'autorole_level: XP roundtrip (hot path)')
check(_inst._get_level_roles(555) == {}, 'autorole_level: level_roles пусто → {}')

import cogs.anime_daily as ad  # noqa: E402

check(ad._load() == {}, 'anime_daily: дефолт {}')
ad._save({'last': '2026-08-12'})
check(ad._load()['last'] == '2026-08-12', 'anime_daily: roundtrip')

import cogs.night_summary as ns  # noqa: E402

ns._save_state({'last_run': '10:00'})
check(ns._load_state()['last_run'] == '10:00', 'night_summary: state roundtrip')

import cogs.giveaway as gw  # noqa: E402

gw._save_giveaways(66, {'1': {'prize': 'Nitro'}})
check(gw._load_giveaways(66)['1']['prize'] == 'Nitro', 'giveaway: roundtrip')

import cogs.security as sc  # noqa: E402

cfg = sc._load_cfg(88)
check(cfg['ai_spam'] is False and cfg['new_account_days'] == 7,
      'security: дефолтный конфиг полный (флаги opt-in выкл)')
cfg['ai_spam'] = False
sc._save_cfg(88, cfg)
check(sc._load_cfg(88)['ai_spam'] is False, 'security: сохранённое значение читается')

import cogs.auto_filter as af  # noqa: E402

c1 = af.load_config(9090)
check(set(('enabled', 'words', 'links', 'caps', 'flood')).issubset(c1),
      'auto_filter: load_config мержит дефолты (words/links/caps/flood)')
af.save_config(9090, dict(c1, enabled=True))
check(af.load_config(9090)['enabled'] is True, 'auto_filter: save → load через общий кеш')
check(any('autofilter_9090' in x for x in cache_stats()['paths']),
      'auto_filter-конфиг в общем кеше (единый кеш для бота и панели)')

import cogs.meeting as mt  # noqa: E402

mcfg = mt._load_cfg(77)
check(mcfg['active'] is False and mcfg['staff_roles'] == [], 'meeting: дефолт cfg полный')
mt._save_cfg(77, dict(mcfg, active=True))
check(mt._load_cfg(77)['active'] is True, 'meeting: cfg roundtrip')
inv_path = 'data/invite_counts_77.json'
save_json(inv_path, {'1': {'total': 5}, '2': 3})
check(mt._load_invites(77) == {'1': 5, '2': 3}, 'meeting: invites нормализация dict/int')

import cogs.dm_logger as dl  # noqa: E402

check(dl._load_dm_log() == {}, 'dm_logger: пустой лог → {}')
save_json(dl.DM_WHITELIST_FILE, [{'id': '42'}, '7', {'note': 'без id'}])
check(dl._load_dm_whitelist() == {'42', '7'}, 'dm_logger: whitelist — dict и str, мусор отброшен')

import services.panel_todo as todo  # noqa: E402

t = todo.add_task('Проверить стор', author='Тест')
check(any(x['id'] == t['id'] for x in todo.list_tasks()), 'panel_todo: задача добавилась')
todo.toggle_task(t['id'])
check([x for x in todo.list_tasks() if x['id'] == t['id']][0]['done'] is True,
      'panel_todo: toggle → done')
todo.delete_task(t['id'])
check(all(x['id'] != t['id'] for x in todo.list_tasks()), 'panel_todo: delete')

# ═══ 6. Линт: все конвертированные коги импортируют json_store ═════════
print('== линт делегатов ==')
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONVERTED = ['anime_daily', 'proactive_ai', 'companion', 'ai_chat', 'mod_kit',
             'mod_plus', 'giveaway', 'health', 'night_summary', 'meeting',
             'security', 'server_info', 'events', 'custom_embeds',
             'autorole_level', 'rejoin_roles', 'reaction_roles_cog',
             'dm_logger', 'dm_report', 'social', 'mod_case', 'auto_filter']
missing = []
for name in CONVERTED:
    src = io.open(os.path.join(_ROOT, 'cogs', name + '.py'), encoding='utf-8').read()
    if 'json_store' not in src:
        missing.append(name)
check(not missing, f'все {len(CONVERTED)} сконвертированных когов на json_store '
                   f'({missing if missing else "все импортируют"})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(0 if FAIL == 0 else 1)
