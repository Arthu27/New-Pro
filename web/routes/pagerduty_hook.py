# -*- coding: utf-8 -*-
"""Мост PagerDuty → Discord: публичный хук + страница настройки.

PagerDuty не умеет Discord-формат вебхуков — панель принимает его события
сама и постит красивую карточку в канал тревог от бота:

- ``POST /hooks/pagerduty/<gid>/<token>`` — публичная точка (токен = секрет).
  200 — событие принято (даже если канал не выбран — не заставляем PD
  ретраить); 503 — бот офлайн (PD повторит позже); 403 — токен/тумблер.
- ``/pagerduty`` — страница: URL хука с кнопкой «копировать», канал
  тревог, тумблер, регенерация токена, кнопка «тестовая тревога».

Доступ: страница — админ (внешняя интеграция касается всего сервера).
"""
from datetime import datetime, timezone

import discord

from web.routes._common import (
    _safe_json_obj,
    _log, _run_async, _fire_panel_notification,
    render_template, session, request, jsonify,
)

from services import pagerduty_hook as PD
from services.channel_routes import get_route, set_route


def _gid(ctx):
    try:
        return int(ctx.active_guild_id() or 0)
    except (TypeError, ValueError):
        return 0


def _bot():
    try:
        import web.app as _app
        return _app.bot_instance
    except Exception:
        return None


def _bot_truth(bot):
    """Правда о боте: (online, status, presence).

    Раньше «онлайн» означало «объект бота существует» — панель уверяла,
    что всё работает, когда шлюз Discord давно отвалился (жалоба
    30.08.2026: «данные отправляет, но он офлайн»). Теперь:
    online  — шлюз жив и бот готов (is_ready и не is_closed);
    starting — подключается (объект есть, готовности ещё нет);
    offline — объекта нет или шлюз закрыт.
    """
    if bot is None:
        return False, 'offline', 'offline'
    try:
        if bot.is_closed():
            return False, 'offline', str(getattr(bot, 'status', 'offline') or 'offline')
    except AttributeError:
        _log.debug('pagerduty: стаб без is_closed — считаем живым')
    except Exception:
        return False, 'offline', 'offline'
    try:
        if not bot.is_ready():
            return False, 'starting', 'offline'
    except AttributeError:
        _log.debug('pagerduty: стаб без is_ready — считаем готовым')
    except Exception:
        return False, 'starting', 'offline'
    return True, 'online', str(getattr(bot, 'status', 'online') or 'online')


def _target_channel(bot, gid):
    """Куда постить тревоги: маршрут pagerduty_channel."""
    cid = int(get_route(gid, 'pagerduty_channel') or 0)
    if not cid or bot is None:
        return None
    guild = bot.get_guild(int(gid))
    if guild is None:
        return None
    return guild.get_channel(cid)


def build_embed(info, guild=None):
    """Данные format_incident → Embed-карточка."""
    color = int(info.get('color') or 0x95A5A6)
    body = f"**{info['incident_title']}**\nИнцидент {info['status_line']}."
    if info.get('url'):
        body += f"\n[Открыть в PagerDuty]({info['url']})"
    embed = discord.Embed(
        title=info['title'],
        description=body,
        color=color,
        timestamp=datetime.now(timezone.utc))
    if info.get('service'):
        embed.add_field(name='Сервис', value=info['service'], inline=True)
    if info.get('assignee'):
        embed.add_field(name='Дежурный', value=info['assignee'], inline=True)
    if info.get('urgency'):
        embed.add_field(
            name='Срочность',
            value='высокая' if info['urgency'] == 'high'
                  else ('средняя' if info['urgency'] == 'low' else info['urgency']),
            inline=True)
    if info.get('occurred_at'):
        embed.add_field(name='Время', value=info['occurred_at'], inline=False)
    footer = f"PagerDuty · {info['event']}"
    if guild is not None:
        footer += f" · {getattr(guild, 'name', '')}"
    embed.set_footer(text=footer)
    return embed


def deliver(info, bot, gid):
    """Отправить карточку в канал тревог. → (status, message).

    status: 'sent' | 'no_channel' | 'offline' | 'error'
    """
    channel = _target_channel(bot, gid)
    if channel is None:
        if bot is None or bot.get_guild(int(gid)) is None:
            PD.log_delivery(gid, info, 'offline', 'бот офлайн — PagerDuty повторит')
            return 'offline', 'Бот офлайн — повторите позже'
        PD.log_delivery(gid, info, 'no_channel', 'канал тревог не выбран')
        return 'no_channel', 'Канал тревог не выбран (Панель → PagerDuty)'
    embed = build_embed(info, guild=channel.guild)
    try:
        _run_async(channel.send(embed=embed))
    except Exception as _ex:
        _log.warning('pagerduty: доставка в %s: %s', gid, _ex)
        PD.log_delivery(gid, info, 'error', str(_ex)[:120])
        return 'error', f'Не удалось отправить: {_ex}'
    PD.log_delivery(gid, info, 'sent', getattr(channel, 'name', ''))
    return 'sent', 'Карточка отправлена'


