# -*- coding: utf-8 -*-
"""Шаблон сервера (Server Template Cog)
======================================
Снимок структуры сервера (роли + категории + каналы) в переносимый JSON:
новый сервер поднимается по знакомому плану в одну команду. Системные и
управляемые ботами роли, кастомные перезаписи прав и премиум-бусты в снимок
не берём — только человеческую структуру.

- /шаблон сохранить <имя> [описание] — снять снимок текущего сервера
- /шаблон список                     — сохранённые шаблоны
- /шаблон инфо <имя>                 — что внутри шаблона
- /шаблон применить <имя>            — создать недостающие роли/каналы
- /шаблон удалить <имя>              — убрать шаблон

Применение консервативное: только СОЗДАЁТ отсутствующее, существующее
не трогает — перебить руками настроенный сервер невозможно.

Хранилище — SQLite (GuildData 'server_template'). Метки — aware UTC.
"""
from datetime import datetime, timezone

import discord
from discord.ext import commands

from db import GuildData
from logger import get_logger
from services import text_format as tf

log = get_logger("server_template")

UTC = timezone.utc
COLOR = 0x1ABC9C
MAX_TEMPLATES = 10


# ─── чистые функции (покрыты тестом на фейках) ──────────────────────────────

def role_snapshot(role):
    """Роль -> компактный dict (id не храним — слепок смысла, не ссылок)."""
    color = getattr(role, 'color', None)
    color_v = getattr(color, 'value', 0) or 0
    perms = getattr(role, 'permissions', None)
    return {
        'name': str(getattr(role, 'name', 'role')),
        'color': int(color_v),
        'permissions': int(getattr(perms, 'value', 0) or 0),
        'hoist': bool(getattr(role, 'hoist', False)),
        'mentionable': bool(getattr(role, 'mentionable', False)),
        'position': int(getattr(role, 'position', 0) or 0),
    }


def snapshot_guild(guild):
    """Сервер -> шаблон. @everyone и managed-роли пропускаем."""
    roles = []
    for role in getattr(guild, 'roles', []):
        if getattr(role, 'is_default', lambda: False)():
            continue
        if getattr(role, 'managed', False):
            continue
        roles.append(role_snapshot(role))
    roles.sort(key=lambda r: r['position'])

    categories = []
    channels_loose = []
    for cat in getattr(guild, 'categories', []):
        entry = {'name': str(getattr(cat, 'name', 'category')), 'channels': []}
        for ch in getattr(cat, 'channels', []):
            entry['channels'].append(channel_snapshot(ch))
        categories.append(entry)
    for ch in getattr(guild, 'text_channels', []):
        if getattr(ch, 'category', None) is None:
            channels_loose.append(channel_snapshot(ch))
    return {'roles': roles, 'categories': categories,
            'channels': channels_loose, 'version': 1}


def channel_snapshot(ch):
    return {
        'name': str(getattr(ch, 'name', 'channel')),
        'type': str(getattr(ch, 'type', 'text')).replace('ChannelType.', ''),
        'topic': str(getattr(ch, 'topic', '') or '')[:200],
        'slowmode': int(getattr(ch, 'slowmode_delay', 0) or 0),
        'nsfw': bool(getattr(ch, 'nsfw', False)),
        'position': int(getattr(ch, 'position', 0) or 0),
    }


def template_meta(tpl):
    """Строка сводки: '12 ролей · 5 категорий · 20 каналов'."""
    n_roles = len(tpl.get('roles', []))
    n_cats = len(tpl.get('categories', []))
    n_ch = sum(len(c.get('channels', [])) for c in tpl.get('categories', []))
    n_ch += len(tpl.get('channels', []))
    return (f"{tf.spell(n_roles, 'роль', 'роли', 'ролей')} · "
            f"{tf.spell(n_cats, 'категория', 'категории', 'категорий')} · "
            f"{tf.spell(n_ch, 'канал', 'канала', 'каналов')}")


