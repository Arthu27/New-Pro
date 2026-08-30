# -*- coding: utf-8 -*-
"""Мост PagerDuty → Discord: приём тревог и красивые карточки.

PagerDuty не умеет слать в Discord-формат (его webhook-схема чужая), поэтому
панель принимает событие сама: ``POST /hooks/pagerduty/<gid>/<token>`` —
и постит карточку в канал тревог от бота. Схемы PagerDuty:

- v3 «Generic Webhooks»: ``{"event_type": "incident.triggered", "incident":
  {...}}``;
- v2 «Webhook Subscriptions»: ``{"messages": [{"type": "incident.trigger",
  "data": {...}}]}``.

Обе понимаются (normalize_payload). Токен на гильдию — секрет в URL;
сменил в панели — старый URL умер. Хранилище data/pagerduty_hook.json.
"""
import json
import os
import secrets

from logger import get_logger

log = get_logger('pagerduty_hook')

PATH = 'data/pagerduty_hook.json'

# Событие → (эмодзи+заголовок, цвет, что произошло с инцидентом)
EVENTS = {
    'incident.triggered': ('🔥 Тревога', 0xE74C3C, 'сработала — нужен взгляд'),
    'incident.acknowledged': ('👀 Принято', 0xF1C40F, 'взята дежурным'),
    'incident.resolved': ('✅ Решено', 0x2ECC71, 'успешно закрыта'),
    'incident.unacknowledged': ('⏳ Ожидает', 0xE67E22, 'снова ждёт ответа'),
    'incident.escalated': ('📣 Эскалация', 0xE74C3C, 'поднята выше по цепочке'),
    'incident.reassigned': ('↪️ Передано', 0x3498DB, 'передана другой команде'),
    'incident.delegated': ('🤝 Делегировано', 0x3498DB, 'передана на другой сервис'),
    'incident.priority_updated': ('🎚 Приоритет', 0x9B59B6, 'приоритет изменён'),
    'incident.responder.replaced': ('🔁 Дежурный', 0x3498DB, 'состав дежурных обновлён'),
    'service.created': ('🆕 Сервис', 0x2ECC71, 'новый сервис в PagerDuty'),
    'service.deleted': ('🗑 Сервис', 0xE74C3C, 'сервис удалён'),
}
DEFAULT_EVENT = ('🔔 PagerDuty', 0x95A5A6, 'новое событие')

# v2-типы → v3-типы (webhook subscriptions зовут их иначе)
_V2_ALIAS = {
    'incident.trigger': 'incident.triggered',
    'incident.acknowledge': 'incident.acknowledged',
    'incident.unacknowledge': 'incident.unacknowledged',
    'incident.resolve': 'incident.resolved',
    'incident.escalate': 'incident.escalated',
    'incident.reassign': 'incident.reassigned',
    'incident.delegate': 'incident.delegated',
}


# ── хранилище (токен + тумблер) ─────────────────────────────────────────

def _load():
    try:
        with open(PATH, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    os.makedirs(os.path.dirname(PATH) or '.', exist_ok=True)
    tmp = PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)


def get_settings(gid):
    """{'token': str, 'enabled': bool} — токен создаётся при первом запросе."""
    row = _load().get(str(gid)) or {}
    token = str(row.get('token') or '').strip()
    if not token:
        token = secrets.token_urlsafe(24)
        data = _load()
        data[str(gid)] = {'token': token,
                          'enabled': bool(row.get('enabled', True))}
        _save(data)
        log.info('pagerduty: выдан токен для %s', gid)
    return {'token': token, 'enabled': bool(row.get('enabled', True))}


def regen_token(gid):
    """Новый токен (старый URL мгновенно умирает)."""
    token = secrets.token_urlsafe(24)
    data = _load()
    row = data.get(str(gid)) or {}
    row['token'] = token
    data[str(gid)] = row
    _save(data)
    log.info('pagerduty: токен %s перегенерирован', gid)
    return token


def set_enabled(gid, on):
    data = _load()
    row = data.get(str(gid)) or {}
    row['enabled'] = bool(on)
    row.setdefault('token', secrets.token_urlsafe(24))
    data[str(gid)] = row
    _save(data)
    return bool(on)


def check_token(gid, token):
    """True, если токен верен и мост включён."""
    st = get_settings(gid)
    return bool(st['enabled']) and secrets.compare_digest(st['token'],
                                                          str(token or ''))


# ── история доставок (кольцевой журнал на 50 событий) ────────────────────
# Ответ на вопрос «данные отправляются или нет?» — видно из панели:
# каждое событие PagerDuty (и тестовая тревога) пишется сюда с результатом
# доставки: sent / offline / no_channel / error. Живёт в том же файле.

