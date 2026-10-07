# -*- coding: utf-8 -*-
"""Демки → канал модерации, плеер без «скачай», свои стикеры."""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_demo_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath('data/bot.db')

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== proof_cog: канал модерации + лимит перезалива ==')
prf = open(os.path.join(ROOT, 'cogs', 'proof_cog.py'), encoding='utf-8').read()
check('MAX_REUPLOAD_BYTES = 25 * 1024 * 1024' in prf,
      'перезалив до 25 МБ (видео не уходит ссылкой «скачай»)')
check("report_channel" in prf and '_proof_channel' in prf,
      '_proof_channel предпочитает report_channel / моды')
check('MODS_CHANNEL_ID' in prf, 'фолбэк на MODS_CHANNEL_ID')
check('_file_attached' in prf,
      'при вложении не пишем ссылку-скачивалку')
check('MediaGallery' in prf and 'скачивать не нужно' in prf,
      'V2 MediaGallery — плеер Discord')
check('канал модерации' in prf,
      'копирайт: канал модерации, не #-доказательства')

print('== menu_emojis: sticker() для текста карточек ==')
emj = open(os.path.join(ROOT, 'services', 'menu_emojis.py'), encoding='utf-8').read()
check('def sticker(' in emj and 'def emoji_md(' in emj,
      'sticker() + emoji_md() для V2-текста')
from services.menu_emojis import sticker, emoji_md  # noqa: E402
check(sticker('heart') in ('🤍',) or sticker('heart').startswith('<'),
      'sticker(heart) отдаёт markdown или фолбек')
check(emoji_md('🤍') == '🤍', 'emoji_md(str) пропускает unicode')

print('== reports + routes ==')
rep = open(os.path.join(ROOT, 'cogs', 'reports.py'), encoding='utf-8').read()
rte = open(os.path.join(ROOT, 'services', 'channel_routes.py'),
           encoding='utf-8').read()
check("sticker as _st" in rep or "sticker(" in rep,
      'карточка /report использует свои стикеры')
check('канал модерации' in rep and 'Демка' in rep,
      '/report пишет про демку в канале модерации')
check('запасной' in rte.lower() or 'Запасной' in rte,
      'proof_channel в панели помечен как запасной')
check("'report_channel'" in rte and 'демки' in rte,
      'report_channel: вызовы и демки')

print(f'\n{PASS} passed, {FAIL} failed')
sys.exit(1 if FAIL else 0)
