"""
Backup — автоматическое резервное копирование данных бота.

• Каждый день в BACKUP_HOUR (по локальному времени хоста, по умолчанию 05:00)
  собирается zip-архив папки data/ в BACKUP_DIR (по умолчанию backups/).
• Хранится не более BACKUP_KEEP последних архивов — старые удаляются.
• Секреты (panel_credentials*, flask_secret.key, .env, сессии) в архив
  НЕ попадают — это гарантирует services/backup.py.
• О каждом бэкапе бот отчитывается в мод-лог канал сервера (карточкой).
• Опционально (BACKUP_ATTACH=1) небольшой архив прикладывается файлом.
  По умолчанию ВЫКЛЮЧЕНО: данные сервера не должны улётать в Discord-канал
  без явного желания владельца. Скачать архив можно и из веб-панели (/backups).

Команды (только администраторы):
  /backup now     — создать копию немедленно
  /backup list    — список архивов на диске
  /backup status  — настройки расписания и статистика

ENV: BACKUP_ENABLED=1|0, BACKUP_HOUR=0..23, BACKUP_KEEP=1..90,
     BACKUP_DIR=backups, BACKUP_ATTACH=0|1
"""
import asyncio
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from logger import get_logger
from services import backup as bk

log = get_logger('backup')

GOLD = 0xD4AF37
GREEN = 0x2ECC71
RED = 0xE74C3C

# Discord без Nitro не принимает файлы больше ~8 МБ — держим запас.
MAX_ATTACH_BYTES = int(7.5 * 1024 * 1024)


def _env_int(name, default, lo=None, hi=None):
    try:
        v = int((os.getenv(name) or '').strip() or default)
    except (TypeError, ValueError):
        v = default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def backup_enabled():
    return (os.getenv('BACKUP_ENABLED', '1').strip().lower()
            not in {'0', 'false', 'no', 'off'})


def backup_hour():
    return _env_int('BACKUP_HOUR', 5, 0, 23)


def backup_keep():
    return _env_int('BACKUP_KEEP', bk.BACKUP_KEEP_DEFAULT, 1, 90)


def backup_dir():
    return (os.getenv('BACKUP_DIR') or bk.BACKUP_DIR_DEFAULT).strip() \
        or bk.BACKUP_DIR_DEFAULT


def backup_attach():
    return os.getenv('BACKUP_ATTACH', '0').strip().lower() in {'1', 'true', 'yes', 'on'}


