# -*- coding: utf-8 -*-
"""Апелляции — УПРОЩЁННАЯ СХЕМА (заказ 2026-09-08)

«короче на счет апеляции просто в этот канал заявку отпраить и все
не надо не у кого ничего открывать человек в бане просто подасть заявку
и куратор посмотрить и решит надо ему это или нет»

Принцип:
- Человек в бане жмёт кнопку «Подать апелляцию» в ЛС бота
- Пишет текст (10-500 символов)
- Бот кидает заявку ПРОСТО в канал апелляций (один канал, без тредов и без открытия доступов)
- Куратор смотрит карточку в этом канале и жмёт Принять / Отклонить
- При принятии — разбан, при отклонении — ЛС с причиной

Совместимость:
- Сохранены все чистые функции и константы, которые ждут тесты и панель
- Кнопка «Взять в работу» оставлена для совместимости, но НЕ открывает канал
- _open_appeal_channel теперь возвращает 'skipped' — ничего не открывает
- Карточки не создают треды, пинг роли — просто сообщение в том же канале
"""

import io
import re
from datetime import datetime, timezone

import discord
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
COLOR_CLOSED = 0x95A5A6

MAX_TEXT = 500
MAX_PER_USER = 3

CURATOR_PING_ROLE_ID = 807030012301541377

DEFAULT_COOLDOWN_HOURS = 72
DEFAULT_STALE_HOURS = 24
DEFAULT_REJECT_TEMPLATES = [
    'Нарушение подтверждено — бан остаётся в силе',
    'Недостаточно доказательств',
    'Повторная подача без новых фактов',
    'Слишком рано — подайте позже',
]
MAX_TEMPLATES = 10
STALE_CHECK_EVERY = 1800

DM_FOOTER = 'Hakumo · Апелляции'


# ─── чистые функции ─────────────────────────────────────────────────────────

def empty_state():
    return {'next_id': 1, 'items': [], 'log_channel_id': 0}


def _clamp_hours(raw_val, default, lo, hi):
    if raw_val is None:
        return default
    try:
        return max(lo, min(int(raw_val), hi))
    except (TypeError, ValueError):
        return default


def settings_of(state):
    raw = (state or {}).get('settings') or {}
    tpl = raw.get('reject_templates')
    if not isinstance(tpl, list) or not tpl:
        tpl = list(DEFAULT_REJECT_TEMPLATES)
    try:
        _pid = int(raw.get('ping_role_id'))
    except (TypeError, ValueError):
        _pid = 0
    return {
        'cooldown_hours': _clamp_hours(raw.get('cooldown_hours'), DEFAULT_COOLDOWN_HOURS, 0, 720),
        'stale_hours': _clamp_hours(raw.get('stale_hours'), DEFAULT_STALE_HOURS, 1, 336),
        'reject_templates': [str(t)[:100] for t in tpl[:MAX_TEMPLATES]],
        'require_reply_on_reject': bool(raw.get('require_reply_on_reject')),
        'invite_on_unban': bool(raw.get('invite_on_unban')),
        'invite_channel_id': _clamp_hours(raw.get('invite_channel_id'), 0, 0, 10 ** 25),
        'ping_role_id': (min(_pid, 10 ** 25) if _pid > 0 else CURATOR_PING_ROLE_ID),
        'block_after_rejects': _clamp_hours(raw.get('block_after_rejects'), 0, 0, 10),
        'escalate_hours': _clamp_hours(raw.get('escalate_hours'), 0, 0, 336),
        'escalate_role_id': _clamp_hours(raw.get('escalate_role_id'), 0, 0, 10 ** 25),
    }


def _dm_embed(status, item, guild_name=''):
    palette = {
        'submitted': (COLOR_PENDING, f'Апелляция #{item.get("id")} отправлена'),
        'accepted': (COLOR_YES, f'Апелляция #{item.get("id")} — принята'),
        'rejected': (COLOR_NO, f'Апелляция #{item.get("id")} — отклонена'),
        'closed': (COLOR_CLOSED, f'Апелляция #{item.get("id")} — закрыта'),
        'pending': (COLOR_PENDING, f'Апелляция #{item.get("id")} — на рассмотрении'),
    }
    color, title = palette.get(status, (COLOR_PENDING, f'Апелляция #{item.get("id")}'))
    embed = discord.Embed(title=title, color=color, timestamp=datetime.now(UTC))
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
    mine = [i for i in (state or {}).get('items', [])
            if int(i.get('user_id') or 0) == int(user_id)
            and i.get('status') == 'rejected' and i.get('reviewed_at')]
    mine.sort(key=lambda i: str(i.get('reviewed_at') or ''))
    return mine[-1] if mine else None


