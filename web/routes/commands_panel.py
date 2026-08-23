# -*- coding: utf-8 -*-
"""Каталог всех команд бота для панели («Бот → Команды»).

Отдаёт полный реестр из services/command_registry: каждая команда с
русским описанием, типом (SLASH/PREFIX), слеш-группой, модулем и
категорией с иконкой. Каталог кэшируется сервисом по mtime cogs/.

Чтение — mod+ (команды бота не секрет), выполнение — как раньше, через
/api/execute-command (admin+) на собственной странице формы.
"""
from web.routes._common import (
    _log, request, jsonify,
)

from services import command_registry as CR


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/api/commands/catalog')
    @login_required
    @role_required('mod')
    def api_commands_catalog():
        """Полный каталог команд панели: счётчики, категории, команды."""
        q = str(request.args.get('q') or '').strip().lower()
        kind = str(request.args.get('kind') or '').strip().lower()
        cat = str(request.args.get('cat') or '').strip().lower()
        try:
            data = CR.catalog()
        except Exception as _ex:
            _log.debug('commands catalog: %s', _ex)
            return jsonify({'success': False,
                            'error': 'Не удалось собрать каталог команд'}), 500

        items = data['commands']
        if q:
            items = [c for c in items
                     if q in c['name'] or q in c['desc'].lower()
                     or any(q in a.lower() for a in c['aliases'])]
        if kind in ('slash', 'prefix'):
            items = [c for c in items if
                     (c['kind'] == kind or (kind == 'slash' and c['kind'] == 'sub'))]
        if cat:
            items = [c for c in items if c['cat'] == cat]
        return jsonify({
            'success': True,
            'total': data['total'],
            'slash': data['slash'] + data['subs'],
            'prefix': data['prefix'],
            'modules': data.get('modules'),
            'categories': data['categories'],
            'shown': len(items),
            'commands': items,
        })
