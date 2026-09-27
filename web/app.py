# -*- coding: utf-8 -*-
"""Минимальная панель модерации (v2). Без старого web/-меню и демо-данных.

Страницы: docs/PANEL-PAGES.md
Роли: owner > admin > curator > mod > helper.
Вход: Discord OAuth (роли с сервера) или пароль (.env / Доступ).
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask, abort, flash, g, jsonify, redirect, render_template,
    request, session, url_for,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
ACCESS_FILE = DATA / 'panel_access.json'
SECRET_FILE = DATA / 'panel_secret.txt'
DISCORD_API = 'https://discord.com/api/v10'

# helper < mod < curator < admin < owner
LEVEL = {
    'helper': 1,
    'mod': 2,
    'curator': 3,
    'admin': 4,
    'owner': 9,
}
ROLE_LABELS = {
    'helper': 'Helper',
    'mod': 'Moderator',
    'curator': 'Curator',
    'admin': 'Admin',
    'owner': 'Owner',
}
PAGES_ALL = [
    ('today', '/', 'Сегодня', 'fa-sun'),
    ('logs', '/logs', 'Журнал', 'fa-book-open'),
    ('users', '/users', 'Пользователи', 'fa-users'),
    ('member', '/member', 'Участник', 'fa-user'),
    ('warns', '/warns', 'Варны', 'fa-triangle-exclamation'),
    ('appeals', '/appeals', 'Апелляции', 'fa-scale-balanced'),
    ('proofs', '/proofs', 'Демки', 'fa-camera'),
    ('reasons', '/reasons', 'Причины', 'fa-list-check'),
    ('bot', '/bot', 'Бот', 'fa-robot'),
    ('modules', '/modules', 'Модули', 'fa-puzzle-piece'),
    ('commands', '/commands', 'Команды', 'fa-terminal'),
    ('anticrash', '/anticrash', 'Антикраш', 'fa-shield-heart'),
    ('access', '/access', 'Доступ', 'fa-key'),
]
PAGES_MOD = [p for p in PAGES_ALL if p[0] in {
    'today', 'logs', 'users', 'member', 'warns', 'appeals', 'proofs', 'reasons'}]
PAGES_OWNER = [p for p in PAGES_ALL if p[0] in {
    'bot', 'modules', 'commands', 'anticrash', 'access'}]

# Какие ключи страниц видит роль (накопительно по уровню)
ROLE_PAGE_KEYS = {
    'helper': {'today', 'logs', 'users', 'member', 'warns'},
    'mod': {'today', 'logs', 'users', 'member', 'warns', 'appeals', 'proofs', 'reasons'},
    'curator': {'today', 'logs', 'users', 'member', 'warns', 'appeals', 'proofs', 'reasons'},
    'admin': {
        'today', 'logs', 'users', 'member', 'warns', 'appeals', 'proofs', 'reasons',
        'bot', 'modules', 'commands', 'anticrash',
    },
    'owner': {p[0] for p in PAGES_ALL},
}

ROLE_CARDS = [
    {
        'key': 'helper',
        'title': 'Helper',
        'tag': '@Helper',
        'blurb': 'Смотрит смены и варны. Без апелляций и настроек сервера.',
        'pages': ['Сегодня', 'Журнал', 'Пользователи', 'Участник', 'Варны'],
    },
    {
        'key': 'mod',
        'title': 'Moderator',
        'tag': '@Moderator',
        'blurb': 'Полная мод-панель: апелляции, демки, причины.',
        'pages': ['Всё у Helper', '+ Апелляции', 'Демки', 'Причины'],
    },
    {
        'key': 'curator',
        'title': 'Curator',
        'tag': '@Curator',
        'blurb': 'Куратор ветки — та же мод-панель, роль с Discord.',
        'pages': ['Как Moderator'],
    },
    {
        'key': 'admin',
        'title': 'Admin',
        'tag': '@Admin',
        'blurb': 'Мод-панель + бот, модули, команды и антикраш.',
        'pages': ['Мод-панель', 'Бот', 'Модули', 'Команды', 'Антикраш'],
    },
    {
        'key': 'owner',
        'title': 'Owner',
        'tag': '@Owner',
        'blurb': 'Полный доступ, включая страницу Доступ.',
        'pages': ['Всё', '+ Доступ'],
    },
]

bot_instance = None


def set_bot_instance(bot):
    global bot_instance
    bot_instance = bot


def _secret_key():
    DATA.mkdir(parents=True, exist_ok=True)
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text(encoding='utf-8').strip() or secrets.token_hex(32)
    key = secrets.token_hex(32)
    SECRET_FILE.write_text(key, encoding='utf-8')
    try:
        os.chmod(SECRET_FILE, 0o600)
    except OSError:
        pass
    return key


app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = _secret_key()
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'


# ── access store (fresh file, no migration from old panel) ─────────────

def _load_access():
    if not ACCESS_FILE.exists():
        return {'users': []}
    try:
        data = json.loads(ACCESS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {'users': []}
    if not isinstance(data, dict):
        return {'users': []}
    users = data.get('users')
    if not isinstance(users, list):
        users = []
    return {'users': users}


def _save_access(data):
    DATA.mkdir(parents=True, exist_ok=True)
    ACCESS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        os.chmod(ACCESS_FILE, 0o600)
    except OSError:
        pass


def _env_owner_creds():
    user = (os.environ.get('PANEL_USER') or 'owner').strip() or 'owner'
    pw = (os.environ.get('PANEL_PASSWORD') or '').strip()
    return user, pw


def _hash_secret(raw: str) -> str:
    raw = str(raw or '')
    return hashlib.sha256(('hakumo|' + raw).encode('utf-8')).hexdigest()


def _secret_matches(stored, raw) -> bool:
    if stored is None or raw is None:
        return False
    stored = str(stored)
    raw = str(raw)
    if not stored or not raw:
        return False
    # поддержка старых plaintext + новых hash
    if stored == raw:
        return True
    return stored == _hash_secret(raw)


def _find_access_user(username: str):
    username = (username or '').strip()
    for u in _load_access()['users']:
        if str(u.get('username', '')).strip() == username:
            return u
    return None


def _auth_user(username, password):
    """Вернуть (username, role) или None."""
    username = (username or '').strip()
    password = password or ''
    if not username or not password:
        return None
    env_u, env_pw = _env_owner_creds()
    if env_pw and username == env_u and password == env_pw:
        return env_u, 'owner'
    u = _find_access_user(username)
    if not u:
        return None
    if not _secret_matches(u.get('password'), password):
        return None
    role = str(u.get('role') or 'mod').strip().lower()
    if role not in LEVEL or role == 'owner':
        role = 'mod'
    return username, role


def _auth_pin(username, pin):
    """Вернуть (username, role) или None. username может быть пустым."""
    pin = (pin or '').strip()
    if not pin or not pin.isdigit() or not (4 <= len(pin) <= 8):
        return None
    env_u, _ = _env_owner_creds()
    owner_pin = (os.environ.get('PANEL_PIN') or '').strip()
    users = list(_load_access()['users'])
    username = (username or '').strip()

    def _role_of(u):
        role = str((u or {}).get('role') or 'mod').strip().lower()
        if role not in LEVEL or role == 'owner':
            role = 'mod'
        return role

    if username:
        if owner_pin and username == env_u and pin == owner_pin:
            return env_u, 'owner'
        u = _find_access_user(username)
        if u and _secret_matches(u.get('pin'), pin):
            return username, _role_of(u)
        return None

    # PIN без логина — только если ровно один матч
    hits = []
    if owner_pin and pin == owner_pin:
        hits.append((env_u, 'owner'))
    for u in users:
        if _secret_matches(u.get('pin'), pin):
            hits.append((str(u.get('username') or '').strip(), _role_of(u)))
    hits = [h for h in hits if h[0]]
    if len(hits) == 1:
        return hits[0]
    return None


def _invite_ok(code: str) -> bool:
    want = (os.environ.get('PANEL_INVITE_CODE') or '').strip()
    return bool(want) and secrets.compare_digest(want, (code or '').strip())


def _recovery_ok(code: str) -> bool:
    want = (os.environ.get('PANEL_RECOVERY_CODE') or '').strip()
    if want and secrets.compare_digest(want, (code or '').strip()):
        return True
    # запас: пароль owner из .env
    _, env_pw = _env_owner_creds()
    return bool(env_pw) and secrets.compare_digest(env_pw, (code or '').strip())


def _upsert_access_user(*, username, password=None, pin=None, role='mod', note=''):
    data = _load_access()
    username = (username or '').strip()
    found = None
    for u in data['users']:
        if str(u.get('username', '')).strip() == username:
            found = u
            break
    if found is None:
        found = {'username': username, 'role': role or 'mod', 'note': note or ''}
        data['users'].append(found)
    if password is not None:
        found['password'] = _hash_secret(password)
    if pin is not None:
        pin = (pin or '').strip()
        if pin:
            found['pin'] = _hash_secret(pin)
        else:
            found.pop('pin', None)
    if role and role in LEVEL and role != 'owner':
        found['role'] = role
    if note is not None:
        found['note'] = note
    _save_access(data)
    return found


def _pages_for_role(role: str):
    keys = ROLE_PAGE_KEYS.get(role) or ROLE_PAGE_KEYS['helper']
    return [p for p in PAGES_ALL if p[0] in keys]


# ── Discord OAuth ──────────────────────────────────────────────────────

def _http_json(method, url, *, headers=None, form=None, timeout=12):
    data = None
    hdrs = dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode('utf-8')
        hdrs.setdefault('Content-Type', 'application/x-www-form-urlencoded')
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode('utf-8')
            payload = json.loads(body) if body else {}
        except Exception:
            payload = {}
        return e.code, payload
    except Exception as e:
        return 0, {'error': str(e)}


def _discord_client_creds():
    cid = (
        (os.environ.get('DISCORD_CLIENT_ID') or '').strip()
        or (os.environ.get('ACTIVITY_CLIENT_ID') or '').strip()
    )
    secret = (
        (os.environ.get('DISCORD_CLIENT_SECRET') or '').strip()
        or (os.environ.get('ACTIVITY_CLIENT_SECRET') or '').strip()
    )
    if not cid:
        token = (os.environ.get('TOKEN') or '').strip()
        if token:
            st, data = _http_json(
                'GET', f'{DISCORD_API}/oauth2/applications/@me',
                headers={'Authorization': f'Bot {token}'},
            )
            if st == 200 and data.get('id'):
                cid = str(data['id'])
    return cid, secret


def _discord_oauth_ready():
    cid, secret = _discord_client_creds()
    return bool(cid and secret)


def _panel_public_base():
    base = (os.environ.get('PANEL_URL') or '').strip().rstrip('/')
    if base:
        return base
    return (request.url_root or '').rstrip('/')


def _discord_redirect_uri():
    custom = (os.environ.get('DISCORD_REDIRECT_URI') or '').strip()
    if custom:
        return custom
    return f'{_panel_public_base()}/auth/discord/callback'


def _discord_avatar_url(user: dict) -> str:
    uid = str(user.get('id') or '')
    avatar = user.get('avatar')
    if uid and avatar:
        ext = 'gif' if str(avatar).startswith('a_') else 'png'
        return f'https://cdn.discordapp.com/avatars/{uid}/{avatar}.{ext}?size=128'
    try:
        idx = (int(uid) >> 22) % 6 if uid else 0
    except Exception:
        idx = 0
    return f'https://cdn.discordapp.com/embed/avatars/{idx}.png'


def _discord_handle(user: dict) -> str:
    uname = (user.get('username') or 'user').strip()
    disc = user.get('discriminator')
    if disc and str(disc) not in ('0', '0000'):
        return f'{uname}#{disc}'
    return uname


def _discord_display(user: dict) -> str:
    return (user.get('global_name') or user.get('username') or 'Discord').strip()


def _staff_role_id_set() -> dict:
    """Наборы Discord role id → уровень панели."""
    try:
        from services.staff_roles import (
            KNOWN_ADMIN_ROLE_ID, KNOWN_CURATOR_BY_KIND, KNOWN_CURATOR_ROLE_ID,
            KNOWN_HELPER_ROLE_ID, KNOWN_MASTER_ROLE_ID, KNOWN_MODERATOR_ROLE_ID,
            KNOWN_GRANT_BY_KIND,
        )
    except Exception:
        KNOWN_ADMIN_ROLE_ID = 1189999426631122964
        KNOWN_CURATOR_BY_KIND = {}
        KNOWN_CURATOR_ROLE_ID = 807030012301541377
        KNOWN_HELPER_ROLE_ID = 948969471916249119
        KNOWN_MASTER_ROLE_ID = 1552637932907667466
        KNOWN_MODERATOR_ROLE_ID = 803553848396349510
        KNOWN_GRANT_BY_KIND = {}

    def _env_rid(*names):
        out = set()
        for n in names:
            try:
                from config import Config
                v = int(getattr(Config, n, 0) or 0)
            except Exception:
                v = int(os.environ.get(n) or 0)
            if v:
                out.add(v)
        return out

    admin = {int(KNOWN_ADMIN_ROLE_ID)} | _env_rid()
    curator = {int(KNOWN_CURATOR_ROLE_ID)} | {
        int(v) for v in (KNOWN_CURATOR_BY_KIND or {}).values() if v
    } | _env_rid(
        'STAFF_CURATOR_ROLE_ID', 'STAFF_HELPER_CURATOR_ROLE_ID',
        'STAFF_MODERATOR_CURATOR_ROLE_ID', 'STAFF_EVENT_CURATOR_ROLE_ID',
        'STAFF_BROADCASTER_CURATOR_ROLE_ID',
    )
    mod = {int(KNOWN_MODERATOR_ROLE_ID), int(KNOWN_MASTER_ROLE_ID)} | _env_rid(
        'STAFF_MODERATOR_ROLE_ID',
    )
    # event/broadcaster → как mod для панели
    for k, rid in (KNOWN_GRANT_BY_KIND or {}).items():
        if k in ('event', 'broadcaster', 'moderator') and rid:
            mod.add(int(rid))
    helper = {int(KNOWN_HELPER_ROLE_ID)} | _env_rid('STAFF_HELPER_ROLE_ID')
    for k, rid in (KNOWN_GRANT_BY_KIND or {}).items():
        if k == 'helper' and rid:
            helper.add(int(rid))
    return {'admin': admin, 'curator': curator, 'mod': mod, 'helper': helper}


def resolve_discord_panel_role(discord_user_id, role_ids) -> str | None:
    """Высшая роль панели по Discord user id + role ids участника. None = нет доступа."""
    try:
        uid = int(discord_user_id)
    except Exception:
        return None
    try:
        from config import Config
        if uid in Config.all_owner_ids():
            return 'owner'
    except Exception:
        pass
    try:
        ids = {int(r) for r in (role_ids or []) if r is not None}
    except Exception:
        ids = set()
    bags = _staff_role_id_set()
    if ids & bags['admin']:
        return 'admin'
    if ids & bags['curator']:
        return 'curator'
    if ids & bags['mod']:
        return 'mod'
    if ids & bags['helper']:
        return 'helper'
    return None


def _fetch_guild_member_roles(discord_user_id: str):
    """Роли участника MAIN_GUILD через Bot token. (roles, error_text)."""
    token = (os.environ.get('TOKEN') or '').strip()
    if not token:
        return None, 'Нет TOKEN бота в .env'
    try:
        from config import Config
        gid = int(getattr(Config, 'MAIN_GUILD_ID', 0) or 0)
    except Exception:
        gid = int(os.environ.get('MAIN_GUILD_ID') or 0)
    if not gid:
        return None, 'Задайте MAIN_GUILD_ID в .env'
    st, data = _http_json(
        'GET',
        f'{DISCORD_API}/guilds/{gid}/members/{discord_user_id}',
        headers={'Authorization': f'Bot {token}'},
    )
    if st == 404:
        return None, 'Тебя нет на основном сервере бота'
    if st != 200:
        return None, f'Discord member API: {st}'
    roles = data.get('roles') or []
    return [str(r) for r in roles], ''


def _start_session(*, username, role, discord_user=None):
    session.clear()
    session['logged_in'] = True
    session['username'] = username
    session['role'] = role
    session['role_label'] = ROLE_LABELS.get(role, role)
    if discord_user:
        session['discord_id'] = str(discord_user.get('id') or '')
        session['discord_handle'] = _discord_handle(discord_user)
        session['discord_display'] = _discord_display(discord_user)
        session['discord_avatar'] = _discord_avatar_url(discord_user)
        session['auth_via'] = 'discord'
    else:
        session['discord_id'] = ''
        session['discord_handle'] = ''
        session['discord_display'] = username
        session['discord_avatar'] = ''
        session['auth_via'] = 'password'


# ── auth helpers ───────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if not session.get('logged_in'):
            return redirect(url_for('login', next=request.path))
        return f(*a, **kw)
    return wrapped


def role_required(min_role):
    need = LEVEL.get(min_role, 1)

    def deco(f):
        @wraps(f)
        def wrapped(*a, **kw):
            if not session.get('logged_in'):
                return redirect(url_for('login', next=request.path))
            have = LEVEL.get(session.get('role') or 'helper', 0)
            if have < need:
                abort(403)
            return f(*a, **kw)
        return wrapped
    return deco


@app.context_processor
def inject_nav():
    role = session.get('role') or ''
    pages = _pages_for_role(role) if role else []
    handle = session.get('discord_handle') or ''
    return {
        'nav_pages': pages,
        'user_name': session.get('discord_display') or session.get('username') or '',
        'user_handle': f'@{handle}' if handle else '',
        'user_avatar': session.get('discord_avatar') or '',
        'user_role': role,
        'user_role_label': session.get('role_label') or ROLE_LABELS.get(role, role),
        'is_owner': role == 'owner',
        'auth_via': session.get('auth_via') or '',
        'mod_nav_keys': {
            'today', 'logs', 'users', 'member', 'warns', 'appeals', 'proofs', 'reasons'},
        'owner_nav_keys': {'bot', 'modules', 'commands', 'anticrash', 'access'},
    }


# ── data readers (punish only) ─────────────────────────────────────────

def _main_guild():
    try:
        from config import Config
        return str(getattr(Config, 'MAIN_GUILD_ID', '') or '') or ''
    except Exception:
        return (os.environ.get('MAIN_GUILD_ID') or '').strip()


def _read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default if default is not None else {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return default if default is not None else {}


def _parse_ts(raw):
    if not raw:
        return None
    try:
        s = str(raw).strip().replace('Z', '+00:00')
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return None


def _punish_kind(action):
    a = str(action or '').lower()
    if not a:
        return ''
    if 'разбан' in a or 'unban' in a or 'бан снят' in a:
        return 'unban'
    if ('размут' in a or 'unmute' in a or 'untimeout' in a
            or 'мут снят' in a or 'таймаут снят' in a):
        return 'unmute'
    if 'бан' in a or a == 'ban' or a.endswith('_ban'):
        return 'ban'
    if 'кик' in a or 'kick' in a:
        return 'kick'
    if 'варн' in a or 'warn' in a or 'предупрежд' in a:
        return 'warn'
    if ('мут' in a or 'mute' in a or 'таймаут' in a or 'timeout' in a
            or 'vmute' in a):
        return 'mute'
    return ''


def _label(kind, raw=''):
    return {
        'ban': 'Бан', 'kick': 'Кик', 'warn': 'Варн', 'mute': 'Мут',
        'timeout': 'Таймаут', 'unban': 'Разбан', 'unmute': 'Размут',
    }.get(kind) or (raw or kind or '—')


def _collect_cases(gid_filter=''):
    """Дела панели + варны → список наказаний, новые сверху."""
    out = []
    md = _read_json(DATA / 'mod_data.json', {})
    cases = (md.get('cases') or md.get('case') or {}) if isinstance(md, dict) else {}
    for gid, rows in cases.items():
        if gid_filter and str(gid) != str(gid_filter):
            continue
        if not isinstance(rows, list):
            continue
        for c in rows:
            if not isinstance(c, dict):
                continue
            kind = _punish_kind(c.get('action'))
            if not kind:
                continue
            out.append({
                'guild_id': str(gid),
                'action': _label(kind, c.get('action')),
                'kind': kind,
                'user_id': str(c.get('user_id') or ''),
                'user_name': str(c.get('user_name') or c.get('user_id') or '—'),
                'mod_id': str(c.get('mod_id') or ''),
                'mod_name': str(c.get('mod_name') or c.get('mod_id') or '—'),
                'reason': str(c.get('reason') or '').strip() or 'без причины',
                'duration': c.get('duration_minutes') or c.get('duration') or '',
                'timestamp': c.get('timestamp') or '',
                'source': 'case',
            })
    wd = _read_json(DATA / 'warnings.json', {})
    if isinstance(wd, dict):
        for gid, users in wd.items():
            if gid_filter and str(gid) != str(gid_filter):
                continue
            if not isinstance(users, dict):
                continue
            for uid, wlist in users.items():
                if not isinstance(wlist, list):
                    continue
                for w in wlist:
                    if not isinstance(w, dict):
                        continue
                    out.append({
                        'guild_id': str(gid),
                        'action': 'Варн',
                        'kind': 'warn',
                        'user_id': str(uid),
                        'user_name': str(uid),
                        'mod_id': str(w.get('mod_id') or ''),
                        'mod_name': str(w.get('mod') or w.get('moderator') or '—'),
                        'reason': str(w.get('reason') or '').strip() or 'без причины',
                        'duration': '',
                        'timestamp': w.get('timestamp') or '',
                        'source': 'warnings',
                    })
    out.sort(key=lambda e: _parse_ts(e.get('timestamp'))
             or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return out


def _is_today(ts):
    d = _parse_ts(ts)
    if not d:
        return False
    now = datetime.now(timezone.utc).astimezone()
    local = d.astimezone()
    return local.date() == now.date()


def _fmt(ts):
    d = _parse_ts(ts)
    if not d:
        return '—'
    return d.astimezone().strftime('%d.%m %H:%M')


def _appeals_list(gid):
    try:
        from db import GuildData
        state = GuildData('appeals').get(gid or '0', 'state', {}) or {}
        items = state.get('items') if isinstance(state, dict) else []
        if not isinstance(items, list):
            return []
        return list(reversed(items[-100:]))
    except Exception:
        return []


def _reasons_bundle(gid):
    reasons, rules = [], []
    # json files first
    for p in DATA.glob(f'mod_reasons_{gid}.json') if gid else []:
        try:
            raw = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(raw, list):
                reasons = raw
            elif isinstance(raw, dict):
                reasons = raw.get('reasons') or raw.get('items') or []
        except Exception:
            pass
    for p in DATA.glob(f'rules_{gid}.json') if gid else []:
        try:
            raw = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(raw, list):
                rules = raw
            elif isinstance(raw, dict):
                rules = raw.get('rules') or raw.get('items') or []
        except Exception:
            pass
    try:
        from db import GuildData
        if gid:
            r = GuildData('mod_reasons').get(int(gid), 'reasons', None)
            if r:
                reasons = r if isinstance(r, list) else reasons
            ru = GuildData('rules').get(int(gid), 'rules', None)
            if ru:
                rules = ru if isinstance(ru, list) else rules
    except Exception:
        pass
    # fallback: any mod_reasons_*.json
    if not reasons:
        for p in sorted(DATA.glob('mod_reasons_*.json')):
            try:
                raw = json.loads(p.read_text(encoding='utf-8'))
                if isinstance(raw, list) and raw:
                    reasons = raw
                    break
                if isinstance(raw, dict):
                    reasons = raw.get('reasons') or raw.get('items') or []
                    if reasons:
                        break
            except Exception:
                continue
    if not rules:
        for p in sorted(DATA.glob('rules_*.json')):
            try:
                raw = json.loads(p.read_text(encoding='utf-8'))
                if isinstance(raw, list) and raw:
                    rules = raw
                    break
                if isinstance(raw, dict):
                    rules = raw.get('rules') or raw.get('items') or []
                    if rules:
                        break
            except Exception:
                continue
    return reasons or [], rules or []


def _proofs_list(gid):
    """Список из proof-конфига / последних дел с proof-ссылкой."""
    items = []
    cfg = _read_json(DATA / f'proof_config_{gid}.json', {}) if gid else {}
    if not cfg:
        for p in DATA.glob('proof_config_*.json'):
            cfg = _read_json(p, {})
            if cfg:
                break
    if isinstance(cfg, dict) and cfg:
        items.append({
            'title': 'Конфиг демок',
            'detail': json.dumps(cfg, ensure_ascii=False)[:240],
            'when': '',
        })
    for ev in _collect_cases(gid)[:80]:
        # proof links иногда в reason
        r = ev.get('reason') or ''
        if 'http' in r or 'discord.com' in r:
            items.append({
                'title': f"{ev['action']} · {ev['user_name']}",
                'detail': r[:200],
                'when': _fmt(ev.get('timestamp')),
            })
    return items[:50]


# ── routes: auth ───────────────────────────────────────────────────────

@app.route('/welcome')
def welcome():
    """Публичная витрина — отдельный gate-дизайн (auth-new.css)."""
    if session.get('logged_in'):
        return redirect(url_for('today'))
    return render_template('welcome.html')


def _safe_next(raw: str | None) -> str:
    nxt = raw or url_for('today')
    if not isinstance(nxt, str) or not nxt.startswith('/'):
        return url_for('today')
    return nxt


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('today'))
    mode = (request.values.get('mode') or 'password').strip().lower()
    if mode not in ('password', 'pin', 'register', 'forgot'):
        mode = 'password'
    err = (request.args.get('error') or '').strip()
    ok = ''
    nxt = _safe_next(request.args.get('next') or request.form.get('next'))

    if request.method == 'POST':
        mode = (request.form.get('mode') or mode).strip().lower()
        if mode == 'password':
            got = _auth_user(request.form.get('username', ''), request.form.get('password', ''))
            if got:
                _start_session(username=got[0], role=got[1])
                return redirect(nxt)
            err = 'Неверный логин или пароль'
        elif mode == 'pin':
            got = _auth_pin(request.form.get('username', ''), request.form.get('pin', ''))
            if got:
                _start_session(username=got[0], role=got[1])
                return redirect(nxt)
            err = 'Неверный PIN (или укажи логин, если PIN не уникален)'
        elif mode == 'register':
            invite = request.form.get('invite', '')
            username = (request.form.get('username') or '').strip()
            password = request.form.get('password') or ''
            pin = (request.form.get('pin') or '').strip()
            env_u, _ = _env_owner_creds()
            if not _invite_ok(invite):
                err = 'Неверный код приглашения (PANEL_INVITE_CODE)'
            elif len(username) < 3:
                err = 'Логин слишком короткий'
            elif len(password) < 6:
                err = 'Пароль минимум 6 символов'
            elif username == env_u:
                err = 'Этот логин занят владельцем'
            elif _find_access_user(username):
                err = 'Такой логин уже есть'
            elif pin and (not pin.isdigit() or not (4 <= len(pin) <= 8)):
                err = 'PIN — 4–8 цифр'
            else:
                _upsert_access_user(username=username, password=password, pin=pin or None, role='mod')
                _start_session(username=username, role='mod')
                return redirect(nxt)
        elif mode == 'forgot':
            username = (request.form.get('username') or '').strip()
            recovery = request.form.get('recovery', '')
            password = request.form.get('password') or ''
            pin = (request.form.get('pin') or '').strip()
            env_u, _ = _env_owner_creds()
            if not _recovery_ok(recovery):
                err = 'Неверный код восстановления'
            elif len(password) < 6:
                err = 'Новый пароль минимум 6 символов'
            elif pin and (not pin.isdigit() or not (4 <= len(pin) <= 8)):
                err = 'PIN — 4–8 цифр'
            elif username == env_u:
                err = 'Пароль owner меняй в .env (PANEL_PASSWORD)'
            elif not _find_access_user(username):
                err = 'Такого логина нет'
            else:
                _upsert_access_user(username=username, password=password, pin=pin if pin else None)
                ok = 'Пароль обновлён — теперь войди'
                mode = 'password'

    _, env_pw = _env_owner_creds()
    hint = '' if env_pw else 'Задайте PANEL_PASSWORD в .env'
    return render_template(
        'login.html',
        error=err,
        ok=ok,
        hint=hint,
        discord_ready=_discord_oauth_ready(),
        mode=mode,
        next=nxt,
    )


@app.route('/auth/discord')
def auth_discord():
    """Быстрый вход через Discord → роль с сервера (Helper/Mod/Curator/Admin/Owner)."""
    if session.get('logged_in'):
        return redirect(url_for('today'))
    cid, secret = _discord_client_creds()
    if not cid or not secret:
        return redirect(url_for(
            'login',
            error='Discord-вход не настроен: задай DISCORD_CLIENT_ID и DISCORD_CLIENT_SECRET в .env',
        ))
    state = secrets.token_urlsafe(24)
    session['oauth_state'] = state
    session['oauth_next'] = _safe_next(request.args.get('next'))
    params = {
        'client_id': cid,
        'response_type': 'code',
        'scope': 'identify',
        'redirect_uri': _discord_redirect_uri(),
        'state': state,
    }
    url = 'https://discord.com/api/oauth2/authorize?' + urllib.parse.urlencode(params)
    return redirect(url)


@app.route('/auth/discord/callback')
def auth_discord_callback():
    err = (request.args.get('error_description') or request.args.get('error') or '').strip()
    if err:
        return redirect(url_for('login', error=f'Discord: {err}'))
    state = request.args.get('state') or ''
    if not state or state != session.get('oauth_state'):
        return redirect(url_for('login', error='Сессия входа устарела — попробуй ещё раз'))
    code = request.args.get('code') or ''
    if not code:
        return redirect(url_for('login', error='Discord не вернул код'))
    cid, secret = _discord_client_creds()
    st, token_data = _http_json(
        'POST',
        'https://discord.com/api/oauth2/token',
        form={
            'client_id': cid,
            'client_secret': secret,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': _discord_redirect_uri(),
        },
    )
    if st != 200 or not token_data.get('access_token'):
        msg = token_data.get('error_description') or token_data.get('error') or f'HTTP {st}'
        return redirect(url_for('login', error=f'Токен Discord: {msg}'))
    st, user = _http_json(
        'GET',
        f'{DISCORD_API}/users/@me',
        headers={'Authorization': f"Bearer {token_data['access_token']}"},
    )
    if st != 200 or not user.get('id'):
        return redirect(url_for('login', error='Не удалось получить профиль Discord'))
    roles, role_err = _fetch_guild_member_roles(str(user['id']))
    if role_err:
        return redirect(url_for('login', error=role_err))
    panel_role = resolve_discord_panel_role(user['id'], roles)
    if not panel_role:
        handle = _discord_handle(user)
        return redirect(url_for(
            'login',
            error=f'@{handle}: нет staff-роли на сервере (Helper / Mod / Curator / Admin)',
        ))
    nxt = session.pop('oauth_next', None) or url_for('today')
    session.pop('oauth_state', None)
    _start_session(
        username=_discord_display(user),
        role=panel_role,
        discord_user=user,
    )
    return redirect(_safe_next(nxt))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('welcome'))


# ── routes: mod pages ──────────────────────────────────────────────────

@app.route('/')
@login_required
@role_required('helper')
def today():
    gid = _main_guild()
    rows = _collect_cases(gid)
    today_rows = [r for r in rows if _is_today(r.get('timestamp'))]
    kpi = {
        'actions': len(today_rows),
        'warns': sum(1 for r in today_rows if r['kind'] == 'warn'),
        'bans': sum(1 for r in today_rows if r['kind'] == 'ban'),
        'kicks': sum(1 for r in today_rows if r['kind'] == 'kick'),
        'mutes': sum(1 for r in today_rows if r['kind'] in ('mute', 'timeout')),
    }
    for r in today_rows:
        r['when'] = _fmt(r.get('timestamp'))
    return render_template('today.html', kpi=kpi, rows=today_rows[:30],
                           fmt=_fmt)


@app.route('/logs')
@login_required
@role_required('helper')
def logs():
    gid = _main_guild()
    rows = _collect_cases(gid)[:200]
    for r in rows:
        r['when'] = _fmt(r.get('timestamp'))
    return render_template('logs.html', rows=rows)


@app.route('/users')
@login_required
@role_required('helper')
def users_page():
    """Участники сервера + счётчики мер. Поиск по нику/нику Discord/ID."""
    gid = _main_guild()
    q = (request.args.get('q') or '').strip()
    ql = q.lower()
    names = {}

    # 1) живой кэш с Discord (бот в том же процессе)
    try:
        bot = bot_instance
        if bot and gid:
            guild = bot.get_guild(int(gid))
            if guild is not None:
                for m in guild.members:
                    label = (
                        getattr(m, 'display_name', None)
                        or getattr(m, 'global_name', None)
                        or getattr(getattr(m, 'name', None), '__str__', lambda: None)()
                        or str(m)
                    )
                    # discord.py Member: display_name, name, global_name, nick
                    parts = [
                        getattr(m, 'display_name', '') or '',
                        getattr(m, 'name', '') or '',
                        getattr(m, 'global_name', None) or '',
                        getattr(m, 'nick', None) or '',
                        str(m.id),
                    ]
                    names[str(m.id)] = parts[0] or parts[1] or str(m.id)
                    # stash searchable blob
                    names[str(m.id) + '::__q'] = ' '.join(p for p in parts if p).lower()
    except Exception:
        pass

    prefer = DATA / f'member_names_{gid}.json' if gid else None
    paths = [prefer] if prefer and prefer.exists() else []
    paths += [p for p in sorted(DATA.glob('member_names_*.json')) if p not in paths]
    for p in paths:
        raw = _read_json(p, {})
        if isinstance(raw, dict):
            for uid, name in raw.items():
                uid = str(uid)
                if uid.endswith('::__q'):
                    continue
                names.setdefault(uid, str(name))
                names.setdefault(uid + '::__q', f"{name} {uid}".lower())
        if any(not k.endswith('::__q') for k in names) and gid and prefer and p == prefer:
            break

    stats = {}
    for ev in _collect_cases(gid):
        uid = str(ev.get('user_id') or '')
        if not uid:
            continue
        st = stats.setdefault(uid, {
            'warns': 0, 'mutes': 0, 'bans': 0, 'kicks': 0, 'total': 0,
            'name': ev.get('user_name') or uid, 'last': ev.get('timestamp'),
        })
        st['total'] += 1
        k = ev.get('kind')
        if k == 'warn':
            st['warns'] += 1
        elif k in ('mute', 'timeout'):
            st['mutes'] += 1
        elif k == 'ban':
            st['bans'] += 1
        elif k == 'kick':
            st['kicks'] += 1
        if ev.get('user_name') and not str(ev.get('user_name')).isdigit():
            st['name'] = ev['user_name']
        names.setdefault(uid, st['name'])
        blob = names.get(uid + '::__q', '')
        names[uid + '::__q'] = (blob + ' ' + str(st['name']) + ' ' + uid).lower()

    # также подтянуть имена из варнов/мер если файл имён пуст
    uids = [k for k in names if not k.endswith('::__q')]
    for uid in list(stats.keys()):
        if uid not in names:
            names[uid] = stats[uid].get('name') or uid
            names[uid + '::__q'] = f"{names[uid]} {uid}".lower()
            uids.append(uid)

    rows = []
    for uid in uids:
        st = stats.get(uid) or {
            'warns': 0, 'mutes': 0, 'bans': 0, 'kicks': 0, 'total': 0, 'last': '',
        }
        display = names.get(uid) or st.get('name') or uid
        if str(display).isdigit() and st.get('name') and not str(st.get('name')).isdigit():
            display = st['name']
        blob = names.get(uid + '::__q') or f"{display} {uid}".lower()
        if ql:
            # частичный поиск: каждое слово q должно встретиться
            tokens = [t for t in ql.split() if t]
            if tokens and not all(tok in blob for tok in tokens):
                # также простая подстрока целиком
                if ql not in blob and ql not in uid:
                    continue
        rows.append({
            'user_id': uid,
            'name': display,
            'warns': st.get('warns', 0),
            'mutes': st.get('mutes', 0),
            'bans': st.get('bans', 0),
            'kicks': st.get('kicks', 0),
            'total': st.get('total', 0),
            'last': _fmt(st.get('last')),
        })
    rows.sort(key=lambda r: (-r['total'], str(r['name']).lower()))
    return render_template('users.html', rows=rows[:300], q=q)


@app.route('/member')
@login_required
@role_required('helper')
def member():
    q = (request.args.get('q') or '').strip()
    rows = []
    if q:
        gid = _main_guild()
        all_rows = _collect_cases(gid)
        ql = q.lower()
        # если ввели ник — резолвим в id через гильдию
        extra_ids = set()
        try:
            bot = bot_instance
            if bot and gid and not q.isdigit():
                guild = bot.get_guild(int(gid))
                if guild is not None:
                    for m in guild.members:
                        blob = ' '.join([
                            getattr(m, 'display_name', '') or '',
                            getattr(m, 'name', '') or '',
                            getattr(m, 'global_name', None) or '',
                            getattr(m, 'nick', None) or '',
                        ]).lower()
                        if ql in blob or all(t in blob for t in ql.split() if t):
                            extra_ids.add(str(m.id))
        except Exception:
            pass
        for r in all_rows:
            uid = str(r.get('user_id', ''))
            uname = str(r.get('user_name', '')).lower()
            if (ql in uid or ql in uname or uid in extra_ids
                    or all(t in uname for t in ql.split() if t)):
                r = dict(r)
                r['when'] = _fmt(r.get('timestamp'))
                rows.append(r)
                if len(rows) >= 100:
                    break
    return render_template('member.html', q=q, rows=rows)


@app.route('/warns')
@login_required
@role_required('helper')
def warns():
    gid = _main_guild()
    rows = [r for r in _collect_cases(gid) if r['kind'] == 'warn'][:200]
    for r in rows:
        r['when'] = _fmt(r.get('timestamp'))
    return render_template('warns.html', rows=rows)


@app.route('/appeals')
@login_required
@role_required('mod')
def appeals():
    gid = _main_guild()
    items = _appeals_list(gid)
    view = []
    for it in items:
        view.append({
            'id': it.get('id') or it.get('case_id') or '—',
            'user': it.get('user_name') or it.get('user_id') or '—',
            'status': it.get('status') or '—',
            'reason': (it.get('reason') or it.get('text') or '')[:160],
            'when': _fmt(it.get('created_at') or it.get('timestamp')),
            'mod': it.get('reviewed_by') or '—',
        })
    return render_template('appeals.html', rows=view)


@app.route('/proofs')
@login_required
@role_required('mod')
def proofs():
    gid = _main_guild()
    return render_template('proofs.html', rows=_proofs_list(gid))


@app.route('/reasons')
@login_required
@role_required('mod')
def reasons():
    gid = _main_guild()
    reasons, rules = _reasons_bundle(gid)
    return render_template('reasons.html', reasons=reasons, rules=rules)


# ── routes: owner-only bot pages ───────────────────────────────────────

@app.route('/bot')
@login_required
@role_required('admin')
def bot_page():
    info = {
        'online': False,
        'name': '—',
        'id': '—',
        'latency': '—',
        'guilds': [],
    }
    bot = bot_instance
    if bot is not None and getattr(bot, 'user', None):
        info['online'] = True
        info['name'] = str(bot.user)
        info['id'] = str(bot.user.id)
        try:
            info['latency'] = f'{round(bot.latency * 1000)} ms'
        except Exception:
            info['latency'] = '—'
        try:
            info['guilds'] = [
                {'id': str(g.id), 'name': g.name, 'members': getattr(g, 'member_count', None) or '—'}
                for g in list(bot.guilds)[:30]
            ]
        except Exception:
            pass
    else:
        # fallback file pulse
        st = _read_json(DATA / 'bot_state.json', {})
        if isinstance(st, dict) and st:
            info['online'] = str(st.get('status') or '').lower() in ('online', 'ready', 'ok')
            info['name'] = st.get('name') or st.get('username') or '—'
            info['latency'] = st.get('latency_ms') or st.get('latency') or '—'
    return render_template('bot.html', info=info)


@app.route('/modules')
@login_required
@role_required('admin')
def modules():
    rows = []
    bot = bot_instance
    if bot is not None:
        try:
            for name, cog in sorted(bot.cogs.items()):
                rows.append({'name': name, 'cls': type(cog).__name__})
        except Exception:
            pass
    if not rows:
        # list files only
        cogs_dir = ROOT / 'cogs'
        for p in sorted(cogs_dir.glob('*.py')):
            if p.name.startswith('_'):
                continue
            rows.append({'name': p.stem, 'cls': '(файл)'})
    return render_template('modules.html', rows=rows)


@app.route('/commands')
@login_required
@role_required('admin')
def commands_page():
    rows = []
    bot = bot_instance
    if bot is not None:
        try:
            for cmd in sorted(bot.tree.get_commands(), key=lambda c: c.name):
                rows.append({
                    'name': f'/{cmd.name}',
                    'desc': (getattr(cmd, 'description', None) or '')[:120],
                })
        except Exception:
            pass
    return render_template('commands.html', rows=rows)


def _anticrash_handler():
    bot = bot_instance
    if not bot:
        return None
    return getattr(bot, 'error_handler', None)


@app.route('/anticrash', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def anticrash_page():
    """Антикраш сервера: щит, антирейд, security, watchdog. Всё opt-in."""
    from web import protection as P
    gid = P.gid_int(_main_guild())
    err = ''
    if request.method == 'POST':
        action = (request.form.get('action') or '').strip()
        try:
            if action == 'kill_all':
                P.kill_all_protections(gid, bot_instance)
                flash('Все защиты выключены', 'ok')
                return redirect(url_for('anticrash_page'))

            system = (request.form.get('system') or '').strip()
            key = (request.form.get('key') or '').strip()
            raw = request.form.get('value')

            if system == 'guardian':
                gu = P.load_guardian(gid)
                if key == 'enabled':
                    gu['enabled'] = raw == '1'
                elif key == 'kick_unauthorized_bots':
                    gu['kick_unauthorized_bots'] = raw == '1'
                elif key == 'punishment':
                    gu['punishment'] = str(raw or 'strip')
                elif key.startswith('event:'):
                    ek = key.split(':', 1)[1]
                    ev = (gu.get('events') or {}).setdefault(ek, {'enabled': False})
                    ev['enabled'] = raw == '1'
                if gid:
                    P.save_guardian(gid, gu)
                flash('Щит сервера обновлён', 'ok')
                return redirect(url_for('anticrash_page'))

            if system == 'antiraid':
                ar = P.load_antiraid(gid)
                if key in ('min_age', 'join_threshold', 'join_window', 'alert_channel_id'):
                    try:
                        ar[key] = int(raw or 0)
                    except Exception:
                        ar[key] = 0
                elif key == 'raid_action':
                    ar[key] = str(raw or 'alert')
                else:
                    ar[key] = raw == '1'
                if gid:
                    P.save_antiraid(gid, ar)
                flash('Антирейд обновлён', 'ok')
                return redirect(url_for('anticrash_page'))

            if system == 'security':
                sec = P.load_security(gid)
                if key in ('ai_spam', 'fake_account', 'link_scanner'):
                    sec[key] = raw == '1'
                elif key == 'new_account_days':
                    sec[key] = max(0, int(raw or 0))
                elif key == 'new_account_action':
                    sec[key] = str(raw or 'warn')
                if gid:
                    P.save_security(gid, sec)
                flash('Security обновлён', 'ok')
                return redirect(url_for('anticrash_page'))

            if system == 'bot':
                from error_handler import DEFAULT_CONFIG
                eh = _anticrash_handler()
                if key not in DEFAULT_CONFIG:
                    err = 'Неизвестный ключ'
                elif eh:
                    val = (raw == '1') if isinstance(DEFAULT_CONFIG[key], bool) else raw
                    eh.update_config(key, val)
                    flash('Watchdog бота обновлён', 'ok')
                    return redirect(url_for('anticrash_page'))
                else:
                    cfg = P.read_json(DATA / 'anticrash_config.json', {})
                    if not isinstance(cfg, dict):
                        cfg = {}
                    cfg[key] = (raw == '1') if isinstance(DEFAULT_CONFIG[key], bool) else raw
                    DATA.mkdir(parents=True, exist_ok=True)
                    (DATA / 'anticrash_config.json').write_text(
                        json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
                    flash('Записано на диск (бот офлайн)', 'ok')
                    return redirect(url_for('anticrash_page'))
        except Exception as ex:
            err = str(ex)

    snap = P.snapshot(gid, bot_instance)
    return render_template(
        'anticrash.html',
        gid=gid or '—',
        snap=snap,
        error=err,
        bot_toggles=[
            'master_enabled', 'alerts_enabled', 'loop_watchdog', 'cog_breaker',
            'filter_enabled', 'connection_watch', 'warning_monitor', 'webhook_enabled',
        ],
        ar_flags=[
            ('join_raid', 'Анти-рейд входов', 'Пачка входов за окно → тревога/мера'),
            ('bot_protection', 'Защита от ботов', 'Чужие боты без разрешения'),
            ('webhook_protection', 'Защита вебхуков', 'Массовое создание вебхуков'),
            ('delete_protection', 'Массовое удаление', 'Снос сообщений/каналов пачкой'),
            ('age_filter', 'Возраст аккаунта', 'Слишком новые аккаунты'),
        ],
        sec_flags=[
            ('ai_spam', 'AI-спам', 'Подозрительный спам-текст'),
            ('fake_account', 'Фейк-аккаунты', 'Подозрительные ники/клоны'),
            ('link_scanner', 'Сканер ссылок', 'Опасные / фишинговые ссылки'),
        ],
    )


@app.route('/access', methods=['GET', 'POST'])
@login_required
@role_required('owner')
def access_page():
    """Категория «Доступ» с нуля: кто входит и что видит."""
    data = _load_access()
    err = ''
    if request.method == 'POST':
        action = request.form.get('action') or ''
        if action == 'add':
            username = (request.form.get('username') or '').strip()
            password = request.form.get('password') or ''
            pin = (request.form.get('pin') or '').strip()
            note = (request.form.get('note') or '').strip()[:80]
            if not username or not password:
                err = 'Нужны логин и пароль'
            elif username == _env_owner_creds()[0]:
                err = 'Этот логин занят владельцем (.env)'
            elif any(u.get('username') == username for u in data['users']):
                err = 'Такой логин уже есть'
            elif pin and (not pin.isdigit() or not (4 <= len(pin) <= 8)):
                err = 'PIN — 4–8 цифр'
            else:
                _upsert_access_user(
                    username=username, password=password,
                    pin=pin or None, role='mod', note=note)
                flash('Модератору выдан вход', 'ok')
                return redirect(url_for('access_page'))
        elif action == 'del':
            username = (request.form.get('username') or '').strip()
            data['users'] = [u for u in data['users'] if u.get('username') != username]
            _save_access(data)
            flash('Доступ снят', 'ok')
            return redirect(url_for('access_page'))
    env_u, _ = _env_owner_creds()
    return render_template(
        'access.html',
        users=data['users'],
        owner_user=env_u,
        error=err,
        role_cards=ROLE_CARDS,
        discord_ready=_discord_oauth_ready(),
    )


@app.errorhandler(403)
def forbidden(_e):
    return render_template(
        'error.html', code=403,
        text='Недостаточно прав для этой страницы.',
    ), 403


@app.get('/health')
def health():
    return jsonify({'ok': True, 'panel': 'mod-core-v2'})
