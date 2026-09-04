# -*- coding: utf-8 -*-
"""Страница «Роли наказаний» (Настройки → Роли наказаний).

Один экран — ВСЕ роли, которые система наказаний умеет выдавать:
- базовые виды: мут чата, войс-мут, «бан»(изоляция) — 1:1 со старой
  страницей «Настройки модерации» (там блок остаётся, значения общие);
- уровни варнов warn_N (1..100, НЕ фиксированные 10) — владелец сам
  добавляет уровни; роль ближайшего уровня выдаётся сама при варне,
  роль предыдущего уровня снимается (cogs/warnings).

Выбор только через селекты (роли подтягиваются с сервера бота),
ручного ввода ID нет — требование владельца 2026-08-28.
Сохранение одним POST — все селекты разом.
"""
import re

from flask import render_template, session, request
from web.routes._common import jsonify

from services import punish_roles as PR
from web.routes._common import _fire_panel_notification, _log
from web.routes.mod_settings import (guild_roles, bot_state,
                                     bot_sees_guild, live_guild)

_ID_RE = re.compile(r'^\d{1,22}$')

BASE_KINDS = (
    ('mute', 'Мут чата', 'fa-comment-slash',
     'Выдаётся вместо таймаута: пока роль на участнике — писать нельзя.'),
    ('vmute', 'Войс-мут', 'fa-microphone-slash',
     'Войс-мут ролью: работает и когда участник не в голосовом канале.'),
    ('ban', '«Бан» (изоляция)', 'fa-user-lock',
     'Участник остаётся на сервере, но видит только канал апелляции.'),
)


def _gid(ctx):
    return ctx.active_guild_id()


def kinds_view():
    return [{'key': k, 'label': lbl, 'icon': ico, 'hint': hint}
            for k, lbl, ico, hint in BASE_KINDS]


def levels_view(gid=None):
    """Карточки уровней варнов: только те, что владелец добавил сам
    (warn_levels), плюс уровни, у которых уже выбрана роль."""
    lvls = PR.levels(gid) if gid else []
    return [{'key': f'warn_{lvl}', 'level': lvl,
             'label': f'{lvl} {_plural(lvl)}',
             'icon': 'fa-triangle-exclamation'}
            for lvl in lvls]


def _plural(n):
    if n == 1:
        return 'предупреждение'
    if n in (2, 3, 4):
        return 'предупреждения'
    return 'предупреждений'


PUNISH_INFO = (
    ('timeout', 'Таймаут', 'fa-clock',
     'Нативный механизм Discord: бот замораживает участника через API — отдельная роль не нужна и не поддерживается.'),
    ('kick', 'Кик', 'fa-door-open',
     'Участник просто удаляется с сервера (может вернуться по ссылке) — роль не требуется.'),
    ('unban', 'Разбан', 'fa-user-plus',
     'Отмена бана/изоляции: бот сам снимает роль изоляции и восстанавливает доступ.'),
)


def settings_view(gid):
    """Что видит экран: готовые селекты + текущий выбор бота."""
    roles = PR.get(gid)
    available = guild_roles(gid)
    avail_ids = {r['id'] for r in available}
    # помечаем выборы на несуществующие роли — их селект покажет как «роль удалена»
    mapping = {}
    unknown = 0
    for k, v in roles.items():
        sid = str(v)
        mapping[k] = sid
        if available and sid not in avail_ids:
            unknown += 1
    st = bot_state()            # 'online' | 'starting' | 'offline'
    online = st == 'online'
    guild_ok = bot_sees_guild(gid)
    import web.app as _app
    demo_on = bool(_app._demo_mode())
    # Откуда пришли роли: живой кэш бота / снимок бота на диске (панель
    # отдельным процессом) / демо-набор превью. Пусто — бота нет и ролей нет.
    source = ''
    if available:
        if demo_on:
            source = 'demo'
        elif live_guild(gid) is not None:
            source = 'live'
        else:
            source = 'disk'
    return {
        'success': True,
        'kinds': kinds_view(),
        'levels': levels_view(gid),
        'warn_level_min': PR.WARN_LEVEL_MIN,
        'warn_level_max': PR.WARN_LEVEL_MAX,
        'punish_info': [{'key': k, 'label': lbl, 'icon': ico, 'hint': hint}
                        for k, lbl, ico, hint in PUNISH_INFO],
        'mapping': mapping,
        'roles': available,
        'roles_count': len(available),
        # список есть, а бота в процессе нет — демо/снимок, а не живой кэш
        'roles_from_demo': source == 'demo',
        'roles_source': source,
        'demo': demo_on,
        'unknown_roles': unknown,
        # Онлайн определяем по ФАКТУ бота (в процессе или по свежему пульсу),
        # а не по списку ролей: при живом боте роли могли ещё не догрузиться —
        # раньше это врало «Бот офлайн».
        'bot_online': online,
        'bot_state': st,
        'bot_guild_ok': guild_ok,
    }


