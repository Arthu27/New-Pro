# -*- coding: utf-8 -*-
"""Настройки модерации: лестница авто-наказаний + исключения временных мер.

Живые хранилища (те же, что читает бот — меняешь в панели, бот применяет):
- data/warn_config_<gid>.json, ключ 'steps' — лестница «N варнов → мера»
  (командный формат ladder-add: мут N мин/ч/дн, кик, бан); рендер подписи —
  cogs.ladder._fmt_step, так что в панели и в Discord текст одинаковый.
- data/temp_whitelist.json, ключ str(gid) — кого временные меры (таймаут,
  мут) не трогают вообще (администраторы всегда вне списка). Все наказания
  выдаются через /modpanel.
- data/punish_roles.json (services.punish_roles) — роли наказаний: мут чата,
  войс-мут, «бан». Роль выбрана — наказание выдаётся ролью (и снимается
  сама по сроку); не выбрана — прежнее поведение (таймаут/изоляция).
- data/channel_routes.json, ключ appeal_menu_channel — канал, где живёт
  постоянное меню подачи апелляций (select + окно, апелляция — тредом).

Доступ: страница и изменение — Админ+ (как остальные рискованные настройки).
"""
import json
import os
import threading
import time

from web.routes._common import (
    _log, _fire_panel_notification,
    render_template, session, request, jsonify,
)

from cogs import ladder as LD
from cogs.warnings import load_warn_config
from services import punish_roles as PR
from services.channel_routes import get_route, set_route

# Короткий in-memory кэш ролей/каналов сервера: эти списки дёргаются на
# каждый опрос сразу несколькими страницами настроек (Роли наказаний,
# Настройки модерации, Каналы, Доступ), а состав меняется редко. Кэш
# убирает повторный обход гильдии и «долгую загрузку селектов»; сбрасывается
# при изменении состава (число ролей/каналов изменилось) и по TTL.
_GUILD_CACHE_LOCK = threading.Lock()
_GUILD_LIST_CACHE = {}      # (gid, kind) -> (ts, payload, sig)
_GUILD_LIST_TTL = 15.0      # сек: роли/каналы почти не меняются


def bot_online():
    """Факт: процесс бота поднят и видит гильдии. От списка ролей НЕ зависит
    (раньше «Роли наказаний» считали офлайном по пустому/грузящемуся списку
    ролей — отсюда ложное «Бот офлайн» при живом боте)."""
    bot = _bot()
    try:
        return bool(bot and getattr(bot, 'guilds', None))
    except Exception:
        return False


def _demo_guild_list(gid, kind):
    """Демо-состав ролей/каналов — тот же источник, что у /api/roles,
    /api/channels и всех остальных пикеров (guild_channels_roles).

    Без него в демо-превью селект «Ролей за наказания» оставался с одной
    строкой «— не выдавать —», хотя рядом /api/roles честно отдавал 13 ролей.
    В боевом режиме (бот поднят) сюда не заходим: там пустой список — сигнал
    «сохранять нельзя», и подменять его демо-ролями опасно.
    """
    try:
        import web.app as _app
        if not _app._demo_mode():
            return []
        from web.routes.guild_admin import guild_channels_roles
        channels, roles = guild_channels_roles(gid)
    except Exception as exc:
        _log.debug("_demo_guild_list(): подавлено: %s", exc)
        return []
    if kind == 'roles':
        return [{'id': str(r.get('id') or ''), 'name': r.get('name') or '',
                 'color': r.get('color')} for r in roles if r.get('id')]
    return [{'id': str(c.get('id') or ''), 'name': c.get('name') or ''}
            for c in channels if c.get('id')]


