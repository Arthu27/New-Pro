# -*- coding: utf-8 -*-
"""Журнал модерации: русские метки действий + только главный сервер.

Проверяем:
  1. services/audit_labels — все 67 действий Discord покрыты русской меткой
     (никаких сырых bot_add / overwrite_create в журнале), легаси-глаголы
     бота тоже переводятся;
  2. /api/logs — при заданном MAIN_GUILD_ID журнал отдаёт ТОЛЬКО его события
     (записи других серверов/демо-заглушек не сливаются в ленту) и старые
     сырые записи переводятся при показе;
  3. /api/search — то же: чужие серверы не ищутся, подписи по-русски;
  4. cogs/logs.py._sync_discord_audit_log — аудит тянется только с главного
     сервера и записывается уже русскими метками.

Запуск: python3 tests/test_audit_labels.py
"""
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_TMP = tempfile.mkdtemp(prefix='hakumo_audit_labels_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['DEMO_MODE'] = '1'
os.environ.pop('TOKEN', None)
os.environ.pop('TОКEN', None)
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'preview123'
os.environ['MAIN_GUILD_ID'] = '987654321098765432'

PASS = 0
FAIL = 0


def check(cond, label, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


# ── 1. Полный словарь меток ────────────────────────────────────────────────
print('== services/audit_labels: покрытие и перевод ==')
import discord  # noqa: E402
from services.audit_labels import AUDIT_LABELS, human_action, audit_label  # noqa: E402
from cogs.logs import CATEGORIES  # noqa: E402

missing = [a.name for a in discord.AuditLogAction if a.name not in AUDIT_LABELS]
check(not missing, f'все {len(list(discord.AuditLogAction))} действий Discord покрыты',
      f'нет: {missing[:6]}')
bad_cat = [k for k, (c, _l) in AUDIT_LABELS.items() if c not in CATEGORIES]
check(not bad_cat, 'все категории меток известны центру логов', f'{bad_cat[:5]}')
non_ru = [k for k, (_c, l) in AUDIT_LABELS.items()
          if not any('а' <= ch.lower() <= 'я' or ch in 'ёЁ' for ch in l)]
check(not non_ru, 'все метки — по-русски', f'{non_ru[:5]}')

check(human_action('bot_add') == 'Бот добавлен',
      'bot_add → по-русски')
check(human_action('AuditLogAction.overwrite_create') == 'Права на канал выданы',
      'AuditLogAction.overwrite_create → по-русски')
check(human_action('Ban') == 'Бан' and human_action('Mute') == 'Мут'
      and human_action('Warn') == 'Предупреждение',
      'легаси-капитализация (mod_data) → по-русски')
check(human_action('Бан') == 'Бан' and human_action('Сервер обновлён') == 'Сервер обновлён',
      'уже переведённое не портится')
check(human_action('') == 'Действие' and human_action(None) == 'Действие',
      'пустое значение — аккуратная заглушка')
check(human_action('какое-то-нестандартное-событие') == 'какое-то-нестандартное-событие',
      'неизвестное остаётся как есть')
check(audit_label('integration_delete') == ('сервер', 'Интеграция удалена'),
      'audit_label отдаёт категорию и метку')

# ── 2. /api/logs: только главный сервер, перевод на показе ─────────────────
print('== /api/logs: изоляция сервера + перевод ==')
import web.app as A  # noqa: E402

MAIN = '111222333444555666'
FOREIGN = '999888777666555444'

with open('data/audit_log.json', 'w', encoding='utf-8') as f:
    json.dump({
        MAIN: [
            {'category': 'сервер', 'action': 'bot_add', 'user_name': 'Sabotash',
             'mod_name': 'Sabotash', 'reason': '', 'timestamp': '2026-08-27T08:02:00+00:00'},
            {'category': 'сервер', 'action': 'overwrite_create', 'user_name': 'Sabotash',
             'mod_name': 'Sabotash', 'reason': '', 'timestamp': '2026-08-27T08:03:00+00:00'},
        ],
        FOREIGN: [
            {'category': 'mod', 'action': 'Бан', 'user_name': 'Чужой-юзер',
             'mod_name': 'Чужой-мод', 'reason': 'чужой сервер', 'timestamp': '2026-08-27T09:00:00+00:00'},
        ],
    }, f, ensure_ascii=False)
with open('data/mod_data.json', 'w', encoding='utf-8') as f:
    json.dump({'case': {
        MAIN: [{'user_id': '523456789012345678', 'mod_id': 'lina.mod', 'action': 'mute',
                'reason': 'тест', 'timestamp': '2026-08-27T10:00:00+00:00'}],
        FOREIGN: [{'user_id': '1', 'mod_id': '2', 'action': 'ban',
                   'reason': 'чужое', 'timestamp': '2026-08-27T10:00:00+00:00'}],
    }}, f, ensure_ascii=False)
with open('data/discord_audit_cache.json', 'w', encoding='utf-8') as f:
    json.dump({
        FOREIGN: [{'category': 'mod', 'action': 'kick', 'user_name': 'Чужой-кик',
                   'mod_name': 'm', 'reason': '', 'timestamp': '2026-08-27T11:00:00+00:00'}],
    }, f, ensure_ascii=False)

_prev_mg = A.MAIN_GUILD_ID
A.MAIN_GUILD_ID = MAIN
try:
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess['logged_in'] = True
        sess['username'] = 't'
        sess['role'] = 'owner'
    r = c.get('/api/logs')
    rows = r.get_json(silent=True) or []
    check(r.status_code == 200 and len(rows) == 3,
          'в ленте только события главного сервера (3 из 4 файловых)',
          f'получено {len(rows)}')
    check(all(str(x.get('guild_id')) == MAIN for x in rows),
          'guild_id у всех строк — главный сервер')
    check(not any('Чужой' in json.dumps(x, ensure_ascii=False) for x in rows),
          'чужие записи не просочились')
    actions = {x.get('action') for x in rows}
    check('Бот добавлен' in actions and 'Права на канал выданы' in actions,
          'старые сырые коды переведены при показе', f'{actions}')
    check('Мут' in actions, 'легаси mute из mod_data → «Мут»', f'{actions}')
    check(not any(a and a.isascii() and '_' in a for a in actions),
          'ни одного сырого snake_case кода в действиях', f'{actions}')

    # ── 3. Поиск: чужое не ищется, русское ищется ──
    r = c.get('/api/search?q=Чужой')
    res = r.get_json(silent=True) or []
    check(not any(x.get('type') == 'log' for x in res),
          'поиск: записи чужого сервера не находятся')
    r = c.get('/api/search?q=права на канал')
    res = r.get_json(silent=True) or []
    check(any(x.get('type') == 'log' and 'Права на канал выданы' in x.get('title', '')
              for x in res),
          'поиск по русской метке находит старую сырую запись', f'{res[:2]}')

    # /api/mod-history (центр модерации «Последние действия»): та же изоляция
    with open('data/warnings.json', 'w', encoding='utf-8') as f:
        json.dump({
            MAIN: {'523456789012345678': [{'reason': 'свой варн', 'moderator': 'admin',
                                           'timestamp': '2026-08-27T10:00:00+00:00'}]},
            FOREIGN: {'623456789012345679': [{'reason': 'чужой варн', 'moderator': 'x',
                                              'timestamp': '2026-08-27T10:00:00+00:00'}]},
        }, f, ensure_ascii=False)
    r = c.get('/api/mod-history')
    hist = r.get_json(silent=True) or []
    hist_rows = hist if isinstance(hist, list) else hist.get('events') or []
    check(r.status_code == 200 and hist_rows
          and all(str(x.get('guild_id')) == MAIN for x in hist_rows),
          '/api/mod-history: только события главного сервера',
          f'{[x.get("guild_id") for x in hist_rows][:6]}')
    check(not any('чуж' in str(x.get('reason', '')).lower() for x in hist_rows),
          '/api/mod-history: чужие причины не просочились')
    r = c.get('/api/warnings')
    wrns = r.get_json(silent=True) or []
    check(r.status_code == 200 and wrns
          and all(str(x.get('guild_id')) == MAIN for x in wrns),
          '/api/warnings: только варны главного сервера',
          f'{[x.get("guild_id") for x in wrns][:6]}')
finally:
    A.MAIN_GUILD_ID = _prev_mg

# ── 4. Синк аудита из Discord: только главный сервер, русские метки ───────
print('== cogs/logs: аудит-синк изолирован главным сервером ==')
from config import Config  # noqa: E402
from cogs.logs import Logs  # noqa: E402

MAIN_I = int(MAIN)
FOREIGN_I = int(FOREIGN)
NOW = datetime.now(timezone.utc)


class _Entries:
    """async-итератор, как у guild.audit_logs()."""

    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        async def gen():
            for r in self._rows:
                yield r
        return gen()


def _entry(eid, action, hours_ago=1):
    return SimpleNamespace(
        id=eid, action=action, reason='',
        created_at=NOW - timedelta(hours=hours_ago),
        target=SimpleNamespace(id=5, name='target', display_name='Target'),
        user=SimpleNamespace(id=6, display_name='Sabotash'),
    )


def _guild(gid, name, rows):
    g = SimpleNamespace(id=gid, name=name)
    g.audit_logs = lambda limit=None, oldest_first=False: _Entries(rows)
    return g


foreign_rows = [
    _entry(10, discord.AuditLogAction.ban),
    _entry(11, discord.AuditLogAction.kick),
]
main_rows = [
    _entry(20, discord.AuditLogAction.bot_add),
    _entry(21, discord.AuditLogAction.integration_delete),
    _entry(22, discord.AuditLogAction.overwrite_update),
]

bot = SimpleNamespace(guilds=[_guild(FOREIGN_I, 'Чужой сервер', foreign_rows),
                              _guild(MAIN_I, 'Главный', main_rows)])
cog = Logs(bot)

_prev_cfg_mg = Config.MAIN_GUILD_ID
for f in ('data/discord_audit_cache.json', 'data/audit_seen.json', 'data/audit_log.json'):
    if os.path.exists(f):
        os.remove(f)
try:
    Config.MAIN_GUILD_ID = MAIN_I
    asyncio.run(cog._sync_discord_audit_log())

    with open('data/discord_audit_cache.json', encoding='utf-8') as f:
        cache = json.load(f)
    check(list(cache.keys()) == [MAIN],
          'кэш аудита — только главный сервер, чужого нет', f'{list(cache)}')
    acts = {e['action'] for e in cache.get(MAIN, [])}
    check(acts == {'Бот добавлен', 'Интеграция удалена', 'Права на канал изменены'},
          'новые записи пишутся уже русскими метками', f'{acts}')

    with open('data/audit_log.json', encoding='utf-8') as f:
        audit = json.load(f)
    check(FOREIGN not in audit and MAIN in audit,
          'общий журнал: чужой сервер не записывался')
    with open('data/audit_seen.json', encoding='utf-8') as f:
        seen = json.load(f)
    check(FOREIGN not in seen and MAIN in seen,
          'курсор синка: чужой сервер даже не трогали')

    # Без MAIN_GUILD_ID — старое поведение (синк всех гильдий бота)
    Config.MAIN_GUILD_ID = 0
    for f in ('data/discord_audit_cache.json', 'data/audit_seen.json'):
        os.remove(f)
    cog._audit_forbidden_notified.clear()
    asyncio.run(cog._sync_discord_audit_log())
    with open('data/discord_audit_cache.json', encoding='utf-8') as f:
        cache2 = json.load(f)
    check(MAIN in cache2 and FOREIGN in cache2,
          'без MAIN_GUILD_ID синк идёт по всем серверам (обратная совместимость)')
finally:
    Config.MAIN_GUILD_ID = _prev_cfg_mg

print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
