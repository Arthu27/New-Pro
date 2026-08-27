# -*- coding: utf-8 -*-
"""Единая точка решения «демо-превью или бой» для веб-панели.

Демо-режим (DEMO_MODE=1) показывает ВЫДУМАННЫЕ данные: участников-
заглушек, сервер-пустышку, счётчики. Он нужен только для показа панели
без бота (витрина до настройки). Чтобы демо не могло вклиниться в боевой
запуск (жалоба владельца: «панель грузит фейк и чужой сервер»), здесь —
жёсткие стоп-правила, по приоритету:

1. бот подключён к процессу панели → НИКОГДА не демо;
2. задан токен бота (TOKEN в .env) → не демо;
3. MAIN_GUILD_ID указывает на настоящий сервер (не заглушку) → не демо.

Правила 2–3 можно сознательно отключить для витрины поверх боевого .env —
флагом DEMO_FORCE=1. Правило 1 абсолютно: живой бот важнее любых флагов.
"""
import os

# ID «серверов», которые заведомо не бывают настоящими: пресеты демо-превью
# (start_panel --demo, scripts/demo_panel.py) и тестовые заглушки.
DEMO_GUILD_PLACEHOLDERS = ('777', '4242', '987654321098765432')

_TRUE = ('1', 'true', 'yes', 'on')


def _flag(env, name):
    return str(env.get(name, '') or '').strip().lower() in _TRUE


def has_real_setup(env=None):
    """Боевая настройка обнаружена: есть токен бота или настоящий сервер."""
    env = os.environ if env is None else env
    if str(env.get('TOKEN', '') or '').strip():
        return True
    gid = str(env.get('MAIN_GUILD_ID', '') or '').strip()
    return bool(gid) and gid not in DEMO_GUILD_PLACEHOLDERS


def demo_mode_active(env=None, bot_connected=False):
    """True, только если демо попросили И оно не перекрывает боевой запуск."""
    env = os.environ if env is None else env
    if not _flag(env, 'DEMO_MODE'):
        return False
    if bot_connected:
        return False
    if has_real_setup(env) and not _flag(env, 'DEMO_FORCE'):
        return False
    return True
