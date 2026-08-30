# -*- coding: utf-8 -*-
"""Стартовая видимость: КАКОЙ код запущен + чистое эхо туннеля.

Инцидент 30.08: владелец запустил /update со стандартным источником
(Arthu27/New-Pro, ветка main — БЕЗ фиксов) — бот молча откатился на
старый код. Ни в логе, ни в панели не было НИ ОДНОГО признака, что
фиксов больше нет: строк запуска не хватало, чтобы это увидеть.

Теперь:
  * ПЕРВАЯ строка запуска — [ВЕРСИЯ] с sha кода (git или маркер
    data/.update_sha от ZIP-обновления) — «на чём я вообще работаю»
    видно сразу, без панели и без гаданий;
  * эхо лога туннеля не топит сообщения бота: ~60 строк cloudflared
    за рестарт сжимаются до нескольких значимых (ошибки, регистрации
    соединений, итог пре-чеков).

Обе функции чистые и покрыты тестами (tests/test_startup_visibility.py).
"""
import os

# Что стоит показывать владельцу из лога cloudflared. Всё прочее —
# служебный INF-шум (таблицы пре-чеков, curve preferences, ICMP proxy,
# metrics server), который прятал сообщения бота.
_TUNNEL_KEEP = (
    'ERR',                      # любые ошибки cloudflared
    'WRN',                      # предупреждения cloudflared
    'registered tunnel connection',   # «туннель поднялся» + локация (fra…)
    'unregistered tunnel connection', # туннель отвалился
    'summary:',                 # итог пре-чеков («Environment is healthy»)
    'failed',                   # сбои подключения/обновления
    'retrying connection',      # cloudflared переподключается
    'shutdown',                 # штатная остановка туннеля
    'connection terminated',    # обрыв соединения
)


def tunnel_line_worth(line):
    """ True — строку лога cloudflared стоит показать владельцу.

    Регистр не важен; пустые строки отбрасываются.
    """
    low = (line or '').strip().lower()
    if not low:
        return False
    return any(k in low for k in _TUNNEL_KEEP)


def version_stamp(bot_dir=None, local_sha=None, _local_sha_fn=None):
    """Человекочитаемая версия запущенного кода для строки [ВЕРСИЯ].

    Порядок: явно переданный sha -> git HEAD каталога -> маркер
    data/.update_sha (его пишет ZIP-обновление) -> «неизвестна».
    Возвращает строку вида «ae9e624» (+ способ определения).
    """
    sha = local_sha
    how = None
    if sha is None:
        # Основной путь — как в панели: git HEAD каталога, иначе маркер
        # data/.update_sha от ZIP-обновления. ВАЖНО: git ПРИОРИТЕТНЕЕ
        # маркера (инцидент 30.08: устаревший маркер врал о версии).
        fn = _local_sha_fn
        if fn is None:
            try:
                from services.self_update import local_sha as _ls
                fn = _ls
            except Exception:
                fn = None
        if fn is not None:
            try:
                sha = fn(bot_dir) or None
                if sha:
                    how = 'git/маркер'
            except Exception:
                sha = None
    if sha is None and _local_sha_fn is None and bot_dir is not None:
        # лёгкий фолбэк, если self_update недоступен: маркер напрямую
        try:
            with open(os.path.join(str(bot_dir), 'data', '.update_sha'),
                      encoding='utf-8') as f:
                sha = (f.read() or '').strip() or None
            if sha:
                how = 'маркер обновления'
        except OSError:
            sha = None
    if not sha:
        return 'НЕИЗВЕСТНА (zip без маркера — запусти /update и перезапусти)'
    short = str(sha).strip()[:7]
    return f'{short}' + (f' ({how})' if how else '')
