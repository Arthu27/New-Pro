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

import importlib

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
            'disabled': data.get('disabled', 0),
            'shown': len(items),
            'commands': items,
        })


    @app.route('/api/commands/switch-bulk', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_commands_switch_bulk():
        """Вкл/выкл сразу список команд (кнопки «Вкл показанные / Выкл показанные»
        и «включить категорию целиком» — вместо кликов по одному)."""
        from services import command_switches as CSW
        data = request.get_json(silent=True) or {}
        names = [str(n).strip() for n in (data.get('names') or [])
                 if str(n).strip()][:500]
        off = bool(data.get('disabled'))
        if not names:
            return jsonify({'success': False,
                            'error': 'Список команд пуст'}), 400
        disabled = CSW.set_disabled_bulk(names, off)
        bot = getattr(importlib.import_module('web.app'), 'bot_instance', None)
        scheduled = False
        if bot is not None and getattr(bot, 'loop', None):
            import asyncio
            try:
                asyncio.run_coroutine_threadsafe(CSW.resync(bot), bot.loop)
                scheduled = True
            except RuntimeError as _ex:
                _log.debug('switch-bulk resync schedule: %s', _ex)
        return jsonify({'success': True, 'count': len(names), 'disabled': off,
                        'disabled_list': sorted(disabled),
                        'bot_online': bot is not None,
                        'resync_scheduled': scheduled})


    @app.route('/api/commands/switches', methods=['GET'])
    @login_required
    @role_required('mod')
    def api_commands_switches():
        """Какие команды выключены владельцем (для тумблеров на карточках)."""
        from services import command_switches as CSW
        return jsonify({'success': True,
                        'disabled': sorted(CSW.disabled_set())})

    @app.route('/api/commands/switch', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_commands_switch():
        """Вкл/выкл команду. Бот онлайн — команда мгновенно исчезает
        из slash-меню Discord (пересинк в фоне) и перестаёт отвечать."""
        from services import command_switches as CSW
        data = request.get_json(silent=True) or {}
        name = str(data.get('name') or '').strip()
        off = bool(data.get('disabled'))
        if not name:
            return jsonify({'success': False,
                            'error': 'Не указана команда'}), 400
        disabled = CSW.set_disabled(name, off)
        bot = getattr(importlib.import_module('web.app'), 'bot_instance', None)
        scheduled = False
        if bot is not None and getattr(bot, 'loop', None):
            import asyncio
            try:
                asyncio.run_coroutine_threadsafe(CSW.resync(bot), bot.loop)
                scheduled = True
            except RuntimeError as _ex:
                _log.debug('switch resync schedule: %s', _ex)
        return jsonify({'success': True, 'name': name, 'disabled': off,
                        'disabled_list': sorted(disabled),
                        'bot_online': bot is not None,
                        'resync_scheduled': scheduled})
