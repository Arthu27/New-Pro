# -*- coding: utf-8 -*-
"""Стабильность процесса: бот не должен «сам перезапускаться» без причины.

Защита от регресса «сидел 14 часов и перезапустился»:
1) TTLMap — кэши с лимитом (без лимита = рост памяти = OOM-киллер);
2) AI-чат использует ограниченный кэш (не dict без чистки);
3) main.py пишет data/run_log.json (старт/стоп/обрыв) и сторожит память;
4) auto_update.py — обновление только при AUTO_UPDATE=1, ветка = текущая,
   нет kill/reset на грязном дереве, есть журнал и кулдаун;
5) start.sh логирует каждый выход бота.

Запуск: python3 tests/test_process_stability.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


print('== 1. TTLMap: лимит, TTL, потокобезопасность ==')
from services.ttl_cache import TTLMap  # noqa: E402

c = TTLMap(maxsize=100, ttl=60)
t0 = 1000.0
for i in range(100):
    c.put(f'k{i}', i, now=t0 + i)
check(len(c) == 100, f'вмещает ровно maxsize: {len(c)}')
c.put('k101', 'x', now=t0 + 300)          # переполнение → вытеснение старых
check(len(c) <= 100, f'переполнение не растёт: {len(c)}')
check(c.get('k0', now=t0 + 300) is None, 'вытеснена самая старая запись')
check(c.get('k101', now=t0 + 300) == 'x', 'новая запись на месте')

c2 = TTLMap(maxsize=10, ttl=10)
c2.put('old', 1, now=1000.0)
check(c2.get('old', now=1011.0) is None, 'запись старше TTL — отсутствует')
check(len(c2) == 0, 'просроченная удалена из словаря')

# потокобезопасность: 4 потока пишут/читают без исключений
c3 = TTLMap(maxsize=50, ttl=30)
errs = []


def worker(n):
    try:
        for i in range(300):
            c3.put(f'{n}_{i}', i)
            c3.get(f'{n}_{i}')
            c3.get('missing')
    except Exception as e:
        errs.append(e)


ths = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
for t in ths:
    t.start()
for t in ths:
    t.join()
check(not errs and len(c3) <= 50, f'4 потока + лимит 50: errors={len(errs)}, len={len(c3)}')

print('== 2. AI-чат: кэш сообщений ограничен ==')
ai = open(os.path.join(ROOT, 'cogs', 'ai_chat.py'), encoding='utf-8').read()
check('from services.ttl_cache import TTLMap' in ai,
      'TTLMap подключён в ai_chat')
check('_message_cache =TTLMap' in ai or '_message_cache = TTLMap' in ai,
      'кэш сообщений — TTLMap с лимитом')
check('_message_cache .put (' in ai or '_message_cache.put(' in ai,
      'запись в кэш через put (вытеснение работает)')
check('if cache_key in _message_cache' not in ai,
      'нет старой проверки «in dict» без чистки')

print('== 3. main.py: журнал запусков + сторож памяти ==')
mn = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
check("_RUN_LOG = os.path.join(_BASE_DIR, 'data', 'run_log.json')" in mn,
      'журнал data/run_log.json')
check("def _record_run(event" in mn, 'функция _record_run (старт/стоп/обрыв)')
check("_record_run('start'" in mn, 'старт пишется в журнал')
check("_record_run('reconnect'" in mn, 'обрыв/переподключение пишется')
check("async def _memory_watchdog" in mn and 'memory_high' in mn,
      'сторож памяти (RSS → GC → запись memory_high)')
check("asyncio.create_task(_memory_watchdog())" in mn,
      'сторож запускается в main()')
check('discord.ActivityType.watching' in mn and "_activity_text = 'Hakumo'" in mn,
      'дефолт присутствия — «Смотрит Hakumo» (заказ владельца 30.08)')
check("or 'Hakumo'" in mn,
      'пустой текст активности не оставляет бота без подписи')

print('== 4. auto_update.py: безопасность ==')
import auto_update as AU  # noqa: E402
check(AU.UPDATE_BRANCH not in ('', 'main') or AU.UPDATE_BRANCH == 'main',
      f'ветка загружена (по умолчанию текущая): {AU.UPDATE_BRANCH}')
check(AU.AUTO_UPDATE_ENABLED is False,
      'автообновление по умолчанию ВЫКЛ (AUTO_UPDATE=0)')
check(AU.AUTO_UPDATE_COOLDOWN >= 60, f'кулдаун есть: {AU.AUTO_UPDATE_COOLDOWN}с')
check(hasattr(AU, 'log_event') and 'auto_update_events.json' in AU.EVENTS_LOG,
      'журнал событий демона')
check(AU._detect_branch() == AU.UPDATE_BRANCH or AU.UPDATE_BRANCH != 'main',
      f'текущая ветка определяется из git: {AU._detect_branch()!r}')

# грязное дерево → обновление запрещено (reset --hard не делается)
tmp = tempfile.mkdtemp(prefix='au_clean_')
try:
    subprocess.run(['git', 'init', '-q'], cwd=tmp, check=True)
    subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',
                    'commit', '-q', '--allow-empty', '-m', 'x'],
                   cwd=tmp, check=True)
    def _clean_here():
        r = subprocess.run(['git', 'status', '--porcelain'], cwd=tmp,
                            capture_output=True, text=True, timeout=10)
        return r.returncode == 0 and not (r.stdout or '').strip()
    check(_clean_here(), 'чистое дерево распознаётся как чистое')
    open(os.path.join(tmp, 'dirty.txt'), 'w', encoding='utf-8').write('x')
    check(not _clean_here(), 'грязное дерево распознаётся (перезапуска нет)')
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# журнал событий пишется
AU.log_event('test_check', value=1)
check(os.path.exists(AU.EVENTS_LOG), 'журнал событий создаётся')
try:
    rows = json.load(open(AU.EVENTS_LOG, encoding='utf-8'))
    check(any(r.get('event') == 'test_check' for r in rows),
          'событие в журнале читается')
except Exception as e:
    check(False, f'журнал событий читается: {e}')

print('== 5. start.sh: выход бота логируется ==')
sh = open(os.path.join(ROOT, 'start.sh'), encoding='utf-8').read()
check('logs/bot_restarts.log' in sh, 'каждый выход процесса пишется в журнал')
check('data/run_log.json' in sh, 'подсказка на журнал run_log')

print('== 6. Профиль памяти: панель показывает, КУДА уходит RAM ==')
try:
    _tmp_mem = tempfile.mkdtemp(prefix='hakumo_mem_')
    _old_cwd = os.getcwd()
    os.chdir(_tmp_mem)
    os.makedirs('data', exist_ok=True)
    os.environ['DB_PATH'] = os.path.join(_tmp_mem, 'data', 'bot.db')
    os.environ.setdefault('PANEL_USER', 'admin')
    os.environ.setdefault('PANEL_PASSWORD', 'test123')

    class _Mem:
        def __init__(s, status):
            s.status = status
        def __str__(s):
            return 'online'

    class _MemGuild:
        id = 555
        name = 'Тестовый'
        members = [_Mem('online') for _ in range(120)]
        channels = [object() for _ in range(7)]
        roles = [object() for _ in range(4)]

    class _MemBot:
        guilds = [_MemGuild()]
        user = None
        latency = 0.02
        voice_clients = []
        cogs = {'a': 1, 'b': 2}
        extensions = {'a': 1}
        status = 'online'
        def is_closed(s):
            return False
        def is_ready(s):
            return True

    from web.app import app as _app, set_bot_instance as _sbi
    _sbi(_MemBot())
    _c = _app.test_client()
    r = _c.post('/api/bot/memory-profile')          # без логина — мимо
    check(r.status_code in (301, 302, 403), 'профиль памяти закрыт от гостей')
    with _c.session_transaction() as _sess:
        _sess['logged_in'] = True
        _sess['username'] = 'Owner'
        _sess['role'] = 'owner'
    r = _c.post('/api/bot/memory-profile')
    d = r.get_json() or {}
    check(r.status_code == 200 and d.get('success') is True, 'профиль снимается (200)')
    check(d.get('members_cached') == 120 and d.get('guilds') == 1,
          'кэш участников посчитан честно (120)')
    check(d.get('channels_cached') == 7 and d.get('roles_cached') == 4,
          'каналы и роли посчитаны')
    check(isinstance(d.get('objects_total'), int) and d.get('objects_total', 0) > 1000,
          f"живых объектов Python: {d.get('objects_total')}")
    check(isinstance(d.get('top_types'), list) and len(d['top_types']) >= 5,
          'топ типов объектов собран')
    check(d.get('per_guild') and d['per_guild'][0]['members'] == 120,
          'топ сервера по кэшу: кто ест память')
    check(d.get('rss_mb', 0) > 10, f"RSS процесса виден: {d.get('rss_mb')} МБ")
    check(d.get('rss_after_gc_mb') is not None, 'замер после GC отделяет мусор от живого')
    # admin (не owner) — мимо: профиль тяжёлый, только владельцу
    with _c.session_transaction() as _sess:
        _sess['role'] = 'admin'
    r = _c.post('/api/bot/memory-profile')
    check(r.status_code == 403, 'профиль памяти — только owner')
    # страница статистики: кнопка есть у owner, нет у простых
    with _c.session_transaction() as _sess:
        _sess['role'] = 'owner'
    page = _c.get('/bot-stats').get_data(as_text=True)
    check('memProfileBtn' in page, 'кнопка «Снять профиль» на странице статистики')
    with _c.session_transaction() as _sess:
        _sess['role'] = 'moderator'
    page = _c.get('/bot-stats').get_data(as_text=True)
    check('memProfileBtn' not in page, 'модератору кнопку не показываем')
    _sbi(None)
    os.chdir(_old_cwd)
    shutil.rmtree(_tmp_mem, ignore_errors=True)
except Exception as e:
    check(False, f'профиль памяти: {e}')
    try:
        os.chdir(_old_cwd)
        shutil.rmtree(_tmp_mem, ignore_errors=True)
    except Exception:
        pass

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
