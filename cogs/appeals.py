# -*- coding: utf-8 -*-
"""Апелляции на баны (Appeals Cog)
=================================
Забаненный не может писать на сервере — бот пишет ему в ЛС.
Команды /апелляция больше НЕТ (владелец 2026-09-08: «она у нас в кнопке»).
Единственный путь подачи —
  • кнопка «Подать апелляцию» под карточкой о бане в ЛС бота.

Публичного меню в канале апелляций НЕТ (владелец 2026-09-24): канал —
только для карточек модерации после подачи из ЛС.

Модераторы получают карточку с select «Принять / Отклонить / Взять в работу»
(стикеры). Принят — пользователь разбанен и получает добрую весть в ЛС.
Отклонён — отказ в ЛС.

Хранилище — SQLite (GuildData 'appeals'). Select живёт в persistent view
и переживает рестарт бота. Метки — aware UTC.
"""
import io
import re
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from db import GuildData
from logger import get_logger
from services.appeal_card import (normalize_appearance, render_appeal_card,
                                  render_url_card, appeal_card_filename,
                                  fetch_remote_image)

log = get_logger("appeals")

UTC = timezone.utc
COLOR_PENDING = 0xFEE75C
COLOR_YES = 0x57F287
COLOR_NO = 0xED4245

MAX_TEXT = 500
MAX_PER_USER = 3  # открытых апелляций одновременно

# Роль куратора: её бот тегает в комнате апелляции при новой заявке
# (владелец 2026-09-08: «807030012301541377 это роль куратора…
# он будет тегать эту роль»). Это дефолт пинга; в панели «Апелляции →
# Правила подачи» можно выбрать другую роль. Старый сохранённый 0 —
# это ничей выбор (прежний дефолт «без пинга»), поэтому он тоже
# мигрирует на куратора: тег должен быть всегда.
CURATOR_PING_ROLE_ID = 807030012301541377

# антиспам и автоматика (меняются из панели «Апелляции → Правила подачи»)
DEFAULT_COOLDOWN_HOURS = 72   # пауза после отказа до новой подачи (0 = без паузы)
DEFAULT_STALE_HOURS = 24      # через сколько часов напоминать о висящей апелляции
DEFAULT_REJECT_TEMPLATES = [
    'Нарушение подтверждено — бан остаётся в силе',
    'Недостаточно доказательств',
    'Повторная подача без новых фактов',
    'Слишком рано — подайте позже',
]
MAX_TEMPLATES = 10
STALE_CHECK_EVERY = 1800  # сек — как часто проверять висящие апелляции

COLOR_CLOSED = 0x95A5A6   # автозакрытие (серый)
DM_FOOTER = 'Hakumo · Апелляции'


# ─── чистые функции (покрыты тестом) ────────────────────────────────────────

def empty_state():
    return {'next_id': 1, 'items': [], 'log_channel_id': 0}


def _clamp_hours(raw_val, default, lo, hi):
    """Часы из настроек: None/мусор → дефолт, число → зажать в [lo, hi]."""
    if raw_val is None:
        return default
    try:
        return max(lo, min(int(raw_val), hi))
    except (TypeError, ValueError):
        return default


def settings_of(state):
    """Настройки апелляций с дефолтами (старые state без settings не ломаются)."""
    raw = (state or {}).get('settings') or {}
    tpl = raw.get('reject_templates')
    if not isinstance(tpl, list) or not tpl:
        tpl = list(DEFAULT_REJECT_TEMPLATES)
    # тег при новой апелляции: 0/мусор/отсутствие — это НИЧЕЙ выбор
    # (прежний дефолт «без пинга»), а владелец 2026-09-08 велел тегать
    # куратора всегда → мигрируем на роль куратора. Строки тоже гасим:
    # '0' — truthy, простой `or None` её пропускал бы.
    try:
        _pid = int(raw.get('ping_role_id'))
    except (TypeError, ValueError):
        _pid = 0
    return {
        'cooldown_hours': _clamp_hours(raw.get('cooldown_hours'),
                                       DEFAULT_COOLDOWN_HOURS, 0, 720),
        'stale_hours': _clamp_hours(raw.get('stale_hours'),
                                    DEFAULT_STALE_HOURS, 1, 336),
        'reject_templates': [str(t)[:100] for t in tpl[:MAX_TEMPLATES]],
        'require_reply_on_reject': bool(raw.get('require_reply_on_reject')),
        # разовая ссылка в ЛС при принятии РЕАЛЬНОГО бана (изоляции не нужно —
        # человек и так на сервере). Выключено по умолчанию: авто-инвайт —
        # это потенциальная дыра, включает только владелец.
        'invite_on_unban': bool(raw.get('invite_on_unban')),
        'invite_channel_id': _clamp_hours(raw.get('invite_channel_id'), 0, 0,
                                          10 ** 25),
        # тег роли при новой апелляции (в комнату апелляции): по умолчанию —
        # роль куратора (владелец 2026-09-08), из панели можно выбрать другую;
        # авто-блок подачи после N отклонённых (0 = выключен)
        'ping_role_id': (min(_pid, 10 ** 25) if _pid > 0
                         else CURATOR_PING_ROLE_ID),
        'block_after_rejects': _clamp_hours(raw.get('block_after_rejects'),
                                            0, 0, 10),
        # эскалация: pending старше N часов → пинг старшей роли в канал
        # (0 часов = выключено; роль 0 = отметить эскалацию без упоминания)
        'escalate_hours': _clamp_hours(raw.get('escalate_hours'), 0, 0, 336),
        'escalate_role_id': _clamp_hours(raw.get('escalate_role_id'), 0, 0,
                                         10 ** 25),
    }


def _dm_embed(status, item, guild_name=''):
    """Фолбек-эмбед ЛС апелляций (если V2 недоступен)."""
    palette = {
        'submitted': (COLOR_PENDING, f'Апелляция #{item.get("id")} отправлена'),
        'accepted': (COLOR_YES, f'Апелляция #{item.get("id")} — принята'),
        'rejected': (COLOR_NO, f'Апелляция #{item.get("id")} — отклонена'),
        'closed': (COLOR_CLOSED, f'Апелляция #{item.get("id")} — закрыта'),
        'pending': (COLOR_PENDING, f'Апелляция #{item.get("id")} — на рассмотрении'),
    }
    color, title = palette.get(status, (COLOR_PENDING, f'Апелляция #{item.get("id")}'))
    embed = discord.Embed(title=title, color=color,
                          timestamp=datetime.now(UTC))
    embed.set_footer(text=f'{guild_name} · {DM_FOOTER}' if guild_name else DM_FOOTER)
    return embed


def _dm_v2_title(status, item):
    """Заголовок V2-карточки в ЛС."""
    n = item.get('id')
    return {
        'submitted': f'Апелляция #{n} отправлена',
        'accepted': f'Апелляция #{n} — принята',
        'rejected': f'Апелляция #{n} — отклонена',
        'closed': f'Апелляция #{n} — закрыта',
        'pending': f'Апелляция #{n} — на рассмотрении',
    }.get(status, f'Апелляция #{n}')


def _dm_v2_accent(status):
    """Акцент контейнера: чёрный для ожидания, зелёный/красный для исхода."""
    return {
        'submitted': 0x000000,
        'pending': 0x000000,
        'accepted': COLOR_YES,
        'rejected': COLOR_NO,
        'closed': COLOR_CLOSED,
    }.get(status, 0x000000)


async def _send_dm_notice(user, *, status, item, guild_name='', body=''):
    """ЛС апелляций: V2 чёрный/статусный блок + фолбек на эмбед."""
    embed = _dm_embed(status, item, guild_name)
    if body:
        embed.description = body
    footer = f'{guild_name} · {DM_FOOTER}' if guild_name else DM_FOOTER
    title = _dm_v2_title(status, item)
    try:
        from services.v2_layouts import V2_AVAILABLE, notice_layout_view
        if V2_AVAILABLE:
            view = notice_layout_view(
                title=title,
                body=body or '',
                footer=footer,
                accent=_dm_v2_accent(status),
                brand='HAKUMO',
                timeout=None)
            if view is not None:
                return await user.send(view=view)
    except Exception as _ex:
        log.debug('appeals dm V2: %s', _ex)
    return await user.send(embed=embed)


def _parse_ts(value):
    s = str(value or '').strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def _last_rejected(state, user_id):
    """Самая свежая отклонённая апелляция пользователя (или None)."""
    mine = [i for i in (state or {}).get('items', [])
            if int(i.get('user_id') or 0) == int(user_id)
            and i.get('status') == 'rejected' and i.get('reviewed_at')]
    mine.sort(key=lambda i: str(i.get('reviewed_at') or ''))
    return mine[-1] if mine else None


def cooldown_block(state, user_id, now):
    """Ошибка кулдауна после отказа или None (чистая функция, пишет тест).

    Реальное время дедлайна удобно человеку: «повторная подача — не раньше
    30.08 15:20 (отказ 27.08 15:20)». cooldown_hours=0 — пауза выключена.
    """
    hours = settings_of(state)['cooldown_hours']
    if hours <= 0:
        return None
    last = _last_rejected(state, user_id)
    if not last:
        return None
    rejected_at = _parse_ts(last.get('reviewed_at'))
    if rejected_at is None:
        return None
    from datetime import timedelta
    deadline = rejected_at + timedelta(hours=hours)
    if now >= deadline:
        return None
    fmt = lambda d: d.strftime('%d.%m %H:%M')  # noqa: E731
    return (f'отказ был {fmt(rejected_at)} — повторная подача '
            f'не раньше {fmt(deadline)}')


def auto_close_unbanned(state, user_id, now):
    """Ручной разбан в Discord: закрыть все ожидающие апелляции пользователя.

    Возвращает список закрытых (чистая функция). Панель показывает их
    в истории со статусом «закрыта (авто)».
    """
    closed = []
    for item in (state or {}).get('items', []):
        if int(item.get('user_id') or 0) != int(user_id):
            continue
        if item.get('status') != 'pending':
            continue
        item['status'] = 'auto_closed'
        item['reviewed_by'] = 'Discord (разбан вручную)'
        item['reviewed_at'] = now.isoformat()
        item['reply'] = None
        closed.append(item)
    return closed


def stale_pending(state, now, stale_hours=None):
    """Висящие апелляции старше stale_hours, о которых ещё не напоминали."""
    from datetime import timedelta
    hours = stale_hours if stale_hours is not None else settings_of(state)['stale_hours']
    edge = now - timedelta(hours=hours)
    out = []
    for item in pending_items(state or {'items': []}):
        if item.get('reminded_at'):
            continue
        created = _parse_ts(item.get('created_at'))
        if created is not None and created <= edge:
            out.append(item)
    return out


def pending_items(state):
    return [i for i in state['items'] if i['status'] == 'pending']


def user_pending(state, user_id):
    return [i for i in pending_items(state) if i['user_id'] == user_id]


def create_appeal(state, user_id, user_name, text, now):
    """Создать апелляцию. Возвращает (item, ошибка).

    Поля-доказательства нет (владелец 2026-09-07: «добавлять
    доказательство не нужно — убери его везде, мы пока это не
    используем»). В старых записях link мог остаться — его нигде
    не показываем.
    """
    text = str(text or '').strip()
    if len(text) < 10:
        return None, f'слишком коротко — напишите подробнее (минимум 10 символов)'
    if len(text) > MAX_TEXT:
        return None, f'максимум {MAX_TEXT} символов'
    # Дубликаты: пока апелляция на рассмотрении, новую не принимаем —
    # одна заявка, одна карточка (жалоба владельца на дубли 2026-09-06).
    pend = user_pending(state, user_id)
    if pend:
        return None, (f'апелляция #{pend[0]["id"]} уже на рассмотрении — '
                      'дождитесь по ней решения')
    if len(user_pending(state, user_id)) >= MAX_PER_USER:
        return None, f'уже есть {MAX_PER_USER} открытых — дождитесь решения'
    blocked = cooldown_block(state, user_id, now)
    if blocked:
        return None, blocked
    # авто-блок злостных подателей: N отклонённых — подача закрыта
    max_rej = settings_of(state)['block_after_rejects']
    if max_rej > 0:
        rejected_n = sum(
            1 for i in (state or {}).get('items', [])
            if int(i.get('user_id') or 0) == int(user_id)
            and i.get('status') == 'rejected')
        if rejected_n >= max_rej:
            return None, ('подача апелляций для вас закрыта модерацией '
                          f'сервера (отклонено: {rejected_n})')
    item = {
        'id': state['next_id'],
        'user_id': int(user_id),
        'user_name': str(user_name),
        'text': text,
        'status': 'pending',           # pending | accepted | rejected
        'created_at': now.isoformat(),
        'reviewed_by': None,
        'reviewed_at': None,
        'reply': None,
        'rating': None,               # оценка рассмотрения от автора: up/down
        'rating_comment': None,       # необязательный комментарий к оценке
        'claimed_by': None,           # {'id','name','at'} — кто взял в работу
        'escalated_at': None,         # когда эскалировали старшей роли
    }
    state['next_id'] += 1
    state['items'].append(item)
    return item, None


def resolve_appeal(state, appeal_id, accept, reviewer_name, now, reply=None):
    """Решение модератора. (item | None, причина_если_None)."""
    for item in state['items']:
        if item['id'] == appeal_id:
            if item['status'] != 'pending':
                return None, f'апелляция #{appeal_id} уже рассмотрена ({item["status"]})'
            item['status'] = 'accepted' if accept else 'rejected'
            item['reviewed_by'] = str(reviewer_name)
            item['reviewed_at'] = now.isoformat()
            item['reply'] = (reply or '').strip()[:300] or None
            return item, None
    return None, f'апелляция #{appeal_id} не найдена'


