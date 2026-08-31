# -*- coding: utf-8 -*-
"""Верификация участников с молодыми аккаунтами (+ анкета).

Сценарий (заказ владельца 31.08):
  • Участник заходит на сервер. Если возраст его Discord-аккаунта МЕНЬШЕ
    порога (настраивается, по умолчанию 2 дня), бот:
      – временно ограничивает доступ (выдаёт «карантинную» роль без прав);
      – пишет в ЛС красивое сообщение: доступ ограничен на 1 день, чтобы
        пройти верификацию — заполни анкету в канале верификации на сервере.
  • В канале верификации висит кнопка «Заполнить анкету». По нажатию бот
    в ЛС собирает ответы (имя, как узнал про сервер, правила, активность…)
    через ЛИЧНЫЕ СООБЩЕНИЯ — на сервере ничего не спамится.
  • Готовая анкета отправляется модераторам (в канал модерации/верификации),
    модератор кнопками «Подтвердить» / «Отклонить» решает судьбу:
      – Подтвердить → снимается карантин, выдаётся роль участника;
      – Отклонить  → кик (с причиной в ЛС).

Настройка (админ) — /verify-setup в Discord и/или панель (route ниже):
  порог дней, карантинная роль, роль участника, канал верификации,
  канал заявок модераторам. Канал верификации бот может создать сам.

Всё хранится в data/verify_<guild_id>.json и data/verify_db.sqlite —
обновление бота эти данные НЕ трогает (каталог data/ в PRESERVE).
"""

import json
import os
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from logger import get_logger

_log = get_logger('age_verification')

DATA_DIR = 'data'


# ── конфиг ──────────────────────────────────────────────────────────────
def _cfg_path(gid):
    return os.path.join(DATA_DIR, f'verify_{gid}.json')


def _default_cfg():
    return {
        'enabled': False,
        'min_age_days': 2,        # моложе этого возраста — карантин + анкета
        'quarantine_role_id': '',
        'member_role_id': '',
        'verify_channel_id': '',
        'review_channel_id': '',  # куда падают анкеты (модерам)
        'kick_after_days': 1,     # сколько дней карантин до авто-кика (0 = не кикать)
    }


