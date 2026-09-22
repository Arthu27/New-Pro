# -*- coding: utf-8 -*-
"""Hakumo Brain — свой ИИ-ассистент сервера.

Приоритет: локальная Ollama (свой мозг) → облачные API (запас) → короткий офлайн.
Модель думает, смотрит досье, вызывает инструменты — не триггеры.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

BRAIN_VERSION = 'hakumo-brain-2'

# Каталог инструментов (для промпта). Реальное исполнение — web.ai_functions.AIFunctions.
TOOL_CATALOG = """
ИНСТРУМЕНТЫ (нет факта в досье → вызови FUNC, не выдумывай):
[FUNC:get_server_stats()]
[FUNC:search_rules(query="...")]
[FUNC:get_user_info(user_id=...)]
[FUNC:get_user_warnings(user_id=...)]
[FUNC:get_user_roles(user_id=...)]
[FUNC:check_user_reputation(user_id=...)]
[FUNC:search_user_messages(user_id=..., limit=20)]
[FUNC:get_weekly_activity(days=7)]
[FUNC:get_moderator_weekly(days=7)]
[FUNC:search_knowledge_base(query="...")]
[FUNC:remember_fact(user_id=..., fact="...")]
[FUNC:recall_facts(user_id=...)]

Правила инструментов:
- Сначала ДОСЬЕ и хроника ниже.
- Цифры, варны, история человека, топ активности — только через FUNC или досье.
- Не больше 3 FUNC за ход.
- ID участника — только из вопроса, не подставляй чужие.
""".strip()

# Команды, которых в боте точно нет — вырезаем из ответа, если модель выдумала.
_BANNED_COMMANDS = (
    '/ticket', '/tickets', '/play', '/skip', '/queue', '/xp', '/shop',
    '/economy', '/balance', '/daily', '/music', '/search',
)


def build_brain_preamble(custom_instructions: str = '') -> list[str]:
    """Системные правила точного ассистента."""
    lines = [
        f'Ты Hakumo Brain ({BRAIN_VERSION}) — AI-ассистент ЭТОГО Discord-сервера.',
        'Ты свой локальный помощник сервера. Не болтун и не набор ключевых слов.',
        '',
        'ТОЧНОСТЬ (важнее красоты):',
        '• Факт о сервере (цифры, имена, роли, каналы, варны, онлайн) — ТОЛЬКО из досье/FUNC.',
        '• Нет факта → скажи «в данных этого нет» и что проверить (/report, панель, /modpanel).',
        '• Не выдумывай команды. Реальные: /modpanel /report /my-violations /afk /history.',
        '• Тикетов, музыки, экономики, XP в боте НЕТ — никогда не советуй их.',
        '• Наказания выдаёт только человек-модератор.',
        '• Лучше короткий честный ответ, чем длинный с ошибкой.',
        '',
        'КАК ДУМАТЬ (внутри, не показывай пользователю):',
        '1) Что спросили?',
        '2) Есть ли ответ в досье/инструкциях/хронике?',
        '3) Нет → [FUNC:...]',
        '4) Сверь факты, убери сомнительное, ответь коротко по-русски.',
        '',
        'СТИЛЬ: русский, 1–4 предложения. Без «дружище», Moebius, «автономный ассистент»,',
        'без «я внимательно прочитал», без «хороший вопрос».',
        'Представляйся только на «кто ты».',
        '',
        TOOL_CATALOG,
    ]
    custom = (custom_instructions or '').strip()
    if custom:
        lines.append('')
        lines.append('ИНСТРУКЦИИ ВЛАДЕЛЬЦА (обязательно):')
        lines.append(custom[:4000])
    return lines


_FUNC_RE = re.compile(r'\[FUNC:[^\]]+\]')
_CMD_RE = re.compile(r'/[a-zA-Z][\w-]{1,32}')


def extract_func_calls(text: str) -> list[str]:
    if not text:
        return []
    return _FUNC_RE.findall(text)[:3]


def strip_func_calls(text: str) -> str:
    if not text:
        return ''
    out = _FUNC_RE.sub('', text)
    return re.sub(r'\n{3,}', '\n\n', out).strip()


def ground_answer(text: str, allowed_slash: set[str] | None = None) -> str:
    """Убрать явные выдумки из ответа модели."""
    if not text:
        return text
    out = str(text)
    for bad in _BANNED_COMMANDS:
        out = re.sub(re.escape(bad), '/report' if 'ticket' in bad else '(нет такой команды)', out, flags=re.I)
    # Вырезаем слеш-команды вне whitelist, если он передан
    if allowed_slash:
        def _fix(m: re.Match) -> str:
            cmd = m.group(0).lstrip('/').lower()
            if cmd in allowed_slash or ('/' + cmd) in allowed_slash:
                return m.group(0)
            return '(команды нет)'
        out = _CMD_RE.sub(_fix, out)
    out = re.sub(r'(?i)\bmoebius\b', '', out)
    out = re.sub(r'(?i)автономн\w*\s+ассистент', 'ассистент', out)
    out = re.sub(r'(?i),?\s*дружище!?', '', out)
    out = re.sub(r'[ \t]{2,}', ' ', out)
    return out.strip()


def build_tool_followup_message(question: str, func_results: str) -> str:
    return (
        'Результаты инструментов (это единственный источник фактов):\n'
        f'{func_results.strip()}\n\n'
        'Ответь пользователю по-русски коротко ТОЛЬКО по этим данным. '
        'Нет данных — так и скажи. Без [FUNC:...], без выдумок.\n'
        f'Вопрос: {question}'
    )


def settings_custom_instructions(cfg: dict[str, Any] | None) -> str:
    if not isinstance(cfg, dict):
        return ''
    return str(cfg.get('custom_instructions') or cfg.get('system_prompt') or '').strip()


def own_model_name(requested: str | None = None) -> str:
    """Имя модели для своего ИИ (Ollama)."""
    return (
        (os.getenv('OLLAMA_MODEL') or '').strip()
        or (os.getenv('AI_OWN_MODEL') or '').strip()
        or 'llama3.1'
    )


def backup_model_name(requested: str | None = None) -> str:
    """Имя модели для облачного запаса."""
    return (
        (requested or '').strip()
        or (os.getenv('AI_MODEL') or '').strip()
        or 'mistral-large-latest'
    )


def check_own_ai() -> dict[str, Any]:
    """Статус своего ИИ (Ollama) для панели."""
    url = (os.getenv('OLLAMA_URL') or 'http://127.0.0.1:11434').rstrip('/')
    model = own_model_name()
    info: dict[str, Any] = {
        'own_ai': True,
        'provider': 'ollama',
        'url': url,
        'model': model,
        'online': False,
        'models': [],
        'hint': '',
    }
    try:
        req = urllib.request.Request(f'{url}/api/tags', method='GET')
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        names = []
        for m in data.get('models') or []:
            name = str(m.get('name') or m.get('model') or '')
            if name:
                names.append(name)
        info['models'] = names[:30]
        info['online'] = True
        have = any(model == n or n.startswith(model + ':') or model in n for n in names)
        if not names:
            info['hint'] = f'Ollama запущена, но моделей нет. Установи: ollama pull {model}'
        elif not have:
            info['hint'] = (
                f'Ollama онлайн, модели «{model}» нет. '
                f'Есть: {", ".join(names[:5])}. Поставь: ollama pull {model}'
            )
        else:
            info['hint'] = f'Свой ИИ готов: {model}'
    except Exception as ex:
        info['hint'] = (
            f'Ollama недоступна ({ex}). На VDS: установи Ollama, '
            f'ollama pull {model}, в .env OLLAMA_URL={url}'
        )
    return info
