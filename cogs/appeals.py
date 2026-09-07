# -*- coding: utf-8 -*-
"""Апелляции на баны (Appeals Cog)
=================================
Забаненный не может написать на сервере — но может написать боту в личку:

    /апелляция [текст]                  (в ЛС боту; сервер — из конфигурации,
                                         без текста откроется форма)

Модераторы получают карточку с кнопками «Принять» / «Отклонить».
Принят — пользователь разбанен и получает добрую весть в ЛС.
Отклонён — получает отказ (с опциональным комментарием модератора).

- /апелляция [текст]             — подать (в ЛС боту; сервер сам берётся из
                                   конфигурации, без текста откроется форма)
- /апелляции настройка #канал    — куда падать карточкам
- /апелляции список              — ожидающие решения

Хранилище — SQLite (GuildData 'appeals'). Кнопки живут в persistent view
и переживают рестарт бота. Метки — aware UTC.
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
        # пинг роли модерации в канал при новой апелляции (0 = без пинга);
        # авто-блок подачи после N отклонённых (0 = выключен)
        'ping_role_id': _clamp_hours(raw.get('ping_role_id'), 0, 0, 10 ** 25),
        'block_after_rejects': _clamp_hours(raw.get('block_after_rejects'),
                                            0, 0, 10),
        # эскалация: pending старше N часов → пинг старшей роли в канал
        # (0 часов = выключено; роль 0 = отметить эскалацию без упоминания)
        'escalate_hours': _clamp_hours(raw.get('escalate_hours'), 0, 0, 336),
        'escalate_role_id': _clamp_hours(raw.get('escalate_role_id'), 0, 0,
                                         10 ** 25),
    }


def _dm_embed(status, item, guild_name=''):
    """Единый вид ЛС апелляций: цвет = исход, номер + сервер, футер Hakumo.

    status: 'submitted' | 'accepted' | 'rejected' | 'closed' | 'pending'.
    """
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


def create_appeal(state, user_id, user_name, text, now, link=None):
    """Создать апелляцию. Возвращает (item, ошибка)."""
    text = str(text or '').strip()
    link = _clean_link(link)
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
        'link': link,
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


def _clean_link(link):
    """Ссылка-доказательство: без протокола — https://, опасные схемы — None."""
    v = str(link or '').strip()
    if not v:
        return None
    if re.match(r'^(javascript|data|vbscript):', v, re.I):
        return None
    if not re.match(r'^https?://', v, re.I):
        v = 'https://' + v
    return v[:500]


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
    link = (item.get('link') or '').strip()
    if link:
        body += f"\n🔗 Доказательство: {link}"
    return body


# ─── view с кнопками ────────────────────────────────────────────────────────

