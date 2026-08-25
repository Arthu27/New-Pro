# -*- coding: utf-8 -*-
"""Каталог всех команд бота: статический разбор cogs/*.py через AST.

Один источник правды для панели («Команды») и справки /help: разбирает
декораторы @app_commands.command / @<группа>.command / @commands.command /
@hybrid_command, вытаскивает имена, описания (description/docstring),
алиасы, слеш-группы и раскладывает команды по русским категориям с иконками.

Кэшируется по mtime каталога cogs/ — пересборка только после правок кода.
"""
import ast
import os

from logger import get_logger

_log = get_logger('command_registry')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COGS_DIR = os.path.join(ROOT, 'cogs')

# ── Категории каталога (ключ → подпись + иконка Font Awesome + цвет) ─────
# Порядок словаря = порядок показа в панели и в /help.
CATEGORIES = {
    'mod': {'label': 'Модерация', 'icon': 'fa-shield-halved'},
    'tickets': {'label': 'Тикеты', 'icon': 'fa-ticket'},
    'logs': {'label': 'Логи и аудит', 'icon': 'fa-scroll'},
    'music': {'label': 'Музыка', 'icon': 'fa-music'},
    'voice': {'label': 'Голосовые', 'icon': 'fa-headset'},
    'economy': {'label': 'Экономика', 'icon': 'fa-coins'},
    'levels': {'label': 'Уровни и карма', 'icon': 'fa-arrow-trend-up'},
    'fun': {'label': 'Игры и развлечения', 'icon': 'fa-dice'},
    'profile': {'label': 'Профили и соц.', 'icon': 'fa-id-card'},
    'info': {'label': 'Инфо и поиск', 'icon': 'fa-circle-info'},
    'automation': {'label': 'Автоматизация', 'icon': 'fa-robot'},
    'ai': {'label': 'AI', 'icon': 'fa-brain'},
    'events': {'label': 'События и команда', 'icon': 'fa-calendar-days'},
    'welcome': {'label': 'Приветствие и вход', 'icon': 'fa-handshake'},
    'system': {'label': 'Система', 'icon': 'fa-server'},
    'misc': {'label': 'Прочее', 'icon': 'fa-puzzle-piece'},
}

# ── Файл модуля → категория ──────────────────────────────────────────────
MODULE_CATEGORY = {
    # модерация ядром и инструментами
    'moderation.py': 'mod', 'moderation_cog.py': 'mod', 'advanced_mod.py': 'mod',
    'mod_case.py': 'mod', 'mod_kit.py': 'mod', 'mod_plus.py': 'mod',
    'mod_tools.py': 'mod', 'warnings.py': 'mod', 'temp_moderation.py': 'mod',
    'proof_cog.py': 'mod', 'auto_filter.py': 'mod', 'antiraid.py': 'mod',
    'security.py': 'mod', 'verification.py': 'mod', 'tag_jail.py': 'mod',
    'impersonation.py': 'mod', 'anti_alt.py': 'mod', 'lockdown.py': 'mod',
    'night_mode.py': 'mod', 'media_only.py': 'mod', 'rejoin_roles.py': 'mod',
    'report_cog.py': 'mod', 'dm_report.py': 'mod', 'appeals.py': 'mod',
    'ladder.py': 'mod', 'ab_cog.py': 'mod',
    # тикеты и поддержка
    'ticket.py': 'tickets', 'sla_cog.py': 'tickets', 'staff_apply.py': 'tickets',
    # логи, аудит, архивы
    'logs.py': 'logs', 'log_menu.py': 'logs', 'dm_logger.py': 'logs',
    'recap.py': 'logs', 'replay.py': 'logs', 'archive.py': 'logs',
    'backup_cog.py': 'logs',
    # музыка и голос
    'music_cog.py': 'music',
    'voice_commands.py': 'voice', 'voice_tracker.py': 'voice',
    'join_to_create.py': 'voice',
    # экономика
    'economy_cog.py': 'economy', 'economy_shop.py': 'economy',
    # уровни, карма, активность
    'level_cog.py': 'levels', 'leveling_engagement.py': 'levels',
    'karma.py': 'levels', 'gamification_cog.py': 'levels',
    'time_tracking_cog.py': 'levels',
    # игры и веселуха
    'fun_cog.py': 'fun', 'minigames.py': 'fun', 'duels.py': 'fun',
    'quiz.py': 'fun', 'anime_daily.py': 'fun', 'companion.py': 'fun',
    'counting.py': 'fun',
    # профили и социальное
    'profile.py': 'profile', 'birthday.py': 'profile', 'starboard.py': 'profile',
    'social.py': 'profile', 'achievements.py': 'profile',
    # инфо, поиск, статистика
    'info_tools.py': 'info', 'server_info.py': 'info', 'search_cog.py': 'info',
    'server_stats.py': 'info', 'leaderboard.py': 'info',
    # автоматизация и контент
    'triggers.py': 'automation', 'scheduler.py': 'automation',
    'reminders.py': 'automation', 'custom_commands.py': 'automation',
    'custom_embeds.py': 'automation', 'webhooks.py': 'automation',
    'night_summary.py': 'automation', 'server_template.py': 'automation',
    # AI
    'ai_chat.py': 'ai', 'ai_moderation.py': 'ai',
    'proactive_ai.py': 'ai', 'proactive_mod.py': 'ai',
    # события и команда
    'giveaway.py': 'events', 'meeting.py': 'events', 'events.py': 'events',
    'duty.py': 'events', 'staff_rating.py': 'events',
    'staff_shifts.py': 'events', 'staff_stats.py': 'events',
    'weekly_crown.py': 'events',
    # вход и приветствие
    'welcome_cog.py': 'welcome', 'welcome_card.py': 'welcome',
    'welcome_pro.py': 'welcome', 'invite_tracker.py': 'welcome',
    'autorole_join.py': 'welcome', 'autorole_level.py': 'welcome',
    'reaction_roles_cog.py': 'welcome',
    # система
    'help.py': 'system', 'health.py': 'system', 'diagnostics.py': 'system',
    'cog_manager.py': 'system', 'feature_flag_cog.py': 'system',
    'changelog_cog.py': 'system', 'mod_report.py': 'system',
    'stats.py': 'system', 'mod_digest.py': 'system',
    # утилиты
    'afk.py': 'misc',
}

