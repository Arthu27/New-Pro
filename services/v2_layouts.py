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
    if selected_uid and pending_label:
        return f'участник <@{selected_uid}> · «{pending_label}»'
    if selected_uid:
        return f'участник <@{selected_uid}>'
    if pending_label:
        return f'Выберите участника · «{pending_label}»'
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
                         footer: str = '',
                         target_select=None, action_select=None,
                         show_banner: bool = None):
    """Финальный /modpanel: шапка + баннер + два чёрных блока с селектами."""
    if not V2_AVAILABLE:
        return None
    if show_banner is None:
        show_banner = SHOW_MENU_BANNER
    items = []
    # 1) шапка
    head = [
        _ui.TextDisplay('# Панель модерации\n-# HAKUMO'),
        _ui.Separator(spacing=SeparatorSpacing.large),
    ]
    if show_banner and banner_filename:
        head.append(_gallery(banner_filename))
    if status:
        head.append(_ui.TextDisplay(status))
    items.append(black_container(*head))
    # 2) участник — заголовок + селект (placeholder отдельный, без дубля)
    if target_select is not None:
        row = _ui.ActionRow()
        row.add_item(target_select)
        items.append(black_container(
            _ui.TextDisplay('**Участник**'),
            row,
        ))
    # 3) действие
    if action_select is not None:
        row = _ui.ActionRow()
        row.add_item(action_select)
        items.append(black_container(
            _ui.TextDisplay('**Действие**'),
            row,
        ))
    return items


def build_modpanel_container(*, banner_filename: str, status: str,
                             footer: str = '',
                             target_select=None, action_select=None,
                             show_banner: bool = None):
    """Один общий Container (фолбек) — без футера."""
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


def build_event_panel_items(*, banner_filename: str, title: str, body: str,
                            phase_line: str = '', voice_line: str = '',
                            howto: str = '',
                            player_row=None, staff_row=None, staff_row2=None,
                            show_banner: bool = None, accent: int = None):
    """Публичная панель /event-panel — V2 как модпанель: баннер + чёрные блоки."""
    if not V2_AVAILABLE:
        return None
    if show_banner is None:
        show_banner = SHOW_MENU_BANNER
    items = []
    head_bits = [
        _ui.TextDisplay(f'# {title}\n-# HAKUMO · EVENTS'),
        _ui.Separator(spacing=SeparatorSpacing.large),
    ]
    if show_banner and banner_filename:
        head_bits.append(_gallery(banner_filename))
    status_parts = []
    if phase_line:
        status_parts.append(phase_line)
    if voice_line:
        status_parts.append(voice_line)
    if body:
        status_parts.append(body)
    if howto:
        status_parts.append(howto)
    if status_parts:
        head_bits.append(_ui.TextDisplay('\n'.join(status_parts)[:3900]))
    items.append(black_container(*head_bits, accent=accent))

    if player_row is not None:
        items.append(black_container(
            _ui.TextDisplay('**Игроки**\n-# записаться в список'),
            player_row,
            accent=accent,
        ))
    if staff_row is not None:
        items.append(black_container(
            _ui.TextDisplay('**Ведущие**\n-# анонс · старт · запись'),
            staff_row,
            accent=accent,
        ))
    if staff_row2 is not None:
        items.append(black_container(
            _ui.TextDisplay('**Ещё**\n-# список · финиш'),
            staff_row2,
            accent=accent,
        ))
    return items


def build_event_start_items(*, title: str, body: str, footer: str = '',
                            accent: int = 0xF0A202):
    """Карточка «▶ Старт» — V2-анонс начала игры."""
    if not V2_AVAILABLE:
        return None
    children = [
        _ui.TextDisplay(f'# ▶ Старт · {title}'),
        _ui.Separator(spacing=SeparatorSpacing.large),
        _ui.TextDisplay(body[:3900]),
    ]
    if footer:
        children.append(_ui.Separator())
        children.append(_ui.TextDisplay(f'-# {footer}'[:500]))
    return [black_container(*children, accent=accent)]


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


def build_report_card_items(*, title: str, body: str = '', footer: str = '',
                            buttons=None, accent: int = None):
    """Карточка вызова модератора (/report) V2 — тот же чёрный блок,
    что у карточек апелляций (единый стиль панелей Hakumo)."""
    return build_appeal_card_items(title=title, body=body, footer=footer,
                                   buttons=buttons, accent=accent)


