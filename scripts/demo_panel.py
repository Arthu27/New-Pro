#!/usr/bin/env python3
"""Демо-превью панели Aether (MOEBIUS) — запуск веб-панели БЕЗ Discord-бота.

Для разработки/превью (песочница Arena, локальный UI-просмотр):
- фейковый сервер (guild id 4242) с парой каналов;
- обычная форма входа с отдельной demo-учётной записью owner / 123321;
- засевает логи, доказательства и наглядную историю объявлений;
- все временные метки aware-UTC, как пишет бот после fix(time); живые данные не затирает.

Запуск:  python3 scripts/demo_panel.py  ->  http://127.0.0.1:8090/login
"""
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

os.environ.setdefault('MAIN_GUILD_ID', '4242')
os.environ.setdefault('SECRET_KEY', 'demo-preview-key-not-real')

GID = 4242
NOW = datetime.now(timezone.utc)
DEMO_USERNAME = 'owner'
DEMO_PASSWORD = '123321'


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
                'timestamp': _iso(NOW - timedelta(seconds=sec)),
            })
        with open(audit_path, 'w', encoding='utf-8') as f:
            json.dump({str(GID): events}, f, ensure_ascii=False, indent=1)

    message_log_path = f'data/message_logs_{GID}.json'
    if not os.path.exists(message_log_path):
        authors = ('Arthur', 'Moder_Nika', 'Meloman', 'Novichok', 'Luna', 'Vortex', 'Mira', 'Spectre')
        channels = ('общий', 'медиа', 'поиск-команды', 'оффтоп')
        messages = []
        for day in range(30):
            daily_total = 14 + ((day * 7 + 11) % 24)
            for index in range(daily_total):
                messages.append({
                    'author': authors[(index * 3 + day) % len(authors)],
                    'channel': channels[(index + day // 3) % len(channels)],
                    'timestamp': _iso(NOW - timedelta(
                        days=day, hours=(index * 5 + day) % 20,
                        minutes=(index * 13) % 60)),
                })
        with open(message_log_path, 'w', encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False)

    announcements_path = 'data/announcements.json'
    if not os.path.exists(announcements_path):
        announcements = [
            {
                'id': 'ann-demo-001',
                'title': 'Добро пожаловать в обновлённую панель',
                'message': 'Мы собрали управление сервером, модерацию и коммуникации в едином рабочем пространстве. Теперь важные операции выполняются быстрее и прозрачнее.',
                'from': 'Arthur', 'guild_id': None, 'channel_id': None,
                'channel_name': None, 'delivered': False, 'deliver_error': None,
                'created_at': _iso(NOW - timedelta(days=4)),
            },
            {
                'id': 'ann-demo-002',
                'title': 'Плановые технические работы',
                'message': 'Сегодня с 22:00 до 22:30 пройдёт обновление инфраструктуры.\n\nВо время работ голосовая статистика может обновляться с небольшой задержкой.',
                'from': 'Moder_Nika', 'guild_id': str(GID), 'channel_id': '777002',
                'channel_name': 'общий', 'delivered': True, 'deliver_error': None,
                'created_at': _iso(NOW - timedelta(days=2, hours=3)),
            },
            {
                'id': 'ann-demo-003',
                'title': 'Новая система доказательств',
                'message': 'Для модераторов открыт обновлённый раздел доказательств. Каждая запись теперь связана с участником, причиной и решением команды.',
                'from': 'Arthur', 'guild_id': str(GID), 'channel_id': '777001',
                'channel_name': 'доказательства', 'delivered': True, 'deliver_error': None,
                'created_at': _iso(NOW - timedelta(hours=18)),
            },
            {
                'id': 'ann-demo-004',
                'title': 'Турнир сообщества в субботу',
                'message': 'Открываем регистрацию на командный турнир.\n\nДата: суббота, 19:00\nФормат: команды по 3 участника\nРегистрация: в канале #общий\n\nПобедители получат уникальную роль и награду профиля.',
                'from': 'EventTeam', 'guild_id': str(GID), 'channel_id': '777002',
                'channel_name': 'общий', 'delivered': False,
                'deliver_error': 'Missing Access: бот временно потерял право Embed Links',
                'created_at': _iso(NOW - timedelta(hours=5)),
            },
            {
                'id': 'ann-demo-005',
                'title': 'Обновление правил безопасности',
                'message': 'Мы уточнили правила публикации ссылок и защиты личных данных.\n\nПожалуйста, ознакомьтесь с изменениями перед следующей публикацией. Если останутся вопросы, обратитесь к модераторам.',
                'from': 'Arthur', 'guild_id': str(GID), 'channel_id': '777002',
                'channel_name': 'общий', 'delivered': True, 'deliver_error': None,
                'created_at': _iso(NOW - timedelta(minutes=35)),
            },
        ]
        with open(announcements_path, 'w', encoding='utf-8') as f:
            json.dump(announcements, f, ensure_ascii=False, indent=2)

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


seed()

import web.app as wapp  # noqa: E402
from flask import redirect, request, session  # noqa: E402

# Arena показывает preview внутри HTTPS iframe. Для такой схемы браузеру нужны
# SameSite=None + Secure, иначе пароль принимается, но cookie не возвращается
# после редиректа и пользователь снова видит Welcome. Только demo-процесс —
# production-конфигурация web/app.py не меняется.
wapp.app.config['SESSION_COOKIE_SAMESITE'] = 'None'
wapp.app.config['SESSION_COOKIE_SECURE'] = True
wapp.app.config['SESSION_COOKIE_PARTITIONED'] = True

# Отдельная учётная запись действует только в памяти demo-процесса. Файл
# production-credentials не перезаписывается, а вход проходит через обычную
# форму /login со штатной проверкой хэша и созданием сессии.
wapp.USERS.clear()
wapp.USERS[DEMO_USERNAME] = {
    'password_hash': wapp._hash_pw(DEMO_PASSWORD),
    'role': 'owner',
}


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

# Некоторые браузеры полностью запрещают cookies в iframe даже с
# SameSite=None/Partitioned. После успешной штатной проверки пароля держим
# короткую server-side demo-сессию, привязанную к адресу прокси и User-Agent.
# Это fallback только запущенного demo-процесса: после рестарта всё исчезает.
_DEMO_AUTH_TTL = 8 * 60 * 60
_demo_authorized = {}


def _demo_client_key():
    forwarded = (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
    address = forwarded or request.remote_addr or 'preview'
    agent = request.headers.get('User-Agent') or 'browser'
    return hashlib.sha256(f'{address}\0{agent}'.encode('utf-8')).hexdigest()


@app.before_request
def restore_demo_session():
    if session.get('logged_in'):
        return None
    expires = _demo_authorized.get(_demo_client_key(), 0)
    if expires <= time.time():
        return None
    session.permanent = True
    session['logged_in'] = True
    session['username'] = DEMO_USERNAME
    session['role'] = 'owner'
    session['avatar'] = ''
    return None


@app.after_request
def remember_demo_session(response):
    key = _demo_client_key()
    location = response.headers.get('Location', '')
    if (request.path == '/login' and request.method == 'POST' and
            response.status_code in (301, 302, 303, 307, 308) and
            location.rstrip('/') == ''):
        _demo_authorized[key] = time.time() + _DEMO_AUTH_TTL
        response.headers['Location'] = '/announcements'
    elif request.path == '/logout':
        _demo_authorized.pop(key, None)
    return response


@app.route('/demo-login')
def demo_login_redirect():
    """Совместимый адрес preview: показывает обычную форму, не создавая сессию."""
    return redirect('/login')


if __name__ == '__main__':
    print('[demo] Панель: http://0.0.0.0:8090/login')
    print(f'[demo] Вход: {DEMO_USERNAME} / {DEMO_PASSWORD}')
    app.run(host='0.0.0.0', port=8090, debug=False, use_reloader=False, threaded=True)
