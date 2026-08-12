# -*- coding: utf-8 -*-
"""Диспетчер уведомлений панели Aether.

Доставляет события (тикеты и др.) по каналам из data/notification_settings.json:

  • web     — broadcast-запись в data/panel_logs.json; её подхватывает опрос
              /api/notifications/poll → бейдж и тост у всего онлайн-персонала;
  • discord — Discord-webhook (если задан webhook_url). Отправку в обычный
              канал сервера выполняет вызывающая сторона через discord_sender;
  • email   — письмо через SMTP (с таймаутом, ошибки не роняют вызов).

Каждое событие также записывается в data/notification_history.json
со статусами доставки по каналам (её показывает страница «Уведомления»).

Модуль не зависит от Flask и discord.py — может вызываться и из панели,
и из когов бота (в фоне, через executor).
"""

from logger import get_logger

_log = get_logger("notification_dispatcher")

import json
import os
import smtplib
import threading
import time
from datetime import datetime, timezone
from email.header import Header
from email.mime.text import MIMEText

SETTINGS_FILE = 'data/notification_settings.json'
HISTORY_FILE = 'data/notification_history.json'
PANEL_LOGS_FILE = 'data/panel_logs.json'

# event_key -> (ключ настройки-переключателя, подпись по-русски, иконка)
EVENTS = {
    'ticket_open': ('event_ticket_open', 'Новый тикет открыт', '🎫'),
    'ticket_message': ('event_ticket_message', 'Новое сообщение в тикете', '💬'),
    'ticket_close': ('event_ticket_close', 'Тикет закрыт', '🔒'),
    'priority_change': ('event_priority_change', 'Изменение приоритета', '⚡'),
    'assignment': ('event_assignment', 'Назначение тикета', '👤'),
    'warn': ('event_warn', 'Выдано предупреждение', '⚠️'),
    'mod_action': ('event_mod_action', 'Действие модерации', '🔨'),
    'staff_apply': ('event_staff_apply', 'Новая заявка в персонал', '📝'),
    'test': (None, 'Тестовое уведомление', '🧪'),
}

# event_key -> страница панели, куда ведёт клик по уведомлению
EVENT_LINKS = {
    'ticket_open': '/ticket-search',
    'ticket_message': '/ticket-search',
    'ticket_close': '/ticket-search',
    'priority_change': '/ticket-search',
    'assignment': '/ticket-search',
    'warn': '/warnings',
    'mod_action': '/logs',
    'staff_apply': '/staff-apps',
    'test': '/notifications',
}

DEFAULT_SETTINGS = {
    'web_enabled': True,
    'discord_enabled': True,
    'email_enabled': False,
    'event_ticket_open': True,
    'event_ticket_message': True,
    'event_ticket_close': True,
    'event_priority_change': False,
    'event_assignment': False,
    'event_warn': True,
    'event_mod_action': True,
    'event_staff_apply': True,
    'discord_channel': '',
    'webhook_url': '',
    'smtp_server': '',
    'smtp_port': 587,
    'smtp_email': '',
    'smtp_password': '',
}

_history_lock = threading.Lock()


