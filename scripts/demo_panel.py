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
                'timestamp': _iso(NOW - timedelta(seconds=sec)),
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


seed()

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