def _cached_guild_list(gid, kind):
    """kind: 'roles' | 'channels' — список с кэшем по составу (число объектов)
    и TTL. При изменении состава сигнатура меняется → мгновенный промах."""
    bot = _bot()
    g = None
    if bot is not None:
        try:
            g = bot.get_guild(int(gid))
        except (TypeError, ValueError):
            g = None
        if g is None:
            try:
                g = next((x for x in bot.guilds if str(x.id) == str(gid)), None)
            except Exception:
                g = None
    if g is None:
        # живой гильдии нет: в демо отдаём демо-состав (иначе селект мёртв),
        # в бою — пустой список, как и раньше (save_settings его отклонит).
        return _demo_guild_list(gid, kind)
    if kind == 'roles':
        sig = len(getattr(g, 'roles', []) or [])
    else:
        sig = len(getattr(g, 'channels', []) or [])
    key = (int(gid), kind)
    now = time.time()
    with _GUILD_CACHE_LOCK:
        hit = _GUILD_LIST_CACHE.get(key)
        if hit and hit[2] == sig and (now - hit[0]) < _GUILD_LIST_TTL:
            return hit[1]
    payload = _build_guild_list(g, kind)
    with _GUILD_CACHE_LOCK:
        _GUILD_LIST_CACHE[key] = (now, payload, sig)
        # лёгкая уборка протухшего
        for k in [k for k, v in _GUILD_LIST_CACHE.items() if (now - v[0]) > 120.0]:
            _GUILD_LIST_CACHE.pop(k, None)
    return payload


def invalidate_guild_lists(gid=None):
    """Сбросить кэш ролей/каналов (после изменений на сервере)."""
    with _GUILD_CACHE_LOCK:
        if gid is None:
            _GUILD_LIST_CACHE.clear()
        else:
            for k in [k for k in _GUILD_LIST_CACHE if k[0] == int(gid)]:
                _GUILD_LIST_CACHE.pop(k, None)


def _build_guild_list(g, kind):
    if kind == 'roles':
        out = []
        for r in sorted(g.roles, key=lambda x: -x.position):
            if r.is_default() or getattr(r, 'managed', False):
                continue
            out.append({'id': str(r.id), 'name': r.name,
                        'color': '#%06x' % r.color.value if r.color else None})
        return out
    out = []
    for ch in g.text_channels:
        out.append({'id': str(ch.id), 'name': ch.name})
    out.sort(key=lambda x: x['name'].lstrip('#').lower())
    return out

ACTIONS = ('mute', 'vmute', 'kick', 'ban')
ACTION_LABELS = {'mute': 'Мут чата', 'vmute': 'Войс-мут', 'kick': 'Кик', 'ban': 'Бан'}
UNITS = (('minute', 'минут'), ('hour', 'часов'), ('day', 'дней'))
TEMP_WHITELIST_PATH = 'data/temp_whitelist.json'
MAX_STEPS = 20
_ID_MIN, _ID_MAX = 17, 22


def _gid(ctx):
    try:
        return int(ctx.active_guild_id() or 0)
    except (TypeError, ValueError):
        return 0


def steps_view(gid):
    """Ступени лестницы с русскими подписями (формат кога 1:1)."""
    cfg = load_warn_config(str(gid))
    raw = cfg.get('steps') or cfg.get('thresholds') or []
    out = []
    seen = set()
    for st in sorted(raw, key=lambda s: int(s.get('count', 0) or 0)):
        count = int(st.get('count', 0) or 0)
        if not count or count in seen:
            continue
        seen.add(count)
        out.append({'count': count,
                    'action': str(st.get('action', 'mute')),
                    'duration': int(st.get('duration', 0) or 0),
                    'unit': str(st.get('unit', 'minute')),
                    'label': LD._fmt_step(st)})
    return out


def normalize_steps(raw):
    """Принять лестницу целиком: уникальные числа, клампы, кик без длительности."""
    if not isinstance(raw, list):
        return []
    out = []
    seen = set()
    for st in raw:
        if not isinstance(st, dict):
            continue
        try:
            count = int(st.get('count', 0) or 0)
        except (TypeError, ValueError):
            count = 0
        if count < 1:                    # «0 варнов» — не ступень, выкидываем
            continue
        if count > 100:
            count = 100
        if count in seen:
            continue
        seen.add(count)
        action = str(st.get('action', 'mute'))
        if action not in ACTIONS:
            action = 'mute'
        try:
            duration = int(st.get('duration', 0) or 0)
        except (TypeError, ValueError):
            duration = 0
        duration = max(0, min(10000, duration))
        unit = str(st.get('unit', 'minute'))
        if unit not in dict(UNITS):
            unit = 'minute'
        if action == 'kick':
            duration = 0
        out.append({'count': count, 'action': action,
                    'duration': duration, 'unit': unit})
        if len(out) >= MAX_STEPS:
            break
    out.sort(key=lambda s: s['count'])
    return out