def load_settings():
    """Загрузить настройки уведомлений (с дефолтами)."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                settings.update(data)
    except Exception as _ex:
        _log.debug("load_settings(): подавлено: %s", _ex)
    return settings


def _append_json_list(path, item, limit=None):
    """Безопасно добавить запись в JSON-список на диске."""
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        items = []
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    items = json.load(f)
                if not isinstance(items, list):
                    items = []
            except Exception:
                items = []
        items.append(item)
        if limit and len(items) > limit:
            items = items[-limit:]
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _record_history(event, title, body, channels, link=''):
    """Записать событие в историю уведомлений (максимум 200 записей)."""
    _, label, icon = EVENTS.get(event, (None, event, '🔔'))
    with _history_lock:
        _append_json_list(HISTORY_FILE, {
            'event': event,
            'label': label,
            'icon': icon,
            'title': title,
            'body': body,
            'link': link,
            'channels': channels,
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        }, limit=200)


def _broadcast_web(title, body, icon, event='', link=''):
    """Веб-канал: broadcast-запись в panel_logs.json для всех онлайн-сотрудников."""
    entry = {
        'username': '',
        'role': 'system',
        'action': f'{icon} {title}',
        'detail': body,
        'ip': '',
        'timestamp': datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        'ts': time.time(),  # float — чтобы бейдж ловил события в ту же секунду, что и просмотр
        'broadcast': True,
        'kind': 'notify',
        'event': event,
        'link': link,
    }
    return _append_json_list(PANEL_LOGS_FILE, entry, limit=1000)


def _send_webhook(url, title, body, icon):
    """Отправить embed в Discord-webhook. Возвращает (ok, ошибка)."""
    try:
        import requests
        payload = {
            'username': 'Aether Уведомления',
            'embeds': [{
                'title': f'{icon} {title}',
                'description': body[:4000],
                'color': 0xC8922A,
                'footer': {'text': 'Aether · Уведомления панели'},
                'timestamp': datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            }],
        }
        r = requests.post(url, json=payload, timeout=8)
        if r.status_code in (200, 204):
            return True, ''
        return False, f'HTTP {r.status_code}'
    except Exception as e:
        return False, str(e)[:200]


def _send_email_sync(settings, title, body, result_box):
    """Отправить email через SMTP (выполняется в фоновом потоке)."""
    try:
        server = (settings.get('smtp_server') or '').strip()
        login = (settings.get('smtp_email') or '').strip()
        password = settings.get('smtp_password') or ''
        port = int(settings.get('smtp_port') or 587)
        if not server or not login:
            result_box.append((False, 'SMTP не настроен'))
            return
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = Header(f'Aether · {title}', 'utf-8')
        msg['From'] = login
        msg['To'] = login
        with smtplib.SMTP(server, port, timeout=10) as smtp:
            smtp.ehlo()
            try:
                smtp.starttls()
                smtp.ehlo()
            except Exception as _ex:
                _log.debug("_send_email_sync(): подавлено: %s", _ex)
            if password:
                smtp.login(login, password)
            smtp.sendmail(login, [login], msg.as_string())
        result_box.append((True, ''))
    except Exception as e:
        result_box.append((False, str(e)[:200]))


def notify_event(event, title, body, link='', discord_sender=None):
    """Отправить событие по всем включённым каналам.

    event          — ключ из EVENTS (ticket_open, ticket_close, ...);
    title/body     — текст уведомления (по-русски);
    discord_sender — опциональный callback (channel_id, title, body) -> bool
                     для отправки в обычный Discord-канал (бот/web-сторона).

    Возвращает dict со статусами каналов: True — доставлено,
    False — ошибка, None — канал не настроен. Всегда fail-safe.
    """
    channels = {'web': None, 'discord': None, 'email': None}
    try:
        settings = load_settings()
        flag, label, icon = EVENTS.get(event, (None, event, '🔔'))
        if flag and not settings.get(flag):
            channels['skipped'] = 'Событие отключено в настройках'
            return channels

        full_title = title or label
        link = link or EVENT_LINKS.get(event, '')

        # ── Веб (панель) ────────────────────────────────────────────────
        if settings.get('web_enabled', True):
            channels['web'] = _broadcast_web(full_title, body, icon, event=event, link=link)

        # ── Discord ─────────────────────────────────────────────────────
        if settings.get('discord_enabled', True):
            hook = (settings.get('webhook_url') or '').strip()
            chan = (settings.get('discord_channel') or '').strip()
            if hook:
                ok, _err = _send_webhook(hook, full_title, body, icon)
                channels['discord'] = ok
            elif chan and callable(discord_sender):
                try:
                    channels['discord'] = bool(discord_sender(chan, f'{icon} {full_title}', body))
                except Exception:
                    channels['discord'] = False

        # ── Email (в потоке с ожиданием результата, максимум 20 c) ──────
        if settings.get('email_enabled'):
            result_box = []
            t = threading.Thread(
                target=_send_email_sync,
                args=(settings, full_title, body, result_box),
                daemon=True,
            )
            t.start()
            t.join(timeout=20)
            if result_box:
                channels['email'] = result_box[0][0]
            else:
                channels['email'] = False

        _record_history(event, full_title, body, channels, link=link)
    except Exception as _ex:
        _log.debug("notify_event(): подавлено: %s", _ex)
    return channels


def send_test(discord_sender=None):
    """Тестовое уведомление по всем настроенным каналам (игнорирует переключатели событий)."""
    return notify_event(
        'test',
        'Тестовое уведомление',
        'Если вы видите это сообщение — канал уведомлений настроен правильно. ✅',
        discord_sender=discord_sender,
    )
