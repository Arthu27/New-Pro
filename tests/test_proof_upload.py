# -*- coding: utf-8 -*-
"""Демка в Discord — файл для плеера, не протухающая ссылка."""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services.proof_upload import (  # noqa: E402
    fit_for_discord, upload_budget,
)

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


class G:
    def __init__(self, limit):
        self.filesize_limit = limit


print('== лимит сервера ==')
check(upload_budget(G(25 * 1024 * 1024)) < 25 * 1024 * 1024, 'запас под лимитом')
check(upload_budget(G(0)) >= 512 * 1024, 'пустой лимит — запасной потолок')

print('== файл уже влезает — без перекодирования ==')
blob = b'\x00\x00\x00\x18ftypmp42' + b'v' * 40
data, name, note = fit_for_discord(blob, 'Happ.mp4', limit=10_000, kind='video')
check(data == blob and name == 'Happ.mp4' and note == '', 'mp4 как есть')

print('== тяжёлое видео сжимается в mp4 под лимит ==')
with tempfile.TemporaryDirectory() as folder:
    src = os.path.join(folder, 'big.mp4')
    subprocess.run(
        [
            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
            '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=25',
            '-f', 'lavfi', '-i', 'sine=frequency=440',
            '-t', '3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-b:v', '4M', '-c:a', 'aac', src,
        ],
        check=True,
    )
    raw = open(src, 'rb').read()
check(len(raw) > 80_000, f'исходник тяжёлый ({len(raw)} б)')
out, out_name, note = fit_for_discord(raw, 'Happ_2026.mp4', limit=40_000, kind='video')
check(bool(out) and len(out) <= 40_000, f'влезло в лимит ({len(out)} б)')
check(out_name.endswith('.mp4'), f'имя mp4 ({out_name})')
check(note == '', 'без пометки-ссылки')
check(out[4:8] == b'ftyp', 'это mp4')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
