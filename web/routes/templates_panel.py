# -*- coding: utf-8 -*-
"""Шаблоны сервера (идеи #151-155): /шаблон из браузера.

Хранилище — GuildData('server_template'), ключ 'templates' — как в коге.
Чистые функции кога используются напрямую (snapshot_guild / template_meta /
diff_plan), применение повторяет cmd_apply шаг за шагом: только СОЗДАЁТ
отсутствующее (по именам, lower), существующее не трогает; роли — с правами
и цветом, каналы — с темой/слоумодом/nsfw, reason со словом шаблона.

Тексты ответов — словами команд (маркдаун-звёзды сняты стилем панели).
Снимок, план и применение требуют живого бота (офлайн — честный 409);
список, инфо, удаление и выгрузки работают и офлайн.

Чтение — mod+; снимок/удаление/применение — admin+ (команда хотела
administrator).
"""
import json
from datetime import datetime, timezone

from web.routes._common import (
    _log, _run_async,
    render_template, session, request, jsonify, Response,
    discord,
)

from db import GuildData
from cogs import server_template as ST

UTC = timezone.utc

db = GuildData('server_template')

ERR_EMPTY_NAME = 'Имя шаблона пустое.'
ERR_OFFLINE_SNAP = 'Бот офлайн — снимок делается с живого сервера.'
ERR_OFFLINE_PLAN = 'Бот офлайн — сравнивать не с чем: список работает и офлайн.'
ERR_OFFLINE_APPLY = 'Бот офлайн — применять шаблон может только живой бот.'
TEXT_NONE_YET = 'Шаблонов пока нет. Сделайте /шаблон сохранить <имя>.'
TEXT_NOTHING = 'Структура уже совпадает — создавать нечего.'


def _store(gid):
    return db.get(gid, 'templates', ST.empty_store()) or ST.empty_store()


def _save(gid, store):
    db.set(gid, 'templates', store)


def norm_name(raw):
    """Правило команды: strip + lower + 30 знаков."""
    return str(raw or '').strip().lower()[:30]


def err_not_found(name):
    return f'Шаблон «{name}» не найден.'


def list_view(gid):
    """Библиотека: имя + сводка его template_meta + карточка-инфо."""
    out = []
    for name, entry in _store(gid).items():
        out.append({
            'name': name,
            'meta': ST.template_meta(entry['template']),
            'description': str(entry.get('description') or ''),
            'created_at': str(entry.get('created_at') or ''),
            'created_by': str(entry.get('created_by') or ''),
            'source_guild': str(entry.get('source_guild') or ''),
        })
    return {'templates': out, 'count': len(out), 'max': ST.MAX_TEMPLATES,
            'empty_text': TEXT_NONE_YET if not out else None}


def info_view(gid, name_raw):
    """Содержимое шаблона — разрез как в /шаблон инфо."""
    name = norm_name(name_raw)
    entry = _store(gid).get(name)
    if not entry:
        return False, err_not_found(name), None
    tpl = entry['template']
    return True, '', {
        'name': name,
        'title': f'Шаблон «{name}» · {ST.template_meta(tpl)}',
        'roles': [r['name'] for r in tpl.get('roles', [])[:15]],
        'roles_total': len(tpl.get('roles', [])),
        'categories': [{'name': c['name'],
                        'channels': [ch['name'] for ch in c.get('channels', [])]}
                       for c in tpl.get('categories', [])[:10]],
        'channels': [c['name'] for c in tpl.get('channels', [])],
        'footer': (f"Создан: {str(entry.get('created_at', ''))[:10]} · "
                   f"{entry.get('created_by', '')}"),
        'description': str(entry.get('description') or ''),
    }


def save_flow(bot, gid, name_raw, description, by):
    """Снимок живого сервера — шаги /шаблон сохранить."""
    name = norm_name(name_raw)
    if not name:
        return False, ERR_EMPTY_NAME, None
    if bot is None:
        return False, ERR_OFFLINE_SNAP, None
    guild = bot.get_guild(int(gid))
    if guild is None:
        return False, ERR_OFFLINE_SNAP, None
    store = _store(gid)
    if name not in store and len(store) >= ST.MAX_TEMPLATES:
        return False, f'Максимум {ST.MAX_TEMPLATES} шаблонов на сервер.', None
    tpl = ST.snapshot_guild(guild)
    store[name] = {
        'template': tpl,
        'description': str(description or '')[:200],
        'created_at': datetime.now(UTC).isoformat(),
        'created_by': str(by),
        'source_guild': getattr(guild, 'name', ''),
    }
    _save(gid, store)
    msg = f'Шаблон «{name}» сохранён: {ST.template_meta(tpl)}.'
    return True, '', {'message': msg, 'meta': ST.template_meta(tpl)}


def delete_flow(gid, name_raw):
    name = norm_name(name_raw)
    store = _store(gid)
    if store.pop(name, None) is None:
        return False, err_not_found(name), None
    _save(gid, store)
    return True, '', {'message': f'Шаблон «{name}» удалён.'}


def plan_view(bot, gid, name_raw):
    """diff_plan кога против живого сервера (+ порог «уже совпадает»)."""
    name = norm_name(name_raw)
    entry = _store(gid).get(name)
    if not entry:
        return False, err_not_found(name), None
    guild = bot.get_guild(int(gid)) if bot is not None else None
    if guild is None:
        return False, ERR_OFFLINE_PLAN, None
    plan = ST.diff_plan(entry['template'], guild)
    n_roles, n_cats, n_ch = (len(plan['roles']), len(plan['categories']),
                             len(plan['channels']))
    return True, '', {
        'name': name,
        'plan': plan,
        'counts': {'roles': n_roles, 'categories': n_cats, 'channels': n_ch},
        'nothing': not any(plan.values()),
        'nothing_text': TEXT_NOTHING,
        'template_meta': ST.template_meta(entry['template']),
    }


