# -*- coding: utf-8 -*-
"""Демо-режим панели (DEMO_MODE=1): витрина без живого Discord-бота.

В демо нет подключённого бота, поэтому всё, что на бою решается его
состоянием, здесь честно эмулируется:

- модули считаются ЗАГРУЖЕННЫМИ (витрина «всё работает»), а щелчки
  «выключить/включить» в менеджере модулей реально переключают флаги и
  запоминаются в data/demo_cog_states.json — страница сразу отражает это;
- профильная карта cogs_policy (LEAN по умолчанию) к демо не применяется:
  панель показывает все 121 страниц без чипов «выкл».

На бою DEMO_MODE не поднят — там всё по-прежнему реальное.
"""
import json
import os

from logger import get_logger

_log = get_logger("demo_cogs")

_PATH = 'data/demo_cog_states.json'
_TRUTHY = ('1', 'true', 'yes', 'on')


def demo_mode():
    """Панель поднята в режиме витрины (DEMO_MODE=1)."""
    return str(os.environ.get('DEMO_MODE', '')).strip().lower() in _TRUTHY


def load_states():
    """{имя_модуля: bool} — переопределения демо (по умолчанию всё вкл)."""
    try:
        with open(_PATH, 'r', encoding='utf-8') as fp:
            d = json.load(fp)
        return {str(k): bool(v) for k, v in d.items()} if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_states(states):
    try:
        os.makedirs('data', exist_ok=True)
        tmp = _PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fp:
            json.dump(states, fp, ensure_ascii=False, indent=2)
        os.replace(tmp, _PATH)
    except OSError as _ex:
        _log.debug("save_states(): %s", _ex)


def is_loaded(name):
    """Модуль в демо загружен, пока его не выключили из менеджера."""
    return load_states().get(str(name), True)


def set_loaded(name, on):
    """Переключить демо-состояние модуля (возвращает итоговое значение)."""
    st = load_states()
    st[str(name)] = bool(on)
    save_states(st)
    return bool(on)
