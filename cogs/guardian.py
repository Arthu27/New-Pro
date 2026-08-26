# -*- coding: utf-8 -*-
"""Hakumo «Щит» — анти-нюк защита сервера (PRO).

Если кто-то (по злому умыслу или со взломанного аккаунта) начнёт:
- сносить каналы/роли пачкой,
- раздавать админские права,
- массово банить и кикать,
- лепить вебхуки,
- тащить на сервер чужих ботов,
- а также если БОТ с правами сам начнёт бесчинствовать (взломанный токен,
  саботаж) — для ботов-нарушителей есть отдельная мера,
— Щит мгновенно останавливает: снимает роли (или кикает/банит) виновника,
кикает неавторизованного бота и шлёт красивую тревогу в лог-канал.

Приглашать ботов могут только люди из выделенного белого списка
«кто может добавлять ботов» (+ общий белый список и владелец).

Всё настраивается из панели: страница /guardian (пороги, меры, белый список),
канал тревог — на странице /channel-settings (маршрут guardian_channel,
фолбэк — -модерация или любой лог-канал).

Хранилище: data/guardian_<guild_id>.json (json_store, атомарная запись).
Чистые функции (нормализация, счётчик окна, опасные права, белый список)
вынесены наружу и покрыты тестом tests/test_guardian.py.
"""

from logger import get_logger

_log = get_logger("guardian")

from json_store import load_json as _js_load, save_json as _js_save

import time
from datetime import datetime, timezone

import discord
from discord.ext import commands

from services.channel_routes import get_route as _route_get

DATA_FILE = 'data/guardian_{guild_id}.json'

# Кто автоматически неприкосновенен (дополнительно к белому списку):
# владелец сервера и сам бот — проверяется в _touch.

# ─── Меры наказания ─────────────────────────────────────────────────────────
PUNISHMENTS = (
    ('strip', 'Снять все роли'),
    ('kick', 'Кикнуть с сервера'),
    ('ban', 'Забанить'),
    ('alert', 'Только тревога в лог'),
)
PUNISH_LABELS = dict(PUNISHMENTS)

# ─── Опасные права роли (кто получил — тот может уничтожить сервер) ─────────
DANGEROUS_PERMS = (
    ('administrator', 'Администратор'),
    ('manage_guild', 'Управление сервером'),
    ('manage_roles', 'Управление ролями'),
    ('manage_channels', 'Управление каналами'),
    ('ban_members', 'Бан участников'),
    ('kick_members', 'Кик участников'),
    ('manage_webhooks', 'Управление вебхуками'),
    ('manage_expressions', 'Управление эмодзи'),
    ('mention_everyone', 'Упоминание всех'),
)

