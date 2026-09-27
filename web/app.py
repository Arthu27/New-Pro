# -*- coding: utf-8 -*-
"""Минимальная панель модерации (v2). Без старого web/-меню и демо-данных.

Страницы: docs/PANEL-PAGES.md
Роли: owner > mod. Страницы бота — только owner.
"""
from __future__ import annotations

import json
import os
import secrets
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

LEVEL = {'mod': 1, 'owner': 9}
PAGES_MOD = [
    ('today', '/', 'Сегодня', 'fa-gauge-high'),
    ('logs', '/logs', 'Журнал', 'fa-scroll'),
    ('member', '/member', 'Участник', 'fa-user'),
    ('warns', '/warns', 'Варны', 'fa-triangle-exclamation'),
    ('appeals', '/appeals', 'Апелляции', 'fa-scale-balanced'),
    ('proofs', '/proofs', 'Демки', 'fa-camera'),
    ('reasons', '/reasons', 'Причины', 'fa-list'),
]
PAGES_OWNER = [
    ('bot', '/bot', 'Бот', 'fa-robot'),
    ('modules', '/modules', 'Модули', 'fa-puzzle-piece'),
    ('commands', '/commands', 'Команды', 'fa-terminal'),
    ('anticrash', '/anticrash', 'Антикраш', 'fa-shield-heart'),
    ('access', '/access', 'Доступ', 'fa-key'),
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


def _auth_user(username, password):
    """Вернуть (username, role) или None."""
    username = (username or '').strip()
    password = password or ''
    if not username or not password:
        return None
    env_u, env_pw = _env_owner_creds()
    if env_pw and username == env_u and password == env_pw:
        return env_u, 'owner'
    for u in _load_access()['users']:
        if str(u.get('username', '')).strip() != username:
            continue
        if str(u.get('password', '')) != password:
            return None
        role = str(u.get('role') or 'mod').strip().lower()
        if role not in LEVEL:
            role = 'mod'
        # доп. аккаунты не могут быть owner через файл — только через .env
        if role == 'owner':
            role = 'mod'
        return username, role
    return None


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
            have = LEVEL.get(session.get('role') or 'mod', 0)
            if have < need:
                abort(403)
            return f(*a, **kw)
        return wrapped
    return deco


@app.context_processor
def inject_nav():
    role = session.get('role') or ''
    pages = list(PAGES_MOD)
    if role == 'owner':
        pages = pages + list(PAGES_OWNER)
    return {
        'nav_pages': pages,
        'user_name': session.get('username') or '',
        'user_role': role,
        'is_owner': role == 'owner',
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('today'))
    err = ''
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        got = _auth_user(username, password)
        if got:
            session.clear()
            session['logged_in'] = True
            session['username'] = got[0]
            session['role'] = got[1]
            nxt = request.args.get('next') or url_for('today')
            if not nxt.startswith('/'):
                nxt = url_for('today')
            return redirect(nxt)
        err = 'Неверный логин или пароль'
    _, env_pw = _env_owner_creds()
    hint = '' if env_pw else 'Задайте PANEL_PASSWORD в .env'
    return render_template('login.html', error=err, hint=hint)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── routes: mod pages ──────────────────────────────────────────────────

@app.route('/')
@login_required
@role_required('mod')
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
@role_required('mod')
def logs():
    gid = _main_guild()
    rows = _collect_cases(gid)[:200]
    for r in rows:
        r['when'] = _fmt(r.get('timestamp'))
    return render_template('logs.html', rows=rows)


@app.route('/member')
@login_required
@role_required('mod')
def member():
    q = (request.args.get('q') or '').strip()
    rows = []
    if q:
        gid = _main_guild()
        all_rows = _collect_cases(gid)
        ql = q.lower()
        for r in all_rows:
            if (ql in str(r.get('user_id', '')).lower()
                    or ql in str(r.get('user_name', '')).lower()):
                r = dict(r)
                r['when'] = _fmt(r.get('timestamp'))
                rows.append(r)
                if len(rows) >= 100:
                    break
    return render_template('member.html', q=q, rows=rows)


@app.route('/warns')
@login_required
@role_required('mod')
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
@role_required('owner')
def anticrash_page():
    """Антикраш — только owner. UI с нуля, данные из error_handler."""
    eh = _anticrash_handler()
    err = ''
    if request.method == 'POST':
        if not eh:
            err = 'Бот офлайн — конфиг не сохранить'
        else:
            try:
                from error_handler import DEFAULT_CONFIG
                key = (request.form.get('key') or '').strip()
                if key not in DEFAULT_CONFIG:
                    err = 'Неизвестный ключ'
                else:
                    raw = request.form.get('value')
                    if isinstance(DEFAULT_CONFIG[key], bool):
                        raw = request.form.get('value') == '1'
                    eh.update_config(key, raw)
                    flash('Сохранено', 'ok')
                    return redirect(url_for('anticrash_page'))
            except Exception as ex:
                err = str(ex)
    overview = {}
    config = {}
    meta = {}
    if eh:
        try:
            overview = eh.get_overview() or {}
        except Exception:
            overview = {'ok': False}
        try:
            from error_handler import CONFIG_META, DEFAULT_CONFIG
            config = dict(getattr(eh, 'config', None) or DEFAULT_CONFIG)
            meta = CONFIG_META
        except Exception:
            pass
    else:
        overview = {'ok': False, 'error': 'Обработчик офлайн'}
        try:
            from error_handler import CONFIG_META, DEFAULT_CONFIG
            config = dict(DEFAULT_CONFIG)
            # файл на диске, если бот ещё не поднялся
            disk = _read_json(DATA / 'anticrash_config.json', {})
            if isinstance(disk, dict):
                config.update(disk)
            meta = CONFIG_META
        except Exception:
            pass
    # ключевые тумблеры для красивого UI (остальное — расширенный блок)
    toggles = [
        'master_enabled', 'alerts_enabled', 'loop_watchdog', 'cog_breaker',
        'filter_enabled', 'connection_watch', 'warning_monitor', 'webhook_enabled',
    ]
    return render_template(
        'anticrash.html',
        overview=overview,
        config=config,
        meta=meta,
        toggles=toggles,
        error=err,
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
            note = (request.form.get('note') or '').strip()[:80]
            if not username or not password:
                err = 'Нужны логин и пароль'
            elif username == _env_owner_creds()[0]:
                err = 'Этот логин занят владельцем (.env)'
            elif any(u.get('username') == username for u in data['users']):
                err = 'Такой логин уже есть'
            else:
                data['users'].append({
                    'username': username,
                    'password': password,
                    'role': 'mod',
                    'note': note,
                })
                _save_access(data)
                flash('Модератору выдан вход', 'ok')
                return redirect(url_for('access_page'))
        elif action == 'del':
            username = (request.form.get('username') or '').strip()
            data['users'] = [u for u in data['users'] if u.get('username') != username]
            _save_access(data)
            flash('Доступ снят', 'ok')
            return redirect(url_for('access_page'))
    env_u, _ = _env_owner_creds()
    mod_pages = [p[2] for p in PAGES_MOD]
    owner_only = [p[2] for p in PAGES_OWNER]
    return render_template(
        'access.html',
        users=data['users'],
        owner_user=env_u,
        error=err,
        mod_pages=mod_pages,
        owner_only=owner_only,
    )


@app.errorhandler(403)
def forbidden(_e):
    return render_template('error.html', code=403,
                           text='Недостаточно прав. Страницы бота — только владельцу.'), 403


@app.get('/health')
def health():
    return jsonify({'ok': True, 'panel': 'mod-core-v2'})
