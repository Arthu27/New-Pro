# -*- coding: utf-8 -*-
"""Файловое хранилище участников сервера.

Зачем
-----
На сервере 20 000+ людей, и каждый раз выкачивать состав из Discord заново
(gateway chunking) — долго и тяжело: панель открывалась с пустым списком,
пока бот не докачает кэш. Заказ владельца: участники живут В ФАЙЛЕ, бот их
сохраняет, панель читает файл и видит состав сразу, а обновляется только
когда реально кто-то вошёл/вышел — не опросом каждые несколько секунд.

Как устроено
------------
* ``data/members_<gid>.json`` — состав сервера: таблица ролей + словарь
  участников по id. Роли вынесены в отдельную таблицу, у участника лежат
  только их id: на 20 000 человек файл остаётся в единицах мегабайт.
* Чтение — из памяти модуля (файл парсится один раз и только если изменился
  по mtime), поэтому отдача списка панели не стоит дискового I/O.
* Запись НЕ на каждое событие: изменения копятся и сбрасываются пачкой не
  чаще раза в ``FLUSH_SEC`` (и принудительно при остановке) — иначе каждый
  вход/выход участника писал бы мегабайты на диск.
* Вошёл — ``upsert()``, вышел — ``remove()``, сменил роль/ник — ``upsert()``.
* Всё через ``json_store`` (общий кэш + атомарная запись через .tmp+rename),
  в async-коде — через ``services.async_io``, чтобы не морозить event loop.

Статус online/offline в файле не хранится осмысленно (меняется постоянно):
панель подмешивает его из живого кэша discord.py, если участник там есть.
"""
import os
import threading
import time

import json_store
from logger import get_logger

_log = get_logger('member_store')

# Как часто максимум сбрасываем накопленные изменения на диск.
FLUSH_SEC = 30.0
# Полный снимок состава пишем сразу, если накопилось много изменений
# (например, бот только что докачал 20 000 человек) — не ждём таймера.
FLUSH_AT_ONCE = 500

_LOCK = threading.RLock()
# gid -> {'roles': {rid: {...}}, 'members': {uid: {...}}, 'saved_at': ts,
#         'member_count': int}
_MEM = {}
# gid -> (mtime_ns, size) последнего прочитанного состояния файла
_SIG = {}
# gid -> число изменений с последнего сброса
_PENDING = {}
_last_flush = {}


def path(guild_id) -> str:
    return f'data/members_{guild_id}.json'


def _sig_of(p):
    try:
        st = os.stat(p)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _blank():
    return {'roles': {}, 'members': {}, 'saved_at': 0, 'member_count': 0}


def _ensure(guild_id):
    """Состав гильдии в памяти; читаем файл, только если он изменился."""
    gid = str(guild_id or '')
    if not gid:
        return _blank()
    with _LOCK:
        p = path(gid)
        sig = _sig_of(p)
        cur = _MEM.get(gid)
        if cur is not None and _SIG.get(gid) == sig:
            return cur
        data = json_store.load_json(p, None, log=_log)
        if not isinstance(data, dict):
            data = _blank()
        else:
            data.setdefault('roles', {})
            data.setdefault('members', {})
            data.setdefault('saved_at', 0)
            data.setdefault('member_count', len(data['members']))
        _MEM[gid] = data
        _SIG[gid] = sig
        _PENDING.setdefault(gid, 0)
        return data


# ── сериализация discord.Member ────────────────────────────────────────────
def role_row(role) -> dict:
    return {'name': str(getattr(role, 'name', '') or ''),
            'color': str(getattr(role, 'color', '') or '')}