# ─── События под защитой ────────────────────────────────────────────────────
# def: (порог, окно сек) — сколько таких действий за окно = атака.
EVENT_SPECS = [
    {'key': 'channel_delete', 'label': 'Удаление каналов', 'icon': 'fa-hashtag',
     'def': (3, 10), 'desc': 'Массовый снос каналов — классический ньюк.'},
    {'key': 'channel_create', 'label': 'Создание каналов', 'icon': 'fa-square-plus',
     'def': (5, 10), 'desc': 'Спам-создание каналов под рейд-чаты.'},
    {'key': 'role_delete', 'label': 'Удаление ролей', 'icon': 'fa-user-tag',
     'def': (2, 10), 'desc': 'Снос ролей ломает всю структуру доступа.'},
    {'key': 'role_create', 'label': 'Создание ролей', 'icon': 'fa-plus',
     'def': (4, 10), 'desc': 'Массовое создание ролей — подготовка к захвату.'},
    {'key': 'dangerous_perms', 'label': 'Опасные права ролям', 'icon': 'fa-key',
     'def': (1, 5), 'action': 'strip',
     'desc': 'Выдача админских прав (бан, роли, каналы, все-пинги). Реакция мгновенная.'},
    {'key': 'member_ban', 'label': 'Массовый бан', 'icon': 'fa-gavel',
     'def': (3, 10), 'desc': 'Пачка банов подряд — зачистка сервера.'},
    {'key': 'member_kick', 'label': 'Массовый кик', 'icon': 'fa-door-open',
     'def': (3, 10), 'desc': 'Пачка киков подряд — выброс участников.'},
    {'key': 'webhook_create', 'label': 'Создание вебхуков', 'icon': 'fa-link',
     'def': (2, 30), 'desc': 'Через вебхуки спамят в обход фильтров и мьюта.'},
    {'key': 'bot_add', 'label': 'Добавление ботов', 'icon': 'fa-robot',
     'def': (1, 5),
     'desc': 'Чужой бот без разрешения — почти всегда захват. Бот кикается сам.'},
    {'key': 'emoji_delete', 'label': 'Удаление эмодзи', 'icon': 'fa-face-smile',
     'def': (5, 30), 'desc': 'Вандальное удаление смайлов пачкой.'},
    {'key': 'guild_update', 'label': 'Изменение сервера', 'icon': 'fa-server',
     'def': (1, 5), 'action': 'alert',
     'desc': 'Смена имени/иконки сервера. По умолчанию — только тревога.'},
]
_SPEC_BY_KEY = {s['key']: s for s in EVENT_SPECS}

MAX_INCIDENTS = 30          # сколько последних инцидентов хранить
_ID_MIN, _ID_MAX = 17, 22   # длина discord ID (как в антирейде)


# ────────────────────────────────────────────────────────────────────────────
# Чистые функции (тестируются отдельно от discord)
# ────────────────────────────────────────────────────────────────────────────
def _default_events():
    out = {}
    for spec in EVENT_SPECS:
        t, w = spec['def']
        out[spec['key']] = {'enabled': True, 'threshold': t, 'window': w,
                            'action': spec.get('action')}
    return out


def guardian_default():
    """Конфиг по умолчанию: ВЫКЛЮЧЕН (opt-in). Пороги-фабрики уже стоят —
    владельцу остаётся один тумблер в панели/командой."""
    return {
        'enabled': False,
        'punishment': 'strip',
        'bot_action': 'strip',
        'kick_unauthorized_bots': True,
        'events': _default_events(),
        'whitelist_users': [],
        'whitelist_roles': [],
        'bot_whitelist_users': [],
        'bot_whitelist_roles': [],
        'incidents': [],
    }


def _clean_ids(raw, limit=200):
    """Список discord ID: только цифры разумной длины, без дублей, с лимитом."""
    if not isinstance(raw, list):
        return []
    seen = set()
    out = []
    for x in raw:
        s = str(x).strip()
        if not (s.isdigit() and _ID_MIN <= len(s) <= _ID_MAX):
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= limit:
            break
    return out


def guardian_normalize(raw):
    """Сшить сырой dict поверх дефолта: клампы, отброс лишнего.

    Неизвестные события игнорируются; порог 1..25, окно 3..300 сек;
    action — из PUNISH_LABELS или None (= общая мера); инциденты сохраняются.
    """
    base = guardian_default()
    if not isinstance(raw, dict):
        return base
    base['enabled'] = bool(raw.get('enabled', base['enabled']))
    pun = str(raw.get('punishment') or base['punishment'])
    base['punishment'] = pun if pun in PUNISH_LABELS else 'strip'
    bact = str(raw.get('bot_action') or base['bot_action'])
    base['bot_action'] = bact if bact in PUNISH_LABELS else 'strip'
    base['kick_unauthorized_bots'] = bool(raw.get(
        'kick_unauthorized_bots', base['kick_unauthorized_bots']))
    base['whitelist_users'] = _clean_ids(raw.get('whitelist_users'))
    base['whitelist_roles'] = _clean_ids(raw.get('whitelist_roles'))
    base['bot_whitelist_users'] = _clean_ids(raw.get('bot_whitelist_users'))
    base['bot_whitelist_roles'] = _clean_ids(raw.get('bot_whitelist_roles'))
    raw_events = raw.get('events')
    if isinstance(raw_events, dict):
        for key, ev in base['events'].items():
            src = raw_events.get(key)
            if not isinstance(src, dict):
                continue
            ev['enabled'] = bool(src.get('enabled', ev['enabled']))
            try:
                ev['threshold'] = max(1, min(25, int(src.get('threshold', ev['threshold']))))
            except (TypeError, ValueError) as _ex:
                _log.debug('guardian: порог %s не изменён: %s', key, _ex)
            try:
                ev['window'] = max(3, min(31 * 86400, int(src.get('window', ev['window']))))
            except (TypeError, ValueError) as _ex:
                _log.debug('guardian: окно %s не изменено: %s', key, _ex)
            act = src.get('action', ev.get('action'))
            ev['action'] = act if act in PUNISH_LABELS else None
    inc = raw.get('incidents')
    if isinstance(inc, list):
        base['incidents'] = [i for i in inc if isinstance(i, dict)][-MAX_INCIDENTS:]
    return base