def cooldown_block(state, user_id, now):
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
    fmt = lambda d: d.strftime('%d.%m %H:%M')
    return (f'отказ был {fmt(rejected_at)} — повторная подача '
            f'не раньше {fmt(deadline)}')


def auto_close_unbanned(state, user_id, now):
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
    return [i for i in state.get('items', []) if i.get('status') == 'pending']


def user_pending(state, user_id):
    return [i for i in pending_items(state) if int(i.get('user_id') or 0) == int(user_id)]


def _clean_link(link):
    v = str(link or '').strip()
    if not v:
        return None
    if re.match(r'^(javascript|data|vbscript):', v, re.I):
        return None
    if not re.match(r'^https?://', v, re.I):
        v = 'https://' + v
    return v[:500]


def create_appeal(state, user_id, user_name, text, now, link=None):
    text = str(text or '').strip()
    if len(text) < 10:
        return None, f'слишком коротко — напишите подробнее (минимум 10 символов)'
    if len(text) > MAX_TEXT:
        return None, f'максимум {MAX_TEXT} символов'
    pend = user_pending(state, user_id)
    if pend:
        return None, (f'апелляция #{pend[0]["id"]} уже на рассмотрении — '
                      'дождитесь по ней решения')
    if len(user_pending(state, user_id)) >= MAX_PER_USER:
        return None, f'уже есть {MAX_PER_USER} открытых — дождитесь решения'
    blocked = cooldown_block(state, user_id, now)
    if blocked:
        return None, blocked
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
        'status': 'pending',
        'created_at': now.isoformat(),
        'reviewed_by': None,
        'reviewed_at': None,
        'reply': None,
        'rating': None,
        'rating_comment': None,
        'claimed_by': None,
        'escalated_at': None,
        'message_id': None,
        'card_channel_id': None,
        'ping_message_id': None,
        'thread_id': None,
    }
    # link больше не используем в простой схеме, но поле оставим для совместимости если передали
    if link:
        cleaned = _clean_link(link)
        if cleaned:
            item['link'] = cleaned
    state['next_id'] += 1
    state['items'].append(item)
    return item, None


def resolve_appeal(state, appeal_id, accept, reviewer_name, now, reply=None):
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
    body = f"**Апелляция #{item['id']}** от {item['user_name']} (`{item['user_id']}`)\n{item['text'][:400]}"
    return body


# ─── rating helpers (для совместимости с тестами и панелью) ─────────────────

def _rate_cell(*lines):
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
    e = discord.Embed(
        title='Оценка рассмотрения',
        color=COLOR_PENDING,
        timestamp=datetime.now(UTC))
    e.add_field(name='Апелляция', value=_rate_cell(f'#{item.get("id")}'), inline=False)
    e.add_field(name='Решение', value=_rate_cell(_rate_outcome(item)), inline=False)
    e.add_field(name='Как оценить', value='> Выберите в меню ниже — помогли или нет.', inline=False)
    e.set_footer(text=f'{guild_name} · {DM_FOOTER}' if guild_name else DM_FOOTER)
    return e


def _rate_thanks_embed(item, verb, comment=None):
    good = verb == 'up'
    e = discord.Embed(
        title='Спасибо за оценку',
        color=COLOR_YES if good else COLOR_NO,
        timestamp=datetime.now(UTC))
    e.add_field(name='Апелляция', value=_rate_cell(f'#{item.get("id")}'), inline=False)
    e.add_field(name='Оценка', value=_rate_cell(_rate_verdict(verb)), inline=False)
    if comment:
        e.add_field(name='Комментарий', value=_rate_cell(comment), inline=False)
    e.set_footer(text=DM_FOOTER)
    return e


def _rate_log_embed(guild, item, author, verb, comment=None):
    try:
        from cogs.logs import _styled_log_embed, _person_block, _bullet, _ts_lines
    except Exception as _ex:
        log.debug('appeals: logs import: %s', _ex)
        # фолбэк если logs не загружен
        def _styled_log_embed(guild, cat, title, fields=None, thumbnail=None, color=0):
            em = discord.Embed(title=title, color=color, timestamp=datetime.now(UTC))
            for n, v in (fields or []):
                em.add_field(name=n, value=v[:1024], inline=False)
            return em
        def _person_block(u): return str(u)
        def _bullet(*a): return '\n'.join('> ' + str(x) for x in a)
        def _ts_lines(v): return [str(v)[:16]] if v else []
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
    except Exception as _ex:
        log.debug('appeals: avatar: %s', _ex)
        av = None
    return _styled_log_embed(
        guild, 'mod', 'Оценка рассмотрения',
        fields=fields, thumbnail=av,
        color=COLOR_YES if verb == 'up' else COLOR_NO)


