"""
Ticket Cog
Полноценная система тикетов с интеграцией в базу данных
Тёмная тема, без эмодзи, на русском языке
"""

MENU_GIF = "https://media.tenor.com/x8v1oNUOmg4AAAAC/rain-dark.gif"


import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import os
import io
import json
import asyncio
from PIL import Image, ImageDraw, ImageFont
from cogs._menu_bg import load_menu_bg

from config import Config
from logger import get_logger

log = get_logger("ticket")

ROOT = os.path.join(os.path.dirname(__file__), '..')
FONTS = os.path.join(ROOT, 'assets', 'fonts')
BG_PATH = os.path.join(ROOT, 'assets', 'profile_bg_pro.jpg')
FONT_B = os.path.join(FONTS, 'Bold.ttf')
FONT_R = os.path.join(FONTS, 'Regular.ttf')

WHITE = (255, 255, 255)
BLACK = (20, 20, 25)
TEAL = (13, 148, 136)
MUTED = (110, 115, 125)
SS = 4

def _f(bold=False, sz=20):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT_R, sz)
    except Exception:
        return ImageFont.load_default()

def _ss_render(w, h, draw_fn, scale=SS):
    big = Image.new('RGBA', (w * scale, h * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    draw_fn(d, scale)
    return big.resize((w, h), Image.Resampling.LANCZOS)

def _load_bg(w, h):
    try:
        bg = Image.open(BG_PATH).convert('RGBA')
        bw, bh = bg.size
        target_ratio = w / h
        src_ratio = bw / bh
        if src_ratio > target_ratio:
            new_w = int(bh * target_ratio)
            x0 = (bw - new_w) // 2
            bg = bg.crop((x0, 0, x0 + new_w, bh))
        else:
            new_h = int(bw / target_ratio)
            y0 = (bh - new_h) // 2
            bg = bg.crop((0, y0, bw, y0 + new_h))
        return bg.resize((w, h), Image.Resampling.LANCZOS)
    except Exception:
        return Image.new('RGBA', (w, h), (255, 255, 255, 255))

def _icon_ticket(d, cx, cy, s, w, color):
    w_t, h_t = s*0.44, s*0.30
    x0, y0 = cx - w_t, cy - h_t
    x1, y1 = cx + w_t, cy + h_t
    d.rounded_rectangle((x0, y0, x1, y1), radius=h_t*0.25, outline=color, width=w)
    r = s*0.1
    d.arc((x0 - r, cy - r, x0 + r, cy + r), -90, 90, fill=WHITE, width=w*2)
    d.arc((x0 - r, cy - r, x0 + r, cy + r), -90, 90, fill=color, width=w)
    d.arc((x1 - r, cy - r, x1 + r, cy + r), 90, 270, fill=WHITE, width=w*2)
    d.arc((x1 - r, cy - r, x1 + r, cy + r), 90, 270, fill=color, width=w)

def _icon_badge(diameter, glyph_fn, ring_color=BLACK, ring_w=None, icon_color=TEAL):
    ring_w = ring_w if ring_w is not None else max(2, diameter // 22)
    def draw(d, scale):
        size = diameter * scale
        rw = ring_w * scale
        r = size * 0.22
        d.rounded_rectangle((rw / 2, rw / 2, size - rw / 2 - 1, size - rw / 2 - 1),
                             radius=r, fill=WHITE, outline=ring_color, width=rw)
        glyph_fn(d, size / 2, size / 2, size * 0.60, max(2, int(size * 0.032)), icon_color)
    return _ss_render(diameter, diameter, draw)

def _corner_bracket(size, thickness, length_ratio=0.35, color=TEAL):
    def draw(d, scale):
        t = thickness * scale
        L = size * scale * length_ratio
        d.line([(0, t / 2), (L, t / 2)], fill=color, width=t)
        d.line([(t / 2, 0), (t / 2, L)], fill=color, width=t)
    return _ss_render(size, size, draw)

def _rounded_panel(w, h, radius, fill=WHITE, outline=BLACK, ow=3):
    def draw(d, scale):
        r = radius * scale
        o = ow * scale
        d.rounded_rectangle((o / 2, o / 2, w * scale - o / 2 - 1, h * scale - o / 2 - 1),
                             radius=r, fill=fill, outline=outline, width=o)
    return _ss_render(w, h, draw)

def generate_ticket_panel_card() -> Image.Image:
    W, H = 920, 520
    bg = load_menu_bg(W, H, "teal")
    d = ImageDraw.Draw(bg)

    # Header
    header_box = _rounded_panel(872, 72, radius=14, fill=WHITE, outline=BLACK, ow=2)
    bg.alpha_composite(header_box, (24, 20))

    badge = _icon_badge(52, _icon_ticket, ring_color=BLACK, ring_w=2, icon_color=TEAL)
    bg.alpha_composite(badge, (36, 30))

    d.text((100, 26), "СЛУЖБА ПОДДЕРЖКИ СЕРВЕРА", fill=BLACK, font=_f(True, 24))
    d.text((100, 56), "ВЫБЕРИТЕ КАТЕГОРИЮ ОБРАЩЕНИЯ В МЕНЮ НИЖЕ", fill=MUTED, font=_f(False, 15))

    pill = _rounded_panel(160, 36, radius=10, fill=WHITE, outline=TEAL, ow=2)
    bg.alpha_composite(pill, (720, 38))
    d.text((738, 46), "SUPPORT v4.0", fill=TEAL, font=_f(True, 14))

    # 4 Category cards
    items = [
        ("ОБЩИЕ ВОПРОСЫ", "Консультации и помощь", "Ответ до 24ч"),
        ("ТЕХ. ПОДДЕРЖКА", "Проблемы с ботом/сервером", "Высокий приоритет"),
        ("ЖАЛОБЫ", "Нарушения правил", "Конфиденциально"),
        ("ЗАЯВКИ В СТАФФ", "Набор модераторов", "Отбор кандидатов")
    ]
    box_w, box_h = 426, 110
    gap_x, gap_y = 20, 14
    start_x, start_y = 24, 106

    for idx, (title, sub, note) in enumerate(items):
        c = idx % 2
        r = idx // 2
        bx = start_x + c * (box_w + gap_x)
        by = start_y + r * (box_h + gap_y)

        box = _rounded_panel(box_w, box_h, radius=14, fill=WHITE, outline=BLACK, ow=2)
        bg.alpha_composite(box, (bx, by))

        ibadge = _icon_badge(64, _icon_ticket, ring_color=BLACK, ring_w=2, icon_color=TEAL)
        bg.alpha_composite(ibadge, (bx + 16, by + 23))

        d.text((bx + 94, by + 18), title, fill=BLACK, font=_f(True, 23))
        d.text((bx + 94, by + 50), sub, fill=TEAL, font=_f(True, 17))
        d.text((bx + 94, by + 78), note, fill=MUTED, font=_f(False, 15))

    br = _corner_bracket(40, 4, color=TEAL)
    bg.alpha_composite(br, (6, 6))
    bg.alpha_composite(br.rotate(270), (W - 46, 6))
    bg.alpha_composite(br.rotate(90), (6, H - 46))
    bg.alpha_composite(br.rotate(180), (W - 46, H - 46))

    return bg

def generate_ticket_panel_bytes() -> io.BytesIO:
    card = generate_ticket_panel_card().convert('RGB')
    buf = io.BytesIO()
    card.save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf


class TicketDB:
    """Работа с базой данных для тикетов"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DB_PATH
        self._ensure_tables()
    
    def _conn(self):
        import sqlite3
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_tables(self):
        conn = self._conn()
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT UNIQUE NOT NULL,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                subject TEXT,
                category TEXT DEFAULT 'general',
                priority TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'open',
                assigned_to INTEGER,
                channel_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                closed_at TEXT,
                closed_by INTEGER
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS ticket_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                content TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    def create_ticket(self, ticket_id: str, guild_id: int, user_id: int, user_name: str, subject: str, priority: str = 'medium', category: str = 'general', channel_id: int = None):
        conn = self._conn()
        try:
            conn.execute(
                'INSERT INTO tickets (ticket_id, guild_id, user_id, user_name, subject, priority, category, channel_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (ticket_id, guild_id, user_id, user_name, subject, priority, category, channel_id)
            )
            conn.commit()
            return True
        except Exception as e:
            log.error(f"Ошибка создания тикета: {e}")
            return False
        finally:
            conn.close()
    
    def close_ticket(self, ticket_id: str, closed_by: int):
        conn = self._conn()
        conn.execute(
            'UPDATE tickets SET status = ?, closed_at = ?, closed_by = ? WHERE ticket_id = ?',
            ('closed', datetime.now().isoformat(), closed_by, ticket_id)
        )
        conn.commit()
        conn.close()
    
    def update_priority(self, ticket_id: str, priority: str):
        conn = self._conn()
        conn.execute('UPDATE tickets SET priority = ? WHERE ticket_id = ?', (priority, ticket_id))
        conn.commit()
        conn.close()
    
    def assign_ticket(self, ticket_id: str, assigned_to: int):
        conn = self._conn()
        conn.execute(
            'UPDATE tickets SET assigned_to = ? WHERE ticket_id = ?',
            (assigned_to, ticket_id)
        )
        conn.commit()
        conn.close()
    
    def get_ticket(self, ticket_id: str) -> dict | None:
        conn = self._conn()
        row = conn.execute('SELECT * FROM tickets WHERE ticket_id = ?', (ticket_id,)).fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_user_tickets(self, user_id: int, status: str = None) -> list:
        conn = self._conn()
        if status and status != 'all':
            rows = conn.execute(
                'SELECT * FROM tickets WHERE user_id = ? AND status = ? ORDER BY created_at DESC',
                (user_id, status)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM tickets WHERE user_id = ? ORDER BY created_at DESC',
                (user_id,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    
    def get_guild_tickets(self, guild_id: int, status: str = None) -> list:
        conn = self._conn()
        if status and status != 'all':
            rows = conn.execute(
                'SELECT * FROM tickets WHERE guild_id = ? AND status = ? ORDER BY created_at DESC',
                (guild_id, status)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM tickets WHERE guild_id = ? ORDER BY created_at DESC',
                (guild_id,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    
    def count_user_open(self, user_id: int, guild_id: int) -> int:
        conn = self._conn()
        row = conn.execute(
            'SELECT COUNT(*) as cnt FROM tickets WHERE user_id = ? AND guild_id = ? AND status = ?',
            (user_id, guild_id, 'open')
        ).fetchone()
        conn.close()
        return row['cnt'] if row else 0
    
    def get_next_id(self, guild_id: int) -> int:
        conn = self._conn()
        row = conn.execute(
            'SELECT COUNT(*) as cnt FROM tickets WHERE guild_id = ?',
            (guild_id,)
        ).fetchone()
        conn.close()
        return (row['cnt'] if row else 0) + 1
    
    def add_message(self, ticket_id: str, user_id: int, user_name: str, content: str):
        conn = self._conn()
        conn.execute(
            'INSERT INTO ticket_messages (ticket_id, user_id, user_name, content) VALUES (?, ?, ?, ?)',
            (ticket_id, user_id, user_name, content)
        )
        conn.commit()
        conn.close()
    
    def get_messages(self, ticket_id: str) -> list:
        conn = self._conn()
        rows = conn.execute(
            'SELECT * FROM ticket_messages WHERE ticket_id = ? ORDER BY created_at ASC',
            (ticket_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


class TicketView(discord.ui.View):
    """Select menu для создания тикета"""
    
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
    
    @discord.ui.select(
        placeholder="Выберите категорию обращения",
        custom_id="ticket_category_select",
        options=[
            discord.SelectOption(label="Общий вопрос", value="general", description="Общие вопросы и консультации"),
            discord.SelectOption(label="Техническая поддержка", value="technical", description="Проблемы с ботом или сервером"),
            discord.SelectOption(label="Жалоба", value="complaint", description="Жалоба на участника или нарушение"),
            discord.SelectOption(label="Предложение", value="suggestion", description="Предложения по улучшению сервера"),
            discord.SelectOption(label="Заявка в команду", value="staff_apply", description="Заявка на роль модератора/хелпера"),
        ]
    )
    async def category_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        category = select.values[0]
        
        # Проверяем лимит открытых тикетов
        open_count = self.cog.db.count_user_open(interaction.user.id, interaction.guild.id)
        if open_count >= Config.TICKET_MAX_OPEN:
            embed = discord.Embed(
                title="Лимит тикетов",
                description=f"У вас уже {open_count} открытых тикетов. Закройте их перед созданием нового.",
                color=discord.Color.dark_grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Номер тикета
        num = self.cog.db.get_next_id(interaction.guild.id)
        ticket_id = f"TK-{num:04d}"
        
        # Создаём канал
        category_name = {
            "general": "Общий вопрос",
            "technical": "Техподдержка",
            "complaint": "Жалоба",
            "suggestion": "Предложение",
            "staff_apply": "Заявка в команду"
        }.get(category, category)
        
        channel = None
        try:
            # Категория для тикетов
            cat = None
            if Config.TICKET_CATEGORY_ID:
                cat = interaction.guild.get_channel(Config.TICKET_CATEGORY_ID)
            
            # Права доступа
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, attach_files=True
                ),
                interaction.guild.me: discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, manage_channels=True
                ),
            }
            # Роль поддержки
            if Config.TICKET_SUPPORT_ROLE_ID:
                support_role = interaction.guild.get_role(Config.TICKET_SUPPORT_ROLE_ID)
                if support_role:
                    overwrites[support_role] = discord.PermissionOverwrite(
                        read_messages=True, send_messages=True
                    )
            
            channel = await interaction.guild.create_text_channel(
                name=f"ticket-{num:04d}",
                overwrites=overwrites,
                category=cat,
                topic=f"Тикет {ticket_id} | {interaction.user.display_name} | {category_name}"
            )
        except Exception as e:
            log.error(f"Ошибка создания канала: {e}")
            embed = discord.Embed(
                title="Ошибка",
                description="Не удалось создать канал для тикета. Обратитесь к администрации.",
                color=discord.Color.dark_grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Сохраняем в БД
        self.cog.db.create_ticket(
            ticket_id=ticket_id,
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            subject=category_name,
            priority="medium",
            category=category,
            channel_id=channel.id
        )
        
        # Сообщение в канале тикета
        embed = discord.Embed(
            title=f"Тикет {ticket_id}",
            description=f"Категория: {category_name}\nАвтор: {interaction.user.mention}\n\nОпишите вашу проблему. Сотрудник команды скоро ответит.",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Статус", value="Открыт", inline=True)
        embed.add_field(name="Приоритет", value="Средний", inline=True)
        
        # Кнопки управления
        view = TicketControlView(self.cog, ticket_id)
        msg = await channel.send(embed=embed, view=view)
        await msg.pin()
        
        # Ответ пользователю
        resp_embed = discord.Embed(
            title="Тикет создан",
            description=f"Ваш тикет: {channel.mention}",
            color=discord.Color.dark_grey()
        )
        await interaction.response.send_message(embed=resp_embed, ephemeral=True)
        
        log.info(f"Тикет {ticket_id} создан: {interaction.user} ({category})")


class TicketControlView(discord.ui.View):
    """Кнопки управления тикетом внутри канала"""
    
    def __init__(self, cog, ticket_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.ticket_id = ticket_id
    
    @discord.ui.button(label="Закрыть", style=discord.ButtonStyle.danger, custom_id="ticket_close_btn")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = self.cog.db.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message("Тикет не найден.", ephemeral=True)
            return
        
        # Только автор или модератор
        is_author = ticket['user_id'] == interaction.user.id
        is_mod = interaction.user.guild_permissions.manage_messages
        if not is_author and not is_mod:
            embed = discord.Embed(
                title="Нет доступа",
                description="Только автор тикета или модератор может закрыть его.",
                color=discord.Color.dark_grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Закрываем
        self.cog.db.close_ticket(self.ticket_id, interaction.user.id)
        
        embed = discord.Embed(
            title=f"Тикет {self.ticket_id} закрыт",
            description=f"Закрыл: {interaction.user.mention}\nДата: {discord.utils.format_dt(datetime.now(), 'F')}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        await interaction.response.send_message(embed=embed)
        
        # Удаляем канал через 5 секунд
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Тикет {self.ticket_id} закрыт")
        except Exception as e:
            log.error(f"Ошибка удаления канала: {e}")
        
        log.info(f"Тикет {self.ticket_id} закрыт: {interaction.user}")
    
    @discord.ui.button(label="Повысить приоритет", style=discord.ButtonStyle.secondary, custom_id="ticket_priority_btn")
    async def priority_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            embed = discord.Embed(
                title="Нет доступа",
                description="Только модератор может изменить приоритет.",
                color=discord.Color.dark_grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        ticket = self.cog.db.get_ticket(self.ticket_id)
        priorities = ['low', 'medium', 'high', 'urgent']
        current_idx = priorities.index(ticket['priority']) if ticket['priority'] in priorities else 1
        new_priority = priorities[min(current_idx + 1, len(priorities) - 1)]
        
        self.cog.db.update_priority(self.ticket_id, new_priority)
        
        priority_names = {'low': 'Низкий', 'medium': 'Средний', 'high': 'Высокий', 'urgent': 'Срочный'}
        embed = discord.Embed(
            title="Приоритет изменён",
            description=f"Новый приоритет: {priority_names.get(new_priority, new_priority)}",
            color=discord.Color.dark_grey()
        )
        await interaction.response.send_message(embed=embed)


class TicketCog(commands.Cog):
    """Полноценная система тикетов"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = TicketDB()
    
    @app_commands.command(name='ticket-panel', description='Создать панель для тикетов (только для администрации)')
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_panel(self, interaction: discord.Interaction):
        """Создать профессиональную карточку-панель для создания тикетов"""
        img_buf = await interaction.client.loop.run_in_executor(
            None, generate_ticket_panel_bytes
        )
        file = discord.File(img_buf, filename="ticket_panel.png")
        view = TicketView(self)
        await interaction.response.send_message(file=file, view=view)
        log.info(f"Ticket panel создана в {interaction.channel}")
    
    @app_commands.command(name='tickets', description='Список ваших тикетов')
    @app_commands.describe(status='Фильтр по статусу')
    @app_commands.choices(status=[
        app_commands.Choice(name='Открытые', value='open'),
        app_commands.Choice(name='Закрытые', value='closed'),
        app_commands.Choice(name='Все', value='all'),
    ])
    async def ticket_list(self, interaction: discord.Interaction, status: app_commands.Choice[str] = None):
        """Список тикетов пользователя"""
        status_val = status.value if status else 'open'
        tickets = self.db.get_user_tickets(interaction.user.id, status_val)
        
        if not tickets:
            embed = discord.Embed(
                title="Тикеты",
                description="У вас нет тикетов по данному фильтру.",
                color=discord.Color.dark_grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"Ваши тикеты ({status_val})",
            description=f"Найдено: {len(tickets)}",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        
        status_names = {'open': 'Открыт', 'closed': 'Закрыт'}
        priority_names = {'low': 'Низкий', 'medium': 'Средний', 'high': 'Высокий', 'urgent': 'Срочный'}
        
        for t in tickets[:10]:
            st = status_names.get(t['status'], t['status'])
            pr = priority_names.get(t['priority'], t['priority'])
            embed.add_field(
                name=f"{t['ticket_id']} — {t['subject']}",
                value=f"Статус: {st} | Приоритет: {pr} | {t['created_at'][:10]}",
                inline=False
            )
        
        if len(tickets) > 10:
            embed.set_footer(text=f"Показано 10 из {len(tickets)}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name='ticket-info', description='Информация о тикете')
    async def ticket_info(self, interaction: discord.Interaction, ticket_id: str):
        """Детальная информация о тикете"""
        ticket = self.db.get_ticket(ticket_id)
        if not ticket:
            embed = discord.Embed(
                title="Тикет не найден",
                description=f"Тикет с ID `{ticket_id}` не существует.",
                color=discord.Color.dark_grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        status_names = {'open': 'Открыт', 'closed': 'Закрыт'}
        priority_names = {'low': 'Низкий', 'medium': 'Средний', 'high': 'Высокий', 'urgent': 'Срочный'}
        
        embed = discord.Embed(
            title=f"Тикет {ticket_id}",
            description=ticket['subject'] or "Без описания",
            color=discord.Color.dark_grey(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Статус", value=status_names.get(ticket['status'], ticket['status']), inline=True)
        embed.add_field(name="Приоритет", value=priority_names.get(ticket['priority'], ticket['priority']), inline=True)
        embed.add_field(name="Автор", value=f"<@{ticket['user_id']}>", inline=True)
        
        if ticket.get('assigned_to'):
            embed.add_field(name="Назначен", value=f"<@{ticket['assigned_to']}>", inline=True)
        
        embed.add_field(name="Создан", value=ticket['created_at'][:16], inline=True)
        
        if ticket.get('closed_at'):
            embed.add_field(name="Закрыт", value=ticket['closed_at'][:16], inline=True)
        
        # Количество сообщений
        messages = self.db.get_messages(ticket_id)
        embed.add_field(name="Сообщений", value=str(len(messages)), inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name='ticket-close', description='Закрыть тикет')
    async def ticket_close(self, interaction: discord.Interaction, ticket_id: str):
        """Закрыть тикет по ID"""
        ticket = self.db.get_ticket(ticket_id)
        if not ticket:
            embed = discord.Embed(
                title="Тикет не найден",
                description=f"Тикет с ID `{ticket_id}` не существует.",
                color=discord.Color.dark_grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if ticket['status'] == 'closed':
            embed = discord.Embed(
                title="Тикет уже закрыт",
                description=f"Тикет `{ticket_id}` уже закрыт.",
                color=discord.Color.dark_grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Проверка прав
        is_author = ticket['user_id'] == interaction.user.id
        is_mod = interaction.user.guild_permissions.manage_messages
        if not is_author and not is_mod:
            embed = discord.Embed(
                title="Нет доступа",
                description="Только автор или модератор может закрыть тикет.",
                color=discord.Color.dark_grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        self.db.close_ticket(ticket_id, interaction.user.id)
        
        embed = discord.Embed(
            title="Тикет закрыт",
            description=f"Тикет `{ticket_id}` успешно закрыт.",
            color=discord.Color.dark_grey()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        log.info(f"Тикет {ticket_id} закрыт через команду: {interaction.user}")
    
    @app_commands.command(name='ticket-assign', description='Назначить тикет на сотрудника')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def ticket_assign(self, interaction: discord.Interaction, ticket_id: str, member: discord.Member):
        """Назначить тикет"""
        ticket = self.db.get_ticket(ticket_id)
        if not ticket:
            embed = discord.Embed(
                title="Тикет не найден",
                color=discord.Color.dark_grey()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        self.db.assign_ticket(ticket_id, member.id)
        
        embed = discord.Embed(
            title="Тикет назначен",
            description=f"Тикет `{ticket_id}` назначен на {member.mention}",
            color=discord.Color.dark_grey()
        )
        await interaction.response.send_message(embed=embed)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Записывать сообщения в тикетах в базу"""
        if message.author.bot:
            return
        if not message.guild:
            return
        
        # Проверяем, является ли канал тикетом
        if not message.channel.name.startswith("ticket-"):
            return
        
        # Ищем ticket_id в topic канала
        if message.channel.topic:
            for part in message.channel.topic.split("|"):
                part = part.strip()
                if part.startswith("TK-"):
                    self.db.add_message(
                        ticket_id=part,
                        user_id=message.author.id,
                        user_name=message.author.display_name,
                        content=message.content[:2000] if message.content else "[медиа]"
                    )
                    break


async def setup(bot):
    cog = TicketCog(bot)
    await bot.add_cog(cog)
    # Регистрируем persistent views
    bot.add_view(TicketView(cog))
    log.info("TicketCog загружен")
