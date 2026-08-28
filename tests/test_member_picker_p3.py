# -*- coding: utf-8 -*-
"""П.3: красивый и быстрый выбор участников.

1. suggest(): offset-пагинация — «Показать ещё» догружает следующие страницы
   без дублей (большой сервер с 80+ участниками в пуле).
2. API /member-card/suggest: аватарки и значок «бот» из кэша живого бота,
   offset применяется, поле items стабильной формы.
3. pickRankMembers (node): совпадение с начала имени выше, порядок остальных
   сохранён, регистр не важен.
4. Быстро: suggest на 5000-имённом пуле < 150 мс (серверный поиск, клиент не
   тянет всю базу).
"""
import os
import subprocess
import sys
import tempfile
import time
import json
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp(prefix='p3_members_')
os.chdir(_TMP)
os.environ.setdefault('PANEL_USER', 'admin')
os.environ.setdefault('PANEL_PASSWORD', 'test123')
os.environ['MAIN_GUILD_ID'] = '777'

PASS = 0
FAIL = 0


def check(ok, msg, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {detail}')


from web.routes import member_card_panel as mcp  # noqa: E402

print('== 1. Пагинация suggest ==')
big_pool = {str(10**17 + i): f'Участник {i:03d}' for i in range(80)}
_orig_pool = mcp._name_pool
mcp._name_pool = lambda gid: big_pool
try:
    p1 = mcp.suggest('777', '@')
    p2 = mcp.suggest('777', '@', offset=mcp.SUGGEST_LIMIT)
    p3 = mcp.suggest('777', '@', offset=9 * mcp.SUGGEST_LIMIT)
    p4 = mcp.suggest('777', '@', offset=79)
    check(len(p1) == mcp.SUGGEST_LIMIT and len(p2) == mcp.SUGGEST_LIMIT,
          f'первые две страницы полные (limit={mcp.SUGGEST_LIMIT})')
    ids = [x['user_id'] for x in (p1 + p2 + p3)]
    check(len(ids) == len(set(ids)) == 3 * mcp.SUGGEST_LIMIT, 'страницы не пересекаются, дублей нет')
    check(len(p4) == 1, 'хвост пагинации отдаётся полностью (1 шт)')
    q = mcp.suggest('777', 'участник 05')
    check(any('Участник 0' in x['name'] for x in q), 'поиск по подстроке имени находит')
finally:
    mcp._name_pool = _orig_pool


print('== 2. API: аватарки + флаг бота + offset ==')
mcp._name_pool = lambda gid: big_pool
import web.app as appmod  # noqa: E402

appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['username'] = 'admin'
    s['role'] = 'mod'
    s['selected_guild'] = '777'

av = SimpleNamespace(url='https://cdn.discordapp.com/avatars/1/x.png')
members = [SimpleNamespace(id=10**17, name='Участник 000', display_avatar=av, bot=False),
           SimpleNamespace(id=10**17 + 1, name='Участник 001', display_avatar=av, bot=True)]
guild = SimpleNamespace(id=777, name='Г', members=members)
bot_prev = appmod.bot_instance
appmod.bot_instance = SimpleNamespace(guilds=[guild],
                                      get_guild=lambda i: guild if int(i) == 777 else None)
try:
    r = client.get('/api/guild/777/member-card/suggest?q=%40')
    d = r.get_json() or {}
    r2 = client.get('/api/guild/777/member-card/suggest?q=%40&offset=' + str(mcp.SUGGEST_LIMIT))
finally:
    appmod.bot_instance = bot_prev
    mcp._name_pool = _orig_pool
items = d.get('items') or []
check(r.status_code == 200 and d.get('success') and len(items) == mcp.SUGGEST_LIMIT,
      f'API: страница №1 полная ({len(items)})')
av_items = [x for x in items if x.get('avatar')]
check(bool(av_items) and av_items[0]['avatar'].startswith('https://cdn.discordapp.com'),
      'API: аватарки подмешаны из кэша бота')
check(any(x.get('bot') for x in items) and any(not x.get('bot') for x in items),
      'API: значок «бот» и обычные участники помечены верно')
off_items = (r2.get_json() or {}).get('items') or []
check(len(off_items) == mcp.SUGGEST_LIMIT and
      {x['user_id'] for x in off_items}.isdisjoint({x['user_id'] for x in items}),
      'API: offset=лимит даёт следующую страницу без пересечений')


print('== 3. Сортировка «начало имени — первым» (node) ==')
NODE = r"""
const fs = require('fs');
global.window = {};
global.document = { createElement: function () { throw new Error('DOM не нужен'); }, addEventListener: function () {} };
eval(fs.readFileSync('ROOTX/web/static/pickers.js', 'utf8'));
const src = [
  { user_id: '1', name: 'зест' },
  { user_id: '2', name: 'мари' },
  { user_id: '3', name: 'промари' },
  { user_id: '4', name: 'Марина' }];
const r = window.pickRankMembers(src, 'мар').map(x => x.user_id).join(',');
const ok = r === '2,4,1,3';
console.log(JSON.stringify({ ok: ok, rank: r }));
""".replace('ROOTX', ROOT)
_tmp_h = tempfile.mkdtemp(prefix='p3_rank_')
hn = os.path.join(_tmp_h, 'h.js')
with open(hn, 'w', encoding='utf-8') as f:
    f.write(NODE)
run = subprocess.run(['node', hn], capture_output=True, text=True, timeout=30)
data = json.loads(run.stdout.strip().splitlines()[-1])
check(bool(data.get('ok')), f"ранжирование «мар»: {data.get('rank')} — нужно 2,4,1,3")


print('== 4. Быстрый suggest на огромном пуле ==')
huge_pool = {str(10**17 + i): f'Пользователь оса {i}' for i in range(5000)}
mcp._name_pool = lambda gid: huge_pool
try:
    t0 = time.time()
    res = mcp.suggest('777', 'оса 4999')
    dt = time.time() - t0
finally:
    mcp._name_pool = _orig_pool
check(res and res[0]['name'].endswith('4999'), 'точечный поиск среди 5000 находит нужного')
check(dt < 0.15, f'suggest(5000) за {dt * 1000:.0f} мс (<150 мс)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
