# -*- coding: utf-8 -*-
"""
Hakumo — Система репортов (ТЗ 2026-08-26)
------------------------------------------
/report -> приватная ветка в канале репортов с панелью управления:
Select-меню для режима обсуждения, слова, вынесения решения (дефолт
по рецидивам / индивидуальное + срок). Переписка при закрытии сжимается
zlib и уходит в архив (services/reports_core). /my_violations — мои
нарушения (обжалование наказаний — глобальная /апелляция в ЛС боту).

Хранение: SQLite data/reports.db + data/reports_<gid>.json (без Postgres —
его на VDS нет, данных мизер). Оформление: чистые эмбеды без эмодзи.
"""
import json as _json
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from logger import get_logger

_log = get_logger('reports')

from services import reports_core as RC

WORD_HINT_EVERY = 10.0  # сек между подсказками «слово не ваше» одному юзеру
_word_hint_ts = {}


def _fire_new_event(event, body):
    """Событие в колокольчик панели (веб). fail-safe: уведомления — не ядро.

    notify_event делает синхронный HTTP (webhook) и запись файла; вызывается
    из async-команд, поэтому тяжёлую часть уводим в рабочий поток — без
    блокировки event loop."""
    try:
        import asyncio as _asyncio
        from services.notification_dispatcher import notify_event
        try:
            _asyncio.get_running_loop()
        except RuntimeError:
            # нет активного loop'а (вызов из синхронного кода) — шлём напрямую
            notify_event(event, None, body)
        else:
            _asyncio.get_running_loop().run_in_executor(
                None, lambda: notify_event(event, None, body))
    except Exception as _ex:
        _log.debug('reports: событие %s: %s', event, _ex)


def _is_mod(member, cfg) -> bool:
    if member is None:
        return False
    if member.guild_permissions.manage_messages:
        return True
    rid = str(cfg.get('mod_role_id') or '')
    return bool(rid) and any(str(r.id) == rid for r in member.roles)


# Вердикт репорта → ключ «классического» разрешения: mute в репорте —
# это timeout (как «Мут (чат + войс)» в /modpanel), ban — «Бан», kick — «Кик».
_VERDICT_ACL = {'mute': 'timeout', 'ban': 'ban', 'kick': 'kick'}


def _verdict_allowed(guild, user, kind) -> bool:
    """Разрешено ли модератору применить вердикт kind классическими правами."""
    key = _VERDICT_ACL.get(kind)
    if not key or guild is None or user is None:
        return True
    try:
        from services.permission_acl import check_action
        return bool(check_action(guild.id, user, key))
    except Exception as _ex:
        _log.debug('reports: verdict acl: %s', _ex)
        return True


def _verdict_limit_denied(guild, user, kind):
    """Лимиты стаффа для вердикта: None — можно, иначе готовый текст отказа.

    Тот же счётчик, что у /mute, /ban и /kick: вердикт по репорту —
    полноценное наказание и списывает расходку модератора.
    """
    key = _VERDICT_ACL.get(kind)
    if not key or guild is None or user is None:
        return None
    try:
        from services import staff_limits as _SL
        ok, deny = _SL.check_action(guild, user, key)
        return None if ok else deny
    except Exception as _ex:
        _log.debug('reports: verdict limit: %s', _ex)
        return None


def _record_verdict(guild, user, kind):
    """Успешный вердикт — в счётчик лимитов модератора."""
    key = _VERDICT_ACL.get(kind)
    if not key or guild is None or user is None:
        return
    try:
        from services import staff_limits as _SL
        _SL.record_hit(guild.id, user.id, key, 1)
    except Exception as _ex:
        _log.debug('reports: verdict record: %s', _ex)


def _any_verdict_allowed(guild, user) -> bool:
    """Есть ли у модератора хоть одно действие для решения репорта."""
    return any(_verdict_allowed(guild, user, k) for k in _VERDICT_ACL)


def _cfg(guild_id) -> dict:
    return RC.load_cfg(guild_id)


async def _dm(user, embed) -> bool:
    try:
        await user.send(embed=embed)
        return True
    except Exception:
        return False


def _violations_field(guild_id, user_id, cfg) -> str:
    vs = RC.violations_of(guild_id, user_id, cfg.get('expiry_days', 90))
    if not vs:
        return 'Нарушений не было'
    lines = []
    for v in vs[-5:]:
        when = datetime.fromtimestamp(v['created'], timezone.utc).strftime('%d.%m.%Y')
        lines.append(f"{RC.KIND_LABELS.get(v['kind'], v['kind'])} · {when}"
                     + (f" · {v['hours']:.0f} ч" if v.get('hours') else ''))
    tail = f'\n…и ещё {len(vs) - 5}' if len(vs) > 5 else ''
    return '\n'.join(lines) + tail


