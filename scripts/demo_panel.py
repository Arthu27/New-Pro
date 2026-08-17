#!/usr/bin/env python3
"""Демо-превью панели Aether (MOEBIUS) — запуск веб-панели БЕЗ Discord-бота.

Для разработки/превью (песочница Arena, локальный UI-просмотр):
- фейковый сервер (guild id 4242) с парой каналов;
- /demo-login — вход как owner (Arthur) без пароля — ТОЛЬКО для демо!;
- засевает data/audit_log.json (логи) и data/modproof_4242.json (галерея демок)
  aware-UTC метками, как пишет бот после fix(time); живые данные не затирает.

Запуск:  python3 scripts/demo_panel.py  ->  http://127.0.0.1:8090/demo-login
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

os.environ.setdefault('MAIN_GUILD_ID', '4242')
os.environ.setdefault('SECRET_KEY', 'demo-preview-key-not-real')
# Демо-пароль владельца: простой и известный, чтобы не набирать случайные
# 16 символов. Живой сервер это не трогает — только демо-запуск.
os.environ.setdefault('PANEL_PASSWORD', 'demo-owner')
_cred = os.path.join('data', 'panel_credentials.json')
if os.path.exists(_cred):
    # Старый сохранённый хэш имеет приоритет над PANEL_PASSWORD —
    # убираем его, чтобы демо-пароль применился (пересоздастся при старте).
    try:
        os.remove(_cred)
    except OSError as _ex:
        print(f'[demo] не удалось убрать старые креды: {_ex}')

GID = 4242
NOW = datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat()


def seed():
    """Засеять демо-данные, если файлов ещё нет (живые не затирать)."""
    os.makedirs('data', exist_ok=True)

    audit_path = 'data/audit_log.json'
    if not os.path.exists(audit_path):
        rows = [
            ('mod',    'Мут',                'Zhulik',   'Arthur',     'Спам в #общий',                 12),
            ('proof',  'Демка добавлена',    'Zhulik',   'Arthur',     'к муту #2',                     15),
            ('warn',   'Предупреждение',     'Troll_228','Moder_Nika', 'Оскорбления участников',        95),
            ('join',   'Зашёл на сервер',    'Novichok', '',           'инвайт от Arthur',              200),
            ('msg',    'Удалено сообщение',  'Spammer',  'AutoMod',    'Реклама сторонних ссылок',      320),
            ('voice',  'Зашёл в голосовой',  'Meloman',  '',           'Общий голосовой',               500),
            ('mod',    'Бан',                'Griever',  'Arthur',     'Рейд-бот, возраст акка 2 часа', 1400),
            ('ticket', 'Тикет закрыт',       'Novichok', 'Moder_Nika', 'вопрос решён',                  2600),
        ]
        events = []
        for i, (cat, action, user, mod, detail, sec) in enumerate(rows):
            events.append({
                'category': cat,
                'action': action,
                'user_id': str(1000000 + i),
                'user_name': user,
                'mod_name': mod,
                'detail': detail,
                'reason': detail if cat == 'mod' else '',
                'timestamp': _iso(NOW - timedelta(seconds=sec)),
            })
        # История модерации за месяц: тренд, команда, рецидивисты
        history = [
            # (action, user_id, user_name, mod_name, reason, days_ago)
            ('Мут',      '1000000', 'Zhulik',   'Arthur',     'Флуд в #общий', 24),
            ('Кик',      '1000000', 'Zhulik',   'Moder_Nika', 'Повторный флуд после варнов', 12),
            ('Мут',      '1000004', 'Spammer',  'Guard_Bot',  'Реклама в трёх каналах', 18),
            ('Мут',      '1000004', 'Spammer',  'Moder_Nika', 'Спам ссылками', 3),
            ('Кик',      '1000002', 'Troll_228', 'Moder_Nika', 'Оскорбления участников', 6),
            ('Мут снят', '1000002', 'Troll_228', 'Arthur',     'Срок истёк', 5),
            ('Мут',      '1000006', 'Griever',  'Arthur',     'Провокация рейда', 30),
            ('Бан',      '1000101', 'RaidBoss', 'Arthur',     'Рейд-бот: 30 аккаунтов за минуту', 8),
            ('Мут',      '1000102', 'CapsLock', 'Guard_Bot',  'КАПС без остановки', 2),
            ('Бан',      '1000103', 'FishBot',  'Moder_Nika', 'Фишинговая ссылка', 1),
            ('Мут снят', '1000102', 'CapsLock', 'Moder_Nika', 'Больше не повторял', 0.5),
        ]
        for action, uid, uname, mname, reason, days_ago in history:
            events.append({
                'category': 'mod', 'action': action,
                'user_id': uid, 'user_name': uname, 'mod_name': mname,
                'reason': reason, 'detail': reason,
                'timestamp': _iso(NOW - timedelta(days=days_ago)),
            })
        with open(audit_path, 'w', encoding='utf-8') as f:
            json.dump({str(GID): events}, f, ensure_ascii=False, indent=1)


    proof_path = f'data/modproof_{GID}.json'
    if not os.path.exists(proof_path):
        rows = [
            (1001, 'Griever',   7, 'Arthur',     'бан',            'Рейд-бот: 30 акков за минуту, возраст 2 часа', 1400),
            (1002, 'Zhulik',    7, 'Arthur',     'мут',            'Спам одним сообщением в пять каналов',         12),
            (1003, 'Troll_228', 5, 'Moder_Nika', 'предупреждение', 'Оскорбления после варна',                      95),
        ]
        items = {}
        for pid, (uid, uname, mid, mname, action, reason, sec) in enumerate(rows, start=1):
            items[str(pid)] = {
                'id': pid,
                'user_id': uid,
                'user_name': uname,
                'mod_id': mid,
                'mod_name': mname,
                'action': action,
                'reason': reason,
                'link': 'https://i.imgur.com/demo.png',
                'url': 'https://i.imgur.com/demo.png',
                'msg_id': 555000 + pid,
                'channel_id': 777001,
                'set_at': _iso(NOW - timedelta(seconds=sec)),
            }
        with open(proof_path, 'w', encoding='utf-8') as f:
            json.dump({'next': 4, 'items': items}, f, ensure_ascii=False, indent=1)

    # голосовая статистика (legacy JSON — при первом чтении автомигрирует
    # в SQLite, ровно как у живых пользователей после обновления)
    voice_path = f'data/voice_stats_{GID}.json'
    if not os.path.exists(voice_path) and not os.path.exists(voice_path + '.legacy'):
        from datetime import date as _date
        _today = str(_date.today())
        vusers = {
            '2001': {'name': 'Meloman',  'avatar': '', 'total_seconds': 2*86400 + 3*3600 + 1200,
                     'daily': {_today: 5400}},
            '2002': {'name': 'Zhulik',   'avatar': '', 'total_seconds': 5*3600 + 25*60,
                     'daily': {_today: 1500}},
            '2003': {'name': 'Novichok', 'avatar': '', 'total_seconds': 47*60 + 13,
                     'daily': {}},
        }
        with open(voice_path, 'w', encoding='utf-8') as f:
            json.dump({'users': vusers}, f, ensure_ascii=False, indent=1)

    # автоматика: ненулевые настройки, чтобы страница «Автоматика» была живой
    # (панель и коги делят эти неймспейсы; засев — только если пусто)
    from db import GuildData
    for ns, demo_settings in (
        ('night_mode', {'enabled': True, 'start_hour': 23, 'end_hour': 7,
                        'slowmode_seconds': 10, 'lock_channels': False,
                        'exempt_channels': [], 'report_channel_id': 0}),
        ('anti_alt', {'enabled': True, 'min_age_days': 7, 'action': 'alert',
                      'log_channel_id': 0, 'whitelist': []}),
        ('mod_digest', {'enabled': True, 'channel_id': 777001, 'hour_utc': 18,
                        'last_sent': None}),
        ('welcome_pro', {'enabled': True, 'channel_id': 777002,
                         'templates': None, 'rotate_index': 0,
                         'dm_enabled': False,
                         'dm_text': 'Привет, {user}! Добро пожаловать на {server}.'}),
    ):
        store = GuildData(ns)
        if store.get(GID, 'settings', None) is None:
            if ns == 'welcome_pro':
                demo_settings.pop('templates', None)
                demo_settings['templates'] = [
                    'Добро пожаловать, {mention}! Ты — {count}-й житель **{server}**.',
                    '{mention} приземлился на **{server}**. Устраивайся поудобнее!',
                    'Поприветствуем {mention}! Участник №{count}.',
                ]
            store.set(GID, 'settings', demo_settings)



def seed_moderation():
    """Демо-данные для страниц модерации (Мод-контроль, Мод-анализ, Варны).

    Только если файлов ещё нет — живые данные не затираем.
    """
    os.makedirs('data', exist_ok=True)
    now_ts = NOW.timestamp()

    def _dump(path, data):
        if not os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=1)

    # Пороги авто-наказаний (страница /warn-config, формат бота)
    _dump(f'data/warn_config_{GID}.json', {'thresholds': [
        {'count': 3, 'action': 'mute'},
        {'count': 5, 'action': 'kick'},
        {'count': 7, 'action': 'ban'},
    ]})

    # Зеркало варнов — формат 1:1 с cogs/warnings.py
    def _warn(n, reason, mod, days_ago):
        return {'id': n, 'reason': reason, 'mod': mod, 'mod_id': '',
                'timestamp': _iso(NOW - timedelta(days=days_ago))}

    _dump('data/warnings.json', {str(GID): {
        '1000000': [_warn(1, 'Флуд в #общий', 'Arthur', 24),
                    _warn(2, 'Капс после мута', 'Moder_Nika', 13),
                    _warn(3, 'Оскорбления', 'Moder_Nika', 12),
                    _warn(4, 'Спам стикерами', 'Guard_Bot', 2)],
        '1000004': [_warn(1, 'Реклама', 'Guard_Bot', 18),
                    _warn(2, 'Спам ссылками', 'Moder_Nika', 3)],
        '1000102': [_warn(1, 'КАПС', 'Guard_Bot', 2)],
    }})

    # Временные наказания: просроченный, истекает через 20 минут, пара дней, неделя
    _dump('data/temp_mutes.json', {str(GID): {
        '1000000': {'until': now_ts + 2 * 3600, 'reason': 'Флуд в #общий',
                    'mod_id': '7', 'created_at': now_ts - 22 * 3600},
        '1000102': {'until': now_ts + 20 * 60, 'reason': 'КАПС без остановки',
                    'mod_id': '9', 'created_at': now_ts - 40 * 60},
        '1000004': {'until': now_ts - 30 * 60, 'reason': 'Спам ссылками',
                    'mod_id': '9', 'created_at': now_ts - 24 * 3600},
    }})
    _dump('data/temp_bans.json', {str(GID): {
        '1000101': {'until': now_ts + 6 * 86400, 'reason': 'Рейд-бот',
                    'mod_id': '7', 'created_at': now_ts - 86400},
    }})

    # Быстрые причины для Мод-контроля
    def _reason(n, text, by, days_ago):
        return {'id': n, 'text': text, 'by': by,
                'at': _iso(NOW - timedelta(days=days_ago))}

    _dump(f'data/mod_reasons_{GID}.json', {
        'warn': [_reason(1, 'Флуд в чате', 'Arthur', 20),
                 _reason(2, 'Оскорбления участников', 'Arthur', 20),
                 _reason(3, 'Реклама и спам', 'Moder_Nika', 15)],
        'mute': [_reason(1, 'Обход фильтра', 'Arthur', 18),
                 _reason(2, 'Срыв ивента', 'Moder_Nika', 10)],
        'kick': [_reason(1, 'Повторные нарушения', 'Arthur', 18)],
        'ban': [_reason(1, 'Рейд-бот', 'Arthur', 18),
                _reason(2, 'Фишинг/скам', 'Arthur', 12)],
    })

    # Анти-рейд и автофильтр — чтобы чек-лист готовности был живым
    _dump(f'data/antiraid_{GID}.json', {
        'join_raid': True, 'bot_protection': True, 'webhook_protection': False,
        'delete_protection': True, 'age_filter': True,
    })
    _dump(f'data/autofilter_{GID}.json', {
        'enabled': True,
        'words': {'enabled': True, 'action': 'warn',
                  'list': ['скам', 'бесплатные нитро', 'перейди по ссылке']},
        'links': {'enabled': True}, 'caps': {'enabled': True},
        'flood': {'enabled': False},
    })

    # Заметки модераторов (досье)
    _dump('data/member_notes.json', {
        '1000000': {'name': 'Zhulik', 'notes': [
            {'note': 'После кика обещал не флудить — следим',
             'timestamp': _iso(NOW - timedelta(days=11)), 'mod': 'Moder_Nika'},
            {'note': 'Снова флуд, выдан варн', 'timestamp': _iso(NOW - timedelta(days=2)),
             'mod': 'Guard_Bot'},
        ]},
        '1000004': {'name': 'Spammer', 'notes': [
            {'note': 'Похоже на промо-аккаунт, проверить переписку',
             'timestamp': _iso(NOW - timedelta(days=3)), 'mod': 'Arthur'},
        ]},
    })

seed()
seed_moderation()

import web.app as wapp  # noqa: E402
from flask import redirect, session  # noqa: E402


class FakeChannel:
    def __init__(self, cid, name):
        self.id = cid
        self.name = name
        self.mention = f'#{name}'

    def __str__(self):
        return self.name


class FakeGuild:
    id = GID
    name = 'Демо-сервер Aether'
    member_count = 128
    owner_id = 7
    icon = None
    banner = None
    splash = None
    description = 'Песочница панели Aether'
    premium_tier = 2
    vanity_url_code = None
    created_at = NOW - timedelta(days=400)

    def __init__(self):
        self.channels = [FakeChannel(777001, 'доказательства'), FakeChannel(777002, 'общий')]
        self.text_channels = self.channels
        self.voice_channels = []
        self.stage_channels = []
        self.forums = []
        self.categories = []
        self.roles = []
        self.emojis = []
        self.stickers = []
        self.members = []

    def get_member(self, uid):
        return None

    def get_channel(self, cid):
        return next((c for c in self.channels if c.id == cid), None)

    def get_role(self, rid):
        return None


class FakeUser:
    id = 1
    name = 'Aether'
    display_name = 'Aether'
    discriminator = '0'
    avatar = None
    bot = True

    def __str__(self):
        return 'Aether#0'


class FakeTempMod:
    """Суррогат кога TempModeration для демо: читает те же data/temp_*.json.

    Реальный ког держит словари в памяти, но /api/temp-mod/active смотрит
    только на атрибуты _mutes/_bans/_kicks/_scheduled — этого хватает,
    чтобы страница «Временная модерация» была живой в превью.
    """

    def __init__(self):
        def _load(name):
            path = os.path.join('data', name)
            if not os.path.exists(path):
                return {}
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    return json.load(fh)
            except (OSError, json.JSONDecodeError):
                return {}

        self._mutes = _load('temp_mutes.json')
        self._bans = _load('temp_bans.json')
        self._kicks = _load('temp_kicks.json')
        self._scheduled = []


class FakeBot:
    """Минимальный суррогат discord.Client для панели."""

    def __init__(self):
        self.guilds = [FakeGuild()]
        self.user = FakeUser()
        self.latency = 0.012
        self.ws = None
        self.loop = None
        self.owner_id = 7

    def is_ready(self):
        return True

    def get_guild(self, gid):
        return next((g for g in self.guilds if g.id == gid), None)

    def get_cog(self, name):
        if name == 'TempModeration':
            return FakeTempMod()
        return None

    def get_channel(self, cid):
        return None

    def get_user(self, uid):
        return None

    def fetch_user(self, uid):
        raise RuntimeError('demo: discord недоступен')

    def is_ws_ratelimited(self):
        return False


wapp.set_bot_instance(FakeBot())
app = wapp.app


@app.before_request
def _demo_autologin():
    """Авто-вход владельцем на каждый запрос.

    В iframe-превью браузеры могут резать cookies (third-party контекст) —
    тогда обычная сессия не живёт и панель бесконечно возвращает на логин.
    Хук чинит это: нет сессии — считаем, что это владелец Arthur.
    Только демо-режим, живой сервер так не умеет.
    """
    if os.environ.get('DEMO_AUTOLOGIN', '1') != '1':
        return None
    if session.get('logged_in'):
        return None
    session['logged_in'] = True
    session['username'] = 'Arthur'
    session['role'] = 'owner'
    session['avatar'] = ''
    return None


@app.route('/demo-login')
def demo_login():
    """Вход в демо одним кликом (без пароля — только песочница!)."""
    session['logged_in'] = True
    session['username'] = 'Arthur'
    session['role'] = 'owner'
    session['avatar'] = ''
    return redirect('/')


if __name__ == '__main__':
    print('[demo] Панель: http://0.0.0.0:8090/demo-login')
    app.run(host='0.0.0.0', port=8090, debug=False, use_reloader=False, threaded=True)
