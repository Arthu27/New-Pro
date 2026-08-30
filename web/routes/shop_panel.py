# -*- coding: utf-8 -*-
"""Менеджер магазина сервера (идея #10): базовые и кастомные предметы экономики.

Панель пишет в то же хранилище GuildData('economy_shop'), что читает ког,
и зовёт РОВНО те же чистые функции: validate_item / upsert_item /
remove_item / effective_items из cogs.economy_shop. Тексты ошибок
одинаковые везде по построению.

Чтение (страница и состояние) — mod+. Запись — admin+, как manage_guild-
команды кога: создать/обновить предмет, удалить предмет.
"""

from flask import has_request_context

from web.routes._common import (
    _log,
    render_template, session, request, jsonify,
)

from cogs import economy_shop as _shop
from cogs.economy_cog import ITEM_DETAILS, RARITY_ORDER

_CARD_KEYS = ("price", "rarity", "desc", "sell", "category", "pet_bonus")


def _categories():
    """Категории = категории базовых предметов + «другое»."""
    cats = {
        str(det.get("category"))
        for det in ITEM_DETAILS.values()
        if isinstance(det, dict) and det.get("category")
    }
    cats.add(_shop.DEFAULT_CATEGORY)
    return sorted(cats)


def shop_payload(gid):
    """Единая картина магазина для панели: и GET, и ответы мутаций."""
    custom = _shop.load_custom(gid)
    items = []
    for name, det in ITEM_DETAILS.items():
        if not isinstance(det, dict):
            continue
        row = {"name": name, "source": "builtin"}
        for key in _CARD_KEYS:
            if det.get(key) is not None:
                row[key] = det.get(key)
        items.append(row)
    for name, det in custom.items():
        row = {"name": name, "source": "custom"}
        for key in _CARD_KEYS + ("by", "created_at", "updated_at"):
            if det.get(key) is not None:
                row[key] = det.get(key)
        items.append(row)
    return {
        "success": True,
        "items": items,
        "builtin_count": len(ITEM_DETAILS),
        "custom_count": len(custom),
        "max_custom": _shop.MAX_CUSTOM_ITEMS,
        "rarities": list(RARITY_ORDER),
        "categories": _categories(),
        "can_edit": has_request_context() and session.get("role") in ("admin", "owner"),
    }


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    @app.route('/shop')
    @login_required
    @role_required('mod')
    def shop_page():
        return render_template('shop.html', role=session.get('role'),
                               username=session.get('username'))

    @app.route('/api/shop/state')
    @login_required
    @role_required('mod')
    def api_shop_state():
        _gid = ctx.active_guild_id_int()
        if _gid is None:
            return jsonify({'success': False, 'error': 'Сервер не выбран (задайте MAIN_GUILD_ID в .env или дождитесь подключения бота)'}), 503
        return jsonify(shop_payload(_gid))

    @app.route('/api/shop/upsert', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_shop_upsert():
        """Создать/обновить кастомный предмет. Валидация — функцией кога."""
        _gid = ctx.active_guild_id_int()
        if _gid is None:
            return jsonify({'success': False, 'error': 'Сервер не выбран (задайте MAIN_GUILD_ID в .env или дождитесь подключения бота)'}), 503
        data = request.get_json(silent=True) or {}
        name = data.get('name')
        card = {k: data.get(k) for k in _CARD_KEYS}
        ok, err = _shop.upsert_item(
            _gid, name, card,
            base=ITEM_DETAILS, rarities=list(RARITY_ORDER),
            categories=_categories(),
            by='panel:%s' % session.get('username'),
        )
        if not ok:
            return jsonify({'success': False, 'error': err}), 400
        body = shop_payload(_gid)
        body['saved'] = (name or '').strip().lower()
        return jsonify(body)

    @app.route('/api/shop/remove', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_shop_remove():
        _gid = ctx.active_guild_id_int()
        if _gid is None:
            return jsonify({'success': False, 'error': 'Сервер не выбран (задайте MAIN_GUILD_ID в .env или дождитесь подключения бота)'}), 503
        data = request.get_json(silent=True) or {}
        ok, err, removed = _shop.remove_item(_gid,
                                             data.get('name'))
        if not ok:
            return jsonify({'success': False, 'error': err}), 404
        body = shop_payload(_gid)
        body['removed'] = removed
        return jsonify(body)
