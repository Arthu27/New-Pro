# -*- coding: utf-8 -*-
"""Лестница наказаний (идеи #156-160): /ladder в браузере.

Конфиг общий с когом: cogs/warnings.load_warn_config <-> LD._save_warn_config
(data/warn_config_<gid>.json, ключ 'steps'). Формат строк — LD._fmt_step,
правила ступеней — как ladder-add (кламп 1..100 / 0..10000, кик без
длительности, ступени уникальны по числу варнов), симуляция — как
ladder-test: активная мера = последняя пройденная ступень, следующая —
первая непройденная, «осталось N». Варны читаются из того же зеркала
data/warnings.json, что смотрит мод-контроль.

Карточка — services/ladder_card.render_ladder_card (Pillow, офлайн).
«Вес ступеней» — панельная сводка: сколько участников сейчас стоит на
каждой ступени и выше (из того же зеркала варнов).

Чтение — mod+; ступени меняет admin+ (командам нужен manage_guild).
"""
from web.routes._common import (
    _log,
    render_template, session, request, jsonify, Response,
)
from web.routes.mod_control import validate_user_id, load_warns_map

from cogs import ladder as LD
from cogs.warnings import load_warn_config

ACTIONS = ('mute', 'kick', 'ban')
UNITS = ('minute', 'hour', 'day')
ERR_ACTION = 'Действие: мут / кик / бан'
ERR_COUNT = 'Количество варнов — целое число'


def load_cfg(gid):
    """Конфиг кога как есть (с его дефолтом {'steps': []})."""
    return load_warn_config(gid)


def _save(gid, cfg):
    LD._save_warn_config(int(gid), cfg)


def steps_of(cfg):
    """Ступени отсортированные, с подписью его _fmt_step."""
    steps = LD._steps(cfg)
    out = []
    for st in sorted(steps, key=lambda s: int(s.get('count', 0))):
        out.append({'count': int(st.get('count', 0)),
                    'action': st.get('action', 'mute'),
                    'duration': int(st.get('duration', 0) or 0),
                    'unit': st.get('unit', 'minute'),
                    'label': LD._fmt_step(st)})
    return out


def add_flow(gid, count_raw, action, duration_raw, unit):
    """ladder-add 1:1: клампы молчаливые, кик — без длительности, дедуп."""
    try:
        count = int(count_raw)
    except (TypeError, ValueError):
        return False, ERR_COUNT, None
    action = str(action or 'mute')
    if action not in ACTIONS:
        return False, ERR_ACTION, None
    unit = str(unit or 'minute')
    if unit not in UNITS:
        unit = 'minute'
    count = max(1, min(count, 100))
    if duration_raw is None:
        duration = 10  # дефолт параметра команды ladder-add
    else:
        try:
            duration = int(duration_raw)
        except (TypeError, ValueError):
            duration = 0
    duration = max(0, min(duration, 10000))
    if action == 'kick':
        duration = 0
    cfg = load_cfg(gid)
    steps = [s for s in LD._steps(cfg) if int(s.get('count', 0)) != count]
    steps.append({'count': count, 'action': action,
                  'duration': duration, 'unit': unit})
    cfg['steps'] = steps
    _save(gid, cfg)
    label = LD._fmt_step({'count': count, 'action': action,
                          'duration': duration, 'unit': unit})
    msg = (f'Ступень сохранена: {count} варнов → {label}. '
           f'Всего ступеней: {len(steps)}.')
    return True, '', {'message': msg, 'steps': steps_of(cfg)}


def remove_flow(gid, count_raw):
    try:
        count = int(count_raw)
    except (TypeError, ValueError):
        return False, ERR_COUNT, None
    cfg = load_cfg(gid)
    steps = LD._steps(cfg)
    new = [s for s in steps if int(s.get('count', 0)) != count]
    if len(new) == len(steps):
        return False, f'Ступени на {count} варнов нет.', None
    cfg['steps'] = new
    _save(gid, cfg)
    return True, '', {'message': f'Ступень на {count} варнов убрана. '
                                 f'Осталось: {len(new)}.',
                      'steps': steps_of(cfg)}


