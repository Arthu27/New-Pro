# -*- coding: utf-8 -*-
"""Баннеры по HTTPS + стикеры на диске — картинки не «отлетают».
Запуск: python3 tests/test_menu_images_online.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_img_')
# работаем в корне репо, но пишем public banners в tmp через monkeypatch
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== 1. Стикер-пак ==')
from services import menu_banners as MB  # noqa: E402

pack_dir = os.path.join(_TMP, 'stickers')
paths = MB.ensure_sticker_pack(pack_dir, force=True)
check(len(paths) >= 8, f'стикеров записано: {len(paths)}')
check(all(os.path.isfile(p) and os.path.getsize(p) > 100 for p in paths),
      'все PNG непустые')

print('== 2. Public banner URL ==')
# пишем в tmp static
MB.PUBLIC_MENU_DIR = os.path.join(_TMP, 'static', 'menu')
os.environ['PANEL_PUBLIC_URL'] = 'https://hakumods.xyz'
out = MB.ensure_public_banners(('modpanel', 'appeals'))
check('modpanel' in out and os.path.isfile(out['modpanel']), 'modpanel png')
url = MB.public_banner_url('modpanel')
check(url.startswith('https://hakumods.xyz/static/menu/'), f'url={url}')
check(MB.BANNER_FILE_VER in url, 'версия в имени файла')
check(os.path.isfile(os.path.join(
    MB.PUBLIC_MENU_DIR, MB.banner_filename('modpanel'))),
      'файл лежит в static/menu')

print('== 3. V2 gallery предпочитает HTTPS ==')
from services import v2_layouts as V2  # noqa: E402

media = V2._resolve_banner_media(kind='modpanel')
check(media.startswith('https://'), f'media={media}')
# attachment fallback
media2 = V2._resolve_banner_media(
    banner_url='', banner_filename='x.png', kind='modpanel')
# public_banner_url всё равно выиграет через try
check(media2.startswith('https://') or media2 == 'x.png',
      f'fallback ok: {media2}')

print('== 4. menu_emojis зовёт ensure_sticker_pack ==')
src = open(os.path.join(ROOT, 'services/menu_emojis.py'), encoding='utf-8').read()
check('ensure_sticker_pack' in src, 'emoji sync восстанавливает PNG')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
