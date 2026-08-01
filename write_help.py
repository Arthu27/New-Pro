code = r'''import discord
from discord import app_commands
from discord.ext import commands

PERM_ICON = {"all": "\U0001f7e2", "мод": "\U0001f7e1", "админ": "\U0001f534", "owner": "\u2699\ufe0f"}
PERM_LABEL = {"all": "Каждый", "мод": "Модerator", "админ": "Иsminin", "owner": "Owner"}

CATEGORIES = [
 {"id": "overview", "эмодзи": "\u26a1", "title": "ANA MENU", "color": 0x00FFF7, "commands": []},
 {"id": "мод", "эмодзи": "\U0001f6e1\ufe0f", "title": "MODERASYON", "color": 0xFF0055, "commands": [
 ("!бан", "Постоянный бан", "!бан @user причина", "админ"),
 ("!кик", "С сервера at", "!кик @user причина", "админ"),
 ("!timeout", "Gecici sustur", "!timeout @user 10m", "админ"),
 ("!clear", "Массовая message удалить", "!clear 50", "мод"),
 ("!lock", "Канал заблокировать", "!lock #channel", "мод"),
 ("!unlock", "Замок ac", "!unlock #channel", "мод"),
 ]},
 {"id": "варн", "эмодзи": "\u26a0\ufe0f", "title": "ПРЕДУПРЕЖДЕНИЕ СИСТЕМА", "color": 0xFFD700, "commands": [
 ("!варн", "Предупреждение ver", "!варн @user причина", "мод"),
 ("!варнings", "Предупреждения listele", "!варнings @user", "мод"),
 ("!clearварнs", "Предупреждения clear", "!clearварнs @user", "админ"),
 ]},
 {"id": "music", "эмодзи": "\U0001f3b5", "title": "MUZIK", "color": 0xBF00FF, "commands": [
 ("!cal", "Muzik cal", "!cal lofi", "all"),
 ("!dur", "Duraklat/devam", "!dur", "all"),
 ("!atla", "Sarkхорошо atla", "!atla", "all"),
 ("!kuyruk", "Kuyrugu goster", "!kuyruk", "all"),
 ("!stop", "Остановить музыку", "!stop", "all"),
 ]},
 {"id": "fun", "эмодзи": "\U0001f3ae", "title": "EGLENCE", "color": 0xFF00CC, "commands": [
 ("!текст", "Текст орёл at", "!текст", "all"),
 ("!кубик", "Бросить кубик", "!кубик 6", "all"),
 ("!число-tahmin", "Число tahmin играu", "!число-tahmin", "all"),
 ("!slot", "Slot makinesi", "!slot", "all"),
 ]},
 {"id": "economy", "эмодзи": "\U0001f4b0", "title": "EKONOMI", "color": 0x00FF88, "commands": [
 ("!bakiye", "Bakiyeni gor", "!bakiye", "all"),
 ("!gunluk", "Gunluk odul al", "!gunluk", "all"),
 ("!transfer", "Деньги gonder", "!transfer @user 1000", "all"),
 ("!liderlik", "Zenginler список","!liderlik", "all"),
 ]},
 {"id": "utility", "эмодзи": "\U0001f527", "title": "ARACLAR", "color": 0x00BFFF, "commands": [
 ("!сервер", "Сервер infosi", "!сервер", "all"),
 ("!пользователь", "Пользователь profili", "!пользователь @kisi", "all"),
 ("!avatar", "Avatar goster", "!avatar @kisi", "all"),
 ("!ping", "Bot gecikmesi", "!ping", "all"),
 ]},
]

TOTAL_PAGES = len(CATEGORIES)
TOTAL_CMDS = sum(len(c["commands"]) for c in CATEGORIES)
CAT_SUMMARY = [c for c in CATEGORIES if c["id"] != "overview"]

def _a(text, *codes):
 return "\033[" + ";".join(str(x) for x in codes) + "m" + text + "\033[0m"

def build_embed(page: int) -> discord.Embed:
 cat = CATEGORIES[page]

 if cat["id"] == "overview":
 heимяer = "\n".join([
 _a("\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557", 1, 36),
 _a("\u2551 \u2551", 36),
 _a("\u2551 \u26a1 R A K U Z A N B O T \u26a1 \u2551", 1, 36),
 _a("\u2551 КОМАНДА КОНТРОЛЬ MERKEZI \u2551", 1, 37),
 _a("\u2551 \u2551", 36),
 _a("\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d", 1, 36),
 ])
 stats = "\n".join([
 _a(" \u25c8 Всего Команда : ", 1, 36) + _a(str(TOTAL_CMDS), 1, 33),
 _a(" \u25c8 Kategori Количество : ", 1, 36) + _a(str(len(CAT_SUMMARY)), 1, 33),
 _a(" \u25c8 Prefix : ", 1, 36) + _a("!", 1, 32),
 _a(" \u25c8 Состояние : ", 1, 36) + _a("\u25cf АКТИВЕН", 1, 32),
 ])
 cats = ""
 for c in CAT_SUMMARY:
 n = len(c["commands"])
 bar = _a("\u25b0" * min(n, 8), 36) + _a("\u25b1" * (8 - min(n, 8)), 2, 36)
 cats += "\n" + _a(f" {c['эмодзи']} {c['title']:<18}", 1, 37) + _a(f"{n} команда ", 33) + bar
 perms = "\n".join([
 _a(" \U0001f7e2 Каждый ", 1, 32) + _a("\u2500 Tum uyeler использовать", 2, 37),
 _a(" \U0001f7e1 Модerator ", 1, 33) + _a("\u2500 Требуется роль модератора", 2, 37),
 _a(" \U0001f534 Иsminin ", 1, 31) + _a("\u2500 Требуется роль администратора", 2, 37),
 _a(" \u2699\ufe0f Owner ", 1, 37) + _a("\u2500 Только сервер sahibi", 2, 37),
 ])
 embed = discord.Embed(
 description="```ansi\n" + heимяer + "\n```" +
 "```ansi\n" + stats + "\n```",
 color=cat["color"]
 )
 embed.имяd_field(name="\U0001f4cb Kategoriler", value="```ansi\n" + cats.strip() + "\n```", inline=False)
 embed.имяd_field(name="\U0001f510 Izin Уровеньleri", value="```ansi\n" + perms + "\n```", inline=False)
 embed.set_footer(text=f"Sayfa 1/{TOTAL_PAGES} \u2022 Aether Bot \u2022 !помощь")
 return embed

 cmds = cat["commands"]
 title_block = "\n".join([
 _a("\u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510", 1, 36),
 _a(f"\u2502 {cat['эмодзи']} {cat['title']:<40}\u2502", 1, 37),
 _a("\u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518", 1, 36),
 ])
 cmd_lines = []
 for name, desc, usage, perm in cmds:
 cmd_lines.append(_a(f" {PERM_ICON[perm]} ", 1) + _a(f"{name:<16}", 1, 36) + _a(desc, 37))
 cmd_lines.append(_a(" \u2514\u2500 ", 2, 36) + _a(usage, 2, 33))
 cmd_lines.append("")
 perm_counts = {}
 for _, _, _, p in cmds:
 perm_counts[p] = perm_counts.get(p, 0) + 1
 summary = " ".join(
 _a(f" {PERM_ICON[k]} {PERM_LABEL[k]}: ", 1, 37) + _a(str(perm_counts[k]), 1, 33)
 for k in ("all", "мод", "админ", "owner") if k in perm_counts
 )
 page_idx = CATEGORIES.index(cat)
 embed = discord.Embed(
 description="```ansi\n" + title_block + "\n```" +
 "```ansi\n" + "\n".join(cmd_lines).rstrip() + "\n```",
 color=cat["color"]
 )
 embed.имяd_field(name="\U0001f4ca Команда Dagilimi", value="```ansi\n" + summary + "\n```", inline=False)
 embed.set_footer(text=f"Sayfa {page_idx+1}/{TOTAL_PAGES} \u2022 Aether Bot \u2022 !помощь")
 return embed


class CategorySelect(discord.ui.Select):
 def __init__(self, current_page: int):
 options = [
 discord.SelectOption(
 label=f"{c['эмодзи']} {c['title']}",
 value=str(i),
 description=f"{len(c['commands'])} команда" if c["commands"] else "Ana sayfa",
 default=(i == current_page),
 )
 for i, c in enumerate(CATEGORIES)
 ]
 super().__init__(placeholder="\u26a1 Kategori sec...", options=options, custom_id="help_select")

 async def callback(self, interaction: discord.Interaction):
 page = int(self.values[0])
 view = HelpView(page=page)
 await interaction.response.edit_message(embed=build_embed(page), view=view)


class HelpView(discord.ui.View):
 def __init__(self, page: int = 0):
 super().__init__(timeout=300)
 self.page = page
 self.имяd_item(CategorySelect(page))
 self._sync()

 def _sync(self):
 self.prev_btn.disabled = (self.page == 0)
 self.next_btn.disabled = (self.page == TOTAL_PAGES - 1)
 self.first_btn.disabled = (self.page == 0)
 self.last_btn.disabled = (self.page == TOTAL_PAGES - 1)
 self.page_label.label = f" {self.page+1} / {TOTAL_PAGES} "

 @discord.ui.button(label="\u23ee", style=discord.ButtonStyle.blurple, row=1, custom_id="help_first")
 async def first_btn(self, interaction, button):
 self.page = 0; self._sync()
 await interaction.response.edit_message(embed=build_embed(self.page), view=self)

 @discord.ui.button(label="\u25c4", style=discord.ButtonStyle.grey, row=1, custom_id="help_prev")
 async def prev_btn(self, interaction, button):
 self.page = max(0, self.page - 1); self._sync()
 await interaction.response.edit_message(embed=build_embed(self.page), view=self)

 @discord.ui.button(label=" 1 / 7 ", style=discord.ButtonStyle.green, disabled=True, row=1, custom_id="help_page")
 async def page_label(self, interaction, button):
 pass

 @discord.ui.button(label="\u25ba", style=discord.ButtonStyle.grey, row=1, custom_id="help_next")
 async def next_btn(self, interaction, button):
 self.page = min(TOTAL_PAGES - 1, self.page + 1); self._sync()
 await interaction.response.edit_message(embed=build_embed(self.page), view=self)

 @discord.ui.button(label="\u23ed", style=discord.ButtonStyle.blurple, row=1, custom_id="help_last")
 async def last_btn(self, interaction, button):
 self.page = TOTAL_PAGES - 1; self._sync()
 await interaction.response.edit_message(embed=build_embed(self.page), view=self)

 @discord.ui.button(label="\u2716 Закрыть", style=discord.ButtonStyle.red, row=2, custom_id="help_close")
 async def close_btn(self, interaction, button):
 await interaction.response.defer()
 await interaction.delete_original_response()


class Help(commands.Cog):
 def __init__(self, bot):
 self.bot = bot

 @commands.command(name="помощь", aliases=["help", "команды", "h", "menu"])
 async def yardim_prefix(self, ctx):
 try:
 await ctx.message.delete()
 except Exception:
 pass
 await ctx.send(embed=build_embed(0), view=HelpView(page=0))

 @app_commands.command(name="помощь", description="Tum bot команды gosterir")
 async def yardim_slash(self, interaction: discord.Interaction):
 await interaction.response.send_message(embed=build_embed(0), view=HelpView(page=0), ephemeral=True)


async def setup(bot):
 await bot.имяd_cog(Help(bot))
'''
import ast
ast.parse(code)  # syntax check

with open('cogs/help.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write(code)

print(f"OK - {len(code)} karakter написано")