TEST_PAYLOAD = {
    'event_type': 'incident.triggered',
    'occurred_at': datetime.now(timezone.utc).isoformat(),
    'incident': {
        'incident_number': 42,
        'title': 'Тестовая тревога — проверка моста PagerDuty',
        'html_url': 'https://hakumo.panel/pagerduty',
        'urgency': 'high',
        'service': {'summary': 'Hakumo Panel'},
        'assignments': [{'assignee': {'summary': 'Владелец панели'}}],
    },
}


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required

    # ── публичная точка: PagerDuty → сюда (без входа в панель) ──
    @app.route('/hooks/pagerduty/<gid>/<token>', methods=['POST'])
    def hook_pagerduty(gid, token):
        if not str(gid).isdigit():
            return jsonify({'success': False, 'error': 'плохой gid'}), 400
        gid = int(gid)
        if not PD.check_token(gid, token):
            _log.debug('pagerduty: отказ токена для %s', gid)
            return jsonify({'success': False, 'error': 'нет доступа'}), 403
        payload = request.get_json(silent=True)
        if payload is None:
            # PagerDuty всегда шлёт JSON; пустое тело терять не будем
            payload = {}
        info = PD.format_incident(payload)
        status, message = deliver(info, _bot(), gid)
        if status == 'offline':
            # 503 — PagerDuty повторит запрос, когда бот вернётся
            return jsonify({'success': False, 'error': message}), 503
        if status == 'no_channel':
            # канал не выбран: не ретраим (настройка, а не сбой)
            _log.warning('pagerduty: %s канал не выбран, событие %s потеряно',
                         gid, info['event'])
            return jsonify({'success': False, 'error': message}), 200
        if status == 'error':
            return jsonify({'success': False, 'error': message}), 503
        return jsonify({'success': True, 'event': info['event']}), 200

    # ── страница ──
    @app.route('/pagerduty')
    @login_required
    @role_required('admin')
    def pagerduty_page():
        return render_template('pagerduty.html',
                               role=session.get('role'),
                               username=session.get('username'),
                               guild_id=_gid(ctx))

    # ── API настроек ──
    @app.route('/api/guild/<gid>/pagerduty', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def api_pagerduty(gid):
        gid = _gid(ctx) or (int(gid) if str(gid).isdigit() else 0)
        if request.method == 'GET':
            st = PD.get_settings(gid)
            channels = []
            bot = _bot()
            online, bot_status, presence = _bot_truth(bot)
            if bot is not None:
                g = bot.get_guild(int(gid))
                if g is not None:
                    channels = sorted(
                        ({'id': str(c.id), 'name': c.name}
                         for c in getattr(g, 'text_channels', ())),
                        key=lambda x: x['name'].lstrip('#').lower())
            elif bot is None:
                # Панель отдельным процессом от бота: страница показывает
                # правду по пульсу бота, каналы — из снимка моста.
                try:
                    from services import bot_bridge as _bb
                    _st = _bb.read_state()
                    _s = _bb.state_status(_st)
                    if _s in ('online', 'starting'):
                        online, bot_status = _s == 'online', _s
                        presence = 'online' if _s == 'online' else 'offline'
                    if _bb.bot_alive_for(gid):
                        channels = sorted(
                            ({'id': c['id'], 'name': c['name']}
                             for c in (_bb.read_channels(gid) or [])
                             if c.get('type') == 'text'),
                            key=lambda x: x['name'].lstrip('#').lower())
                except Exception as _pex:
                    _log.debug('pagerduty: remote bridge: %s', _pex)
            return jsonify({
                'success': True,
                'enabled': st['enabled'],
                'token': st['token'],
                'hook_path': f'/hooks/pagerduty/{gid}/{st["token"]}',
                'channel_id': int(get_route(gid, 'pagerduty_channel') or 0),
                'bot_online': online,          # правда о шлюзе, не «объект есть»
                'bot_status': bot_status,      # online | starting | offline
                'bot_presence': presence,      # чем бот выглядит в Discord
                'channels': channels,
                'history': PD.recent(gid, 15),
                'history_stats': PD.history_stats(gid),
            })

        data = _safe_json_obj()
        who = session.get('username', '?')
        if 'channel_id' in data:
            try:
                cid = int(data.get('channel_id') or 0)
            except (TypeError, ValueError):
                cid = 0
            set_route(gid, 'pagerduty_channel', cid)
            _fire_panel_notification(
                'pagerduty', 'Канал тревог PagerDuty',
                f'{who}: ' + (f'#{cid}' if cid else 'не выбран'))
        if 'enabled' in data:
            PD.set_enabled(gid, bool(data.get('enabled')))
            _fire_panel_notification(
                'pagerduty', 'Мост PagerDuty',
                f'{who}: ' + ('включён' if data.get('enabled') else 'выключен'))
        new_token = None
        if data.get('regen'):
            new_token = PD.regen_token(gid)
            _fire_panel_notification(
                'pagerduty', 'Токен PagerDuty перегенерирован',
                f'{who}: старый URL больше не работает')
        st = PD.get_settings(gid)
        return jsonify({
            'success': True,
            'enabled': st['enabled'],
            'token': st['token'],
            'hook_path': f'/hooks/pagerduty/{gid}/{st["token"]}',
            'channel_id': int(get_route(gid, 'pagerduty_channel') or 0),
            'regenerated': new_token is not None,
        })

    @app.route('/api/guild/<gid>/pagerduty/test', methods=['POST'])
    @login_required
    @role_required('admin')
    def api_pagerduty_test(gid):
        gid = _gid(ctx) or (int(gid) if str(gid).isdigit() else 0)
        status, message = deliver(PD.format_incident(TEST_PAYLOAD),
                                  _bot(), gid)
        ok = status == 'sent'
        if ok:
            _fire_panel_notification(
                'pagerduty', 'Тестовая тревога отправлена',
                f"{session.get('username', '?')} → канал #{get_route(gid, 'pagerduty_channel')}")
        return jsonify({'success': ok,
                        'message' if ok else 'error': message}), 200
