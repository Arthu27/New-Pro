# -*- coding: utf-8 -*-
"""Самообновление /update (заказ, пункт 5.6).

- verify_zip: валидный архив требует опорные файлы (main.py, config.py,
  web/app.py) и целостность; битый не пропускается.
- verify_python: любой .py с синтаксической ошибкой блокирует раскатку.
- stage_update: раскатывает файлы поверх копии, БЕРЕЖНО обходя data/,
  logs/, .env, .git и т.п.; пишет маркер data/update_pending.json
  (sha/ветка/канал отчёта).
- download_zip: ошибка HTTP — вежливый отказ; переразмерный поток — стоп.
- Команда: не-владелец получает вежливый отказ; владелец проходит весь
  цикл без ручного скачивания (замена файлов + os.execv перезапуск).
- announce_pending: после рестарта бот отчитывается в канал из маркера и
  снимает его (повторно не дублирует).

Запуск: python3 tests/test_self_update.py
"""
import asyncio
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
from types import SimpleNamespace as NS
from unittest.mock import patch

_TMP = tempfile.mkdtemp(prefix='hakumo_update_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['OWNER_ID'] = '4242'

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


from services import self_update as SU  # noqa: E402

GOOD_FILES = {
    'bot-main/main.py': "print('hi')\n",
    'bot-main/config.py': "TOKEN = ''\n",
    'bot-main/web/app.py': "x = 1\n",
    'bot-main/cogs/alpha.py': "NEW = True\n",
    'bot-main/data/state.json': "IGNORED_BY_PRESERVE\n",
    'bot-main/.env': "TOKEN=hacker\n",
    'bot-main/logs/old.log': "IGNORED\n",
}


def make_zip(files, path):
    with zipfile.ZipFile(path, 'w') as zf:
        for name, body in files.items():
            zf.writestr(name, body)
    return path


print('== 1. Целостность архива ==')
zip_path = os.path.join(_TMP, 'good.zip')
make_zip(GOOD_FILES, zip_path)
ok, err, meta = SU.verify_zip(zip_path)
check(ok and meta is not None, 'валидный архив проходит verify_zip')
_names, root, rel = meta
check(root == 'bot-main/' and 'cogs/alpha.py' in rel,
      'root каталога и относительные пути определены')

bad_path = os.path.join(_TMP, 'garbage.zip')
with open(bad_path, 'wb') as f:
    f.write(b'not-a-zip-at-all' * 100)
ok, err, _ = SU.verify_zip(bad_path)
check(not ok and 'zip' in err, 'байтовый мусор — «скачался битый архив»')

zip_missing = os.path.join(_TMP, 'missing.zip')
make_zip({'bot-main/main.py': "x=1\n"}, zip_missing)
ok, err, _ = SU.verify_zip(zip_missing)
check(not ok and 'web/app.py' in err, 'без опорных файлов — отказ с пояснением')

zip_broken = os.path.join(_TMP, 'synt.zip')
make_zip(GOOD_FILES | {'bot-main/cogs/broken.py': "def x(:\n"}, zip_broken)
ok, err = SU.verify_python(zip_broken, 'bot-main/')
check(not ok and 'нема' not in err, 'синтаксически битый .py блокирует обновление')
ok, err = SU.verify_python(zip_path, 'bot-main/')
check(ok, 'здоровые .py компилируются — проверка пропускает')

print('== 2. Раскатка поверх копии (бережная) ==')
bot_dir = tempfile.mkdtemp(prefix='hakumo_botdir_')
os.makedirs(os.path.join(bot_dir, 'data'), exist_ok=True)
os.makedirs(os.path.join(bot_dir, 'cogs'), exist_ok=True)
with open(os.path.join(bot_dir, '.env'), 'w') as f:
    f.write('TOKEN=secret\n')
with open(os.path.join(bot_dir, 'data', 'state.json'), 'w') as f:
    f.write('{"important": true}\n')
with open(os.path.join(bot_dir, 'cogs', 'alpha.py'), 'w') as f:
    f.write('OLD = True\n')

ok, err, stats = SU.stage_update(zip_path, bot_dir, 'bot-main/', rel,
                                 channel_id=98765, sha='abc1234', branch='arena/x')
check(ok and stats and stats['copied'] >= 3, 'файлы раскатаны')
with open(os.path.join(bot_dir, 'cogs', 'alpha.py')) as f:
    check('NEW = True' in f.read(), 'старое содержимое заменено новым')
with open(os.path.join(bot_dir, '.env')) as f:
    check('TOKEN=secret' in f.read(), '.env НЕ перезаписан (секреты на месте)')
with open(os.path.join(bot_dir, 'data', 'state.json')) as f:
    check('{"important": true}' in f.read(), 'data/ НЕ тронута (данные на месте)')
check(not os.path.exists(os.path.join(bot_dir, 'logs')), 'logs/ из архива не появилась')

pen = SU.peek_pending(bot_dir)
check(pen and pen['sha'] == 'abc1234' and pen['channel_id'] == 98765,
      'маркер ожидающего подтверждения записан (sha + канал)')

print('== 3. Скачивание: ошибки сети аккуратны ==')
class _FakeResp:
    def __init__(self, status=200, chunks=()):
        self.status_code = status
        self._chunks = list(chunks)
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def iter_content(self, chunk_size=0):
        return iter(self._chunks)

import requests  # noqa: E402

with patch.object(requests, 'get', lambda *a, **k: _FakeResp(status=404)):
    ok, err, _ = SU.download_zip(_TMP)
check(not ok and '404' in err, '404 от GitHub — вежливая ошибка, не traceback')
with patch.object(requests, 'get', lambda *a, **k: _FakeResp(chunks=[b'x' * (SU._MAX_ZIP_BYTES + 1)])):
    ok, err, _ = SU.download_zip(_TMP)
check(not ok and 'большой' in err, 'переразмерный поток обрезается с отказом')

print('== 4. Команда /update: полный цикл за один вызов ==')
import cogs.diagnostics as DIAG  # noqa: E402


class _Resp:
    def __init__(self):
        self.deferred = False
        self.first = []
    async def defer(self, ephemeral=False):
        self.deferred = True


class _Follow:
    def __init__(self):
        self.sent = []
        self.edited = []
    async def send(self, content=None, wait=False):
        self.sent.append(content)
        return NS(id=555)
    async def edit_message(self, message_id=None, content=None):
        self.edited.append((message_id, content))


async def _run():
    # ── не-владелец: вежливо
    cog = DIAG.Diagnostics.__new__(DIAG.Diagnostics)
    fol = _Follow()
    sent = []

    class _R2:
        async def send_message(self, content=None, ephemeral=False):
            sent.append((content, ephemeral))
    inter = NS(user=NS(id=1), response=_R2(), followup=fol, channel_id=98765)
    await DIAG.Diagnostics.update_cmd.callback(cog, inter)
    check(sent and 'только для владельца' in sent[0][0] and sent[0][1],
          'не-владелец — вежливый эфемерный отказ')

    # ── владелец: весь конвейер автоматом
    resp = _Resp()
    fol = _Follow()
    inter = NS(user=NS(id=4242), response=resp, followup=fol, channel_id=98765)
    exec_called = []
    sleeps = []
    stage_calls = []

    # КРИТИЧНО: реальный stage_update НИКОГДА не должен трогать репозиторий —
    # оборачиваем: раскатку редиректим на tmp-копию, аргументы запоминаем.
    real_stage = SU.stage_update

    def _safe_stage(zip_p, bd, root_, rel_, channel_id=0, sha='', branch=''):
        stage_calls.append({'bot_dir': bd, 'channel_id': channel_id,
                            'sha': sha, 'branch': branch})
        return real_stage(zip_p, bot_dir, root_, rel_,
                          channel_id=channel_id, sha=sha, branch=branch)

    async def _fast_sleep(x):
        sleeps.append(x)
    real_dl = SU.download_zip
    try:
        with patch.object(SU, 'download_zip', lambda d: (True, None, zip_path)), \
             patch.object(SU, 'stage_update', _safe_stage), \
             patch.object(SU, 'remote_sha', lambda: 'abc1234'), \
             patch.object(os, 'execv', lambda *a: exec_called.append(a)), \
             patch.object(DIAG.asyncio, 'sleep', _fast_sleep):
            await DIAG.Diagnostics.update_cmd.callback(cog, inter)
    finally:
        SU.download_zip = real_dl
    check(resp.deferred, 'команда сразу подтверждает приём (defer) — без «не отвечает»')
    check(exec_called, 'после успешной раскатки — реальный перезапуск через execv')
    check(exec_called and exec_called[0][0] == sys.executable
          and exec_called[0][1][0] == sys.executable,
          'перезапуск тем же интерпретатором с теми же аргументами')
    tail = fol.edited[-1][1] if fol.edited else ''
    check('Перезапускаюсь' in tail and 'файлов' in tail,
          'финальное сообщение: заменено файлов + перезапуск (без техдеталей)')
    check(stage_calls and stage_calls[0]['channel_id'] == 98765
          and stage_calls[0]['sha'] == 'abc1234',
          'канал отчёта и sha доходят до маркера из команды')
    pen2 = SU.peek_pending(bot_dir)
    check(pen2 is not None and pen2['channel_id'] == 98765,
          'маркер ожидания записан (его прочитает on_ready после рестарта)')

    # ошибка скачивания — цикл останавливается на первом шаге
    fol = _Follow()
    resp2 = _Resp()
    inter = NS(user=NS(id=4242), response=resp2, followup=fol, channel_id=98765)
    with patch.object(SU, 'download_zip', lambda d: (False, 'сеть умерла', None)):
        await DIAG.Diagnostics.update_cmd.callback(cog, inter)
    check(fol.edited and 'Не вышло скачать' in fol.edited[0][1]
          and 'Ничего не трогал' in fol.edited[0][1],
          'сеть умерла — честный отказ «ничего не трогал»')
    with open(os.path.join(bot_dir, 'cogs', 'alpha.py')) as f:
        check('NEW = True' in f.read(), 'при отказе рабочие файлы нетронуты')

asyncio.run(_run())

print('== 5. Отчёт после рестарта ==')
async def _announce():
    fake_bot = NS()
    got = []
    fake_bot.get_channel = lambda cid: NS(send=lambda text: got.append(text) or asyncio.sleep(0))
    class _Ch:
        async def send(self, text):
            got.append(text)
    fake_bot.get_channel = lambda cid: _Ch()
    fake_bot.fetch_channel = None
    ok = await SU.announce_pending(fake_bot, bot_dir)
    check(ok and got and 'Обновление завершено' in got[0] and 'abc1234'[:7] in got[0],
          'после рестарта отчёт ушёл в канал вызова /update')
    ok2 = await SU.announce_pending(fake_bot, bot_dir)
    check(ok2 is False and SU.peek_pending(bot_dir) is None,
          'маркер снят — повторного приветствия не будет')
asyncio.run(_announce())

print('== 6. Интеграция: команда зарегистрирована ==')
import slash_budget  # noqa: E402
check('update' in slash_budget.KEEP_SLASH, "update в KEEP_SLASH (видно в меню)")
main_src = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
check('announce_pending' in main_src, 'main.py отчитывается после рестарта из /update')
diag_src = open(os.path.join(ROOT, 'cogs/diagnostics.py'), encoding='utf-8').read()
check('name ="update"' in diag_src or "name='update'" in diag_src
      or 'name ="update"' in diag_src.replace("='", ' ="'),
      '/update — слеш-команда диагностики')
check('os .execv' in diag_src, 'перезапуск через os.execv (Windows-совместимый)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
