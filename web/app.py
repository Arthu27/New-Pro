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
import asyncio
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask, abort, flash, g, jsonify, redirect, render_template,
    request, send_from_directory, session, url_for,
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
    ('staff', '/staff', 'Staff', 'fa-user-shield'),
    ('users', '/users', 'Участники', 'fa-users'),
    ('member', '/member', 'Участник', 'fa-user'),
    ('channels', '/channels', 'Каналы', 'fa-table'),
    ('warns', '/warns', 'Варны', 'fa-triangle-exclamation'),
    ('appeals', '/appeals', 'Апелляции', 'fa-scale-balanced'),
    ('proofs', '/proofs', 'Демки', 'fa-camera'),
    ('reasons', '/reasons', 'Правила', 'fa-scroll'),
    ('bot', '/bot', 'Бот', 'fa-robot'),
    ('modules', '/modules', 'Модули', 'fa-puzzle-piece'),
    ('commands', '/commands', 'Команды', 'fa-terminal'),
    ('anticrash', '/anticrash', 'Антикраш', 'fa-shield-heart'),
    ('access', '/access', 'Доступ', 'fa-key'),
]
PAGES_MOD = [p for p in PAGES_ALL if p[0] in {
    'today', 'logs', 'staff', 'users', 'member', 'channels',
    'warns', 'appeals', 'proofs', 'reasons'}]
PAGES_OWNER = [p for p in PAGES_ALL if p[0] in {
    'bot', 'modules', 'commands', 'anticrash', 'access'}]

# Какие ключи страниц видит роль (накопительно по уровню)
# Admin НЕ видит бот/модули/команды — только owner.
# Helper видит Правила (не причины наказаний как отдельный список).
ROLE_PAGE_KEYS = {
    'helper': {'today', 'logs', 'staff', 'users', 'member', 'warns', 'reasons'},
    'mod': {
        'today', 'logs', 'staff', 'users', 'member', 'channels',
        'warns', 'appeals', 'proofs', 'reasons',
    },
    'curator': {
        'today', 'logs', 'staff', 'users', 'member', 'channels',
        'warns', 'appeals', 'proofs', 'reasons',
    },
    'admin': {
        'today', 'logs', 'staff', 'users', 'member', 'channels',
        'warns', 'appeals', 'proofs', 'reasons', 'anticrash',
    },
    'owner': {p[0] for p in PAGES_ALL},
}

# Меры, которые роль может ВЫДАТЬ из панели
ROLE_PUNISH_ACTIONS = {
    'helper': ('warn', 'mute'),
    'mod': ('warn', 'mute', 'kick', 'ban'),
    'curator': ('warn', 'mute', 'kick', 'ban'),
    'admin': ('warn', 'mute', 'kick', 'ban'),
    'owner': ('warn', 'mute', 'kick', 'ban'),
}
# Виды в журнале/истории, которые роль НЕ видит
ROLE_HIDDEN_KINDS = {
    'helper': frozenset({'ban', 'kick'}),
    'mod': frozenset(),
    'curator': frozenset(),
    'admin': frozenset(),
    'owner': frozenset(),
}
PUNISH_LABELS = {
    'warn': 'Варн',
    'mute': 'Мут',
    'kick': 'Кик',
    'ban': 'Бан',
}

ROLE_CARDS = [
    {
        'key': 'helper',
        'title': 'Helper',
        'tag': '@Helper',
        'blurb': 'Варн/мут с лимитами. Бан и кик скрыты. Правила — можно.',
        'pages': ['Сегодня', 'Журнал', 'Staff', 'Участники', 'Варны', 'Правила'],
    },
    {
        'key': 'mod',
        'title': 'Moderator',
        'tag': '@Moderator',
        'blurb': 'Полная мод-панель: апелляции, демки, каналы, правила.',
        'pages': ['Всё у Helper', '+ Каналы', 'Апелляции', 'Демки', 'Правила'],
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
        'blurb': 'Мод-панель + антикраш. Без бота/модулей/команд.',
        'pages': ['Мод-панель', 'Антикраш'],
    },
    {
        'key': 'owner',
        'title': 'Owner',
        'tag': '@Owner',
        'blurb': 'Полный доступ, включая бота и Доступ.',
        'pages': ['Всё', '+ Бот', 'Модули', 'Команды', 'Доступ'],
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


@app.after_request
def _auth_static_headers(resp):
    try:
        path = request.path or ''
    except Exception:
        return resp
    if path.startswith('/static/auth-new.css') or path in ('/login', '/welcome'):
        resp.headers['Cache-Control'] = 'no-store, max-age=0'
    # Ошибку не запоминать: иначе чужой браузер и Discord часами показывают старый 404.
    if resp.status_code >= 400:
        resp.headers['Cache-Control'] = 'no-store, max-age=0'
        resp.headers['CDN-Cache-Control'] = 'no-store'
    return resp


# Публичные шаблоны профилей. Без логина и без флага «выключить»:
# profile-card / most-active / couple-card всегда отдаются.
# Файлы лежат вне git (data/ + /var/lib/hakumo/profiles), деплой их не сносит.
_PROFILE_PUBLIC = frozenset({
    'index.html',
    'profile-card.png',
    'most-active.png',
    'couple-card.png',
})


def _profiles_folder() -> str:
    try:
        from services.profile_templates import profiles_dir
        return str(profiles_dir())
    except Exception:
        folder = DATA / 'profile_templates'
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder)


def _public_file(folder: str, name: str, *, mimetype: str | None = None):
    """Картинка для чужого браузера и Discord: не скачивание и не закрытый ресурс."""
    kwargs = {'mimetype': mimetype} if mimetype else {}
    resp = send_from_directory(folder, name, **kwargs)
    resp.headers.pop('Content-Disposition', None)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Cross-Origin-Resource-Policy'] = 'cross-origin'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Cache-Control'] = 'public, max-age=300, must-revalidate'
    return resp


@app.route('/profiles')
@app.route('/profiles/')
def profiles_gallery():
    folder = _profiles_folder()
    return _public_file(folder, 'index.html', mimetype='text/html')


@app.route('/profiles/<path:filename>')
def profiles_file(filename):
    """Короткие ссылки: /profiles/couple-card.png и соседние карточки."""
    name = os.path.basename(str(filename or '').replace('\\', '/'))
    if name not in _PROFILE_PUBLIC:
        abort(404)
    return _public_file(_profiles_folder(), name)


try:
    from services.profile_templates import ensure_profile_templates as _ensure_profiles
    _ensure_profiles(overwrite=False)
except Exception as _prof_ex:
    import logging
    logging.getLogger('profile_templates').debug('ensure: %s', _prof_ex)


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
    got = (code or '').strip()
    if not want or not got:
        return False
    a, b = want.casefold(), got.casefold()
    if len(a) != len(b):
        return False
    return secrets.compare_digest(a, b)


def _recovery_ok(code: str) -> bool:
    want = (os.environ.get('PANEL_RECOVERY_CODE') or '').strip()
    got = (code or '').strip()
    if want and got:
        a, b = want.casefold(), got.casefold()
        if len(a) == len(b) and secrets.compare_digest(a, b):
            return True
    # запас: пароль owner из .env
    _, env_pw = _env_owner_creds()
    return bool(env_pw) and secrets.compare_digest(env_pw, (code or '').strip())


def _upsert_access_user(*, username, password=None, pin=None, role='mod', note='',
                        discord_id=None, display_name=None, avatar=None):
    data = _load_access()
    username = (username or '').strip()
    found = None
    for u in data['users']:
        if str(u.get('username', '')).strip() == username:
            found = u
            break
        if discord_id and str(u.get('discord_id') or '') == str(discord_id):
            found = u
            break
    if found is None:
        found = {'username': username, 'role': role or 'mod', 'note': note or ''}
        data['users'].append(found)
    if username:
        found['username'] = username
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
    if discord_id:
        found['discord_id'] = str(discord_id)
    if display_name:
        found['display_name'] = str(display_name)
    if avatar:
        found['avatar'] = str(avatar)
    _save_access(data)
    return found


def _pages_for_role(role: str):
    keys = ROLE_PAGE_KEYS.get(role) or ROLE_PAGE_KEYS['helper']
    return [p for p in PAGES_ALL if p[0] in keys]


def _session_discord_role_ids():
    """Роли Discord текущего пользователя панели (для staff_limits)."""
    uid = str(session.get('discord_id') or '').strip()
    if not uid.isdigit():
        return []
    m = _find_guild_member(uid)
    if m is None:
        return []
    try:
        return [int(r.id) for r in (getattr(m, 'roles', None) or []) if getattr(r, 'id', None)]
    except Exception:
        return []


def _viewer_punish_actions(role: str | None = None):
    role = role or session.get('role') or 'helper'
    return list(ROLE_PUNISH_ACTIONS.get(role) or ROLE_PUNISH_ACTIONS['helper'])


def _viewer_hidden_kinds(role: str | None = None):
    role = role or session.get('role') or 'helper'
    return ROLE_HIDDEN_KINDS.get(role) or frozenset()


def _filter_cases_for_viewer(rows):
    """Скрыть наказания, которые роль не должна видеть."""
    hidden = _viewer_hidden_kinds()
    if not hidden:
        return list(rows or [])
    out = []
    for r in rows or []:
        kind = str((r or {}).get('kind') or '').lower()
        if kind in hidden:
            continue
        out.append(r)
    return out


