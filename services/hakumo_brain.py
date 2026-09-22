# -*- coding: utf-8 -*-
"""Hakumo Brain — свой ИИ-ассистент сервера.

Не набор триггеров. Модель:
  1) читает вопрос и досье сервера
  2) при необходимости вызывает инструменты [FUNC:...]
  3) сравнивает факты и отвечает коротко по-русски

Офлайн-фолбэк по ключам — только если ни Ollama, ни API недоступны.
"""
from __future__ import annotations

import re
from typing import Any

BRAIN_VERSION = 'hakumo-brain-1'

# Каталог инструментов (для промпта). Реальное выполнение — web.ai_functions.AIFunctions.
TOOL_CATALOG = """
ИНСТРУМЕНТЫ (если данных в досье не хватает — вызови, не выдумывай):
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
- Сначала смотри ДОСЬЕ и хроники ниже — часто ответ уже там.
- Нужны свежие/точные цифры или история участника — вызови FUNC.
- Можно несколько FUNC подряд (не больше 3 за ответ).
- После FUNC не выдумывай результат: дождись данных системы.
- ID участника бери из вопроса (@ / цифры), не подставляй чужие.
""".strip()


def build_brain_preamble(custom_instructions: str = '') -> list[str]:
    """Системные правила «думающего» ассистента."""
    lines = [
        f'Ты Hakumo Brain ({BRAIN_VERSION}) — AI-ассистент ЭТОГО Discord-сервера.',
        'Ты НЕ шаблон и НЕ набор ключевых слов. Ты думаешь над каждым сообщением.',
        '',
        'КАК РАБОТАТЬ (внутри, не показывай ход мыслей пользователю):',
        '1) Пойми, что именно спросили (факт / помощь / статус / человек / настройка).',
        '2) Найди ответ в досье сервера, правилах, хронике канала, инструкциях.',
        '3) Если данных мало — вызови инструмент [FUNC:...].',
        '4) Сравни факты, отбрось противоречия, ответь уверенно и коротко.',
        '',
        'СТИЛЬ: только русский. 1–4 предложения на простой вопрос. Без «дружище»,',
        'без Moebius, без «автономный ассистент», без «я внимательно прочитал».',
        'Представляйся только если спросили «кто ты».',
        'Не выдумывай команды, цифры, имена и наказания. Чего нет в данных — скажи честно',
        'и предложи, куда смотреть (/report, панель, /modpanel).',
        'Тикет-системы нет. Жалобы — /report.',
        'Наказания выдаёт только модератор-человек — ты не наказываешь.',
        '',
        TOOL_CATALOG,
    ]
    custom = (custom_instructions or '').strip()
    if custom:
        lines.append('')
        lines.append('ИНСТРУКЦИИ ВЛАДЕЛЬЦА СЕРВЕРА (выполняй обязательно):')
        lines.append(custom[:4000])
    return lines


_FUNC_RE = re.compile(r'\[FUNC:[^\]]+\]')


def extract_func_calls(text: str) -> list[str]:
    if not text:
        return []
    return _FUNC_RE.findall(text)[:3]


def strip_func_calls(text: str) -> str:
    if not text:
        return ''
    out = _FUNC_RE.sub('', text)
    return re.sub(r'\n{3,}', '\n\n', out).strip()


def build_tool_followup_message(question: str, func_results: str) -> str:
    """Второй ход: модель получает результаты инструментов."""
    return (
        'Результаты инструментов по твоему запросу:\n'
        f'{func_results.strip()}\n\n'
        'Собери итоговый ответ пользователю на русском: коротко, по фактам выше. '
        'Не повторяй теги [FUNC:...]. Не выдумывай то, чего нет в результатах.\n'
        f'Исходный вопрос: {question}'
    )


def settings_custom_instructions(cfg: dict[str, Any] | None) -> str:
    if not isinstance(cfg, dict):
        return ''
    return str(cfg.get('custom_instructions') or cfg.get('system_prompt') or '').strip()