def member_row(member, roles_by_id=None, guild_id=None):
    """Участник в том виде, в каком его храним и отдаём панели."""
    gid = str(guild_id or getattr(getattr(member, 'guild', None), 'id', '') or '')
    roles = getattr(member, 'roles', None) or []
    # @everyone — не роль в смысле панели: у API исторически roles[1:].
    # id гильдии берём из аргумента (он у нас всегда есть), а не только из
    # member.guild — иначе «@everyone» протекал в список ролей участника.
    own = [r for r in roles if str(getattr(r, 'id', '')) != gid]
    rids = []
    for r in own:
        rid = str(getattr(r, 'id', ''))
        if not rid:
            continue
        rids.append(rid)
        if roles_by_id is not None:
            roles_by_id[rid] = role_row(r)
    top = getattr(member, 'top_role', None)
    joined = getattr(member, 'joined_at', None)
    created = getattr(member, 'created_at', None)
    av = getattr(member, 'display_avatar', None)
    return {
        'id': str(getattr(member, 'id', '')),
        'name': str(getattr(member, 'name', '') or ''),
        'display_name': str(getattr(member, 'display_name', '') or getattr(member, 'name', '') or ''),
        'avatar': str(getattr(av, 'url', '') or ''),
        'bot': bool(getattr(member, 'bot', False)),
        'joined_at': joined.isoformat() if joined else None,
        'created_at': created.isoformat() if created else None,
        'nick': getattr(member, 'nick', None),
        'role_ids': rids,
        'top_role': str(getattr(top, 'name', '') or '') if top else None,
        'status': str(getattr(member, 'status', '') or 'offline'),
    }


# ── чтение ────────────────────────────────────────────────────────────────
def count(guild_id) -> int:
    return len(_ensure(guild_id)['members'])


def saved_at(guild_id):
    return _ensure(guild_id).get('saved_at') or 0


def get(guild_id, user_id):
    """Один участник по id (или None) — для карточки 360° и поиска."""
    row = _ensure(guild_id)['members'].get(str(user_id or ''))
    return _expand(guild_id, row) if row else None


def _expand(guild_id, row):
    """Дополнить строку участника именами/цветами ролей из таблицы гильдии."""
    if not row:
        return None
    data = _MEM.get(str(guild_id)) or _ensure(guild_id)
    roles = data.get('roles') or {}
    out = dict(row)
    out['roles'] = [dict(roles.get(rid) or {'name': rid, 'color': ''})
                    for rid in (row.get('role_ids') or [])]
    out.pop('role_ids', None)
    return out


def snapshot(guild_id, offset=0, limit=None):
    """Список участников (страница). Порядок — как в файле."""
    data = _ensure(guild_id)
    members = data['members']
    keys = list(members.keys())
    if offset:
        keys = keys[offset:]
    if limit:
        keys = keys[:limit]
    return [_expand(guild_id, members[k]) for k in keys]


def find(guild_id, q, limit=25):
    """Быстрый поиск по нику/имени/id внутри сохранённого состава."""
    q = str(q or '').strip().lower()
    data = _ensure(guild_id)
    members = data['members']
    if not q:
        return snapshot(guild_id, 0, limit)
    head, tail = [], []
    for uid, row in members.items():
        nm = str(row.get('name') or '').lower()
        dn = str(row.get('display_name') or '').lower()
        if uid == q:
            head.insert(0, row)
        elif nm.startswith(q) or dn.startswith(q):
            head.append(row)
        elif q in nm or q in dn or q in uid:
            tail.append(row)
        if len(head) >= limit:
            break
    out = [_expand(guild_id, r) for r in (head + tail)[:limit]]
    return out


# ── запись ────────────────────────────────────────────────────────────────
def _touch(guild_id, n=1):
    """Пометить, что есть несохранённые изменения.

    Намеренно НЕ пишем на диск здесь: upsert/remove вызываются из
    async-обработчиков Discord, а синхронная запись мегабайтного файла
    морозит event loop шлюза. Сбрасывает накопленное aflush() из кога
    (в рабочем потоке) и flush() при остановке.
    """
    gid = str(guild_id)
    _PENDING[gid] = _PENDING.get(gid, 0) + n
    return _PENDING[gid]


def pending(guild_id=None):
    """Сколько изменений ещё не на диске (по гильдии или всего)."""
    with _LOCK:
        if guild_id is not None:
            return _PENDING.get(str(guild_id), 0)
        return sum(_PENDING.values())


