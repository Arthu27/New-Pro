# -*- coding: utf-8 -*-
"""Вшитый каталог трибун и баннеров Broadcaster-бота.

Баннер собирается в памяти: цвет и название живут в коде, не в сети.
"""
from __future__ import annotations

import struct
import zlib
from typing import Optional

# key, название в меню, короткое описание, RGB баннера
TRIBUNES = (
    {
        'key': 'love',
        'title': 'Любовная трибуна',
        'blurb': 'Разговоры про отношения и симпатии',
        'rgb': (214, 72, 98),
    },
    {
        'key': 'dating',
        'title': 'Трибуна знакомств',
        'blurb': 'Знакомства вживую, без спешки',
        'rgb': (232, 122, 74),
    },
    {
        'key': 'talk',
        'title': 'Общая трибуна',
        'blurb': 'Свободный разговор на любую тему',
        'rgb': (70, 110, 190),
    },
    {
        'key': 'night',
        'title': 'Ночная трибуна',
        'blurb': 'Тихий вечерний эфир',
        'rgb': (48, 42, 92),
    },
    {
        'key': 'music',
        'title': 'Музыкальная трибуна',
        'blurb': 'Треки, вкусы и что сейчас в наушниках',
        'rgb': (120, 64, 180),
    },
    {
        'key': 'games',
        'title': 'Игровая трибуна',
        'blurb': 'Игры, пати и кто во что играет',
        'rgb': (36, 140, 110),
    },
    {
        'key': 'cinema',
        'title': 'Кинотрибуна',
        'blurb': 'Фильмы и сериалы',
        'rgb': (150, 40, 55),
    },
    {
        'key': 'anime',
        'title': 'Аниме-трибуна',
        'blurb': 'Тайтлы, персонажи и рекомендации',
        'rgb': (180, 70, 150),
    },
    {
        'key': 'sport',
        'title': 'Спортивная трибуна',
        'blurb': 'Матчи, команды и споры до свистка',
        'rgb': (30, 130, 70),
    },
    {
        'key': 'humor',
        'title': 'Юмор-трибуна',
        'blurb': 'Истории и шутки без перегиба',
        'rgb': (200, 150, 40),
    },
)


def all_tribunes() -> list:
    return [dict(x) for x in TRIBUNES]


def tribune_by_key(key: str) -> Optional[dict]:
    key = (key or '').strip().lower()
    for item in TRIBUNES:
        if item['key'] == key:
            return dict(item)
    return None


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack('>I', len(data))
        + tag
        + data
        + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def banner_png(item: dict) -> bytes:
    """Цветной баннер 800×320. Вшит в код, без внешних файлов."""
    r, g, b = item.get('rgb') or (40, 40, 40)
    r, g, b = int(r), int(g), int(b)
    width, height = 800, 320
    rows = []
    for y in range(height):
        shade = 0.45 + 0.55 * (1 - y / max(1, height - 1))
        rr = max(0, min(255, int(r * shade)))
        gg = max(0, min(255, int(g * shade)))
        bb = max(0, min(255, int(b * shade)))
        # белая полоса слева — чтобы обложки отличались даже в тёмной теме
        px = bytearray()
        for x in range(width):
            if 18 <= x <= 28:
                px.extend((255, 255, 255))
            else:
                px.extend((rr, gg, bb))
        rows.append(b'\x00' + bytes(px))
    raw = b''.join(rows)
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return (
        b'\x89PNG\r\n\x1a\n'
        + _chunk(b'IHDR', ihdr)
        + _chunk(b'IDAT', zlib.compress(raw, 9))
        + _chunk(b'IEND', b'')
    )