def build_notice_items(*, title: str, body: str = '', footer: str = '',
                       accent: int = None, brand: str = 'HAKUMO'):
    """ЛС/уведомление V2: чёрный (или статусный) контейнер, бренд, текст."""
    if not V2_AVAILABLE:
        return None
    children = []
    head = f'# {title}' if title else '# Уведомление'
    if brand:
        head = f'{head}\n-# {brand}'
    children.append(_ui.TextDisplay(head[:500]))
    children.append(_ui.Separator(spacing=SeparatorSpacing.large))
    if body:
        children.append(_ui.TextDisplay(str(body)[:3500]))
    if footer:
        children.append(_ui.Separator())
        children.append(_ui.TextDisplay(f'-# {footer}'[:500]))
    return [black_container(*children, accent=accent if accent is not None else _BLACK)]


def notice_layout_view(*, title: str, body: str = '', footer: str = '',
                       accent: int = None, brand: str = 'HAKUMO', timeout=None):
    items = build_notice_items(
        title=title, body=body, footer=footer, accent=accent, brand=brand)
    if not items:
        return None
    view = _ui.LayoutView(timeout=timeout)
    for it in items:
        view.add_item(it)
    return view


# Акценты ответов (как у success/error embed)
ACCENT_OK = 0x2ECC71
ACCENT_ERR = 0xE74C3C
ACCENT_INFO = 0x3498DB
ACCENT_WARN = 0xF39C12


def success_notice_view(title: str, body: str = '', *, footer: str = '',
                        brand: str = 'HAKUMO'):
    return notice_layout_view(
        title=f'✅ {title}' if title and not str(title).startswith('✅') else (title or 'Готово'),
        body=body, footer=footer, accent=ACCENT_OK, brand=brand, timeout=None)


def error_notice_view(body: str, title: str = 'Ошибка', *, footer: str = '',
                      brand: str = 'HAKUMO'):
    t = title or 'Ошибка'
    if not str(t).startswith('❌'):
        t = f'❌ {t}'
    return notice_layout_view(
        title=t, body=body, footer=footer, accent=ACCENT_ERR, brand=brand,
        timeout=None)


def info_notice_view(title: str, body: str = '', *, footer: str = '',
                     brand: str = 'HAKUMO'):
    t = title or 'Инфо'
    if not str(t).startswith('ℹ️'):
        t = f'ℹ️ {t}'
    return notice_layout_view(
        title=t, body=body, footer=footer, accent=ACCENT_INFO, brand=brand,
        timeout=None)


def notice_from_embed(embed):
    """Классический success/error/info Embed → V2 LayoutView (или None)."""
    if embed is None or not V2_AVAILABLE:
        return None
    import re
    desc = str(getattr(embed, 'description', None) or '').strip()
    title = str(getattr(embed, 'title', None) or '').strip()
    footer = ''
    try:
        ft = getattr(embed, 'footer', None)
        footer = str(getattr(ft, 'text', None) or '') if ft else ''
    except Exception:
        footer = ''
    # поля Embed → строки в body
    field_lines = []
    try:
        for f in list(getattr(embed, 'fields', None) or []):
            name = str(getattr(f, 'name', None) or '').strip()
            value = str(getattr(f, 'value', None) or '').strip()
            if name and value:
                field_lines.append(f'**{name}:** {value}')
            elif value:
                field_lines.append(value)
    except Exception:
        field_lines = []
    colour = getattr(embed, 'colour', None) or getattr(embed, 'color', None)
    try:
        accent = int(getattr(colour, 'value', None) or _BLACK)
    except Exception:
        accent = _BLACK
    body = desc
    # ## ✅ Title\nbody  /  ## ❌ Title\nbody
    m = re.match(r'^##\s*([✅❌ℹ️⚠️])?\s*(.+?)(?:\n+([\s\S]*))?$', desc)
    if m:
        mark, ttl, rest = m.group(1), (m.group(2) or '').strip(), (m.group(3) or '').strip()
        # убрать хвост-разделитель ✦
        if rest:
            rest = re.sub(r'\n*✦[^\n]*$', '', rest).strip()
        title = f'{mark} {ttl}'.strip() if mark else ttl
        body = rest
    elif title and desc:
        body = desc
    elif desc and not title:
        title = 'Сообщение'
        body = desc
    if field_lines:
        extra = '\n'.join(field_lines)
        body = f'{body}\n\n{extra}'.strip() if body else extra
    if not title and not body:
        return None
    # убрать DIVIDER из body
    if body:
        body = re.sub(r'\n*✦[^\n]*$', '', body).strip()
    return notice_layout_view(
        title=title or 'Сообщение', body=body or '', footer=footer,
        accent=accent, brand='HAKUMO', timeout=None)


def layout_plain_text(view) -> str:
    """Собрать видимый текст из LayoutView (для PanelInteraction / логов)."""
    if view is None:
        return ''
    parts = []

    def _walk(node):
        content = getattr(node, 'content', None)
        if isinstance(content, str) and content.strip():
            parts.append(content.strip())
        for ch in list(getattr(node, 'children', None) or []):
            _walk(ch)
        # Container / ActionRow иногда держат items
        for ch in list(getattr(node, 'items', None) or []):
            _walk(ch)

    try:
        for child in list(getattr(view, 'children', None) or []):
            _walk(child)
    except Exception:
        pass
    return '\n'.join(parts)