def needs_flush(guild_id=None):
    """Пора ли сбрасывать: накопили пачку или прошёл интервал."""
    with _LOCK:
        gids = [str(guild_id)] if guild_id is not None else list(_PENDING.keys())
        now = time.time()
        for gid in gids:
            if not _PENDING.get(gid):
                continue
            if (_PENDING[gid] >= FLUSH_AT_ONCE
                    or now - _last_flush.get(gid, 0.0) >= FLUSH_SEC):
                return True
    return False


def _write(guild_id):
    gid = str(guild_id)
    with _LOCK:
        data = _MEM.get(gid)
        if data is None:
            data = _ensure(gid)
        data['member_count'] = len(data['members'])
        data['saved_at'] = int(time.time())
        ok = json_store.save_json(path(gid), data, indent=0, log=_log)
        if ok:
            _PENDING[gid] = 0
            _last_flush[gid] = time.time()
            _SIG[gid] = _sig_of(path(gid))
        return ok


async def aflush(guild_id=None):
    """Несблокировать loop: сброс накопленного в рабочем потоке.

    Вызывается из кога member_store_sync по таймеру и после докачки кэша.
    """
    import asyncio
    with _LOCK:
        gids = [str(guild_id)] if guild_id is not None else list(_MEM.keys())
    done = 0
    for gid in gids:
        if not _PENDING.get(gid):
            continue
        try:
            if await asyncio.to_thread(_write, gid):
                done += 1
        except Exception as _ex:                        # noqa: BLE001
            _log.debug('aflush(%s): %s', gid, _ex)
    return done


def flush(guild_id=None):
    """Синхронный сброс — для остановки бота и тестов (вне event loop)."""
    with _LOCK:
        gids = [str(guild_id)] if guild_id else list(_MEM.keys())
    done = 0
    for gid in gids:
        if _PENDING.get(gid):
            try:
                if _write(gid):
                    done += 1
            except Exception as _ex:                    # noqa: BLE001
                _log.debug('flush(%s): %s', gid, _ex)
    return done


def upsert(guild_id, member):
    """Участник вошёл или изменился — добавить/обновить в хранилище."""
    gid = str(guild_id or getattr(getattr(member, 'guild', None), 'id', '') or '')
    if not gid:
        return False
    with _LOCK:
        data = _ensure(gid)
        row = member_row(member, roles_by_id=data['roles'], guild_id=gid)
        uid = row['id']
        if not uid:
            return False
        data['members'][uid] = row
        _touch(gid)
    return True


def upsert_many(guild_id, members):
    """Пачка участников (после докачки кэша). Диск — за вызывающим (aflush)."""
    gid = str(guild_id)
    with _LOCK:
        data = _ensure(gid)
        roles = data['roles']
        n = 0
        for m in members:
            row = member_row(m, roles_by_id=roles, guild_id=gid)
            if row['id']:
                data['members'][row['id']] = row
                n += 1
        if n:
            _touch(gid, n)
    return n


def remove(guild_id, user_id):
    """Участник вышел — убрать из хранилища (заказ владельца)."""
    gid = str(guild_id)
    uid = str(user_id or '')
    with _LOCK:
        data = _ensure(gid)
        if uid not in data['members']:
            return False
        del data['members'][uid]
        _touch(gid)
    return True


def replace_guild_roles(guild_id, roles):
    """Обновить таблицу ролей гильдии (роль создана/переименована/удалена)."""
    gid = str(guild_id)
    with _LOCK:
        data = _ensure(gid)
        data['roles'] = {str(getattr(r, 'id', '')): role_row(r)
                         for r in (roles or [])
                         if str(getattr(r, 'id', '')) != gid}
        _touch(gid, FLUSH_AT_ONCE)
    return True


def stats():
    with _LOCK:
        return {gid: {'members': len(d['members']),
                      'roles': len(d.get('roles') or {}),
                      'pending': _PENDING.get(gid, 0)}
                for gid, d in _MEM.items()}