def save_steps(gid, steps):
    cfg = load_warn_config(str(gid))
    if not isinstance(cfg, dict):
        cfg = {}
    cfg['steps'] = normalize_steps(steps)
    LD._save_warn_config(int(gid), cfg)
    return cfg


def temp_whitelist(gid):
    try:
        with open(TEMP_WHITELIST_PATH, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        row = data.get(str(gid), [])
        return [str(x) for x in row] if isinstance(row, list) else []
    except (OSError, ValueError):
        return []


def save_temp_whitelist(gid, ids):
    clean = []
    for x in ids or ():
        s = str(x).strip()
        if not (s.isdigit() and _ID_MIN <= len(s) <= _ID_MAX):
            continue
        if s in clean:
            continue
        clean.append(s)
        if len(clean) >= 200:
            break
    try:
        with open(TEMP_WHITELIST_PATH, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data[str(gid)] = clean
    os.makedirs('data', exist_ok=True)
    tmp = TEMP_WHITELIST_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, TEMP_WHITELIST_PATH)
    return clean


ROLE_KINDS = (('mute', 'Мут чата'), ('vmute', 'Войс-мут'), ('ban', '«Бан»'))
ROLE_HINTS = {
    'mute': 'Выдаётся вместо таймаута: пока роль на участнике — писать нельзя.',
    'vmute': 'Войс-мут ролью: работает и когда участник не в голосовом канале.',
    'ban': 'Участник остаётся на сервере, но видит только канал апелляции.',
}


def _bot():
    try:
        import web.app as _app
        return _app.bot_instance
    except Exception:
        return None


def guild_roles(gid):
    """Роли сервера для селектов (кэш 15с; без @everyone и managed)."""
    return _cached_guild_list(gid, 'roles')


def guild_channels(gid):
    """Текстовые каналы сервера (кэш 15с; для меню апелляций)."""
    return _cached_guild_list(gid, 'channels')


def roles_view(gid):
    """Выбранные роли наказаний + канал меню апелляций (как их читает бот)."""
    roles = PR.get(gid) or {}
    return {
        'punish_roles': {k: int(roles.get(k) or 0) for k, _l in ROLE_KINDS},
        'kinds': [{'key': k, 'label': lbl, 'hint': ROLE_HINTS[k]}
                  for k, lbl in ROLE_KINDS],
        'appeal_menu_channel': int(get_route(gid, 'appeal_menu_channel') or 0),
    }


def save_punish_roles(gid, mapping):
    """Записать роли наказаний; 0/пусто — снять выбор (вернётся старое поведение)."""
    clean = {}
    for k, _lbl in ROLE_KINDS:
        v = (mapping or {}).get(k)
        try:
            v = int(v or 0)
        except (TypeError, ValueError):
            v = 0
        if v < 0:
            v = 0
        clean[k] = v
    PR.set_roles(gid, **clean)
    return clean


def mod_view(gid):
    steps = steps_view(gid)
    out = {
        'steps': steps,
        'actions': [{'key': k, 'label': v} for k, v in ACTION_LABELS.items()],
        'units': [{'key': k, 'label': v} for k, v in UNITS],
        'temp_whitelist': temp_whitelist(gid),
        'max_steps': MAX_STEPS,
        'bot_online': _bot() is not None,
        'roles': guild_roles(gid),
        'channels': guild_channels(gid),
    }
    out.update(roles_view(gid))
    return out


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/mod-settings')
    @login_required
    @role_required('admin')
    def mod_settings_page():
        return render_template('mod_settings.html',
                               role=session.get('role'),
                               username=session.get('username'),
                               guild_id=_gid(ctx))

    @app.route('/api/guild/<gid>/mod-settings', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_mod_settings(gid):
        # gid из URL — сервер, чьи правила и ACL применяются.
        try:
            acl_gid = int(str(gid))
        except (TypeError, ValueError):
            acl_gid = 0
        gid = _gid(ctx)
        if not gid:
            gid = acl_gid or 0
        if request.method == 'GET':
            return jsonify({'success': True, 'cfg': mod_view(gid)})

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'success': False,
                            'error': 'Пустой или битый JSON'}), 400
        who = session.get('username', '?')
        if 'steps' in data:
            # Классические разрешения: в сохранённой лестнице не должно быть
            # ступеней с действиями, закрытыми роли этого пользователя
            # (те же правила, что в /modpanel, «Пользователях» и планировщике).
            import web.app as _app
            from web.routes._common import viewer_member, acl_action_allowed
            _bot = _app.bot_instance
            _member = viewer_member(_bot, acl_gid) if _bot is not None else None
            for _st in (data.get('steps') or []):
                _act = str(_st.get('action', 'mute') if isinstance(_st, dict) else 'mute').strip().lower()
                if _act in ACTIONS and not acl_action_allowed(acl_gid, _member, _act):
                    return jsonify({'success': False,
                                    'error': f'Нет права: ступень «{ACTION_LABELS.get(_act, _act)}» '
                                             'не разрешена вашей роли (настройка — '
                                             '«Права команд»)'}), 403
            save_steps(gid, data.get('steps'))
            _fire_panel_notification(
                'mod_settings', 'Настройки модерации: лестница обновлена',
                f'{who}: ступеней — {len(steps_view(gid))}')
        if 'temp_whitelist' in data:
            save_temp_whitelist(gid, data.get('temp_whitelist'))
            _fire_panel_notification(
                'mod_settings', 'Исключения временных мер обновлены',
                f'{who}: в списке — {len(temp_whitelist(gid))}')
        if 'punish_roles' in data:
            saved = save_punish_roles(gid, data.get('punish_roles'))
            chosen = ', '.join(f'{k}={v}' for k, lbl in ROLE_KINDS
                               for v in [saved.get(k) or 0] if v) or 'ничего (старое поведение)'
            _fire_panel_notification(
                'mod_settings', 'Роли наказаний обновлены',
                f'{who}: {chosen}')
        if 'appeal_menu_channel' in data:
            try:
                cid = int(data.get('appeal_menu_channel') or 0)
            except (TypeError, ValueError):
                cid = 0
            set_route(gid, 'appeal_menu_channel', cid)
            _fire_panel_notification(
                'mod_settings', 'Канал меню апелляций',
                f'{who}: канал ID {cid or "не выбран"}')
        if data.get('publish_menu'):
            import web.app as _app
            from web.routes._common import _run_async
            bot = _app.bot_instance
            cog = bot.get_cog('Appeals') if bot else None
            g = bot.get_guild(int(gid)) if bot else None
            channel = g.get_channel(int(get_route(gid, 'appeal_menu_channel') or 0)) \
                if g is not None else None
            if cog is None or g is None:
                return jsonify({'success': False,
                                'error': 'Бот офлайн или модуль апелляций не загружен'}), 503
            if channel is None:
                return jsonify({'success': False,
                                'error': 'Сначала выберите канал меню апелляций'}), 400
            try:
                ok, text = _run_async(cog.publish_appeal_menu(channel))
            except Exception as _ex:
                _log.warning('mod-settings publish_menu: %s', _ex)
                return jsonify({'success': False,
                                'error': f'Не получилось: {_ex}'}), 200
            if not ok:
                return jsonify({'success': False, 'error': text}), 200
            _fire_panel_notification(
                'mod_settings', 'Меню апелляций опубликовано',
                f'{who}: {text}')
        return jsonify({'success': True, 'cfg': mod_view(gid)})
