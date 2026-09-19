# -*- coding: utf-8 -*-
"""Components V2 — конструкторы сообщений нового формата Discord.

Что это: Components V2 (флаг IS_COMPONENTS_V2) — новый конструктор
сообщений Discord вместо эмбедов: блоки TextDisplay (текст с markdown-
заголовками), Container с акцент-цветом и рамкой, Section с картинкой
сбоку, Separator, MediaGallery. discord.py 2.6+ отдаёт их через
LayoutView, флаг ставится библиотекой автоматически — и в
Messageable.send, и в Webhook.send (проверено: 'if view.has_components_v2():
flags.components_v2 = True').

Правило модуля: каждое сообщение строится ДВАЖДЫ — V2-раскладкой и
классическим эмбедом. Если библиотека/клиент старые — уходит фолбек,
бот ничего не теряет. Отправка всегда через send_v2_or_embed().
"""
from datetime import datetime

from discord import SeparatorSpacing

import discord

from logger import get_logger

_log = get_logger("v2_layouts")

try:
    from discord import ui as _ui
    V2_AVAILABLE = all(hasattr(_ui, c) for c in (
        'LayoutView', 'TextDisplay', 'Container', 'Section',
        'Separator', 'Thumbnail', 'MediaGallery', 'ActionRow'))
except Exception as _ex:                                    # pragma: no cover
    V2_AVAILABLE = False
    _log.warning("v2_layouts(): Components V2 недоступны: %s", _ex)


def v2_available() -> bool:
    return V2_AVAILABLE


# ── ГИВКИ ────────────────────────────────────────────────────────────

def giveaway_start_layout(prize: str, winners: int, ends_at: datetime,
                          footer: str = '', icon_url: str = None):
    """Старт розыгрыша в формате V2: контейнер с акцентом, приз крупно,
    детали в три колонки-строки, таймер Discord (<t:...:R>)."""
    if not V2_AVAILABLE:
        return None
    ts = int(ends_at.timestamp())
    head = _ui.TextDisplay('# 🎉 РОЗЫГРЫШ НАЧАЛСЯ')
    prize_block = _ui.TextDisplay(f'## 🏆 {prize}\n'
                                  f'Нажми **Участвовать**, чтобы выиграть!')
    details = _ui.TextDisplay(
        f'**Победителей:** {winners}   •   '
        f'**Участников сейчас:** 0\n'
        f'**Завершение:** <t:{ts}:F> — <t:{ts}:R>')
    box = _ui.Container(head, _ui.Separator(spacing=SeparatorSpacing.large),
                        prize_block, _ui.Separator(), details,
                        accent_colour=discord.Colour(0x2ECC71))
    if footer:
        box.add_item(_ui.Separator())
        box.add_item(_ui.TextDisplay(f'-# {footer}'))
    view = _ui.LayoutView(timeout=None)
    view.add_item(box)
    return view


def giveaway_start_embed(prize: str, winners: int, ends_at: datetime,
                         footer: str = ''):
    """Фолбек: тот же старт розыгрыша классическим эмбедом."""
    ts = int(ends_at.timestamp())
    e = discord.Embed(title='🎉 РОЗЫГРЫШ НАЧАЛСЯ', color=0x2ECC71,
                      timestamp=ends_at)
    e.description = (f'**🏆 Награда:** `{prize}`\n\n'
                     'Чтобы участвовать, нажми кнопку **Участвовать**!\n'
                     f'Завершается <t:{ts}:R>.')
    e.add_field(name='🏆 Победителей', value=str(winners), inline=True)
    e.add_field(name='⏰ Завершение', value=f'<t:{ts}:F>', inline=True)
    if footer:
        e.set_footer(text=footer)
    return e


def giveaway_end_layout(prize: str, winner_mentions: list, footer: str = '',
                        ok: bool = True):
    """Финал розыгрыша в V2: победители крупно, золото/серый акцент."""
    if not V2_AVAILABLE:
        return None
    colour = discord.Colour(0xF0CD7A) if ok else discord.Colour.dark_grey()
    if winner_mentions:
        body = _ui.TextDisplay(
            f'## 🏆 {prize}\n' +
            '\n'.join(f'- {m}' for m in winner_mentions) +
            '\nПоздравляем! Свяжитесь с администрацией для получения приза.')
    else:
        body = _ui.TextDisplay(f'## {prize}\nНедостаточно участников — '
                               'победитель не определён.')
    view = _ui.LayoutView(timeout=None)
    view.add_item(_ui.Container(
        _ui.TextDisplay('# 🎉 РОЗЫГРЫШ ЗАВЕРШЁН'),
        _ui.Separator(spacing=SeparatorSpacing.large),
        body,
        accent_colour=colour))
    return view


