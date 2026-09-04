# -*- coding: utf-8 -*-
"""Мост «процесс бота ⇄ процесс веб-панели» (data/bot_state.json + data/bot_roles_<gid>.json).

Зачем
-----
Панель умеет работать отдельным процессом от бота (start_panel.bat / .sh,
gunicorn, панель на VDS), но живое состояние бота (гильдии, роли) хранится
только в памяти процесса бота. В отдельном процессе web.app.bot_instance
всегда None — и панель честно отвечала «Бот офлайн», даже когда бот работал.
Это и есть главная причина жалобы «бот онлайн, а в настройках пишет офлайн».

Как устроено
------------
* Процесс бота (main.py, фоновая задача) раз в ~5 секунд атомарно пишет
  крошечный пульс data/bot_state.json: статус (starting/online/offline),
  пинг до Discord, список гильдий {id, имя}.
* Роли сервера бот сохраняет в data/bot_roles_<gid>.json только когда они
  реально изменились (сравнение по сигнатуре: id+имя+позиция) — роли почти
  не меняются, диск не дёргается.
* Веб-панель (в ЛЮБОМ процессе) читает эти файлы: пульс свежий (TTL) и
  status=online — значит бот в сети; роли для селектов берутся из снимка
  (формат совпадает с живым списком: порядок по позиции, managed/@everyone
  отфильтрованы на чтении).

Файлы крошечные, лежат в общем data/ (бот и панель видят одну папку).
Старый пульс после смерти бота «протухает» по TTL — врать «онлайн» дольше
~15 секунд мост не может.
"""
import json
import os
import threading
import time

from logger import get_logger

log = get_logger('bot_bridge')

BASE = os.path.join('data')
STATE_FILE = os.path.join(BASE, 'bot_state.json')
ROLE_FILE = os.path.join(BASE, 'bot_roles_{gid}.json')
# Каналы пишем в ТОТ ЖЕ файл, что живые /api/channels откладывают при офлайне
# (panel_channels_cache_<gid>.json) — тогда пикеры каналов по всей панели
# работают и в отдельном процессе, и при кратком офлайне бота.
CHANNEL_FILE = os.path.join(BASE, 'panel_channels_cache_{gid}.json')

WRITE_EVERY_SEC = 5.0   # период пульса бота
# Пульс свежим считаем не дольше TTL: переживает 2-3 пропущенные записи
# (пауза GC, занятый диск) и не врёт «онлайн» дольше этого после смерти бота.
TTL_SEC = 15.0

_LOCK = threading.Lock()
_last_write = [0.0]
# gid -> сигнатура ролей, записанных в файл (id+имя+позиция+managed).
_ROLE_FP = {}
# gid -> сигнатура каналов (id+имя+тип+позиция+категория).
_CHAN_FP = {}


# ── запись (вызывается из процесса бота) ─────────────────────────────────
def write_state(status='starting', latency_ms=None, guilds=None, force=False):
    """Записать пульс бота. status: 'starting' | 'online' | 'offline'.

    force=True — писать сразу (первый тик/старт); иначе не чаще
    WRITE_EVERY_SEC, чтобы цикл бота не дёргал диск каждую секунду.
    """
    if status not in ('starting', 'online', 'offline'):
        status = 'starting'
    now = time.time()
    with _LOCK:
        if not force and now - _last_write[0] < WRITE_EVERY_SEC:
            return False
        _last_write[0] = now
    payload = {
        'status': status,
        'latency_ms': latency_ms,
        'guilds': [dict(g) for g in (guilds or []) if isinstance(g, dict)],
        'ts': now,
        'pid': os.getpid(),
    }
    try:
        os.makedirs(BASE, exist_ok=True)
        tmp = STATE_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fp:
            json.dump(payload, fp, ensure_ascii=False)
        os.replace(tmp, STATE_FILE)
        return True
    except Exception as ex:                       # noqa: BLE001
        log.debug('bot_bridge.write_state: %s', ex)
        return False