def load_cfg(gid) -> dict:
    cfg = _default_cfg()
    try:
        with open(_cfg_path(gid), encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update({k: data[k] for k in cfg if k in data})
    except FileNotFoundError:
        _log.debug('verify: конфиг %s ещё не создан — значения по умолчанию', _cfg_path(gid))
    except Exception as ex:
        _log.debug('verify load_cfg(%s): %s', gid, ex)
    return cfg


def save_cfg(gid, cfg: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = _cfg_path(gid) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _cfg_path(gid))


# ── БД заявок (кто на карантине / чья анкета на рассмотрении) ───────────
import sqlite3

_DB_PATH = os.path.join(DATA_DIR, 'verify_db.sqlite')


def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS pending (
            guild_id   TEXT NOT NULL,
            user_id    TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'quarantine',  -- quarantine|application|approved|kicked
            quarantined_at REAL,
            answers    TEXT,
            message_id TEXT,
            PRIMARY KEY (guild_id, user_id)
        )""")
    conn.commit()
    return conn


def _set_pending(gid, uid, **fields):
    cols = ['guild_id', 'user_id'] + list(fields.keys())
    vals = [str(gid), str(uid)] + [
        (json.dumps(v, ensure_ascii=False) if k == 'answers' else v)
        for k, v in fields.items()]
    placeholders = ','.join('?' for _ in cols)
    update = ','.join(f'{c}=excluded.{c}' for c in fields.keys())
    with _db() as c:
        c.execute(
            f"INSERT INTO pending ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(guild_id,user_id) DO UPDATE SET {update}",
            vals)


def _get_pending(gid, uid):
    with _db() as c:
        row = c.execute(
            "SELECT * FROM pending WHERE guild_id=? AND user_id=?",
            (str(gid), str(uid))).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d['answers'] = json.loads(d.get('answers') or 'null')
    except Exception:
        d['answers'] = None
    return d


def _all_pending(gid, status=None):
    with _db() as c:
        if status:
            rows = c.execute(
                "SELECT * FROM pending WHERE guild_id=? AND status=?",
                (str(gid), status)).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM pending WHERE guild_id=?", (str(gid),)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d['answers'] = json.loads(d.get('answers') or 'null')
        except Exception:
            d['answers'] = None
        out.append(d)
    return out


def _del_pending(gid, uid):
    with _db() as c:
        c.execute("DELETE FROM pending WHERE guild_id=? AND user_id=?",
                  (str(gid), str(uid)))


# ── Вопросы анкеты ───────────────────────────────────────────────────────
QUESTIONS = [
    ('q1', 'Как тебя зовут (или ник, как обращаться)?'),
    ('q2', 'Сколько тебе лет?'),
    ('q3', 'Откуда узнал(а) про наш сервер / кто пригласил?'),
    ('q4', 'Ознакомился(лась) ли с правилами сервера? Готов(а) их соблюдать?'),
    ('q5', 'Пара слов о себе: чем интересуешься, чем планируешь заниматься на сервере?'),
]


def _dm_welcome(guild_name, days_limit, verify_channel_mention):
    """Красивое приветственное ЛС для аккаунта на карантине."""
    e = discord.Embed(
        title='🔒 Доступ к серверу временно ограничен',
        description=(
            f'Привет! Мы заметили, что твой Discord-аккаунт создан **менее '
            f'{days_limit} дн. назад**. На сервере **{guild_name}** действует '
            f'защита от свежесозданных аккаунтов — поэтому тебе временно '
            f'ограничили доступ (на срок до **1 дня**).\n\n'
            f'Это не бан и не наказание: просто напиши короткую **анкету**, '
            f'чтобы модераторы убедились, что ты живой человек.\n\n'
            f'**Как пройти верификацию:**\n'
            f'1️⃣ Зайди на сервер → канал {verify_channel_mention or "«Верификация»"}\n'
            f'2️⃣ Нажми кнопку **«Заполнить анкету»**\n'
            f'3️⃣ Ответь на несколько вопросов **в личных сообщениях бота**\n\n'
            f'Модераторы проверят анкету и откроют доступ. Обычно это быстро 🙂'
        ),
        color=0xF0B232)
    e.set_footer(text='Если кнопка не появляется — проверь, что ЛС от участников сервера разрешены.')
    return e


def _dm_approved(guild_name):
    return discord.Embed(
        title='✅ Верификация пройдена',
        description=(f'Поздравляем! Твоя анкета на сервере **{guild_name}** '
                     f'одобрена — полный доступ открыт. Добро пожаловать! 🎉'),
        color=0x2ECC71)


def _dm_declined(guild_name, reason=''):
    desc = (f'К сожалению, твоя заявка на верификацию на сервере '
            f'**{guild_name}** отклонена.')
    if reason:
        desc += f'\n\nПричина: {reason}'
    return discord.Embed(title='❌ Верификация отклонена', description=desc,
                         color=0xE74C3C)


# ── Кнопка в канале верификации ─────────────────────────────────────────
class StartApplicationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Заполнить анкету', style=discord.ButtonStyle.success,
                       emoji='📝', custom_id='verify_start_btn')
    async def start(self, interaction: discord.Interaction, button):
        if not interaction.guild:
            return
        cfg = load_cfg(interaction.guild_id)
        if not cfg.get('enabled'):
            return await interaction.response.send_message(
                'Верификация сейчас выключена.', ephemeral=True)
        pend = _get_pending(interaction.guild_id, interaction.user.id)
        if not pend:
            # возможно, аккаунт уже не молодой/не на карантине — пусть модераторы
            return await interaction.response.send_message(
                'На тебя не наложено ограничение верификации — всё в порядке, '
                'дополнительная анкета не нужна.', ephemeral=True)
        if pend['status'] in ('application', 'approved'):
            return await interaction.response.send_message(
                'Ты уже отправил анкету — модераторы проверяют её. Ожидай, пожалуйста.',
                ephemeral=True)
        # начинаем диалог в ЛС
        try:
            dm = await interaction.user.create_dm()
        except Exception:
            return await interaction.response.send_message(
                'Не получается написать тебе в ЛС. Открой личные сообщения от '
                'участников сервера (Настройки → Конфиденциальность) и попробуй снова.',
                ephemeral=True)
        await interaction.response.send_message(
            'Открыл личные сообщения — анкета придёт туда.', ephemeral=True)
        cog = interaction.client.get_cog('AgeVerification')
        if cog:
            await cog.begin_application(interaction.user, interaction.guild, dm)


# ── Кнопки модерации под анкетой ────────────────────────────────────────
class ReviewView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _mod_only(self, interaction) -> bool:
        cfg = load_cfg(interaction.guild_id)
        member = interaction.user
        is_mod = (member.guild_permissions.administrator
                  or member.guild_permissions.manage_roles
                  or member.guild_permissions.kick_members)
        if not is_mod:
            await interaction.response.send_message(
                'Решение по верификации принимают модераторы.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Подтвердить', style=discord.ButtonStyle.success,
                       emoji='✅', custom_id='verify_approve_btn')
    async def approve(self, interaction: discord.Interaction, button):
        if not await self._mod_only(interaction):
            return
        pend = _get_pending(interaction.guild_id, _uid_from_footer(interaction.message))
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not pend:
            return await interaction.followup.send('Заявка не найдена (возможно, уже обработана).', ephemeral=True)
        member = guild.get_member(int(pend['user_id']))
        cfg = load_cfg(guild.id)
        try:
            if member is not None:
                qrole = guild.get_role(int(cfg['quarantine_role_id'])) if cfg.get('quarantine_role_id') else None
                mrole = guild.get_role(int(cfg['member_role_id'])) if cfg.get('member_role_id') else None
                if qrole and qrole in member.roles:
                    await member.remove_roles(qrole, reason='Верификация пройдена')
                if mrole and mrole not in member.roles:
                    await member.add_roles(mrole, reason='Верификация пройдена')
            try:
                await interaction.client.get_user(int(pend['user_id'])).send(
                    embed=_dm_approved(guild.name))
            except Exception as ex:
                _log.debug('verify approve DM: %s', ex)
        except discord.Forbidden:
            return await interaction.followup.send(
                'У бота нет прав на роли (выдача/снятие). Проверьте иерархию ролей.', ephemeral=True)
        _set_pending(guild.id, pend['user_id'], status='approved')
        await _mark_reviewed(interaction.message, approved=True, by=interaction.user)
        await interaction.followup.send('✅ Участник верифицирован, доступ открыт.', ephemeral=True)

    @discord.ui.button(label='Отклонить и кикнуть', style=discord.ButtonStyle.danger,
                       emoji='❌', custom_id='verify_reject_btn')
    async def reject(self, interaction: discord.Interaction, button):
        if not await self._mod_only(interaction):
            return
        pend = _get_pending(interaction.guild_id, _uid_from_footer(interaction.message))
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not pend:
            return await interaction.followup.send('Заявка не найдена (возможно, уже обработана).', ephemeral=True)
        member = guild.get_member(int(pend['user_id']))
        reason = f'Верификация отклонена модератором {interaction.user}'
        try:
            if member is not None:
                try:
                    await member.send(embed=_dm_declined(guild.name, 'Анкета не прошла проверку.'))
                except Exception as ex:
                    _log.debug('verify reject DM %s: %s', pend['user_id'], ex)
                await member.kick(reason=reason)
        except discord.Forbidden:
            return await interaction.followup.send(
                'Не удалось кикнуть: нет прав или роль участника выше роли бота.', ephemeral=True)
        _set_pending(guild.id, pend['user_id'], status='kicked')
        await _mark_reviewed(interaction.message, approved=False, by=interaction.user)
        await interaction.followup.send('❌ Заявка отклонена, участник кикнут.', ephemeral=True)


def _uid_from_footer(message):
    """Достать user_id из футера анкеты (пишем туда uid)."""
    for embed in message.embeds:
        if embed.footer and embed.footer.text:
            txt = embed.footer.text
            if 'uid:' in txt:
                return txt.split('uid:')[-1].strip().rstrip(')')
    return None


async def _mark_reviewed(message, approved, by):
    try:
        e = message.embeds[0]
        e.color = discord.Color(0x2ECC71 if approved else 0xE74C3C)
        e.add_field(name='Решение',
                    value=('✅ Одобрено' if approved else '❌ Отклонено') + f' — {by.mention}',
                    inline=False)
        for b in (message.components or []):
            for child in getattr(b, 'children', []):
                if hasattr(child, 'disabled'):
                    child.disabled = True
        await message.edit(embed=e, view=None)
    except Exception as ex:
        _log.debug('verify _mark_reviewed: %s', ex)


# ── Диалог анкеты в ЛС (через wait_for) ─────────────────────────────────
class AgeVerification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._active = set()   # user_id, кому бот сейчас задаёт вопросы

    async def cog_load(self):
        self.bot.add_view(StartApplicationView())
        self.bot.add_view(ReviewView())
        _db()
        self.auto_kick_loop.start()
        _log.info('AgeVerification: панели зарегистрированы')

    async def cog_unload(self):
        self.auto_kick_loop.cancel()

    # ── авто-кик зависших на карантине ───────────────────────────────
    @tasks.loop(hours=6)
    async def auto_kick_loop(self):
        """Тех, кто НЕ отправил анкету и провисел в карантине дольше
        kick_after_days — кикаем (0 = не кикать никогда)."""
        now = time.time()
        for guild in self.bot.guilds:
            try:
                cfg = load_cfg(guild.id)
                if not cfg.get('enabled'):
                    continue
                kick_days = int(cfg.get('kick_after_days', 1) or 0)
                if kick_days <= 0:
                    continue
                deadline = kick_days * 86400
                for p in _all_pending(guild.id, status='quarantine'):
                    qat = p.get('quarantined_at') or 0
                    if not qat or (now - qat) < deadline:
                        continue
                    member = guild.get_member(int(p['user_id']))
                    if member is None:
                        _del_pending(guild.id, p['user_id'])
                        continue
                    try:
                        await member.send(embed=_dm_declined(
                            guild.name,
                            f'Анкета верификации не была заполнена за {kick_days} дн.'))
                    except Exception as ex:
                        _log.debug('verify auto-kick DM %s: %s', p['user_id'], ex)
                    try:
                        await member.kick(
                            reason=f'Верификация: анкета не заполнена за {kick_days} дн.')
                        _set_pending(guild.id, p['user_id'], status='kicked')
                    except discord.Forbidden:
                        _log.warning('verify auto-kick: нет прав на %s', member)
                    except Exception as ex:
                        _log.debug('verify auto-kick: %s', ex)
            except Exception as ex:
                _log.debug('verify auto-kick loop guild %s: %s', guild.id, ex)

    @auto_kick_loop.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_ready()

    # ── вход на сервер ────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        cfg = load_cfg(member.guild.id)
        if not cfg.get('enabled'):
            return
        # возраст аккаунта
        created = member.created_at
        age_days = (datetime.now(timezone.utc) - created).total_seconds() / 86400
        if age_days >= float(cfg.get('min_age_days', 2)):
            # аккаунт достаточно старый — верификация не нужна
            return
        # выдать карантинную роль
        try:
            role = member.guild.get_role(int(cfg['quarantine_role_id'])) if cfg.get('quarantine_role_id') else None
            if role is not None:
                await member.add_roles(role, reason=f'Аккаунт моложе {cfg["min_age_days"]} дн. — верификация')
        except discord.Forbidden:
            _log.warning('verify: нет прав выдать карантинную роль на %s', member.guild.id)
        except Exception as ex:
            _log.debug('verify quarantine role: %s', ex)

        _set_pending(member.guild.id, member.id, status='quarantine',
                     quarantined_at=time.time())

        # ЛС
        vch = member.guild.get_channel(int(cfg['verify_channel_id'])) if cfg.get('verify_channel_id') else None
        mention = vch.mention if vch else None
        try:
            await member.send(embed=_dm_welcome(member.guild.name,
                                                cfg.get('min_age_days', 2), mention))
        except discord.Forbidden:
            _log.info('verify: ЛС закрыты у %s на %s — уведомить не вышло', member, member.guild.id)
        except Exception as ex:
            _log.debug('verify welcome DM: %s', ex)

    # ── сбор анкеты в ЛС ──────────────────────────────────────────────
    async def begin_application(self, user: discord.User, guild: discord.Guild, dm_channel):
        if user.id in self._active:
            return
        self._active.add(user.id)
        answers = {}
        try:
            await dm_channel.send(
                embed=discord.Embed(
                    title='📝 Анкета верификации',
                    description=(f'Сервер **{guild.name}**\nОтветь на 5 вопросов '
                                 f'ниже по очереди. Отвечай честно — это видят модераторы.\n'
                                 f'Можешь отменить в любой момент, написав `отмена`.'),
                    color=0x5865F2))
            for key, question in QUESTIONS:
                await dm_channel.send(f'**{question}**')

                def check(m):
                    return m.author.id == user.id and m.channel.id == dm_channel.id

                try:
                    msg = await self.bot.wait_for('message', timeout=600, check=check)
                except Exception:
                    await dm_channel.send('⌛ Время вышло (10 минут без ответа). '
                                         'Заполни анкету заново кнопкой в канале верификации.')
                    return
                if msg.content.strip().lower() in ('отмена', 'cancel', 'стоп'):
                    await dm_channel.send('Анкета отменена. Можешь начать заново, когда будешь готов.')
                    return
                answers[key] = msg.content.strip()[:1000]

            # отправить модераторам
            await self._submit_application(guild, user, answers)
            await dm_channel.send(embed=discord.Embed(
                title='📨 Анкета отправлена',
                description='Спасибо! Твоя заявка у модераторов — как только проверят, '
                            'ты получишь уведомление здесь, в ЛС.',
                color=0x2ECC71))
        finally:
            self._active.discard(user.id)

    async def _submit_application(self, guild, user, answers):
        cfg = load_cfg(guild.id)
        _set_pending(guild.id, user.id, status='application', answers=answers)
        e = discord.Embed(
            title='🆕 Новая анкета верификации',
            color=0x5865F2)
        acct_age = (datetime.now(timezone.utc) - user.created_at).days
        e.add_field(name='Участник', value=f'{user.mention} ({user})\nID: `{user.id}`', inline=False)
        e.add_field(name='Возраст аккаунта', value=f'{acct_age} дн.', inline=True)
        for key, question in QUESTIONS:
            e.add_field(name=question, value=answers.get(key, '—')[:1000] or '—', inline=False)
        e.set_footer(text=f'verify application · uid: {user.id}')
        view = ReviewView()
        # канал заявок → канал верификации → первый доступный системный
        target = None
        for cid in (cfg.get('review_channel_id'), cfg.get('verify_channel_id')):
            if cid:
                target = guild.get_channel(int(cid))
                if target:
                    break
        try:
            if target is not None:
                msg = await target.send(embed=e, view=view)
            else:
                # запасной вариант — системный канал сервера
                target = guild.system_channel
                msg = await target.send(embed=e, view=view) if target else None
            if msg:
                _set_pending(guild.id, user.id, message_id=str(msg.id))
        except Exception as ex:
            _log.warning('verify: некуда отправить анкету на %s: %s', guild.id, ex)

    # ── настройка в Discord ───────────────────────────────────────────
    @app_commands.command(name='verify-setup',
                          description='Настроить верификацию молодых аккаунтов')
    @app_commands.describe(
        min_age_days='Возраст аккаунта (дней), ниже которого нужна анкета (по умолч. 2)',
        quarantine_role='Роль-ограничение для непроверенных (без доступа)',
        member_role='Роль, которую выдать после верификации (роль участника)',
        verify_channel='Канал с кнопкой анкеты (создам сам, если не указан)',
        review_channel='Канал, куда падают анкеты модераторам',
        enabled='Включить систему сразу?')
    @app_commands.checks.has_permissions(administrator=True)
    async def verify_setup(self, interaction: discord.Interaction,
                           min_age_days: app_commands.Range[int, 0, 365] = 2,
                           quarantine_role: discord.Role = None,
                           member_role: discord.Role = None,
                           verify_channel: discord.TextChannel = None,
                           review_channel: discord.TextChannel = None,
                           enabled: bool = True):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        cfg = load_cfg(guild.id)
        cfg['min_age_days'] = min_age_days
        if quarantine_role:
            cfg['quarantine_role_id'] = str(quarantine_role.id)
        if member_role:
            cfg['member_role_id'] = str(member_role.id)
        if review_channel:
            cfg['review_channel_id'] = str(review_channel.id)

        # создать канал верификации, если не задан
        if verify_channel is None:
            over = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=True, send_messages=False, read_messages=True),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, manage_messages=True,
                    embed_links=True, read_message_history=True),
            }
            qrole = guild.get_role(int(cfg['quarantine_role_id'])) if cfg.get('quarantine_role_id') else None
            if qrole:
                over[qrole] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=False, read_messages=True)
            try:
                verify_channel = await guild.create_text_channel(
                    'верификация', overwrites=over,
                    topic='Подтверди, что ты не бот: жми «Заполнить анкету»',
                    reason='Система верификации: канал не задан — создан')
            except Exception as ex:
                return await interaction.followup.send(
                    f'Не удалось создать канал верификации: {ex}. Укажи канал параметром.',
                    ephemeral=True)
        cfg['verify_channel_id'] = str(verify_channel.id)
        cfg['enabled'] = enabled
        save_cfg(guild.id, cfg)

        # кнопка в канале верификации
        try:
            pin_embed = discord.Embed(
                title='🛡️ Верификация участников',
                description=('Если у тебя **новый аккаунт**, доступ к серверу '
                            'временно ограничен. Нажми кнопку ниже и ответь на '
                            'несколько вопросов **в личных сообщениях бота** — '
                            'модераторы откроют доступ.'),
                color=0x5865F2)
            await verify_channel.send(embed=pin_embed, view=StartApplicationView())
        except Exception as ex:
            _log.warning('verify: кнопка в канале %s: %s', verify_channel.id, ex)

        e = discord.Embed(title='Система верификации настроена', color=0x2ECC71)
        e.add_field(name='Статус', value='🟢 Включена' if enabled else '⚪ Выключена', inline=False)
        e.add_field(name='Порог возраста', value=f'{min_age_days} дн.', inline=True)
        e.add_field(name='Канал анкеты', value=verify_channel.mention, inline=True)
        e.add_field(name='Карантинная роль', value=quarantine_role.mention if quarantine_role else 'не задана', inline=True)
        e.add_field(name='Роль участника', value=member_role.mention if member_role else 'не задана', inline=True)
        e.add_field(name='Канал заявок модерам', value=review_channel.mention if review_channel else '= канал верификации', inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)


async def setup(bot):
    from config import Config
    await bot.add_cog(AgeVerification(bot), guilds=Config.guild_objects())