# Модули-исполнители: этим командам панель умеет показывать форму «Выполнить»
# (белый список дублирует серверный /api/execute-command).
EXECUTABLE = ('ban', 'timeout', 'warn', 'jail', 'unjail')

_KIND_LABEL = {'slash': 'SLASH', 'prefix': 'PREFIX', 'sub': 'SLASH'}

_cache = {'stamp': None, 'data': None}


def _const_str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _const_list(node):
    if isinstance(node, (ast.List, ast.Tuple)):
        out = []
        for el in node.elts:
            if isinstance(el, ast.Constant) and isinstance(el.value, str):
                out.append(el.value)
        return out
    return []


def _kwargs(call):
    out = {}
    if isinstance(call, ast.Call):
        for kw in call.keywords:
            out[kw.arg] = kw.value
    return out


def _clean_desc(text, limit=140):
    if not text:
        return ''
    line = str(text).strip().split('\n')[0].strip()
    line = line.rstrip('.')
    return line[:limit]


def _enabled_module_files():
    """Файлы модулей, которые реально загрузит бот (профиль cogs_policy).

    Каталог показывает ТОЛЬКО живые команды: спящие по профилю модули
    (BOT_FULL=0 по умолчанию — лёгкий состав) честно не отображаются.
    """
    try:
        import cogs_policy
        files = sorted(f for f in os.listdir(COGS_DIR) if f.endswith('.py'))
        enabled, _gone = cogs_policy.select_from_environment(files)
        return set(enabled), len(_gone)
    except Exception as _ex:
        _log.debug('command_registry: профиль недоступен (%s) — показываю всё', _ex)
        return {f for f in os.listdir(COGS_DIR)
                if f.endswith('.py') and not f.startswith('_')}, 0


