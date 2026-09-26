# services/csp_hashes.py — хэши статичных инлайн-обработчиков панели
#
# СТРОГИЙ CSP ПАНЕЛИ (2026-09-08). У панели 100+ шаблонов, в которых
# исторически живут инлайн-обработчики вида onclick="doThing(1)".
# Динамические (с интерполированными аргументами) переписаны на
# data-act-делегирование (см. base.html), а СТАТИЧНЫЕ — те, чей код
# одинаков при каждом рендере — разрешаются точечными sha256-хэшами
# вместо выбрасывания 'unsafe-inline' на всю панель.
#
# CSP3: hash-source в script-src применяется к обработчикам on*-атрибутов
# ТОЛЬКО вместе с 'unsafe-hashes'. Хэш считается по значению атрибута
# БЕЗ имени атрибута и кавычек: entity-декодированный текст → UTF-8 →
# SHA-256 → base64. Ровно так делает Chrome, и ровно так делаем мы
# (проверено тестом test_public_csp.py: html-парсер → значение → sha256
# обязан совпасть с хэшем в заголовке отрендеренной страницы).
#
# Динамические обработчики (JS-конкатенация с данными внутри значения)
# хэшировать бессмысленно — их код меняется от запроса к запросу; они
# обязаны жить делегированием. Сканер такие значения ПРОПУСКАЕТ: если
# такой остался в шаблоне, обработчик в браузере молча умрёт — тест
# test_web_hygiene.py («динамических обработчиков нет») ловит регресс.

import base64
import hashlib
import html
import logging
import os
import re

_log = logging.getLogger('hakumo.csp_hashes')

_TPL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'web', 'templates')

# on*= в РАЗМЕТКЕ и в JS-строках; не трогаем oncontent*/onrols* (не события
# в нашем коде — это части слов из локализации) и содержимое комментариев.
_HANDLER_RE = re.compile(r'\son[a-z]+\s*=\s*(["\'])(.*?)\1', re.S)
_NOT_EVENT_RE = re.compile(r'\son(tent|rols)\b')
# Признак динамического обработчика: JS-конкатенация внутри значения.
_DYNAMIC_RE = re.compile(r"'\s*\+|\+\s*'")

_cache = {'stamp': None, 'hashes': ()}


def _scan():
    """Собрать уникальные хэши статичных обработчиков всех шаблонов."""
    stamp = []
    skipped = []
    for fn in sorted(os.listdir(_TPL_DIR)):
        if not fn.endswith('.html'):
            continue
        p = os.path.join(_TPL_DIR, fn)
        try:
            stamp.append((fn, os.path.getmtime(p), os.path.getsize(p)))
        except OSError as e:
            # шаблон исчез между listdir и stat — в хэши не попадает,
            # но молчать нельзя: панель молча потеряет обработчики.
            skipped.append('%s: %s' % (fn, e))
    stamp = tuple(stamp)
    if stamp == _cache['stamp']:
        return _cache['hashes']

    unique = set()
    for fn, _mt, _sz in stamp:
        try:
            with open(os.path.join(_TPL_DIR, fn), encoding='utf-8') as fh:
                src = fh.read()
        except (OSError, UnicodeDecodeError) as e:
            skipped.append('%s: %s' % (fn, e))
            continue
        for m in _HANDLER_RE.finditer(src):
            if _NOT_EVENT_RE.match(m.group(0)):
                continue
            code = m.group(2)
            if _DYNAMIC_RE.search(code):
                continue  # динамические — только через делегирование
            # Браузер видит ЗНАЧЕНИЕ атрибута: entity-декодированный текст.
            unique.add(html.unescape(code))

    if skipped:
        _log.warning('csp_hashes: шаблоны пропущены (%d): %s',
                     len(skipped), '; '.join(skipped[:5]))

    hashes = tuple(sorted(
        "'sha256-" + base64.b64encode(hashlib.sha256(c.encode('utf-8')).digest()).decode('ascii') + "'"
        for c in unique))
    _cache['stamp'] = stamp
    _cache['hashes'] = hashes
    return hashes


def panel_handler_hashes():
    """Список 'sha256-...' для статичных on*-обработчиков панели.

    Кэш — по (mtime, size) шаблонов: в проде пересчёт только после
    правки шаблона; на каждый HTTP-ответ — копия уже готового кортежа.
    """
    return list(_scan())


def panel_script_src(nonce):
    """Готовая script-src-директива панели: nonce + 'unsafe-hashes' +
    хэши обработчиков. 'unsafe-inline' больше нет: инлайн-скрипты
    идут с nonce, обработчики — по хэшам, остальное мёртво."""
    parts = ["script-src 'self' 'nonce-%s'" % nonce]
    parts.extend(panel_handler_hashes())
    parts.append("'unsafe-hashes'")
    parts.append('https://static.cloudflareinsights.com')
    return ' '.join(parts)
