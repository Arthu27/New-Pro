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
  войс-мут, «бан», уровни варнов. Выбираются ТОЛЬКО на отдельной странице
  «Роли наказаний» (/role-settings) — здесь их записи нет, чтобы не было
  двух мест правки одной настройки. Роль выбрана — наказание выдаётся ролью
  (и снимается сама по сроку); не выбрана — прежнее поведение
  (таймаут/изоляция).
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
    """Факт «бот в сети» для страниц панели. От списка ролей НЕ зависит
    (раньше «Роли наказаний» считали офлайном по пустому/грузящемуся списку
    ролей — отсюда ложное «Бот офлайн» при живом боте).

    Два источника правды:
    1. бот в ЭТОМ процессе (панель запущена вместе с ботом) — как раньше;
    2. панель в ОТДЕЛЬНОМ процессе (start_panel + start_bot, gunicorn,
       панель на VDS) — свежий пульс бота data/bot_state.json
       (services.bot_bridge). Без него отдельная панель всегда видела
       bot_instance=None и писала «Бот офлайн», даже когда бот работал.
    """
    bot = _bot()
    if bot is not None:
        try:
            guilds = getattr(bot, 'guilds', None)
        except Exception:
            guilds = None
        if guilds:
            return True
        # объект бота есть, но гильдий ещё нет (подключается) — ещё не онлайн
        return False
    from services import bot_bridge as _bb
    return _bb.state_status() == 'online'


def bot_state():
    """'online' | 'starting' | 'offline' — правда о боте для предупреждений.

    1) бот в этом процессе: готов и видит гильдии → online; объект есть,
       но гильдий пока нет → starting (подключается);
    2) бота в процессе нет: свежий пульс из data/bot_state.json
       (панель работает отдельным процессом от бота).
    """
    bot = _bot()
    if bot is not None:
        try:
            guilds = getattr(bot, 'guilds', None)
        except Exception:
            guilds = None
        if guilds:
            try:
                ready = bool(bot.is_ready())
            except Exception:
                ready = True   # стабы тестов без is_ready — считаем готовым
            return 'online' if ready else 'starting'
        return 'starting'      # объект есть, но Discord ещё не отдал гильдии
    from services import bot_bridge as _bb
    return _bb.state_status()


def bot_sees_guild(gid):
    """Видит ли работающий бот эту гильдию (в своём процессе или по пульсу)."""
    if live_guild(gid) is not None:
        return True
    from services import bot_bridge as _bb
    st = _bb.read_state()
    if _bb.state_status(st) == 'offline':
        return False
    return str(gid) in _bb.guild_ids(st)


def live_guild(gid):
    """Объект гильдии из бота ЭТОГО процесса (или None).

    Порядок поиска тот же, что всегда был в _cached_guild_list:
    get_guild, затем страховочный проход по bot.guilds.
    """
    bot = _bot()
    if bot is None:
        return None
    try:
        g = bot.get_guild(int(gid))
    except (TypeError, ValueError):
        g = None
    if g is None:
        try:
            g = next((x for x in bot.guilds if str(x.id) == str(gid)), None)
        except Exception:
            g = None
    return g


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


def _remote_disk_roles(gid):
    """Роли из снимка бота (data/bot_roles_<gid>.json) для панели, в процессе
    которой бота нет (start_panel + start_bot / gunicorn / панель на VDS).

    Требуем СВЕЖИЙ пульс 'online' и что бот реально видит эту гильдию, иначе
    возвращаем пусто — страница честно скажет «бот офлайн/роли недоступны»,
    а не покажет устаревший список.
    """
    from services import bot_bridge as _bb
    st = _bb.read_state()
    if _bb.state_status(st) != 'online':
        return []
    if str(gid) not in _bb.guild_ids(st):
        return []
    rows = _bb.read_roles(gid)
    out = []
    for r in rows or []:
        if r.get('managed'):
            continue                      # управляемые (бот/интеграции) — как в живом списке
        rid = str(r.get('id') or '')
        if not rid or rid == str(gid):    # @everyone — не роль выбора
            continue
        out.append({'id': rid,
                    'name': str(r.get('name') or '?'),
                    'color': r.get('color')})
    return out


def _cached_guild_list(gid, kind):
    """kind: 'roles' | 'channels' — список с кэшем по составу (число объектов)
    и TTL. При изменении состава сигнатура меняется → мгновенный промах."""
    g = live_guild(gid)
    if g is None:
        # живой гильдии в этом процессе нет: в демо отдаём демо-состав
        # (иначе селект мёртв), в отдельном процессе от бота — дисковый
        # снимок ролей бота; в остальном — пустой список, save_settings его
        # отклонит с человеческой подсказкой.
        demo = _demo_guild_list(gid, kind)
        if demo:
            return demo
        if kind == 'roles':
            return _remote_disk_roles(gid)
        return []
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


def mod_view(gid):
    """Конфиг страницы /mod-settings: лестница, исключения, канал меню.

    Роли наказаний сюда НЕ включены — они живут в одном месте, на
    /role-settings (иначе две страницы правят одно хранилище и расходятся).
    """
    return {
        'steps': steps_view(gid),
        'actions': [{'key': k, 'label': v} for k, v in ACTION_LABELS.items()],
        'units': [{'key': k, 'label': v} for k, v in UNITS],
        'temp_whitelist': temp_whitelist(gid),
        'max_steps': MAX_STEPS,
        'bot_online': bot_online(),
        'bot_state': bot_state(),
        'appeal_menu_channel': int(get_route(gid, 'appeal_menu_channel') or 0),
    }


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