class AppealView(discord.ui.View):
    """Persistent-кнопки под конкретную апелляцию.

    custom_id уникален для каждой апелляции ('appeal:accept:7'), поэтому
    view можно перерегистрировать после рестарта бота (on_ready ниже) —
    кнопки не умирают, пока апелляция ждёт решения.
    """

    def __init__(self, cog, guild_id, appeal_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.appeal_id = appeal_id
        for label, style, verb in (
                ('Принять', discord.ButtonStyle.success, 'accept'),
                ('Отклонить', discord.ButtonStyle.danger, 'reject')):
            btn = discord.ui.Button(
                label=label, style=style,
                custom_id=f'appeal:{verb}:{appeal_id}')
            btn.callback = self._make_cb(verb == 'accept')
            self.add_item(btn)
        claim = discord.ui.Button(
            label='Взять в работу', style=discord.ButtonStyle.primary,
            emoji='✋', custom_id=f'appeal:claim:{appeal_id}')
        claim.callback = self._claim
        self.add_item(claim)

    def _claim_btn(self):
        for child in self.children:
            if str(getattr(child, 'custom_id', '')).startswith('appeal:claim:'):
                return child
        return None

    async def _claim(self, interaction):
        """Взять апелляцию в работу / снять с себя (повторный клик)."""
        # Права решает владелец (панель → Права команд → «Бан»), Discord-права
        # не при чём — та же строгая модель, что у /modpanel.
        try:
            from services.permission_acl import check_action as _acl
            if not _acl(self.guild_id, interaction.user, 'ban'):
                await interaction.response.send_message(
                    'Апелляции тебе не дал владелец (панель → Доступ → '
                    'Права команд → Классические разрешения).', ephemeral=True)
                return
        except Exception as _ex:
            log.debug('appeals claim acl: %s', _ex)
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
                     'его на сервере.' if _opened else
                     '\n⚠ Канал апелляции не открылся: участник вне сервера '
                     'или у бота нет прав на канал.')
        embed = (interaction.message.embeds[0]
                 if interaction.message and interaction.message.embeds else None)
        if embed is not None:
            tail = (f'В работе: {item["claimed_by"]["name"]}'
                    if item.get('claimed_by') else 'Очередь общая')
            embed.set_footer(text=tail)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.edit_message(view=self)
        await interaction.followup.send(note, ephemeral=True)

    def _make_cb(self, accept):
        async def _cb(interaction):
            await self._resolve(interaction, accept)
        return _cb

    async def _resolve(self, interaction, accept):
        # Права решает владелец (панель → Права команд → «Бан»), а не
        # Discord-права: «своя система, Discord не при чём» (строгая модель
        # permission_acl). Одно действие «Бан» открывает и решение апелляций.
        gid = self.guild_id
        try:
            from services.permission_acl import check_action
            if not check_action(gid, interaction.user, 'ban'):
                await interaction.response.send_message(
                    '🚫 Апелляции тебе не дал владелец (панель → Доступ → '
                    'Права команд → Классические разрешения).', ephemeral=True)
                return
        except Exception as _ex:
            log.debug('appeals: acl resolve: %s', _ex)
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

        # Карточка сделала своё дело: решение вынесено — сообщение с кнопками
        # удаляем, чтобы канал апелляций не замусоривался (владелец
        # 2026-09-06). Модератору — короткий ephemeral-ответ, полная история
        # живёт в панели («Апелляции → История решений»).
        status = ('принята (разбанен)' if (accept and unbanned)
                  else ('принята' if accept else 'отклонена'))
        _done_note = (f'Апелляция #{item["id"]} — {status}. Карточка удалена; '
                      'история — в панели «Апелляции».')
        try:
            await interaction.response.send_message(_done_note, ephemeral=True)
        except Exception as _ex:
            log.debug('appeals: ответ решения: %s', _ex)
            try:
                await interaction.followup.send(_done_note, ephemeral=True)
            except Exception as _ex2:
                log.debug('appeals: followup решения: %s', _ex2)
        await self.cog._delete_appeal_card(
            guild, state, item, message=interaction.message)



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
    link = str(item.get('link') or '').strip()
    if link.startswith('http://') or link.startswith('https://'):
        fields.append(('Доказательство', _bullet(f'[открыть]({link})')))
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
        self.link = discord.ui.TextInput(
            label='Ссылка-доказательство (необязательно)',
            placeholder='https://… — скрин, видео или сообщение',
            required=False, max_length=500)
        self.add_item(self.text)
        self.add_item(self.link)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self.cog._is_banned(self.guild, interaction.user):
            await interaction.followup.send(
                ' Вы не забанены на этом сервере — апелляция не нужна.', ephemeral=True)
            return
        item, err = await self.cog._submit_appeal(
            interaction.user, self.guild, self.text.value,
            link=self.link.value)
        if err:
            await interaction.followup.send(f' Не получилось: {err}.', ephemeral=True)
            return
        from cogs.embed_utils import hakumo_embed as _ae
        await interaction.followup.send(
            embed=_ae('appeal', f'Апелляция #{item["id"]} отправлена',
                      f'Модераторы сервера **{self.guild.name}** уже получили её. '
                      'Ответ придёт сюда, в личку.'), ephemeral=True)


# (выбора сервера больше нет: апелляция всегда идёт на главный сервер
#  из конфигурации — см. cmd_appeal / _main_guild)

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
        self.link = discord.ui.TextInput(
            label='Ссылка-доказательство (необязательно)',
            placeholder='https://… — скрин, видео или сообщение',
            required=False, max_length=500)
        self.add_item(self.text)
        self.add_item(self.link)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        item, err = await self.cog._submit_channel_appeal(
            interaction.user, self.guild, self.text.value,
            link=self.link.value, channel=interaction.channel)
        if err:
            await interaction.followup.send(f'Не получилось: {err}.', ephemeral=True)
            return
        await interaction.followup.send(
            f'Апелляция **#{item["id"]}** принята — обсуждение в треде. '
            'Модераторы уже видят её.', ephemeral=True)