def diff_plan(tpl, guild):
    """Что применение создаст: недостающие имена ролей/категорий/каналов."""
    have_roles = {str(r.name).lower() for r in getattr(guild, 'roles', [])}
    have_cats = {str(c.name).lower() for c in getattr(guild, 'categories', [])}
    have_ch = {str(c.name).lower() for c in getattr(guild, 'text_channels', [])}
    have_ch |= {str(c.name).lower() for c in getattr(guild, 'voice_channels', [])}
    plan = {'roles': [], 'categories': [], 'channels': []}
    for r in tpl.get('roles', []):
        if r['name'].lower() not in have_roles:
            plan['roles'].append(r['name'])
    for c in tpl.get('categories', []):
        for ch in c.get('channels', []):
            if ch['name'].lower() not in have_ch:
                plan['channels'].append(ch['name'])
        if c['name'].lower() not in have_cats:
            plan['categories'].append(c['name'])
    for ch in tpl.get('channels', []):
        if ch['name'].lower() not in have_ch:
            plan['channels'].append(ch['name'])
    return plan


def empty_store():
    return {}


# ─── ког ────────────────────────────────────────────────────────────────────

class ServerTemplate(commands.Cog):
    """Снимки структуры сервера: сохранить, развернуть, сравнить."""

    def __init__(self, bot):
        self.bot = bot
        self.db = GuildData('server_template')

    def _store(self, guild_id):
        return self.db.get(guild_id, 'templates', empty_store()) or empty_store()

    def _save_store(self, guild_id, store):
        self.db.set(guild_id, 'templates', store)

    @commands.hybrid_group(name='шаблон', aliases=['template'],
                           description='Шаблоны структуры сервера')
    @commands.has_permissions(administrator=True)
    async def grp(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.reply('Команды: `сохранить`, `список`, `инфо`, `применить`, `удалить`.',
                            mention_author=False)

    @grp.command(name='сохранить', description='Снять снимок текущего сервера')
    async def cmd_save(self, ctx, имя: str, *, описание: str = ''):
        имя = имя.strip().lower()[:30]
        if not имя:
            await ctx.reply('Имя шаблона пустое.', mention_author=False)
            return
        store = self._store(ctx.guild.id)
        if имя not in store and len(store) >= MAX_TEMPLATES:
            await ctx.reply(f'Максимум {MAX_TEMPLATES} шаблонов на сервер.',
                            mention_author=False)
            return
        tpl = snapshot_guild(ctx.guild)
        store[имя] = {
            'template': tpl,
            'description': описание[:200],
            'created_at': datetime.now(UTC).isoformat(),
            'created_by': str(ctx.author),
            'source_guild': ctx.guild.name,
        }
        self._save_store(ctx.guild.id, store)
        await ctx.reply(f'Шаблон **{имя}** сохранён: {template_meta(tpl)}.',
                        mention_author=False)

    @grp.command(name='список', description='Сохранённые шаблоны')
    async def cmd_list(self, ctx):
        store = self._store(ctx.guild.id)
        if not store:
            await ctx.reply('Шаблонов пока нет. Сделайте `/шаблон сохранить <имя>`.',
                            mention_author=False)
            return
        lines = []
        for name, entry in store.items():
            lines.append(f"**{name}** — {template_meta(entry['template'])}"
                         + (f" — {entry['description'][:60]}" if entry.get('description') else ''))
        embed = discord.Embed(title='Шаблоны сервера', description='\n'.join(lines),
                              color=COLOR)
        await ctx.reply(embed=embed, mention_author=False)

    @grp.command(name='инфо', description='Что внутри шаблона')
    async def cmd_info(self, ctx, имя: str):
        entry = self._store(ctx.guild.id).get(имя.strip().lower())
        if not entry:
            await ctx.reply(f'Шаблон **{имя}** не найден.', mention_author=False)
            return
        tpl = entry['template']
        lines = [f"Роли: {', '.join(r['name'] for r in tpl['roles'][:15]) or '—'}"]
        for cat in tpl['categories'][:10]:
            chs = ', '.join(c['name'] for c in cat['channels'])
            lines.append(f"{cat['name']}: {chs or '—'}")
        if tpl['channels']:
            lines.append('Без категории: ' + ', '.join(c['name'] for c in tpl['channels']))
        embed = discord.Embed(title=f"Шаблон «{имя}» · {template_meta(tpl)}",
                              description=tf.clamp_text('\n'.join(lines), 3800),
                              color=COLOR)
        embed.set_footer(text=f"Создан: {entry['created_at'][:10]} · {entry['created_by']}")
        await ctx.reply(embed=embed, mention_author=False)

    @grp.command(name='применить', description='Создать недостающие роли и каналы')
    async def cmd_apply(self, ctx, имя: str):
        entry = self._store(ctx.guild.id).get(имя.strip().lower())
        if not entry:
            await ctx.reply(f'Шаблон **{имя}** не найден.', mention_author=False)
            return
        tpl = entry['template']
        plan = diff_plan(tpl, ctx.guild)
        if not any(plan.values()):
            await ctx.reply('Структура уже совпадает — создавать нечего.',
                            mention_author=False)
            return

        msg = await ctx.reply(f'Применяю **{имя}**: '
                              f'{len(plan["roles"])} ролей, {len(plan["categories"])} категорий, '
                              f'{len(plan["channels"])} каналов…', mention_author=False)
        made_roles, made_cats, made_chs = 0, 0, 0

        for r in tpl['roles']:
            if r['name'] not in plan['roles']:
                continue
            try:
                await ctx.guild.create_role(
                    name=r['name'],
                    permissions=discord.Permissions(r['permissions']),
                    color=discord.Color(r['color']),
                    hoist=r['hoist'], mentionable=r['mentionable'],
                    reason=f'Шаблон «{имя}»')
                made_roles += 1
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.warning('template: роль %s не создана на %s: %s',
                            r['name'], ctx.guild.id, _ex)

        cat_map = {}
        existing_cats = {c.name.lower(): c for c in ctx.guild.categories}
        for c in tpl['categories']:
            if c['name'].lower() in existing_cats:
                cat_map[c['name']] = existing_cats[c['name'].lower()]
                continue
            try:
                created = await ctx.guild.create_category(c['name'], reason=f'Шаблон «{имя}»')
                cat_map[c['name']] = created
                made_cats += 1
            except (discord.Forbidden, discord.HTTPException) as _ex:
                log.warning('template: категория %s не создана на %s: %s',
                            c['name'], ctx.guild.id, _ex)

        existing_ch = {c.name.lower() for c in ctx.guild.channels}
        for c in tpl['categories']:
            parent = cat_map.get(c['name'])
            for ch in c['channels']:
                if ch['name'].lower() in existing_ch:
                    continue
                if await self._mk_channel(ctx.guild, ch, parent, имя):
                    made_chs += 1
        for ch in tpl['channels']:
            if ch['name'].lower() in existing_ch:
                continue
            if await self._mk_channel(ctx.guild, ch, None, имя):
                made_chs += 1

        await msg.edit(content=(f'Шаблон **{имя}** применён: '
                                f'{made_roles} новых ролей, {made_cats} категорий, '
                                f'{made_chs} каналов. Существующие не трогал.'))

    async def _mk_channel(self, guild, spec, parent, tpl_name):
        kind = spec.get('type', 'text')
        try:
            if 'voice' in kind:
                await guild.create_voice_channel(
                    spec['name'], category=parent, reason=f'Шаблон «{tpl_name}»')
            elif 'forum' in kind:
                await guild.create_forum(
                    name=spec['name'], category=parent,
                    topic=spec.get('topic') or None, reason=f'Шаблон «{tpl_name}»')
            else:
                await guild.create_text_channel(
                    spec['name'], category=parent,
                    topic=spec.get('topic') or None,
                    slowmode_delay=spec.get('slowmode', 0),
                    nsfw=spec.get('nsfw', False), reason=f'Шаблон «{tpl_name}»')
            return True
        except (discord.Forbidden, discord.HTTPException) as _ex:
            log.warning('template: канал %s не создан на %s: %s',
                        spec.get('name'), guild.id, _ex)
            return False

    @grp.command(name='удалить', description='Удалить шаблон')
    async def cmd_delete(self, ctx, имя: str):
        store = self._store(ctx.guild.id)
        if store.pop(имя.strip().lower(), None) is None:
            await ctx.reply(f'Шаблон **{имя}** не найден.', mention_author=False)
            return
        self._save_store(ctx.guild.id, store)
        await ctx.reply(f'Шаблон **{имя}** удалён.', mention_author=False)


async def setup(bot):
    await bot.add_cog(ServerTemplate(bot))
