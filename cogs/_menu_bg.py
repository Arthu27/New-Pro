"""
Menu Background Generator — Custom Architectural Background Styles for Each Menu
Каждое меню получает свой уникальный фоновый паттерн (Blueprint, Circuit, Diamond, Crown),
подчеркивающий атмосферу раздела (Топ, Экономика, Тикеты, Сервер), сохраняя профессиональный белый стиль.
"""

import os
import math
from PIL import Image, ImageDraw

ROOT = os.path.join(os.path.dirname(__file__), '..')
BG_PATH = os.path.join(ROOT, 'assets', 'profile_bg_pro.jpg')

WHITE = (255, 255, 255, 255)


def _load_base_bg(w, h):
    try:
        bg = Image.open(BG_PATH).convert('RGBA')
        bw, bh = bg.size
        target_ratio = w / h
        src_ratio = bw / bh
        if src_ratio > target_ratio:
            new_w = int(bh * target_ratio)
            x0 = (bw - new_w) // 2
            bg = bg.crop((x0, 0, x0 + new_w, bh))
        else:
            new_h = int(bw / target_ratio)
            y0 = (bh - new_h) // 2
            bg = bg.crop((0, y0, bw, y0 + new_h))
        return bg.resize((w, h), Image.Resampling.LANCZOS)
    except Exception:
        return Image.new('RGBA', (w, h), WHITE)


def load_menu_bg(w: int, h: int, theme: str = "default") -> Image.Image:
    """Загружает фон и наносит уникальный тематический фоновый стиль для каждого меню"""
    base = _load_base_bg(w, h)
    overlay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    if theme == "gold":
        # Золотой паттерн "Корона и лучи лидерства" (Leaderboard)
        gold_c = (217, 119, 6, 28)
        # Диагональные королевские лучи с правого верхнего угла
        for i in range(0, w + h, 80):
            d.line([(i, 0), (0, i)], fill=gold_c, width=2)
        # Декоративные геометрические ромбы в фоне
        for x in range(120, w, 220):
            for y in range(80, h, 180):
                r = 35
                pts = [(x, y - r), (x + r, y), (x, y + r), (x - r, y), (x, y - r)]
                d.line(pts, fill=gold_c, width=2)

    elif theme == "teal":
        # Бирюзовый паттерн "Кибер-цепи и узлы безопасности" (Ticket / Support)
        teal_c = (13, 148, 136, 28)
        # Горизонтальные и вертикальные печатные дорожки (Circuit Board)
        for y in range(80, h, 120):
            d.line([(0, y), (w, y)], fill=teal_c, width=2)
            for x in range(100, w, 200):
                d.ellipse((x - 5, y - 5, x + 5, y + 5), outline=teal_c, width=2)
                d.line([(x, y), (x + 30, y - 30)], fill=teal_c, width=2)

    elif theme == "emerald":
        # Изумрудный паттерн "Алмазная решетка казначейства" (Economy / Shop)
        em_c = (16, 185, 129, 28)
        # Гексагональная/ромбическая сетка богатства
        step_x, step_y = 120, 70
        for x in range(-60, w + 120, step_x):
            for y in range(-40, h + 80, step_y):
                pts = [
                    (x, y - 30),
                    (x + 50, y),
                    (x, y + 30),
                    (x - 50, y),
                    (x, y - 30)
                ]
                d.line(pts, fill=em_c, width=2)

    elif theme == "blue":
        # Синий паттерн "Инженерный чертеж и радарная сетка" (ServerInfo / Utility)
        blue_c = (2, 132, 199, 26)
        # Инженерная координатная сетка (Blueprint grid)
        for x in range(0, w, 60):
            d.line([(x, 0), (x, h)], fill=blue_c, width=1)
        for y in range(0, h, 60):
            d.line([(0, y), (w, y)], fill=blue_c, width=1)
        # Радарные дуги из правого угла
        for r in range(150, 800, 150):
            d.arc((w - r, -r, w + r, r), 90, 180, fill=blue_c, width=2)

    return Image.alpha_composite(base, overlay)


async def setup(bot):
    pass

