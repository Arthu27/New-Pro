# -*- coding: utf-8 -*-
"""Экономика — обзор (вырезано из routes_extra.py — нарезка аудита, поведение 1:1)."""

from web.routes._common import (
    _run_async, _fetch_channel_msgs_async, _fetch_channel_msgs_sync,
    _load_ai_tickets, _notify_discord_sender, _fire_panel_notification,
    _process_action, _log,
    ms_normalize_query, ms_member_match, ms_search_members, ms_member_payload,
    ms_normalize_warn, ms_normalize_case, calculate_ai_ticket_stats, _REPO_ROOT,
    render_template, session, redirect, url_for, request, jsonify, Response,
    os, json, time, math, discord, datetime, timezone,
)

def register(ctx):
    app = ctx.app
    ROLES = ctx.ROLES
    login_required = ctx.login_required
    role_required = ctx.role_required
    MAIN_GUILD_ID = ctx.MAIN_GUILD_ID
    active_guild_id = ctx.active_guild_id
    _resolve_member_async = ctx._resolve_member_async


    # ── ECONOMY: живой обзор (страница /economy) ───────────────
    @app.route('/api/economy/overview')
    @login_required
    @role_required('admin')
    def api_economy_overview():
        import web.app as _app
        from db import UserData
        from cogs.economy_cog import ITEM_DETAILS
        try:
            all_users = UserData('economy').get_all() or {}
        except Exception:
            all_users = {}
        bot = _app.bot_instance

        def _name(uid):
            try:
                u = bot.get_user(int(uid)) if bot else None
                return getattr(u, 'display_name', None) or getattr(u, 'name', None)
            except Exception:
                return None

        rows = []
        for uid, d in all_users.items():
            if not isinstance(d, dict):
                continue
            bal = int(d.get('balance', 0) or 0)
            bank = int(d.get('bank', 0) or 0)
            rows.append({'id': str(uid), 'name': _name(uid) or f'ID {uid}',
                         'balance': bal, 'bank': bank,
                         'vault': int(d.get('vault', 0) or 0), 'total': bal + bank})
        lb = sorted(rows, key=lambda r: -r['total'])
        richest = sorted(rows, key=lambda r: -r['bank'])
        catalog = [{'name': name,
                    'price': int(v.get('price', 0)), 'rarity': v.get('rarity', ''),
                    'category': v.get('category', ''), 'desc': v.get('desc', ''),
                    'pet_bonus': v.get('pet_bonus', 0)}
                   for name, v in ITEM_DETAILS.items()]
        catalog.sort(key=lambda x: x['price'])
        return jsonify({'ok': True, 'users': len(rows),
                        'in_circulation': sum(r['total'] for r in rows),
                        'gems_total': sum(r['vault'] for r in rows),
                        'leaderboard': lb[:20], 'richest': richest[:10],
                        'catalog': catalog})
