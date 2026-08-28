# -*- coding: utf-8 -*-
"""Автоответы по триггерам (Triggers Cog)
========================================
Бот сам отвечает на ключевые слова: «правила» → ссылка на правила,
«ip» → адрес игрового сервера. Модераторам не нужно повторять одно и то
же по сто раз — фраза в чате вызывает готовый ответ.

- /триг добавить слово | ответ   — новый триггер (| разделяет)
- /триг точный слово | ответ     — срабатывает только на точное слово
- /триг список                   — все триггеры
- /триг убрать <№>               — удалить
- /триг кулдаун <сек>            — пауза между срабатываниями одного слова

Хранилище — SQLite (GuildData 'triggers'). Боты триггеры не дёргают.
"""
from datetime import datetime, timezone

import discord
from discord.ext import commands

from db import GuildData
from logger import get_logger
from services import text_format as tf

log = get_logger("triggers")

UTC = timezone.utc
COLOR = 0x3498DB
MAX_TRIGGERS = 50
DEFAULT_COOLDOWN = 30


# ─── чистые функции (покрыты тестом) ────────────────────────────────────────

def empty_state():
    return {'next_id': 1, 'items': [], 'cooldown': DEFAULT_COOLDOWN}


def add_trigger(state, trigger, response, exact=False):
    """Добавить правило. Возвращает (item, ошибка)."""
    trigger = str(trigger or '').strip()
    response = str(response or '').strip()
    if not trigger or len(trigger) < 2:
        return None, 'триггер — хотя бы 2 символа'
    if not response:
        return None, 'пустой ответ'
    if len(state['items']) >= MAX_TRIGGERS:
        return None, f'максимум {MAX_TRIGGERS} триггеров'
    low = trigger.lower()
    if any(i['trigger'].lower() == low and i['exact'] == bool(exact)
           for i in state['items']):
        return None, f'такой триггер уже есть — №{[i for i in state["items"] if i["trigger"].lower() == low][0]["id"]}'
    item = {
        'id': state['next_id'],
        'trigger': trigger,
        'response': response[:900],
        'exact': bool(exact),
        'uses': 0,
        'created_at': datetime.now(UTC).isoformat(),
    }
    state['next_id'] += 1
    state['items'].append(item)
    return item, None


def remove_trigger(state, item_id):
    for i, item in enumerate(state['items']):
        if item['id'] == item_id:
            state['items'].pop(i)
            return True
    return False


def matches(item, content):
    """Срабатывает ли правило на текст. exact — слово целиком, иначе подстрока."""
    trig = item['trigger'].lower()
    text = str(content or '').lower()
    if item.get('exact'):
        # слово целиком: границы — не буквы/цифры
        import re as _re
        return bool(_re.search(r'(?<![\wё])' + _re.escape(trig) + r'(?![\wё])', text))
    return trig in text


def find_match(items, content, cooldowns, now, cooldown=DEFAULT_COOLDOWN):
    """Первое сработавшее правило с учётом кулдауна.

    cooldowns: {trigger_id: ISO времени последнего срабатывания} — in-memory
    карта кога, в БД не пишется (намеренно: кулдаун — рантайм-штука).
    """
    for item in sorted(items, key=lambda i: -len(i['trigger'])):
        if not matches(item, content):
            continue
        last = cooldowns.get(item['id'])
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                if (now - last_dt).total_seconds() < cooldown:
                    continue
            except ValueError:
                log.debug('triggers: битая метка кулдауна у #%s', item['id'])
        return item
    return None


def fire(item, cooldowns, now):
    """Отметить срабатывание: счётчик + кулдаун."""
    item['uses'] = item.get('uses', 0) + 1
    cooldowns[item['id']] = now.isoformat()


def split_spec(text):
    """'слово | ответ на него' -> ('слово', 'ответ на него'). None, если нет '|'."""
    parts = str(text or '').split('|', 1)
    if len(parts) != 2:
        return None, None
    return parts[0].strip(), parts[1].strip()


# ─── ког ────────────────────────────────────────────────────────────────────