def giveaway_end_embed(prize: str, winner_mentions: list, ok: bool = True):
    """Фолбек: финал классическим эмбедом (как раньше)."""
    if not winner_mentions:
        return discord.Embed(title='Розыгрыш завершён',
                             description='Недостаточно участников.',
                             color=discord.Color.dark_grey())
    winners_text = '\n'.join(f'**{w}**' for w in winner_mentions)
    return discord.Embed(
        title='🎉 Розыгрыш завершён',
        description=f'**Приз:** {prize}\n\n**Победители:**\n{winners_text}\n\n'
                    'Поздравляем! Свяжитесь с администрацией.',
        color=0xF0CD7A)


# ── ПРАВИЛА ──────────────────────────────────────────────────────────

def rules_layout(title: str, items: list, footer: str = '',
                 icon_url: str = None, accent: int = 0x818CF8,
                 intro: str = ''):
    """Правила сервера в V2: контейнер, заголовок, вступление, иконка сбоку
    (Section), каждый пункт — отдельным блоком с разделителем. Голосом
    вебхука такое сообщение приходит от «Правила сервера», а не от бота."""
    if not V2_AVAILABLE:
        return None
    children = [_ui.TextDisplay(f'# {title}'),
                _ui.Separator(spacing=SeparatorSpacing.large)]
    if icon_url:
        children.append(_ui.Section(
            _ui.TextDisplay(intro or ('Соблюдай простые правила — и всем '
                                      'будет комфортно. Наказания выдаёт '
                                      'только модератор-человек.')),
            accessory=_ui.Thumbnail(media=icon_url)))
    elif intro:
        children.append(_ui.TextDisplay(intro))
    for i, item in enumerate(items, 1):
        head, text = (item if isinstance(item, (list, tuple)) else (None, item))
        line = f'**{i}. {head}**' if head else f'**{i}.**'
        if text:
            line += f'\n{text}'
        children.append(_ui.TextDisplay(line))
        children.append(_ui.Separator())
    if footer:
        children.append(_ui.TextDisplay(f'-# {footer}'))
    view = _ui.LayoutView(timeout=None)
    view.add_item(_ui.Container(*children, accent_colour=discord.Colour(accent)))
    return view


def rules_embed(title: str, items: list, footer: str = ''):
    """Фолбек: правила классическим эмбедом."""
    e = discord.Embed(title=title, color=0x818CF8)
    for i, item in enumerate(items[:10], 1):
        head, text = (item if isinstance(item, (list, tuple)) else (None, item))
        name = f'{i}. {head}' if head else f'{i}.'
        e.add_field(name=name, value=(text or '—')[:1024], inline=False)
    if footer:
        e.set_footer(text=footer[:200])
    return e


# ── МОДЕРАЦИЯ /modpanel ──────────────────────────────────────────────

def modpanel_status_text(selected_uid=None, pending_label=None) -> str:
    """Подпись под баннером в шапке панели (без «порядок любой»)."""
    bits = []
    if selected_uid:
        bits.append(f'участник <@{selected_uid}>')
    if pending_label:
        bits.append(f'«{pending_label}»')
    if bits:
        return ' · '.join(bits)
    return 'Выберите участника и действие ниже.'


# Чёрный акцент Container (рамка/полоса слева) — селекты Discord
# нельзя перекрасить, поэтому каждый select живёт в своём чёрном блоке.
_BLACK = 0x000000


def black_container(*children, accent: int = None):
    """Container с чёрным accent (0x000000) или своим цветом."""
    colour = discord.Colour(accent if accent is not None else _BLACK)
    return _ui.Container(*children, accent_colour=colour)


def _gallery(banner_filename: str):
    from discord.components import MediaGalleryItem
    return _ui.MediaGallery(MediaGalleryItem(f'attachment://{banner_filename}'))


# Баннер в шапке вместе с заголовком (как в референсе V2).
SHOW_MENU_BANNER = True