def load_cfg(guild_id):
    """Конфиг сервера (дефолт, если файла нет). Дешёвый читатель через кеш."""
    return guardian_normalize(_js_load(DATA_FILE.format(guild_id=guild_id),
                                       {}, log=_log))


def save_cfg(guild_id, cfg):
    cfg = guardian_normalize(cfg)
    _js_save(DATA_FILE.format(guild_id=guild_id), cfg, log=_log)
    return cfg


def guardian_record_incident(cfg, row):
    """Добавить инцидент в конфиг (cap MAX_INCIDENTS). Мутирует cfg."""
    inc = cfg.setdefault('incidents', [])
    inc.append(row)
    del inc[:-MAX_INCIDENTS]
    return cfg


def is_whitelisted(cfg, user_id, role_ids=()):
    """Освобождён ли пользователь (или его роль) от Щита."""
    try:
        uid = str(int(user_id))
    except (TypeError, ValueError):
        return True    # неизвестный актёр — не наказываем вслепую
    if uid in set(str(x) for x in cfg.get('whitelist_users') or ()):
        return True
    wl_roles = set(str(x) for x in cfg.get('whitelist_roles') or ())
    for rid in role_ids or ():
        if str(rid) in wl_roles:
            return True
    return False


def can_add_bots(cfg, user_id, role_ids=(), owner_id=0, bot_id=0):
    """Может ли этот человек ЗВАТЬ ботов на сервер.

    Разрешено: владельцу сервера; самому боту-Щиту; общему белому списку
    (доверенные — им можно всё); выделенному списку «кто может добавлять
    ботов» (пользователи и роли). Остальным — нельзя.
    """
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return False
    if uid and uid in (int(owner_id or 0), int(bot_id or 0)):
        return True
    if is_whitelisted(cfg, uid, role_ids):
        return True
    if str(uid) in set(str(x) for x in cfg.get('bot_whitelist_users') or ()):
        return True
    wl_roles = set(str(x) for x in cfg.get('bot_whitelist_roles') or ())
    for rid in role_ids or ():
        if str(rid) in wl_roles:
            return True
    return False


def newly_dangerous(before, after):
    """Какие опасные права появились у роли после правки [(name, label), ...]."""
    out = []
    for name, label in DANGEROUS_PERMS:
        if getattr(after, name, False) and not getattr(before, name, False):
            out.append((name, label))
    return out


class WindowCounter:
    """Скользящее окно: сколько действий актёр совершил за N секунд."""

    def __init__(self):
        self._hits = {}

    def hit(self, key, now, window, times=1):
        lst = [t for t in self._hits.get(key, []) if now - t <= window]
        lst.extend([now] * max(1, int(times)))
        self._hits[key] = lst
        return len(lst)

    def reset(self, key):
        self._hits.pop(key, None)