def _viewer_is_limit_exempt(role: str | None = None) -> bool:
    """Owner панели / OWNER_ID бота — без квот в UI и на /api/punish."""
    role = role or session.get('role') or 'helper'
    if role == 'owner':
        return True
    uid = str(session.get('discord_id') or '').strip()
    if uid.isdigit():
        try:
            from config import Config
            if int(uid) in Config.all_owner_ids():
                return True
        except Exception:
            pass
    return False


def _viewer_limits_card():
    """Карточка лимитов для шапки/страниц — чётко: что можно и сколько осталось."""
    role = session.get('role') or 'helper'
    # Владелец не должен видеть чужие квоты хелпера/куратора
    if _viewer_is_limit_exempt(role):
        return {
            'role': role,
            'role_label': ROLE_LABELS.get(role, role),
            'actions': _viewer_punish_actions(role),
            'slots': [],
            'can_punish': True,
            'show': False,
            'exempt': True,
        }
    gid = _main_guild()
    uid = str(session.get('discord_id') or '').strip() or '0'
    allowed = _viewer_punish_actions(role)
    hidden = _viewer_hidden_kinds(role)
    items = []
    lim_map, win_map = {}, {}
    try:
        from services.staff_limits import (
            check_limit, effective_limits, human_window, ACTION_TITLES,
        )
        role_ids = _session_discord_role_ids()
        if gid:
            lim_map, win_map = effective_limits(gid, role_ids)
        for key in ('warn', 'mute', 'kick', 'ban'):
            title = PUNISH_LABELS.get(key) or ACTION_TITLES.get(key, key)
            if key in hidden or key not in allowed:
                items.append({
                    'key': key,
                    'title': title,
                    'locked': True,
                    'used': 0,
                    'limit': 0,
                    'left': 0,
                    'window': '',
                    'hint': 'недоступно твоей роли',
                })
                continue
            limit = int(lim_map.get(key) or 0)
            if limit <= 0:
                items.append({
                    'key': key,
                    'title': title,
                    'locked': False,
                    'used': 0,
                    'limit': 0,
                    'left': None,
                    'window': '',
                    'hint': 'без лимита',
                })
                continue
            _ok, used, lim = check_limit(gid, uid, key, 1, role_ids)
            used = int(used or 0)
            lim = int(lim or limit)
            items.append({
                'key': key,
                'title': title,
                'locked': False,
                'used': used,
                'limit': lim,
                'left': max(0, lim - used),
                'window': human_window(win_map.get(key) or 86400),
                'hint': f'{used}/{lim} за {human_window(win_map.get(key) or 86400)}',
            })
    except Exception:
        for key in ('warn', 'mute', 'kick', 'ban'):
            title = PUNISH_LABELS.get(key, key)
            locked = key in hidden or key not in allowed
            items.append({
                'key': key,
                'title': title,
                'locked': locked,
                'used': 0,
                'limit': 0,
                'left': 0 if locked else None,
                'window': '',
                'hint': 'недоступно' if locked else '—',
            })
    # Карточка только если есть РЕАЛЬНЫЕ квоты (не «замок» на чужих мерах)
    has_quota = any(
        (not it.get('locked')) and (it.get('limit') or 0) > 0
        for it in items)
    return {
        'role': role,
        'role_label': ROLE_LABELS.get(role, role),
        'actions': allowed,
        'slots': items,
        'can_punish': bool(allowed),
        'show': has_quota,
        'exempt': False,
    }


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
    limits = _viewer_limits_card() if session.get('logged_in') else None
    badges = {}
    if session.get('logged_in') and LEVEL.get(role, 0) >= LEVEL['mod']:
        try:
            pend = sum(
                1 for it in _appeals_list(_main_guild())
                if str(it.get('status') or '').lower() in ('pending', 'open', 'new', 'ожидает', '')
            )
            if pend:
                badges['appeals'] = pend
        except Exception:
            pass
    return {
        'nav_badges': badges,
        'nav_pages': pages,
        'user_name': session.get('discord_display') or session.get('username') or '',
        'user_handle': f'@{handle}' if handle else '',
        'user_avatar': session.get('discord_avatar') or '',
        'user_role': role,
        'user_role_label': session.get('role_label') or ROLE_LABELS.get(role, role),
        'is_owner': role == 'owner',
        'auth_via': session.get('auth_via') or '',
        'mod_nav_keys': {
            'today', 'logs', 'staff', 'users', 'member', 'channels',
            'warns', 'appeals', 'proofs', 'reasons'},
        'owner_nav_keys': {'bot', 'modules', 'commands', 'anticrash', 'access'},
        'viewer_limits': limits,
        'punish_actions': _viewer_punish_actions(role) if role else [],
        'punish_labels': PUNISH_LABELS,
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
    if 'appeal_reject' in a or ('апелляц' in a and 'отклон' in a):
        return 'appeal_reject'
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
        'appeal_reject': 'Апелляция · отклонена',
    }.get(kind) or (raw or kind or '—')


def _proof_name_hints(gid_filter=''):
    """Имена из демок — часто единственный след после бана (юзер ушёл)."""
    hints = {}
    paths = []
    if gid_filter:
        p = DATA / f'modproof_{gid_filter}.json'
        if p.exists():
            paths.append(p)
    if not paths:
        paths = sorted(DATA.glob('modproof_*.json'))
    for p in paths:
        raw = _read_json(p, {})
        items = (raw.get('items') or {}) if isinstance(raw, dict) else {}
        for e in items.values() if isinstance(items, dict) else []:
            if not isinstance(e, dict):
                continue
            for key_id, key_name in (
                    ('user_id', 'user_name'), ('mod_id', 'mod_name')):
                uid = str(e.get(key_id) or '').strip()
                nm = str(e.get(key_name) or '').strip()
                if uid.isdigit() and nm and not nm.isdigit() and nm.lower() not in ('none', 'null'):
                    hints.setdefault(uid, nm)
    return hints


