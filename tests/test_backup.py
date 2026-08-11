# -*- coding: utf-8 -*-
"""Тесты резервного копирования: services/backup.py + cogs/backup_cog.py + панель.

Запуск: python3 tests/test_backup.py
"""
import asyncio
import json
import os
import sys
import tempfile
import zipfile

# временная рабочая директория — data/, backups/ не мусорят в репо
_TMP = tempfile.mkdtemp(prefix='aether_backup_test_')
os.chdir(_TMP)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import backup as bk  # noqa: E402

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


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── подготовка data/ ────────────────────────────────────────────────────
os.makedirs('data/sub', exist_ok=True)
with open('data/x.json', 'w') as f:
    json.dump({'a': 1}, f)
with open('data/sub/inner.json', 'w') as f:
    json.dump({'b': 2}, f)
# «секреты», которые НЕ должны попасть в архив
for secret in ('panel_credentials.json', 'panel_credentials.txt',
               'flask_secret.key', 'web_session_abcdef'):
    with open(f'data/{secret}', 'w') as f:
        f.write('SECRET')

# ═══ 1. СЕРВИС: создание архива ═══════════════════════════════════════════
print('== services/backup: create_backup ==')
info = bk.create_backup(reason='тест', by='tester')
check(bool(bk.BACKUP_NAME_RE.match(info['name'])), 'имя архива соответствует паттерну')
check(os.path.isfile(os.path.join('backups', info['name'])), 'архив лежит в backups/')
check(info['files'] == 2, f'упакованы 2 обычных файла (есть {info["files"]})')
check(info['skipped'] >= 4, f'секреты пропущены (skipped={info["skipped"]})')
check(info['size'] > 0 and info['source_bytes'] > 0, 'размеры посчитаны')

with zipfile.ZipFile(os.path.join('backups', info['name'])) as zf:
    names = set(zf.namelist())
    manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
check('data/x.json' in names and 'data/sub/inner.json' in names,
      'внутри есть вложенные файлы с префиксом data/')
check('manifest.json' in names, 'внутри есть manifest.json')
check(not any('panel_credentials' in n or 'flask_secret' in n or 'web_session' in n
              for n in names), 'ни одного секрета в архиве')
check(manifest.get('reason') == 'тест' and manifest.get('by') == 'tester',
      'manifest хранит причину и автора')

# второй архив в ту же секунду — уникальное имя
info2 = bk.create_backup(reason='тест-2')
check(info2['name'] != info['name'], 'два архива в ту же секунду — разные имена')

# отсутствующая data/ → FileNotFoundError и никаких .part-обломков
try:
    bk.create_backup(data_dir='no_such_dir', backup_dir='backups')
    check(False, 'create_backup без data/ должен кидать FileNotFoundError')
except FileNotFoundError:
    check(not [f for f in os.listdir('backups') if f.endswith('.part')],
          'create_backup без data/: FileNotFoundError, .part-обломков нет')

# ═══ 2. СЕРВИС: список, ротация, resolve ═════════════════════════════════
print('== services/backup: list/rotate/resolve ==')
# чужеродный файл с похожим именем не показываем и не удаляем
with open('backups/backup_evil.zip', 'w') as f:
    f.write('not ours')

# делаем различимый порядок по времени
all_names = [i['name'] for i in bk.list_backups()]
for n, ts in zip(all_names, (1_700_000_100, 1_700_000_200)):
    os.utime(os.path.join('backups', n), (ts, ts))
items = bk.list_backups()
check(len(items) == 2, f'list_backups: 2 наших архива, чужой проигнорирован (есть {len(items)})')
check(items[0]['mtime'] >= items[1]['mtime'], 'list_backups: свежие первые')
check(all('size_h' in i for i in items), 'list_backups: human-readable размер прилагается')

# ротация: keep=1 → остаётся самый свежий, чужой файл не тронут
removed = bk.rotate_backups(keep=1)
check(len(removed) == 1 and len(bk.list_backups()) == 1, 'rotate: keep=1 оставил ровно 1')
check(os.path.exists('backups/backup_evil.zip'), 'rotate: чужой backup_evil.zip не тронут')
check(removed[0] == items[1]['name'], 'rotate: удалён именно самый старый')

# resolve: валидный/отсутствующий/traversal/мусор
good = bk.list_backups()[0]['name']
check(bk.resolve_backup(good, 'backups') is not None, 'resolve: существующий архив → путь')
check(bk.resolve_backup('backup_20200101_000000_aaaa.zip') is None,
      'resolve: валидное имя, но файла нет → None')
check(bk.resolve_backup('../config.py') is None, 'resolve: path traversal → None')
check(bk.resolve_backup('..%2f..%2fconfig.py') is None, 'resolve: url-encoded traversal → None')
check(bk.resolve_backup('backups/../../x.zip') is None, 'resolve: вложенный traversal → None')
check(bk.resolve_backup('../../etc' + chr(47) + 'passwd.zip') is None, 'resolve: abs traversal → None')
check(bk.resolve_backup(None) is None and bk.resolve_backup('') is None,
      'resolve: None/пустое имя → None')
