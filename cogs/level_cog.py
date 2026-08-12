"""
Level Cog
Система уровней — РЕАЛЬНЫЕ данные из data/xp_{guild}.json (накапливаются
модулем cogs/autorole_level.py). Ранее здесь была декоративная заглушка —
теперь карточка, топ, награды и !setlevel работают на живом хранилище.
"""
import discord
from discord.ext import commands

from logger import get_logger
from json_store import load_json as _js_load, save_json as _js_save

log = get_logger("level_cog")

# Формула прогрессии — зеркало autorole_level._level_from_xp
# (100 XP на 1-й уровень, каждый следующий ×1.15, floor).
def _progress_from_xp(xp) -> tuple:
    """(level, текущий_xp_в_уровне, нужно_до_следующего)."""
    level = 0
    required = 100
    xp = max(0, int(xp or 0))
    while xp >= required:
        xp -= required
        level += 1
        required = int(required * 1.15)
    return level, xp, required


def _xp_total_for_level(level) -> int:
    """Сколько суммарно XP нужно, чтобы достичь level."""
    total = 0
    required = 100
    for _ in range(max(0, int(level))):
        total += required
        required = int(required * 1.15)
    return total


def _bar(ratio: float, length: int = 16) -> str:
    ratio = min(1.0, max(0.0, ratio))
    done = round(ratio * length)
    return '█' * done + '░' * (length - done)


class LevelCog(commands.Cog):
    """Уровни: карточка, топ, награды, установка уровня (живые данные)."""

    # ── хранилище (data/xp_{gid}.json: uid → {'xp','level'}) ────────────
    def _xp_data(self, guild_id) -> dict:
        return _js_load(f'data/xp_{int(guild_id)}.json', {}, log=log)

    def _save_xp_data(self, guild_id, data: dict):
        _js_save(f'data/xp_{int(guild_id)}.json', data, log=log)

    def _level_roles(self, guild_id) -> dict:
        return _js_load(f'data/level_roles_{int(guild_id)}.json', {}, log=log)

    # ── команды ──────────────────────────────────────────────────────────
    @commands.command(name='level-rank', aliases=['уровень'])
    async def rank(self, ctx, member: discord.Member = None):
        """Показать карточку уровня (реальные данные)"""
        if not ctx.guild:
            await ctx.send('Эта команда работает на сервере.')
            return
        member = member or ctx.author
        data = self._xp_data(ctx.guild.id)
        rec = data.get(str(member.id)) or {}
        total = int(rec.get('xp', 0) or 0)
        level, cur, need = _progress_from_xp(total)

        # место в рейтинге сервера (по суммарному XP)
        ordered = sorted(((int(r.get('xp', 0) or 0), uid) for uid, r in data.items()
                          if isinstance(r, dict)), reverse=True)
        place = next((i + 1 for i, (_, uid) in enumerate(ordered)
                      if uid == str(member.id)), len(ordered) + 1)

        embed = discord.Embed(
            title=f"📊 Уровень — {member.display_name}",
            color=discord.Color.dark_grey(),
            timestamp=discord.utils.utcnow(),
        )
        try:
            embed.set_thumbnail(url=member.display_avatar.url)
        except Exception as _ex:
            log.debug("rank(): подавлено: %s", _ex)
        embed.add_field(name="Уровень", value=f"**{level}**", inline=True)
        embed.add_field(name="XP", value=f"{cur}/{need}", inline=True)
        embed.add_field(name="Рейтинг", value=f"#{place} из {len(ordered)}"
                        if ordered else '—', inline=True)
        embed.add_field(name="Прогресс",
                        value=f"`{_bar(cur / need)}` {int(cur / need * 100)}%"
                        if need else '`—`', inline=False)
        embed.set_footer(text=f"Всего опыта: {total:,}")
        await ctx.send(embed=embed)

    @commands.command(name='level-lb', aliases=['level-top'])
    async def leaderboard(self, ctx):
        """Топ-10 участников сервера по уровням"""
        if not ctx.guild:
            await ctx.send('Эта команда работает на сервере.')
            return
        data = self._xp_data(ctx.guild.id)
        rows = []
        for uid, rec in data.items():
            if not isinstance(rec, dict):
                continue
            total = int(rec.get('xp', 0) or 0)
            if total <= 0:
                continue
            lvl, _, _ = _progress_from_xp(total)
            rows.append((total, lvl, uid))
        rows.sort(reverse=True)

        embed = discord.Embed(
            title="🏆 Таблица лидеров по уровням",
            color=discord.Color.dark_grey(),
            timestamp=discord.utils.utcnow(),
        )
        if not rows:
            embed.description = ('Пока пусто — опыт начисляется за сообщения.\n'
                                 'Напишите что-нибудь в чат!')
        medals = ['🥇', '🥈', '🥉']
        lines = []
        for i, (total, lvl, uid) in enumerate(rows[:10]):
            member = ctx.guild.get_member(int(uid))
            name = member.display_name if member else f'ID {uid}'
            mark = medals[i] if i < 3 else f'**#{i + 1}**'
            lines.append(f'{mark} {name} — ур. **{lvl}** · {total:,} XP')
        embed.description = '\n'.join(lines) if lines else embed.description
        embed.set_footer(text=f'{ctx.guild.name} · участников в рейтинге: {len(rows)}')
        await ctx.send(embed=embed)

    @commands.command(name='rewards', aliases=['награды'])
    async def rewards(self, ctx):
        """Награды за уровни — реальные из настроек сервера"""
        if not ctx.guild:
            await ctx.send('Эта команда работает на сервере.')
            return
        lvl_roles = self._level_roles(ctx.guild.id)
        embed = discord.Embed(
            title="🎁 Награды за уровни",
            color=discord.Color.dark_grey(),
            timestamp=discord.utils.utcnow(),
        )
        if not lvl_roles:
            embed.description = ('Награды не настроены.\nМодератор может задать их '
                                 'в веб-панели (Левелинг → роли за уровни).')
        else:
            lines = []
            for lvl_s, role_id in sorted(lvl_roles.items(),
                                         key=lambda kv: int(kv[0])):
                role = ctx.guild.get_role(int(role_id))
                name = role.name if role else f'ID {role_id}'
                lines.append(f'Уровень **{lvl_s}** — {name}')
            embed.description = '\n'.join(lines)
        await ctx.send(embed=embed)

    @commands.command(name='setlevel', aliases=['установитьуровень'])
    @commands.has_permissions(administrator=True)
    async def setlevel(self, ctx, member: discord.Member, level: int):
        """Установить уровень участника (пишет суммарный XP по формуле)"""
        if not ctx.guild:
            await ctx.send('Эта команда работает на сервере.')
            return
        if level < 0 or level > 1000:
            await ctx.send('Уровень должен быть от 0 до 1000.')
            return
        data = self._xp_data(ctx.guild.id)
        uid = str(member.id)
        rec = data.get(uid) or {}
        total = _xp_total_for_level(level)
        rec['xp'] = total
        rec['level'] = level
        data[uid] = rec
        self._save_xp_data(ctx.guild.id, data)

        embed = discord.Embed(
            title="✅ Уровень обновлён",
            description=(f"**{member.mention}:** уровень {level}\n"
                         f"Суммарный опыт выставлен на {total:,} XP"),
            color=discord.Color.dark_grey(),
            timestamp=discord.utils.utcnow(),
        )
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_ready(self):
        """Бот готов"""
        log.info("LevelCog loaded")


async def setup(bot):
    await bot.add_cog(LevelCog(bot))