def get_appeal(state, appeal_id):
    for item in state['items']:
        if item['id'] == appeal_id:
            return item
    return None


def fmt_card_text(item):
    """Текст карточки для мод-канала (экран логики, покрыт тестом)."""
    body = f"**Апелляция #{item['id']}** от {item['user_name']} (`{item['user_id']}`)\n{item['text'][:400]}"
    return body


# ─── view: select со стикерами (кнопки не нужны) ───────────────────────────

def _appeal_staff_ok(interaction) -> bool:
    """Кто видит канал апелляций — может решать карточку.

    Discord уже режет видимость канала; ACL «Бан» здесь не ставим —
    иначе админы/кураторы без явного ban в панели получали тишину
    (владелец 2026-09-24: «не отвечает админа · всем кто видит канал»).
    """
    try:
        ch = getattr(interaction, 'channel', None)
        user = getattr(interaction, 'user', None)
        if ch is None or user is None:
            return True
        perms = ch.permissions_for(user)
        return bool(getattr(perms, 'view_channel', True))
    except Exception:
        return True


def _appeal_select_emoji(kind: str):
    try:
        from services.menu_emojis import emoji_for_appeal, schedule_ensure_menu_emojis
        # фон: при первом клике стикеры уже могут быть в кэше
        return emoji_for_appeal(kind)
    except Exception:
        return {'accept': '✅', 'reject': '❌', 'claim': '✋'}.get(kind, '❔')


class AppealView(discord.ui.LayoutView):
    """Persistent-select под апелляцией — Components V2 LayoutView.

    custom_id уникален для каждой апелляции ('appeal:menu:7'), поэтому
    view можно перерегистрировать после рестарта бота (on_ready ниже).
    Старые кнопки appeal:accept/reject/claim переживают через
    AppealLegacyButtonsView.
    """

    def __init__(self, cog, guild_id, appeal_id, *, title='', body='',
                 footer='', image_filename=None, accent=None,
                 banned_user_id=None):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.appeal_id = appeal_id
        self._card_title = title
        self._card_body = body
        self._card_footer = footer
        self._image_filename = image_filename
        self._accent = accent
        self._banned_user_id = banned_user_id
        self._resolved = False
        # Legacy button refs — только для старых карточек / тестов claim.
        self._accept_btn = discord.ui.Button(
            label='Принять', style=discord.ButtonStyle.success,
            custom_id=f'appeal:accept:{appeal_id}')
        self._accept_btn.callback = self._make_cb(True)
        self._reject_btn = discord.ui.Button(
            label='Отклонить', style=discord.ButtonStyle.danger,
            custom_id=f'appeal:reject:{appeal_id}')
        self._reject_btn.callback = self._make_cb(False)
        self._claim_btn_ref = discord.ui.Button(
            label='Взять в работу', style=discord.ButtonStyle.primary,
            emoji='✋', custom_id=f'appeal:claim:{appeal_id}')
        self._claim_btn_ref.callback = self._claim
        self._action_select = None
        self._rebuild_card()

    def _make_select(self):
        """Select «Принять / Отклонить / Взять в работу» со стикерами."""
        try:
            from services.menu_emojis import schedule_ensure_menu_emojis
            schedule_ensure_menu_emojis(getattr(self.cog, 'bot', None))
        except Exception:
            pass
        claim_label = 'Взять в работу'
        try:
            state = self.cog._load(self.guild_id)
            item = get_appeal(state, self.appeal_id) if state else None
            claim = (item or {}).get('claimed_by') or None
            if claim:
                claim_label = f'В работе: {str(claim.get("name") or "")[:40]}'
        except Exception:
            pass
        opts = [
            discord.SelectOption(
                label='Принять', value='accept',
                description='Разбанить и закрыть апелляцию',
                emoji=_appeal_select_emoji('accept')),
            discord.SelectOption(
                label='Отклонить', value='reject',
                description='Отказать в апелляции',
                emoji=_appeal_select_emoji('reject')),
            discord.SelectOption(
                label=claim_label[:100], value='claim',
                description='Взять в работу / снять с себя',
                emoji=_appeal_select_emoji('claim')),
        ]
        sel = discord.ui.Select(
            placeholder='Действие с апелляцией',
            options=opts,
            custom_id=f'appeal:menu:{self.appeal_id}',
            min_values=1, max_values=1)
        sel.callback = self._on_select
        self._action_select = sel
        return sel

    def _rebuild_card(self):
        """Собрать V2-карточку (select со стикерами; после решения — без меню)."""
        self.clear_items()
        select = None if self._resolved else self._make_select()
        from services.v2_layouts import V2_AVAILABLE, build_appeal_card_items, black_container
        if V2_AVAILABLE and (self._card_title or self._card_body or self._image_filename):
            items = build_appeal_card_items(
                title=self._card_title or f'Апелляция #{self.appeal_id}',
                body=self._card_body,
                footer=self._card_footer,
                image_filename=self._image_filename,
                select=select,
                accent=self._accent,
            )
            if items:
                for it in items:
                    self.add_item(it)
                return
        if self._resolved:
            return
        if V2_AVAILABLE and select is not None:
            from discord import ui as _ui
            row = _ui.ActionRow()
            row.add_item(select)
            self.add_item(black_container(row))
        elif select is not None:
            self.add_item(select)

    def apply_resolved(self, *, title, body, footer, accent):
        """Пересобрать карточку после решения — без меню."""
        self._resolved = True
        self._card_title = title
        self._card_body = body
        self._card_footer = footer
        self._accent = accent
        # картинку оставляем (attachment:// уже в сообщении)
        self._rebuild_card()

    def _claim_btn(self):
        return self._claim_btn_ref

    async def _on_select(self, interaction):
        """Маршрутизация select → claim / accept / reject."""
        values = []
        try:
            data = getattr(interaction, 'data', None) or {}
            values = list(data.get('values') or [])
        except Exception:
            values = []
        if not values:
            try:
                values = list(getattr(self._action_select, 'values', None) or [])
            except Exception:
                values = []
        action = (values[0] if values else '') or ''
        if action == 'claim':
            await self._claim(interaction)
        elif action == 'accept':
            await self._resolve(interaction, True)
        elif action == 'reject':
            await self._resolve(interaction, False)
        else:
            try:
                await interaction.response.send_message(
                    'Неизвестное действие — выберите пункт меню ещё раз.',
                    ephemeral=True)
            except Exception as _ex:
                log.debug('appeals: unknown select: %s', _ex)

    async def _claim(self, interaction):
        """Взять апелляцию в работу / снять с себя (повторный клик)."""
        # Кто видит канал — может взять в работу (без ACL «Бан»).
        if not _appeal_staff_ok(interaction):
            try:
                await interaction.response.send_message(
                    'Нет доступа к каналу апелляций.', ephemeral=True)
            except Exception:
                pass
            return
        gid = self.guild_id
        state = self.cog._load(gid)
        item = get_appeal(state, self.appeal_id)
        if item is None or item.get('status') != 'pending':
            await interaction.response.send_message(
                'Апелляция уже решена — в работу не взять.', ephemeral=True)
            return
        uid = str(interaction.user.id)
        claim = item.get('claimed_by') or None
        btn = self._claim_btn()
        if claim and str(claim.get('id')) != uid:
            await interaction.response.send_message(
                f'Уже в работе у **{claim.get("name")}** — '
                'дождитесь его решения.', ephemeral=True)
            return
        now = datetime.now(UTC).isoformat()
        if claim:
            item['claimed_by'] = None
            note = 'Вы сняли апелляцию с работы — очередь снова общая.'
            if btn is not None:
                btn.label = 'Взять в работу'
                btn.style = discord.ButtonStyle.primary
        else:
            item['claimed_by'] = {'id': uid, 'name': str(interaction.user),
                                  'at': now}
            note = 'Апелляция у вас в работе — решение ждут от вас.'
            if btn is not None:
                btn.label = f'В работе: {interaction.user.display_name}'
                btn.style = discord.ButtonStyle.secondary
        self.cog._save(gid, state)
        # «Взять в работу» = открыть канал апелляции забаненному: модератор
        # забрал дело — человек сразу видит комнату и может диалог (владелец
        # 2026-09-06). Снятие с работы канал не трогает.
        if not claim:
            _opened, _ch = False, None
            _guild = None
            try:
                _guild = self.cog.bot.get_guild(gid)
            except Exception as _ex:
                log.debug('appeals: guild на «взять в работу» #%s: %s',
                          item['id'], _ex)
            if _guild is not None:
                try:
                    _user = await self.cog.bot.fetch_user(int(item['user_id']))
                    _opened, _ch = await self.cog._open_appeal_channel(
                        _guild, _user)
                except Exception as _ex:
                    log.debug('appeals: канал по «взять в работу» #%s: %s',
                              item['id'], _ex)
            note += ('\n🚪 Канал апелляции открыт участнику — он уже видит '
                     'его на сервере.' if _opened == 'opened' else
                     '\n🚪 Участник забанен жёстко: доступ к каналу '
                     'апелляции включится сразу после разбана.' if _opened == 'deferred' else
                     '\n⚠ Канал апелляции не открылся: участник вне сервера '
                     'или у бота нет прав на канал.')
            # Владелец 2026-09-08: как только модератор взял апелляцию в
            # работу — в комнату приходит сообщение, КТО будет вести дело:
            # «вас будет обслуживать вот этот человек». Человек сразу
            # понимает, к кому обращаться с вопросами.
            if _opened == 'opened' and _ch is not None:
                try:
                    await _ch.send(
                        f"🤝 **Вас будет обслуживать:** "
                        f"{interaction.user.mention} "
                        f"({interaction.user.display_name}) — ваша апелляция "
                        f"у него в работе. Общайтесь здесь.")
                except Exception as _ann_ex:
                    log.debug('appeals: объявление в комнату #%s: %s',
                              item['id'], _ann_ex)
            elif _opened == 'deferred' and _ch is not None:
                # Жёстко забаненный: сообщение ляжет в комнату и будет
                # ждать его возвращения после разбана.
                try:
                    await _ch.send(
                        f"🤝 **Вас будет обслуживать:** "
                        f"{interaction.user.mention} "
                        f"({interaction.user.display_name}) — ваша апелляция "
                        f"у него в работе.")
                except Exception as _ann_ex:
                    log.debug('appeals: объявление (deferred) #%s: %s',
                              item['id'], _ann_ex)
        else:
            # Снятие с работы — честно сказать в комнате, что ведущий
            # сменился: человек не будет ждать ответа от ушедшего модера.
            try:
                _guild = self.cog.bot.get_guild(gid)
                if _guild is not None:
                    _room = await self.cog._appeal_channel(_guild)
                    if _room is not None:
                        await _room.send(
                            f"🌀 {interaction.user.display_name} больше не "
                            f"ведёт вашу апелляцию — она снова в общей "
                            f"очереди модерации.")
            except Exception as _uncl_ex:
                log.debug('appeals: снятие с работы, комната #%s: %s',
                          item['id'], _uncl_ex)
        # LayoutView нельзя смешивать с embed — Discord отклонит payload.
        # Select обновляем через пересборку карточки.
        self._card_footer = (
            f'В работе: {item["claimed_by"]["name"]}'
            if item.get('claimed_by') else 'Очередь общая')
        if self._card_title or self._card_body or self._image_filename:
            self._rebuild_card()
        banned_uid = int(item.get('user_id') or self._banned_user_id or 0)
        edit_kw = {
            'view': self,
            'embed': None,
            'embeds': [],
        }
        # V2: без content
        try:
            await interaction.response.edit_message(**edit_kw)
        except Exception as _ed:
            log.debug('appeals claim edit: %s', _ed)
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=True)
            except Exception as _df:
                log.debug('appeals claim defer: %s', _df)
        try:
            await interaction.followup.send(note, ephemeral=True)
        except Exception as _fu:
            log.debug('appeals claim followup: %s', _fu)

    def _make_cb(self, accept):
        async def _cb(interaction):
            await self._resolve(interaction, accept)
        return _cb

    async def _resolve(self, interaction, accept):
        # Кто видит канал апелляций — может решить карточку.
        # ACL «Бан» больше не блокирует (владелец 2026-09-24).
        gid = self.guild_id
        if not _appeal_staff_ok(interaction):
            try:
                await interaction.response.send_message(
                    'Нет доступа к каналу апелляций.', ephemeral=True)
            except Exception:
                pass
            return
        if accept:
            # Лимиты стаффа: принятие апелляции = разбан, расходка «unban»
            # (та же, что у /unban и панели). Проверяем ДО решения и только
            # на принятие: отклонение расходки не несёт. Раньше блок стоял
            # внутри except ACL-проверки и в нормальном пути не работал
            # вовсе (обход системы 2026-09-05).
            try:
                from services import staff_limits as _SL
                _guild = self.cog.bot.get_guild(gid)
                _ok, _deny = _SL.check_action(_guild, interaction.user, 'unban')
                if not _ok:
                    await interaction.response.send_message(f'🚫 {_deny}', ephemeral=True)
                    return
            except Exception as _ex:
                log.debug('appeals: limit accept: %s', _ex)
        state = self.cog._load(gid)
        item, err = resolve_appeal(state, self.appeal_id, accept,
                                   str(interaction.user), datetime.now(UTC))
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        self.cog._save(gid, state)
        unbanned = False
        member_present = False
        guild = self.cog.bot.get_guild(gid)
        if accept and guild is not None:
            # Дело «unban» + карточка «Блокировка снята» с автором решения —
            # ДО снятия роли: тогда слушатели логов видят свежее дело и не
            # рисуют дубль карточки без автора (владелец 2026-09-06).
            await self.cog._log_unban_decision(
                guild, item, interaction.user.id,
                interaction.user.display_name or str(interaction.user))
        if accept:
            if guild is not None:
                member = guild.get_member(item['user_id'])
                member_present = member is not None
                # мягкое возвращение: снять роль-бан, изоляцию и таймаут
                if member is not None:
                    try:
                        from services import punish_roles as PR
                        rid = PR.role_for(gid, 'ban')
                        role = guild.get_role(rid) if rid else None
                        if role is not None and role in getattr(member, 'roles', []):
                            await member.remove_roles(
                                role, reason=f'Апелляция #{item["id"]} принята')
                            PR.clear(gid, member.id, rid)
                    except Exception as _ex:
                        log.debug('appeals: снять роль бана: %s', _ex)
                    try:
                        mod = self.cog.bot.get_cog('Moderation')
                        if mod is not None:
                            await mod._unisolate_member(guild, member)
                            rest = getattr(mod, '_restore_roles_after_unban', None)
                            if callable(rest):
                                await rest(guild, member)
                        # снимаем ЛЮБОЙ мут (нативный таймаут + роли чат/войс-мута)
                        from services import mute_state
                        await mute_state.clear_all_mutes(guild, member)
                    except Exception as _ex:
                        log.debug('appeals: снятие изоляции/таймаута: %s', _ex)
                try:
                    await guild.unban(discord.Object(id=item['user_id']),
                                      reason=f'Апелляция #{item["id"]} принята')
                    unbanned = True
                except discord.NotFound:
                    unbanned = True  # уже разбанен руками
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    log.error('appeals: unban %s на %s не удался: %s',
                              item['user_id'], gid, _ex)
            if unbanned:  # расходка «unban» — в счётчик лимитов принявшего
                try:
                    from services import staff_limits as _SL
                    _SL.record_hit(gid, interaction.user.id, 'unban', 1)
                except Exception as _ex:
                    log.debug('appeals: record unban: %s', _ex)
        _settings = settings_of(state)
        invite_url = None
        if accept and unbanned and not member_present and guild is not None:
            invite_url = await self.cog._make_return_invite(guild, _settings)
        await self.cog._notify_user(
            item, accept, unbanned,
            cooldown_hours=_settings['cooldown_hours'],
            guild_name=str(getattr(guild, 'name', '') or ''),
            member_present=member_present, invite_url=invite_url,
            guild_id=gid)

        # Карточка остаётся: V2-блок обновляется — кто решил, исход, без кнопок.
        status = ('принята (разбанен)' if (accept and unbanned)
                  else ('принята' if accept else 'отклонена'))
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception as _ex:
            log.debug('appeals: defer решения: %s', _ex)
        await self.cog._finalize_appeal_card(
            guild, state, item,
            accept=accept, unbanned=unbanned,
            reviewer=interaction.user,
            message=interaction.message,
            view=self)
        _done_note = (f'Апелляция #{item["id"]} — {status}. '
                      'Карточка обновлена (кто принял и исход).')
        try:
            await interaction.followup.send(_done_note, ephemeral=True)
        except Exception as _ex2:
            log.debug('appeals: followup решения: %s', _ex2)


