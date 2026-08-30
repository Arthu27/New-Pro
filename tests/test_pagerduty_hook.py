# -*- coding: utf-8 -*-
"""Мост PagerDuty → Discord (панель принимает события и постит карточки).

1. services.pagerduty_hook: форматтер v2/v3 payload, токены, тумблер.
2. Публичный хук /hooks/pagerduty/<gid>/<token>: верный токен → карточка
   в канал; неверный → 403; бот офлайн → 503 (PD ретраит); выключен → 403.
3. Панель: GET/POST /api/guild/<gid>/pagerduty (канал, тумблер, реген),
   /pagerduty/test — тестовая тревога; страница /pagerduty отвечает 200.
4. Канал-роут pagerduty_channel: адаптер на хабе каналов.

Запуск: python3 tests/test_pagerduty_hook.py
"""
import asyncio
import os
import shutil
import sys
import tempfile
import threading

_TMP = tempfile.mkdtemp(prefix='hakumo_pagerduty_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
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


G = 777
CH_ALERTS = 301


# ── фейки Discord ────────────────────────────────────────────────────────

class _Ch:
    def __init__(s, i, guild=None):
        s.id = i
        s.name = f'канал-{i}'
        s.guild = guild
        s.sent = []

    async def send(s, embed=None, **kw):
        s.sent.append(embed)


class _Guild:
    def __init__(s, i):
        s.id = i
        s.name = 'Тест'
        s.icon = None
        s.member_count = 10
        s.members = []
        s.channels = [_Ch(300 + k, guild=s) for k in range(4)]
        s.text_channels = s.channels
        s.roles = []

    def get_channel(s, cid):
        return next((c for c in s.channels if c.id == cid), None)


class _Bot:
    def __init__(s, guild):
        s.guilds = [guild]
        s.user = None
        s.voice_clients = []
        s.latency = 0.03

    def get_guild(s, gid):
        return s.guilds[0] if int(gid) == s.guilds[0].id else None

    def get_cog(s, name):
        return None

    def is_closed(s):
        return False

    async def change_presence(s, **kw):
        pass


print('== 1. Форматтер: v3 и v2, цвета и поля ==')
from services import pagerduty_hook as PD  # noqa: E402

v3 = {'event_type': 'incident.triggered', 'occurred_at': '2026-08-27T10:00:00Z',
      'incident': {'incident_number': 12, 'title': 'API не отвечает',
                   'html_url': 'https://pagerduty.com/i/12', 'urgency': 'high',
                   'service': {'summary': 'Payment API'},
                   'assignments': [{'assignee': {'summary': 'OnCall-1'}}]}}
info = PD.format_incident(v3)
check(info['title'] == '🔥 Тревога #12' and info['color'] == 0xE74C3C,
      'v3 triggered: заголовок с номером и красный цвет')
check(info['service'] == 'Payment API' and info['assignee'] == 'OnCall-1'
      and info['urgency'] == 'high' and info['url'].endswith('/12'),
      'v3: сервис, дежурный, срочность и ссылка разобраны')

v3r = dict(v3, event_type='incident.resolved')
check(PD.format_incident(v3r)['color'] == 0x2ECC71, 'resolved → зелёный')
v3a = dict(v3, event_type='incident.acknowledged')
check(PD.format_incident(v3a)['kind'] == 'ack', 'acknowledged → kind ack')

v2 = {'messages': [{'type': 'incident.trigger',
                    'data': {'incident_number': 7, 'title': 'Диск полный',
                             'service': {'summary': 'DB'},
                             'assignments': [{'assignee': {'summary': 'DevOps'}}]}}]}
info2 = PD.format_incident(v2)
check(info2['title'] == '🔥 Тревога #7' and info2['service'] == 'DB',
      'v2 messages[] тоже понимается')

junk = PD.format_incident({'hello': 'world'})
check(junk['title'].startswith('🔔') and junk['incident_title'] == '—',
      'мусорный payload не роняет форматтер')
check(PD.format_incident(None)['kind'] == 'other', 'None — тоже не падает')

print('== 2. Токены: выдача, регенерация, сверка ==')
st = PD.get_settings(G)
check(st['token'] and st['enabled'], 'токен создан, мост включён по умолчанию')
check(PD.check_token(G, st['token']), 'верный токен проходит')
check(not PD.check_token(G, 'nope'), 'неверный токен отвергнут')
PD.set_enabled(G, False)
check(not PD.check_token(G, st['token']), 'выключенный мост не принимает')
PD.set_enabled(G, True)
new = PD.regen_token(G)
check(new != st['token'] and PD.check_token(G, new)
      and not PD.check_token(G, st['token']), 'регенерация убивает старый URL')

print('== 3. Публичный хук: доставка карточек ==')
from web.app import app as _flask_app, set_bot_instance  # noqa: E402

guild = _Guild(G)
bot = _Bot(guild)
_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()
bot.loop = _loop
set_bot_instance(bot)

from services.channel_routes import set_route  # noqa: E402
from web.routes._common import _run_async  # noqa: E402

client = _flask_app.test_client()
token = PD.get_settings(G)['token']

# маршрут ещё не задан: 200, но карточки нет (ретраев не просим)
r = client.post(f'/hooks/pagerduty/{G}/{token}', json=v3)
check(r.status_code == 200 and not r.get_json().get('success'),
      'без канала: честный 200 без ретраев PagerDuty')

set_route(G, 'pagerduty_channel', CH_ALERTS)
r = client.post(f'/hooks/pagerduty/{G}/{token}', json=v3)
d = r.get_json()
alert_ch = guild.get_channel(CH_ALERTS)
check(r.status_code == 200 and d.get('success') and len(alert_ch.sent) == 1,
      f'событие принято и доставлено ({d.get("event")})')
card = alert_ch.sent[0]
check(card.title == '🔥 Тревога #12' and 'Payment API' in str(card.fields)
      and 'https://pagerduty.com/i/12' in card.description,
      'карточка: заголовок, сервис и ссылка на месте')
check('PagerDuty · incident.triggered' in card.footer.text,
      'подпись называет событие')

r = client.post(f'/hooks/pagerduty/{G}/{token}', json=v3r)
check(r.status_code == 200 and len(alert_ch.sent) == 2, 'resolved тоже доставлен')

r = client.post(f'/hooks/pagerduty/{G}/bad-token', json=v3)
check(r.status_code == 403, 'чужой токен → 403')

r = client.post(f'/hooks/pagerduty/{G}/?x=1', json=v3)  # мусорный путь — 404
check(r.status_code == 404, 'мусорный путь не ломает сервер')

# бот офлайн → 503, PagerDuty повторит
set_bot_instance(None)
r = client.post(f'/hooks/pagerduty/{G}/{token}', json=v3)
check(r.status_code == 503, 'бот офлайн → 503 (PD ретраит, тревога не теряется)')
set_bot_instance(bot)

# тумблер выключен → 403
PD.set_enabled(G, False)
r = client.post(f'/hooks/pagerduty/{G}/{token}', json=v3)
check(r.status_code == 403, 'выключенный мост → 403')
PD.set_enabled(G, True)

print('== 4. Панель: настройки и тест ==')
with client.session_transaction() as sess:
    sess.clear()
    sess['logged_in'] = True
    sess['username'] = 'Owner'
    sess['role'] = 'owner'
    sess['selected_guild'] = '777'

r = client.get('/api/guild/777/pagerduty')
d = r.get_json()
check(r.status_code == 200 and d.get('success'), 'GET настроек — 200')
check(d.get('hook_path', '').startswith(f'/hooks/pagerduty/777/')
      and d.get('token'), 'hook_path и токен на месте')
check(any(c['id'] == str(CH_ALERTS) for c in d.get('channels', [])),
      'список каналов сервера отдан')
check(d.get('bot_online') is True and d.get('channel_id') == CH_ALERTS,
      'готовность: бот онлайн и канал выбран')

r = client.post('/api/guild/777/pagerduty', json={'channel_id': 302})
d = r.get_json()
check(d.get('success') and d.get('channel_id') == 302,
      'смена канала сохраняется')

before = d.get('token')
r = client.post('/api/guild/777/pagerduty', json={'regen': True})
d = r.get_json()
check(d.get('success') and d.get('token') != before and d.get('regenerated'),
      'регенерация токена из панели')
token = d['token']

r = client.post('/api/guild/777/pagerduty', json={'channel_id': CH_ALERTS})
n_before = len(alert_ch.sent)
r = client.post('/api/guild/777/pagerduty/test')
d = r.get_json()
check(r.status_code == 200 and d.get('success')
      and len(alert_ch.sent) == n_before + 1,
      f'тестовая тревога дошла ({d.get("message")})')
check(alert_ch.sent[-1].title == '🔥 Тревога #42', 'тест — карточка «#42»')

r = client.get('/pagerduty')
check(r.status_code == 200 and b'PagerDuty' in r.data, 'страница /pagerduty — 200')

# гость не видит настройки
with client.session_transaction() as sess:
    sess.clear()
r = client.get('/api/guild/777/pagerduty')
check(r.status_code in (301, 302, 401, 403), 'гостю закрыто')
r = client.get('/pagerduty')
check(r.status_code in (301, 302, 401, 403), 'страница гостю закрыта')

print('== 5. Канал-роут на хабе ==')
from services.channel_routes import get_route  # noqa: E402

check(get_route(G, 'pagerduty_channel') == CH_ALERTS,
      'маршрут pagerduty_channel хранится')
with client.session_transaction() as sess:   # снова владелец
    sess['logged_in'] = True
    sess['username'] = 'Owner'
    sess['role'] = 'owner'
    sess['selected_guild'] = '777'
r = client.get('/api/channel-routes')
d = r.get_json()
keys = [x['key'] for x in (d or {}).get('routes', [])]
check('pagerduty_channel' in keys, 'маршрут виден на хабе каналов')

print('== 6. История доставок: видно из панели, отправляются данные или нет ==')
r = client.get(f'/api/guild/{G}/pagerduty')
d = r.get_json()
hist = d.get('history') or []
check(len(hist) >= 4, f'история пишется ({len(hist)} событий)')
st = d.get('history_stats') or {}
check(st.get('total', 0) >= 4 and st.get('sent', 0) >= 3, 'сводка истории считает доставки')
check(any(e.get('status') == 'no_channel' for e in hist), 'событие «канал не выбран» попало в историю')
check(any(e.get('status') == 'offline' for e in hist), 'событие «бот офлайн» попало в историю (не потерялось)')
check(d.get('bot_status') == 'online' and d.get('bot_online') is True,
      'бот готов — статус online')
check(hist[0].get('at', '') >= hist[-1].get('at', ''), 'история: новые сверху')

print('== 7. Правда о статусе бота (жалоба «данные отправляет, но офлайн») ==')
# шлюз закрыт: объект есть, но бот мёртв — раньше писалось «online»
class _DeadBot(_Bot):
    def __init__(s, guild):
        super().__init__(guild)
        s.status = 'offline'
    def is_closed(s):
        return True
    def is_ready(s):
        return False
set_bot_instance(_DeadBot(guild))
r = client.get(f'/api/guild/{G}/pagerduty')
d = r.get_json()
check(d.get('bot_online') is False and d.get('bot_status') == 'offline',
      'мёртвый шлюз = честный offline (не «объект есть = онлайн»)')
r = client.get('/api/stats')
d = r.get_json()
check(d.get('status') == 'offline', '/api/stats не врёт про мёртвый шлюз (был хардкод online)')
# подключается: объект есть, готовности нет
class _StartingBot(_Bot):
    def __init__(s, guild):
        super().__init__(guild)
        s.status = 'offline'
    def is_closed(s):
        return False
    def is_ready(s):
        return False
set_bot_instance(_StartingBot(guild))
r = client.get('/api/stats')
d = r.get_json()
check(d.get('status') == 'starting', '/api/stats: подключение = starting')
# живой бот с presence idle: шлюз онлайн, но ВЫГЛЯДИТ «не в сети»
class _IdleBot(_Bot):
    def __init__(s, guild):
        super().__init__(guild)
        s.status = 'idle'
    def is_closed(s):
        return False
    def is_ready(s):
        return True
set_bot_instance(_IdleBot(guild))
r = client.get('/api/stats')
d = r.get_json()
check(d.get('status') == 'online' and d.get('presence') == 'idle',
      'шлюз жив + presence=idle — оба факта видны отдельно')
set_bot_instance(bot)   # вернуть как было

print('== 8. Новая страница: мост, история, превью ==')
r = client.get('/pagerduty')
page = r.get_data(as_text=True)
for marker, what in [('pd-bridge', 'диаграмма моста PagerDuty→Панель→Discord'),
                     ('pdHistBody', 'таблица истории сигналов'),
                     ('pdCard', 'превью карточки Discord'),
                     ('bot_status', 'правдивый статус бота в JS'),
                     ('setLiveRefresh', 'живое обновление моста')]:
    check(marker in page, f'страница содержит {what}')

print('== 9. Node-харнесс: живой JS моста (статусы, история, маска) ==')
import json as _json
import re as _re
import subprocess as _sp
page_src = open(os.path.join(ROOT, 'web', 'templates', 'pagerduty.html'),
                encoding='utf-8').read()
_scripts = _re.findall(r'<script>(.*?)</script>', page_src, _re.S)
check(len(_scripts) >= 1, 'inline-скрипт страницы извлечён')
page_js = _scripts[-1].replace('{{ (guild_id|string)|tojson }}', '777')

harness = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const byId = {};
function makeEl(id) {
  const e = { id, textContent: '', title: '',
              style: {}, disabled: false, value: '0', checked: false,
              _classes: new Set(), _handlers: {}, _html: '' };
  Object.defineProperty(e, 'innerHTML', {
    get() { return this._html; }, set(v) { this._html = String(v); }
  });
  Object.defineProperty(e, 'className', {
    get() { return Array.from(e._classes).join(' '); },
    set(v) { e._classes = new Set(String(v).split(/\s+/).filter(Boolean)); }
  });
  e.classList = {
    add(c) { e._classes.add(c); }, remove(c) { e._classes.delete(c); },
    contains(c) { return e._classes.has(c); }
  };
  e.addEventListener = (t, fn) => { (e._handlers[t] = e._handlers[t] || []).push(fn); };
  e.getAttribute = (k) => e['attr_' + k] !== undefined ? e['attr_' + k] : null;
  e.setAttribute = (k, v) => { e['attr_' + k] = String(v); };
  return e;
}
const doc = {
  getElementById: (id) => byId[id] || (byId[id] = makeEl(id)),
  querySelectorAll: (sel) => sel.includes('pd-tab') ? TABS : [],
  createElement: () => makeEl('tmp'),
  body: { appendChild() {}, removeChild() {} }
};
const TABS = ['triggered', 'ack', 'resolved'].map(k => {
  const t = makeEl('tab-' + k); t.setAttribute('data-kind', k); return t; });
const tabs = TABS;

let DATA = {
  success: true, enabled: true, token: 'tok123secret456', bot_online: true,
  bot_status: 'online', bot_presence: 'online',
  hook_path: '/hooks/pagerduty/777/tok123secret456', channel_id: 301,
  channels: [{ id: '301', name: 'тревоги' }, { id: '302', name: 'общее' }],
  history: [
    { at: '2026-08-30T10:00:00+00:00', event: 'incident.triggered', title: '🔥 Тревога #12',
      incident: 'API не отвечает', status: 'sent', note: 'тревоги' },
    { at: '2026-08-30T09:00:00+00:00', event: 'incident.triggered', title: '🔥 Тревога #11',
      incident: 'БД молчит', status: 'offline', note: 'бот офлайн — PagerDuty повторит' }
  ],
  history_stats: { total: 2, sent: 1, offline: 1, no_channel: 0, error: 0,
                   last_at: '2026-08-30T10:00:00+00:00' }
};
const win = {
  setLiveRefresh: (fn) => { win._tick = fn; },
  showToast: () => {}, confirm: () => true
};
const fetchMock = () => Promise.resolve({
  ok: true, json: () => Promise.resolve(DATA)
});
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
function fail(m) { console.error('FAIL: ' + m); process.exit(1); }

(async () => {
  new Function('document', 'window', 'location', 'navigator', 'fetch', src)(
    doc, win, { origin: 'https://panel.example' },
    { clipboard: { writeText: () => Promise.resolve() } }, fetchMock);
  await sleep(60);

  // 1) всё готово → мост зелёный, пилюля ок
  if (!byId['pdState']._classes.has('ok')) fail('пилюля моста не ок при готовом мосте');
  if (!byId['pdNodeBot'].className.includes('ok')) fail('узел Discord не зелёный при живом боте');
  if (byId['pdNodeBotSt'].innerHTML.indexOf('бот онлайн') === -1) fail('нет подписи «бот онлайн»');
  if (byId['pdHook'].textContent.indexOf('•••') === -1) fail('токен не замаскирован по умолчанию');

  // 2) история: 2 строки, чипы со статусами
  const rows = (byId['pdHistBody'].innerHTML.match(/<tr>/g) || []).length;
  if (rows !== 2) fail('строк истории ' + rows + ', а нужно 2');
  if (byId['pdHistBody'].innerHTML.indexOf('бот офлайн — повторит PD') === -1)
    fail('нет чипа «бот офлайн» в истории');
  if (String(byId['pdKpiSent'].textContent) !== '1') fail('KPI доставлено != 1');

  // 3) тик: бот отвалился → узел красный, пилюля err, история не дёргается заново
  DATA.bot_status = 'offline'; DATA.bot_online = false;
  await win._tick(); await sleep(30);
  if (!byId['pdNodeBot'].className.includes('err')) fail('узел Discord не покраснел');
  if (!byId['pdState']._classes.has('err')) fail('пилюля не err при мёртвом боте');
  if (byId['pdNodeBotSt'].innerHTML.indexOf('тревога не теряется') === -1)
    fail('нет подписи «тревога не теряется»');

  // 4) бот подключается → warn
  DATA.bot_status = 'starting'; DATA.bot_online = false;
  await win._tick(); await sleep(30);
  if (!byId['pdNodeBot'].className.includes('warn')) fail('узел Discord не warn при подключении');

  // 5) живой бот с presence=idle: подключён, но выглядит «не в сети» — и это сказано
  DATA.bot_status = 'online'; DATA.bot_online = true; DATA.bot_presence = 'idle';
  await win._tick(); await sleep(30);
  if (!byId['pdNodeBot'].className.includes('ok')) fail('idle-бот должен быть зелёным (шлюз жив)');
  if (byId['pdNodeBotSt'].innerHTML.indexOf('нет на месте') === -1)
    fail('нет подсказки про idle-видимость');

  // 6) вкладки превью меняют цвет карточки
  tabs[1]._handlers['click'][0]();
  if (byId['pdCard'].style.borderLeftColor !== 'var(--warn)')
    fail('вкладка «Принято» не перекрасила превью');

  // 7) глаз: токен раскрывается и прячется обратно
  byId['pdEye']._handlers['click'][0]();
  if (byId['pdHook'].textContent.indexOf('tok123secret456') === -1) fail('глаз не раскрыл токен');
  byId['pdEye']._handlers['click'][0]();
  if (byId['pdHook'].textContent.indexOf('•••') === -1) fail('глаз не спрятал токен');

  console.log('OK: мост, статусы, история, маска, превью');
})().catch(e => { console.error('ИСКЛЮЧЕНИЕ: ' + (e && e.message)); process.exit(1); });
"""
_js = os.path.join(_TMP, 'pd_page.js')
open(_js, 'w', encoding='utf-8').write(page_js)
_h = os.path.join(_TMP, 'pd_harness.js')
open(_h, 'w', encoding='utf-8').write(harness)
try:
    _proc = _sp.run(['node', _h, _js], capture_output=True, text=True, timeout=60)
    check(_proc.returncode == 0,
          'JS моста работает: статусы online/offline/starting, idle-подсказка, '
          'история, KPI, маска токена, превью'
          + (f' [{_proc.stderr.strip()[:160]}]' if _proc.returncode else ''))
except FileNotFoundError:
    check(False, 'node недоступен для харнесса')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