def simulate_view(gid, uid_raw):
    """ladder-test 1:1: активная мера и следующая ступень по текущим варнам."""
    ok, err, uid = validate_user_id(uid_raw)
    if not ok:
        return False, err, None
    total = len(load_warns_map(gid).get(str(uid), []))
    steps = steps_of(load_cfg(gid))
    matched = None
    for st in steps:
        if total >= st['count']:
            matched = st
    nxt = next((s for s in steps if total < s['count']), None)
    lines = [f'Сейчас предупреждений: {total}']
    if matched:
        lines.append(f"Активная мера: {matched['label']}")
    else:
        lines.append('Активной меры нет — участник ниже первой ступени.')
    if nxt:
        lines.append(f"Следующая ступень: {nxt['count']} варнов → "
                     f"{nxt['label']} (осталось {nxt['count'] - total})")
    return True, '', {'total': total, 'matched': matched, 'next': nxt,
                      'lines': lines}


def impact_view(gid):
    """«Вес ступеней»: сколько участников сейчас на каждой ступени и выше."""
    warns = load_warns_map(gid)
    steps = steps_of(load_cfg(gid))
    out = []
    for st in steps:
        out.append({'count': st['count'], 'label': st['label'],
                    'users': sum(1 for w in warns.values()
                                 if len(w) >= st['count'])})
    return {'steps': out, 'warned_users': sum(1 for w in warns.values() if w)}


def csv_rows(gid):
    impact = {s['count']: s['users'] for s in impact_view(gid)['steps']}
    return [(s['count'], s['action'], s['duration'], s['unit'], s['label'],
             impact.get(s['count'], 0))
            for s in steps_of(load_cfg(gid))]


def _csv_cell(text):
    return str(text).replace(';', ',').replace('\r', ' ').replace('\n', ' ')


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    @app.route('/ladder')
    @login_required
    @role_required('mod')
    def ladder_page():
        return render_template('ladder.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id(),
                               can_edit=session.get('role') in ('admin', 'owner'))

    @app.route('/api/guild/<gid>/ladder/view')
    @login_required
    @role_required('mod')
    def api_ladder_view(gid):
        from services import freshness as FSH
        return jsonify({'success': True,
                        'steps': steps_of(load_cfg(gid)),
                        'impact': impact_view(gid),
                        'cooldown': FSH.cooldown_config(gid),
                        'can_edit': session.get('role') in ('admin', 'owner')})

    @app.route('/api/guild/<gid>/ladder/cooldown', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_ladder_cooldown(gid):
        """Пороги авто-остывания статуса нарушителя (services/freshness)."""
        from services import freshness as FSH
        data = request.get_json(silent=True) or {}
        cfg, err = FSH.save_cooldown_config(
            gid, data.get('warm_days'), data.get('cold_days'))
        if err:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, 'cooldown': cfg,
                        'message': 'Пороги остывания сохранены'})

    @app.route('/api/guild/<gid>/ladder/card.png')
    @login_required
    @role_required('mod')
    def api_ladder_card(gid):
        import web.app as appmod
        guild = (appmod.bot_instance.get_guild(int(gid))
                 if appmod.bot_instance else None)
        name = getattr(guild, 'name', '') or ''
        steps = steps_of(load_cfg(gid))
        try:
            from services.ladder_card import render_ladder_card
            png = render_ladder_card(steps, guild_name=name)
        except Exception as exc:
            _log.debug('ladder card: %s', exc)
            png = None
        if png is None:
            return jsonify({'success': False,
                            'error': 'Карточка не отрисовалась'}), 500
        resp = Response(png, mimetype='image/png')
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    @app.route('/api/guild/<gid>/ladder/simulate')
    @login_required
    @role_required('mod')
    def api_ladder_simulate(gid):
        ok, err, view = simulate_view(gid, request.args.get('user'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **view})

    @app.route('/api/guild/<gid>/ladder/add', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_ladder_add(gid):
        data = request.get_json(silent=True) or {}
        ok, err, payload = add_flow(gid, data.get('count'), data.get('action'),
                                    data.get('duration'), data.get('unit'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/ladder/remove', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_ladder_remove(gid):
        ok, err, payload = remove_flow(
            gid, (request.get_json(silent=True) or {}).get('count'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, **payload})

    @app.route('/api/guild/<gid>/ladder/export.csv')
    @login_required
    @role_required('mod')
    def api_ladder_export(gid):
        body = '\ufeff' + 'count;action;duration;unit;label;users_at_or_above\n'
        body += '\n'.join(';'.join(_csv_cell(c) for c in row)
                          for row in csv_rows(gid))
        resp = Response(body, mimetype='text/csv; charset=utf-8')
        resp.headers['Content-Disposition'] = (
            f'attachment; filename=ladder_{gid}.csv')
        return resp