# ────────────────────────────────────────────────────────────────────────────
# Ког
# ────────────────────────────────────────────────────────────────────────────
class Guardian(commands.Cog):
    """Анти-нюк движок: слушает опасные события и гасит атаку в зародыше."""

    def __init__(self, bot):
        self.bot = bot
        self._counter = WindowCounter()

    # — утилиты доступа/белого списка —
    def _member_role_ids(self, guild, user_id):
        member = guild.get_member(int(user_id)) if user_id else None
        if member is None:
            return ()
        return [r.id for r in getattr(member, 'roles', [])]

    def _member_mention(self, actor_id, actor_name):
        if actor_id:
            return f'<@{actor_id}> (`{actor_name}`)'
        return f'`{actor_name}`'

    async def _actor(self, guild, action, target_id=None, max_age=15):
        """Кто это сделал — по журналу аудита Discord. (user_id, имя)."""
        try:
            async for entry in guild.audit_logs(limit=6, action=action):
                if target_id is not None and getattr(entry.target, 'id', None) != target_id:
                    continue
                try:
                    age = (datetime.now(timezone.utc) - entry.created_at).total_seconds()
                except (TypeError, AttributeError):
                    age = 0
                if age > max_age:
                    continue
                u = entry.user
                return (getattr(u, 'id', 0) or 0, (str(u) if u else '—'))
        except Exception as _ex:
            _log.debug('guardian: audit-лог недоступен (%s): %s', action, _ex)
        return (0, '—')

    # — главный цикл реакции —
    async def _touch(self, guild, event_key, actor_id=0, actor_name='—',
                     detail='', times=1):
        """Засчитать действие; при превышении порога — наказать и взвить тревогу."""
        cfg = load_cfg(guild.id)
        if not cfg.get('enabled'):
            return
        ev = (cfg.get('events') or {}).get(event_key) or {}
        if not ev.get('enabled'):
            return
        spec = _SPEC_BY_KEY.get(event_key)
        if spec is None:
            return
        if actor_id:
            if actor_id in (getattr(guild, 'owner_id', 0),
                            getattr(getattr(self.bot, 'user', None), 'id', 0)):
                return
            if is_whitelisted(cfg, actor_id, self._member_role_ids(guild, actor_id)):
                return
        key = (guild.id, event_key, actor_id)
        count = self._counter.hit(key, time.time(),
                                  ev.get('window', 10), times=times)
        threshold = ev.get('threshold', 3)
        if count < threshold:
            _log.info('guardian: %s × %s/%s от %s (гильдия %s)',
                      event_key, count, threshold, actor_id, guild.id)
            return
        self._counter.reset(key)
        action = ev.get('action') or cfg.get('punishment', 'strip')
        # Если нарушитель — БОТ, применяем отдельную меру для ботов:
        # у бота «вечная жизнь» не нужна — его можно и удалить сразу.
        try:
            _actor_member = guild.get_member(int(actor_id)) if actor_id else None
        except Exception as _ex:
            _log.debug('guardian: актёр не резолвится: %s', _ex)
            _actor_member = None
        if _actor_member is not None and getattr(_actor_member, 'bot', False):
            action = cfg.get('bot_action', 'strip')
        applied = await self._punish(guild, actor_id, action, spec)
        await self._alert(guild, spec, actor_id, actor_name, action, applied,
                          detail, count)
        try:
            row = {'ts': int(time.time()), 'event': event_key,
                   'label': spec['label'], 'actor_id': str(actor_id or ''),
                   'actor_name': str(actor_name or '—'), 'action': action,
                   'action_label': PUNISH_LABELS.get(action, action),
                   'applied': applied, 'detail': str(detail or '')[:160]}
            save_cfg(guild.id, guardian_record_incident(load_cfg(guild.id), row))
        except Exception as _ex:
            _log.debug('guardian: инцидент не записан: %s', _ex)

    async def _punish(self, guild, actor_id, action, spec):
        """Применить меру. Возвращает человекочитаемый итог."""
        if action == 'alert' or not actor_id:
            return '—'
        member = guild.get_member(int(actor_id))
        try:
            if action == 'strip':
                if member is None:
                    return 'нарушителя нет на сервере'
                me_top = getattr(getattr(guild, 'me', None), 'top_role', None)
                roles = [r for r in getattr(member, 'roles', [])
                         if r != guild.default_role and not getattr(r, 'managed', False)
                         and (me_top is None or r < me_top)]
                if not roles:
                    return 'ролей для снятия нет'
                await member.remove_roles(*roles,
                                          reason='Hakumo Щит: анти-нюк — снятие ролей')
                return f'снято ролей: {len(roles)}'
            if action == 'kick':
                if member is None:
                    return 'нарушителя нет на сервере'
                await guild.kick(member, reason='Hakumo Щит: анти-нюк (кик)')
                return 'кикнут'
            if action == 'ban':
                await guild.ban(discord.Object(id=int(actor_id)),
                                reason='Hakumo Щит: анти-нюк (бан)',
                                delete_message_seconds=0)
                return 'забанен'
        except Exception as _ex:
            _log.warning('guardian: мера %s для %s не применена: %s',
                         action, actor_id, _ex)
            return 'не удалось (проверьте права бота)'
        return '—'

    async def _alert(self, guild, spec, actor_id, actor_name, action,
                     applied, detail, count):
        """Красивая тревога в маршрутный канал (хаб Каналы/фолбэк -модерация)."""
        ch = None
        cid = _route_get(guild.id, 'guardian_channel')
        if cid:
            ch = guild.get_channel(cid)
        if ch is None:
            try:
                from cogs.logs import ensure_log_channel
                ch = await ensure_log_channel(guild, 'модерация')
            except Exception as _ex:
                _log.debug('guardian: лог-канал не найден: %s', _ex)
                ch = None
        if ch is None:
            return
        try:
            from cogs.embed_utils import hakumo_embed
            fields = [
                ('Нарушитель', self._member_mention(actor_id, actor_name), True),
                ('Сработало', f'{count} подряд', True),
                ('Мера', PUNISH_LABELS.get(action, action), True),
                ('Итог', applied, True),
            ]
            if detail:
                fields.append(('Детали', detail[:200], False))
            e = hakumo_embed('mod', f'Щит: {spec["label"]}',
                             'Щит остановил опасную волну действий '
                             'и применил меру автоматически.',
                             fields=fields, guild=guild, footer_extra='Щит сервера')
            await ch.send(embed=e)
        except Exception as _ex:
            _log.debug('guardian: тревога не ушла: %s', _ex)

    # ─── слушатели событий ───────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        actor = await self._actor(channel.guild, discord.AuditLogAction.channel_delete,
                                  target_id=channel.id)
        await self._touch(channel.guild, 'channel_delete', actor[0], actor[1],
                          detail=f'канал «{getattr(channel, "name", "?")}»')

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        actor = await self._actor(channel.guild, discord.AuditLogAction.channel_create,
                                  target_id=channel.id)
        await self._touch(channel.guild, 'channel_create', actor[0], actor[1],
                          detail=f'канал «{getattr(channel, "name", "?")}»')

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        actor = await self._actor(role.guild, discord.AuditLogAction.role_delete,
                                  target_id=role.id)
        await self._touch(role.guild, 'role_delete', actor[0], actor[1],
                          detail=f'роль «{getattr(role, "name", "?")}»')

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        actor = await self._actor(role.guild, discord.AuditLogAction.role_create,
                                  target_id=role.id)
        await self._touch(role.guild, 'role_create', actor[0], actor[1],
                          detail=f'роль «{getattr(role, "name", "?")}»')

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        nd = newly_dangerous(getattr(before, 'permissions', None),
                             getattr(after, 'permissions', None))
        if not nd:
            return
        actor = await self._actor(after.guild, discord.AuditLogAction.role_update,
                                  target_id=after.id)
        labels = ', '.join(lbl for _n, lbl in nd)
        await self._touch(after.guild, 'dangerous_perms', actor[0], actor[1],
                          detail=f'роль «{getattr(after, "name", "?")}»: {labels}')

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        actor = await self._actor(guild, discord.AuditLogAction.ban,
                                  target_id=getattr(user, 'id', None))
        await self._touch(guild, 'member_ban', actor[0], actor[1],
                          detail=f'жертва: `{getattr(user, "name", user)}`')

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        # Кик отличаем от самостоятельного выхода только по свежей записи аудита.
        actor = await self._actor(member.guild, discord.AuditLogAction.kick,
                                  target_id=member.id, max_age=10)
        if not actor[0]:
            return
        await self._touch(member.guild, 'member_kick', actor[0], actor[1],
                          detail=f'жертва: `{member}`')

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel):
        actor = await self._actor(channel.guild, discord.AuditLogAction.webhook_create)
        if not actor[0]:
            return
        await self._touch(channel.guild, 'webhook_create', actor[0], actor[1],
                          detail=f'канал «{getattr(channel, "name", "?")}»')

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not getattr(member, 'bot', False):
            return
        cfg = load_cfg(member.guild.id)
        if not cfg.get('enabled'):
            return
        ev = (cfg.get('events') or {}).get('bot_add') or {}
        if not ev.get('enabled'):
            return
        actor = await self._actor(member.guild, discord.AuditLogAction.bot_add,
                                  target_id=member.id)
        if not actor[0]:
            return
        # выделенный белый список «кто может добавлять ботов» + общий + владелец
        if can_add_bots(cfg, actor[0],
                        self._member_role_ids(member.guild, actor[0]),
                        owner_id=getattr(member.guild, 'owner_id', 0),
                        bot_id=getattr(getattr(self.bot, 'user', None), 'id', 0)):
            _log.info('guardian: бот %s добавлен разрешённым %s — ок',
                      member.id, actor[0])
            return
        kicked = False
        if cfg.get('kick_unauthorized_bots'):
            try:
                await member.guild.kick(member,
                                        reason='Hakumo Щит: бот добавлен без разрешения')
                kicked = True
            except Exception as _ex:
                _log.warning('guardian: бот %s не кикнут: %s', member.id, _ex)
        if kicked:
            detail = f'бот `{member}` — кикнут'
        elif cfg.get('kick_unauthorized_bots'):
            detail = f'бот `{member}` — кикнуть не удалось'
        else:
            detail = f'бот `{member}` — кик ботов выключен в настройках'
        # bot_add по умолчанию срабатывает с первого раза (порог 1)
        await self._touch(member.guild, 'bot_add', actor[0], actor[1], detail=detail)

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        after_ids = set(getattr(e, 'id', 0) for e in after)
        deleted = [e for e in before if getattr(e, 'id', 0) not in after_ids]
        if not deleted:
            return
        actor = await self._actor(guild, discord.AuditLogAction.emoji_delete, max_age=12)
        names = ' '.join(f'`:{getattr(e, "name", "?")}:`' for e in deleted[:5])
        await self._touch(guild, 'emoji_delete', actor[0], actor[1],
                          detail=names, times=len(deleted))

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        changes = []
        if getattr(before, 'name', None) != getattr(after, 'name', None):
            changes.append(f'имя: `{before.name}` → `{after.name}`')
        try:
            if (before.icon and after.icon and before.icon.key != after.icon.key) \
                    or bool(before.icon) != bool(after.icon):
                changes.append('иконка изменена')
        except AttributeError as _ex:
            _log.debug('guardian: иконка сервера не сравнивается: %s', _ex)
        if not changes:
            return
        actor = await self._actor(after, discord.AuditLogAction.guild_update)
        if not actor[0]:
            return
        await self._touch(after, 'guild_update', actor[0], actor[1],
                          detail='; '.join(changes))


async def setup(bot):
    await bot.add_cog(Guardian(bot))