def write_roles(guild_id, role_objs):
    """Снимок ролей гильдии — только если состав/порядок изменились.

    role_objs — discord.Role-подобные объекты (id/name/color/position/managed).
    @everyone (id == guild_id) в файл не пишем; managed сохраняем — на чтении
    панель их отфильтрует так же, как в живом списке.
    """
    gid = str(guild_id or '')
    if not gid:
        return False
    rows = []
    sig = []
    try:
        ordered = sorted(role_objs, key=lambda r: -(int(getattr(r, 'position', 0) or 0)))
    except Exception:                             # noqa: BLE001
        ordered = list(role_objs or [])
    for r in ordered:
        rid = str(getattr(r, 'id', '') or '')
        if not rid or rid == gid:
            continue                              # @everyone — не роль выбора
        color = getattr(r, 'color', None)
        try:
            color_hex = '#%06x' % color.value if color is not None else None
        except Exception:                         # noqa: BLE001
            color_hex = None
        row = {
            'id': rid,
            'name': str(getattr(r, 'name', '') or ''),
            'color': color_hex,
            'position': int(getattr(r, 'position', 0) or 0),
            'managed': bool(getattr(r, 'managed', False)),
        }
        rows.append(row)
        sig.append((rid, row['name'], row['position'], row['managed']))
    # Пишем, только если файла нет либо сигнатура изменилась (переименование,
    # создание/удаление роли, смена позиции) — роли меняются редко.
    path = ROLE_FILE.format(gid=gid)
    try:
        if _ROLE_FP.get(gid) == sig and os.path.exists(path):
            return False
        os.makedirs(BASE, exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fp:
            json.dump(rows, fp, ensure_ascii=False)
        os.replace(tmp, path)
        _ROLE_FP[gid] = sig
        return True
    except Exception as ex:                       # noqa: BLE001
        log.debug('bot_bridge.write_roles(%s): %s', gid, ex)
        return False


def write_channels(guild_id, channel_objs):
    """Снимок каналов гильдии (для /api/channels и пикеров панели).

    Пишем в тот же data/panel_channels_cache_<gid>.json, который живой
    /api/channels откладывает при офлайне — формат {'channels': [...]}.
    Статичные поля те же, что у живого списка; connected (сколько людей в
    войсе) в снимке всегда 0 — его нельзя узнать без живого кэша, и он
    нужен только на живой странице каналов.
    """
    gid = str(guild_id or '')
    if not gid:
        return False
    _TYPE = {'news': 'text', 'forum': 'text', 'stage_voice': 'voice'}
    rows = []
    sig = []
    try:
        ordered = sorted(channel_objs or [],
                         key=lambda c: (int(getattr(c, 'position', 0) or 0),
                                        str(getattr(c, 'name', '') or '')))
    except Exception:                             # noqa: BLE001
        ordered = list(channel_objs or [])
    for c in ordered:
        cid = str(getattr(c, 'id', '') or '')
        if not cid:
            continue
        tname = str(getattr(c, 'type', '') or '').rsplit('.', 1)[-1]
        ctype = _TYPE.get(tname, tname)
        cat = getattr(c, 'category', None)
        cat_id = str(getattr(cat, 'id', '') or '') if cat is not None else None
        cat_name = str(getattr(cat, 'name', '') or '') if cat is not None else None
        cat_pos = int(getattr(cat, 'position', 0) or 0) if cat is not None else -1
        created = getattr(c, 'created_at', None)
        row = {
            'id': cid,
            'name': str(getattr(c, 'name', '') or ''),
            'type': ctype,
            'position': int(getattr(c, 'position', 0) or 0),
            'category': cat_name,
            'category_id': cat_id,
            'category_pos': cat_pos,
            'topic': str(getattr(c, 'topic', '') or '') if hasattr(c, 'topic') else '',
            'nsfw': bool(getattr(c, 'nsfw', False)) if hasattr(c, 'nsfw') else False,
            'slowmode': int(getattr(c, 'slowmode_delay', 0) or 0) if hasattr(c, 'slowmode_delay') else 0,
            'bitrate': int((getattr(c, 'bitrate', 0) or 0) // 1000) if hasattr(c, 'bitrate') else 0,
            'user_limit': int(getattr(c, 'user_limit', 0) or 0) if hasattr(c, 'user_limit') else 0,
            'news': tname == 'news',
            'stage': tname == 'stage_voice',
            'forum': tname == 'forum',
            'connected': 0,
            'created_at': created.isoformat() if created else None,
            'mention': getattr(c, 'mention', ''),
        }
        rows.append(row)
        sig.append((cid, row['name'], ctype, row['position'], cat_id))
    path = CHANNEL_FILE.format(gid=gid)
    try:
        if _CHAN_FP.get(gid) == sig and os.path.exists(path):
            return False
        os.makedirs(BASE, exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fp:
            json.dump({'channels': rows}, fp, ensure_ascii=False)
        os.replace(tmp, path)
        _CHAN_FP[gid] = sig
        return True
    except Exception as ex:                       # noqa: BLE001
        log.debug('bot_bridge.write_channels(%s): %s', gid, ex)
        return False


# ── чтение (вызывается из любого процесса — бота или панели) ─────────────
def read_state():
    """Содержимое пульса + вычисленный 'age' (сек от записи); None — файла нет."""
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        if not isinstance(data, dict):
            return None
        try:
            age = time.time() - float(data.get('ts') or 0)
        except (TypeError, ValueError):
            age = float('inf')
        data['age'] = age
        return data
    except (OSError, ValueError):
        return None


def state_status(state=None):
    """'online' | 'starting' | 'offline' по пульсу (с учётом свежести).

    Протухший файл (бот умер/перезапускается дольше TTL) = offline.
    """
    st = state if state is not None else read_state()
    if not st:
        return 'offline'
    try:
        if float(st.get('age') or float('inf')) > TTL_SEC:
            return 'offline'
    except (TypeError, ValueError):
        return 'offline'
    status = st.get('status')
    return status if status in ('online', 'starting') else 'offline'


def guild_ids(state=None):
    """ID гильдий из пульса (живого, иначе пусто)."""
    st = state if state is not None else read_state()
    if not st or state_status(st) == 'offline':
        return []
    out = []
    for g in (st.get('guilds') or []):
        if isinstance(g, dict) and str(g.get('id') or ''):
            out.append(str(g['id']))
    return out


def read_roles(guild_id):
    """Список ролей из снимка бота: [{id,name,color,position,managed}] или None."""
    gid = str(guild_id or '')
    if not gid:
        return None
    try:
        with open(ROLE_FILE.format(gid=gid), 'r', encoding='utf-8') as fp:
            rows = json.load(fp)
        if not isinstance(rows, list):
            return None
        return [r for r in rows if isinstance(r, dict)]
    except (OSError, ValueError):
        return None


def read_channels(guild_id):
    """Список каналов из снимка бота (panel_channels_cache): [{...}] или None."""
    gid = str(guild_id or '')
    if not gid:
        return None
    try:
        with open(CHANNEL_FILE.format(gid=gid), 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        rows = data.get('channels') if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return None
        return [r for r in rows if isinstance(r, dict)]
    except (OSError, ValueError):
        return None


def bot_alive_for(guild_id):
    """Короткая проверка «бот онлайн и видит эту гильдию» по пульсу.

    Удобна эндпоинтам-пикерам: пульс свежий + гильдия в списке = можно
    показывать дисковые снимки ролей/каналов.
    """
    st = read_state()
    if state_status(st) != 'online':
        return False
    return str(guild_id) in guild_ids(st)