class AppealRateSelect(discord.ui.Select):
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
            await interaction.response.send_message('Эта апелляция ещё не решена — оценивать рано.', ephemeral=True)
            return
        if int(interaction.user.id) != int(item['user_id']):
            await interaction.response.send_message('Оценить может только автор апелляции.', ephemeral=True)
            return
        if item.get('rating'):
            await interaction.response.send_message('Оценка уже сохранена — спасибо.', ephemeral=True)
            return
        await interaction.response.send_modal(
            AppealRateModal(self.cog, self.guild_id, self.appeal_id, self.values[0], self.view))


class AppealRateView(discord.ui.View):
    def __init__(self, cog, guild_id, appeal_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.appeal_id = appeal_id
        self.add_item(AppealRateSelect(cog, guild_id, appeal_id))


class AppealRateModal(discord.ui.Modal):
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
            await interaction.response.send_message('Оценка уже сохранена или апелляция недоступна.', ephemeral=True)
            return
        cm = str(self.comment.value or '').strip()[:300]
        item['rating'] = self.verb
        item['rating_comment'] = cm or None
        self.cog._save(self.guild_id, state)
        try:
            _guild = self.cog.bot.get_guild(self.guild_id)
            _target = await self.cog._rating_channel(_guild) if _guild else None
            if _target is not None:
                try:
                    _re = _rate_log_embed(_guild, item, interaction.user, self.verb, cm)
                    await _target.send(embed=_re)
                except Exception as _ex:
                    log.debug('appeals: rate send: %s', _ex)
                    _verdict = _rate_verdict(self.verb)
                    _note = f'Апелляция #{item["id"]}\nОценка: "{_verdict}"'
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
            log.debug('appeals: скрыть меню оценки #%s: %s', self.appeal_id, _ex)
        await interaction.response.send_message(embed=thanks, ephemeral=True)


# ─── view с кнопками (простая схема: только принять/отклонить + взять в работу для совместимости) ───

class AppealView(discord.ui.View):
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
        # кнопка «Взять в работу» оставлена для совместимости с тестами и панелью,
        # но в простой схеме она НЕ открывает канал, только помечает кто взял
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
        try:
            from services.permission_acl import check_action as _acl
            if not _acl(self.guild_id, interaction.user, 'ban'):
                await interaction.response.send_message(
                    'Апелляции тебе не дал владелец (панель → Доступ → Права команд → Классические разрешения).',
                    ephemeral=True)
                return
        except Exception as _ex:
            log.debug('appeals claim acl: %s', _ex)
        gid = self.guild_id
        state = self.cog._load(gid)
        item = get_appeal(state, self.appeal_id)
        if item is None or item.get('status') != 'pending':
            await interaction.response.send_message('Апелляция уже решена — в работу не взять.', ephemeral=True)
            return
        uid = str(interaction.user.id)
        claim = item.get('claimed_by') or None
        btn = self._claim_btn()
        if claim and str(claim.get('id')) != uid:
            await interaction.response.send_message(f'Уже в работе у **{claim.get("name")}** — дождитесь его решения.', ephemeral=True)
            return
        now = datetime.now(UTC).isoformat()
        if claim:
            item['claimed_by'] = None
            note = 'Вы сняли апелляцию с работы — очередь снова общая.'
            if btn is not None:
                btn.label = 'Взять в работу'
                btn.style = discord.ButtonStyle.primary
        else:
            item['claimed_by'] = {'id': uid, 'name': str(interaction.user), 'at': now}
            note = 'Апелляция у вас в работе — решение ждут от вас.'
            if btn is not None:
                btn.label = f'В работе: {interaction.user.display_name}'
                btn.style = discord.ButtonStyle.secondary
        self.cog._save(gid, state)
        # В простой схеме канал НЕ открываем — просто помечаем
        embed = (interaction.message.embeds[0] if interaction.message and interaction.message.embeds else None)
        if embed is not None:
            tail = (f'В работе: {item["claimed_by"]["name"]}' if item.get('claimed_by') else 'Очередь общая')
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
        gid = self.guild_id
        try:
            from services.permission_acl import check_action
            if not check_action(gid, interaction.user, 'ban'):
                await interaction.response.send_message(
                    '🚫 Апелляции тебе не дал владелец (панель → Доступ → Права команд → Классические разрешения).',
                    ephemeral=True)
                return
        except Exception as _ex:
            log.debug('appeals: acl resolve: %s', _ex)
        if accept:
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
        item, err = resolve_appeal(state, self.appeal_id, accept, str(interaction.user), datetime.now(UTC))
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        self.cog._save(gid, state)
        unbanned = False
        member_present = False
        guild = self.cog.bot.get_guild(gid)
        if accept and guild is not None:
            await self.cog._log_unban_decision(guild, item, interaction.user.id,
                                               interaction.user.display_name or str(interaction.user))
        if accept and guild is not None:
            member = guild.get_member(item['user_id'])
            member_present = member is not None
            if member is not None:
                try:
                    from services import punish_roles as PR
                    rid = PR.role_for(gid, 'ban')
                    role = guild.get_role(rid) if rid else None
                    if role is not None and role in getattr(member, 'roles', []):
                        await member.remove_roles(role, reason=f'Апелляция #{item["id"]} принята')
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
                    from services import mute_state
                    await mute_state.clear_all_mutes(guild, member)
                except Exception as _ex:
                    log.debug('appeals: снятие изоляции/таймаута: %s', _ex)
            try:
                await guild.unban(discord.Object(id=item['user_id']), reason=f'Апелляция #{item["id"]} принята')
                unbanned = True
            except discord.NotFound:
                unbanned = True
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.error('appeals: unban %s на %s не удался: %s', item['user_id'], gid, _ex)
            if unbanned:
                try:
                    from services import staff_limits as _SL
                    _SL.record_hit(gid, interaction.user.id, 'unban', 1)
                except Exception as _ex:
                    log.debug('appeals: record unban: %s', _ex)
        _settings = settings_of(state)
        await self.cog._notify_user(
            item, accept, unbanned,
            cooldown_hours=_settings['cooldown_hours'],
            guild_name=str(getattr(guild, 'name', '') or ''),
            member_present=member_present,
            guild_id=gid)

        # Карточка решена — удаляем чтобы канал не замусоривался, история в панели
        # Сначала пробуем отредактировать для красоты, потом удаляем
        try:
            embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else None
            if embed is not None:
                embed.color = COLOR_YES if accept else COLOR_NO
                status = ('принята (разбанен)' if (accept and unbanned) else ('принята' if accept else 'отклонена'))
                embed.title = f'Апелляция #{item["id"]} — {status}'
                embed.add_field(name='Решение', value=f'{"✅ Принята" if accept else "❌ Отклонена"}: {interaction.user.display_name}', inline=False)
                if item.get('reply'):
                    embed.add_field(name='Комментарий', value=item['reply'][:300], inline=False)
                embed.set_footer(text=f'Рассмотрел: {interaction.user} · {item["id"]}')
                await interaction.message.edit(embed=embed, view=None)
            else:
                await interaction.message.edit(view=None)
        except Exception as _ex:
            log.debug('appeals: edit после решения: %s', _ex)

        # Удаляем карточку (простая схема: заявка в канал, решили — чистим)
        try:
            await interaction.message.delete()
        except Exception as _ex:
            log.debug('appeals: delete карточки: %s', _ex)

        # Чистим пинг роли если был
        try:
            if item.get('ping_message_id') and guild is not None:
                ch = self._guild_ch(guild, item.get('card_channel_id'))
                if ch is not None:
                    try:
                        msg = await ch.fetch_message(int(item['ping_message_id']))
                        await msg.delete()
                    except Exception as _ex:
                        log.debug('appeals: del ping: %s', _ex)
        except Exception as _ex:
            log.debug('appeals: cleanup ping: %s', _ex)

        status = ('принята (разбанен)' if (accept and unbanned) else ('принята' if accept else 'отклонена'))
        _done_note = f'Апелляция #{item["id"]} — {status}. Карточка удалена, история в панели.'
        try:
            await interaction.response.send_message(_done_note, ephemeral=True)
        except Exception as _ex:
            log.debug('appeals: response: %s', _ex)
            try:
                await interaction.followup.send(_done_note, ephemeral=True)
            except Exception as _ex2:
                log.debug('appeals: followup решения: %s', _ex2)


# ─── модалки подачи ─────────────────────────────────────────────────────────

class AppealModal(discord.ui.Modal):
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
            await interaction.followup.send('Вы не забанены на этом сервере — апелляция не нужна.', ephemeral=True)
            return
        item, err = await self.cog._submit_appeal(interaction.user, self.guild, self.text.value)
        if err:
            await interaction.followup.send(f'Не получилось: {err}.', ephemeral=True)
            return
        await interaction.followup.send(
            embed=discord.Embed(
                title=f'Апелляция #{item["id"]} отправлена',
                description=f'Модераторы сервера **{self.guild.name}** уже получили её в канале апелляций. Ответ придёт сюда, в личку.',
                color=COLOR_PENDING),
            ephemeral=True)


MENU_CUSTOM_ID = 'appeal:menu:open'


class AppealChannelModal(discord.ui.Modal):
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
            f'Апелляция **#{item["id"]}** отправлена в канал апелляций. Модераторы уже видят её.',
            ephemeral=True)