check(bk.resolve_backup(good, 'no_such_backup_dir') is None,
      'resolve: в несуществующей папке → None')

check(bk.format_size(512) == '512 Б', 'format_size: байты')
check(bk.format_size(2048) == '2.0 КБ', 'format_size: килобайты')
check(bk.format_size(int(1.5 * 1024 * 1024)) == '1.5 МБ', 'format_size: мегабайты')
check(bk.format_size('мусор') == '0 Б', 'format_size: мусор → 0 Б')
check(bk.valid_backup_name(good) and not bk.valid_backup_name('evil.zip'),
      'valid_backup_name: true/false')

# ═══ 3. КОГ: env-конфиг, расписание, run_backup ═══════════════════════════
print('== cogs/backup_cog: конфиг и ядро ==')
os.environ['BACKUP_ENABLED'] = '0'  # чтобы при создании кога не стартовал loop
from cogs import backup_cog as bc  # noqa: E402


class FakeBot:
    guilds = []

    def get_cog(self, name):
        return None


check(bc.backup_enabled() is False, 'BACKUP_ENABLED=0 → выключен')
os.environ['BACKUP_ENABLED'] = '1'
check(bc.backup_enabled() is True, 'BACKUP_ENABLED=1 → включён')
check(bc.backup_hour() == 5, 'час по умолчанию — 05:00')
os.environ['BACKUP_HOUR'] = 'abc'
check(bc.backup_hour() == 5, 'кривой BACKUP_HOUR → дефолт 5')
os.environ['BACKUP_HOUR'] = '99'
check(bc.backup_hour() == 23, 'BACKUP_HOUR=99 → зажат в 23')
os.environ['BACKUP_HOUR'] = '7'
check(bc.backup_hour() == 7, 'BACKUP_HOUR=7')
os.environ['BACKUP_KEEP'] = '0'
check(bc.backup_keep() == 1, 'BACKUP_KEEP=0 → зажат в 1')
os.environ['BACKUP_KEEP'] = '3'
check(bc.backup_keep() == 3, 'BACKUP_KEEP=3')
check(bc.backup_attach() is False, 'BACKUP_ATTACH по умолчанию выключен')
os.environ['BACKUP_ATTACH'] = '1'
check(bc.backup_attach() is True, 'BACKUP_ATTACH=1')
os.environ['BACKUP_ATTACH'] = '0'

os.environ['BACKUP_ENABLED'] = '0'  # конструктор не должен стартовать loop вне Discord
cog = bc.Backup(FakeBot())
check(cog._last_run_date is None, 'ког создался, запусков не было')
check(cog.auto_backup.is_running() is False, 'при BACKUP_ENABLED=0 цикл не стартует')
os.environ['BACKUP_ENABLED'] = '1'

# should_run_now — чистая логика расписания
import datetime as _dt  # noqa: E402
now_run = _dt.datetime(2026, 8, 11, 7, 0)
now_idle = _dt.datetime(2026, 8, 11, 8, 0)
check(cog.should_run_now(now_run) is True, 'в целевой час — пора бэкапить')
check(cog.should_run_now(now_idle) is False, 'в другой час — не пора')
cog.mark_ran(now_run)
check(cog.should_run_now(now_run) is False, 'после mark_ran второй раз в тот же день — не пора')

# run_backup: создаёт и ротирует (бот без гильдий → без Discord-уведомления)
for f in os.listdir('backups'):
    if not f.startswith('backup_evil'):
        os.remove(os.path.join('backups', f))
info_r, removed_r = run(cog.run_backup(reason='тест-ког', by='tests'))
check(os.path.isfile(os.path.join('backups', info_r['name'])), 'run_backup: архив создан')
check(removed_r == [], 'run_backup: ротировать нечего')
check(cog._last_run_ok is True, 'run_backup: флаг успеха выставлен')

# ═══ 4. КОГ: slash-команды ════════════════════════════════════════════════
print('== cogs/backup_cog: /backup ==')


class FakeResp:
    def __init__(self):
        self.deferred = False
        self.sent = []

    async def defer(self, ephemeral=False):
        self.deferred = True

    async def send_message(self, content=None, embed=None, ephemeral=False):
        self.sent.append((content, embed))

    async def send(self, content=None, embed=None, ephemeral=False):  # followup-стиль
        self.sent.append((content, embed))


class FakeUser:
    def __str__(self):
        return 'Admin#0001'


class FakeInter:
    def __init__(self):
        self.user = FakeUser()
        self.response = FakeResp()
        self.followup = FakeResp()


inter = FakeInter()
run(bc.Backup.backup_now.callback(cog, inter))
check(inter.response.deferred, '/backup now: ответ отложен (дефер)')
check(inter.followup.sent and inter.followup.sent[-1][1] is not None,
      '/backup now: прислал эмбед-отчёт')