def _appeal_name_hints(gid_filter=''):
    """Имена из апелляций (автор + кто решил)."""
    hints = {}
    try:
        items = _appeals_list(gid_filter) if gid_filter else []
    except Exception:
        items = []
    for e in items:
        if not isinstance(e, dict):
            continue
        for key_id, key_name in (
                ('user_id', 'user_name'),
                ('reviewer_id', 'reviewed_by'),
                ('mod_id', 'mod_name')):
            uid = str(e.get(key_id) or '').strip()
            nm = str(e.get(key_name) or '').strip()
            if uid.isdigit() and nm and not nm.isdigit() and nm.lower() not in ('none', 'null'):
                hints.setdefault(uid, nm)
    return hints


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
                        'user_name': str(w.get('user_name') or uid),
                        'mod_id': str(w.get('mod_id') or ''),
                        'mod_name': str(w.get('mod') or w.get('moderator') or '—'),
                        'reason': str(w.get('reason') or '').strip() or 'без причины',
                        'duration': '',
                        'timestamp': w.get('timestamp') or '',
                        'source': 'warnings',
                    })
    out.sort(key=lambda e: _parse_ts(e.get('timestamp'))
             or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    book = _namebook(gid_filter)
    book.update(_proof_name_hints(gid_filter))
    book.update(_appeal_name_hints(gid_filter))
    for row in out:
        row['user_name'] = _best_name(row.get('user_name'), row.get('user_id'), book)
        row['mod_name'] = _best_name(row.get('mod_name'), row.get('mod_id'), book)
    return out


def _namebook(gid=''):
    """id → отображаемое имя: живой кэш Discord и сохранённые ники."""
    book = {}
    gid = str(gid or _main_guild() or '')
    try:
        bot = bot_instance
        if bot and gid:
            guild = bot.get_guild(int(gid))
            if guild is not None:
                for m in list(getattr(guild, 'members', []) or []):
                    name = (
                        getattr(m, 'display_name', None)
                        or getattr(m, 'global_name', None)
                        or getattr(m, 'name', None)
                        or str(m.id)
                    )
                    book[str(m.id)] = str(name)
    except Exception:
        pass
    paths = []
    prefer = DATA / f'member_names_{gid}.json' if gid else None
    if prefer and prefer.exists():
        paths.append(prefer)
    for p in sorted(DATA.glob('member_names_*.json')):
        if p not in paths:
            paths.append(p)
    for p in paths:
        raw = _read_json(p, {})
        if not isinstance(raw, dict):
            continue
        for uid, name in raw.items():
            uid = str(uid)
            if uid.endswith('::__q'):
                continue
            label = str(name or '').strip()
            if label and not label.isdigit():
                book.setdefault(uid, label)
    return book


def _is_id(value) -> bool:
    """Discord snowflake, не короткий числовой ник."""
    s = str(value or '').strip()
    return s.isdigit() and len(s) >= 15


def _best_name(primary, secondary, book, fallback='—'):
    """Имя вместо голого Discord ID. Уже готовое имя не затираем."""
    p = str(primary or '').strip()
    s = str(secondary or '').strip()
    if p.lower() in ('none', 'null'):
        p = ''
    if s.lower() in ('none', 'null'):
        s = ''
    # сначала книга имён (даже короткий тестовый id / snowflake)
    for raw in (p, s):
        if raw.isdigit() and raw in book:
            label = str(book[raw] or '').strip()
            if label and not label.isdigit() and label.lower() not in ('none', 'null'):
                return label
    if p and not p.isdigit() and p not in ('—', '-'):
        return p
    if s and not s.isdigit() and s not in ('—', '-'):
        return s
    # лучше показать snowflake, чем пустое «—» в журнале банов
    if _is_id(s) or (s.isdigit() and len(s) >= 15):
        return s
    if _is_id(p) or (p.isdigit() and len(p) >= 15):
        return p
    if s.isdigit():
        return s
    if p.isdigit():
        return p
    return fallback


def _mod_activity(gid, days):
    """Сколько мер каждый модератор выдал за N дней."""
    from datetime import timedelta
    edge = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
    hidden = _viewer_hidden_kinds()
    stats = {}
    for r in _collect_cases(gid):
        if r.get('kind') in hidden:
            continue
        ts = _parse_ts(r.get('timestamp'))
        if ts is None or ts < edge:
            continue
        key = str(r.get('mod_id') or r.get('mod_name') or '—')
        st = stats.setdefault(key, {
            'id': str(r.get('mod_id') or '') if str(r.get('mod_id') or '').isdigit() else '',
            'name': r.get('mod_name') or '—',
            'warns': 0, 'mutes': 0, 'kicks': 0, 'bans': 0, 'total': 0,
        })
        st['total'] += 1
        k = r.get('kind')
        if k == 'warn':
            st['warns'] += 1
        elif k in ('mute', 'timeout'):
            st['mutes'] += 1
        elif k == 'kick':
            st['kicks'] += 1
        elif k == 'ban':
            st['bans'] += 1
    return sorted(stats.values(), key=lambda x: (-x['total'], str(x['name']).lower()))


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
    """Правила/причины: каталог mod_reasons (1.1–1.9) + опциональные JSON."""
    reasons, rules = [], []

    # 1) каноничный каталог бота — то, что в /modpanel
    try:
        from services.mod_reasons import select_options_data, rules_for_channel
        catalog = select_options_data()
        for row in catalog:
            reasons.append({
                'code': row.get('value') or '',
                'title': row.get('title') or row.get('label') or '',
                'text': row.get('text') or '',
                'punish': row.get('punish') or '',
                'duration': row.get('duration') or '',
                'actions': row.get('actions') or [],
                'name': row.get('label') or '',
            })
        for row in rules_for_channel():
            code = row.get('code') or ''
            title = row.get('title') or ''
            text = row.get('t') or ''
            if not code and not title and text:
                rules.append({
                    'code': '',
                    'title': 'Примечание',
                    'text': text,
                    'punish': '',
                    'duration': '',
                    'note': True,
                })
            else:
                rules.append({
                    'code': code,
                    'title': title or code,
                    'text': text,
                    'punish': row.get('punish') or '',
                    'duration': row.get('duration') or '',
                    'actions': row.get('actions') or [],
                    'note': False,
                })
    except Exception:
        pass

    # 2) json overrides / дополнения
    for p in DATA.glob(f'mod_reasons_{gid}.json') if gid else []:
        try:
            raw = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(raw, list) and raw:
                reasons = raw
            elif isinstance(raw, dict):
                extra = raw.get('reasons') or raw.get('items') or []
                if extra:
                    reasons = extra
        except Exception:
            pass
    for p in DATA.glob(f'rules_{gid}.json') if gid else []:
        try:
            raw = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(raw, list) and raw:
                rules = raw
            elif isinstance(raw, dict):
                extra = raw.get('rules') or raw.get('items') or []
                if extra:
                    rules = extra
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

    # если rules пусты — покажем тот же каталог как правила
    if not rules and reasons:
        rules = [
            {
                'code': (r.get('code') if isinstance(r, dict) else ''),
                'title': (r.get('title') or r.get('name') if isinstance(r, dict) else str(r)),
                'text': (r.get('text') if isinstance(r, dict) else ''),
                'punish': (r.get('punish') if isinstance(r, dict) else ''),
                'duration': (r.get('duration') if isinstance(r, dict) else ''),
                'actions': (r.get('actions') if isinstance(r, dict) else []),
                'note': False,
            }
            for r in reasons
        ]
    return reasons or [], rules or []


def _proofs_list(gid):
    """Реальные демки из data/modproof_{gid}.json (+ локальные медиа)."""
    items = []
    book = _namebook(gid)
    try:
        from cogs.proof_cog import proof_list
        rows = proof_list(int(gid), limit=80) if gid else []
    except Exception:
        rows = []
        raw = _read_json(DATA / f'modproof_{gid}.json', {}) if gid else {}
        bag = (raw.get('items') or {}) if isinstance(raw, dict) else {}
        rows = sorted(
            (bag.values() if isinstance(bag, dict) else []),
            key=lambda e: int((e or {}).get('id') or 0), reverse=True)[:80]
    for e in rows:
        if not isinstance(e, dict):
            continue
        uid = str(e.get('user_id') or '')
        mid = str(e.get('mod_id') or '')
        media = e.get('media') if isinstance(e.get('media'), dict) else {}
        local = str(media.get('file') or '').strip()
        media_url = ''
        media_kind = str(media.get('kind') or '').strip()
        media_name = str(media.get('name') or '').strip()
        resolved = None
        if local:
            for cand in (Path(local), ROOT / local, DATA / 'uploads' / 'proofs' / Path(local).name):
                try:
                    if cand.is_file():
                        resolved = cand
                        break
                except OSError:
                    pass
        # fallback: файл по шаблону {gid}_{id}.* (старые записи без media.file)
        if resolved is None and gid and e.get('id') is not None:
            base = DATA / 'uploads' / 'proofs'
            if base.is_dir():
                for cand in sorted(base.glob(f"{gid}_{e.get('id')}.*")):
                    if cand.is_file():
                        resolved = cand
                        break
        if resolved is not None:
            media_url = f'/proof-media/{resolved.name}'
            if not media_kind:
                ext = resolved.suffix.lower()
                media_kind = 'video' if ext in ('.mp4', '.webm', '.mov') else 'image'
            if not media_name:
                media_name = resolved.name
        jump = ''
        try:
            ch = int(e.get('channel_id') or 0)
            msg = int(e.get('msg_id') or 0)
            if gid and ch and msg:
                jump = f'https://discord.com/channels/{gid}/{ch}/{msg}'
        except Exception:
            jump = ''
        link = str(e.get('url') or e.get('link') or jump or '').strip()
        status = str(e.get('review_status') or 'pending').lower()
        reviewer = str(e.get('reviewed_by') or '').strip()
        items.append({
            'id': e.get('id'),
            'title': f"#{e.get('id')} · {e.get('action') or 'демка'}",
            'user_id': uid if _is_id(uid) else '',
            'user_name': _best_name(e.get('user_name'), uid, book),
            'mod_id': mid if _is_id(mid) else '',
            'mod_name': _best_name(e.get('mod_name'), mid, book),
            'reason': str(e.get('reason') or '')[:280],
            'detail': str(e.get('reason') or '')[:200],
            'when': _fmt(e.get('set_at')),
            'status': status,
            'reviewer': reviewer,
            'link': link,
            'media_url': media_url,
            'media_kind': media_kind,
            'media_name': media_name,
        })
    return items[:80]


PENDING_PINS_FILE = DATA / 'panel_pending_pins.json'
PIN_TTL_SEC = 10 * 60


def _load_pending_pins():
    raw = _read_json(PENDING_PINS_FILE, {})
    return raw if isinstance(raw, dict) else {}


def _save_pending_pins(data: dict):
    DATA.mkdir(parents=True, exist_ok=True)
    PENDING_PINS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        os.chmod(PENDING_PINS_FILE, 0o600)
    except OSError:
        pass


def _purge_pending_pins(data: dict | None = None) -> dict:
    data = dict(data if data is not None else _load_pending_pins())
    now = datetime.now(timezone.utc).timestamp()
    changed = False
    for uid in list(data.keys()):
        row = data.get(uid) or {}
        try:
            exp = float(row.get('exp') or 0)
        except Exception:
            exp = 0
        if exp and exp < now:
            data.pop(uid, None)
            changed = True
    if changed:
        _save_pending_pins(data)
    return data


def _member_avatar_url(member) -> str:
    try:
        av = getattr(member, 'display_avatar', None)
        if av is not None:
            return str(av.url)
    except Exception:
        pass
    try:
        uid = int(getattr(member, 'id', 0) or 0)
        idx = (uid >> 22) % 6 if uid else 0
    except Exception:
        idx = 0
    return f'https://cdn.discordapp.com/embed/avatars/{idx}.png'


def _guild_member_snapshot(m, *, role=None):
    display = (
        getattr(m, 'display_name', None)
        or getattr(m, 'global_name', None)
        or getattr(m, 'name', None)
        or str(m.id)
    )
    handle = getattr(m, 'name', '') or ''
    return {
        'id': str(m.id),
        'name': display,
        'handle': handle,
        'role': role or '',
        'role_label': ROLE_LABELS.get(role, role or ''),
        'avatar': _member_avatar_url(m),
        'joined': getattr(m, 'joined_at', None),
        'created': getattr(getattr(m, 'created_at', None), 'isoformat', lambda: None)(),
    }


def _avatar_url_from_user_payload(user: dict) -> str:
    uid = str((user or {}).get('id') or '0')
    av = (user or {}).get('avatar')
    if av:
        return f'https://cdn.discordapp.com/avatars/{uid}/{av}.png?size=1024'
    try:
        idx = (int(uid) >> 22) % 6
    except Exception:
        idx = 0
    return f'https://cdn.discordapp.com/embed/avatars/{idx}.png'


def _snapshot_from_api_member(row: dict, *, role=None) -> dict:
    user = row.get('user') or {}
    uid = str(user.get('id') or '')
    handle = str(user.get('username') or '')
    display = (
        row.get('nick')
        or user.get('global_name')
        or handle
        or uid
    )
    return {
        'id': uid,
        'name': str(display),
        'handle': handle,
        'role': role or '',
        'role_label': ROLE_LABELS.get(role, role or ''),
        'avatar': _avatar_url_from_user_payload(user),
        'joined': row.get('joined_at'),
        'created': None,
    }


def _match_rank(q: str, *, name: str, handle: str, uid: str, nick: str = '') -> int:
    """Меньше = лучше. Точный ник выше случайных вхождений."""
    ql = (q or '').strip().lower()
    if not ql:
        return 50
    name_l = str(name or '').lower()
    handle_l = str(handle or '').lower()
    nick_l = str(nick or '').lower()
    uid_s = str(uid or '')
    if ql == uid_s or ql in (name_l, handle_l, nick_l):
        return 0
    if any(p.startswith(ql) for p in (name_l, handle_l, nick_l) if p):
        return 1
    if any(ql in p for p in (name_l, handle_l, nick_l) if p):
        return 2
    tokens = [t for t in ql.split() if t]
    if tokens and all(
            any(t in p for p in (name_l, handle_l, nick_l) if p) for t in tokens):
        return 3
    return 9


def _discord_rest_member_search(gid: str, q: str, *, limit: int = 25):
    """Живой поиск участников через Discord API (не только кэш бота)."""
    token = (os.environ.get('TOKEN') or '').strip()
    query = (q or '').strip()
    if not token or not gid or not query:
        return [], ''
    url = (
        f'{DISCORD_API}/guilds/{gid}/members/search?'
        + urllib.parse.urlencode({
            'query': query,
            'limit': max(1, min(int(limit), 100)),
        })
    )
    st, data = _http_json(
        'GET', url,
        headers={
            'Authorization': f'Bot {token}',
            'User-Agent': 'HakumoPanel (https://hakumods.xyz, 1.0)',
        },
        timeout=10,
    )
    if st != 200:
        err = ''
        if isinstance(data, dict):
            err = str(data.get('message') or data.get('error') or '')[:160]
        return [], err or f'Discord search HTTP {st}'
    if not isinstance(data, list):
        return [], 'Discord search: неожиданный ответ'
    return data, ''


def _search_guild_members(q: str = '', *, staff_only=False, limit=40):
    """Поиск участников гильдии по имени/нику/ID. (items, error)."""
    people = []
    bot = bot_instance
    gid = _main_guild()
    if not bot or not gid:
        return people, 'Бот ещё не подключён — подожди пару секунд'
    try:
        guild = bot.get_guild(int(gid))
    except Exception:
        guild = None
    if guild is None:
        return people, 'Сервер не найден (MAIN_GUILD_ID)'

    ql = (q or '').strip().lower()
    try:
        from config import Config
        owner_ids = {int(x) for x in Config.all_owner_ids()}
    except Exception:
        owner_ids = set()

    by_id: dict[str, dict] = {}

    def _accept(snap: dict, *, nick: str = '') -> None:
        if not snap.get('id'):
            return
        role = snap.get('role') or ''
        if staff_only and not role:
            return
        snap = dict(snap)
        if ql:
            rank = _match_rank(
                ql,
                name=snap.get('name') or '',
                handle=snap.get('handle') or '',
                uid=snap.get('id') or '',
                nick=nick,
            )
            if rank >= 9:
                return
            snap['_rank'] = rank
        else:
            snap['_rank'] = 50
        prev = by_id.get(snap['id'])
        if prev is None or int(snap.get('_rank', 99)) < int(prev.get('_rank', 99)):
            by_id[snap['id']] = snap

    api_err = ''
    if ql:
        rows, api_err = _discord_rest_member_search(
            str(gid), q, limit=max(int(limit), 40))
        for row in rows:
            try:
                user = row.get('user') or {}
                if user.get('bot'):
                    continue
                uid = int(user.get('id') or 0)
                role_ids = [
                    int(x) for x in (row.get('roles') or []) if str(x).isdigit()
                ]
                role = resolve_discord_panel_role(uid, role_ids)
                if not role and uid in owner_ids:
                    role = 'owner'
                snap = _snapshot_from_api_member(row, role=role)
                _accept(snap, nick=str(row.get('nick') or ''))
            except Exception:
                continue

    for m in list(getattr(guild, 'members', []) or []):
        try:
            if getattr(m, 'bot', False):
                continue
            role_ids = [r.id for r in getattr(m, 'roles', []) or []]
            role = resolve_discord_panel_role(m.id, role_ids)
            if not role and int(m.id) in owner_ids:
                role = 'owner'
            if staff_only and not role:
                continue
            if ql and not _fuzzy_match(
                    ql,
                    getattr(m, 'display_name', None),
                    getattr(m, 'name', None),
                    m.id,
                    getattr(m, 'nick', None) or '',
                    getattr(m, 'global_name', None) or ''):
                continue
            snap = _guild_member_snapshot(m, role=role)
            _accept(snap, nick=str(getattr(m, 'nick', None) or ''))
        except Exception:
            continue

    people = list(by_id.values())
    if staff_only:
        order = {'owner': 0, 'admin': 1, 'curator': 2, 'mod': 3, 'helper': 4}
        people.sort(key=lambda p: (
            int(p.get('_rank', 50)),
            order.get(p.get('role'), 9),
            str(p.get('name') or '').lower(),
        ))
    else:
        people.sort(key=lambda p: (
            int(p.get('_rank', 50)),
            str(p.get('name') or '').lower(),
        ))
    out = []
    for p in people[: max(1, int(limit))]:
        p.pop('_rank', None)
        out.append(p)
    if ql and not out and api_err:
        return out, api_err
    return out, ''


def _list_login_people(q: str = ''):
    """Staff с сервера для выбора на логине."""
    return _search_guild_members(q, staff_only=True, limit=80)


def _find_guild_member(uid: str):
    bot = bot_instance
    gid = _main_guild()
    if not bot or not gid or not str(uid).isdigit():
        return None
    try:
        guild = bot.get_guild(int(gid))
    except Exception:
        guild = None
    if guild is None:
        return None
    try:
        member = guild.get_member(int(uid))
    except Exception:
        member = None
    if member is not None:
        return member
    try:
        return _run_on_bot(guild.fetch_member(int(uid)), timeout=12)
    except Exception:
        return None


def _rest_guild_member(uid: str):
    """Участник через REST, если кэш/fetch не сработали."""
    gid = _main_guild()
    token = (os.environ.get('TOKEN') or '').strip()
    if not gid or not token or not str(uid).isdigit():
        return None
    url = f'{DISCORD_API}/guilds/{gid}/members/{uid}'
    st, data = _http_json(
        'GET', url,
        headers={
            'Authorization': f'Bot {token}',
            'User-Agent': 'HakumoPanel (https://hakumods.xyz, 1.0)',
        },
        timeout=10,
    )
    if st != 200 or not isinstance(data, dict) or not data.get('user'):
        return None
    return data


class _RestMember:
    """Минимальный объект участника из REST для регистрации."""

    def __init__(self, row: dict):
        user = row.get('user') or {}
        self.id = int(user.get('id') or 0)
        self.name = str(user.get('username') or '')
        self.global_name = user.get('global_name')
        self.nick = row.get('nick')
        self.display_name = (
            row.get('nick')
            or user.get('global_name')
            or user.get('username')
            or str(self.id)
        )
        self.bot = bool(user.get('bot'))
        self._avatar = _avatar_url_from_user_payload(user)
        self.roles = []
        for rid in row.get('roles') or []:
            try:
                self.roles.append(type('R', (), {'id': int(rid)})())
            except Exception:
                continue

    @property
    def display_avatar(self):
        return type('A', (), {'url': self._avatar})()


def _issue_pin_to_dm(discord_id: str):
    """Сгенерировать PIN, сохранить pending, отправить в ЛС. (ok_msg, err)."""
    bot = bot_instance
    if not bot or not getattr(bot, 'loop', None):
        return '', 'Бот не готов отправлять ЛС'
    people, _ = _list_login_people()
    person = next((p for p in people if p['id'] == str(discord_id)), None)
    if not person:
        return '', 'Этот человек не в staff-списке'
    pin = f'{secrets.randbelow(10**6):06d}'
    data = _purge_pending_pins()
    data[str(discord_id)] = {
        'pin': _hash_secret(pin),
        'role': person['role'],
        'name': person['name'],
        'handle': person.get('handle') or '',
        'avatar': person.get('avatar') or '',
        'exp': datetime.now(timezone.utc).timestamp() + PIN_TTL_SEC,
    }
    _save_pending_pins(data)

    async def _send():
        user = bot.get_user(int(discord_id))
        if user is None:
            user = await bot.fetch_user(int(discord_id))
        text = (
            f"**Hakumo** — код входа в панель\n"
            f"PIN: `{pin}`\n"
            f"Действует {PIN_TTL_SEC // 60} мин. Никому не пересылай."
        )
        await user.send(text)

    import asyncio
    try:
        fut = asyncio.run_coroutine_threadsafe(_send(), bot.loop)
        fut.result(timeout=20)
    except Exception as e:
        msg = str(e)
        if 'Cannot send messages to this user' in msg or '50007' in msg:
            return '', 'Не смог написать в ЛС — открой личку с ботом (Allow DMs)'
        return '', f'ЛС не отправилось: {msg[:160]}'
    return f'PIN отправлен в Discord ЛС → @{person.get("handle") or person["name"]}', ''


def _auth_pending_pin(discord_id: str, pin: str):
    pin = (pin or '').strip()
    if not pin.isdigit() or not (4 <= len(pin) <= 8):
        return None
    data = _purge_pending_pins()
    row = data.get(str(discord_id))
    if not row:
        return None
    if not _secret_matches(row.get('pin'), pin):
        return None
    data.pop(str(discord_id), None)
    _save_pending_pins(data)
    role = str(row.get('role') or 'mod')
    if role not in LEVEL:
        role = 'mod'
    name = row.get('name') or row.get('handle') or str(discord_id)
    return {
        'username': name,
        'role': role,
        'discord_id': str(discord_id),
        'handle': row.get('handle') or '',
        'avatar': row.get('avatar') or '',
    }


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
    mode = (request.values.get('mode') or 'people').strip().lower()
    if mode not in ('people', 'password', 'pin', 'register', 'forgot'):
        mode = 'people'
    err = (request.args.get('error') or '').strip()
    ok = (request.args.get('ok') or '').strip()
    nxt = _safe_next(request.args.get('next') or request.form.get('next'))
    selected_id = (request.values.get('uid') or '').strip()
    people_q = (request.values.get('pq') or '').strip()
    reg_id = (request.values.get('member_id') or request.values.get('reg_id') or '').strip()

    if request.method == 'POST':
        mode = (request.form.get('mode') or mode).strip().lower()
        if mode == 'people':
            action = (request.form.get('action') or 'send').strip()
            selected_id = (request.form.get('uid') or '').strip()
            people_q = (request.form.get('pq') or '').strip()
            if not selected_id:
                err = 'Выбери человека'
            else:
                msg, e2 = _issue_pin_to_dm(selected_id)
                if e2:
                    err = e2
                else:
                    # PIN вводится на отдельной странице
                    return redirect(url_for(
                        'login', mode='pin', uid=selected_id,
                        next=nxt, ok=msg,
                    ))
        elif mode == 'password':
            got = _auth_user(request.form.get('username', ''), request.form.get('password', ''))
            if got:
                _start_session(username=got[0], role=got[1])
                return redirect(nxt)
            err = 'Неверный логин или пароль'
        elif mode == 'pin':
            uid = (request.form.get('uid') or '').strip()
            selected_id = uid
            if uid:
                gotp = _auth_pending_pin(uid, request.form.get('pin', ''))
                if gotp:
                    _start_session(username=gotp['username'], role=gotp['role'])
                    session['discord_id'] = gotp['discord_id']
                    session['discord_handle'] = gotp.get('handle') or ''
                    session['discord_display'] = gotp['username']
                    session['discord_avatar'] = gotp.get('avatar') or ''
                    session['auth_via'] = 'pin-dm'
                    session['role_label'] = ROLE_LABELS.get(gotp['role'], gotp['role'])
                    return redirect(nxt)
            got = _auth_pin(request.form.get('username', ''), request.form.get('pin', ''))
            if got:
                _start_session(username=got[0], role=got[1])
                return redirect(nxt)
            err = 'Неверный или просроченный PIN'
        elif mode == 'register':
            invite = request.form.get('invite', '')
            password = request.form.get('password') or ''
            reg_id = (request.form.get('member_id') or request.form.get('reg_id') or '').strip()
            username = (request.form.get('username') or '').strip()
            env_u, _ = _env_owner_creds()
            member = _find_guild_member(reg_id) if reg_id else None
            if member is None and reg_id:
                row = _rest_guild_member(reg_id)
                if row is not None:
                    member = _RestMember(row)
            if not _invite_ok(invite):
                err = 'Неверный код приглашения'
            elif not member:
                err = 'Найди себя по имени Discord и выбери из списка'
            elif len(password) < 6:
                err = 'Пароль минимум 6 символов'
            else:
                handle = getattr(member, 'name', '') or ''
                display = (
                    getattr(member, 'display_name', None)
                    or getattr(member, 'global_name', None)
                    or handle
                    or str(member.id)
                )
                username = (username or handle or display).strip()
                if len(username) < 3:
                    err = 'Логин слишком короткий'
                elif username == env_u:
                    err = 'Этот логин занят владельцем'
                else:
                    existing = _find_access_user(username)
                    if existing and str(existing.get('discord_id') or '') not in ('', str(member.id)):
                        err = 'Такой логин уже есть'
                    else:
                        try:
                            role_ids = [r.id for r in getattr(member, 'roles', []) or []]
                            role = resolve_discord_panel_role(member.id, role_ids) or 'mod'
                        except Exception:
                            role = 'mod'
                        if role == 'owner':
                            role = 'admin'
                        if role not in LEVEL:
                            role = 'mod'
                        _upsert_access_user(
                            username=username,
                            password=password,
                            role=role,
                            note=f'@{handle}' if handle else '',
                            discord_id=str(member.id),
                            display_name=display,
                            avatar=_member_avatar_url(member),
                        )
                        _start_session(username=username, role=role)
                        session['discord_id'] = str(member.id)
                        session['discord_handle'] = handle
                        session['discord_display'] = display
                        session['discord_avatar'] = _member_avatar_url(member)
                        session['auth_via'] = 'register'
                        session['role_label'] = ROLE_LABELS.get(role, role)
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

    people, people_err = _list_login_people(people_q) if mode == 'people' else ([], '')
    if mode == 'people' and people_err and not err:
        err = people_err

    reg_person = None
    if mode == 'register' and reg_id:
        m = _find_guild_member(reg_id)
        if m is not None:
            reg_person = _guild_member_snapshot(m)
        else:
            row = _rest_guild_member(reg_id)
            if row is not None:
                try:
                    from config import Config
                    owner_ids = {int(x) for x in Config.all_owner_ids()}
                except Exception:
                    owner_ids = set()
                user = row.get('user') or {}
                uid = int(user.get('id') or 0)
                role_ids = [
                    int(x) for x in (row.get('roles') or []) if str(x).isdigit()
                ]
                role = resolve_discord_panel_role(uid, role_ids)
                if not role and uid in owner_ids:
                    role = 'owner'
                reg_person = _snapshot_from_api_member(row, role=role)

    pin_person = None
    if mode == 'pin' and selected_id:
        m = _find_guild_member(selected_id)
        if m is not None:
            pin_person = _guild_member_snapshot(m)
        else:
            people_all, _ = _list_login_people()
            pin_person = next((p for p in people_all if p['id'] == selected_id), None)

    _, env_pw = _env_owner_creds()
    hint = '' if env_pw else 'Задайте PANEL_PASSWORD в .env'
    invite_set = bool((os.environ.get('PANEL_INVITE_CODE') or '').strip())
    return render_template(
        'login.html',
        error=err,
        ok=ok,
        hint=hint,
        discord_ready=_discord_oauth_ready(),
        mode=mode,
        next=nxt,
        people=people,
        people_q=people_q,
        selected_id=selected_id,
        reg_id=reg_id,
        reg_person=reg_person,
        pin_person=pin_person,
        invite_set=invite_set,
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




def _run_on_bot(coro, timeout=25):
    bot = bot_instance
    if not bot or not getattr(bot, 'loop', None):
        raise RuntimeError('Бот офлайн')
    return asyncio.run_coroutine_threadsafe(coro, bot.loop).result(timeout=timeout)


def _audit_events(gid: str, limit=300):
    raw = _read_json(DATA / 'audit_log.json', {})
    items = []
    if isinstance(raw, dict):
        items = list(raw.get(str(gid)) or [])
    elif isinstance(raw, list):
        items = raw
    return list(reversed(items[-limit:]))


def _staff_feed(gid: str, limit=80):
    """Лента staff: наказания + решения по апелляциям + важные audit.

    Join/leave/смены ролей сюда НЕ кладём — они отдельно на /logs,
    иначе забивают ленту и пропадают «кто отклонил».
    """
    book = _namebook(gid)
    book.update(_proof_name_hints(gid))
    book.update(_appeal_name_hints(gid))
    feed = []
    for r in _collect_cases(gid)[:120]:
        feed.append({
            'kind': 'punish',
            'action': r.get('action') or r.get('kind'),
            'who': r.get('mod_name') or '—',
            'who_id': str(r.get('mod_id') or '') if str(r.get('mod_id') or '').isdigit() else '',
            'target': r.get('user_name') or '—',
            'target_id': str(r.get('user_id') or '') if str(r.get('user_id') or '').isdigit() else '',
            'detail': r.get('reason') or '',
            'when': _fmt(r.get('timestamp')),
            'ts': r.get('timestamp') or '',
        })
    # Решения по апелляциям (в т.ч. старые reject без дела) — кто принял/отклонил
    for it in _appeals_list(gid):
        st = str(it.get('status') or '').lower()
        if st not in ('accepted', 'rejected'):
            continue
        uid = str(it.get('user_id') or '')
        rid = str(it.get('reviewer_id') or it.get('mod_id') or '')
        who = str(it.get('reviewed_by') or '').strip()
        feed.append({
            'kind': 'appeal',
            'action': 'Апелляция · принята' if st == 'accepted' else 'Апелляция · отклонена',
            'who': _best_name(who, rid, book, fallback='—'),
            'who_id': rid if rid.isdigit() else '',
            'target': _best_name(it.get('user_name'), uid, book),
            'target_id': uid if uid.isdigit() else '',
            'detail': (it.get('text') or it.get('reason') or '')[:160],
            'when': _fmt(it.get('reviewed_at') or it.get('created_at')),
            'ts': it.get('reviewed_at') or it.get('created_at') or '',
        })
    # Шум: входы/выходы/роли/войс — на /logs отдельным блоком, не в staff-ленте
    _audit_noise = {
        'Участник вошёл', 'Участник вышел', 'Изменение ролей',
        'Пользователю включили звук', 'Пользователю выключили звук',
        'Пользователя заглушили', 'С пользователя сняли заглушение',
    }
    for ev in _audit_events(gid, 400):
        act = str(ev.get('action') or '')
        if act in _audit_noise:
            continue
        cat = str(ev.get('category') or '')
        al = act.lower()
        interesting = (
            cat in ('mod', 'mute')
            or 'бан' in al or 'кик' in al
            or 'мут' in al or 'варн' in al
            or 'тайм' in al or 'timeout' in al
            or bool(ev.get('mod_name') or ev.get('mod_id'))
        )
        if not interesting:
            continue
        who_id = str(ev.get('mod_id') or ev.get('user_id') or '')
        target_id = str(ev.get('target_id') or ev.get('user_id') or '')
        feed.append({
            'kind': 'audit',
            'action': act,
            'who': _best_name(ev.get('mod_name') or ev.get('user_name'), who_id, book),
            'who_id': who_id if who_id.isdigit() else '',
            'target': _best_name(
                ev.get('target_name') or ev.get('user_name'),
                ev.get('target_id') or ev.get('user_id'),
                book,
            ),
            'target_id': target_id if target_id.isdigit() else '',
            'detail': ev.get('reason') or ev.get('channel_name') or '',
            'when': _fmt(ev.get('timestamp')),
            'ts': ev.get('timestamp') or '',
        })
    # Наказания и апелляции не должны вытесняться audit-хвостом:
    # сначала режем audit, потом мержим по времени.
    core = [f for f in feed if f.get('kind') in ('punish', 'appeal')]
    audit = [f for f in feed if f.get('kind') == 'audit']
    core.sort(key=lambda x: str(x.get('ts') or ''), reverse=True)
    audit.sort(key=lambda x: str(x.get('ts') or ''), reverse=True)
    room = max(0, int(limit) - len(core))
    merged = core + audit[:room]
    merged.sort(key=lambda x: str(x.get('ts') or ''), reverse=True)
    return merged[:limit]


def _fuzzy_match(q: str, *parts) -> bool:
    ql = (q or '').strip().lower()
    if not ql:
        return True
    blob = ' '.join(str(p or '') for p in parts).lower()
    if ql in blob:
        return True
    tokens = [t for t in ql.split() if t]
    if tokens and all(t in blob for t in tokens):
        return True
    # prefix / similar: каждое слово начинается так же
    words = blob.replace('@', ' ').split()
    for tok in tokens or [ql]:
        if not any(w.startswith(tok) or tok in w for w in words):
            return False
    return True


def _search_accounts(q: str, limit=12):
    """Аккаунты для логина по паролю: access users + staff."""
    out = []
    ql = (q or '').strip()
    for u in _load_access()['users']:
        name = str(u.get('username') or '')
        note = str(u.get('note') or '')
        if not _fuzzy_match(ql, name, note):
            continue
        out.append({
            'username': name,
            'label': name,
            'hint': note or (u.get('role') or 'mod'),
            'kind': 'account',
        })
    people, _ = _list_login_people(ql)
    for p in people:
        out.append({
            'username': p.get('handle') or p.get('name'),
            'label': p.get('name'),
            'hint': f"@{p.get('handle') or ''} · {p.get('role_label')}",
            'kind': 'staff',
            'avatar': p.get('avatar'),
        })
    # unique by username
    seen = set()
    uniq = []
    for row in out:
        key = str(row.get('username') or '').lower()
        if not key or key in seen:
            continue
        seen.add(key)
        uniq.append(row)
        if len(uniq) >= limit:
            break
    return uniq


# ── routes: mod pages ──────────────────────────────────────────────────

@app.route('/')
@login_required
@role_required('helper')
def today():
    gid = _main_guild()
    rows = _filter_cases_for_viewer(_collect_cases(gid))
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
    return render_template(
        'today.html', kpi=kpi, rows=today_rows[:30], fmt=_fmt,
        limits=_viewer_limits_card(),
        hidden_kinds=sorted(_viewer_hidden_kinds()),
    )


@app.route('/logs')
@login_required
@role_required('helper')
def logs():
    gid = _main_guild()
    span = 'month' if request.args.get('span') == 'month' else 'week'
    days = 30 if span == 'month' else 7
    rows = _filter_cases_for_viewer(_collect_cases(gid))[:200]
    for r in rows:
        r['when'] = _fmt(r.get('timestamp'))
    feed = _staff_feed(gid, 60)
    hidden = _viewer_hidden_kinds()
    if hidden:
        feed = [
            f for f in feed
            if not any(h in str(f.get('action') or '').lower()
                       for h in ('бан', 'ban', 'кик', 'kick'))
        ]
    book = _namebook(gid)
    joins = [e for e in _audit_events(gid, 200)
             if e.get('action') in ('Участник вошёл', 'Участник вышел')][:40]
    for e in joins:
        e['when'] = _fmt(e.get('timestamp'))
        e['user_name'] = _best_name(e.get('user_name'), e.get('user_id'), book)
        e['user_id'] = str(e.get('user_id') or '')
    return render_template(
        'logs.html', rows=rows, feed=feed, joins=joins,
        limits=_viewer_limits_card(),
        hidden_kinds=sorted(hidden),
        activity=_mod_activity(gid, days),
        span=span,
    )


@app.route('/staff')
@login_required
@role_required('helper')
def staff_page():
    gid = _main_guild()
    span = 'month' if request.args.get('span') == 'month' else 'week'
    days = 30 if span == 'month' else 7
    feed = _staff_feed(gid, 100)
    people, err = _list_login_people()
    return render_template(
        'staff.html', feed=feed, people=people, error=err,
        activity=_mod_activity(gid, days), span=span,
        hidden_kinds=sorted(_viewer_hidden_kinds()),
    )


@app.route('/channels')
@login_required
@role_required('mod')
def channels_page():
    """Таблица способностей каналов (чтение)."""
    gid = _main_guild()
    rows = []
    bot = bot_instance
    try:
        guild = bot.get_guild(int(gid)) if bot and gid else None
    except Exception:
        guild = None
    if guild is not None:
        everyone = guild.default_role

        def _order(c):
            cat = getattr(c, 'category', None)
            cp = getattr(cat, 'position', -1) if cat is not None else -1
            return (cp, getattr(c, 'position', 0), str(getattr(c, 'name', '')).lower())

        for ch in sorted(guild.channels, key=_order):
            cls = type(ch).__name__
            if 'Category' in cls:
                group, kind, icon = 'category', 'категория', 'fa-folder'
            elif 'Voice' in cls or 'Stage' in cls:
                group, kind, icon = 'voice', 'голос', 'fa-volume-high'
            elif 'Forum' in cls:
                group, kind, icon = 'forum', 'форум', 'fa-comments'
            else:
                group, kind, icon = 'text', 'текст', 'fa-hashtag'
            cat = getattr(getattr(ch, 'category', None), 'name', None) or 'Без категории'
            perms = None
            try:
                perms = ch.permissions_for(everyone) if everyone else None
            except Exception:
                perms = None

            def flag(name, _p=perms):
                return bool(getattr(_p, name, False)) if _p else False

            rows.append({
                'id': str(ch.id),
                'name': getattr(ch, 'name', '?'),
                'kind': kind,
                'group': group,
                'icon': icon,
                'cat': cat,
                'view': flag('view_channel'),
                'send': flag('send_messages'),
                'speak': flag('speak'),
                'connect': flag('connect'),
                'manage': flag('manage_channels'),
                'stream': flag('stream'),
            })
    shown = [r for r in rows if r.get('group') != 'category']
    groups, seen = [], {}
    for r in shown:
        key = r['cat']
        if key not in seen:
            seen[key] = {'name': key, 'items': []}
            groups.append(seen[key])
        seen[key]['items'].append(r)
    kpi = {
        'total': len(shown),
        'text': sum(1 for r in shown if r['group'] == 'text'),
        'voice': sum(1 for r in shown if r['group'] == 'voice'),
        'closed': sum(1 for r in shown if not r['view']),
    }
    return render_template('channels.html', rows=shown, groups=groups, kpi=kpi)


@app.get('/api/login/accounts')
def api_login_accounts():
    q = (request.args.get('q') or '').strip()
    return jsonify({'ok': True, 'items': _search_accounts(q, 14)})


@app.get('/api/login/members')
def api_login_members():
    """Публичный поиск участников по имени — для вкладки Создать."""
    q = (request.args.get('q') or '').strip()
    if len(q) < 1:
        return jsonify({'ok': True, 'items': []})
    people, err = _search_guild_members(q, staff_only=False, limit=20)
    items = [{
        'id': p['id'],
        'name': p['name'],
        'handle': p.get('handle') or '',
        'avatar': p.get('avatar') or '',
        'role': p.get('role') or '',
        'role_label': p.get('role_label') or '',
    } for p in people]
    return jsonify({'ok': True, 'items': items, 'error': err or ''})


@app.get('/api/users/search')
@login_required
@role_required('helper')
def api_users_search():
    q = (request.args.get('q') or '').strip()
    people, _ = _search_guild_members(q, staff_only=False, limit=20)
    items = [{
        'id': p['id'],
        'name': p['name'],
        'handle': p.get('handle') or '',
        'avatar': p.get('avatar') or '',
    } for p in people]
    return jsonify({'ok': True, 'items': items})


@app.post('/api/punish')
@login_required
@role_required('helper')
def api_punish():
    """Выдать меру из панели (через бота). Учитывает роль и staff_limits."""
    data = request.get_json(silent=True) or request.form
    action = str(data.get('action') or '').strip().lower()
    uid = str(data.get('user_id') or '').strip()
    rule = str(data.get('rule') or '').strip()
    note = str(data.get('note') or '').strip()[:200]
    legacy_reason = str(data.get('reason') or '').strip()[:400]
    try:
        minutes = int(data.get('minutes') or 10)
    except Exception:
        minutes = 10
    if action not in ('warn', 'mute', 'kick', 'ban'):
        return jsonify({'ok': False, 'error': 'action: warn|mute|kick|ban'}), 400
    allowed = _viewer_punish_actions()
    if action not in allowed:
        return jsonify({
            'ok': False,
            'error': f'Твоя роль не может выдавать: {PUNISH_LABELS.get(action, action)}',
        }), 403
    if not uid.isdigit():
        return jsonify({'ok': False, 'error': 'user_id'}), 400
    # хелперу мут — максимум час
    if action == 'mute' and (session.get('role') or 'helper') == 'helper':
        minutes = min(max(1, minutes), 60)

    # причина = правило из каталога (+ комментарий)
    reason = ''
    try:
        from services.mod_reasons import is_known, allows, format_reason
        if rule:
            if not is_known(rule):
                return jsonify({'ok': False, 'error': 'Неизвестное правило'}), 400
            act_key = 'timeout' if action == 'mute' else action
            if action != 'kick' and not allows(rule, act_key):
                return jsonify({
                    'ok': False,
                    'error': f'Правило {rule} не предусматривает: {PUNISH_LABELS.get(action, action)}',
                }), 400
            reason = format_reason(rule)
        elif not legacy_reason:
            return jsonify({'ok': False, 'error': 'Выбери правило'}), 400
    except ImportError:
        pass
    if not reason:
        reason = legacy_reason or 'Панель'
    if note:
        reason = f'{reason} · {note}'
    reason = reason[:400]
    # лимиты staff_limits (owner — без квот)
    if not _viewer_is_limit_exempt():
        try:
            from services.staff_limits import check_limit, limit_deny_text, human_window, get_windows
            gid0 = _main_guild()
            actor = str(session.get('discord_id') or '').strip()
            if gid0 and actor.isdigit():
                sl_key = 'mute' if action == 'mute' else action
                role_ids = _session_discord_role_ids()
                ok_l, used, lim = check_limit(gid0, actor, sl_key, 1, role_ids)
                if not ok_l and lim > 0:
                    win = (get_windows(gid0) or {}).get(sl_key)
                    return jsonify({
                        'ok': False,
                        'error': limit_deny_text(sl_key, used, lim, 1, window=win),
                    }), 429
        except Exception:
            pass
    bot = bot_instance
    gid = _main_guild()
    if not bot or not gid:
        return jsonify({'ok': False, 'error': 'Бот офлайн'}), 503

    async def _do():
        guild = bot.get_guild(int(gid))
        if guild is None:
            raise RuntimeError('guild not found')
        member = guild.get_member(int(uid))
        if member is None:
            member = await guild.fetch_member(int(uid))
        mod_name = session.get('discord_display') or session.get('username') or 'panel'
        mod_id = session.get('discord_id') or '0'
        target_name = (
            getattr(member, 'display_name', None)
            or getattr(member, 'name', None)
            or str(member.id)
        )
        # В audit Discord исполнителем будет бот — имя модератора в reason
        ban_reason = f'{reason} · панель: {mod_name}'[:512]
        cog = bot.get_cog('moderation') or bot.get_cog('Moderation')
        if action == 'warn':
            warns = bot.get_cog('warnings')
            if warns is None:
                raise RuntimeError('warnings cog offline')
            await warns.add_warning(member, guild.me, reason)
            act = 'warn'
        elif action == 'mute':
            from datetime import timedelta
            until = datetime.now(timezone.utc) + timedelta(minutes=max(1, minutes))
            await member.timeout(until, reason=ban_reason)
            act = 'timeout'
        elif action == 'kick':
            await member.kick(reason=ban_reason)
            act = 'kick'
        elif action == 'ban':
            await member.ban(reason=ban_reason, delete_message_days=0)
            act = 'ban'
        else:
            act = action
        if cog and hasattr(cog, 'save_case'):
            try:
                cog.save_case(
                    guild.id, act, member.id, mod_id, reason,
                    mod_name=mod_name,
                    duration=minutes if action == 'mute' else None,
                    user_name=target_name)
            except TypeError:
                cog.save_case(
                    guild.id, act, member.id, mod_id, reason,
                    mod_name=mod_name,
                    duration=minutes if action == 'mute' else None)
        return {'action': act, 'user': str(member), 'id': str(member.id),
                'mod': mod_name, 'reason': (rule or reason)[:80]}

    try:
        result = _run_on_bot(_do())
        if not _viewer_is_limit_exempt():
            try:
                from services.staff_limits import record_hit
                actor = str(session.get('discord_id') or '').strip()
                if gid and actor.isdigit():
                    sl_key = 'mute' if action == 'mute' else action
                    record_hit(gid, actor, sl_key, 1)
            except Exception:
                pass
        return jsonify({'ok': True, **result})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:200]}), 500


