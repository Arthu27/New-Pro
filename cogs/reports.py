# -*- coding: utf-8 -*-
"""
Aether — Система репортов (ТЗ 2026-08-26)
------------------------------------------
/report -> приватная ветка в канале репортов с панелью управления:
Select-меню для режима обсуждения, слова, вынесения решения (дефолт
по рецидивам / индивидуальное + срок). Переписка при закрытии сжимается
zlib и уходит в архив (services/reports_core). /my_violations + /appeal
с восстановлением переписки из архива.

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


def _is_mod(member, cfg) -> bool:
    if member is None:
        return False
    if member.guild_permissions.manage_messages:
        return True
    rid = str(cfg.get('mod_role_id') or '')
    return bool(rid) and any(str(r.id) == rid for r in member.roles)


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
        except Exception:
            pass


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
#  КОГ
# ═══════════════════════════════════════════════════════════════════
class Reports(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        RC.db()  # создать таблицы
        self.bot.add_view(ReportPanelView())  # персистентная панель
        _log.info('Reports: панель зарегистрирована')

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
        applied = 'Применено.'
        try:
            if v['kind'] == 'mute' and member:
                hours = v.get('hours') or 24
                until = datetime.now(timezone.utc) + timedelta(
                    minutes=1, hours=min(hours, 672))  # лимит Discord — 28 дней
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
                        except Exception:
                            pass
                    interaction.client.loop.create_task(_unban_later())
            elif v['kind'] == 'none':
                applied = 'Нарушений не зафиксировано.'
        except Exception as ex:
            return await interaction.response.send_message(
                f'Discord не принял наказание: {ex}', ephemeral=True)

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
        except Exception:
            pass
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
            except Exception:
                pass
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
        cfg = _cfg(interaction.guild_id)
        if not cfg.get('channel_id'):
            return await interaction.response.send_message(
                'Канал репортов не привязан — админ должен выполнить /report-setup.',
                ephemeral=True)
        if user.bot or user.id == interaction.user.id:
            return await interaction.response.send_message(
                'На себя и ботов жаловаться нельзя.', ephemeral=True)
        ch = interaction.guild.get_channel(int(cfg['channel_id']))
        if ch is None:
            return await interaction.response.send_message(
                'Канал репортов не найден.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            thread = await ch.create_thread(
                name=f'репорт · {user.display_name[:40]}',
                type=discord.ChannelType.private_thread,
                auto_archive_duration=10080,
                reason=f'Жалоба от {interaction.user}')
        except Exception as ex:
            return await interaction.followup.send(
                f'Не удалось создать ветку: {ex}', ephemeral=True)
        for uid in (interaction.user.id, user.id):
            try:
                m = await interaction.guild.fetch_member(uid)
                await thread.add_user(m)
            except Exception:
                pass
        RC.ticket_create(interaction.guild_id, thread.id,
                         interaction.user.id, user.id)
        proof_bits = []
        if proof:
            proof_bits.append(f'Ссылка: {proof[:200]}')
        if proof_file is not None:
            proof_bits.append(f'Файл: {proof_file.filename} '
                              f'({proof_file.size // 1024} КБ) — вложением ниже')
        proof_line = '\n'.join(proof_bits) if proof_bits else '—'
        e = discord.Embed(
            title='Репорт',
            color=0xE74C3C,
            description=(f"Обвиняемый: **{user.display_name}** · `{user.id}`\n"
                         f"Подал: {interaction.user.mention}\n\n"
                         f"**Причина:** {reason[:1000]}\n"
                         f"**Доказательства:** {proof_line}\n\n"
                         f"**Прошлые нарушения ({cfg.get('expiry_days', 90)} дн):**\n"
                         + _violations_field(interaction.guild_id, user.id, cfg)),
            timestamp=datetime.now(timezone.utc))
        e.set_thumbnail(url=user.display_avatar.url)
        e.set_footer(text=f'{interaction.guild.name} · до выбора режима пишут модератор и обвинитель')
        send_kw = {'embed': e, 'view': ReportPanelView()}
        if proof_file is not None:
            try:
                send_kw['file'] = await proof_file.to_file()
            except Exception as ex:
                _log.warning('report proof_file: %s', ex)
        await thread.send(**send_kw)
        await interaction.followup.send(
            f'Репорт создан: {thread.mention}', ephemeral=True)

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
        except Exception:
            pass
        await interaction.response.send_message(
            embed=discord.Embed(title='Свидетель приглашён',
                                description=f'{user.mention} присоединился к рассмотрению.',
                                color=0x5865F2))

    @app_commands.command(name='my_violations', description='Мои нарушения')
    async def my_violations_slash(self, interaction):
        cfg = _cfg(interaction.guild_id)
        field = _violations_field(interaction.guild_id, interaction.user.id, cfg)
        has = field != 'Нарушений не было'
        e = discord.Embed(title='Мои нарушения',
                          description=field, color=0x99AAB5)
        await interaction.response.send_message(
            embed=e, view=MyViolationsView() if has else None, ephemeral=True)

    @app_commands.command(name='appeal', description='Обжаловать нарушение')
    @app_commands.describe(description='Почему решение надо пересмотреть',
                           proof_file='Скрин/видео к апелляции — грузится в ветку сразу')
    async def appeal_slash(self, interaction, description: str,
                           proof_file: discord.Attachment = None):
        cfg = _cfg(interaction.guild_id)
        if not cfg.get('channel_id'):
            return await interaction.response.send_message(
                'Канал репортов не привязан.', ephemeral=True)
        vs = RC.violations_of(interaction.guild_id, interaction.user.id,
                              cfg.get('expiry_days', 90))
        if not vs:
            return await interaction.response.send_message(
                'Нарушений для обжалования нет.', ephemeral=True)
        file_obj = None
        if proof_file is not None:
            try:
                file_obj = await proof_file.to_file()
            except Exception as ex:
                _log.warning('appeal proof_file: %s', ex)
        await interaction.response.send_message(
            'Какое нарушение обжалуем:',
            view=AppealSelectView(vs, description, file_obj), ephemeral=True)

    @app_commands.command(name='report-setup',
                          description='Настроить систему репортов: канал + роль + права')
    @app_commands.describe(mod_role='Роль модераторов',
                           channel='Канал веток (не указан — создам закрытый #репорты)')
    @app_commands.checks.has_permissions(administrator=True)
    async def report_setup_slash(self, interaction,
                                 mod_role: discord.Role,
                                 channel: discord.TextChannel = None):
        guild = interaction.guild
        if channel is None:
            # ТЗ 1.8: канал репортов видят только модераторы и менеджеры —
            # создаём сразу с закрытыми правами, ничего руками делать не надо
            over = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                mod_role: discord.PermissionOverwrite(
                    read_messages=True, send_messages=True,
                    manage_threads=True, read_message_history=True),
                guild.me: discord.PermissionOverwrite(
                    read_messages=True, send_messages=True,
                    manage_threads=True, create_private_threads=True,
                    manage_messages=True, embed_links=True, attach_files=True,
                    read_message_history=True),
            }
            try:
                channel = await guild.create_text_channel(
                    'репорты', overwrites=over,
                    reason='Настройка системы репортов')
            except Exception as ex:
                return await interaction.response.send_message(
                    f'Канал создать не вышло: {ex}. Укажите готовый канал '
                    'параметром channel.', ephemeral=True)
            made = True
        else:
            # существующий канал закрываем от @everyone и открываем модам
            # (точечно, чужие оверрайты не трогаем)
            try:
                await channel.set_permissions(
                    guild.default_role, read_messages=False,
                    reason='Система репортов: канал только для модерации')
                await channel.set_permissions(
                    mod_role, read_messages=True, send_messages=True,
                    manage_threads=True, read_message_history=True,
                    reason='Система репортов')
                await channel.set_permissions(
                    guild.me, read_messages=True, send_messages=True,
                    manage_threads=True, create_private_threads=True,
                    manage_messages=True, embed_links=True, attach_files=True,
                    read_message_history=True,
                    reason='Система репортов')
            except Exception as ex:
                _log.warning('report-setup perms: %s', ex)
            made = False
        cfg = _cfg(interaction.guild_id)
        cfg['channel_id'] = str(channel.id)
        cfg['mod_role_id'] = str(mod_role.id)
        RC.save_cfg(interaction.guild_id, cfg)
        perms = channel.permissions_for(guild.me)
        e = discord.Embed(
            title='Система репортов настроена',
            description=(f"Канал: {channel.mention}"
                         f"{' · создан и закрыт от участников' if made else ' · права обновлены: только модерация'}\n"
                         f"Роль модератора: {mod_role.mention}\n\n"
                         f"Создание приватных веток: "
                         f"{'ок' if perms.create_private_threads else 'НЕТ ПРАВА'} · "
                         f"Управление ветками: "
                         f"{'ок' if perms.manage_threads else 'НЕТ ПРАВА'}\n"
                         f"Лестница рецидивов: " + ' → '.join(
                             s['label'] for s in cfg['ladder']) +
                         f"\nСрок давности: {cfg['expiry_days']} дн"),
            color=0x2ECC71)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name='report-settings',
                          description='Настройки рецидивов репортов')
    @app_commands.checks.has_permissions(administrator=True)
    async def report_settings_slash(self, interaction,
                                    expiry_days: app_commands.Range[int, 1, 365] = None):
        cfg = _cfg(interaction.guild_id)
        if expiry_days:
            cfg['expiry_days'] = expiry_days
            RC.save_cfg(interaction.guild_id, cfg)
        e = discord.Embed(
            title='Настройки рецидивов',
            description=('Лестница (по порядку нарушений):\n' + '\n'.join(
                f"{s['n']}-е → {s['label']}" for s in cfg['ladder']) +
                f"\nСрок давности: {cfg['expiry_days']} дн"),
            color=0x5865F2)
        await interaction.response.send_message(embed=e, ephemeral=True)

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
            except Exception:
                pass


# ── Select: апелляция ───────────────────────────────────────────────
class AppealSelectView(discord.ui.View):
    def __init__(self, violations, description, file_obj=None):
        super().__init__(timeout=180)
        self.description = description
        self.file_obj = file_obj
        self.select.options = [
            discord.SelectOption(
                label=f"{RC.KIND_LABELS.get(v['kind'], v['kind'])} · "
                      f"{datetime.fromtimestamp(v['created'], timezone.utc).strftime('%d.%m.%Y')}",
                value=str(v['id'])) for v in violations[-25:]]

    @discord.ui.select(cls=discord.ui.Select, placeholder='Нарушение')
    async def choose(self, interaction, select):
        await interaction.response.defer(ephemeral=True)
        cfg = _cfg(interaction.guild_id)
        ch = interaction.guild.get_channel(int(cfg['channel_id']))
        if ch is None:
            return await interaction.followup.send('Канал репортов не найден.',
                                                   ephemeral=True)
        thread = await ch.create_thread(
            name=f'апелляция · {interaction.user.display_name[:36]}',
            type=discord.ChannelType.private_thread,
            auto_archive_duration=10080,
            reason=f'Апелляция {interaction.user}')
        await thread.add_user(interaction.user)
        RC.ticket_create(interaction.guild_id, thread.id,
                         interaction.user.id, interaction.user.id, kind='appeal')
        with RC.db() as c:
            row = c.execute('SELECT thread_id FROM violations WHERE id=?',
                            (int(select.values[0]),)).fetchone()
        old_thread = row[0] if row else ''
        e = discord.Embed(
            title='Апелляция',
            color=0x5865F2,
            description=(f"Подал: {interaction.user.mention}\n"
                         f"Нарушение: `#{select.values[0]}`\n\n"
                         f"**Доводы:** {self.description[:1500]}"))
        send_kw = {'embed': e, 'view': AppealPanelView(select.values[0], old_thread)}
        if self.file_obj is not None:
            send_kw['file'] = self.file_obj
        await thread.send(**send_kw)
        await interaction.followup.send(f'Апелляция создана: {thread.mention}',
                                        ephemeral=True)


class AppealPanelView(discord.ui.View):
    def __init__(self, violation_id, old_thread):
        super().__init__(timeout=None)
        self.violation_id = violation_id
        self.old_thread = old_thread

    async def _mod(self, interaction):
        cfg = _cfg(interaction.guild_id)
        if not _is_mod(interaction.user, cfg):
            await interaction.response.send_message('Только модератор.',
                                                    ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Одобрить (снять)', style=discord.ButtonStyle.success,
                       custom_id='rpt_appr_ok')
    async def approve(self, interaction, button):
        if not await self._mod(interaction):
            return
        RC.remove_violation(self.violation_id)
        e = discord.Embed(title='Апелляция одобрена',
                          description='Нарушение снято с учёта.',
                          color=0x2ECC71)
        await interaction.response.send_message(embed=e)
        await _dm(interaction.user, e)

    @discord.ui.button(label='Отклонить', style=discord.ButtonStyle.danger,
                       custom_id='rpt_appr_no')
    async def reject(self, interaction, button):
        if not await self._mod(interaction):
            return
        e = discord.Embed(title='Апелляция отклонена',
                          description='Решение остаётся в силе.',
                          color=0xE74C3C)
        await interaction.response.send_message(embed=e)
        await _dm(interaction.user, e)

    @discord.ui.button(label='Показать переписку', style=discord.ButtonStyle.secondary,
                       custom_id='rpt_appr_show')
    async def show(self, interaction, button):
        if not await self._mod(interaction):
            return
        await interaction.response.defer()
        msgs = []
        try:
            msgs = RC.archive_load(interaction.guild_id, self.old_thread)
        except Exception:
            pass
        if not msgs:
            return await interaction.followup.send(
                'Архива нет — тикет закрывался без переписки.', ephemeral=True)
        await interaction.channel.send(
            embed=discord.Embed(title='Восстановление переписки',
                                description=f'{len(msgs)} сообщений из архива тикета.',
                                color=0x99AAB5))
        import asyncio as _aio
        chunk, n = [], 0
        for author, _uid, _ts, content in msgs[:60]:
            if not content:
                continue
            chunk.append(f'**{author}:** {content[:200]}')
            n += 1
            if len(chunk) == 5:
                await interaction.channel.send('\n'.join(chunk))
                await _aio.sleep(0.8)
                chunk = []
        if chunk:
            await interaction.channel.send('\n'.join(chunk))


class MyViolationsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label='Подать апелляцию', style=discord.ButtonStyle.primary,
                       custom_id='rpt_my_appeal')
    async def appeal(self, interaction, button):
        await interaction.response.send_message(
            'Опишите доводы и выполните команду /appeal — выберите нарушение из списка.',
            ephemeral=True)


async def setup(bot):
    await bot.add_cog(Reports(bot))