class AppealMenuSelect(discord.ui.Select):
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
        cog = interaction.client.get_cog('Appeals')
        if cog is None:
            await interaction.response.send_message('Модуль апелляций не загружен.', ephemeral=True)
            return
        await interaction.response.send_modal(AppealChannelModal(cog, interaction.guild))


class AppealMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(AppealMenuSelect())


DM_APPEAL_CUSTOM_ID = 'appeal:dm:open'


class AppealDMView(discord.ui.View):
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
            await interaction.response.send_message('Бот только что перезапускался — нажмите кнопку ещё раз.', ephemeral=True)
            return
        guild = cog._main_guild()
        if guild is None:
            await interaction.response.send_message('Бот ещё не настроен: владелец не указал главный сервер.', ephemeral=True)
            return
        try:
            banned = await cog._is_banned(guild, interaction.user)
        except Exception as _ex:
            log.debug('appeals dm: бан-чек: %s', _ex)
            banned = True
        if not banned:
            await interaction.response.send_message(f'Вы не забанены на сервере **{guild.name}** — апелляция не нужна.', ephemeral=True)
            return
        await interaction.response.send_modal(AppealModal(cog, guild))


# ─── Cog ────────────────────────────────────────────────────────────────────

class Appeals(commands.Cog):
    """Приём и разбор апелляций — простая схема: заявка в канал."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('appeals')
        self._views_restored = False
        self._stale_started = False

    @commands.Cog.listener()
    async def on_ready(self):
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
        try:
            self.bot.add_view(AppealDMView())
        except Exception as _ex:
            log.debug('appeals: dm-view: %s', _ex)
        rated = 0
        for guild in list(self.bot.guilds):
            state = self._load(guild.id)
            for item in state.get('items', []):
                if (item.get('status') in ('accepted', 'rejected') and not item.get('rating')):
                    try:
                        self.bot.add_view(AppealRateView(self, guild.id, item['id']))
                        rated += 1
                    except Exception as _ex:
                        log.debug('appeals: rate-view #%s: %s', item['id'], _ex)
        if rated:
            log.info('appeals: восстановлено %s rate-view после рестарта', rated)
        if restored:
            log.info('appeals: восстановлено %s view после рестарта', restored)
        # В простой схеме цикл напоминаний выключен — не спамим канал
        # (оставляем флаг чтобы on_ready не запускал повторно)

    def _load(self, guild_id):
        return self.db.get(guild_id, 'state', empty_state()) or empty_state()

    def _save(self, guild_id, state):
        self.db.set(guild_id, 'state', state)

    def _mod_context(self, state, guild_id, user_id):
        try:
            from services.appeal_context import build_context
            return build_context(state, guild_id, user_id)['line']
        except Exception as _ex:
            log.debug('appeals: контекст %s: %s', user_id, _ex)
            return 'история наказаний недоступна'

    async def _fire_panel_event(self, item):
        try:
            import asyncio as _asyncio
            from services.notification_dispatcher import notify_event
            _body = (f'#{item["id"]} от **{item["user_name"]}**: '
                     f'{item["text"][:120]}')
            await _asyncio.to_thread(notify_event, 'appeal_new', None, _body)
        except Exception as _ex:
            log.debug('appeals: событие колокольчика: %s', _ex)

    def _guild_ch(self, guild, cid):
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

    def _get_target_channel(self, guild, state):
        """Где живёт заявка — один канал апелляций. Просто."""
        try:
            from services.channel_routes import resolve_route, channel_on_guild
            for key in ('ban_appeal_channel', 'appeals_channel'):
                cid = int(resolve_route(guild.id, key, guild) or 0)
                if cid:
                    ch = channel_on_guild(guild, cid)
                    if ch is not None:
                        return ch
        except Exception as _ex:
            log.debug('appeals: маршрут канала: %s', _ex)
        cid = (state or {}).get('log_channel_id')
        ch = self._guild_ch(guild, cid) if cid else None
        if ch is not None:
            return ch
        try:
            from services.channel_routes import KNOWN_CHANNELS, channel_on_guild
            for k in ('ban_appeal_channel', 'appeals_channel'):
                guess = int(KNOWN_CHANNELS.get(k) or 0)
                if guess:
                    ch = channel_on_guild(guild, guess)
                    if ch is not None:
                        return ch
        except Exception as _ex:
            log.debug('appeals: known channel: %s', _ex)
        if getattr(guild, 'system_channel', None) is not None:
            return guild.system_channel
        for ch in getattr(guild, 'text_channels', []):
            try:
                if ch.permissions_for(guild.me).send_messages:
                    return ch
            except Exception as _ex:
                log.debug('appeals: permissions_for: %s', _ex)
                continue
        return None

    def _log_channel(self, guild, state):
        return self._get_target_channel(guild, state)

    async def _card_channel(self, guild, state):
        ch = self._get_target_channel(guild, state)
        return ch, False

    async def _appeal_channel(self, guild):
        if guild is None:
            return None
        try:
            state = self._load(guild.id)
            return self._get_target_channel(guild, state)
        except Exception as _ex:
            log.debug('appeals: _appeal_channel compat: %s', _ex)
            return None

    async def _rating_channel(self, guild):
        try:
            from services.channel_routes import APPEAL_RATING_CHANNEL_ID as _RID, channel_on_guild as _on_g
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
            except Exception as _ex:
                log.debug('appeals: rating fetch: %s', _ex)
        return None

    async def _open_appeal_channel(self, guild, user, fallback_channel=None):
        """Упрощённая схема: ничего никому не открываем."""
        ch = await self._appeal_channel(guild)
        return 'skipped', ch

    async def _make_return_invite(self, guild, settings):
        return None

    async def _log_unban_decision(self, guild, item, mod_id, mod_name):
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
            except Exception as _ex:
                log.debug('appeals: get_member: %s', _ex)
                user_obj = None
            if user_obj is None:
                try:
                    user_obj = await self.bot.fetch_user(int(item['user_id']))
                except Exception as _ex:
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
        """Удалить карточку решённой апелляции — канал остаётся чистым."""
        # если передали message из клика — уже удалили в _resolve
        if message is not None:
            try:
                await message.delete()
            except Exception as _ex:
                log.debug('appeals: delete via message: %s', _ex)
            return True

        # удаление по сохранённым id (панель)
        async def _del_in(ch, mid):
            if ch is None or not mid:
                return False
            try:
                msg = await ch.fetch_message(int(mid))
                await msg.delete()
                return True
            except Exception as _ex:
                log.debug('appeals: del msg %s: %s', mid, _ex)
                return False

        deleted = False
        if guild is not None and item.get('message_id'):
            try:
                cid = int(item.get('card_channel_id') or 0)
            except (TypeError, ValueError):
                cid = 0
            ch = self._guild_ch(guild, cid) if cid else self._get_target_channel(guild, state or {})
            deleted = await _del_in(ch, item.get('message_id'))

        # пинг тоже чистим
        if guild is not None and item.get('ping_message_id'):
            try:
                cid = int(item.get('card_channel_id') or 0)
            except (TypeError, ValueError):
                cid = 0
            ch = self._guild_ch(guild, cid) if cid else self._get_target_channel(guild, state or {})
            await _del_in(ch, item.get('ping_message_id'))

        # ветка если была (совместимость)
        try:
            tid = int(item.get('thread_id') or 0)
        except (TypeError, ValueError):
            tid = 0
        if tid and guild is not None:
            th = self._guild_ch(guild, tid)
            if th is not None:
                try:
                    await th.delete()
                    deleted = True
                except Exception as _ex:
                    log.debug('appeals: del thread %s: %s', tid, _ex)
        return deleted

    def _dm_channel_line(self, opened, channel):
        name = getattr(channel, 'name', '') or 'апелляции'
        return f'Заявка в канале **#{name}** — куратор посмотрит и решит.'

    async def _ping_mod_role(self, target_channel, settings, item):
        rid = int(settings.get('ping_role_id') or 0)
        if not rid or target_channel is None:
            return None
        guild = getattr(target_channel, 'guild', None)
        get_role = getattr(guild, 'get_role', None)
        if callable(get_role) and get_role(rid) is None:
            return None
        try:
            return await target_channel.send(
                f'<@&{rid}> — новая апелляция **#{item["id"]}** ожидает решения.',
                allowed_mentions=discord.AllowedMentions(roles=True))
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.debug('appeals: пинг роли #%s: %s', item.get('id'), _ex)
            return None

    async def _escalate_overdue(self, guild, state, now):
        return 0

    async def _stale_loop(self):
        # В простой схеме напоминания выключены — не спамим
        return

    def _strip_appeal_embed_texts(self, embed):
        embed.title = None
        embed.description = None
        try:
            embed.clear_fields()
        except Exception as _ex:
            log.debug('appeals: clear_fields: %s', _ex)
        try:
            embed.remove_author()
        except Exception as _ex:
            log.debug('appeals: remove_author: %s', _ex)
        try:
            embed.remove_footer()
        except Exception as _ex:
            log.debug('appeals: remove_footer: %s', _ex)

    async def _paint_appeal_card(self, embed, item, appearance):
        # _paint_appeal_card — единый хелпер для обоих путей подачи (ЛС и канал)
        # Оба пути подачи рисуют карточку одним хелпером _paint_appeal_card
        file = None
        try:
            if appearance.get('mode') == 'url' and appearance.get('url'):
                data, fname = await fetch_remote_image(appearance['url'])
                if data:
                    comp = render_url_card(
                        data, appeal_id=item['id'],
                        user_name=item['user_name'], text=item['text'],
                        theme=appearance.get('theme'))
                    payload, name = ((comp, appeal_card_filename(item['id'])) if comp else (data, fname))
                    file = discord.File(io.BytesIO(payload), filename=name)
                    embed.set_image(url=f'attachment://{name}')
                    if comp:
                        self._strip_appeal_embed_texts(embed)
                else:
                    # если хост не отдал файл — картинка не скачалась, уходим на ссылку
                    log.debug('appeals: картинка не скачалась %s — fallback на URL', appearance.get('url'))
                    embed.set_image(url=appearance['url'])
            elif appearance.get('mode') == 'auto':
                png = render_appeal_card(
                    appeal_id=item['id'], user_name=item['user_name'],
                    text=item['text'],
                    theme=appearance.get('theme'))
                if png:
                    fn = appeal_card_filename(item['id'])
                    file = discord.File(io.BytesIO(png), filename=fn)
                    embed.set_image(url=f'attachment://{fn}')
                    self._strip_appeal_embed_texts(embed)
        except Exception as _ex:
            log.debug('appeals: карточка-картинка #%s: %s', item.get('id'), _ex)
        return file

    # совместимость: второй путь тоже через _paint_appeal_card (для тестов)
    async def _paint_appeal_card_compat(self, *a, **kw):
        return await self._paint_appeal_card(*a, **kw)

    async def _as_member(self, guild, user):
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
            except Exception as _ex:
                log.debug('appeals: fetch_member %s: %s', uid, _ex)
        return user

    async def _submit_channel_appeal(self, user, guild, text, link=None, channel=None):
        guild_id = guild.id
        state = self._load(guild_id)
        item, err = create_appeal(state, user.id, str(user), text, datetime.now(UTC), link=link)
        if err:
            return None, err
        self._save(guild_id, state)

        embed = discord.Embed(
            title=f'Апелляция #{item["id"]} — новая',
            description=item['text'],
            color=COLOR_PENDING, timestamp=datetime.now(UTC))
        embed.set_author(name=str(user),
                         icon_url=user.display_avatar.url if getattr(user, 'display_avatar', None) else None)
        embed.add_field(name='Участник', value=f'{user.mention} · `{user.id}`', inline=False)
        embed.add_field(name='Контекст', value=self._mod_context(state, guild.id, user.id), inline=False)
        embed.set_footer(text=f'appeal #{item["id"]} · {guild.name}')

        view = AppealView(self, guild_id, item['id'])
        # Картинка если настроена
        try:
            appearance = normalize_appearance(state.get('appearance'))
            card_file = await self._paint_appeal_card(embed, item, appearance)
        except Exception as _ex:
            log.debug('appeals: карточка-картинка #%s: %s', item['id'], _ex)
            card_file = None

        target = self._get_target_channel(guild, state)
        if target is not None:
            send_kw = {'embed': embed, 'view': view}
            if card_file is not None:
                send_kw['file'] = card_file
            try:
                msg = await target.send(**send_kw)
                item['message_id'] = msg.id
                item['card_channel_id'] = getattr(target, 'id', None)
                ping = await self._ping_mod_role(target, settings_of(state), item)
                item['ping_message_id'] = getattr(ping, 'id', None)
                self._save(guild_id, state)
                await self._fire_panel_event(item)
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.error('appeals: карточка #%s не ушла: %s', item['id'], _ex)

        try:
            dm = _dm_embed('submitted', item, str(guild.name))
            dm.description = (f'Заявка **#{item["id"]}** отправлена в канал **#{getattr(target, "name", "апелляции")}**. '
                              'Куратор посмотрит и решит. Ответ придёт сюда, в личку.')
            await user.send(embed=dm)
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.debug('appeals: ЛС подтверждения #%s: %s', item['id'], _ex)

        return item, None

    async def _submit_appeal(self, user, guild, text, link=None):
        return await self._submit_channel_appeal(user, guild, text, link=link, channel=None)

    def _main_guild(self):
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
        try:
            await guild.fetch_ban(discord.Object(id=user.id))
            return True
        except discord.NotFound as _ex:
            log.debug('appeals: not banned %s: %s', user.id, _ex)
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.warning('appeals: ban-check %s на %s: %s', user.id, guild.id, _ex)
            return True
        member = guild.get_member(user.id)
        if member is not None:
            try:
                from services import punish_roles as PR
                rid = PR.role_for(guild.id, 'ban')
                if rid and any(r.id == rid for r in getattr(member, 'roles', [])):
                    return True
            except Exception as _ex:
                log.debug('appeals: isolation check: %s', _ex)
        return False

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        try:
            state = self._load(guild.id)
            closed = auto_close_unbanned(state, user.id, datetime.now(UTC))
            if not closed:
                return
            self._save(guild.id, state)
            for item in closed:
                try:
                    dm = _dm_embed('closed', item, str(guild.name))
                    dm.description = 'Бан снят вручную — апелляция закрыта.'
                    await user.send(embed=dm)
                except Exception as _ex:
                    log.debug('appeals: ЛС автозакрытия #%s: %s', item['id'], _ex)
        except Exception as _ex:
            log.debug('appeals: on_member_unban: %s', _ex)

    async def publish_appeal_menu(self, channel):
        if channel is None:
            return False, 'Канал не найден'
        guild = channel.guild
        state = self._load(guild.id)
        embed = discord.Embed(
            title='⚖ Апелляции',
            description=(
                'Несогласны с наказанием?\n'
                'Нажмите **«Подать апелляцию»** ниже — откроется окно.\n\n'
                'Ваша заявка уйдёт прямо в канал апелляций, куратор посмотрит и решит. '
                'Никаких открытий доступов — просто заявка в этот канал.'),
            color=0xF1C40F,
            timestamp=datetime.now(UTC))
        embed.set_footer(text=f'{guild.name} · апелляции',
                         icon_url=guild.icon.url if guild.icon else None)
        try:
            msg = await channel.send(embed=embed, view=AppealMenuView())
            state['menu'] = {'channel_id': channel.id, 'message_id': msg.id, 'webhook_id': 0}
            self._save(guild.id, state)
            return True, f'Меню опубликовано в {channel.mention}'
        except (discord.Forbidden, discord.HTTPException) as _ex:
            return False, f'Бот не может писать в этот канал: {_ex}'

    async def _notify_user(self, item, accept, unbanned, cooldown_hours=0,
                           guild_name='', member_present=False, invite_url=None,
                           guild_id=0):
        try:
            user = await self.bot.fetch_user(item['user_id'])
        except (discord.NotFound, discord.HTTPException):
            return
        if accept:
            embed = _dm_embed('accepted', item, guild_name)
            if unbanned:
                embed.description = f'Бан на сервере **{guild_name}** снят — апелляция принята. Добро пожаловать назад!'
            else:
                embed.description = f'Ваша апелляция на сервере **{guild_name}** принята.'
        else:
            embed = _dm_embed('rejected', item, guild_name)
            embed.description = 'К сожалению, в этот раз — нет.'
            if item.get('text'):
                embed.add_field(name='Ваша апелляция', value=str(item['text'])[:300], inline=False)
            if item.get('reply'):
                embed.add_field(name='Комментарий модератора', value=str(item['reply'])[:300], inline=False)
            if cooldown_hours > 0:
                reviewed = _parse_ts(item.get('reviewed_at'))
                if reviewed is not None:
                    from datetime import timedelta
                    retry = reviewed + timedelta(hours=cooldown_hours)
                    embed.add_field(name='Повторная подача', value=f'не раньше **{retry.strftime("%d.%m %H:%M")}**', inline=False)
        try:
            await user.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.debug('appeals: ЛС %s закрыты: %s', item['user_id'], _ex)


async def setup(bot):
    cog = Appeals(bot)
    await bot.add_cog(cog)
