# -*- coding: utf-8 -*-
"""Файл демки, который Discord показывает плеером, а не ссылкой.

Лимит берётся с сервера (guild.filesize_limit). Если ролик тяжелее —
сжимаем в mp4 и вкладываем в сообщение канала доказательств.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

UPLOAD_MARGIN = 256 * 1024
FALLBACK_LIMIT = 10 * 1024 * 1024
# Исходник тяжелее этого не гоняем через ffmpeg: слишком долго для бота.
SOURCE_MAX = 120 * 1024 * 1024


def upload_budget(guild) -> int:
    """Сколько байт Discord примет в одно вложение на этом сервере."""
    raw = 0
    try:
        raw = int(getattr(guild, 'filesize_limit', 0) or 0)
    except Exception:
        raw = 0
    if raw < 512 * 1024:
        raw = FALLBACK_LIMIT
    return max(512 * 1024, raw - UPLOAD_MARGIN)


def _safe_stem(filename: str) -> str:
    base = os.path.basename(filename or '').strip()
    stem = os.path.splitext(base)[0]
    cleaned = ''.join(ch if ch.isalnum() or ch in '._- ' else '_' for ch in stem)
    cleaned = ' '.join(cleaned.split()).strip(' ._')
    return (cleaned or 'proof')[:80]


def _which(name: str) -> str:
    return shutil.which(name) or ''


def _probe_duration(path: str) -> float:
    ffprobe = _which('ffprobe')
    if not ffprobe:
        return 0.0
    try:
        out = subprocess.check_output(
            [
                ffprobe, '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                path,
            ],
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
        return max(0.0, float(out.decode().strip() or 0))
    except Exception:
        return 0.0


def _run_ffmpeg(args: list, timeout: int = 180) -> bool:
    ffmpeg = _which('ffmpeg')
    if not ffmpeg:
        return False
    try:
        subprocess.run(
            [ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', *args],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        return True
    except Exception:
        return False


def _shrink_video(data: bytes, limit: int) -> bytes:
    """H.264 mp4 не тяжелее limit. Пусто, если не вышло."""
    if not data or not _which('ffmpeg'):
        return b''
    # Два прохода: сначала по длительности, потом жёстче, если не влезло.
    scales = ('1280:-2', '854:-2', '640:-2')
    with tempfile.TemporaryDirectory(prefix='proofvid_') as folder:
        src = os.path.join(folder, 'in.bin')
        with open(src, 'wb') as handle:
            handle.write(data)
        duration = _probe_duration(src) or 30.0
        audio = 64_000
        target_bits = max(40_000, int(limit * 8 * 0.82 / duration) - audio)
        # Последний проход без звука: на коротком ролике AAC сам не влезает в лимит.
        passes = [
            (scale, max(40_000, int(target_bits * (0.55 ** i))), False)
            for i, scale in enumerate(scales)
        ]
        passes.append(('640:-2', max(30_000, target_bits // 4), True))
        for index, (scale, bitrate, silent) in enumerate(passes):
            dest = os.path.join(folder, f'out{index}.mp4')
            args = [
                '-i', src,
                '-vf', f'scale={scale}:force_original_aspect_ratio=decrease',
                '-c:v', 'libx264', '-preset', 'veryfast',
                '-b:v', str(bitrate),
                '-maxrate', str(max(bitrate + 1, int(bitrate * 1.15))),
                '-bufsize', str(max(bitrate, bitrate * 2)),
                '-movflags', '+faststart',
                '-pix_fmt', 'yuv420p',
            ]
            if silent:
                args += ['-an']
            else:
                args += ['-c:a', 'aac', '-b:a', '64k']
            args.append(dest)
            ok = _run_ffmpeg(args)
            if not ok or not os.path.isfile(dest):
                continue
            blob = open(dest, 'rb').read()
            if blob and len(blob) <= limit:
                return blob
    return b''


def _shrink_image(data: bytes, limit: int) -> bytes:
    if not data or not _which('ffmpeg'):
        return b''
    with tempfile.TemporaryDirectory(prefix='proofimg_') as folder:
        src = os.path.join(folder, 'in.bin')
        dest = os.path.join(folder, 'out.jpg')
        with open(src, 'wb') as handle:
            handle.write(data)
        ok = _run_ffmpeg([
            '-i', src,
            '-vf', "scale='min(1600,iw)':-2",
            '-q:v', '6',
            dest,
        ], timeout=60)
        if not ok or not os.path.isfile(dest):
            return b''
        blob = open(dest, 'rb').read()
        return blob if blob and len(blob) <= limit else b''


def fit_for_discord(
    data: bytes,
    filename: str,
    *,
    limit: int,
    kind: str,
) -> tuple[bytes, str, str]:
    """Байты для вложения Discord.

    Возвращает (data, filename, note). note пустой, если файл ушёл как был.
    Пустые data — вложить нечего.
    """
    name = os.path.basename(filename or '') or 'proof.bin'
    if not data:
        return b'', name, ''
    if len(data) <= limit:
        return data, name[:100], ''
    if kind == 'video':
        shrunk = _shrink_video(data, limit)
        if shrunk:
            return shrunk, f'{_safe_stem(name)}.mp4', ''
    elif kind == 'image':
        shrunk = _shrink_image(data, limit)
        if shrunk:
            return shrunk, f'{_safe_stem(name)}.jpg', ''
    return b'', name, ''