def build_modpanel_items(*, banner_filename: str, status: str,
                         footer: str = 'Hakumo · модерация',
                         target_select=None, action_select=None,
                         show_banner: bool = None):
    """Карточки как в референсе: шапка · участник · действие · футер."""
    if not V2_AVAILABLE:
        return None
    if show_banner is None:
        show_banner = SHOW_MENU_BANNER
    items = []
    # 1) шапка: заголовок + HAKUMO + разделитель + баннер + статус
    head = [
        _ui.TextDisplay('# Панель модерации\n-# HAKUMO'),
        _ui.Separator(spacing=SeparatorSpacing.large),
    ]
    if show_banner and banner_filename:
        head.append(_gallery(banner_filename))
    if status:
        head.append(_ui.TextDisplay(status))
    items.append(black_container(*head))
    # 2) участник — заголовок без дубля placeholder
    if target_select is not None:
        row = _ui.ActionRow()
        row.add_item(target_select)
        items.append(black_container(
            _ui.TextDisplay('**Участник**'),
            row,
        ))
    # 3) действие — заголовок без дубля placeholder
    if action_select is not None:
        row = _ui.ActionRow()
        row.add_item(action_select)
        items.append(black_container(
            _ui.TextDisplay('**Действие**'),
            row,
        ))
    # 4) футер
    foot = (footer or 'Hakumo · модерация').strip()
    if foot:
        items.append(black_container(_ui.TextDisplay(f'-# {foot}')))
    return items


def build_modpanel_container(*, banner_filename: str, status: str,
                             footer: str = 'Hakumo · модерация',
                             target_select=None, action_select=None,
                             show_banner: bool = None):
    """Один общий Container (фолбек) — без раздельных блоков."""
    if not V2_AVAILABLE:
        return None
    if show_banner is None:
        show_banner = SHOW_MENU_BANNER
    children = [
        _ui.TextDisplay('# Панель модерации\n-# HAKUMO'),
        _ui.Separator(spacing=SeparatorSpacing.large),
    ]
    if show_banner and banner_filename:
        children.append(_gallery(banner_filename))
    if status:
        children.append(_ui.TextDisplay(status))
    if target_select is not None:
        row = _ui.ActionRow()
        row.add_item(target_select)
        children.append(row)
    if action_select is not None:
        row = _ui.ActionRow()
        row.add_item(action_select)
        children.append(row)
    if footer:
        children.append(_ui.Separator())
        children.append(_ui.TextDisplay(f'-# {footer}'))
    return black_container(*children)


def build_appeals_menu_items(*, banner_filename: str, body: str,
                             footer: str, menu_select=None,
                             show_banner: bool = None):
    """Баннер в шапке + select апелляций — как у модерации."""
    if not V2_AVAILABLE:
        return None
    if show_banner is None:
        show_banner = SHOW_MENU_BANNER
    items = []
    head = [
        _ui.TextDisplay('# Апелляции\n-# HAKUMO'),
        _ui.Separator(spacing=SeparatorSpacing.large),
    ]
    if show_banner and banner_filename:
        head.append(_gallery(banner_filename))
    if body:
        head.append(_ui.TextDisplay(body))
    items.append(black_container(*head))
    if menu_select is not None:
        row = _ui.ActionRow()
        row.add_item(menu_select)
        items.append(black_container(
            _ui.TextDisplay('**Обращение**\n-# подать или проверить'),
            row,
        ))
    if footer:
        items.append(black_container(_ui.TextDisplay(f'-# {footer}')))
    return items


def build_staff_menu_items(*, banner_filename: str, body: str = None,
                           role_select=None, show_banner: bool = None):
    """Наборы: шапка с баннером + select роли."""
    if not V2_AVAILABLE:
        return None
    if show_banner is None:
        show_banner = SHOW_MENU_BANNER
    items = []
    head = [
        _ui.TextDisplay('# Наборы\n-# HAKUMO'),
        _ui.Separator(spacing=SeparatorSpacing.large),
    ]
    if show_banner and banner_filename:
        head.append(_gallery(banner_filename))
    if body:
        head.append(_ui.TextDisplay(body))
    items.append(black_container(*head))
    if role_select is not None:
        row = _ui.ActionRow()
        row.add_item(role_select)
        items.append(black_container(
            _ui.TextDisplay('**Роль**\n-# на какую подать'),
            row,
        ))
    return items


def build_events_menu_items(*, banner_filename: str, status: str,
                            action_row=None, show_banner: bool = None):
    """Ивенты: шапка с баннером + действия."""
    if not V2_AVAILABLE:
        return None
    if show_banner is None:
        show_banner = SHOW_MENU_BANNER
    items = []
    head = [
        _ui.TextDisplay('# Ивенты\n-# HAKUMO'),
        _ui.Separator(spacing=SeparatorSpacing.large),
    ]
    if show_banner and banner_filename:
        head.append(_gallery(banner_filename))
    if status:
        head.append(_ui.TextDisplay(status))
    items.append(black_container(*head))
    if action_row is not None:
        items.append(black_container(
            _ui.TextDisplay('**Действия**'),
            action_row,
        ))
    return items