emb = inter.followup.sent[-1][1]
check('backup_' in (emb.fields[0].value or ''), '/backup now: в отчёте имя архива')

inter2 = FakeInter()
run(bc.Backup.backup_list.callback(cog, inter2))
emb2 = inter2.response.sent[-1][1]
check('backup_' in (emb2.description or ''), '/backup list: перечисляет архивы')
check('Всего' in (emb2.footer.text or ''), '/backup list: футер со статистикой')

inter3 = FakeInter()
run(bc.Backup.backup_status.callback(cog, inter3))
emb3 = inter3.response.sent[-1][1]
check('включён' in (emb3.description or '') and '07:00' in (emb3.description or ''),
      '/backup status: расписание и состояние')
check('Хранилище' in [f.name for f in emb3.fields], '/backup status: поле хранилища')

# ротация через keep=3: делаем ещё 3 ручных (всего станет 5+) → останется 3
for _ in range(3):
    run(cog.run_backup(reason='для ротации'))
items_now = bk.list_backups(bk.BACKUP_DIR_DEFAULT)
check(len(items_now) == 3, f'ротация работает: осталось {len(items_now)} из 6')
check(os.path.exists('backups/backup_evil.zip'), 'чужой файл всё ещё цел после ротаций')

# ═══ 5. ПАНЕЛЬ: страница и API ════════════════════════════════════════════
print('== панель: /backups и /api/backups ==')
from web.app import app as _flask_app, set_bot_instance  # noqa: E402
set_bot_instance(FakeBot())
client = _flask_app.test_client()

r = client.get('/api/backups')
check(r.status_code in (302, 401, 403), f'API без логина закрыто ({r.status_code})')


def login_as(role):
    # discord_id специально НЕ ставим: login_required перечитывал бы роль
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'PanelBackup'
        s['role'] = role


login_as('uye')
r = client.get('/api/backups')
check(r.status_code == 403, f'uye в API бэкапов не пускают ({r.status_code})')
r = client.get('/backups')
check(r.status_code in (302, 403), f'uye на страницу /backups не пускают ({r.status_code})')

login_as('mod')
r = client.get('/api/backups')
check(r.status_code == 403, f'mod тоже мало — бэкапы это admin+ ({r.status_code})')

login_as('admin')
r = client.get('/api/backups')
d = r.get_json()
check(r.status_code == 200 and d.get('success') is True, 'admin: список отдаётся')
check(d['stats']['total'] == 3 and 'keep' in d.get('settings', {}),
      'admin: статистика и настройки в ответе')
check('dir' not in d.get('settings', {}), 'настройки не светят путь на диске')

# создать через панель
r = client.post('/api/backups')
d = r.get_json()
check(d.get('success') is True and bk.resolve_backup(d['item']['name']) is not None,
      'POST: бэкап создан через панель')
# keep=3 → сразу поротировалось до 3
check(len(bk.list_backups()) == 3, 'POST: ротация применена (осталось 3)')
check(d['item']['name'].endswith('.zip') and 'size_h' in d['item'],
      'POST: в ответе имя и human-readable размер')

# скачать
r = client.get('/api/backups/download/' + d['item']['name'])
check(r.status_code == 200 and r.data[:2] == b'PK', 'download: отдаётся настоящий zip')
check('attachment' in (r.headers.get('Content-Disposition') or ''),
      'download: Content-Disposition=attachment')

# скачать несуществующее / мусорное имя
r = client.get('/api/backups/download/backup_20200101_000000_aaaa.zip')
check(r.status_code == 404, 'download: валидное имя без файла → 404')
r = client.get('/api/backups/download/evil.zip')
check(r.status_code == 404, 'download: мусорное имя → 404')
r = client.get('/api/backups/download/..%2F..%2Fconfig.py')
check(r.status_code in (400, 404), f'download: traversal заблокирован ({r.status_code})')
r = client.get('/api/backups/download/%2e%2e%2f%2e%2e%2fconfig.py')
check(r.status_code in (400, 404), f'download: encoded traversal заблокирован ({r.status_code})')

# удалить
victim = bk.list_backups()[-1]['name']
r = client.delete('/api/backups/' + victim)
check(r.get_json().get('success') is True
      and bk.resolve_backup(victim) is None, 'DELETE: архив удалён')
r = client.delete('/api/backups/' + victim)
check(r.status_code == 404, 'DELETE: повторное удаление → 404')
r = client.delete('/api/backups/evil.zip')
check(r.status_code == 400, 'DELETE: мусорное имя → 400')

# страница рендерится
r = client.get('/backups')
page = r.get_data(as_text=True)
check(r.status_code == 200 and 'Разерв' not in page and '/api/backups' in page,
      'страница /backups рендерится и дергает API')

# меню панели знает про страницу
from services.panel_menu import MENU  # noqa: E402
check(any(p['path'] == '/backups'
          for g in MENU for p in g['pages']), 'в меню панели есть пункт «Бэкапы»')

# ─── финал ───────────────────────────────────────────────────────────────
import shutil  # noqa: E402
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