class AppealLegacyButtonsView(discord.ui.View):
    """Старые кнопки на карточках до перехода на select.

    custom_id совпадает (appeal:accept/reject/claim:N) — после рестарта
    бот продолжает отвечать на клики по старым сообщениям.
    """

    def __init__(self, cog, guild_id, appeal_id, *, snap=None):
        super().__init__(timeout=None)
        snap = dict(snap or {})
        self._inner = AppealView(
            cog, guild_id, appeal_id,
            title=str(snap.get('title') or ''),
            body=str(snap.get('body') or ''),
            footer=str(snap.get('footer') or ''),
            image_filename=snap.get('image') or None,
            accent=snap.get('accent'),
            banned_user_id=snap.get('user_id'),
        )
        # LayoutView уже собрал select — нам нужны только кнопки-колбэки.
        accept = discord.ui.Button(
            label='Принять', style=discord.ButtonStyle.success,
            custom_id=f'appeal:accept:{appeal_id}')
        accept.callback = self._inner._make_cb(True)
        reject = discord.ui.Button(
            label='Отклонить', style=discord.ButtonStyle.danger,
            custom_id=f'appeal:reject:{appeal_id}')
        reject.callback = self._inner._make_cb(False)
        claim = discord.ui.Button(
            label='Взять в работу', style=discord.ButtonStyle.primary,
            emoji='✋', custom_id=f'appeal:claim:{appeal_id}')
        claim.callback = self._inner._claim
        self.add_item(accept)
        self.add_item(reject)
        self.add_item(claim)


def _rate_cell(*lines):
    """Столбик оценки: полоска цитаты + кавычки — как таблица логов."""
    out, seen = [], set()
    for ln in lines:
        t = str(ln or '').strip()
        if not t or t in seen:
            continue
        seen.add(t)
        if not t.startswith(('<@', '<#', '<t:', '>', '"', 'http', '[')):
            t = '"' + t.replace('"', "'") + '"'
        if not t.startswith('>'):
            t = '> ' + t
        out.append(t)
    return '\n'.join(out) or '> —'


def _rate_outcome(item):
    return {'accepted': 'принята', 'rejected': 'отклонена'}.get(
        item.get('status'), item.get('status') or '—')


def _rate_verdict(verb):
    return 'помогли разобраться' if verb == 'up' else 'не помогли'


def _rate_prompt_embed(item, guild_name=''):
    """Карточка-меню в ЛС: таблица + селект «помогли / нет»."""
    e = discord.Embed(
        title='Оценка рассмотрения',
        color=COLOR_PENDING,
        timestamp=datetime.now(UTC))
    e.add_field(name='Апелляция', value=_rate_cell(f'#{item.get("id")}'),
                inline=False)
    e.add_field(name='Решение', value=_rate_cell(_rate_outcome(item)),
                inline=False)
    e.add_field(name='Как оценить',
                value='> Выберите в меню ниже — помогли или нет.',
                inline=False)
    e.set_footer(text=f'{guild_name} · {DM_FOOTER}' if guild_name else DM_FOOTER)
    return e


def _rate_thanks_embed(item, verb, comment=None):
    """После оценки: та же таблица, уже с вердиктом."""
    good = verb == 'up'
    e = discord.Embed(
        title='Спасибо за оценку',
        color=COLOR_YES if good else COLOR_NO,
        timestamp=datetime.now(UTC))
    e.add_field(name='Апелляция', value=_rate_cell(f'#{item.get("id")}'),
                inline=False)
    e.add_field(name='Оценка', value=_rate_cell(_rate_verdict(verb)),
                inline=False)
    if comment:
        e.add_field(name='Комментарий', value=_rate_cell(comment), inline=False)
    e.set_footer(text=DM_FOOTER)
    return e


def _rate_log_embed(guild, item, author, verb, comment=None):
    """Таблица в канал модеров: апелляция, текст, оценка, сроки."""
    from cogs.logs import _styled_log_embed, _person_block, _bullet, _ts_lines
    fields = [
        ('Апелляция', _rate_cell(f'#{item.get("id")}')),
        ('Автор', _person_block(author)),
        ('Решение', _rate_cell(_rate_outcome(item))),
        ('Оценка', _rate_cell(_rate_verdict(verb))),
    ]
    txt = str(item.get('text') or '').strip()
    if txt:
        fields.append(('Текст', _rate_cell(txt[:220])))
    reply = str(item.get('reply') or '').strip()
    if reply:
        fields.append(('Ответ модерации', _rate_cell(reply[:220])))
    who = item.get('reviewed_by')
    if who:
        fields.append(('Рассмотрел', _rate_cell(who)))
    if comment:
        fields.append(('Комментарий', _rate_cell(comment)))
    _c = _ts_lines(item.get('created_at'))
    if _c:
        fields.append(('Подана', _bullet(*_c)))
    _r = _ts_lines(item.get('reviewed_at'))
    if _r:
        fields.append(('Рассмотрена', _bullet(*_r)))
    av = None
    try:
        av = str(author.display_avatar.url)
    except Exception:
        av = None
    return _styled_log_embed(
        guild, 'mod', 'Оценка рассмотрения',
        fields=fields, thumbnail=av,
        color=COLOR_YES if verb == 'up' else COLOR_NO)


class AppealRateSelect(discord.ui.Select):
    """Меню оценки: помогли / не помогли. Как размут — один селект, не кнопки."""

    def __init__(self, cog, guild_id, appeal_id):
        options = [
            discord.SelectOption(
                label='Помогли разобраться', value='up',
                description='Рассмотрели честно, стало понятно',
                emoji='👍'),
            discord.SelectOption(
                label='Не помогли', value='down',
                description='Остались вопросы или обида',
                emoji='👎'),
        ]
        super().__init__(
            placeholder='Как прошло рассмотрение?',
            options=options, min_values=1, max_values=1,
            custom_id=f'app_rate:{guild_id}:{appeal_id}')
        self.cog = cog
        self.guild_id = guild_id
        self.appeal_id = appeal_id

    async def callback(self, interaction):
        state = self.cog._load(self.guild_id)
        item = get_appeal(state, self.appeal_id)
        if item is None or item['status'] not in ('accepted', 'rejected'):
            await interaction.response.send_message(
                'Эта апелляция ещё не решена — оценивать рано.',
                ephemeral=True)
            return
        if int(interaction.user.id) != int(item['user_id']):
            await interaction.response.send_message(
                'Оценить может только автор апелляции.', ephemeral=True)
            return
        if item.get('rating'):
            await interaction.response.send_message(
                'Оценка уже сохранена — спасибо.', ephemeral=True)
            return
        await interaction.response.send_modal(
            AppealRateModal(self.cog, self.guild_id, self.appeal_id,
                            self.values[0], self.view))