def apply_flow(bot, gid, name_raw):
    """Применение — последовательность cmd_apply кога 1:1."""
    name = norm_name(name_raw)
    entry = _store(gid).get(name)
    if not entry:
        return False, err_not_found(name), 400, None
    if bot is None:
        return False, ERR_OFFLINE_APPLY, 409, None
    guild = bot.get_guild(int(gid))
    if guild is None:
        return False, ERR_OFFLINE_APPLY, 409, None
    tpl = entry['template']
    plan = ST.diff_plan(tpl, guild)
    if not any(plan.values()):
        return False, TEXT_NOTHING, 400, None

    cog = ST.ServerTemplate(bot)
    made_roles, made_cats, made_chs = 0, 0, 0

    for r in tpl['roles']:
        if r['name'] not in plan['roles']:
            continue
        try:
            _run_async(guild.create_role(
                name=r['name'],
                permissions=discord.Permissions(r['permissions']),
                color=discord.Color(r['color']),
                hoist=r['hoist'], mentionable=r['mentionable'],
                reason=f'Шаблон «{name}»'), timeout=15)
            made_roles += 1
        except Exception as exc:
            _log.debug('templates apply role %s: %s', r['name'], exc)

    cat_map = {}
    existing_cats = {c.name.lower(): c for c in guild.categories}
    for c in tpl['categories']:
        if c['name'].lower() in existing_cats:
            cat_map[c['name']] = existing_cats[c['name'].lower()]
            continue
        try:
            cat_map[c['name']] = _run_async(
                guild.create_category(c['name'], reason=f'Шаблон «{name}»'),
                timeout=15)
            made_cats += 1
        except Exception as exc:
            _log.debug('templates apply category %s: %s', c['name'], exc)

    existing_ch = {c.name.lower() for c in guild.channels}
    for c in tpl['categories']:
        parent = cat_map.get(c['name'])
        for ch in c['channels']:
            if ch['name'].lower() in existing_ch:
                continue
            if _run_async(cog._mk_channel(guild, ch, parent, name), timeout=30):
                made_chs += 1
    for ch in tpl['channels']:
        if ch['name'].lower() in existing_ch:
            continue
        if _run_async(cog._mk_channel(guild, ch, None, name), timeout=30):
            made_chs += 1

    msg = (f'Шаблон «{name}» применён: {made_roles} новых ролей, '
           f'{made_cats} категорий, {made_chs} каналов. Существующие не трогал.')
    return True, '', 200, {
        'message': msg,
        'made': {'roles': made_roles, 'categories': made_cats,
                 'channels': made_chs},
    }


def csv_rows(gid):
    return [(v['name'], v['meta'], v['description'], v['created_at'],
             v['created_by']) for v in list_view(gid)['templates']]


def _csv_cell(text):
    return str(text).replace(';', ',').replace('\r', ' ').replace('\n', ' ')


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    @app.route('/templates')
    @login_required
    @role_required('mod')
    def templates_page():
        return render_template('templates.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id(),
                               can_edit=session.get('role') in ('admin', 'owner'))

    @app.route('/api/guild/<gid>/templates/list')
    @login_required
    @role_required('mod')
    def api_templates_list(gid):
        return jsonify({'success': True, **list_view(gid)})

    @app.route('/api/guild/<gid>/templates/info')
    @login_required
    @role_required('mod')
    def api_templates_info(gid):
        ok, err, view = info_view(gid, request.args.get('name'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 404
        return jsonify({'success': True, 'info': view})

    @app.route('/api/guild/<gid>/templates/save', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_templates_save(gid):
        data = request.get_json(silent=True) or {}
        import web.app as appmod
        ok, err, payload = save_flow(appmod.bot_instance, gid, data.get('name'),
                                     data.get('description'),
                                     f"панель:{session.get('username', '?')}")
        if not ok:
            code = 409 if err == ERR_OFFLINE_SNAP else 400
            return jsonify({'success': False, 'error': err}), code
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/templates/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_templates_delete(gid):
        ok, err, payload = delete_flow(
            gid, (request.get_json(silent=True) or {}).get('name'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 404
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/templates/plan')
    @login_required
    @role_required('mod')
    def api_templates_plan(gid):
        import web.app as appmod
        ok, err, view = plan_view(appmod.bot_instance, gid,
                                  request.args.get('name'))
        if not ok:
            code = 409 if err == ERR_OFFLINE_PLAN else 404
            return jsonify({'success': False, 'error': err}), code
        return jsonify({'success': True, **view})

    @app.route('/api/guild/<gid>/templates/apply', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_templates_apply(gid):
        import web.app as appmod
        ok, err, code, payload = apply_flow(
            appmod.bot_instance, gid,
            (request.get_json(silent=True) or {}).get('name'))
        if not ok:
            return jsonify({'success': False, 'error': err}), code
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/templates/export.json')
    @login_required
    @role_required('mod')
    def api_templates_export_json(gid):
        name = norm_name(request.args.get('name'))
        entry = _store(gid).get(name)
        if not entry:
            return jsonify({'success': False,
                            'error': err_not_found(name)}), 404
        body = json.dumps(entry, ensure_ascii=False, indent=2)
        resp = Response(body, mimetype='application/json; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=template_{name}_{gid}.json')
        return resp

    @app.route('/api/guild/<gid>/templates/export.csv')
    @login_required
    @role_required('mod')
    def api_templates_export_csv(gid):
        body = '\ufeff' + 'name;meta;description;created_at;created_by\n'
        body += '\n'.join(';'.join(_csv_cell(c) for c in row)
                          for row in csv_rows(gid))
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=templates_{gid}.csv')
        return resp
