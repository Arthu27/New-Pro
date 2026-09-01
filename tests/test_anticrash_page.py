# -*- coding: utf-8 -*-
"""Тесты страницы «Анти-краш центр»: рендер, контракт API, права, конфиг.

Запуск: python3 tests/test_anticrash_page.py
"""
import json
import math
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix='hakumo_ac_page_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from error_handler import ErrorHandler, DEFAULT_CONFIG, CONFIG_META  # noqa: E402

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


# ═══ 1. Живой обработчик с наполненной статистикой ═══════════════════════
print('== ErrorHandler: наполнение и overview ==')


class FakeGuild:
    def __init__(self, gid):
        self.id = gid


class BareBot:
    """Бот без error_handler — анти-краш «офлайн»."""
    guilds = []


class FakeBot:
    guilds = [FakeGuild(1001), FakeGuild(1002), FakeGuild(1003)]
    latency = 0.042

    def is_closed(self):
        return False


eh = ErrorHandler(FakeBot())

try:
    raise ValueError('тестовый бум')
except ValueError as e:
    eh._log_error('юнит-ошибка', e, where='test:unit', critical=True)

for _ in range(2):
    try:
        raise KeyError('шум')
    except KeyError as e:
        eh._log_error('обычная ошибка', e, where='test:other')

for _ in range(20):
    eh._track_cog('cogs.test_cog')

ov = eh.get_overview()
check(ov.get('ok') is True, 'overview: ok=True')

# ключи, которые читает JS страницы
NEED_KEYS = [
    'ok', 'master_enabled', 'watchdog_on', 'breaker_on', 'filter_on',
    'warning_monitor_on', 'connection_watch_on', 'webhook_on',
    'uptime_human', 'guilds', 'daily7', 'total_errors', 'errors_last_hour',
    'critical', 'warnings_total', 'latency_ms', 'loop_lag_max', 'loop_lag_recent',
    'disconnects', 'disconnects_hour', 'filtered', 'repeats_hidden',
    'alerts_sent', 'alerts_queued', 'channel_configured',
    'webhook_sent', 'webhook_dropped', 'breakers', 'top_types', 'top_cogs',
    'warnings', 'last_errors',
]
missing = [k for k in NEED_KEYS if k not in ov]
check(not missing, f'overview: все ключи для страницы на месте ({missing or "ок"})')
check(ov['total_errors'] == 3 and ov['critical'] == 1, 'overview: счётчики ошибок')
check(ov['guilds'] == 3 and ov['latency_ms'] == 42, 'overview: guilds и пинг')
check(len(ov['daily7']) == 7 and ov['daily7'][-1]['count'] == 3,
      'overview: график 7 дней, сегодня — последняя колонка')
check(ov['daily7'][-1]['day'] == time.strftime('%Y-%m-%d', time.localtime()),
      'overview: последний день графика — сегодня')
check(ov['breakers'] and ov['breakers'][0]['module'] == 'cogs.test_cog'
      and ov['breakers'][0]['tripped_at'], 'overview: breaker сработал и отдаёт время')
le = ov['last_errors'][0]
check(all(k in le for k in ('ts', 'type', 'where', 'loc', 'msg', 'critical')),
      'overview: формат записи last_errors полный')
check(le['type'] == 'KeyError' and ov['last_errors'][-1]['type'] == 'ValueError',
      'overview: last_errors от новых к старым')
check(isinstance(ov['warnings'], dict) and isinstance(ov['top_types'], list),
      'overview: warnings словарь, топы списком')

# ═══ 2. Панель: страница ═════════════════════════════════════════════════
print('== панель: /anticrash ==')
from web.app import app as _flask_app, set_bot_instance  # noqa: E402

FakeBot.error_handler = eh
set_bot_instance(FakeBot())
client = _flask_app.test_client()


def login_as(role):
    # discord_id специально НЕ ставим: login_required перечитывал бы роль
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'PanelAC'
        s['role'] = role


r = client.get('/anticrash')
check(r.status_code in (302, 401, 403), f'страница без логина закрыта ({r.status_code})')

login_as('uye')
check(client.get('/anticrash').status_code in (302, 403), 'uye не пускают на страницу')
login_as('mod')
check(client.get('/anticrash').status_code in (302, 403), 'mod тоже — страница admin+')

login_as('admin')
r = client.get('/anticrash')
page = r.get_data(as_text=True)
check(r.status_code == 200, 'admin: страница рендерится (200)')

# статическая разметка: все контейнеры, которым нужен JS
MARKERS = ('id="ac-hero"', 'id="hero-title"', 'id="hero-sub"', 'id="hero-chips"',
           'id="hero-updated"', 'data-state="dead"',
           'id="v-total"', 'id="v-hour"', 'id="v-crit"', 'id="v-warnings"',
           'id="v-uptime"', 'id="v-ping"', 'id="v-lag"', 'id="v-disconnects"',
           'id="v-filtered"', 'id="v-alerts"', 'id="v-webhook"',
           'id="daily-chart"', 'id="daily-total"',
           'id="breaker-list"', 'id="top-types"', 'id="top-cogs"',
           'id="top-warnings"', 'id="last-errors"',
           'id="cfg-groups"', 'id="cfg-note"', 'id="ac-toast"')