@app.route('/users')
@login_required
@role_required('helper')
def users_page():
    """Участники сервера — профили таблицей + счётчики мер."""
    gid = _main_guild()
    q = (request.args.get('q') or '').strip()
    ql = q.lower()
    names = {}
    avatars = {}
    handles = {}
    role_names = {}

    try:
        bot = bot_instance
        if bot and gid:
            guild = bot.get_guild(int(gid))
            if guild is not None:
                for m in guild.members:
                    if getattr(m, 'bot', False):
                        continue
                    uid = str(m.id)
                    display = (
                        getattr(m, 'display_name', None)
                        or getattr(m, 'global_name', None)
                        or getattr(m, 'name', None)
                        or uid
                    )
                    handle = getattr(m, 'name', '') or ''
                    parts = [
                        display, handle,
                        getattr(m, 'global_name', None) or '',
                        getattr(m, 'nick', None) or '',
                        uid,
                    ]
                    names[uid] = display
                    handles[uid] = handle
                    avatars[uid] = _member_avatar_url(m)
                    names[uid + '::__q'] = ' '.join(p for p in parts if p).lower()
                    try:
                        roles = [
                            r.name for r in getattr(m, 'roles', []) or []
                            if getattr(r, 'name', None) and r.name != '@everyone'
                        ]
                        role_names[uid] = roles[:8]
                    except Exception:
                        role_names[uid] = []
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
        display = names.get(uid) or st.get('name') or ''
        if _is_id(display):
            alt = st.get('name') or ''
            display = alt if alt and not _is_id(alt) else ''
        if not display or _is_id(display):
            display = '—'
        blob = names.get(uid + '::__q') or f"{display} {uid}".lower()
        if ql:
            tokens = [t for t in ql.split() if t]
            if tokens and not all(tok in blob for tok in tokens):
                if ql not in blob and ql not in uid:
                    continue
        rows.append({
            'user_id': uid,
            'name': display,
            'handle': handles.get(uid) or '',
            'avatar': avatars.get(uid) or f'https://cdn.discordapp.com/embed/avatars/{(int(uid) >> 22) % 6 if uid.isdigit() else 0}.png',
            'roles': role_names.get(uid) or [],
            'warns': st.get('warns', 0),
            'mutes': st.get('mutes', 0),
            'bans': st.get('bans', 0),
            'kicks': st.get('kicks', 0),
            'total': st.get('total', 0),
            'last': _fmt(st.get('last')),
        })
    rows.sort(key=lambda r: (-r['total'], str(r['name']).lower()))
    kpi = {
        'total': len(rows),
        'warns': sum(r['warns'] for r in rows),
        'mutes': sum(r['mutes'] for r in rows),
        'bans': sum(r['bans'] for r in rows),
        'kicks': sum(r['kicks'] for r in rows),
    }
    return render_template(
        'users.html', rows=rows[:300], q=q, kpi=kpi,
        limits=_viewer_limits_card(),
        hidden_kinds=sorted(_viewer_hidden_kinds()),
    )