def _full_bleed_gallery(banner_filename: str):
    """Совместимость: MediaGallery (раньше full-bleed)."""
    return _gallery(banner_filename)


def build_log_card_items(*, title: str, rows=None, footer: str = '',
                         accent: int = None, image_filename: str = None,
                         note: str = None):
    """Карточка лога Components V2 (webhook/channel): текст + опционально фото."""
    if not V2_AVAILABLE:
        return None
    children = []
    head = f'# {title}' if title else '# Лог'
    if note:
        head = f'{head}\n{note}'
    children.append(_ui.TextDisplay(head[:4000]))
    if rows:
        lines = []
        for name, value in list(rows)[:12]:
            n = str(name or '').strip()
            v = str(value or '').strip()
            if not v:
                continue
            lines.append(f'**{n}**\n{v}' if n else v)
        if lines:
            children.append(_ui.TextDisplay('\n\n'.join(lines)[:4000]))
    if image_filename:
        children.append(_full_bleed_gallery(image_filename))
    if footer:
        children.append(_ui.TextDisplay(f'-# {footer}'[:500]))
    return [black_container(*children, accent=accent if accent is not None else _BLACK)]


def build_log_card_view(*, title: str, rows=None, footer: str = '',
                        accent: int = None, image_filename: str = None,
                        note: str = None, timeout=None):
    """LayoutView для лога — готов к channel/webhook .send(view=...)."""
    items = build_log_card_items(
        title=title, rows=rows, footer=footer, accent=accent,
        image_filename=image_filename, note=note)
    if not items:
        return None
    view = _ui.LayoutView(timeout=timeout)
    for it in items:
        view.add_item(it)
    return view


def build_appeal_card_items(*, title: str, body: str = '', footer: str = '',
                            image_filename: str = None, buttons=None,
                            accent: int = None):
    """Карточка апелляции V2: текст/фото + ActionRow с кнопками."""
    if not V2_AVAILABLE:
        return None
    children = []
    head = f'# {title}' if title else '# Апелляция'
    if body:
        head = f'{head}\n{body}'
    children.append(_ui.TextDisplay(head[:4000]))
    if image_filename:
        children.append(_full_bleed_gallery(image_filename))
    if footer:
        children.append(_ui.TextDisplay(f'-# {footer}'[:500]))
    if buttons:
        row = _ui.ActionRow()
        for btn in buttons:
            row.add_item(btn)
        children.append(row)
    return [black_container(*children, accent=accent if accent is not None else _BLACK)]


def build_notice_items(*, title: str, body: str = '', footer: str = '',
                       accent: int = None):
    """Короткое V2-уведомление (ЛС / пост-апелляция)."""
    if not V2_AVAILABLE:
        return None
    text = f'# {title}' if title else ''
    if body:
        text = f'{text}\n{body}' if text else body
    children = [_ui.TextDisplay(text[:4000])]
    if footer:
        children.append(_ui.TextDisplay(f'-# {footer}'[:500]))
    return [black_container(*children, accent=accent if accent is not None else _BLACK)]


def notice_layout_view(*, title: str, body: str = '', footer: str = '',
                       accent: int = None, timeout=None):
    items = build_notice_items(title=title, body=body, footer=footer, accent=accent)
    if not items:
        return None
    view = _ui.LayoutView(timeout=timeout)
    for it in items:
        view.add_item(it)
    return view


async def send_v2_or_embed(target, *, view, embed, fallback_view=None,
                           v2_items=None):
    """Отправить V2-раскладку, а если её нет/клиент старый — эмбед.

    target — TextChannel/Webhook (всё, что умеет .send).
    v2_items — кнопки, добавляемые внутрь раскладки (для V2 кнопки живут
    в том же сообщении); fallback_view — обычный View с кнопками для
    эмбед-ветки (например, GiveawayView). Возвращает сообщение или None.
    """
    fallback_kw = {'embed': embed}
    if fallback_view is not None:
        fallback_kw['view'] = fallback_view
    try:
        if view is not None and V2_AVAILABLE:
            for item in (v2_items or []):
                view.add_item(item)
            return await target.send(view=view)
        return await target.send(**fallback_kw)
    except Exception as _ex:
        # V2 мог не пройти (клиент/канал не поддержал) — вторая попытка
        # уже классическим эмбедом
        _log.warning("send_v2_or_embed(): V2 не прошёл (%s), отправляю эмбед", _ex)
        if view is not None:
            try:
                return await target.send(**fallback_kw)
            except Exception as _ex2:
                _log.error("send_v2_or_embed(): и фолбек не прошёл: %s", _ex2)
        raise
