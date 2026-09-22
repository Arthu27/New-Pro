# -*- coding: utf-8 -*-
"""Настройки Discord AI-чата (каналы, реплаи, сила модели).

Файл: data/ai_chat_settings.json. Читается когом и панелью.
Канал по умолчанию — боевой AI-чат владельца.
"""
from __future__ import annotations

import os
from typing import Any

from json_store import load_json, save_json
from logger import get_logger

_log = get_logger('ai_chat_settings')

SETTINGS_FILE = 'data/ai_chat_settings.json'

# Боевой канал AI-чата (заказ владельца).
DEFAULT_CHAT_CHANNEL_ID = 1312434963941167134

DEFAULT_SETTINGS: dict[str, Any] = {
    'enabled': True,
    # Каналы, где ИИ отвечает на сообщения (и на reply к своим).
    'channels': [DEFAULT_CHAT_CHANNEL_ID],
    # Отвечать, когда человек делает reply на сообщение бота в этих каналах.
    'reply_to_bot': True,
    # Отвечать на любое сообщение в канале (не только mention/reply).
    'respond_all': True,
    # Требовать @упоминание бота (если respond_all=False).
    'require_mention': False,
    # Сила ответа Discord-чата (пусто = AI_MODEL / mistral-large-latest).
    'model': '',
    'temperature': 0.18,
    'max_tokens': 1600,
}


def _normalize(raw: dict | None) -> dict:
    cfg = dict(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return cfg
    if 'enabled' in raw:
        cfg['enabled'] = bool(raw['enabled'])
    if 'reply_to_bot' in raw:
        cfg['reply_to_bot'] = bool(raw['reply_to_bot'])
    if 'respond_all' in raw:
        cfg['respond_all'] = bool(raw['respond_all'])
    if 'require_mention' in raw:
        cfg['require_mention'] = bool(raw['require_mention'])
    if 'model' in raw and raw['model'] is not None:
        cfg['model'] = str(raw['model']).strip()
    try:
        if 'temperature' in raw:
            t = float(raw['temperature'])
            cfg['temperature'] = max(0.0, min(1.0, t))
    except (TypeError, ValueError):
        pass
    try:
        if 'max_tokens' in raw:
            cfg['max_tokens'] = max(256, min(4096, int(raw['max_tokens'])))
    except (TypeError, ValueError):
        pass
    chans = raw.get('channels')
    if isinstance(chans, list):
        out = []
        for c in chans:
            try:
                cid = int(str(c).strip())
                if cid > 0:
                    out.append(cid)
            except (TypeError, ValueError):
                continue
        # Не даём случайно стереть единственный боевой канал пустым списком
        # через битый JSON — пустой список = «все выкл», это явно ок.
        cfg['channels'] = out
    return cfg


def load_settings() -> dict:
    data = load_json(SETTINGS_FILE, None, log=_log)
    if data is None:
        # Первый запуск — сразу пишем дефолт с боевым каналом.
        cfg = dict(DEFAULT_SETTINGS)
        save_settings(cfg)
        return cfg
    return _normalize(data)


def save_settings(cfg: dict) -> bool:
    normalized = _normalize(cfg)
    return bool(save_json(SETTINGS_FILE, normalized, log=_log))


def channel_ids(cfg: dict | None = None) -> set[int]:
    c = cfg if cfg is not None else load_settings()
    return {int(x) for x in (c.get('channels') or [])}


def env_channel_ids() -> set[int]:
    """Доп. каналы из .env: AI_CHAT_CHANNELS=id1,id2"""
    raw = (os.getenv('AI_CHAT_CHANNELS') or '').strip()
    out: set[int] = set()
    if not raw:
        return out
    for part in raw.replace(';', ',').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return out
