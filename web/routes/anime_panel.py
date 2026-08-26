# -*- coding: utf-8 -*-
"""Панель «Аниме дня» (идеи #66-70): статус ежедневной рассылки, настройки,
обратный отсчёт, превью карточки, диагностика «почему молчит».

Хранилище — файл кога cogs/anime_daily.py (читаем и пишем его же
_load/_save, чтобы кеш json_store не расходился с ботом):
    data/anime_daily_config.json
    {gid: {'enabled': bool, 'channel_id': int|None, 'tur_id': int|None,
           'tur_adi': str, 'role_id': int|None}}
Набор ключей и типы — ровно как пишет /anime-setup. Расписание одно на
всех (10:00 локального времени, логика before_loop) — отсюда честный
обратный отсчёт.

Чтение и превью — mod+, настройки — admin+.
"""
import os
from datetime import datetime, timedelta
from types import SimpleNamespace

from web.routes._common import (
    _log,
    render_template, session, request, jsonify,
)

from cogs import anime_daily as AD

KATEGORILER = AD.KATEGORILER          # категории — единый словарь кога
RANDOM_LABEL = 'Случайно'

SAMPLE_ANIME = {
    'title_english': 'Cowboy Bebop',
    'title': 'Cowboy Bebop',
    'score': 8.75,
    'episodes': 26,
    'url': 'https://myanimelist.net/anime/1/Cowboy_Bebop',
    'images': {'jpg': {'large_image_url':
                       'https://cdn.myanimelist.net/images/anime/4/19644.jpg'}},
    'synopsis': (
        'In the year 2071, humanity has colonized several of the planets and '
        'moons of the solar system leaving the now uninhabitable surface of '
        'planet Earth behind. The Inter Solar System Police attempts to keep '
        'peace in the galaxy, aided in part by outlaw bounty hunters, referred '
        'to as "Cowboys". The ragtag team aboard the spaceship Bebop are two '
        'such individuals. Mellow and carefree Spike Spiegel is balanced by '
        'his boisterous, pragmatic partner Jet Black as the pair makes a '
        'living chasing bounties and collecting rewards.'),
}


def public_config(data, gid):
    """Вид записи гильдии для панели; пустая запись — честные дефолты."""
    rec = (data or {}).get(str(gid))
    if not isinstance(rec, dict):
        rec = {}
    return {
        'configured': bool(rec),
        'enabled': bool(rec.get('enabled')),
        'channel_id': rec.get('channel_id'),
        'role_id': rec.get('role_id'),
        'tur_id': rec.get('tur_id'),
        'category': str(rec.get('tur_adi') or RANDOM_LABEL),
    }