@app.route('/member')
@login_required
@role_required('helper')
def member():
    q = (request.args.get('q') or '').strip()
    rows = []
    profile = None
    if q:
        gid = _main_guild()
        all_rows = _collect_cases(gid)
        ql = q.lower()
        extra_ids = set()
        member_obj = None
        try:
            bot = bot_instance
            if bot and gid:
                guild = bot.get_guild(int(gid))
                if guild is not None:
                    if q.isdigit():
                        member_obj = guild.get_member(int(q))
                    else:
                        for m in guild.members:
                            blob = ' '.join([
                                getattr(m, 'display_name', '') or '',
                                getattr(m, 'name', '') or '',
                                getattr(m, 'global_name', None) or '',
                                getattr(m, 'nick', None) or '',
                            ]).lower()
                            if ql in blob or all(t in blob for t in ql.split() if t):
                                extra_ids.add(str(m.id))
                                if member_obj is None:
                                    member_obj = m
        except Exception:
            pass

        target_ids = set()
        if q.isdigit():
            target_ids.add(q)
        target_ids |= extra_ids

        for r in all_rows:
            uid = str(r.get('user_id', ''))
            uname = str(r.get('user_name', '')).lower()
            if (uid in target_ids or ql in uid or ql in uname
                    or all(t in uname for t in ql.split() if t)):
                r = dict(r)
                r['when'] = _fmt(r.get('timestamp'))
                rows.append(r)
                if len(rows) >= 100:
                    break
                if uid:
                    target_ids.add(uid)

        # профиль
        uid = None
        if member_obj is not None:
            uid = str(member_obj.id)
        elif target_ids:
            uid = next(iter(sorted(target_ids)))
        elif q.isdigit():
            uid = q

        if uid:
            snap = None
            if member_obj is not None:
                snap = _guild_member_snapshot(member_obj)
            roles = []
            joined = '—'
            created = '—'
            if member_obj is not None:
                try:
                    roles = [
                        r.name for r in getattr(member_obj, 'roles', []) or []
                        if getattr(r, 'name', None) and r.name != '@everyone'
                    ]
                except Exception:
                    roles = []
                try:
                    ja = getattr(member_obj, 'joined_at', None)
                    if ja:
                        joined = ja.astimezone().strftime('%d.%m.%Y')
                except Exception:
                    pass
                try:
                    ca = getattr(member_obj, 'created_at', None)
                    if ca:
                        created = ca.strftime('%d.%m.%Y')
                except Exception:
                    pass
            warns = sum(1 for r in rows if r.get('kind') == 'warn')
            mutes = sum(1 for r in rows if r.get('kind') in ('mute', 'timeout'))
            bans = sum(1 for r in rows if r.get('kind') == 'ban')
            kicks = sum(1 for r in rows if r.get('kind') == 'kick')
            profile = {
                'id': uid,
                'name': _best_name(
                    (snap or {}).get('name') or (rows[0].get('user_name') if rows else ''),
                    uid,
                    _namebook(gid),
                ),
                'handle': (snap or {}).get('handle') or '',
                'avatar': (snap or {}).get('avatar') or f'https://cdn.discordapp.com/embed/avatars/{(int(uid) >> 22) % 6 if uid.isdigit() else 0}.png',
                'roles': roles,
                'joined': joined,
                'created': created,
                'warns': warns,
                'mutes': mutes,
                'bans': bans,
                'kicks': kicks,
                'total': len(rows),
                'on_server': member_obj is not None,
            }
    rows = _filter_cases_for_viewer(rows)
    if profile:
        hidden = _viewer_hidden_kinds()
        if 'ban' in hidden:
            profile['bans'] = None
        if 'kick' in hidden:
            profile['kicks'] = None
        profile['total'] = len(rows)
        profile['warns'] = sum(1 for r in rows if r.get('kind') == 'warn')
        profile['mutes'] = sum(1 for r in rows if r.get('kind') in ('mute', 'timeout'))
    return render_template(
        'member.html', q=q, rows=rows, profile=profile,
        limits=_viewer_limits_card(),
        hidden_kinds=sorted(_viewer_hidden_kinds()),
    )


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
    book = _namebook(gid)
    view = []
    for it in items:
        uid = str(it.get('user_id') or it.get('author_id') or '')
        mid = str(it.get('reviewer_id') or it.get('mod_id') or '')
        reviewer = str(it.get('reviewed_by') or it.get('mod_name') or '').strip()
        st_raw = str(it.get('status') or '').lower()
        st_ru = {
            'pending': 'ожидает',
            'accepted': 'принята',
            'rejected': 'отклонена',
            'auto_closed': 'закрыта',
        }.get(st_raw, st_raw or '—')
        decided = _fmt(it.get('reviewed_at')) if it.get('reviewed_at') else ''
        view.append({
            'id': it.get('id') or it.get('case_id') or '—',
            'user_id': uid if _is_id(uid) else '',
            'user': _best_name(it.get('user_name') or it.get('username'), uid, book),
            'status': st_ru,
            'status_raw': st_raw,
            'reason': (it.get('text') or it.get('reason') or '')[:160],
            'when': _fmt(it.get('created_at') or it.get('timestamp')),
            'decided': decided,
            'mod_id': mid if _is_id(mid) else '',
            # кто отклонил/принял — reviewed_by (имя), не пустой «—»
            'mod': _best_name(reviewer, mid, book,
                              fallback='ожидает' if st_raw == 'pending' else '—'),
        })
    return render_template('appeals.html', rows=view)