class AppealRateView(discord.ui.View):
    """Оценка рассмотрения: селект в ЛС, persistent после рестарта."""

    def __init__(self, cog, guild_id, appeal_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.appeal_id = appeal_id
        self.add_item(AppealRateSelect(cog, guild_id, appeal_id))


class AppealRateModal(discord.ui.Modal):
    """Оценка + необязательный комментарий «почему так».

    Открывается из кнопки AppealRateView (custom_id переживает рестарт,
    сама модалка привязана к живому клику — persistent ей не нужен).
    """

    def __init__(self, cog, guild_id, appeal_id, verb, src_view):
        super().__init__(title='Как прошло рассмотрение?')
        self.cog = cog
        self.guild_id = guild_id
        self.appeal_id = appeal_id
        self.verb = verb
        self.src_view = src_view
        self.comment = discord.ui.TextInput(
            label='Пара слов (необязательно)',
            placeholder='Что было хорошо — или что можно улучшить…',
            required=False, max_length=300,
            style=discord.TextStyle.paragraph)
        self.add_item(self.comment)

    async def on_submit(self, interaction):
        state = self.cog._load(self.guild_id)
        item = get_appeal(state, self.appeal_id)
        ok = (item is not None
              and item.get('status') in ('accepted', 'rejected')
              and not item.get('rating')
              and int(interaction.user.id) == int(item.get('user_id') or 0))
        if not ok:
            await interaction.response.send_message(
                'Оценка уже сохранена или апелляция недоступна.',
                ephemeral=True)
            return
        cm = str(self.comment.value or '').strip()[:300]
        item['rating'] = self.verb
        item['rating_comment'] = cm or None
        self.cog._save(self.guild_id, state)
        # Оценка рассмотрения — в канал владельца 1518751543329951904,
        # не в тред карточки и не в комнату апелляции (2026-09-06).
        try:
            _guild = self.cog.bot.get_guild(self.guild_id)
            _target = await self.cog._rating_channel(_guild) if _guild else None
            if _target is not None:
                try:
                    _re = _rate_log_embed(
                        _guild, item, interaction.user, self.verb, cm)
                    await _target.send(embed=_re)
                except Exception:
                    _verdict = _rate_verdict(self.verb)
                    _note = (f'Апелляция #{item["id"]}\n'
                             f'Оценка: "{_verdict}"')
                    if cm:
                        _note += f'\nКомментарий: "{cm}"'
                    await _target.send(_note[:500])
        except Exception as _ex:
            log.debug('appeals: отзыв #%s в канал: %s', self.appeal_id, _ex)
        thanks = _rate_thanks_embed(item, self.verb, cm)
        try:
            for child in self.src_view.children:
                child.disabled = True
            if interaction.message is not None:
                await interaction.message.edit(embed=thanks, view=self.src_view)
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.debug('appeals: скрыть меню оценки #%s: %s',
                      self.appeal_id, _ex)
        await interaction.response.send_message(embed=thanks, ephemeral=True)


class AppealModal(discord.ui.Modal):
    """Окно подачи: текст апелляции + ссылка-доказательство (необязательно)."""

    def __init__(self, cog, guild):
        super().__init__(title=f'Апелляция · {str(guild.name)[:30]}')
        self.cog = cog
        self.guild = guild
        self.text = discord.ui.TextInput(
            label='Текст апелляции',
            placeholder='Расскажите, что произошло (минимум 10 символов)',
            required=True, max_length=500, style=discord.TextStyle.paragraph)
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self.cog._is_banned(self.guild, interaction.user):
            await interaction.followup.send(
                ' Вы не забанены на этом сервере — апелляция не нужна.', ephemeral=True)
            return
        item, err = await self.cog._submit_appeal(
            interaction.user, self.guild, self.text.value)
        if err:
            await interaction.followup.send(f' Не получилось: {err}.', ephemeral=True)
            return
        from cogs.embed_utils import hakumo_embed as _ae
        await interaction.followup.send(
            embed=_ae('appeal', f'Апелляция #{item["id"]} отправлена',
                      f'Модераторы сервера **{self.guild.name}** уже получили её. '
                      'Ответ придёт сюда, в личку.'), ephemeral=True)


# (выбора сервера больше нет: апелляция всегда идёт на главный сервер
#  из конфигурации — см. _main_guild)

# ─── меню апелляций в канале (не в ЛС) ────────────────────────────────

MENU_CUSTOM_ID = 'appeal:menu:open'


class AppealChannelModal(discord.ui.Modal):
    """Окно подачи апелляции из меню в канале."""

    def __init__(self, cog, guild):
        super().__init__(title=f'Апелляция · {str(guild.name)[:30]}')
        self.cog = cog
        self.guild = guild
        self.text = discord.ui.TextInput(
            label='Что произошло?', style=discord.TextStyle.paragraph,
            placeholder='Расскажите свою версию — спокойно и по делу (от 10 символов)',
            required=True, max_length=500)
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        item, err = await self.cog._submit_channel_appeal(
            interaction.user, self.guild, self.text.value,
            channel=interaction.channel)
        if err:
            await interaction.followup.send(f'Не получилось: {err}.', ephemeral=True)
            return
        await interaction.followup.send(
            f'Апелляция **#{item["id"]}** принята — обсуждение в треде. '
            'Модераторы уже видят её.', ephemeral=True)


class AppealMenuSelect(discord.ui.Select):
    """Select «Подать апелляцию» в канале — УСТАРЕЛ (подача только в ЛС).

    View остаётся persistent, чтобы клик по старому меню не «молчал»:
    отвечаем подсказкой и просим бота снять витрину.
    """

    def __init__(self):
        super().__init__(
            custom_id=MENU_CUSTOM_ID,
            placeholder='Несогласны с наказанием? Подайте апелляцию…',
            min_values=1, max_values=1,
            options=[discord.SelectOption(
                label='Подать апелляцию', value='submit',
                description='Откроется окно: расскажите, что произошло',
                emoji='⚖️')])

    async def callback(self, interaction: discord.Interaction):
        # Публичное меню отключено (владелец 2026-09-24/25): только ЛС.
        try:
            await interaction.response.send_message(
                'Публичное меню апелляций отключено.\n'
                'Если вам выдали бан — откройте **ЛС с ботом** и нажмите '
                'кнопку **«Подать апелляцию»** под карточкой о бане.',
                ephemeral=True)
        except Exception:
            return
        cog = interaction.client.get_cog('Appeals')
        guild = interaction.guild
        if cog is not None and guild is not None:
            try:
                await cog._purge_appeal_menu(guild)
            except Exception as _ex:
                log.debug('appeals: purge после клика по старому меню: %s', _ex)


WEBHOOK_NAME = 'Апелляции Hakumo'
HOOK_USERNAME = '⚖ Апелляции'


async def _channel_webhook(channel):
    """Найти/создать вебхук бота в канале.

    Меню и карточки апелляций отправляются вебхуком бота (application-
    owned): красивое имя и аватар вместо сырого аккаунта, а кнопки/селекты
    работают как раньше — интеракции приходят боту. None — вебхук недоступен
    (нет прав или канал не поддерживает), тогда обычная отправка.
    """
    fetch = getattr(channel, 'webhooks', None)
    if fetch is None:
        return None
    try:
        hooks = await fetch()
    except Exception as _ex:
        log.debug('appeals: webhooks(%s): %s', channel, _ex)
        return None
    me_id = None
    try:
        me_id = channel.guild.me.id
    except Exception as _ex:
        log.debug('appeals: guild.me недоступен: %s', _ex)
    for h in hooks or ():
        try:
            if me_id is None or h.user is None or h.user.id == me_id:
                return h
        except Exception as _ex:
            log.debug('appeals: вебхук пропущен: %s', _ex)
    create = getattr(channel, 'create_webhook', None)
    if create is None:
        return None
    try:
        return await create(name=WEBHOOK_NAME)
    except Exception as _ex:
        log.debug('appeals: create_webhook: %s', _ex)
        return None


def _hook_avatar(guild):
    try:
        return guild.icon.url if guild.icon else None
    except Exception:
        return None


class AppealMenuView(discord.ui.View):
    """Обёртка меню (persistent — переживает рестарт)."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(AppealMenuSelect())


DM_APPEAL_CUSTOM_ID = 'appeal:dm:open'


class AppealDMView(discord.ui.View):
    """Кнопка «Подать апелляцию» в ЛС о бане (persistent).

    Живёт в личке бота под карточкой «Вам выдан бан» и переживает
    рестарт: ког достаём из interaction на клике, ссылку не держим.
    Единственный путь подачи из ЛС (владелец 2026-09-08: команда
    /апелляция убрана — «она у нас в кнопке»).
    """

    def __init__(self):
        super().__init__(timeout=None)
        btn = discord.ui.Button(
            label='Подать апелляцию', style=discord.ButtonStyle.success,
            emoji='⚖', custom_id=DM_APPEAL_CUSTOM_ID)
        btn.callback = self._open
        self.add_item(btn)

    async def _open(self, interaction):
        cog = None
        try:
            cog = interaction.client.get_cog('Appeals')
        except Exception as _ex:
            log.debug('appeals dm: cog: %s', _ex)
        if cog is None:
            await interaction.response.send_message(
                'Бот только что перезапускался — нажмите кнопку ещё раз.',
                ephemeral=True)
            return
        guild = cog._main_guild()
        if guild is None:
            await interaction.response.send_message(
                'Бот ещё не настроен: владелец не указал главный сервер. '
                'Напишите администрации сервера другим способом.',
                ephemeral=True)
            return
        try:
            banned = await cog._is_banned(guild, interaction.user)
        except Exception as _ex:
            log.debug('appeals dm: бан-чек: %s', _ex)
            banned = True   # не отпугнуть человека сбоем проверки
        if not banned:
            await interaction.response.send_message(
                f'Вы не забанены на сервере **{guild.name}** — '
                'апелляция не нужна.', ephemeral=True)
            return
        await interaction.response.send_modal(AppealModal(cog, guild))


# ─── ког ────────────────────────────────────────────────────────────────────

class Appeals(commands.Cog):
    """Приём и разбор апелляций забаненных пользователей."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('appeals')
        self._views_restored = False
        self._stale_started = False
        self._retention_started = False

    @commands.Cog.listener()
    async def on_ready(self):
        """Перерегистрировать кнопки ожидающих апелляций после рестарта."""
        if self._views_restored:
            return
        self._views_restored = True
        restored = 0
        for guild in list(self.bot.guilds):
            state = self._load(guild.id)
            for item in pending_items(state):
                if item.get('message_id'):
                    snap = item.get('card_v2') or {}
                    self.bot.add_view(
                        AppealView(
                            self, guild.id, item['id'],
                            title=str(snap.get('title') or ''),
                            body=str(snap.get('body') or ''),
                            footer=str(snap.get('footer') or ''),
                            image_filename=snap.get('image') or None,
                            accent=snap.get('accent'),
                            banned_user_id=item.get('user_id'),
                        ),
                        message_id=item['message_id'])
                    # старые карточки с кнопками — тот же custom_id
                    try:
                        self.bot.add_view(AppealLegacyButtonsView(
                            self, guild.id, item['id'], snap={
                                **snap, 'user_id': item.get('user_id')}))
                    except Exception as _leg:
                        log.debug('appeals: legacy buttons #%s: %s',
                                  item['id'], _leg)
                    restored += 1
        try:
            self.bot.add_view(AppealMenuView())
        except Exception as _ex:
            log.debug('appeals: меню-view: %s', _ex)
        # кнопка «Подать апелляцию» в ЛС о бане — глобальная регистрация
        try:
            self.bot.add_view(AppealDMView())
        except Exception as _ex:
            log.debug('appeals: dm-view: %s', _ex)
        rated = 0
        for guild in list(self.bot.guilds):
            state = self._load(guild.id)
            for item in state.get('items', []):
                if (item.get('status') in ('accepted', 'rejected')
                        and not item.get('rating')):
                    try:
                        self.bot.add_view(AppealRateView(self, guild.id, item['id']))
                        rated += 1
                    except Exception as _ex:
                        log.debug('appeals: rate-view #%s: %s', item['id'], _ex)
        if rated:
            log.info('appeals: восстановлено %s rate-view после рестарта', rated)
        if restored:
            log.info('appeals: восстановлено %s view после рестарта', restored)
        # починка карточек + убрать публичное меню из канала (подача только в ЛС)
        try:
            import asyncio

            async def _boot_fix():
                await asyncio.sleep(3)
                for g in list(self.bot.guilds):
                    try:
                        await self._purge_appeal_menu(g)
                    except Exception as _ex:
                        log.warning('appeals: boot purge menu %s: %s', g.id, _ex)
                    try:
                        await self._repair_appeal_cards(g)
                    except Exception as _ex:
                        log.warning('appeals: boot repair %s: %s', g.id, _ex)

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = self.bot.loop
            loop.create_task(_boot_fix())
        except Exception as _ex:
            log.warning('appeals: boot_fix task: %s', _ex)
        # цикл напоминаний о висящих апелляциях — один раз (on_ready бывает повторно)
        if not self._stale_started:
            self._stale_started = True
            try:
                import asyncio
                asyncio.get_event_loop().create_task(self._stale_loop())
            except Exception as _ex:
                log.debug('appeals: старт _stale_loop: %s', _ex)
        # хранение 14 дней: прогон при старте + суточный цикл
        if not self._retention_started:
            self._retention_started = True
            try:
                import asyncio

                async def _retention_boot():
                    await asyncio.sleep(8)
                    try:
                        from services.data_retention import run_retention
                        # сначала dry-run в лог, затем apply
                        run_retention(dry_run=True)
                        report = run_retention(dry_run=False)
                        log.info('appeals: retention startup ok days=%s parts=%s',
                                 report.get('days'), list((report.get('parts') or {})))
                    except Exception as _ex:
                        log.warning('appeals: retention startup: %s', _ex)
                    while True:
                        await asyncio.sleep(24 * 3600)
                        try:
                            from services.data_retention import run_retention
                            run_retention(dry_run=False)
                        except Exception as _ex:
                            log.warning('appeals: retention daily: %s', _ex)

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = self.bot.loop
                loop.create_task(_retention_boot())
            except Exception as _ex:
                log.debug('appeals: старт retention: %s', _ex)

    def _load(self, guild_id):
        return self.db.get(guild_id, 'state', empty_state()) or empty_state()

    def _save(self, guild_id, state):
        self.db.set(guild_id, 'state', state)

    def _mod_context(self, state, guild_id, user_id):
        """Строка «Контекст модератора» для карточки: наказания и апелляции юзера."""
        try:
            from services.appeal_context import build_context
            return build_context(state, guild_id, user_id)['line']
        except Exception as _ex:
            log.debug('appeals: контекст %s: %s', user_id, _ex)
            return 'история наказаний недоступна'

    async def _fire_panel_event(self, item):
        """Событие «новая апелляция» в колокольчик панели (веб).

        notify_event делает синхронный HTTP (webhook) и запись файла —
        уводим в рабочий поток, чтобы не блокировать event loop."""
        try:
            import asyncio as _asyncio
            from services.notification_dispatcher import notify_event
            _body = (f'#{item["id"]} от **{item["user_name"]}**: '
                     f'{item["text"][:120]}')
            await _asyncio.to_thread(notify_event, 'appeal_new', None, _body)
        except Exception as _ex:
            log.debug('appeals: событие колокольчика: %s', _ex)

    async def _ping_mod_role(self, target_channel, settings, item):
        """Тег роли при новой апелляции — по умолчанию куратора (см. константу).

        Роль существует на ЭТОМ сервере? Если гильда под рукой — сверяем:
        на «чужих» серверах без такой роли не рисуем @invalid-role и не
        дёргаем людей зря. Возвращает отправленное сообщение: его id
        запоминаем в карточке, чтобы после решения удалить и пинг —
        канал остаётся чистым."""
        rid = int(settings.get('ping_role_id') or 0)
        if not rid or target_channel is None:
            return None
        guild = getattr(target_channel, 'guild', None)
        get_role = getattr(guild, 'get_role', None)
        if callable(get_role) and get_role(rid) is None:
            log.debug('appeals: роли #%s нет на сервере — пинг пропущен', rid)
            return None
        try:
            return await target_channel.send(
                f'<@&{rid}> — новая апелляция **#{item.get("id")}** от '
                f'<@{item.get("user_id")}> ожидает решения.',
                allowed_mentions=discord.AllowedMentions(roles=True, users=True))
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.debug('appeals: пинг роли #%s: %s', item.get('id'), _ex)
            return None

    async def _escalate_overdue(self, guild, state, now):
        """Просроченные прямо в канал старшей роли (0 ч в настройках = выкл).

        Отмечаем item['escalated_at'], чтобы пинг был один раз; сохраняем
        state только если что-то эскалировали.
        """
        from datetime import timedelta
        settings = settings_of(state)
        hours = int(settings.get('escalate_hours') or 0)
        if hours <= 0:
            return 0
        edge = now - timedelta(hours=hours)
        due = []
        for item in pending_items(state):
            if item.get('escalated_at'):
                continue
            created = _parse_ts(item.get('created_at'))
            if created is not None and created <= edge:
                due.append(item)
        if not due:
            return 0
        channel, _ = await self._card_channel(guild, state)
        rid = int(settings.get('escalate_role_id') or 0)
        mention = f'<@&{rid}> ' if rid else ''
        n = 0
        for item in due:
            created = _parse_ts(item.get('created_at'))
            age_h = (max(0, int((now - created).total_seconds() // 3600))
                     if created is not None else 0)
            if channel is not None:
                try:
                    await channel.send(
                        f'{mention}эскалация: апелляция **#{item["id"]}** от '
                        f'**{item["user_name"]}** ждёт решения уже '
                        f'**{age_h} ч** — нужен взгляд старшего модератора.',
                        allowed_mentions=discord.AllowedMentions(roles=True))
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    log.debug('appeals: эскалация #%s: %s', item['id'], _ex)
            item['escalated_at'] = now.isoformat()
            n += 1
        self._save(guild.id, state)
        return n

    async def _make_return_invite(self, guild, settings):
        """Разовая ссылка-возврат для принятого РЕАЛЬНОГО Discord-бана.

        Работает только если владелец включил «разовые ссылки» в «Правилах
        подачи» и выбрал канал. 1 использование, 24 часа. Изоляции ссылка не
        нужна вовсе — звонок сюда не доходит.
        """
        try:
            if not settings.get('invite_on_unban'):
                return None
            cid = int(settings.get('invite_channel_id') or 0)
            channel = guild.get_channel(cid) if (guild and cid) else None
            if channel is None:
                return None
            inv = await channel.create_invite(
                max_uses=1, max_age=86400, unique=True,
                reason='Апелляция принята — возврат на сервер')
            return str(inv.url)
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.debug('appeals: инвайт возврата: %s', _ex)
            return None

    # ---- напоминания о висящих апелляциях ----
    async def _stale_loop(self):
        """Раз в STALE_CHECK_EVERY: напомнить в канал карточек о старых pending."""
        import asyncio
        await asyncio.sleep(30)   # дать боту прогреться после старта
        while True:
            try:
                for guild in list(self.bot.guilds):
                    now = datetime.now(UTC)
                    # эскалация: pending старше escalate_hours → старшей роли
                    state = self._load(guild.id)
                    await self._escalate_overdue(guild, state, now)
                    state = self._load(guild.id)
                    stale = stale_pending(state, now)
                    if not stale:
                        continue
                    channel, _ = await self._card_channel(guild, state)
                    for item in stale:
                        age_h = 0
                        created = _parse_ts(item.get('created_at'))
                        if created is not None:
                            age_h = max(0, int((now - created).total_seconds() // 3600))
                        if channel is not None:
                            try:
                                await channel.send(
                                    f'⚖ Апелляция **#{item["id"]}** от '
                                    f'**{item["user_name"]}** ждёт решения уже '
                                    f'**{age_h} ч** — загляните в очередь.')
                            except (discord.Forbidden, discord.HTTPException) as _ex:
                                log.debug('appeals: напоминание #%s: %s', item['id'], _ex)
                        # и человеку в ЛС: его апелляция не потерялась
                        try:
                            user = await self.bot.fetch_user(int(item['user_id']))
                            body = (
                                f'Ваша апелляция **#{item["id"]}** ждёт решения '
                                f'уже **{age_h} ч** — она не потерялась: '
                                'модераторам только что напомнили.')
                            await _send_dm_notice(
                                user, status='pending', item=item,
                                guild_name=str(guild.name), body=body)
                        except (discord.NotFound, discord.Forbidden,
                                discord.HTTPException) as _ex:
                            log.debug('appeals: ЛС-напоминание #%s: %s', item['id'], _ex)
                        item['reminded_at'] = now.isoformat()
                    self._save(guild.id, state)
            except Exception as _ex:
                log.debug('appeals: _stale_loop: %s', _ex)
            await asyncio.sleep(STALE_CHECK_EVERY)

    # ---- ручной разбан → апелляции закрываются сами ----
    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        """Разбанили руками (не кнопкой) — ожидающие апелляции теряют смысл."""
        try:
            state = self._load(guild.id)
            closed = auto_close_unbanned(state, user.id, datetime.now(UTC))
            if not closed:
                return
            self._save(guild.id, state)
            for item in closed:
                # карточка остаётся с пометкой «закрыта» (бан снят вручную)
                try:
                    await self._finalize_appeal_card(
                        guild, state, item,
                        accept=True, unbanned=True, closed=True,
                        reviewer='Discord (разбан вручную)')
                except Exception as _ex:
                    log.debug('appeals: автозакрытие карточки #%s: %s', item['id'], _ex)
                try:
                    await _send_dm_notice(
                        user, status='closed', item=item,
                        guild_name=str(guild.name),
                        body=('Бан снят вручную в Discord — решение по '
                              'апелляции больше не нужно. Доступ уже с вами.'))
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    log.debug('appeals: ЛС автозакрытия #%s: %s', item['id'], _ex)
            log.info('appeals: %s апелляций закрыто автоматически (ручной разбан %s на %s)',
                     len(closed), user.id, guild.id)
        except Exception as _ex:
            log.debug('appeals: on_member_unban: %s', _ex)

    # ---- меню апелляций в канале (ОТКЛЮЧЕНО: подача только в ЛС) ----
    async def publish_appeal_menu(self, channel):
        """Публичное меню в канале больше не публикуем.

        Владелец 2026-09-24: апелляция — только кнопка в ЛС после бана,
        канал апелляций не витрина. Если старое меню ещё висит — снимаем.
        """
        guild = getattr(channel, 'guild', None) if channel is not None else None
        if guild is not None:
            try:
                await self._purge_appeal_menu(guild)
            except Exception as _ex:
                log.debug('appeals: publish→purge: %s', _ex)
        return False, (
            'Меню в канал не публикуем: апелляцию подают кнопкой в ЛС '
            'после бана. Канал — только для карточек модерации.')

    async def _purge_appeal_menu(self, guild):
        """Удалить публичное меню «Подать апелляцию» из канала апелляций.

        Подача — только из ЛС. Чистим:
          1) сообщение из state.menu (если ещё есть);
          2) orphan-сообщения бота/вебхука в канале с жёлтым embed
             «⚖ Апелляции на наказания» или select custom_id appeal:menu:open
             (после Auto-Repair/рестарта старые ветки могли переопубликовать
             меню без записи в state — сканируем историю).
        """
        try:
            state = self._load(guild.id)
            menu = state.get('menu') or {}
            mid = int(menu.get('message_id') or 0)
            cid = int(menu.get('channel_id') or 0)
            deleted = 0
            channels = []

            async def _resolve_ch(channel_id):
                if not channel_id:
                    return None
                ch = guild.get_channel(channel_id) or self.bot.get_channel(channel_id)
                if ch is not None:
                    return ch
                fetch = getattr(guild, 'fetch_channel', None)
                if callable(fetch):
                    try:
                        return await fetch(int(channel_id))
                    except Exception:
                        return None
                return None

            # каналы-кандидаты: state.menu + ban_appeal + appeal_menu_channel
            seen = set()
            for raw_id in (cid,):
                ch = await _resolve_ch(raw_id)
                if ch is not None and int(ch.id) not in seen:
                    channels.append(ch)
                    seen.add(int(ch.id))
            try:
                ch_appeal = await self._appeal_channel(guild)
                if ch_appeal is not None and int(ch_appeal.id) not in seen:
                    channels.append(ch_appeal)
                    seen.add(int(ch_appeal.id))
            except Exception:
                pass
            try:
                from services.channel_routes import get_route
                for key in ('appeal_menu_channel', 'ban_appeal_channel'):
                    rid = int(get_route(guild.id, key) or 0)
                    ch = await _resolve_ch(rid)
                    if ch is not None and int(ch.id) not in seen:
                        channels.append(ch)
                        seen.add(int(ch.id))
            except Exception as _ex:
                log.debug('appeals: purge route channels: %s', _ex)

            # 1) точечное удаление по state.menu (это точно наше меню)
            if mid and cid:
                ch = await _resolve_ch(cid)
                if ch is not None:
                    try:
                        msg = await ch.fetch_message(mid)
                        try:
                            await msg.delete()
                            deleted += 1
                        except discord.NotFound:
                            pass
                    except discord.NotFound:
                        pass
                    except Exception as _ex:
                        log.debug('appeals: purge menu msg: %s', _ex)

            # 2) скан истории на orphan-меню
            for ch in channels:
                try:
                    deleted += await self._scan_purge_menu_in_channel(ch)
                except Exception as _ex:
                    log.debug('appeals: scan purge %s: %s', getattr(ch, 'id', '?'), _ex)

            if menu:
                state['menu'] = None
                self._save(guild.id, state)
            if deleted or menu:
                log.info('appeals: публичное меню снято guild=%s deleted=%s channels=%s',
                         guild.id, deleted, [c.id for c in channels])
            return True
        except Exception as _ex:
            log.warning('appeals: purge menu: %s', _ex)
            return False

    @staticmethod
    def _msg_looks_like_appeal_menu(msg) -> bool:
        """Жёлтый embed «Апелляции на наказания» или select appeal:menu:open."""
        try:
            for emb in (getattr(msg, 'embeds', None) or ()):
                title = str(getattr(emb, 'title', '') or '')
                desc = str(getattr(emb, 'description', '') or '')
                if 'Апелляции на наказания' in title:
                    return True
                if ('Несогласны с наказанием' in desc
                        and 'Подать апелляцию' in desc):
                    return True
        except Exception:
            pass
        try:
            for row in (getattr(msg, 'components', None) or ()):
                children = getattr(row, 'children', None)
                if children is None:
                    children = getattr(row, 'components', None) or ()
                for child in children or ():
                    cid = str(getattr(child, 'custom_id', '') or '')
                    if cid == MENU_CUSTOM_ID or cid.startswith('appeal:menu:'):
                        return True
                    for nested in (getattr(child, 'children', None) or ()):
                        ncid = str(getattr(nested, 'custom_id', '') or '')
                        if ncid == MENU_CUSTOM_ID or ncid.startswith('appeal:menu:'):
                            return True
        except Exception:
            pass
        return False

    async def _safe_delete_menu_msg(self, msg) -> bool:
        """Удалить меню апелляций: наше сообщение, вебхук или любой бот с этим embed."""
        if msg is None or not self._msg_looks_like_appeal_menu(msg):
            return False
        try:
            me = getattr(getattr(msg, 'guild', None), 'me', None)
            author = getattr(msg, 'author', None)
            webhook_id = getattr(msg, 'webhook_id', None)
            mine = bool(webhook_id)
            if me is not None and author is not None:
                if getattr(author, 'id', None) == getattr(me, 'id', None):
                    mine = True
            # Любой бот с этим точным меню — сносим (иначе orphan после смены кода)
            if author is not None and getattr(author, 'bot', False):
                mine = True
            if not mine:
                return False
            await msg.delete()
            return True
        except discord.NotFound:
            return True
        except Exception as _ex:
            log.warning('appeals: safe delete menu fail id=%s: %s',
                        getattr(msg, 'id', '?'), _ex)
            return False

    async def _scan_purge_menu_in_channel(self, channel, *, limit: int = 200) -> int:
        """Пройти историю канала и снять orphan-меню апелляций."""
        if channel is None or not hasattr(channel, 'history'):
            return 0
        deleted = 0
        try:
            async for msg in channel.history(limit=limit):
                if not self._msg_looks_like_appeal_menu(msg):
                    continue
                if await self._safe_delete_menu_msg(msg):
                    deleted += 1
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.warning('appeals: history scan %s: %s', getattr(channel, 'id', '?'), _ex)
        return deleted

    async def _ensure_appeal_menu(self, guild):
        """Совместимость: больше не публикуем — только чистим старое меню."""
        return await self._purge_appeal_menu(guild)

    async def _repair_appeal_cards(self, guild):
        """Починить карточки: select вместо мёртвых кнопок; решённые — без меню.

        После смены UI (кнопки → select) и сбоя V2-edit карточка оставалась
        «новой» хотя в базе уже rejected. Между правками — пауза, иначе
        Discord 429 и часть карточек не обновляется.
        """
        import asyncio
        state = self._load(guild.id)
        fixed = 0
        skipped = 0
        appeal_ch = None
        try:
            appeal_ch = await self._appeal_channel(guild)
        except Exception as _ex:
            log.debug('appeals: repair channel: %s', _ex)
            appeal_ch = None

        async def _fetch_with_retry(ch, mid, aid, tries=4):
            for attempt in range(tries):
                try:
                    return await ch.fetch_message(mid)
                except discord.NotFound:
                    return None
                except discord.HTTPException as _ex:
                    # 429 / краткий сбой сети
                    wait = 1.5 * (attempt + 1)
                    try:
                        if getattr(_ex, 'status', None) == 429:
                            wait = float(getattr(_ex, 'retry_after', None) or wait)
                    except Exception:
                        pass
                    log.debug('appeals: repair fetch #%s try=%s: %s (sleep %.1fs)',
                              aid, attempt + 1, _ex, wait)
                    await asyncio.sleep(wait)
                except Exception as _ex:
                    log.debug('appeals: repair fetch #%s: %s', aid, _ex)
                    return None
            return None

        for item in list(state.get('items') or []):
            mid = int(item.get('message_id') or 0)
            if not mid:
                continue
            ch_id = int(item.get('card_channel_id') or item.get('thread_id') or 0)
            ch = None
            if ch_id:
                ch = guild.get_channel(ch_id) or self.bot.get_channel(ch_id)
            if ch is None and appeal_ch is not None:
                ch = appeal_ch
                if not ch_id:
                    item['card_channel_id'] = int(appeal_ch.id)
            if ch is None:
                continue
            msg = await _fetch_with_retry(ch, mid, item.get('id'))
            if msg is None:
                skipped += 1
                continue
            status = str(item.get('status') or '')
            snap = dict(item.get('card_v2') or {})
            try:
                if status == 'pending':
                    view = AppealView(
                        self, guild.id, item['id'],
                        title=str(snap.get('title') or f'Апелляция #{item["id"]}'),
                        body=str(snap.get('body') or item.get('text') or ''),
                        footer=str(snap.get('footer') or ''),
                        image_filename=snap.get('image'),
                        accent=snap.get('accent'),
                        banned_user_id=item.get('user_id'),
                    )
                    await msg.edit(view=view)
                    fixed += 1
                elif status in ('accepted', 'rejected', 'closed'):
                    # решённая в базе, но на дискорде ещё «новая» с кнопками
                    await self._finalize_appeal_card(
                        guild, state, item,
                        accept=(status == 'accepted'),
                        unbanned=False,
                        reviewer=item.get('reviewed_by') or '—',
                        message=msg,
                        closed=(status == 'closed'))
                    fixed += 1
                # не долбить Discord подряд
                await asyncio.sleep(0.75)
            except discord.HTTPException as _ex:
                wait = float(getattr(_ex, 'retry_after', None) or 2.0)
                log.warning('appeals: repair #%s http: %s (sleep %.1fs)',
                            item.get('id'), _ex, wait)
                await asyncio.sleep(wait)
            except Exception as _ex:
                log.debug('appeals: repair #%s: %s', item.get('id'), _ex)
        if fixed or skipped:
            log.info('appeals: починено карточек %s (пропуск %s) на guild=%s',
                     fixed, skipped, guild.id)
        return fixed

    async def _appeal_channel(self, guild):
        """Канал апелляции: сохранённый маршрут → известный ID → fetch.

        resolve_route подставляет известный ID только если канал уже в
        кэше. После рестарта кэш пуст — тогда fetch_channel по известному
        ID всё равно находит комнату (владелец 2026-09-06: канал не
        открывался забаненному).
        """
        try:
            from services.channel_routes import (
                get_route as _get_route, KNOWN_CHANNELS as _KNOWN,
                channel_on_guild as _on_g)
            _cid = int(_get_route(guild.id, 'ban_appeal_channel') or 0)
            if not _cid:
                # known ID — только для основного сервера; на чужих гильдиях
                # fetch даёт «Guild ID resolved to a different guild».
                try:
                    from config import Config
                    main = int(getattr(Config, 'MAIN_GUILD_ID', 0) or 0)
                except Exception:
                    main = 0
                if main and int(getattr(guild, 'id', 0) or 0) != main:
                    return None
                _cid = int(_KNOWN.get('ban_appeal_channel') or 0)
        except Exception as _ex:
            log.debug('appeals: маршрут канала апелляции: %s', _ex)
            _cid = 0
            _on_g = None
        if not _cid:
            return None
        ch = None
        if callable(_on_g):
            ch = _on_g(guild, _cid)
        if ch is None:
            getter = getattr(guild, 'get_channel', None)
            ch = getter(_cid) if callable(getter) else None
        if ch is not None:
            return ch
        fetch = getattr(guild, 'fetch_channel', None)
        if callable(fetch):
            try:
                ch = await fetch(_cid)
                # защита: канал должен принадлежать этой гильдии
                g_id = int(getattr(getattr(ch, 'guild', None), 'id', 0) or 0)
                if g_id and g_id != int(getattr(guild, 'id', 0) or 0):
                    return None
                return ch
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as _ex:
                log.debug('appeals: fetch_channel %s: %s', _cid, _ex)
        return None

    async def _rating_channel(self, guild):
        """Куда писать оценку рассмотрения — канал владельца, не карточки."""
        try:
            from services.channel_routes import (
                APPEAL_RATING_CHANNEL_ID as _RID, channel_on_guild as _on_g)
        except Exception as _ex:
            log.debug('appeals: rating channel import: %s', _ex)
            return None
        if guild is None or not _RID:
            return None
        ch = _on_g(guild, _RID) if callable(_on_g) else None
        if ch is not None:
            return ch
        fetch = getattr(guild, 'fetch_channel', None)
        if callable(fetch):
            try:
                return await fetch(int(_RID))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException,
                    TypeError, ValueError) as _ex:
                log.debug('appeals: rating fetch_channel: %s', _ex)
        return None

    async def _as_member(self, guild, user):
        """Участник сервера: из ЛС приходит User, set_permissions хочет Member."""
        uid = getattr(user, 'id', None)
        getter = getattr(guild, 'get_member', None)
        if callable(getter) and uid:
            mem = getter(uid)
            if mem is not None:
                return mem
        fetch = getattr(guild, 'fetch_member', None)
        if callable(fetch) and uid:
            try:
                return await fetch(int(uid))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException,
                    TypeError, ValueError) as _ex:
                log.debug('appeals: fetch_member %s: %s', uid, _ex)
        return user

    async def _open_appeal_channel(self, guild, user, fallback_channel=None):
        """Открыть канал апелляции подавшему (до подачи он скрыт — владелец).

        Порядок канала: маршрут «Комната апелляции» / известный ID.
        Канал карточек сюда не подмешиваем — туда забаненного не пускаем
        (fallback_channel игнорируется нарочно).

        Два случая (владелец 2026-09-07: «заявка подается, но канал для
        участника не открывается»):
        1) Участник НА сервере (роль-«бан»/изоляция) — цель overwrite
           Member: доступ появляется сразу.
        2) Жёсткий бан — Member НЕ существует (get/fetch_member → нет),
           overwrite по User из ЛС Discord отвергает (NotFound, фикс
           2026-09-06). Ставим overwrite по discord.Object(user.id):
           Discord разрешает member-overwrite для тех, кто не на сервере —
           доступ «включится» сам, как только человека разбанят и он
           вернётся. До этого забаненный сервер не видит вовсе — это
           ограничение Discord, честно говорим об этом в ЛС.

        Возвращает (статус, канал): 'opened' — доступ уже виден,
        'deferred' — overwrite стоит, откроется после разбана,
        'failed' — не получилось (нет комнаты/прав).
        """
        _iso = await self._appeal_channel(guild)
        if _iso is None:
            log.error('appeals: канал апелляции не задан — некому открывать доступ (guild %s)', getattr(guild, 'id', '?'))
            return 'failed', None
        uid = getattr(user, 'id', None)
        member = None
        if uid:
            getter = getattr(guild, 'get_member', None)
            member = getter(uid) if callable(getter) else None
        if member is None:
            fetch = getattr(guild, 'fetch_member', None)
            if callable(fetch) and uid:
                try:
                    member = await fetch(int(uid))
                except (discord.NotFound, discord.Forbidden,
                        discord.HTTPException, TypeError, ValueError) as _ex:
                    log.debug('appeals: fetch_member %s: %s', uid, _ex)
        on_guild = member is not None
        if not on_guild:
            # жёсткий бан: Member нет и не будет — цель overwrite по ID
            member = user if uid is not None else None
        ow = discord.PermissionOverwrite(
            view_channel=True, send_messages=True,
            read_message_history=True, attach_files=True,
            embed_links=True, add_reactions=True)
        status = 'failed'

        async def _apply(target):
            """Один overwrite; цель — Member (на сервере) или Object(id)."""
            nonlocal status
            set_perm = getattr(target, 'set_permissions', None)
            if callable(set_perm):
                try:
                    if on_guild:
                        await set_perm(member, overwrite=ow)
                    else:
                        await set_perm(
                            discord.Object(id=int(uid)), overwrite=ow)
                    status = 'opened' if on_guild else 'deferred'
                    return True
                except (discord.Forbidden, discord.HTTPException,
                        TypeError) as _ex:
                    log.debug('appeals: set_permissions %s на %s: %s',
                              uid, getattr(target, 'id', '?'), _ex)
            return False

        # тред: add_user работает только для тех, кто УЖЕ на сервере;
        # забаненному добавление в тред невозможно — overwrite на родителя
        add_user = getattr(_iso, 'add_user', None)
        if callable(add_user) and on_guild:
            try:
                await add_user(member)
                status = 'opened'
            except (discord.Forbidden, discord.HTTPException,
                    TypeError) as _ex:
                log.debug('appeals: add_user %s: %s', uid, _ex)
        if await _apply(_iso):
            if status == 'deferred':
                # overwrite на самом треде для не-участника бессмысленен —
                # доступ решает родитель: дублируем туда
                parent = getattr(_iso, 'parent', None)
                if parent is not None:
                    await _apply(parent)
            return status, _iso
        parent = getattr(_iso, 'parent', None)
        if parent is not None and await _apply(parent):
            return status, _iso
        if status == 'opened':
            return status, _iso
        return 'failed', None

    async def _log_unban_decision(self, guild, item, mod_id, mod_name):
        """Дело «unban» + карточка «Блокировка снята» с автором решения.

        Раньше разбан по апелляции уходил в логи «системой» или вовсе без
        автора: аудита могло не быть, а дело не писалось никогда. Теперь
        пишем дело от имени принявшего модератора и даём единую карточку
        со столбиком автора (владелец 2026-09-06).
        """
        if guild is None:
            return None
        case_id = None
        try:
            mod_cog = self.bot.get_cog('Moderation')
            save = getattr(mod_cog, 'save_case', None)
            if callable(save):
                import asyncio as _aio
                case_id = await _aio.to_thread(
                    save, guild.id, 'unban', int(item['user_id']),
                    int(mod_id or 0), f'Апелляция #{item["id"]} принята',
                    str(mod_name or 'модератор'))
        except Exception as _ex:
            log.debug('appeals: дело разбана #%s: %s', item.get('id'), _ex)
        try:
            from cogs.logs import send_action_log

            class _Mod:
                bot = False
                id = int(mod_id or 0)
                name = str(mod_name or 'модератор')
                display_name = name
                mention = f'<@{id}>' if id else name

            user_obj = None
            try:
                user_obj = guild.get_member(int(item['user_id']))
            except Exception:
                user_obj = None
            if user_obj is None:
                try:
                    user_obj = await self.bot.fetch_user(int(item['user_id']))
                except (discord.NotFound, discord.Forbidden,
                        discord.HTTPException) as _ex:
                    log.debug('appeals: fetch автора #%s: %s', item.get('id'), _ex)
            if user_obj is not None:
                await send_action_log(
                    guild, 'unban', user_obj, _Mod(),
                    reason=f'Апелляция #{item["id"]} принята',
                    case_id=case_id)
        except Exception as _ex:
            log.debug('appeals: карточка разбана #%s: %s', item.get('id'), _ex)
        return case_id

    def _resolved_card_parts(self, item, *, accept, unbanned=False, reviewer=None,
                             closed=False):
        """title/body/footer/accent для карточки после решения."""
        if closed:
            status_word = 'закрыта'
            title = f'Апелляция #{item["id"]} — закрыта'
            outcome = '⏹ Закрыта · бан снят вручную'
            accent = COLOR_CLOSED
        else:
            status_word = 'принята' if accept else 'отклонена'
            title = f'Апелляция #{item["id"]} — {status_word}'
            outcome = ('✅ Принята' + (' · разбанен' if unbanned else '')
                       if accept else '❌ Отклонена')
            accent = COLOR_YES if accept else COLOR_NO
        snap = item.get('card_v2') or {}
        base_body = str(snap.get('body') or item.get('text') or '').strip()
        who = None
        if reviewer is not None and not isinstance(reviewer, str):
            mention = getattr(reviewer, 'mention', None)
            name = (getattr(reviewer, 'display_name', None)
                    or getattr(reviewer, 'name', None) or str(reviewer))
            who = f'{mention} ({name})' if mention else str(name)
        elif reviewer:
            who = str(reviewer)
        if not who:
            who = str(item.get('reviewed_by') or 'модератор')
        decision = [
            '**Решение**',
            outcome,
            f'Модератор: {who}',
        ]
        reviewed_at = item.get('reviewed_at')
        if reviewed_at:
            try:
                dt = _parse_ts(reviewed_at)
                if dt is not None:
                    decision.append(f'Когда: <t:{int(dt.timestamp())}:f>')
            except Exception:
                decision.append(f'Когда: {reviewed_at}')
        reply = (item.get('reply') or '').strip()
        if reply:
            decision.append(f'Комментарий: {reply}')
        body = (base_body + '\n\n' + '\n'.join(decision)).strip()[:3500]
        footer = f'решение вынесено · {status_word}'
        return title, body, footer, accent

    async def _finalize_appeal_card(self, guild, state, item, *, accept=False,
                                    unbanned=False, reviewer=None,
                                    message=None, view=None, closed=False):
        """Оставить карточку после решения: кто принял, исход, без кнопок.

        Пинг роли модерации убираем (он больше не нужен). Саму карточку
        не удаляем — в канале видно историю решения.
        """
        title, body, footer, accent = self._resolved_card_parts(
            item, accept=accept, unbanned=unbanned, reviewer=reviewer,
            closed=closed)
        # обновить снимок — после рестарта карточка останется «решённой»
        snap = dict(item.get('card_v2') or {})
        snap.update({
            'title': title, 'body': body, 'footer': footer,
            'accent': accent, 'resolved': True,
        })
        item['card_v2'] = snap
        try:
            gid = int(getattr(guild, 'id', 0) or item.get('guild_id') or 0)
            if gid and state is not None:
                self._save(gid, state)
        except Exception as _ex:
            log.debug('appeals: save после finalize: %s', _ex)

        edit_view = view
        if edit_view is None:
            edit_view = AppealView(
                self, int(getattr(guild, 'id', 0) or 0), item['id'],
                title=title, body=body, footer=footer,
                image_filename=snap.get('image'),
                accent=accent)
        if hasattr(edit_view, 'apply_resolved'):
            edit_view.apply_resolved(
                title=title, body=body, footer=footer, accent=accent)
        else:
            edit_view._card_title = title
            edit_view._card_body = body
            edit_view._card_footer = footer
            edit_view._accent = accent
            edit_view._resolved = True
            edit_view._rebuild_card()

        edit_kw = {'view': edit_view}
        # V2-карточки нельзя править через content/embeds — Discord 400,
        # карточка остаётся «новая» с кнопками (баг на #14).
        is_v2 = bool(item.get('card_v2')) or bool(
            getattr(message, 'flags', None)
            and getattr(message.flags, 'is_components_v2', False))
        if not is_v2:
            edit_kw.update({'content': None, 'embed': None, 'embeds': []})
        # 1) сообщение из интеракции
        edited = False
        if message is not None:
            try:
                await message.edit(**edit_kw)
                edited = True
            except Exception as _ex:
                log.warning('appeals: finalize edit message #%s: %s',
                            item.get('id'), _ex)
        if not edited:
            # 2) панель / автозакрытие / повтор после сбоя — fetch по message_id
            try:
                mid = int(item.get('message_id') or 0)
                ch_id = int(item.get('card_channel_id')
                            or item.get('thread_id') or 0)
                ch = None
                if guild is not None and ch_id:
                    ch = guild.get_channel(ch_id) or self.bot.get_channel(ch_id)
                if ch is None and message is not None:
                    ch = getattr(message, 'channel', None)
                if ch is not None and mid:
                    msg = await ch.fetch_message(mid)
                    # повторно: только view для V2
                    await msg.edit(view=edit_view)
                    edited = True
            except Exception as _ex:
                log.warning('appeals: finalize fetch/edit #%s: %s',
                            item.get('id'), _ex)
        if not edited:
            log.error('appeals: карточка #%s не обновлена после решения',
                      item.get('id'))

        # пинг роли больше не нужен — убираем только его
        try:
            await self._delete_appeal_ping(guild, item, message=message)
        except Exception as _ex:
            log.debug('appeals: ping cleanup: %s', _ex)
        return True

    async def _delete_appeal_ping(self, guild, item, message=None):
        """Удалить только пинг роли под карточкой (карточку не трогаем)."""
        ping_id = item.get('ping_message_id')
        if not ping_id:
            return False
        ch = None
        try:
            ch_id = int(item.get('card_channel_id') or 0)
            if guild is not None and ch_id:
                ch = guild.get_channel(ch_id) or self.bot.get_channel(ch_id)
            if ch is None and message is not None:
                ch = getattr(message, 'channel', None)
            if ch is None:
                return False
            msg = await ch.fetch_message(int(ping_id))
            await msg.delete()
            return True
        except Exception as _ex:
            log.debug('appeals: delete ping: %s', _ex)
            return False

    async def _delete_appeal_card(self, guild, state, item, message=None):
        """Удалить карточку решённой апелляции — вместе с пингом роли.

        Решение вынесено — сообщение с кнопками больше не нужно: канал
        апелляций остаётся чистым, история живёт в панели («Апелляции →
        История решений»). Карточку в собственной ветке убираем вместе
        с веткой; тихо переживаем ошибки — удаление не главное.
        """
        guild = guild or getattr(message, 'guild', None)
        state = state or {}

        async def _del_in(ch, mid):
            if ch is None or not mid:
                return False
            try:
                msg = await ch.fetch_message(int(mid))
                await msg.delete()
                return True
            except Exception as _ex:
                log.debug('appeals: удалить сообщение #%s: %s', mid, _ex)
                return False

        # 1) ветка, созданная под карточку, — уходит целиком
        try:
            tid = int(item.get('thread_id') or 0)
        except (TypeError, ValueError):
            tid = 0
        if tid:
            th = None
            msg_ch = getattr(message, 'channel', None) if message is not None else None
            if msg_ch is not None and getattr(msg_ch, 'id', 0) == tid:
                th = msg_ch
            elif guild is not None:
                th = self._guild_ch(guild, tid)
            if th is not None:
                try:
                    await th.delete()
                    if item.get('ping_message_id'):
                        await _del_in(self._guild_ch(guild, item.get('card_channel_id'))
                                      if guild is not None else None,
                                      item.get('ping_message_id'))
                    return True
                except Exception as _ex:
                    log.debug('appeals: удалить ветку #%s: %s', tid, _ex)
        # 2) само сообщение карточки — из клика или по сохранённым id
        deleted = False
        if message is not None:
            _del = getattr(message, 'delete', None)
            if callable(_del):
                try:
                    await _del()
                    deleted = True
                except Exception as _ex:
                    log.debug('appeals: удалить карточку по клику: %s', _ex)
        if not deleted and guild is not None:
            try:
                cid = int(item.get('card_channel_id') or 0)
            except (TypeError, ValueError):
                cid = 0
            ch = self._guild_ch(guild, cid) if cid else self._log_channel(guild, state)
            deleted = await _del_in(ch, item.get('message_id'))
        # 3) пинг роли под карточкой — тоже мусор после решения
        if guild is not None and item.get('ping_message_id'):
            try:
                cid = int(item.get('card_channel_id') or 0)
            except (TypeError, ValueError):
                cid = 0
            ch = self._guild_ch(guild, cid) if cid else self._log_channel(guild, state)
            await _del_in(ch, item.get('ping_message_id'))
        return deleted

    def _dm_channel_line(self, opened, channel):
        """Строка про канал для ЛС-подтверждения: имя канала, не абстракция.

        opened: 'opened' | 'deferred' | 'failed' (см. _open_appeal_channel).
        """
        if opened == 'opened':
            name = getattr(channel, 'name', '') or 'канал апелляции'
            return (f'Канал **#{name}** на сервере открыт для вас — карточка '
                    'видна там. Ответ придёт в личные сообщения — обычно в '
                    'течение суток.')
        if opened == 'deferred':
            name = getattr(channel, 'name', '') or 'канал апелляции'
            return (f'Вы забанены, поэтому сервер пока не виден. Канал '
                    f'**#{name}** откроется для вас автоматически — сразу, '
                    'как только модераторы примут апелляцию и снимут бан. '
                    'Ответ придёт в личные сообщения.')
        return ('Канал апелляции открыть не получилось (боту нужны права '
                'управления каналом) — модераторы увидят карточку и напишут '
                'вам. Ответ придёт в личные сообщения.')

    def _guild_ch(self, guild, cid):
        """Канал или ветка по ID (пикер логов/апелляций отдаёт оба)."""
        if not cid or guild is None:
            return None
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            return None
        fn = getattr(guild, 'get_channel_or_thread', None)
        if callable(fn):
            ch = fn(cid)
            if ch is not None:
                return ch
        ch = guild.get_channel(cid)
        if ch is not None:
            return ch
        getter = getattr(guild, 'get_thread', None)
        return getter(cid) if callable(getter) else None

    def _strip_appeal_embed_texts(self, embed):
        """Тексты живут в PNG: иначе Discord рисует их НАД картинкой."""
        embed.title = None
        embed.description = None
        try:
            embed.clear_fields()
        except Exception as _ex:
            log.debug('appeal embed clear_fields: %s', _ex)
        try:
            embed.remove_author()
        except Exception as _ex:
            log.debug('appeal embed remove_author: %s', _ex)
        try:
            embed.remove_footer()
        except Exception as _ex:
            log.debug('appeal embed remove_footer: %s', _ex)

    async def _paint_appeal_card(self, embed, item, appearance):
        """Картинка карточки: авто / URL-композит (фото сверху, надписи ниже).

        Возвращает discord.File или None. Когда PNG собран, поля эмбеда
        очищаем — Discord всегда кладёт set_image под title/fields.
        """
        file = None
        try:
            if appearance.get('mode') == 'url' and appearance.get('url'):
                data, fname = await fetch_remote_image(appearance['url'])
                if data:
                    comp = render_url_card(
                        data, appeal_id=item['id'],
                        user_name=item['user_name'], text=item['text'],
                        theme=appearance.get('theme'))
                    payload, name = ((comp, appeal_card_filename(item['id']))
                                     if comp else (data, fname))
                    file = discord.File(io.BytesIO(payload), filename=name)
                    embed.set_image(url=f'attachment://{name}')
                    if comp:
                        self._strip_appeal_embed_texts(embed)
                else:
                    log.warning('appeals: своя картинка #%s не скачалась (%s) — '
                                'показываю ссылкой', item['id'], fname)
                    embed.set_image(url=appearance['url'])
            elif appearance.get('mode') == 'auto':
                import asyncio as _aio
                from functools import partial as _partial
                png = await _aio.to_thread(_partial(
                    render_appeal_card,
                    appeal_id=item['id'], user_name=item['user_name'],
                    text=item['text'],
                    theme=appearance.get('theme')))
                if png:
                    fn = appeal_card_filename(item['id'])
                    file = discord.File(io.BytesIO(png), filename=fn)
                    embed.set_image(url=f'attachment://{fn}')
                    self._strip_appeal_embed_texts(embed)
        except Exception as _ex:
            log.debug('appeals: карточка-картинка #%s: %s', item.get('id'), _ex)
        return file

    def _appeal_card_text_from_embed(self, embed):
        """Собрать title/body/footer ДО paint (paint может очистить embed)."""
        body_bits = []
        if getattr(embed, 'description', None):
            body_bits.append(str(embed.description))
        for field in getattr(embed, 'fields', None) or []:
            body_bits.append(f'**{field.name}**\n{field.value}')
        author = getattr(embed, 'author', None)
        if author and getattr(author, 'name', None):
            body_bits.insert(0, f'от **{author.name}**')
        footer = ''
        try:
            footer = str(getattr(getattr(embed, 'footer', None), 'text', '') or '')
        except Exception:
            footer = ''
        accent = None
        accent = 0x000000  # чёрный акцент как у /modpanel
        return {
            'title': str(getattr(embed, 'title', None) or ''),
            'body': '\n\n'.join(body_bits)[:3500],
            'footer': footer,
            'accent': accent,
        }

    def _appeal_v2_send_kw(self, guild_id, item, embed, card_file=None,
                           *, snap=None):
        """kwargs для отправки карточки апелляции: V2 LayoutView (+файл).

        content тегает забаненного — модератор может кликнуть и проверить
        профиль (владелец 2026-09-24).
        """
        snap = dict(snap or self._appeal_card_text_from_embed(embed))
        image_name = getattr(card_file, 'filename', None) if card_file else None
        snap['image'] = image_name
        banned_uid = int(item.get('user_id') or 0)
        # в теле карточки — кликабельный тег, не голый ник
        body = str(snap.get('body') or '')
        if banned_uid and f'<@{banned_uid}>' not in body:
            who = f'<@{banned_uid}>'
            name = str(item.get('user_name') or '')
            mention_line = f'от {who}' + (f' (**{name}**)' if name else '')
            body = (mention_line + ('\n\n' + body if body else '')).strip()
            snap['body'] = body[:3500]
        view = AppealView(
            self, guild_id, item['id'],
            title=snap.get('title') or f'Апелляция #{item["id"]}',
            body=snap.get('body') or '',
            footer=snap.get('footer') or '',
            image_filename=image_name,
            accent=snap.get('accent'),
            banned_user_id=banned_uid or None,
        )
        kw = {'view': view}
        if card_file is not None:
            kw['file'] = card_file
        if banned_uid:
            # V2 запрещает content вместе с LayoutView — тег уже в body;
            # отдельный пинг шлёт _ping_mod_role.
            pass
        # снимок для add_view после рестарта — иначе claim сотрёт карточку
        item['card_v2'] = {
            'title': snap.get('title') or '',
            'body': snap.get('body') or '',
            'footer': snap.get('footer') or '',
            'image': image_name,
            'accent': snap.get('accent'),
            'user_id': banned_uid or None,
        }
        return kw

    
    async def _submit_channel_appeal(self, user, guild, text, channel=None):
        """Апелляция из меню в канале: карточка в отдельном треде."""
        guild_id = guild.id
        state = self._load(guild_id)
        item, err = create_appeal(state, user.id, str(user), text,
                                  datetime.now(UTC))
        if err:
            return None, err
        self._save(guild_id, state)

        if channel is None:
            try:
                from services.channel_routes import get_route
                cid = int(get_route(guild.id, 'appeal_menu_channel') or 0)
                channel = self._guild_ch(guild, cid) if cid else None
            except Exception:
                channel = None
        if channel is None:
            menu = state.get('menu') or {}
            cid = int(menu.get('channel_id') or 0)
            channel = self._guild_ch(guild, cid) if cid else None
        if channel is None:
            channel, _ = await self._card_channel(guild, state)
        embed = discord.Embed(
            title=f'Апелляция #{item["id"]} — новая',
            description=item['text'],
            color=COLOR_PENDING, timestamp=datetime.now(UTC))
        embed.set_author(name=str(user),
                         icon_url=user.display_avatar.url
                         if getattr(user, 'display_avatar', None) else None)
        embed.add_field(name='Участник',
                        value=f'{user.mention} · `{user.id}`', inline=False)
        embed.add_field(name='Контекст модератора',
                        value=self._mod_context(state, guild.id, user.id),
                        inline=False)
        embed.set_footer(text=f'appeal #{item["id"]} · решение — меню под карточкой')
        card_file = None
        snap = self._appeal_card_text_from_embed(embed)
        try:
            appearance = normalize_appearance(state.get('appearance'))
            card_file = await self._paint_appeal_card(embed, item, appearance)
        except Exception as _ex:
            log.debug('appeals: карточка-картинка #%s: %s', item['id'], _ex)

        # Куда падает карточка: «всё сюда, кроме логов» — сама комната
        # апелляции, где и кнопки, и обсуждение (владелец 2026-09-06).
        # Нет комнаты — запасной путь прежний: канал карточек, заявка
        # уходит в собственную ветку; меню-канал — последний запасной.
        target, use_thread = await self._card_channel(guild, state)
        if target is None:
            target = channel
            use_thread = True
        if target is not None:
            name = f'Апелляция #{item["id"]} · {str(user)[:40]}'
            send_kw = self._appeal_v2_send_kw(
                guild_id, item, embed, card_file, snap=snap)
            card = None
            if use_thread:
                try:
                    thread = await target.create_thread(
                        name=name, type=discord.ChannelType.public_thread)
                    card = await thread.send(**send_kw)
                    item['thread_id'] = thread.id
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    # Нет права «Создавать публичные ветки» — НЕ теряем
                    # апелляцию: карточка с кнопками ложится прямо в канал.
                    log.warning('appeals: тред #%s не создан (%s) — карточка в канал',
                                item['id'], _ex)
                    try:
                        card = await target.send(**send_kw)
                    except (discord.Forbidden, discord.HTTPException) as _ex2:
                        log.error('appeals: карточка #%s не ушла и в канал: %s',
                                  item['id'], _ex2)
            else:
                # комната апелляции: карточка прямо в канал — это дом заявки
                try:
                    card = await target.send(**send_kw)
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    log.error('appeals: карточка #%s не ушла в комнату: %s',
                              item['id'], _ex)
            if card is not None:
                item['message_id'] = card.id
                item['thread_url'] = card.jump_url
                # где лежит карточка (для удаления после решения) + пинг
                item['card_channel_id'] = getattr(target, 'id', None)
                ping = await self._ping_mod_role(target, settings_of(state), item)
                item['ping_message_id'] = getattr(ping, 'id', None)
                await self._fire_panel_event(item)
        # Канал апелляции открываем автору ТОЛЬКО теперь: владелец просил,
        # чтобы канал был виден не в момент бана, а после подачи апелляции
        # (2026-09-05). До подачи у человека все каналы закрыты. Канал
        # карточек не открываем — туда забаненного не пускаем.
        ch_opened, ch_ref = await self._open_appeal_channel(guild, user,
                                                            fallback_channel=target)
        self._save(guild_id, state)
        try:
            body = (
                f'Модераторы сервера **{guild.name}** уже получили вашу '
                f'апелляцию.\n\n'
                + self._dm_channel_line(ch_opened, ch_ref))
            await _send_dm_notice(user, status='submitted', item=item,
                                  guild_name=str(guild.name), body=body)
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.debug('appeals: ЛС подтверждения #%s не дошло: %s', item['id'], _ex)
        return item, None

    # ---- подача (ЛС боту) ----
    async def _submit_appeal(self, user, guild, text):
        """Общая точка создания апелляции: проверка бана, лимит, карточка."""
        guild_id = guild.id
        state = self._load(guild_id)
        item, err = create_appeal(state, user.id, str(user), text,
                                  datetime.now(UTC))
        if err:
            return None, err
        self._save(guild_id, state)

        embed = discord.Embed(title=f'Апелляция #{item["id"]} — новая',
                              description=item['text'],
                              color=COLOR_PENDING,
                              timestamp=datetime.now(UTC))
        embed.set_author(name=str(user), icon_url=user.display_avatar.url
                         if getattr(user, 'display_avatar', None) else None)
        embed.add_field(name='Участник',
                        value=f'{user.mention} · `{user.id}`', inline=False)
        embed.add_field(name='Контекст модератора',
                        value=self._mod_context(state, guild.id, user.id),
                        inline=False)
        embed.set_footer(text=f'user_id: {item["user_id"]} · appeal #{item["id"]} · меню под карточкой')
        # «всё сюда, кроме логов»: карточка живёт в комнате апелляции;
        # нет комнаты — запасной канал карточек (владелец 2026-09-06)
        channel, use_thread = await self._card_channel(guild, state)
        if channel is not None:
            # Оформление карточки: V2 LayoutView + опциональная картинка.
            appearance = normalize_appearance(state.get('appearance'))
            snap = self._appeal_card_text_from_embed(embed)
            painted = await self._paint_appeal_card(embed, item, appearance)
            send_kwargs = self._appeal_v2_send_kw(
                guild_id, item, embed, painted, snap=snap)
            msg = None
            if use_thread:
                # запасной путь без комнаты: заявка — в собственную ветку,
                # чтобы канал карточек не замусоривался. Раньше это делал
                # только путь «меню в канале», а из ЛС карточка падала
                # голым сообщением в общий канал (несостыковка 2026-09-08).
                try:
                    thread = await channel.create_thread(
                        name=f'Апелляция #{item["id"]} · {str(user)[:40]}',
                        type=discord.ChannelType.public_thread)
                    msg = await thread.send(**send_kwargs)
                    item['thread_id'] = thread.id
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    # нет права «Создавать публичные ветки» — НЕ теряем
                    # заявку: карточка ложится прямо в канал (как в меню-пути)
                    log.warning('appeals: тред #%s не создан (%s) — карточка в канал',
                                item['id'], _ex)
            if msg is None:
                try:
                    msg = await channel.send(**send_kwargs)
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    log.error('appeals: карточка #%s на %s не ушла: %s',
                              item['id'], guild_id, _ex)
            if msg is not None:
                item['message_id'] = msg.id
                item['thread_url'] = msg.jump_url
                # где лежит карточка (для удаления после решения) + пинг
                item['card_channel_id'] = getattr(channel, 'id', None)
                self._save(guild_id, state)
                ping = await self._ping_mod_role(channel, settings_of(state), item)
                item['ping_message_id'] = getattr(ping, 'id', None)
                await self._fire_panel_event(item)
        # Канал апелляции открывается после подачи при ЛЮБОМ пути подачи
        # (скрыт до подачи — заказ владельца 2026-09-05). Сначала СОХРАНЯЕМ
        # state, потом вешаем на локальный item временные поля для ответа:
        # item уезжает в JSON — канал и имя канала в БД хранить нельзя.
        _opened, _ch_ref = await self._open_appeal_channel(guild, user)
        self._save(guild_id, state)
        item['_channel_status'] = _opened           # временно, только для ответа
        item['_channel_name'] = getattr(_ch_ref, 'name', '') or ''
        try:
            body = (
                f'Модераторы сервера **{guild.name}** уже получили вашу '
                f'апелляцию.\n\n'
                + self._dm_channel_line(_opened, _ch_ref))
            await _send_dm_notice(user, status='submitted', item=item,
                                  guild_name=str(guild.name), body=body)
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.debug('appeals: ЛС подтверждения #%s не дошло: %s', item['id'], _ex)
        return item, None

    def _main_guild(self):
        """Главный сервер — всегда из конфигурации (без вопросов пользователю).

        Источник истины — Config.MAIN_GUILD_ID. Если конфиг не задан, но бот
        стоит ровно на одном сервере — берём его (единственный возможный).
        Иначе None: честно отвечаем, что бот не настроен.
        """
        try:
            from config import Config
            gid = int(getattr(Config, 'MAIN_GUILD_ID', 0) or 0)
        except Exception as _ex:
            log.debug('appeals: MAIN_GUILD_ID: %s', _ex)
            gid = 0
        g = self.bot.get_guild(gid) if gid else None
        if g is None and not gid and len(getattr(self.bot, 'guilds', [])) == 1:
            g = self.bot.guilds[0]
        return g

    async def _is_banned(self, guild, user):
        """Забанен ли человек ПО ЛЮБОЙ нашей механике.

        1. Настоящий Discord-бан — fetch_ban.
        2. Панельный «бан» — изоляция: участник на сервере, но носит
           назначенную роль-«бан» (выдаёт модерация). Без этого пункта
           изолированные получали ложное «вы не в бане».
        """
        real_ban = None
        try:
            await guild.fetch_ban(discord.Object(id=user.id))
            real_ban = True
        except discord.NotFound:
            real_ban = False  # реального бана нет — ниже смотрим изоляцию
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.warning('appeals: ban-check %s на %s: %s', user.id, guild.id, _ex)
            return True
        if real_ban:
            return True
        member = guild.get_member(user.id)
        if member is not None:
            try:
                from services import punish_roles as PR
                rid = PR.role_for(guild.id, 'ban')
                if rid and any(r.id == rid for r in getattr(member, 'roles', [])):
                    return True
            except Exception as _ex:
                log.debug('appeals: isolation ban-check: %s', _ex)
        return False

    # ---- модераторские ----


    # ---- утилиты ----
    def _log_channel(self, guild, state):
        """Запасной канал карточек, если комната апелляции не задана.

        Порядок: Каналы и маршруты → «Карточки апелляций» → известный канал
        модеров, если он есть на сервере → старый log_channel_id (наследие)
        → системный. Главный канал карточек теперь сама комната апелляции —
        см. _card_channel («всё сюда, кроме логов», владелец 2026-09-06).
        """
        try:
            from services.channel_routes import resolve_route, channel_on_guild
            rcid = int(resolve_route(guild.id, 'appeals_channel', guild) or 0)
            rch = channel_on_guild(guild, rcid) if rcid else None
            if rch is not None:
                return rch
        except Exception as _ex:
            log.debug('appeals: маршрут карточек: %s', _ex)
        cid = (state or {}).get('log_channel_id')
        ch = self._guild_ch(guild, cid) if cid else None
        if ch is not None:
            return ch
        return guild.system_channel

    async def _card_channel(self, guild, state):
        """Куда класть карточку апелляции — «всё сюда, кроме логов».

        Главная точка — сама комната апелляции (маршрут «Комната
        апелляции»): заявка, кнопки модераторов и обсуждение живут в одном
        канале, забаненный видит свою карточку (владелец 2026-09-06).
        Комнаты нет — запасной путь прежний: канал карточек, и там
        заявка уходит в собственную ветку, чтобы канал не замусоривался.
        Возвращает (канал | None, создавать_ли_ветку).
        """
        room = await self._appeal_channel(guild)
        if room is not None:
            return room, False
        return self._log_channel(guild, state), True

    async def _notify_user(self, item, accept, unbanned, cooldown_hours=0,
                           guild_name='', member_present=False, invite_url=None,
                           guild_id=0):
        """ЛС о решении — V2-карточка (фолбек: эмбед).

        Развилка принятия: панельный «бан» — изоляция (человек на сервере);
        командный /ban — Discord-бан (может вернуться по ссылке).
        """
        try:
            user = await self.bot.fetch_user(item['user_id'])
        except (discord.NotFound, discord.HTTPException):
            return
        if accept:
            status = 'accepted'
            if member_present:
                body = (
                    f'Наказание снято: изоляция убрана — вы снова видите '
                    f'каналы сервера **{guild_name}**.\n\n'
                    f'Добро пожаловать назад!')
            elif unbanned:
                body = f'Бан на сервере **{guild_name}** снят.'
                if invite_url:
                    body += (f'\n\n**Ссылка для возврата** '
                             f'(один раз, 24 ч):\n{invite_url}')
                else:
                    body += ('\n\nМожно вернуться по вашему приглашению '
                             'на сервер — или попросите свежую ссылку '
                             'у модераторов.')
            else:
                body = (f'Ваша апелляция на сервере **{guild_name}** '
                        'принята.')
            who = str(item.get('reviewed_by') or '').strip()
            if who:
                body += f'\n\n**Решение вынес**\n{who}'
        else:
            status = 'rejected'
            body = 'К сожалению, в этот раз — нет.'
            text_brief = str(item.get('text') or '').strip()
            if text_brief:
                body += f'\n\n**Ваша апелляция**\n{text_brief[:300]}'
            if item.get('reply'):
                body += (f'\n\n**Комментарий модератора**\n'
                         f'{str(item["reply"])[:300]}')
            who = str(item.get('reviewed_by') or '').strip()
            if who:
                body += f'\n\n**Решение вынес**\n{who}'
            if cooldown_hours > 0:
                reviewed = _parse_ts(item.get('reviewed_at'))
                if reviewed is not None:
                    from datetime import timedelta
                    retry = reviewed + timedelta(hours=cooldown_hours)
                    body += (f'\n\n**Повторная подача**\n'
                             f'не раньше **{retry.strftime("%d.%m %H:%M")}**')
        try:
            await _send_dm_notice(user, status=status, item=item,
                                  guild_name=guild_name, body=body)
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.debug('appeals: ЛС %s закрыты: %s', item['user_id'], _ex)
            return
        # после решения — меню-оценка (селект)
        if guild_id and not item.get('rating'):
            try:
                view = AppealRateView(self, guild_id, item.get('id'))
                await user.send(
                    embed=_rate_prompt_embed(item, guild_name), view=view)
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.debug('appeals: ЛС-оценка #%s: %s', item.get('id'), _ex)


async def setup(bot):
    cog = Appeals(bot)
    await bot.add_cog(cog)
