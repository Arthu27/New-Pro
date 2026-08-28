# -*- coding: utf-8 -*-
"""Страница «Роли наказаний» (Настройки → Роли наказаний).

Один экран — ВСЕ роли, которые система наказаний умеет выдавать:
- базовые виды: мут чата, войс-мут, «бан»(изоляция) — 1:1 со старой
  страницей «Настройки модерации» (там блок остаётся, значения общие);
- уровни варнов warn_1..warn_10 — роль ближайшего уровня выдаётся
  сама при варне, роль предыдущего уровня снимается (cogs/warnings).

Выбор только через селекты (роли подтягиваются с сервера бота),
ручного ввода ID нет — требование владельца 2026-08-28.
Сохранение одним POST — все селекты разом.
"""
import re

from flask import render_template, session, jsonify, request

from services import punish_roles as PR
from web.routes._common import _fire_panel_notification, _log
from web.routes.mod_settings import guild_roles

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


def levels_view():
    """Селекты уровней варнов: warn_1…warn_N (одноразовая фича — ровно N варнов)."""
    return [{'key': f'warn_{lvl}', 'level': lvl,
             'label': f'{lvl} {_plural(lvl)}',
             'icon': 'fa-triangle-exclamation'}
            for lvl in range(PR.WARN_LEVEL_MIN, PR.WARN_LEVEL_MAX + 1)]


def _plural(n):
    if n == 1:
        return 'предупреждение'
    if n in (2, 3, 4):
        return 'предупреждения'
    return 'предупреждений'


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
    return {
        'success': True,
        'kinds': kinds_view(),
        'levels': levels_view(),
        'mapping': mapping,
        'roles': available,
        'roles_count': len(available),
        'unknown_roles': unknown,
        'bot_online': bool(available),
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