@app.route('/proofs')
@login_required
@role_required('mod')
def proofs():
    gid = _main_guild()
    return render_template('proofs.html', rows=_proofs_list(gid))


@app.route('/proof-media/<path:name>')
@login_required
@role_required('mod')
def proof_media(name):
    """Локальные файлы демок (CDN Discord протухает)."""
    base = (ROOT / 'data' / 'uploads' / 'proofs').resolve()
    # только basename — никаких ../
    safe = Path(name).name
    if not safe or safe.startswith('.'):
        abort(404)
    path = (base / safe).resolve()
    try:
        path.relative_to(base)
    except ValueError:
        abort(404)
    if not path.is_file():
        abort(404)
    return send_from_directory(str(base), safe)


@app.route('/reasons')
@app.route('/rules')
@login_required
@role_required('helper')
def reasons():
    """Правила сервера (+ причины наказаний для mod+)."""
    gid = _main_guild()
    reasons_list, rules = _reasons_bundle(gid)
    role = session.get('role') or 'helper'
    show_reasons = LEVEL.get(role, 0) >= LEVEL['mod']
    allowed = set(_viewer_punish_actions(role))
    annotated = []
    for r in rules:
        if not isinstance(r, dict):
            annotated.append({'title': str(r), 'text': '', 'code': '', 'locked': False, 'note': False})
            continue
        row = dict(r)
        acts = set(row.get('actions') or [])
        row['locked'] = bool(acts) and not (acts & allowed) and not row.get('note')
        annotated.append(row)
    return render_template(
        'reasons.html',
        reasons=reasons_list if show_reasons else [],
        rules=annotated,
        show_reasons=show_reasons,
        limits=_viewer_limits_card(),
    )