def _scan():
    enabled_files, sleeping = _enabled_module_files()
    commands = []
    for fn in sorted(os.listdir(COGS_DIR)):
        if not fn.endswith('.py') or fn.startswith('_'):
            continue
        if fn not in enabled_files:
            continue
        path = os.path.join(COGS_DIR, fn)
        try:
            tree = ast.parse(open(path, encoding='utf-8').read())
        except (SyntaxError, UnicodeDecodeError) as _ex:
            _log.debug('command_registry: %s пропущен: %s', fn, _ex)
            continue

        # слеш-группы: varname = app_commands.Group(name=...)
        groups = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                f = node.value.func
                if isinstance(f, ast.Attribute) and f.attr == 'Group':
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            kw = _kwargs(node.value)
                            gname = _const_str(kw.get('name')) or t.id
                            groups[t.id] = gname.strip().lower()

        cat = MODULE_CATEGORY.get(fn, 'misc')
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for d in node.decorator_list:
                func = d.func if isinstance(d, ast.Call) else d
                kind = None
                group = None
                if isinstance(func, ast.Attribute) and func.attr == 'command':
                    base = func.value
                    base_id = getattr(base, 'id', None)
                    if base_id == 'app_commands':
                        kind = 'slash'
                    elif base_id == 'commands':
                        kind = 'prefix'
                    elif base_id in groups:
                        kind = 'sub'
                        group = groups[base_id]
                elif isinstance(func, ast.Name) and func.id == 'hybrid_command':
                    kind = 'prefix'   # гибрид доступен и как префикс
                if not kind:
                    continue

                kw = _kwargs(d) if isinstance(d, ast.Call) else {}
                name = _const_str(kw.get('name'))
                if not name:
                    name = node.name
                    for pre in ('cmd_', 'wc_', 'wc'):
                        if name.startswith(pre) and len(name) > len(pre) + 1:
                            name = name[len(pre):]
                            break
                name = name.strip().lower().replace('_', '-')
                if not name:
                    continue
                desc = (_clean_desc(_const_str(kw.get('description')))
                        or _clean_desc(ast.get_docstring(node)))
                aliases = _const_list(kw.get('aliases'))
                qualified = f'{group} {name}' if group else name
                commands.append({
                    'name': qualified,
                    'bare': name,
                    'kind': kind,
                    'group': group or '',
                    'cat': cat,
                    'module': fn,
                    'desc': desc or 'Описание скоро появится',
                    'aliases': aliases[:4],
                    'executable': name in EXECUTABLE,
                })
    # стабильный порядок: категория → имя; дубли квалифицированного имени
    # (одна и та же команда в двух модулях) сворачиваем в первую запись.
    order = {k: i for i, k in enumerate(CATEGORIES)}
    commands.sort(key=lambda c: (order.get(c['cat'], 99), c['name']))
    seen = set()
    deduped = []
    for c in commands:
        if c['name'] in seen:
            continue
        seen.add(c['name'])
        deduped.append(c)

    # Честность боевого меню: slash_budget при загрузке бота жёстко режет
    # глобальное slash-меню до KEEP_SLASH. Каталог панели обязан показывать
    # то же, что видит пользователь, поэтому в боевом профиле (не BOT_FULL)
    # вычищенные слеши/подкоманды из каталога тоже убираем.
    try:
        from slash_budget import KEEP_SLASH
    except Exception:
        KEEP_SLASH = frozenset()
    full_requested = (os.environ.get('BOT_FULL', '') or '').strip() not in ('', '0', 'false', 'False')
    if KEEP_SLASH and not full_requested:
        keep = set(KEEP_SLASH)
        deduped = [c for c in deduped
                   if c['kind'] == 'prefix'
                   or c['bare'] in keep or c['name'] in keep]
    return deduped



def _annotate_switches(data):
    """Пометить выключенные владельцем команды (кэш не должен мешать).

    Каталог кэшируется по mtime cogs/, а переключатели живут в другом
    файле — поэтому флаг off проставляется при каждом обращении.
    """
    try:
        from services import command_switches as _csw
        off = _csw.disabled_set()
    except Exception:
        off = set()

    def _is_off(c):
        name = _csw_norm(c.get('name') or '')
        bare = _csw_norm(c.get('bare') or '')
        return bool(off) and (name in off or bare in off)

    try:
        from services.command_switches import normalize as _csw_norm
    except Exception:
        return data
    n = 0
    for c in data.get('commands', []):
        flag = _is_off(c)
        c['off'] = flag
        n += 1 if flag else 0
    data['disabled'] = n
    return data


def catalog(force=False):
    """Полный каталог с кэшем по mtime каталога cogs/ + профилю модулей."""
    try:
        stamp = max(os.path.getmtime(os.path.join(COGS_DIR, f))
                    for f in os.listdir(COGS_DIR) if f.endswith('.py'))
    except OSError:
        stamp = 0
    # профиль модулей — часть ключа кэша: BOT_FULL/профили меняют набор команд
    stamp = (stamp, tuple(sorted((k, os.environ.get(k, '')) for k in
                                 ('BOT_FULL', 'MOD_ONLY', 'BOT_SLIM', 'BOT_CORE',
                                  'DISABLED_COGS', 'EXTRA_COGS'))))
    if not force and _cache['data'] is not None and _cache['stamp'] == stamp:
        return _annotate_switches(_cache['data'])

    commands = _scan()
    enabled_files, sleeping = _enabled_module_files()
    cats = []
    for key, meta in CATEGORIES.items():
        n = sum(1 for c in commands if c['cat'] == key)
        if n:
            cats.append({'id': key, 'label': meta['label'],
                         'icon': meta['icon'], 'count': n})
    data = {
        'total': len(commands),
        'slash': sum(1 for c in commands if c['kind'] == 'slash'),
        'subs': sum(1 for c in commands if c['kind'] == 'sub'),
        'prefix': sum(1 for c in commands if c['kind'] == 'prefix'),
        'modules': {'enabled': len(enabled_files), 'sleeping': sleeping},
        'categories': cats,
        'commands': commands,
    }
    _cache['stamp'] = stamp
    _cache['data'] = data
    return _annotate_switches(data)


def catalog_by_category():
    """{label: [имена]} для /help — только категории с командами."""
    data = catalog()
    out = {}
    for cat in data['categories']:
        out[cat['label']] = [c['name'] for c in data['commands']
                             if c['cat'] == cat['id']]
    return out