missing_markers = [m for m in MARKERS if m not in page]
check(not missing_markers,
      f'разметка: все {len(MARKERS)} контейнеров на месте ({missing_markers or "ок"})')

check('CFG_GROUPS' in page and 'ac-cfg-group' in page, 'страница: группировка настроек в JS')
check('ac-savebar' in page and 'Сохранить' in page, 'страница: липкая панель сохранения')
check("/api/anticrash/overview" in page and "/api/anticrash/config" in page
      and "/api/anticrash/reset" in page, 'страница: дёргает все три API')
check('setLiveRefresh' in page and 'loadOverview' in page and 'g*:guardian' in page, 'страница: live-обновление пушем (SSE), таймер — подстраховка')
check('document.hidden' in page, 'страница: пауза опроса в фоновой вкладке')
check('{%' not in page and '{{' not in page,
      'страница: после рендера не осталось сырых Jinja-тегов')

# каждый ключ конфига должен быть разложен по группам (против «потерявшихся» полей)
not_grouped = [k for k in DEFAULT_CONFIG if f"'{k}'" not in page]
check(not not_grouped, f'все {len(DEFAULT_CONFIG)} ключей конфига разложены по группам '
                       f'({not_grouped or "ок"})')

# ═══ 3. Панель: API overview / config / reset ═══════════════════════════
print('== панель: API ==')
r = client.get('/api/anticrash/overview')
d = r.get_json()
check(r.status_code == 200 and d.get('ok') is True, 'API overview: 200 и ok')
check(d['total_errors'] == ov['total_errors'], 'API overview: живые данные обработчика')
check(d['breakers'][0]['module'] == 'cogs.test_cog', 'API overview: breaker виден в API')

login_as('mod')
check(client.get('/api/anticrash/overview').status_code == 403, 'API overview: mod закрыт')
check(client.post('/api/anticrash/config', json={'master_enabled': False}).status_code == 403,
      'API config POST: mod закрыт')
check(client.post('/api/anticrash/reset').status_code == 403, 'API reset: mod закрыт')

login_as('admin')
r = client.get('/api/anticrash/config')
d = r.get_json()
check(d.get('ok') is True and 'config' in d and 'meta' in d and 'order' in d,
      'API config GET: config+meta+order')
check(d['order'] == list(DEFAULT_CONFIG.keys()), 'API config GET: order = DEFAULT_CONFIG')
meta_ok = all(k in d['meta'] and {'label', 'desc', 'type'} <= set(d['meta'][k])
              for k in DEFAULT_CONFIG)
check(meta_ok, 'API config GET: meta покрывает все ключи (label/desc/type)')
# meta и порядок согласованы — страница не покажет поле без описания
check(all(k in CONFIG_META for k in DEFAULT_CONFIG), 'CONFIG_META без пропусков')

r = client.post('/api/anticrash/config',
                json={'loop_lag_threshold': 7.5, 'master_enabled': False})
d = r.get_json()
check(d.get('ok') is True, 'API config POST: валидные значения приняты')
check(abs(eh.config['loop_lag_threshold'] - 7.5) < 1e-9
      and eh.config['master_enabled'] is False, 'API config POST: применено в обработчике')
check(eh.get_overview()['master_enabled'] is False,
      'API config POST: master выключен — страница покажет «отключён»')

r = client.post('/api/anticrash/config', json={'__evil__': 1})
check(r.status_code == 400 and '__evil__' in r.get_json().get('errors', {}),
      'API config POST: неизвестный ключ → 400 с errors')
r = client.post('/api/anticrash/config', json={'loop_lag_threshold': 'abc'})
check(r.status_code == 400 and 'loop_lag_threshold' in r.get_json().get('errors', {}),
      'API config POST: кривое число → 400 с errors')
check(abs(eh.config['loop_lag_threshold'] - 7.5) < 1e-9,
      'API config POST: провал не испортил старое значение')

r = client.post('/api/anticrash/config', json={'master_enabled': True,
                                               'loop_lag_threshold': 5.0})
check(r.get_json().get('ok') is True, 'API config POST: вернулся рабочий конфиг')

r = client.post('/api/anticrash/reset')
check(r.get_json().get('ok') is True and eh.stats['total_errors'] == 0
      and not eh.stats['breakers'], 'API reset: статистика обнулена')

# обработчик офлайн (бот без error_handler)
set_bot_instance(BareBot())
r = client.get('/api/anticrash/overview')
check(r.get_json().get('ok') is False, 'overview без обработчика: ok=False (страница покажет «офлайн»)')
r = client.get('/api/anticrash/config')
check(r.status_code == 503, 'config без обработчика: 503')
set_bot_instance(FakeBot())

# ═══ 4. Шаблон: рендер без ошибок с реальными ctx-переменными ═══════════
print('== шаблон: Jinja ==')
check('ac-m-lbl' in page and 'ac-group-label' in page, 'шаблон: группированные метрики')
check('keys:' in page, 'шаблон: массивы ключей групп на месте')
check(page.count('ac-cfg-head') >= 1 and 'fa-chevron-down' in page,
      'шаблон: сворачиваемые группы (шеврон)')
check('color-mix' in page, 'шаблон: theme-aware цвета (color-mix)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