class Triggers(commands.Cog):
    """Автоответы на ключевые слова."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('triggers')
        self._cooldowns = {}  # {guild_id: {trigger_id: iso}}

    def _state(self, guild_id):
        return self.db.get(guild_id, 'state', empty_state()) or empty_state()

    def _save(self, guild_id, state):
        self.db.set(guild_id, 'state', state)

    # ---- слушатель ----
    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return
        state = self._state(message.guild.id)
        if not state['items']:
            return
        cds = self._cooldowns.setdefault(message.guild.id, {})
        now = datetime.now(UTC)
        item = find_match(state['items'], message.content, cds, now,
                          state.get('cooldown', DEFAULT_COOLDOWN))
        if item is None:
            return
        fire(item, cds, now)
        self._save(message.guild.id, state)
        try:
            await message.reply(item['response'], mention_author=False)
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.debug('triggers: ответ на #%s не ушёл: %s', item['id'], _ex)

    # ---- команды ----
    @commands.hybrid_group(name='триг', aliases=['trigger', 'триггер'],
                           description='Автоответы на слова')
    @commands.has_permissions(manage_guild=True)
    async def grp(self, ctx):
        if ctx.invoked_subcommand is None:
            await self._list(ctx)

    @grp.command(name='добавить', description='триггер | ответ (подстрока)')
    async def cmd_add(self, ctx, *, спека: str):
        trigger, response = split_spec(спека)
        if trigger is None:
            await ctx.reply('Формат: `/триг добавить слово | ответ`.',
                            mention_author=False)
            return
        state = self._state(ctx.guild.id)
        item, err = add_trigger(state, trigger, response, exact=False)
        if err:
            await ctx.reply(f'Не добавлено: {err}.', mention_author=False)
            return
        self._save(ctx.guild.id, state)
        await ctx.reply(f'Триггер **№{item["id"]}** на «{item["trigger"]}» добавлен.',
                        mention_author=False)

    @grp.command(name='точный', description='триггер | ответ (слово целиком)')
    async def cmd_add_exact(self, ctx, *, спека: str):
        trigger, response = split_spec(спека)
        if trigger is None:
            await ctx.reply('Формат: `/триг точный слово | ответ`.', mention_author=False)
            return
        state = self._state(ctx.guild.id)
        item, err = add_trigger(state, trigger, response, exact=True)
        if err:
            await ctx.reply(f'Не добавлено: {err}.', mention_author=False)
            return
        self._save(ctx.guild.id, state)
        await ctx.reply(f'Точный триггер **№{item["id"]}** на «{item["trigger"]}» добавлен.',
                        mention_author=False)

    @grp.command(name='убрать', description='Удалить триггер по номеру')
    async def cmd_remove(self, ctx, номер: int):
        state = self._state(ctx.guild.id)
        if not remove_trigger(state, номер):
            await ctx.reply(f'Триггер №{номер} не найден.', mention_author=False)
            return
        self._save(ctx.guild.id, state)
        await ctx.reply(f'Триггер №{номер} удалён.', mention_author=False)

    @grp.command(name='кулдаун', description='Пауза между срабатываниями (сек)')
    async def cmd_cooldown(self, ctx, сек: int):
        if not 0 <= сек <= 3600:
            await ctx.reply('Кулдаун: 0–3600 секунд.', mention_author=False)
            return
        state = self._state(ctx.guild.id)
        state['cooldown'] = сек
        self._save(ctx.guild.id, state)
        await ctx.reply(f'Кулдаун триггеров: **{сек} сек**.', mention_author=False)

    @grp.command(name='список', description='Все триггеры')
    async def cmd_list(self, ctx):
        await self._list(ctx)

    async def _list(self, ctx):
        state = self._state(ctx.guild.id)
        if not state['items']:
            await ctx.reply('Триггеров нет. Добавьте: `/триг добавить слово | ответ`.',
                            mention_author=False)
            return
        lines = []
        for i in state['items'][:20]:
            kind = 'слово целиком' if i['exact'] else 'подстрока'
            uses = tf.spell(i.get('uses', 0), 'срабатывание', 'срабатывания', 'срабатываний')
            lines.append(f"**№{i['id']}** `{i['trigger']}` ({kind}, {uses}) → {i['response'][:60]}")
        embed = discord.Embed(title=f"Триггеры ({len(state['items'])})",
                              description='\n'.join(tf.clamp_text(x, 220) for x in lines),
                              color=COLOR)
        embed.set_footer(text=f"Кулдаун: {state.get('cooldown', DEFAULT_COOLDOWN)} сек")
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot):
    await bot.add_cog(Triggers(bot))
