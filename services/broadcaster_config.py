# -*- coding: utf-8 -*-
"""config/broadcaster.json + переменные окружения. Токен только в .env."""
from __future__ import annotations

import json
import os
from copy import deepcopy

CONFIG_PATH = os.environ.get(
    'BROADCASTER_CONFIG',
    os.path.join('config', 'broadcaster.json'),
)

DEFAULT_WISHES = [
    'Пусть этот день пройдёт спокойно и без лишней суеты.',
    'Хорошего настроения. Маленькая радость сегодня тоже считается.',
    'Пусть получится то, что давно откладывал.',
    'Тёплого вечера и людей, с которыми легко молчать.',
    'Пусть сегодня кто-нибудь скажет тебе что-то доброе.',
    'Береги силы. Не обязательно успеть всё.',
    'Пусть музыка, которую включишь, попадёт в настроение.',
    'Хороших новостей и ни одной лишней тревоги.',
    'Пусть вечер будет мягче, чем день.',
    'Улыбнись кому-нибудь просто так. Иногда этого хватает.',
    'Пусть планы на сегодня сбудутся хотя бы наполовину.',
    'Спокойной головы и тёплого чата.',
    'Пусть рядом окажутся свои.',
    'Не торопись. День ещё не кончился.',
    'Пусть получится отдохнуть по-настоящему, а не «между делом».',
    'Хорошего эфира тем, кто сегодня на трибуне.',
    'Пусть ночь будет тихой.',
    'Сделай одну приятную мелочь для себя.',
    'Пусть день закроется на хорошей ноте.',
    'До завтра. Сегодня ты уже молодец, что просто здесь.',
]


def load_cfg(path: str | None = None) -> dict:
    path = path or CONFIG_PATH
    raw = {}
    if path and os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            raw = loaded
    cfg = deepcopy(raw)
    cfg.setdefault('guild_id', '793336829280780331')
    cfg.setdefault('broadcaster_role_id', '1551180629687664670')
    cfg.setdefault('timezone', 'Europe/Moscow')
    cfg.setdefault('tribune_category_id', '0')
    cfg.setdefault('announce_channel_id', '0')
    cfg.setdefault('gender_role_ids', ['804361264641474602', '804361268017627156'])
    cfg.setdefault('event_duration_minutes', 120)
    love = dict(cfg.get('love') or {})
    love.setdefault('category_id', '0')
    love.setdefault('lobby_name', 'войти в лав руму')
    love.setdefault('room_name', 'лав рума')
    love.setdefault('user_limit', 2)
    cfg['love'] = love
    wishes = dict(cfg.get('wishes') or {})
    wishes.setdefault('channel_id', '0')
    wishes.setdefault('times', ['10:00', '21:00'])
    wishes.setdefault('delete_after_minutes', 30)
    wishes.setdefault('timezone', cfg.get('timezone') or 'Europe/Moscow')
    wishes.setdefault('messages', list(DEFAULT_WISHES))
    cfg['wishes'] = wishes

    env_map = {
        'BROADCASTER_GUILD_ID': 'guild_id',
        'BROADCASTER_ROLE_ID': 'broadcaster_role_id',
        'BROADCASTER_TZ': 'timezone',
        'BROADCASTER_ANNOUNCE_CHANNEL': 'announce_channel_id',
        'BROADCASTER_WISH_CHANNEL': None,
    }
    for env_key, field in env_map.items():
        value = (os.environ.get(env_key) or '').strip()
        if not value:
            continue
        if field:
            cfg[field] = value
        elif env_key == 'BROADCASTER_WISH_CHANNEL':
            cfg['wishes']['channel_id'] = value
    times = (os.environ.get('BROADCASTER_WISH_TIMES') or '').strip()
    if times:
        cfg['wishes']['times'] = [x.strip() for x in times.split(',') if x.strip()]
    delay = (os.environ.get('BROADCASTER_WISH_DELETE_MINUTES') or '').strip()
    if delay:
        cfg['wishes']['delete_after_minutes'] = int(delay)
    return cfg


def wishes_cfg(cfg: dict | None = None) -> dict:
    cfg = cfg or load_cfg()
    return dict(cfg.get('wishes') or {})