class Backup(commands.Cog):
    """Автобэкапы + ручное управление архивами."""

    def __init__(self, bot):
        self.bot = bot
        self._last_run_date = None
        self._last_run_ok = None   # None=ещё не было, True/False — итог последнего
        if backup_enabled():
            self.auto_backup.start()
        else:
            log.info('[BACKUP] автобэкап выключен (BACKUP_ENABLED=0)')

    def cog_unload(self):
        self.auto_backup.cancel()

    # ── расписание ───────────────────────────────────────────────────────
    def should_run_now(self, now=None):
        """Чистая проверка «пора ли делать авто-бэкап» (легко тестируется)."""
        now = now or datetime.now()
        return now.hour == backup_hour() and self._last_run_date != now.date()

    def mark_ran(self, now=None):
        self._last_run_date = (now or datetime.now()).date()

    @tasks.loop(seconds=60)
    async def auto_backup(self):
        try:
            if not backup_enabled() or not self.should_run_now():
                return
            self.mark_ran()  # даже при ошибке не долбим каждую минуту
            await self.run_backup(reason='авто (по расписанию)')
        except Exception as e:
            self._last_run_ok = False
            log.warning(f'[BACKUP] авто-бэкап не удался: {e}')

    @auto_backup.before_loop
    async def _before_auto(self):
        await self.bot.wait_until_ready()

    # ── ядро ─────────────────────────────────────────────────────────────
    async def run_backup(self, reason='ручной', by=None):
        """Создать архив, подрезать старые, отчитаться. Возвращает (info, removed)."""
        info = await asyncio.to_thread(
            bk.create_backup, backup_dir=backup_dir(), reason=reason, by=by)
        removed = await asyncio.to_thread(
            bk.rotate_backups, backup_dir=backup_dir(), keep=backup_keep())
        self._last_run_ok = True
        log.info(f"[BACKUP] +{info['name']} ({bk.format_size(info['size'])}, "
                 f"файлов: {info['files']}), удалено старых: {len(removed)}")
        try:
            await self._notify(info, removed)
        except Exception as e:
            log.warning(f'[BACKUP] уведомление в Discord не отправлено: {e}')
        return info, removed

    async def _notify(self, info, removed):
        """Карточка-отчёт в мод-лог (+ файл, если разрешено и влезает)."""
        guilds = getattr(self.bot, 'guilds', None) or []
        if not guilds:
            return
        from cogs.logs import ensure_log_channel, _styled_log_embed, _safe_send
        ch = await ensure_log_channel(guilds[0], 'mod')
        if not ch:
            return
        fields = [
            ('Архив', f"`{info['name']}`"),
            ('Размер', f"{bk.format_size(info['size'])} "
                       f"(исходных {bk.format_size(info['source_bytes'])})"),
            ('Файлов в архиве', str(info['files'])),
            ('Причина', info.get('reason') or '—'),
        ]
        if info.get('by'):
            fields.append(('Запустил', info['by']))
        if info.get('skipped'):
            fields.append(('Пропущено (секреты/занятые)', str(info['skipped'])))
        if removed:
            fields.append(('Ротация', f'удалено старых: {len(removed)} '
                                      f'(храним последние {backup_keep()})'))
        embed = _styled_log_embed(guilds[0], 'сервер', '💾 Резервная копия данных',
                                  fields=fields, color=GREEN)

        # Файл прикладываем ТОЛЬКО при явном BACKUP_ATTACH=1 и маленьком размере —
        # с картинкой-логом и без лишнего риска утечки данных в канал.
        if backup_attach() and info['size'] <= MAX_ATTACH_BYTES:
            path = bk.resolve_backup(info['name'], backup_dir())
            if path:
                await ch.send(embed=embed,
                              file=discord.File(path, filename=info['name']))
                return
        await _safe_send(ch, embed=embed)

    # ── команды ──────────────────────────────────────────────────────────
    backup_group = app_commands.Group(name='backup',
                                      description='Резервные копии данных бота')

    @backup_group.command(name='now', description='Создать резервную копию прямо сейчас')
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_now(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            info, removed = await self.run_backup(
                reason='ручной (команда)', by=str(interaction.user))
        except Exception as e:
            await interaction.followup.send(
                f'⚠️ Бэкап не удался: `{str(e)[:300]}`', ephemeral=True)
            return
        e = discord.Embed(title='💾 Резервная копия создана', color=GREEN,
                          timestamp=datetime.now(timezone.utc))
        e.add_field(name='Архив', value=f"`{info['name']}`", inline=False)
        e.add_field(name='Размер', value=bk.format_size(info['size']), inline=True)
        e.add_field(name='Файлов', value=str(info['files']), inline=True)
        if removed:
            e.add_field(name='Удалено старых', value=str(len(removed)), inline=True)
        e.set_footer(text='Все копии: /backup list · Скачать: веб-панель → Бэкапы')
        await interaction.followup.send(embed=e, ephemeral=True)

    @backup_group.command(name='list', description='Показать список резервных копий на диске')
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_list(self, interaction: discord.Interaction):
        items = await asyncio.to_thread(bk.list_backups, backup_dir())
        e = discord.Embed(title='💾 Резервные копии', color=GOLD,
                          timestamp=datetime.now(timezone.utc))
        if not items:
            e.description = ('Архивов пока нет. Первый появится по расписанию '
                             f'(в {backup_hour():02d}:00) или после /backup now.')
        else:
            shown = items[:10]
            e.description = '\n'.join(
                f"`{i + 1}.` `{it['name']}` — **{it['size_h']}** · {it['created_at']}"
                for i, it in enumerate(shown))
            if len(items) > len(shown):
                e.description += f'\n… и ещё {len(items) - len(shown)}'
            total = sum(it['size'] for it in items)
            e.set_footer(text=f'Всего {len(items)} шт · {bk.format_size(total)} · '
                              f'храним последние {backup_keep()}')
        await interaction.response.send_message(embed=e, ephemeral=True)

    @backup_group.command(name='status', description='Настройки и статус автобэкапа')
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_status(self, interaction: discord.Interaction):
        e = discord.Embed(title='💾 Статус резервного копирования', color=GOLD,
                          timestamp=datetime.now(timezone.utc))
        if backup_enabled():
            last = (self._last_run_date.isoformat()
                    if self._last_run_date else 'ещё не было')
            ok = {None: '—', True: '✅ успешно', False: '⚠️ ошибка (см. консоль)'}[
                self._last_run_ok]
            e.description = (f'Автобэкап: **включён**, ежедневно в **{backup_hour():02d}:00**\n'
                             f'Последний запуск: **{last}** · итог: {ok}')
        else:
            e.description = 'Автобэкап: **выключен** (BACKUP_ENABLED=0)'
        e.add_field(name='Хранилище', value=f'`{backup_dir()}/`', inline=True)
        e.add_field(name='Храним копий', value=str(backup_keep()), inline=True)
        e.add_field(name='Файл в лог-канал',
                    value='вкл' if backup_attach() else 'выкл (BACKUP_ATTACH)', inline=True)
        e.add_field(name='Панель',
                    value='Скачать/создать/удалить: веб-панель → раздел «Бэкапы»',
                    inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Backup(bot))