class AppealMenuSelect(discord.ui.Select):
    """Select «Подать апелляцию» в канале (persistent)."""

    def __init__(self):
        super().__init__(
            custom_id=MENU_CUSTOM_ID,
            placeholder='Несогласны с наказанием? Подайте апелляцию…',
            min_values=1, max_values=1,
            options=[discord.SelectOption(
                label='Подать апелляцию', value='submit',
                description='Откроется окно: что произошло и ссылка-доказательство',
                emoji='⚖️')])

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog('Appeals')
        if cog is None:
            await interaction.response.send_message(
                'Модуль апелляций не загружен.', ephemeral=True)
            return
        await interaction.response.send_modal(
            AppealChannelModal(cog, interaction.guild))


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
    Открывает ту же форму, что /апелляция (владелец 2026-09-06:
    «внизу кнопка для апелляции — чтобы типо разбан»).
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
                    self.bot.add_view(AppealView(self, guild.id, item['id']),
                                      message_id=item['message_id'])
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
        # цикл напоминаний о висящих апелляциях — один раз (on_ready бывает повторно)
        if not self._stale_started:
            self._stale_started = True
            try:
                import asyncio
                asyncio.get_event_loop().create_task(self._stale_loop())
            except Exception as _ex:
                log.debug('appeals: старт _stale_loop: %s', _ex)

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
        """Пинг роли модерации при новой апелляции (0 в настройках = без пинга).

        Возвращает отправленное сообщение: его id запоминаем в карточке,
        чтобы после решения удалить и пинг — канал остаётся чистым."""
        rid = int(settings.get('ping_role_id') or 0)
        if not rid or target_channel is None:
            return None
        try:
            return await target_channel.send(
                f'<@&{rid}> — новая апелляция **#{item["id"]}** ожидает решения.',
                allowed_mentions=discord.AllowedMentions(roles=True))
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
                            embed = _dm_embed('pending', item, str(guild.name))
                            embed.description = (
                                f'Ваша апелляция **#{item["id"]}** ждёт решения '
                                f'уже **{age_h} ч** — она не потерялась: '
                                'модераторам только что напомнили.')
                            await user.send(embed=embed)
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
                # карточка в канале: вопрос закрыт — сообщение удаляем,
                # канал не замусоривается (владелец 2026-09-06)
                try:
                    await self._delete_appeal_card(guild, state, item)
                except Exception as _ex:
                    log.debug('appeals: автозакрытие карточки #%s: %s', item['id'], _ex)
                try:
                    dm = _dm_embed('closed', item, str(guild.name))
                    dm.description = ('Бан снят вручную в Discord — решение по '
                                      'апелляции больше не нужно. Доступ уже с вами.')
                    await user.send(embed=dm)
                except (discord.Forbidden, discord.HTTPException) as _ex:
                    log.debug('appeals: ЛС автозакрытия #%s: %s', item['id'], _ex)
            log.info('appeals: %s апелляций закрыто автоматически (ручной разбан %s на %s)',
                     len(closed), user.id, guild.id)
        except Exception as _ex:
            log.debug('appeals: on_member_unban: %s', _ex)

    # ---- меню апелляций в канале ----
    async def publish_appeal_menu(self, channel):
        """Опубликовать меню подачи апелляций в канал (из панели).

        Возвращает (ok, сообщение). Повторная публикация обновляет сообщение.
        """
        if channel is None:
            return False, 'Канал не найден'
        guild = channel.guild
        state = self._load(guild.id)
        embed = discord.Embed(
            title='⚖ Апелляции на наказания',
            description=(
                'Несогласны с наказанием — варном, мутом или баном?\n'
                'Выберите ниже **«Подать апелляцию»**: откроется окно — '
                'расскажите свою версию и, если есть, приложите ссылку '
                'на скрин или видео.\n\n'
                'Для вашей апелляции создастся отдельный тред — '
                'модераторы ответят прямо в нём.'),
            color=0xF1C40F,
            timestamp=datetime.now(UTC))
        embed.set_footer(text=f'{guild.name} · апелляции',
                         icon_url=guild.icon.url if guild.icon else None)
        old = (state.get('menu') or {})
        avatar = _hook_avatar(guild)
        msg = None
        used_hook = None
        # главный путь — вебхук: имя «⚖ Апелляции», кнопки работают как раньше
        hook = await _channel_webhook(channel)
        if hook is not None:
            used_hook = hook
            try:
                if (old.get('message_id')
                        and int(old.get('webhook_id') or 0) == hook.id
                        and int(old.get('channel_id') or 0) == channel.id):
                    msg = await hook.edit_message(
                        int(old['message_id']), embed=embed, view=AppealMenuView())
                else:
                    msg = await hook.send(
                        embed=embed, view=AppealMenuView(), wait=True,
                        username=HOOK_USERNAME, avatar_url=avatar)
            except Exception as _ex:
                log.debug('appeals: меню через вебхук не ушло: %s', _ex)
                msg = None
        # фолбэк — обычная отправка от бота (вебхука нет или не вышло)
        if msg is None:
            try:
                if (old.get('message_id')
                        and int(old.get('channel_id') or 0) == channel.id
                        and not int(old.get('webhook_id') or 0)):
                    msg = await channel.edit_message(
                        int(old['message_id']), embed=embed, view=AppealMenuView())
                if msg is None:
                    msg = await channel.send(embed=embed, view=AppealMenuView())
            except (discord.Forbidden, discord.HTTPException) as _ex:
                return False, f'Бот не может писать в этот канал: {_ex}'
        state['menu'] = {'channel_id': channel.id, 'message_id': msg.id,
                         'webhook_id': getattr(used_hook, 'id', 0) or 0}
        self._save(guild.id, state)
        how = 'вебхуком' if used_hook is not None else 'от бота'
        return True, f'Меню опубликовано в {channel.mention} ({how})'

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
                return await fetch(_cid)
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

        Цель overwrite — Member, не User из ЛС: иначе Discord отвечает
        NotFound и комната не открывается (владелец 2026-09-06).
        Ветка: add_user + права на родителе.
        """
        _iso = await self._appeal_channel(guild)
        if _iso is None:
            log.error('appeals: канал апелляции не задан — некому открывать доступ (guild %s)', getattr(guild, 'id', '?'))
            return False, None
        member = await self._as_member(guild, user)
        ow = discord.PermissionOverwrite(
            view_channel=True, send_messages=True,
            read_message_history=True, attach_files=True,
            embed_links=True, add_reactions=True)
        opened = False
        add_user = getattr(_iso, 'add_user', None)
        if callable(add_user):
            try:
                await add_user(member)
                opened = True
            except (discord.Forbidden, discord.HTTPException, TypeError) as _ex:
                log.debug('appeals: add_user %s: %s', getattr(member, 'id', '?'), _ex)
        set_perm = getattr(_iso, 'set_permissions', None)
        if callable(set_perm):
            try:
                await set_perm(member, overwrite=ow)
                return True, _iso
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.error('appeals: открыть канал апелляции для %s: %s',
                          getattr(member, 'id', '?'), _ex)
                parent = getattr(_iso, 'parent', None)
                pset = getattr(parent, 'set_permissions', None)
                if callable(pset):
                    try:
                        await pset(member, overwrite=ow)
                        return True, _iso
                    except (discord.Forbidden, discord.HTTPException) as _ex2:
                        log.debug('appeals: parent set_permissions: %s', _ex2)
                return opened, _iso
        parent = getattr(_iso, 'parent', None)
        pset = getattr(parent, 'set_permissions', None)
        if callable(pset):
            try:
                await pset(member, overwrite=ow)
                return True, _iso
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.debug('appeals: parent set_permissions: %s', _ex)
        return opened, (_iso if opened else None)

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
        """Строка про канал для ЛС-подтверждения: имя канала, не абстракция."""
        if opened:
            name = getattr(channel, 'name', '') or 'канал апелляции'
            return (f'Канал **#{name}** на сервере открыт для вас — карточка '
                    'видна там. Ответ придёт в личные сообщения — обычно в '
                    'течение суток.')
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
                        link=item.get('link'), theme=appearance.get('theme'))
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
                png = render_appeal_card(
                    appeal_id=item['id'], user_name=item['user_name'],
                    text=item['text'], link=item.get('link'),
                    theme=appearance.get('theme'))
                if png:
                    fn = appeal_card_filename(item['id'])
                    file = discord.File(io.BytesIO(png), filename=fn)
                    embed.set_image(url=f'attachment://{fn}')
                    self._strip_appeal_embed_texts(embed)
        except Exception as _ex:
            log.debug('appeals: карточка-картинка #%s: %s', item.get('id'), _ex)
        return file

    async def _submit_channel_appeal(self, user, guild, text, link=None, channel=None):
        """Апелляция из меню в канале: карточка в отдельном треде."""
        guild_id = guild.id
        state = self._load(guild_id)
        item, err = create_appeal(state, user.id, str(user), text,
                                  datetime.now(UTC), link=link)
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
        if item.get('link'):
            embed.add_field(name='Доказательство', value=item['link'], inline=False)
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
        try:
            appearance = normalize_appearance(state.get('appearance'))
            card_file = await self._paint_appeal_card(embed, item, appearance)
        except Exception as _ex:
            log.debug('appeals: карточка-картинка #%s: %s', item['id'], _ex)

        view = AppealView(self, guild_id, item['id'])
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
            send_kw = {'embed': embed, 'view': view}
            if card_file is not None:
                send_kw['file'] = card_file
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
            embed = _dm_embed('submitted', item, str(guild.name))
            embed.description = (
                f'Модераторы сервера **{guild.name}** уже получили её. '
                + self._dm_channel_line(ch_opened, ch_ref))
            await user.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.debug('appeals: ЛС подтверждения #%s не дошло: %s', item['id'], _ex)
        return item, None

    # ---- подача (ЛС боту) ----
    async def _submit_appeal(self, user, guild, text, link=None):
        """Общая точка создания апелляции: проверка бана, лимит, карточка."""
        guild_id = guild.id
        state = self._load(guild_id)
        item, err = create_appeal(state, user.id, str(user), text,
                                  datetime.now(UTC), link=link)
        if err:
            return None, err
        self._save(guild_id, state)

        embed = discord.Embed(title=f'Апелляция #{item["id"]} — новая',
                              description=item['text'],
                              color=COLOR_PENDING,
                              timestamp=datetime.now(UTC))
        if item.get('link'):
            embed.add_field(name='Доказательство', value=item['link'], inline=False)
        embed.set_author(name=str(user), icon_url=user.display_avatar.url
                         if getattr(user, 'display_avatar', None) else None)
        embed.add_field(name='Контекст модератора',
                        value=self._mod_context(state, guild.id, user.id),
                        inline=False)
        embed.set_footer(text=f'user_id: {item["user_id"]} · appeal #{item["id"]}')
        # «всё сюда, кроме логов»: карточка живёт в комнате апелляции;
        # нет комнаты — запасной канал карточек (владелец 2026-09-06)
        channel, _use_thread = await self._card_channel(guild, state)
        if channel is not None:
            view = AppealView(self, guild_id, item['id'])
            # Оформление карточки из панели: авто-картинка в выбранной теме,
            # своя картинка по URL (скачиваем файлом — без пережатия) или
            # обычный эмбед без картинки.
            appearance = normalize_appearance(state.get('appearance'))
            send_kwargs = {'embed': embed, 'view': view}
            painted = await self._paint_appeal_card(embed, item, appearance)
            if painted is not None:
                send_kwargs['file'] = painted
            try:
                msg = await channel.send(**send_kwargs)
                item['message_id'] = msg.id
                # где лежит карточка (для удаления после решения) + пинг
                item['card_channel_id'] = getattr(channel, 'id', None)
                self._save(guild_id, state)
                ping = await self._ping_mod_role(channel, settings_of(state), item)
                item['ping_message_id'] = getattr(ping, 'id', None)
                await self._fire_panel_event(item)
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.error('appeals: карточка #%s на %s не ушла: %s',
                          item['id'], guild_id, _ex)
        # Канал апелляции открывается после подачи при ЛЮБОМ пути подачи
        # (скрыт до подачи — заказ владельца 2026-09-05). Сначала СОХРАНЯЕМ
        # state, потом вешаем на локальный item временные поля для ответа:
        # item уезжает в JSON — канал и имя канала в БД хранить нельзя.
        _opened, _ch_ref = await self._open_appeal_channel(guild, user)
        self._save(guild_id, state)
        item['_channel_opened'] = bool(_opened)      # временно, только для ответа
        item['_channel_name'] = getattr(_ch_ref, 'name', '') if _opened else ''
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

    @app_commands.command(name='апелляция',
                          description='Обжаловать наказание — подаётся в ЛС боту',
                          extras={'keep_global': True})
    @app_commands.allowed_contexts(guilds=False, dms=True, private_channels=True)
    @app_commands.describe(текст='Что произошло — до 500 символов; без текста откроется форма')
    async def cmd_appeal(self, interaction: discord.Interaction,
                         текст: str = ''):
        """Обжаловать наказание: /апелляция [текст] в ЛС боту.

        Сервер никогда не спрашиваем — он из конфигурации. Без текста
        открываем форму с полем-доказательством.
        """
        if interaction.guild is not None:
            await interaction.response.send_message(
                'Апелляция подаётся в личных сообщениях боту: открой ЛС бота '
                'и вызови команду там.', ephemeral=True)
            return
        guild = self._main_guild()
        if guild is None:
            await interaction.response.send_message(
                'Бот ещё не настроен: владелец не указал главный сервер. '
                'Напишите администрации сервера другим способом.', ephemeral=True)
            return
        if not await self._is_banned(guild, interaction.user):
            await interaction.response.send_message(
                f'Вы не забанены на сервере **{guild.name}** — апелляция не нужна.',
                ephemeral=True)
            return
        текст = (текст or '').strip()
        if not текст:
            # удобная форма: текст + ссылка-доказательство (необязательно)
            await interaction.response.send_modal(AppealModal(self, guild))
            return
        # Карточка + открытие канала легко занимают больше 3с Discord.
        await interaction.response.defer(ephemeral=True)
        item, err = await self._submit_appeal(interaction.user, guild, текст)
        if err:
            await interaction.followup.send(
                f'Не получилось: {err}.', ephemeral=True)
            return
        from cogs.embed_utils import hakumo_embed
        if item.pop('_channel_opened', False):
            _ch_name = str(item.pop('_channel_name', '') or 'канал апелляции')
            _extra = (f'Канал **#{_ch_name}** на сервере открыт для вас — '
                      'карточка видна там. Ответ придёт в личку.')
        else:
            item.pop('_channel_name', None)
            _extra = ('Ответ придёт в личку. Канал апелляции открыть не '
                      'получилось (боту нужны права) — модераторы напишут '
                      'вам сами.')
        e = hakumo_embed('appeal', f'Апелляция #{item["id"]} отправлена',
                         f'Модераторы сервера **{guild.name}** уже получили '
                         f'её. {_extra}')
        await interaction.followup.send(embed=e)


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
        """ЛС о решении — единый embed.

        Развилка принятия по нашей механике: панельный «бан» — изоляция
        (человек на сервере, возвращаем доступ), командный /ban — настоящий
        Discord-бан (человек вне сервера, может вернуться по ссылке, если
        владелец включил разовые инвайты в «Правилах подачи»).
        Отказ — карточка-итог: текст апелляции, комментарий, дата репоста.
        """
        try:
            user = await self.bot.fetch_user(item['user_id'])
        except (discord.NotFound, discord.HTTPException):
            return
        if accept:
            embed = _dm_embed('accepted', item, guild_name)
            if member_present:
                embed.description = (
                    f'Наказание снято: изоляция убрана — вы снова видите '
                    f'каналы сервера **{guild_name}**. Добро пожаловать назад!')
            elif unbanned:
                embed.description = (
                    f'Бан на сервере **{guild_name}** снят. '
                    + (f'Возвращайтесь по ссылке (работает один раз, 24 ч):\n{invite_url}'
                       if invite_url else
                       'Можно вернуться по вашему приглашению на сервер.'))
                if not invite_url:
                    embed.description += ' Или попросите свежую ссылку у знакомых модераторов.'
            else:
                embed.description = (f'Ваша апелляция на сервере **{guild_name}** '
                                     'принята.')
        else:
            embed = _dm_embed('rejected', item, guild_name)
            embed.description = 'К сожалению, в этот раз — нет.'
            text_brief = str(item.get('text') or '').strip()
            if text_brief:
                embed.add_field(name='Ваша апелляция',
                                value=text_brief[:300], inline=False)
            if item.get('reply'):
                embed.add_field(name='Комментарий модератора',
                                value=str(item['reply'])[:300], inline=False)
            if cooldown_hours > 0:
                reviewed = _parse_ts(item.get('reviewed_at'))
                if reviewed is not None:
                    from datetime import timedelta
                    retry = reviewed + timedelta(hours=cooldown_hours)
                    embed.add_field(
                        name='Повторная подача',
                        value=f'не раньше **{retry.strftime("%d.%m %H:%M")}**',
                        inline=False)
        try:
            await user.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.debug('appeals: ЛС %s закрыты: %s', item['user_id'], _ex)
            return
        # после решения — меню-оценка (селект), как размут
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