async def _send_interaction(interaction, kw):
    """response.send_message или followup — без смешения embed+LayoutView."""
    try:
        resp = getattr(interaction, 'response', None)
        done = bool(resp and callable(getattr(resp, 'is_done', None)) and resp.is_done())
        if done:
            await interaction.followup.send(**kw)
        else:
            await interaction.response.send_message(**kw)
        return True
    except Exception as ex:
        _log.info('respond_v2: %s — followup', ex)
        try:
            await interaction.followup.send(**kw)
            return True
        except Exception as ex2:
            _log.warning('respond_v2 followup: %s', ex2)
            return False


async def respond_v2(interaction, *, kind: str = 'info', title: str = '',
                     body: str = '', footer: str = '', ephemeral: bool = True,
                     brand: str = 'HAKUMO', fallback_embed=None):
    """Единый ответ на interaction: V2 notice, иначе классический embed.

    kind: 'ok' | 'err' | 'info' | 'warn'
    Никогда не шлёт embed= вместе с LayoutView.
    """
    kind = (kind or 'info').lower()
    if kind in ('ok', 'success', 'done'):
        view = success_notice_view(title or 'Готово', body, footer=footer, brand=brand)
        accent = ACCENT_OK
        mark = '✅'
    elif kind in ('err', 'error', 'fail'):
        view = error_notice_view(body, title=title or 'Ошибка', footer=footer, brand=brand)
        accent = ACCENT_ERR
        mark = '❌'
    elif kind in ('warn', 'warning'):
        view = notice_layout_view(
            title=f'⚠️ {title}' if title and '⚠️' not in title else (title or 'Внимание'),
            body=body, footer=footer, accent=ACCENT_WARN, brand=brand)
        accent = ACCENT_WARN
        mark = '⚠️'
    else:
        view = info_notice_view(title or 'Инфо', body, footer=footer, brand=brand)
        accent = ACCENT_INFO
        mark = 'ℹ️'

    kw = {'ephemeral': bool(ephemeral)}
    if view is not None and V2_AVAILABLE:
        kw['view'] = view
    else:
        if fallback_embed is not None:
            kw['embed'] = fallback_embed
        else:
            # локальный фолбек без циклического импорта embed_utils
            e = discord.Embed(color=accent)
            e.description = f'## {mark} {title or kind}\n{body or ""}'
            if footer:
                e.set_footer(text=footer[:200])
            kw['embed'] = e

    return await _send_interaction(interaction, kw)


async def reply_embed_v2(interaction, embed, *, ephemeral: bool = True):
    """Классический Embed → V2 LayoutView reply (без смеси embed+view)."""
    kw = {'ephemeral': bool(ephemeral)}
    v2 = None
    if V2_AVAILABLE and embed is not None:
        try:
            v2 = notice_from_embed(embed)
        except Exception as ex:
            _log.debug('reply_embed_v2 convert: %s', ex)
            v2 = None
    if v2 is not None:
        kw['view'] = v2
    elif embed is not None:
        kw['embed'] = embed
    else:
        return False
    ok = await _send_interaction(interaction, kw)
    if not ok and kw.get('view') is not None and embed is not None:
        return await _send_interaction(interaction, {
            'ephemeral': bool(ephemeral), 'embed': embed})
    return ok


async def reply_text_v2(interaction, text, *, kind: str = 'info',
                        title: str = '', ephemeral: bool = True):
    """Короткий текстовый ответ как V2 notice."""
    body = str(text or '').strip()
    if not title:
        if kind in ('err', 'error', 'fail'):
            title = 'Ошибка'
        elif kind in ('ok', 'success', 'done'):
            title = 'Готово'
        elif kind in ('warn', 'warning'):
            title = 'Внимание'
        else:
            title = 'Сообщение'
    return await respond_v2(
        interaction, kind=kind, title=title, body=body, ephemeral=ephemeral)


async def send_dm_v2(user, embed=None, *, view=None, content=None):
    """DM: V2 notice из embed, либо embed+view (кнопки апелляции и т.п.)."""
    send_kw = {}
    if content is not None:
        send_kw['content'] = content
    if view is not None:
        # обычный View с кнопками — только вместе с embed (не LayoutView)
        if embed is not None:
            send_kw['embed'] = embed
        send_kw['view'] = view
    elif embed is not None:
        v2 = notice_from_embed(embed) if V2_AVAILABLE else None
        if v2 is not None:
            send_kw['view'] = v2
        else:
            send_kw['embed'] = embed
    if not send_kw:
        return False
    await user.send(**send_kw)
    return True


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