def save_settings(gid, mapping, who='?'):
    """Проверить и сохранить весь выбор; вернуть (ok, err, saved).

    Роль обязана существовать на сервере (выбор — только из списка бота,
    ручной ID отклоняем), ключ — только известный вид/уровень.
    """
    if not isinstance(mapping, dict):
        return False, 'Пустой набор ролей', None
    available = guild_roles(gid)
    if not available:
        return False, ('Бот офлайн: список ролей сервера недоступен — '
                       'сохранять сейчас нельзя'), None
    avail_ids = {r['id'] for r in available}
    clean, bad = {}, []
    for key, raw in mapping.items():
        key = str(key or '')
        if not PR.valid_kind(key):
            bad.append(key)
            continue
        sid = str(raw or '').strip()
        if sid in ('', '0'):
            clean[key] = 0
            continue
        if not _ID_RE.match(sid) or sid not in avail_ids:
            bad.append(key)
            continue
        clean[key] = int(sid)
    if bad:
        return False, ('Часть выборов — не роль этого сервера '
                       f'({", ".join(sorted(bad))}) — ничего не сохранено'), None
    saved = PR.set_roles(gid, who=str(who or '?'), **clean)
    return True, None, saved


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/role-settings')
    @login_required
    @role_required('admin')
    def role_settings_page():
        return render_template('role_settings.html',
                               role=session.get('role'),
                               username=session.get('username'),
                               guild_id=ctx.active_guild_id())

    @app.route('/api/guild/<gid>/role-settings', methods=['GET'])
    @login_required
    @role_required('admin')
    def api_role_settings(gid):
        try:
            return jsonify(settings_view(gid))
        except Exception as _ex:
            _log.debug('role-settings GET: %s', _ex)
            return jsonify({'success': False,
                            'error': 'Не удалось собрать настройки ролей'}), 500

    @app.route('/api/guild/<gid>/role-settings', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_role_settings_save(gid):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'success': False,
                            'error': 'Пустой или битый JSON'}), 400
        who = session.get('username', '?')
        ok, err, saved = save_settings(gid, data.get('mapping'), who=who)
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        chosen = ', '.join(f'{k}→{v}' for k, v in sorted(saved.items())
                           if v) or 'ничего (старое поведение)'
        _fire_panel_notification(
            'mod_settings', 'Роли наказаний обновлены',
            f'{who}: {chosen}')
        view = settings_view(gid)
        view['message'] = 'Роли наказаний сохранены'
        return jsonify(view)

    @app.route('/api/guild/<gid>/role-settings/warn-level', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_role_settings_warn_level_add(gid):
        """Добавить уровень варнов (карточку «N предупреждений → роль»)."""
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'success': False, 'error': 'Пустой или битый JSON'}), 400
        ok, err = PR.add_level(ctx.active_guild_id() or gid, data.get('level'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        view = settings_view(gid)
        return jsonify({'success': True, 'levels': view['levels'],
                        'message': err})

    @app.route('/api/guild/<gid>/role-settings/warn-level/<int:level>', methods=['DELETE'])
    @login_required
    @role_required('admin')
    def api_role_settings_warn_level_del(gid, level):
        """Удалить уровень: карточку и её роль (если была выбрана)."""
        ok, err = PR.remove_level(ctx.active_guild_id() or gid, level)
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        view = settings_view(gid)
        return jsonify({'success': True, 'levels': view['levels'],
                        'message': err})
