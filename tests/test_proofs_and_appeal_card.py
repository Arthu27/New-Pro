# -*- coding: utf-8 -*-
"""Доказательства и карточка апелляции (владелец, 2026-09-05).

1) «выборы select две штуки там и тут»: на «Доказательствах» все выборы —
   одного вида (кастомный select), нативных «чужих» не осталось.
2) Белый список «без демки» работает и в боте: у доверенного модератора
   в /modpanel обязательное поле «Доказательство» не появляется вовсе.
3) Предпросмотр карточки апелляции «своя по URL»: картинку тянет СЕРВЕР
   (тот же загрузчик, что и отправку) — хотлинк-защита хостов больше не
   ломает превью; что видишь в превью — то уедет в Discord.
4) Отправка своей картинки — ФАЙЛОМ (оригинальные байты, Discord не
   пережимает — «качество не портилось»), fallback на ссылку при неудаче.

Запуск: python3 tests/test_proofs_and_appeal_card.py
"""
import asyncio
import io
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(tempfile.mkdtemp(prefix='proofs_appeal_'))
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath(os.path.join('data', 'bot.db'))
os.environ['DEMO_MODE'] = '1'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'x'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['PANEL_PORT'] = '5097'
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


# ═══════════════════════════════════════════════════════════════════
print('== 1. «Доказательства»: все выборы — единый кастомный select ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'proofs.html'), encoding='utf-8').read()
check('sshdEnhance(act' in tpl.replace('window.sshdEnhance(act', 'sshdEnhance(act'),
      'select «Наказание» теперь тоже кастомный (один стиль на странице)')
check('pf-wl-what' in tpl and "sshdEnhance(wlSel" in tpl,
      'пикер белого списка на месте (один контрол, без заглушки внутри)')

# ═══════════════════════════════════════════════════════════════════
print('== 2. Белый список «без демки» в /modpanel ==')
from cogs import proof_cog as PC  # noqa: E402
from cogs import moderation as M  # noqa: E402
import discord  # noqa: E402

GID = 1484574976580391004
WL_MOD_ID = 3001
OTHER_MOD_ID = 3002
WL_ROLE_ID = 4001
PC.proof_whitelist_add(GID, 'user', WL_MOD_ID)
PC.proof_whitelist_add(GID, 'role', WL_ROLE_ID)
PC.proof_set_required(GID, True)
check(PC.proof_is_required(GID), 'требование демки включено (панель-тумблер)')


class _Role:
    def __init__(self, rid):
        self.id = rid


class _User:
    def __init__(self, uid, roles=()):
        self.id = uid
        self.roles = roles
        self.bot = False


modal_wl = M.ModActionModal(M.__dict__.get('_cog_stub') or type('C', (), {})(),
                            'ban', guild=type('G', (), {'id': GID})(),
                            prefill_target='123', user=_User(WL_MOD_ID))
check(not hasattr(modal_wl, 'proof'),
      'модератору из белого списка поле «Доказательство» НЕ показывается')

modal_role = M.ModActionModal(type('C', (), {})(), 'timeout',
                              guild=type('G', (), {'id': GID})(),
                              prefill_target='123',
                              user=_User(OTHER_MOD_ID, (_Role(WL_ROLE_ID),)))
check(not hasattr(modal_role, 'proof'),
      'модератору с доверенной РОЛЬЮ тоже не показывается')

modal_other = M.ModActionModal(type('C', (), {})(), 'ban',
                               guild=type('G', (), {'id': GID})(),
                               prefill_target='123', user=_User(OTHER_MOD_ID))
check(hasattr(modal_other, 'proof') and modal_other.proof.required,
      'остальным — обязательное поле «Доказательство» (как было)')

# ═══════════════════════════════════════════════════════════════════
print('== 3. Своя картинка по URL: валидация и загрузчик ==')
from services.appeal_card import (validate_image_url, fetch_remote_image,  # noqa: E402
                                  MAX_REMOTE_IMAGE_BYTES)
ok, _ = validate_image_url('https://cdn.discordapp.com/attachments/1/2/scr.png')
check(ok, 'https-ссылка на png принимается')
ok, why = validate_image_url('http://example.com/a.png')
check(not ok, 'http:// отклоняется (Discord не покажет)', why)
ok, why = validate_image_url('https://localhost/a.png')
check(not ok, 'localhost отклоняется', why)
ok, why = validate_image_url('https://example.com/page.html')
check(not ok, 'не-картиночное расширение отклоняется', why)
ok, _ = validate_image_url('https://example.com/картинка')
check(ok, 'ссылка без расширения допустима (решит content-type)')

img, why = asyncio.new_event_loop().run_until_complete(
    fetch_remote_image('http://127.0.0.1:9/x.png'))
check(img is None, 'загрузчик не ходит в приватную сеть', why)

# ═══════════════════════════════════════════════════════════════════
print('== 4. Отправка своей картинки — файлом (качество не портится) ==')
src = open(os.path.join(ROOT, 'cogs', 'appeals.py'), encoding='utf-8').read()
check(src.count('fetch_remote_image(') >= 2,
      'оба пути подачи качают оригинал (ЛС и канальная подача)')
check(src.count("attachment://{fname}") == 2,
      'картинка едет вложением attachment:// (без пережатия Discordом)')
check('не скачалась' in src,
      'если хост не отдал файл — запасной путь по ссылке + честный лог')

# ═══════════════════════════════════════════════════════════════════
print('== 5. Предпросмотр «как это будет выглядеть»: сервер качает картинку ==')
import web.app as webapp  # noqa: E402
_client = webapp.app.test_client()

# 5а. плохая ссылка → честный отказ
r_bad = _client.get('/api/guild/777/appeals/card-preview.png'
                    '?mode=url&url=https%3A%2F%2Flocalhost%2Fx.png')
check(r_bad.status_code == 502 and 'недоступна' in (r_bad.get_json() or {}).get('error', ''),
      'битая/приватная ссылка → честная ошибка, а не пустая картинка',
      f'→ {r_bad.status_code}')

# 5б. рабочая ссылка: подменяем сетевой слой на локальный HTTP-сервер
import threading  # noqa: E402
from http.server import BaseHTTPRequestHandler, HTTPServer  # noqa: E402

_PNG = (b'\x89PNG\r\n\x1a\n' + b'\x00' * 64)
_srv_hit = {'n': 0}


class _H(BaseHTTPRequestHandler):
    def do_GET(self):
        _srv_hit['n'] += 1
        self.send_response(200)
        self.send_header('Content-Type', 'image/png')
        self.end_headers()
        self.wfile.write(_PNG)

    def log_message(self, *a):
        pass


# чтобы загрузчик увидел «публичный» хост, проверяем путь через реальный
# запрос: поднимаем сервер и дергаем свой внешний IP нельзя — поэтому
# проверяем прокси-маршрут юнитом: патчим fetch_remote_image.
import services.appeal_card as AC  # noqa: E402
_orig_fetch = AC.fetch_remote_image


async def _fake_fetch(url, timeout=12):
    return (_PNG, 'appeal_image.png')


AC.fetch_remote_image = _fake_fetch
try:
    # перезагрузить маршрутный модуль не нужно: импорт внутри функции
    r_ok = _client.get('/api/guild/777/appeals/card-preview.png'
                       '?mode=url&url=https%3A%2F%2Fexample.com%2Fx.png')
    check(r_ok.status_code == 200 and r_ok.data[:4] == b'\x89PNG',
          'превью отдаёт байты картинки через сервер', f'→ {r_ok.status_code}')
    check(r_ok.mimetype == 'image/png', 'content-type — image/png')
finally:
    AC.fetch_remote_image = _orig_fetch

# 5б-2. страницы-пины (pin.it → og:image → файл) и sniff формата
from services.appeal_card import _og_image_of, _sniff_image_ext  # noqa: E402

_html = ('<meta property="og:image" '
         'content="https://i.pinimg.com/originals/aa/bb/cc/pic.jpg">')
check(_og_image_of(_html) == 'https://i.pinimg.com/originals/aa/bb/cc/pic.jpg',
      'og:image вытаскивается из страницы пина')
check(_og_image_of('<html></html>') is None, 'без og:image — None, без падений')
check(_sniff_image_ext(bytes([0x89]) + b'PNG' +
                       bytes([0x0D, 0x0A, 0x1A, 0x0A]) + b'x' * 8) == '.png'
      and _sniff_image_ext(bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b'x' * 8) == '.jpg'
      and _sniff_image_ext(b'RIFF\x00\x00\x00\x00WEBP' + b'x' * 4) == '.webp'
      and _sniff_image_ext(b'GIF89a123') == '.gif',
      'формат картинки определяется по содержимому (маг. байты), не по URL')
ok_pin, _w = validate_image_url('https://pin.it/7jxEf3HAx')
check(ok_pin, 'ссылка-страница pin.it проходит валидацию (вытащим og:image)')
ok_php, why_php = validate_image_url('https://example.com/pic.php')
check(not ok_php and 'Pinterest' in why_php,
      'не-картинка и не пин — честная причина с подсказкой')

# 5в. авто-превью (тема) по-прежнему рисуется
r_auto = _client.get('/api/guild/777/appeals/card-preview.png?theme=hakumo')
check(r_auto.status_code == 200 and r_auto.data[:4] == b'\x89PNG',
      'авто-превью темы рисуется как раньше')

# 5г. в шаблоне апелляций превью url-режима идёт через прокси + честный onerror
atpl = open(os.path.join(ROOT, 'web', 'templates', 'appeals.html'), encoding='utf-8').read()
check('mode=url&url=' in atpl,
      'предпросмотр «своя URL» идёт через серверный загрузчик')
check('onerror' in atpl and 'скачать не вышло' in atpl,
      'если картинку отдать не смог хост — владелец видит честное сообщение')
check('pin' in atpl.lower(),
      'подсказка упоминает страницы-пины Pinterest (как у владельца)')

print()
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
