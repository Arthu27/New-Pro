# -*- coding: utf-8 -*-
"""«Настройки не все завершены» — что НЕ настроено для системы бота.

Правило (заказ владельца 2026-08-27): если системой пользоваться рано,
бот НЕ молчит и НЕ ломается молча — он говорит по-человечески, ЧТО именно
не настроено. В списке только НЕЗАВЕРШЁННОЕ: то, что уже настроено,
не упоминается.

Формат единый для всех систем:
    system_missing(guild) -> [str, ...]   # человеческие пункты
    readiness_block(title, missing) -> str|None  # готовый текст или None
"""


def readiness_block(title: str, missing) -> str or None:
    """Красивый текст «настройки не все завершены» или None, если всё ок."""
    items = [m for m in (missing or []) if m]
    if not items:
        return None
    lines = [f'**{title}: настройки не все завершены.**', '']
    for i, m in enumerate(items, 1):
        lines.append(f'**{i}.** {m}')
    lines.append('')
    lines.append('Доделайте — и всё заработает.')
    return '\n'.join(lines)


def staff_apply_missing(guild) -> list:
    """Что не готово для системы заявок в команду (/staff-panel).

    Проверяем только то, без чего заявки реально теряются или
    не работают. Куратор — необязателен, его не требуем.
    """
    if not guild:
        return []
    issues = []
    from cogs.staff_apply import apply_target
    from services.staff_roles import resolve_staff_role

    # 1) куда приходят заявки: ветка хелперов/модераторов или общий канал
    try:
        ch_h, _ = apply_target('Хелпер', guild)
        ch_m, _ = apply_target('Модератор', guild)
    except Exception:
        ch_h = ch_m = None
    if ch_h is None and ch_m is None:
        issues.append('не выбран канал, куда приходят заявки — панель → '
                      '«Настройки» → «Каналы и маршруты» (ветка хелперов, '
                      'ветка модераторов или общий канал заявок)')
    else:
        if ch_h is None:
            issues.append('заявки хелперов падают в общую ветку: отдельная '
                          'ветка хелперов не выбрана (не обязательно, но '
                          'удобнее) — «Каналы и маршруты»')
        if ch_m is None:
            issues.append('заявки модераторов падают в общую ветку: отдельная '
                          'ветка модераторов не выбрана (не обязательно, но '
                          'удобнее) — «Каналы и маршруты»')

    # 2) роли, выдаваемые после одобрения
    for kind, label in (('helper', 'хелпера'), ('moderator', 'модератора')):
        try:
            role, searched = resolve_staff_role(guild, kind)
        except Exception:
            role, searched = None, []
        if role is None:
            names = ' / '.join(f'«{n}»' for n in searched[:3]) or 'по имени'
            issues.append(f'роль {label} не найдена на сервере — создайте её '
                          f'(искали: {names}) или выберите готовую: панель → '
                          f'«Настройки» → «Бот» → «Заявки в команду»')
    return issues