def next_run(now=None):
    """Когда ког пошлёт следующее предложение: 10:00 локального времени,
    минувшее сегодня — завтра (before_loop кога 1:1)."""
    now = now or datetime.now()
    target = now.replace(hour=10, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return target


def readiness(cfg, channel_state, role_state):
    """Диагностика «почему молчит». channel_state/role_state:
    True — нашёлся у бота, False — потерян, None — бот офлайн, не проверить.
    """
    issues = []
    if not cfg['configured']:
        issues.append('настройки не заданы (команда /anime-setup или форма ниже)')
    if not cfg['enabled']:
        issues.append('рассылка выключена')
    if not cfg['channel_id']:
        issues.append('канал не задан')
    if channel_state is False:
        issues.append('канал не найден у бота — задайте заново')
    if role_state is False:
        issues.append('роль не найдена у бота — задайте заново')
    ready = (cfg['enabled'] and bool(cfg['channel_id'])
             and channel_state is not False)
    return {'ready': ready, 'issues': issues}


def normalize_settings(current, payload):
    """Частичные правки -> запись формата /anime-setup (все пять ключей).
    -> (record | None, err)
    """
    current = current if isinstance(current, dict) else {}
    new = {
        'enabled': bool(current.get('enabled')),
        'channel_id': current.get('channel_id'),
        'tur_id': current.get('tur_id'),
        'tur_adi': str(current.get('tur_adi') or RANDOM_LABEL),
        'role_id': current.get('role_id'),
    }
    if 'enabled' in payload:
        enabled = payload.get('enabled')
        if not isinstance(enabled, bool):
            return None, 'Включение — true или false'
        new['enabled'] = enabled
    if 'channel_id' in payload:
        value = str(payload.get('channel_id') or '').strip()
        if value and not value.isdigit():
            return None, 'ID канала — только цифры'
        new['channel_id'] = int(value) if value else None
    if 'category' in payload:
        category = str(payload.get('category') or '').strip()
        if category != RANDOM_LABEL and category not in KATEGORILER:
            return None, 'Категория — из списка'
        new['tur_id'] = None if category == RANDOM_LABEL else KATEGORILER[category]
        new['tur_adi'] = category
    if 'role_id' in payload:
        value = str(payload.get('role_id') or '').strip()
        if value and not value.isdigit():
            return None, 'ID роли — только цифры'
        new['role_id'] = int(value) if value else None
    if new['enabled'] and not new['channel_id']:
        return None, 'Без канала включать нельзя'
    return new, ''


def preview_embed(guild_name, category):
    """Превью карточки настоящим _embed_build кога на эталонных данных —
    текст, поля и обрезка сводки ровно такие, как уйдут в Discord."""
    fake_guild = SimpleNamespace(name=guild_name, icon=None)
    embed, summary = AD._embed_build(fake_guild, dict(SAMPLE_ANIME), category)
    return {
        'title': embed.title,
        'url': embed.url,
        'description': embed.description,
        'fields': [{'name': f.name, 'value': str(f.value)}
                   for f in embed.fields],
        'footer': embed.footer.text if embed.footer else '',
        'has_translate_button': True,
        'summary_full_len': len(summary),
        'sample': True,
    }


def _resolve_states(bot, gid, cfg):
    """(channel_state, role_state, guild_name, bot_online) через живого бота."""
    if not bot:
        return None, None, 'Hakumo', False
    try:
        guild = bot.get_guild(int(gid))
    except Exception as _ex:
        _log.debug('anime: get_guild(%s): %s', gid, _ex)
        return None, None, 'Hakumo', False
    if guild is None:
        return None, None, 'Hakumo', True
    channel_state = None
    if cfg['channel_id']:
        try:
            channel_state = guild.get_channel(int(cfg['channel_id'])) is not None
        except Exception as _ex:
            _log.debug('anime: get_channel: %s', _ex)
    role_state = None
    if cfg['role_id']:
        try:
            role_state = guild.get_role(int(cfg['role_id'])) is not None
        except Exception as _ex:
            _log.debug('anime: get_role: %s', _ex)
    return channel_state, role_state, str(getattr(guild, 'name', '') or 'Hakumo'), True


# ─────────────────────────────────────────────────────────────────────
# Маршруты
# ─────────────────────────────────────────────────────────────────────
def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _notify(title):
        from web.routes._common import _fire_panel_notification
        try:
            _fire_panel_notification(
                'anime_daily', title,
                f'Через панель ({session.get("username", "?")})')
        except Exception as _ex:
            _log.debug('anime: уведомление не ушло: %s', _ex)

    @app.route('/anime-daily')
    @login_required
    @role_required('mod')
    def anime_page():
        return render_template('anime_daily.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/anime-daily/overview')
    @login_required
    @role_required('mod')
    def api_anime_overview(gid):
        import web.app as appmod
        cfg = public_config(AD._load(), gid)
        channel_state, role_state, guild_name, bot_online = _resolve_states(
            appmod.bot_instance, gid, cfg)
        target = next_run()
        now = datetime.now()
        return jsonify({
            'success': True,
            'config': cfg,
            'categories': [RANDOM_LABEL] + list(KATEGORILER),
            'next': {'at': target.isoformat(timespec='minutes'),
                     'in_seconds': max(0, int((target - now).total_seconds()))},
            'readiness': readiness(cfg, channel_state, role_state),
            'bot_online': bot_online,
            'preview': preview_embed(guild_name, cfg['category']),
            'can_edit': session.get('role') in ('admin', 'owner'),
        })

    @app.route('/api/guild/<gid>/anime-daily/settings', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_anime_settings(gid):
        data = request.get_json(silent=True) or {}
        cfg = AD._load()
        record, err = normalize_settings(cfg.get(str(gid)), data)
        if record is None:
            return jsonify({'success': False, 'error': err}), 400
        cfg[str(gid)] = record
        os.makedirs('data', exist_ok=True)
        AD._save(cfg)
        _notify('Аниме дня: настройки обновлены '
                f'(включено — {record["enabled"]}, категория «{record["tur_adi"]}»)')
        return jsonify({'success': True,
                        'config': public_config({str(gid): record}, gid)})