HISTORY_LIMIT = 50


def log_delivery(gid, info, status, note=''):
    """Записать доставку: (gid, карточка-данные, статус, пояснение)."""
    try:
        from datetime import datetime, timezone
        data = _load()
        row = data.get(str(gid)) or {}
        hist = row.get('history') if isinstance(row.get('history'), list) else []
        hist.append({
            'at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'event': str(info.get('event') or ''),
            'title': str(info.get('title') or '')[:80],
            'incident': str(info.get('incident_title') or '')[:120],
            'status': str(status or ''),
            'note': str(note or '')[:120],
        })
        row['history'] = hist[-HISTORY_LIMIT:]
        data[str(gid)] = row
        _save(data)
    except Exception as ex:            # история — не критичный путь
        log.debug('pagerduty: история не записана: %s', ex)


def recent(gid, limit=15):
    """Последние события (новые первыми)."""
    row = _load().get(str(gid)) or {}
    hist = row.get('history') if isinstance(row.get('history'), list) else []
    out = list(reversed(hist))[:max(1, int(limit or 15))]
    return out


def history_stats(gid):
    """Сводка по истории: сколько всего, доставлено, ждало бота, падений."""
    row = _load().get(str(gid)) or {}
    hist = row.get('history') if isinstance(row.get('history'), list) else []
    st = {'total': len(hist), 'sent': 0, 'offline': 0, 'no_channel': 0,
          'error': 0, 'last_at': ''}
    for e in hist:
        k = str(e.get('status') or '')
        if k in st:
            st[k] += 1
    if hist:
        st['last_at'] = str(hist[-1].get('at') or '')
    return st


# ── разбор payload PagerDuty (v2 и v3) ───────────────────────────────────

def normalize_payload(payload):
    """Любая схема PagerDuty → (event_type_v3, incident_dict).

    Мусор/пустота → (None, {}).
    """
    if not isinstance(payload, dict):
        return None, {}
    # v2: {"messages": [{"type": "incident.trigger", "data": {...}}]}
    if isinstance(payload.get('messages'), list) and payload['messages']:
        msg = payload['messages'][0]
        if isinstance(msg, dict):
            etype = str(msg.get('type') or '')
            etype = _V2_ALIAS.get(etype, etype)
            inc = msg.get('data')
            return etype, inc if isinstance(inc, dict) else {}
    # v3: {"event_type": "incident.triggered", "incident": {...}}
    etype = str(payload.get('event_type') or '')
    etype = _V2_ALIAS.get(etype, etype)
    inc = payload.get('incident')
    if not isinstance(inc, dict):
        inc = payload.get('data') if isinstance(payload.get('data'), dict) else {}
    return etype, inc if isinstance(inc, dict) else {}


def format_incident(payload):
    """payload PagerDuty → данные для embed-карточки (чистая функция).

    Возвращает dict: kind, title (с эмодзи), color, incident_title, number,
    url, service, assignee, urgency, occurred_at, event, status_line.
    """
    event, inc = normalize_payload(payload)
    payload = payload if isinstance(payload, dict) else {}
    head, color, what = EVENTS.get(event or '', DEFAULT_EVENT)
    number = inc.get('incident_number') or inc.get('number')
    title = head if not number else f'{head} #{number}'
    service = ''
    svc = inc.get('service')
    if isinstance(svc, dict):
        service = str(svc.get('summary') or svc.get('name') or '').strip()
    elif isinstance(svc, str):
        service = svc
    assignee = ''
    assignments = inc.get('assignments')
    if isinstance(assignments, list) and assignments:
        names = []
        for a in assignments:
            who = a.get('assignee') if isinstance(a, dict) else None
            if isinstance(who, dict):
                names.append(str(who.get('summary') or who.get('name') or '').strip())
        assignee = ', '.join(x for x in names if x)
    urgency = str(inc.get('urgency') or '').strip()
    occurred = str(payload.get('occurred_at')
                   or inc.get('created_at')
                   or inc.get('last_status_change_at') or '').strip()
    url = str(inc.get('html_url') or inc.get('url') or '').strip()
    return {
        'kind': 'triggered' if event == 'incident.triggered'
            else ('resolved' if event == 'incident.resolved'
                  else ('ack' if event == 'incident.acknowledged' else 'other')),
        'event': event or 'неизвестное событие',
        'title': title,
        'color': color,
        'incident_title': str(inc.get('title') or inc.get('summary')
                              or payload.get('description') or '—').strip(),
        'number': number,
        'url': url,
        'service': service,
        'assignee': assignee,
        'urgency': urgency,
        'occurred_at': occurred,
        'status_line': what,
    }