# ═══════════════════════════════════════════════════════════════════
#  ПАНЕЛЬ УПРАВЛЕНИЯ ТИКЕТОМ (персистентная)
# ═══════════════════════════════════════════════════════════════════
class ReportPanelView(discord.ui.View):
    """Главное сообщение в ветке: 5 кнопок, сабменю — Select'ами."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _mod_only(self, interaction) -> bool:
        cfg = _cfg(interaction.guild_id)
        if not _is_mod(interaction.user, cfg):
            await interaction.response.send_message(
                'Панель доступна модераторам.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Выбрать режим', style=discord.ButtonStyle.secondary,
                       custom_id='rpt_mode')
    async def btn_mode(self, interaction, button):
        if not await self._mod_only(interaction):
            return
        await interaction.response.send_message(
            'Режим обсуждения:', view=ModeSelectView(), ephemeral=True)

    @discord.ui.button(label='Дать слово', style=discord.ButtonStyle.secondary,
                       custom_id='rpt_word')
    async def btn_word(self, interaction, button):
        if not await self._mod_only(interaction):
            return
        t = RC.ticket_get(interaction.channel_id)
        if not t:
            await interaction.response.send_message(
                'Это не ветка репорта.', ephemeral=True)
            return
        await interaction.response.send_message(
            'Кому дать слово:', view=WordSelectView(t), ephemeral=True)

    @discord.ui.button(label='Позвать модератора', style=discord.ButtonStyle.secondary,
                       custom_id='rpt_call')
    async def btn_call(self, interaction, button):
        if not await self._mod_only(interaction):
            return
        cfg = _cfg(interaction.guild_id)
        rid = cfg.get('mod_role_id')
        ping = f'<@&{rid}> ' if rid else ''
        e = discord.Embed(
            title='Запрошен дополнительный модератор',
            description=f'Ветку вызвал {interaction.user.mention}. '
                        'Подключайтесь к рассмотрению.',
            color=0x5865F2)
        await interaction.response.send(f'{ping}', embed=e)

    @discord.ui.button(label='Вынести решение', style=discord.ButtonStyle.primary,
                       custom_id='rpt_verdict')
    async def btn_verdict(self, interaction, button):
        if not await self._mod_only(interaction):
            return
        t = RC.ticket_get(interaction.channel_id)
        if not t or t.get('closed'):
            await interaction.response.send_message(
                'Ветка не активна.', ephemeral=True)
            return
        # Классические разрешения: без «Бана»/«Кика»/«Таймаута» решение
        # не выносят — кнопка живёт, но честно объясняет, чего не хватает.
        if not _any_verdict_allowed(interaction.guild, interaction.user):
            await interaction.response.send_message(
                'Тебе не дано ни одного действия для решения (панель → '
                'Доступ → Права команд → Классические разрешения).',
                ephemeral=True)
            return
        await interaction.response.send_message(
            'Тип решения:', view=VerdictTypeSelect(), ephemeral=True)

    @discord.ui.button(label='Закрыть тикет', style=discord.ButtonStyle.danger,
                       custom_id='rpt_close')
    async def btn_close(self, interaction, button):
        if not await self._mod_only(interaction):
            return
        await interaction.response.send_message(
            'Переписка сожмётся в архив, ветка удалится. Закрываем?',
            view=CloseConfirmView(), ephemeral=True)


# ── Select: режим обсуждения ────────────────────────────────────────
class ModeSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.select(cls=discord.ui.Select,
                       placeholder='Как идёт обсуждение',
                       options=[
                           discord.SelectOption(label='По очереди', value='turn',
                                                description='Обвинитель и обвиняемый говорят по очереди, слово передаёт модератор'),
                           discord.SelectOption(label='Свободный', value='free',
                                                description='Писать могут все участники'),
                           discord.SelectOption(label='Слово вручную', value='manual',
                                                description='Модератор выбирает, кто говорит'),
                       ])
    async def choose(self, interaction, select):
        t = RC.ticket_get(interaction.channel_id)
        if not t:
            await interaction.response.send_message('Это не ветка репорта.',
                                                    ephemeral=True)
            return
        mode = select.values[0]
        word = t['reporter_id'] if mode != 'free' else ''
        RC.ticket_set(interaction.channel_id, mode=mode, word_id=word)
        labels = {'turn': 'По очереди', 'free': 'Свободный', 'manual': 'Слово вручную'}
        who = f"Слово: <@{word}>." if word else 'Писать могут все.'
        e = discord.Embed(title='Режим обсуждения',
                          description=f'**{labels[mode]}**\n{who}',
                          color=0x5865F2)
        await interaction.response.send_message(embed=e)
        try:
            await interaction.channel.edit(auto_archive_duration=10080)
        except Exception as _ae:
            _log.debug('auto_archive_duration: подавлено: %s', _ae)


# ── Select: дать слово ──────────────────────────────────────────────
class WordSelectView(discord.ui.View):
    def __init__(self, ticket):
        super().__init__(timeout=180)
        self.ticket = ticket
        opts = []
        for uid, label in ((ticket['reporter_id'], 'Обвинитель'),
                           (ticket['accused_id'], 'Обвиняемый')):
            opts.append(discord.SelectOption(label=label, value=str(uid)))
        for uid in ticket.get('witnesses', [])[:3]:
            opts.append(discord.SelectOption(label=f'Свидетель {uid}', value=str(uid)))
        self.select.options = opts[:25]

    @discord.ui.select(cls=discord.ui.Select, placeholder='Кому дать слово')
    async def choose(self, interaction, select):
        uid = select.values[0]
        RC.ticket_set(interaction.channel_id, word_id=uid)
        try:
            await interaction.channel.add_user(
                await interaction.guild.fetch_member(int(uid)))
        except Exception as _ex:
            _log.debug('WordSelect.add_user: %s', _ex)
        e = discord.Embed(title='Слово передано',
                          description=f'Говорит <@{uid}>. Остальные сообщения удаляются.',
                          color=0x2ECC71)
        await interaction.response.send_message(embed=e)


# ── Select: тип решения ─────────────────────────────────────────────
class VerdictTypeSelect(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.select(cls=discord.ui.Select, placeholder='Тип решения',
                       options=[
                           discord.SelectOption(label='Дефолтное (по рецидивам)', value='default',
                                                description='Рассчитывается автоматически по числу нарушений'),
                           discord.SelectOption(label='Индивидуальное', value='custom',
                                                description='Модератор сам выбирает наказание и срок'),
                       ])
    async def choose(self, interaction, select):
        t = RC.ticket_get(interaction.channel_id)
        if not t:
            return await interaction.response.send_message('Это не ветка репорта.',
                                                           ephemeral=True)
        if select.values[0] == 'default':
            cfg = _cfg(interaction.guild_id)
            past = RC.violations_of(interaction.guild_id, t['accused_id'],
                                    cfg.get('expiry_days', 90))
            step = RC.compute_default(cfg['ladder'], len(past) + 1)
            pending = {'kind': step['kind'], 'hours': step.get('hours', 0),
                       'label': step.get('label') or RC.KIND_LABELS.get(step['kind'], ''),
                       'source': 'default'}
            RC.ticket_set(interaction.channel_id,
                          verdict=_json.dumps(pending, ensure_ascii=False))
            await interaction.response.send_message(
                embed=discord.Embed(
                    title='Дефолтное наказание',
                    description=(f"Нарушений в сроке давности: **{len(past)}** — это "
                                 f"**{len(past) + 1}-е**.\nПорог лестницы: {step['label']}."),
                    color=0xF39C12),
                view=ApplyVerdictView(), ephemeral=True)
        else:
            await interaction.response.send_message(
                'Наказание:', view=PunishSelectView(), ephemeral=True)


class PunishSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.select(cls=discord.ui.Select, placeholder='Наказание',
                       options=[discord.SelectOption(label=v, value=k)
                                for k, v in RC.KIND_LABELS.items()
                                if k != 'none'] +
                               [discord.SelectOption(label='Без наказания', value='none')])
    async def choose(self, interaction, select):
        kind = select.values[0]
        if kind in ('mute', 'ban'):
            await interaction.response.send_message(
                'Срок:', view=DurationSelectView(kind), ephemeral=True)
            return
        label = RC.KIND_LABELS.get(kind, kind)
        pending = {'kind': kind, 'hours': 0, 'label': label, 'source': 'custom'}
        RC.ticket_set(interaction.channel_id,
                      verdict=_json.dumps(pending, ensure_ascii=False))
        await interaction.response.send_message(
            embed=discord.Embed(title='Решение к применению',
                                description=f'**{label}**', color=0xF39C12),
            view=ApplyVerdictView(), ephemeral=True)


class DurationSelectView(discord.ui.View):
    def __init__(self, kind):
        super().__init__(timeout=180)
        self.kind = kind
        self.select.options = [
            discord.SelectOption(label=name,
                                 value=str(int(hours)) if hours else '0',
                                 description='До развотда' if not hours else '')
            for name, hours in RC.DURATIONS]

    @discord.ui.select(cls=discord.ui.Select, placeholder='Срок')
    async def choose(self, interaction, select):
        hours = float(select.values[0])
        name = next((n for n, h in RC.DURATIONS
                     if int(h) == int(hours)), 'срок')
        label = f"{RC.KIND_LABELS[self.kind]} · {name}"
        pending = {'kind': self.kind, 'hours': hours, 'label': label,
                   'source': 'custom'}
        RC.ticket_set(interaction.channel_id,
                      verdict=_json.dumps(pending, ensure_ascii=False))
        await interaction.response.send_message(
            embed=discord.Embed(title='Решение к применению',
                                description=f'**{label}**', color=0xF39C12),
            view=ApplyVerdictView(), ephemeral=True)


class ApplyVerdictView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label='Применить', style=discord.ButtonStyle.success,
                       custom_id='rpt_apply')
    async def apply(self, interaction, button):
        await Reports.apply_verdict(interaction)

    @discord.ui.button(label='Отмена', style=discord.ButtonStyle.secondary,
                       custom_id='rpt_cancel')
    async def cancel(self, interaction, button):
        RC.ticket_set(interaction.channel_id, verdict='')
        await interaction.response.edit_message(
            content='Отменено.', view=None, embed=None)


class CloseConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label='Закрыть и архивировать', style=discord.ButtonStyle.danger,
                       custom_id='rpt_close_yes')
    async def yes(self, interaction, button):
        await Reports.close_ticket(interaction)

    @discord.ui.button(label='Отмена', style=discord.ButtonStyle.secondary,
                       custom_id='rpt_close_no')
    async def no(self, interaction, button):
        await interaction.response.edit_message(content='Отменено.', view=None)


# ═══════════════════════════════════════════════════════════════════
#  ЖАЛОБЫ КАРТОЧКОЙ В КАНАЛ МОДЕРАЦИИ (заказ владельца 2026-08-31)
#  ─────────────────────────────────────────────────────────────────
#  /report отправляет карточку (скрин/видео вложением) в выбранный
#  владельцем канал репортов (панель или /report-setup). Если канал не
#  задан — бот создаёт закрытый #модерация как запасной вариант.
#  Под карточкой кнопки: Принять / Отклонить / Открыть разбор.
#  Карточка сразу тегает роль модераторов (отдельной кнопки-вызова нет —
#  тег уходит автоматически при отправке жалобы).
# ═══════════════════════════════════════════════════════════════════
MOD_CHANNEL_NAME = 'модерация'


async def _ensure_mod_channel(guild, mod_role):
    """Канал модерации: найти по имени/конфигу или создать закрытый.

    Возвращает (channel, created:bool). Канал видят только модераторы и
    бот; @everyone прав на чтение не имеет.
    """
    # 1) уже настроенный канал репортов из конфига
    cfg = _cfg(guild.id)
    cid = cfg.get('channel_id')
    if cid:
        ch = guild.get_channel(int(cid))
        if ch is not None:
            return ch, False
    # 2) канал с известным именем
    ch = discord.utils.get(guild.text_channels, name=MOD_CHANNEL_NAME)
    if ch is not None:
        return ch, False
    # 3) создаём закрытый канал модерации
    over = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False, read_messages=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, read_messages=True, send_messages=True,
            embed_links=True, attach_files=True, manage_messages=True,
            manage_channels=True, read_message_history=True,
            create_private_threads=True, manage_threads=True),
    }
    if mod_role is not None:
        over[mod_role] = discord.PermissionOverwrite(
            view_channel=True, read_messages=True, send_messages=True,
            manage_messages=True, read_message_history=True,
            create_private_threads=True, manage_threads=True)
    try:
        ch = await guild.create_text_channel(
            MOD_CHANNEL_NAME, overwrites=over,
            topic='Жалобы участников и их разбор. Видно только модерации.',
            reason='Система репортов: канал модерации не найден — создан')
        return ch, True
    except Exception as ex:
        _log.warning('reports: не удалось создать канал модерации: %s', ex)
        return None, False


def _mod_role_from_cfg(guild):
    """Роль модераторов из конфига репортов (панель/`/report-setup`)."""
    rid = str(_cfg(guild.id).get('mod_role_id') or '')
    if rid.isdigit():
        role = guild.get_role(int(rid))
        if role is not None:
            return role
    return None


class ReportCardView(discord.ui.View):
    """Кнопки под карточкой жалобы в канале модерации (персистентные)."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _mod_only(self, interaction) -> bool:
        if not _is_mod(interaction.user, _cfg(interaction.guild_id)):
            await interaction.response.send_message(
                'Разбирать жалобы могут модераторы.', ephemeral=True)
            return False
        return True

    async def _card_state(self, interaction):
        """Запись жалобы по сообщению-карточке (kind='card')."""
        return RC.ticket_get(interaction.message.id)

    @discord.ui.button(label='Принять', style=discord.ButtonStyle.success,
                       emoji='✅', custom_id='rcard_accept')
    async def accept(self, interaction, button):
        if not await self._mod_only(interaction):
            return
        t = await self._card_state(interaction)
        RC.ticket_set(interaction.message.id,
                      verdict=_json.dumps({'kind': 'accepted',
                                           'label': 'Жалоба принята'}),
                      closed=datetime.now(timezone.utc).timestamp())
        e = interaction.message.embeds[0] if interaction.message.embeds else None
        if e is not None:
            e.color = discord.Color(0x2ECC71)
            e.add_field(name='Статус',
                        value=f'✅ Принято — {interaction.user.mention}',
                        inline=False)
        for b in self.children:
            b.disabled = b.custom_id not in ('rcard_thread',)
        await interaction.response.edit_message(
            embed=e, view=self,
            content=f'{interaction.message.content or ""}'.strip())
        await interaction.followup.send(
            f'Жалоба принята {interaction.user.mention}. Откройте разбор '
            'кнопкой «Открыть разбор», если нужна отдельная ветка.',
            ephemeral=True)

    @discord.ui.button(label='Отклонить', style=discord.ButtonStyle.danger,
                       emoji='❌', custom_id='rcard_reject')
    async def reject(self, interaction, button):
        if not await self._mod_only(interaction):
            return
        RC.ticket_set(interaction.message.id,
                      verdict=_json.dumps({'kind': 'none',
                                           'label': 'Отклонено'}),
                      closed=datetime.now(timezone.utc).timestamp())
        e = interaction.message.embeds[0] if interaction.message.embeds else None
        if e is not None:
            e.color = discord.Color(0x99AAB5)
            e.add_field(name='Статус',
                        value=f'❌ Отклонено — {interaction.user.mention}',
                        inline=False)
        for b in self.children:
            b.disabled = True
        await interaction.response.edit_message(embed=e, view=self)

    @discord.ui.button(label='Открыть разбор', style=discord.ButtonStyle.primary,
                       emoji='🧵', custom_id='rcard_thread')
    async def open_thread(self, interaction, button):
        if not await self._mod_only(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        t = await self._card_state(interaction)
        accused_name = ''
        if t:
            member = interaction.guild.get_member(int(t['accused_id']))
            accused_name = member.display_name if member else 'участник'
        try:
            thread = await interaction.message.create_thread(
                name=f'разбор · {accused_name[:40]}',
                auto_archive_duration=10080,
                reason=f'Разбор жалобы от модератора {interaction.user}')
        except Exception as ex:
            return await interaction.followup.send(
                f'Не удалось создать ветку: {ex}', ephemeral=True)
        if t:
            for uid in (t.get('reporter_id'), t.get('accused_id')):
                try:
                    m = await interaction.guild.fetch_member(int(uid))
                    await thread.add_user(m)
                except Exception as _sx:
                    _log.debug('rcard add_user: %s', _sx)
            RC.ticket_set(interaction.message.id, thread_id=str(thread.id))
        await thread.send(
            f'Ветка разбора жалобы. {interaction.user.mention} ведёт '
            'модерацию. Здесь доступна полная панель: режим слова, '
            'решение (варн/мут/кик/бан) и архивация.',
            view=ReportPanelView())
        await interaction.followup.send(
            f'Ветка разбора создана: {thread.mention}', ephemeral=True)

# ═══════════════════════════════════════════════════════════════════
#  КОГ
# ═══════════════════════════════════════════════════════════════════
class Reports(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        RC.db()  # создать таблицы
        self.bot.add_view(ReportPanelView())   # панель в ветке разбора
        self.bot.add_view(ReportCardView())    # карточки жалоб в канале модерации
        _log.info('Reports: панели зарегистрированы')

    # ── применение решения ──────────────────────────────────────────
    @classmethod
    async def apply_verdict(cls, interaction):
        t = RC.ticket_get(interaction.channel_id)
        if not t or not t.get('verdict'):
            return await interaction.response.send_message(
                'Решение не выбрано.', ephemeral=True)
        try:
            v = _json.loads(t['verdict'])
        except Exception:
            return await interaction.response.send_message(
                'Решение повреждено, выберите заново.', ephemeral=True)
        guild = interaction.guild
        cfg = _cfg(guild.id)
        reason = f'Решение по репорту (ветка {interaction.channel_id})'
        member = guild.get_member(int(t['accused_id']))
        # Классические разрешения: применяем только то, что дано роли
        # модератора (не дал «Бан» — бан не применится, даже если вердикт
        # выбран раньше).
        if not _verdict_allowed(guild, interaction.user, v['kind']):
            return await interaction.response.send_message(
                f'Действие «{RC.KIND_LABELS.get(v["kind"], v["kind"])}» тебе '
                'не дал владелец (панель → Доступ → Права команд → '
                'Классические разрешения).', ephemeral=True)
        _lim = _verdict_limit_denied(guild, interaction.user, v['kind'])
        if _lim:
            return await interaction.response.send_message(f'🚫 {_lim}', ephemeral=True)
        applied = 'Применено.'
        try:
            if v['kind'] == 'mute' and member:
                hours = v.get('hours') or 24
                try:  # потолок длительности мута для этого модератора
                    from services import staff_limits as _SL
                    _cap = _SL.effective_max_duration(
                        guild.id, 'mute',
                        [r.id for r in getattr(interaction.user, 'roles', [])])
                    if _cap and _cap > 0:
                        hours = min(hours, max(1, int(_cap // 3600)))
                except Exception as _ex:
                    _log.debug('вердикт mute cap: %s', _ex)
                until = datetime.now(timezone.utc) + timedelta(
                    minutes=1, hours=min(hours, 672))  # лимит Discord — 28 дней
                try:  # таймаут глушит чат И голос — сначала снимаем отдельный войс-мут
                    from services import mute_state
                    await mute_state.clear_voice_mute(guild, member)
                except Exception as _mse:
                    _log.debug('вердикт mute: очистка войс-мута: %s', _mse)
                await member.timeout(until, reason=reason)
                applied = f'Мут до {until:%d.%m %H:%M} UTC.'
            elif v['kind'] == 'kick' and member:
                await member.kick(reason=reason)
                applied = 'Кик выполнен.'
            elif v['kind'] == 'ban':
                await guild.ban(int(t['accused_id']), reason=reason,
                                delete_message_seconds=0)
                applied = 'Бан выдан.'
                if v.get('hours'):
                    async def _unban_later():
                        await discord.utils.sleep_until(
                            datetime.now(timezone.utc) + timedelta(hours=v['hours']))
                        try:
                            await guild.unban(
                                discord.Object(id=int(t['accused_id'])),
                                reason='Срок временного бана истёк')
                        except Exception as _sx1:
                            _log.debug('подавлено: %s', _sx1)
                    interaction.client.loop.create_task(_unban_later())
            elif v['kind'] == 'none':
                applied = 'Нарушений не зафиксировано.'
        except Exception as ex:
            return await interaction.response.send_message(
                f'Discord не принял наказание: {ex}', ephemeral=True)

        if v['kind'] in ('mute', 'kick', 'ban'):
            _record_verdict(guild, interaction.user, v['kind'])

        if v['kind'] != 'none':
            RC.add_violation(guild.id, t['accused_id'], v['kind'],
                             v.get('hours', 0), reason, t['thread_id'])

        e = discord.Embed(title='Решение вынесено',
                          description=(f"**{v['label']}**\nОбвиняемый: <@{t['accused_id']}>\n"
                                       f"Модератор: {interaction.user.mention}\n{applied}"),
                          color=0x2ECC71 if v['kind'] == 'none' else 0xE74C3C)
        await interaction.response.edit_message(content='', embed=None, view=None)
        await interaction.channel.send(embed=e)
        for uid in (t['reporter_id'], t['accused_id']):
            user = interaction.client.get_user(int(uid)) or \
                await interaction.client.fetch_user(int(uid))
            if user:
                await _dm(user, e)

    # ── закрытие и архив ────────────────────────────────────────────
    @classmethod
    async def close_ticket(cls, interaction):
        t = RC.ticket_get(interaction.channel_id)
        if not t:
            return await interaction.response.send_message(
                'Это не ветка репорта.', ephemeral=True)
        await interaction.response.defer()
        msgs = []
        try:
            async for m in interaction.channel.history(limit=1000):
                msgs.append((m.author.display_name, str(m.author.id),
                             m.created_at.isoformat(), (m.content or '')[:1500]))
            msgs.reverse()
        except Exception as ex:
            _log.warning('close_ticket.history: %s', ex)
        size = RC.archive_save(interaction.guild_id, interaction.channel_id,
                               msgs, {'count': len(msgs), 'verdict': t.get('verdict', '')})
        RC.ticket_set(interaction.channel_id, closed=datetime.now(timezone.utc).timestamp())
        verdict_label = ''
        try:
            verdict_label = _json.loads(t.get('verdict') or '{}').get('label', '')
        except Exception as _ve:
            _log.debug('verdict label: подавлено: %s', _ve)
        e = discord.Embed(
            title='Тикет закрыт',
            description=(f"Итог: **{verdict_label or 'решение не вынесено'}**\n"
                         f"В архиве {len(msgs)} сообщений ({size // 1024} КБ, zlib)."),
            color=0x99AAB5)
        for uid in (t['reporter_id'], t['accused_id']):
            try:
                user = interaction.client.get_user(int(uid))
                if user:
                    await _dm(user, e)
            except Exception as _sx2:
                _log.debug('подавлено: %s', _sx2)
        try:
            await interaction.followup.send('Архив сохранён. Ветка удаляется.',
                                            ephemeral=True)
            await interaction.channel.delete()
        except Exception as ex:
            await interaction.followup.send(f'Архив сохранён, ветку удалить не вышло: {ex}',
                                            ephemeral=True)

    # ── команды ─────────────────────────────────────────────────────
    @app_commands.command(name='report', description='Подать жалобу на участника')
    @app_commands.describe(user='На кого жалоба', reason='Причина',
                           proof_file='Скрин/видео-доказательство — грузится в ветку сразу',
                           proof='Ссылка на доказательства (если файл не нужен)')
    async def report_slash(self, interaction, user: discord.Member,
                           reason: str, proof_file: discord.Attachment = None,
                           proof: str = ''):
        if user.bot or user.id == interaction.user.id:
            return await interaction.response.send_message(
                'На себя и ботов жаловаться нельзя.', ephemeral=True)
        # Видео/фото-доказательство: принимаем изображение или видео.
        if proof_file is not None:
            _ct = (getattr(proof_file, 'content_type', '') or '').lower()
            if not (_ct.startswith('image/') or _ct.startswith('video/')):
                return await interaction.response.send_message(
                    'Доказательство должно быть фото или видео. Можно также '
                    'дать ссылку через параметр «proof».', ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = interaction.guild
        cfg = _cfg(guild.id)

        # КД на повторный репорт ОДНОГО И ТОГО ЖЕ участника: если открытая
        # жалоба от этого пользователя на эту же цель уже есть (окно из cfg,
        # по умолчанию 1 день) — команду использовать нельзя (заказ владельца).
        try:
            _cd = int(cfg.get('reporter_target_cooldown_sec') or 86400)
        except (TypeError, ValueError):
            _cd = 86400
        if RC.has_recent_open_report(guild.id, interaction.user.id, user.id, _cd):
            return await interaction.followup.send(
                'Ты уже подал жалобу на этого участника — повторно жаловаться '
                'на него можно, когда модераторы разберут предыдущую (или '
                'через несколько минут). Не дублируй репорт.', ephemeral=True)
        mod_role = _mod_role_from_cfg(guild)

        # Канал модерации: берём настроенный/по имени, иначе создаём закрытый.
        ch, created = await _ensure_mod_channel(guild, mod_role)
        if ch is None:
            return await interaction.followup.send(
                'Не удалось подготовить канал модерации (не хватило прав '
                '«Управление каналами»?). Сообщите администратору.',
                ephemeral=True)

        proof_bits = []
        if proof:
            proof_bits.append(f'Ссылка: {proof[:200]}')
        if proof_file is not None:
            kind = 'видео' if (proof_file.content_type or '').startswith('video') else 'фото'
            proof_bits.append(f'{kind.capitalize()}: {proof_file.filename} '
                              f'({proof_file.size // 1024} КБ) — вложением ниже')
        proof_line = '\n'.join(proof_bits) if proof_bits else 'не приложены'

        e = discord.Embed(
            title='🚨 Новая жалоба',
            color=0xE74C3C,
            description=(
                f"**На кого:** {user.mention} · `{user.id}`\n"
                f"**Кто пожаловался:** {interaction.user.mention}\n"
                f"**Канал:** {interaction.channel.mention}\n\n"
                f"**Причина:**\n{reason[:1500]}\n\n"
                f"**Доказательства:** {proof_line}\n\n"
                f"**Прошлые нарушения ({cfg.get('expiry_days', 90)} дн):**\n"
                + _violations_field(guild.id, user.id, cfg)),
            timestamp=datetime.now(timezone.utc))
        e.set_thumbnail(url=user.display_avatar.url)
        e.set_footer(text=f'{guild.name} · модерация')

        ping = mod_role.mention if mod_role else ''
        header = f'{ping} Новая жалоба на {user.mention}'.strip()
        send_kw = {'embed': e, 'view': ReportCardView(),
                   'allowed_mentions': discord.AllowedMentions(
                       roles=True, users=True)}
        if ping:
            send_kw['content'] = header
        if proof_file is not None:
            try:
                send_kw['file'] = await proof_file.to_file()
            except Exception as ex:
                _log.warning('report proof_file: %s', ex)
        try:
            card = await ch.send(**send_kw)
        except discord.Forbidden as _fe:
            return await interaction.followup.send(
                'Бот не может отправить жалобу в канал модерации — не хватает '
                'прав (просмотр/отправка/вложения). Выдайте их роли бота.',
                ephemeral=True)

        # Привязываем запись жалобы к сообщению-карточке (id сообщения = ключ).
        RC.ticket_create(guild.id, card.id, interaction.user.id, user.id,
                         kind='card')
        _fire_new_event('report_new',
                        f'На **{user.display_name}** пожаловался '
                        f'{interaction.user.display_name}: {reason[:120]}')

        note = f'Жалоба отправлена модерации: {ch.mention}.'
        if created:
            note += ' Канал модерации создан автоматически.'
        if not mod_role:
            note += (' Роль модераторов не настроена — задайте её в панели '
                     'или командой /report-setup, чтобы бот тегал модерацию.')
        await interaction.followup.send(note, ephemeral=True)

    @app_commands.command(name='witness',
                          description='Пригласить свидетеля в ветку репорта')
    @app_commands.describe(user='Кого позвать')
    async def witness_slash(self, interaction, user: discord.Member):
        cfg = _cfg(interaction.guild_id)
        if not _is_mod(interaction.user, cfg):
            return await interaction.response.send_message(
                'Только модератор.', ephemeral=True)
        t = RC.ticket_get(interaction.channel_id)
        if not t:
            return await interaction.response.send_message(
                'Работает только внутри ветки репорта.', ephemeral=True)
        RC.add_witness(interaction.channel_id, user.id)
        try:
            await interaction.channel.add_user(user)
        except Exception as _ae:
            _log.debug('add_user в ветку: подавлено: %s', _ae)
        await interaction.response.send_message(
            embed=discord.Embed(title='Свидетель приглашён',
                                description=f'{user.mention} присоединился к рассмотрению.',
                                color=0x5865F2))

    @app_commands.command(name='my-violations', description='Мои нарушения')
    async def my_violations_slash(self, interaction):
        cfg = _cfg(interaction.guild_id)
        field = _violations_field(interaction.guild_id, interaction.user.id, cfg)
        has = field != 'Нарушений не было'
        e = discord.Embed(title='Мои нарушения',
                          description=field, color=0x99AAB5)
        # ВАЖНО: discord.py send_message падает на view=None (ждёт MISSING),
        # поэтому view передаём только когда реально есть.
        kwargs = {'embed': e, 'ephemeral': True}
        if has:
            kwargs['view'] = MyViolationsView()
        await interaction.response.send_message(**kwargs)

    # Команды /report-setup и /report-settings удалены (2026-09-01):
    # канал веток, роль модераторов и срок давности настраиваются в
    # веб-панели (страница «Репорты», /api/guild/<gid>/report-settings).
    # Слеш-команды в Discord больше не регистрируются.

    # ── фильтр слова ────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.guild is None:
            return
        if not isinstance(message.channel, discord.Thread):
            return
        t = RC.ticket_get(message.channel.id)
        if not t or t.get('closed'):
            return
        cfg = _cfg(message.guild.id)
        member = message.author if hasattr(message.author, 'roles') else None
        if _is_mod(member, cfg):
            return
        mode = t.get('mode', 'wait')
        allowed = {'free': None, 'wait': t['reporter_id'],
                   'turn': t.get('word_id'), 'manual': t.get('word_id')}
        uid = str(message.author.id)
        if mode == 'free' or allowed.get(mode) == uid:
            return
        try:
            await message.delete()
        except Exception:
            return
        import time as _time
        now = _time.monotonic()
        if now - _word_hint_ts.get(uid, 0) > WORD_HINT_EVERY:
            _word_hint_ts[uid] = now
            try:
                await message.channel.send(
                    content=f"<@{uid}>, сейчас слово у другого участника — "
                            f"модератор передаст его кнопкой «Дать слово».",
                    delete_after=6)
            except Exception as _sx4:
                _log.debug('подавлено: %s', _sx4)


class MyViolationsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label='Подать апелляцию', style=discord.ButtonStyle.primary,
                       custom_id='rpt_my_appeal')
    async def appeal(self, interaction, button):
        await interaction.response.send_message(
            'Апелляция подаётся через /апелляция в ЛС боту.',
            ephemeral=True)


async def setup(bot):
    await bot.add_cog(Reports(bot))
