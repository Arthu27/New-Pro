# -*- coding: utf-8 -*-
"""Раздел «Участники»: наблюдение и AFK-список работают по-настоящему.

Две поломки, найденные подробным разбором раздела:

1. «Наблюдение» была пуста ВСЕГДА. Бот кладёт фигуранта в
   data/mod_advanced_data.json (cogs/moderation.py, 2+ мьюта), а панель
   читала data/mod_data.json — там ключ watchlist не создаёт никто.
   То есть «настроил, а не работает» в чистом виде.

2. AFK-список жил только в памяти бота и обнулялся на каждом рестарте,
   поэтому страница «AFK список» показывала пусто, хотя люди стояли в AFK.

Запуск:  .venv/bin/python tests/test_members_category.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DEMO_MODE', '1')

PASS = FAIL = 0
GID = '987654321098765432'
ADV = 'data/mod_advanced_data.json'
MOD = 'data/mod_data.json'


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


def _backup(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return f.read()


def _restore(path, text):
    if text is None:
        if os.path.exists(path):
            os.remove(path)
    else:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)


_adv_bk, _mod_bk = _backup(ADV), _backup(MOD)

from web.app import app  # noqa: E402

client = app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'
    s['selected_guild'] = GID

print('== 1. «Наблюдение» читает тот файл, куда пишет бот ==')
os.makedirs('data', exist_ok=True)
with open(ADV, 'w', encoding='utf-8') as f:
    json.dump({'watchlist': {GID: {'4242424242': {
        'reason': 'Автоматически: 2-й мьют. спам',
        'added_by': 'Модератор#0001',
        'timestamp': '2026-09-02T10:00:00+00:00',
        'until': 1893456000,
    }}}}, f, ensure_ascii=False)
_restore(MOD, None)   # старого файла нет — как на свежей установке

r = client.get(f'/api/watchlist/{GID}')
rows = r.get_json() or []
check(r.status_code == 200, f'API наблюдения -> {r.status_code}')
check(len(rows) == 1, f'фигурант из mod_advanced_data.json виден (пришло {len(rows)})')
if rows:
    check(rows[0]['id'] == '4242424242', f"id совпал: {rows[0]['id']}")
    check('2-й мьют' in rows[0]['reason'], f"причина доехала: {rows[0]['reason'][:40]}")
    check(rows[0]['added_by'] == 'Модератор#0001', 'кто добавил — видно')

print('== 2. старые записи из mod_data.json не теряются ==')
_restore(ADV, None)
with open(MOD, 'w', encoding='utf-8') as f:
    json.dump({'watchlist': {GID: {'777': {'reason': 'старая запись',
                                           'added_by': 'X', 'timestamp': ''}}}}, f,
              ensure_ascii=False)
rows = client.get(f'/api/watchlist/{GID}').get_json() or []
check(len(rows) == 1 and rows[0]['id'] == '777',
      f'запасной файл отдал старую запись (пришло {len(rows)})')

print('== 3. битый JSON не роняет страницу ==')
with open(ADV, 'w', encoding='utf-8') as f:
    f.write('{ не json')
r = client.get(f'/api/watchlist/{GID}')
check(r.status_code == 200, f'битый файл -> {r.status_code}, а не 500')

print('== 4. AFK-список переживает рестарт бота ==')
from cogs.afk import AFK, AFK_STATE_FILE  # noqa: E402


class _FakeBot:
    guilds = []

    def get_guild(self, gid):
        return None


async def _afk_roundtrip():
    if os.path.exists(AFK_STATE_FILE):
        os.remove(AFK_STATE_FILE)
    cog = AFK(_FakeBot())
    await cog.cog_load()
    check(cog._afk == {}, 'на пустом файле список пуст')

    cog._set(GID, 5150, 'отошёл на час')
    cog._set(GID, 5151, 'сплю')
    await cog._flush()          # _mark_dirty создал задачу — дожидаемся записи
    check(os.path.exists(AFK_STATE_FILE), f'файл состояния создан: {AFK_STATE_FILE}')

    # «Рестарт»: новый экземпляр кога читает файл
    cog2 = AFK(_FakeBot())
    await cog2.cog_load()
    check(len(cog2._afk.get(GID, {})) == 2,
          f"после «рестарта» восстановлено {len(cog2._afk.get(GID, {}))} из 2")
    check(cog2._get(GID, 5150) and cog2._get(GID, 5150)['reason'] == 'отошёл на час',
          'причина AFK сохранилась')

    # вышел из AFK — записи нет и на диске тоже
    cog2._remove(GID, 5150)
    await cog2._flush()
    cog3 = AFK(_FakeBot())
    await cog3.cog_load()
    check(cog3._get(GID, 5150) is None, 'вышедший из AFK не возвращается после рестарта')
    check(cog3._get(GID, 5151) is not None, 'остальной список на месте')


asyncio.run(_afk_roundtrip())

print('== 5. AFK API не падает на мусорном id ==')
r = client.get('/api/afk/не-число')
check(r.status_code == 200, f'/api/afk/не-число -> {r.status_code} (было 500)')

print('== 6. «Приглашения»: старые записи получают нужные поля ==')
# Файл исторически писался как {user, inviter, timestamp}, а шаблон рисует
# name/avatar/invite_code/joined_at — карточки выходили без имени и времени.
_joins = f'data/invite_joins_{GID}.json'
_joins_bk = _backup(_joins)
with open(_joins, 'w', encoding='utf-8') as f:
    json.dump([{'user': 'newbie_09', 'inviter': 'artem.mods',
                'timestamp': '2026-08-24T12:00:00+00:00'}], f, ensure_ascii=False)
d = client.get(f'/api/guild/{GID}/invite-tracker-full').get_json() or {}
rj = (d.get('recent_joins') or [{}])[0]
check(rj.get('name') == 'newbie_09', f"имя доехало: {rj.get('name')!r} (было пусто)")
check(rj.get('joined_at') == '2026-08-24T12:00:00+00:00',
      f"время доехало: {rj.get('joined_at')!r} (было пусто)")
check(rj.get('inviter') == 'artem.mods', 'кто пригласил — на месте')
check(all(k in rj for k in ('avatar', 'invite_code', 'user_id')),
      f'набор полей полный: {sorted(rj)}')
with open(_joins, 'w', encoding='utf-8') as f:
    f.write('{ не json')
check(client.get(f'/api/guild/{GID}/invite-tracker-full').status_code == 200,
      'битый файл входов -> 200, а не 500')
check(client.get('/api/guild/не-число/invite-tracker-full').status_code == 200,
      'мусорный id сервера -> 200, а не 500')
_restore(_joins, _joins_bk)

# Отдельного кога учёта приглашений здесь НЕТ сознательно: invite_tracker.py
# удалён из проекта решением владельца, и tests/test_cogs_policy.py стережёт,
# что файл не вернётся на диск. Поэтому в боевом режиме «Вступили»/«Вышли»
# остаются пустыми — источник данных для них отсутствует. Возвращать учёт
# можно только решением владельца, а не обходом имени файла.

# ── прибираем за собой, чтобы не портить демо-данные ──
_restore(ADV, _adv_bk)
_restore(MOD, _mod_bk)
if os.path.exists(AFK_STATE_FILE):
    os.remove(AFK_STATE_FILE)

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