@app.get('/api/rules')
@login_required
@role_required('helper')
def api_rules():
    """Правила для селекта наказания, фильтр по action=warn|mute|ban|kick."""
    action = (request.args.get('action') or '').strip().lower()
    allowed = _viewer_punish_actions()
    if action and action not in allowed:
        return jsonify({'ok': False, 'error': 'недоступно', 'items': []}), 403
    try:
        from services.mod_reasons import select_options_data
        key = 'timeout' if action == 'mute' else action
        items = select_options_data(key if action else None)
        # хелперу — только правила, где есть warn/mute
        if session.get('role') == 'helper':
            items = [it for it in items if set(it.get('actions') or []) & {'warn', 'mute'}]
        return jsonify({'ok': True, 'items': items})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)[:160], 'items': []}), 500



# ── routes: owner-only bot pages ───────────────────────────────────────

@app.route('/bot')
@login_required
@role_required('owner')
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
@role_required('owner')
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
@role_required('owner')
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

            if action == 'arm_max':
                P.arm_all_protections(gid, bot_instance)
                flash('Антикраш PRO включён на максимум', 'ok')
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


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'error': 'not found'}), 404
    return render_template(
        'error.html', code=404,
        text='Такой страницы нет — либо ссылка устарела.',
    ), 404


@app.errorhandler(500)
def server_error(_e):
    if request.path.startswith('/api/'):
        return jsonify({'ok': False, 'error': 'server error'}), 500
    return render_template(
        'error.html', code=500,
        text='Что-то сломалось. Попробуй обновить страницу.',
    ), 500


@app.get('/health')
def health():
    return jsonify({'ok': True, 'panel': 'mod-core-v2'})
