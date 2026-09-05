# -*- coding: utf-8 -*-
"""E2E: улучшенные логи (бан/разбан/кик с модератором и причиной, детальные
эмбеды сообщений/каналов/ролей/инвайтов/таймаута) + Центр логов (select-меню).

Запуск: python3 tests/test_logs_center.py
"""
import asyncio, datetime, os, sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs('data', exist_ok=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord
from cogs.logs import (Logs, LogsCenterView, LOG_CENTER_ITEMS,
                       _lc_find_channel, _styled_log_embed)

PASS = 0; FAIL = 0
def check(ok, msg):
    global PASS, FAIL
    if ok: PASS += 1; print(f'  PASS: {msg}')
    else: FAIL += 1; print(f'  FAIL: {msg}')

NOW = datetime.datetime.now(datetime.timezone.utc)

# ─── фейки ────────────────────────────────────────────────────────────
class FakeAvatar:
    url = 'http://x/av.png'
class FakePerms:
    administrator = False
    view_audit_log = True
    manage_guild = False
    manage_channels = False
    manage_roles = False
    kick_members = False
    ban_members = False
    moderate_members = False
class FakeChannel:
    def __init__(self, cid, name, ctype='text'):
        self.id = cid; self.name = name; self.type = type('T', (), {'name': ctype})()
        self.mention = f'<#{cid}>'; self.topic = None; self.category = None
        self.members = []; self.sent = []
    async def send(self, content=None, embed=None, **kw):
        self.sent.append(embed or content); return object()
class FakeRole:
    def __init__(self, rid, name, perms=None, color=0x9B59B6):
        self.id = rid; self.name = name; self.mention = f'<@&{rid}>'
        self.hoist = True; self.mentionable = False; self.members = []
        self.color = type('C', (), {'value': color})()
        p = FakePerms()
        for k in (perms or []): setattr(p, k, True)
        self.permissions = p
class FakeUser:
    def __init__(self, uid, name, bot=False):
        self.id = uid; self.display_name = name; self.name = name
        self.mention = f'<@{uid}>'; self.bot = bot
        self.display_avatar = FakeAvatar()
    def __str__(self): return f'{self.display_name}#{self.id % 10000:04d}'
class FakeAuditEntry:
    _seq = 9000
    def __init__(self, target_id, user, reason):
        FakeAuditEntry._seq += 1
        self.id = FakeAuditEntry._seq
        self.target = type('T', (), {'id': target_id})()
        self.user = user; self.reason = reason
        self.created_at = NOW
class FakeGuild:
    def __init__(self):
        self.id = 555; self.name = 'TestGuild'; self.icon = None
        self.banner = None; self.member_count = 41
        self.channels = {}
        for i, n in enumerate(['-модерация', '-участники', '-сообщения', '-ses',
                               '-сервер', '-приветствие', 'ticket-log', 'ai-alerts', 'общий']):
            c = FakeChannel(100 + i, n)
            c.guild = self
            self.channels[100 + i] = c
        self.categories = []
        self.me = FakeUser(999, 'Hakumo', bot=True)
        self.me.guild_permissions = FakePerms()
        self.default_role = FakeRole(1, '@everyone')
        self.roles = [self.default_role]
        self.audit_entries = []
    @property
    def text_channels(self):
        return [c for c in self.channels.values() if not isinstance(getattr(c.type, 'name', ''), type(None)) and c.type.name == 'text']
    def get_channel(self, cid): return self.channels.get(cid)
    def audit_logs(self, limit=8, action=None, oldest_first=False, **kw):
        class _Iter:
            def __init__(self, items): self._it = iter(items)
            def __aiter__(self): return self
            async def __anext__(self):
                try: return next(self._it)
                except StopIteration: raise StopAsyncIteration
        return _Iter(list(self.audit_entries))
    async def create_text_channel(self, name, category=None, reason=None, topic=None):
        c = FakeChannel(900 + len(self.channels), name)
        c.category = category; c.topic = topic; c.guild = self
        self.channels[c.id] = c
        return c
    async def create_category(self, name, **kw):
        c = FakeChannel(900 + len(self.channels), name, 'category')
        c.guild = self
        self.categories.append(c); return c
class FakeMember(FakeUser):
    def __init__(self, uid, name, guild):
        super().__init__(uid, name)
        self.guild = guild; self.nick = None
        self.created_at = NOW - datetime.timedelta(days=400)
        self.joined_at = NOW - datetime.timedelta(days=30)
        self.roles = [guild.default_role]
        self.timed_out_until = None
class FakeMessage:
    def __init__(self, mid, content, author, channel, guild):
        self.id = mid; self.content = content; self.author = author
        self.channel = channel; self.guild = guild
        self.created_at = NOW - datetime.timedelta(minutes=5)
        self.attachments = []; self.mentions = []; self.role_mentions = []
        self.jump_url = f'http://x/{mid}'
class FakeResp:
    def __init__(self): self.edited = None; self.sent = None
    async def edit_message(self, embed=None, view=None): self.edited = (embed, view)
    async def send_message(self, content=None, embed=None, view=None, ephemeral=False):
        self.sent = (content, embed, view, ephemeral)
class FakeInter:
    def __init__(self, guild, user):
        self.guild = guild; self.user = user; self.response = FakeResp()

guild = FakeGuild()
cog = Logs(bot=None)
loop = asyncio.new_event_loop()
run = loop.run_until_complete

def last_embed(chname):
    ch = guild.text_channels and [c for c in guild.channels.values() if c.name == chname][0]
    return ch.sent[-1] if ch and ch.sent else None

def desc_of(e):
    """Текст лог-эмбеда для проверок.

    В канале Discord логи уходят как "только картинка" (_safe_send очищает
    description), но исходный текст сохраняется в e._hakumo_log_desc.
    Если карточка не отрендерилась (fallback) — возвращаем description как есть.
    """
    if not e:
        return ''
    return getattr(e, '_hakumo_log_desc', None) or e.description or ''

print('== бан / кик / разбан с модератором и причиной ==')
mod = FakeUser(50, 'TestMod')
victim = FakeUser(77, 'Spamer')
guild.audit_entries = [FakeAuditEntry(77, mod, 'Флуд и реклама')]
run(cog.on_member_ban(guild, victim))
e = last_embed('-модерация')
check(e and 'Пользователь заблокирован' in desc_of(e) and 'TestMod' in desc_of(e)
      and 'Флуд и реклама' in desc_of(e) and 'Причина' in desc_of(e),
      f'бан: модератор + причина в эмбеде')
check('Hakumo Log' in getattr(e, '_hakumo_log_footer', ''), 'футер «Hakumo Log · …» сохранён (в канале — только картинка)')
check(e.description is None and e.image and e.image.url == 'attachment://hakumo_log_card.jpg',
      'в канал уходит ТОЛЬКО карточка-картинка (description очищен)')

guild.audit_entries = [FakeAuditEntry(77, mod, None)]
run(cog.on_member_unban(guild, victim))
e = last_embed('-модерация')
check(e and 'Блокировка снята' in desc_of(e) and 'TestMod' in desc_of(e), 'разбан: эмбед с модератором')

mem = FakeMember(88, 'Kicked', guild)
guild.audit_entries = [FakeAuditEntry(88, mod, 'Нарушение правил')]
run(cog.on_member_remove(mem))
e_mod = last_embed('-модерация')
e_mem = last_embed('-участники')
check(e_mem and 'покинул сервер' in desc_of(e_mem), 'выход: эмбед в -участники')
check(e_mod and 'Участник кикнут' in desc_of(e_mod) and 'Нарушение правил' in desc_of(e_mod)
      and 'TestMod' in desc_of(e_mod), 'кик: отдельный эмбед в -модерация с причиной')

print('== детальные эмбеды сообщений ==')
author = FakeMember(90, 'Author', guild)
msg = FakeMessage(1001, 'удалённый текст', author, guild.channels[108], guild)
msg.attachments = [object(), object()]
run(cog.on_message_delete(msg))
e = last_embed('-сообщения')
check(e and 'Сообщение удалено' in desc_of(e) and 'удалённый текст' in desc_of(e)
      and 'Вложений удалено' in desc_of(e) and 'Отправлено' in desc_of(e),
      'удаление: текст + вложения + дата')
check(e.thumbnail and e.thumbnail.url, 'удаление: аватарка автора')

before = FakeMessage(1002, 'было это', author, guild.channels[108], guild)
after = FakeMessage(1002, 'стало другое', author, guild.channels[108], guild)
run(cog.on_message_edit(before, after))
e = last_embed('-сообщения')
check(e and 'Было' in desc_of(e) and 'Стало' in desc_of(e) and 'Перейти к сообщению' in desc_of(e),
      'правка: было/стало + ссылка')

print('== таймаут ==')
m_before = FakeMember(91, 'Violator', guild)
m_after = FakeMember(91, 'Violator', guild)
m_after.timed_out_until = NOW + datetime.timedelta(minutes=30)
guild.audit_entries = [FakeAuditEntry(91, mod, 'оскорбления')]
run(cog.on_member_update(m_before, m_after))
e = last_embed('-модерация')
check(e and 'замьючен' in desc_of(e) and 'Действует до' in desc_of(e) and 'оскорбления' in desc_of(e),
      'таймаут: эмбед с модератором, причиной и сроком')

print('== каналы / роли / инвайты / сервер ==')
run(cog.on_guild_channel_create(guild.channels[108]))
e = last_embed('-сервер')
check(e and 'Канал создан' in desc_of(e) and 'текстовый' in desc_of(e), 'создание канала: тип по-русски')

class _Ch(FakeChannel):
    def __init__(self, cid, name):
        super().__init__(cid, name)
        self.topic = 'старая тема'; self.slowmode_delay = 0; self.nsfw = False
b_ch = _Ch(108, 'старое-имя'); a_ch = _Ch(108, 'новое-имя')
b_ch.guild = guild; a_ch.guild = guild
guild.audit_entries = [FakeAuditEntry(108, mod, None)]
run(cog.on_guild_channel_update(b_ch, a_ch))
e = last_embed('-сервер')
check(e and 'Канал изменён' in desc_of(e) and 'старое-имя' in desc_of(e) and 'новое-имя' in desc_of(e),
      'изменение канала: diff названия')

role = FakeRole(300, 'НоваяРоль', perms=['kick_members', 'ban_members'], color=0xFF8800)
role.guild = guild
run(cog.on_guild_role_create(role))
e = last_embed('-сервер')
check(e and 'Роль создана' in desc_of(e) and '#ff8800' in desc_of(e) and 'Бан' in desc_of(e),
      'роль создана: цвет + ключевые права')

inviter = FakeUser(60, 'Inviter')
invite = type('I', (), {'guild': guild, 'code': 'ABC123', 'inviter': inviter,
                        'channel': guild.channels[108], 'max_uses': 10, 'max_age': 86400,
                        'temporary': False})()
run(cog.on_invite_create(invite))
e = last_embed('-сервер')
check(e and 'discord.gg/ABC123' in desc_of(e) and 'Inviter' in desc_of(e) and '1 дн.' in desc_of(e),
      'инвайт: код, создатель, срок')

print('== Центр логов (select-меню) ==')
admin = FakeMember(10, 'Boss', guild)
admin.guild_permissions = FakePerms(); admin.guild_permissions.administrator = True
view = LogsCenterView(guild, admin.id)
ov = view.overview_embed()
check('Центр логов' in ov.description and len(ov.fields) == 2, 'обзор: заголовок + 2 поля')
check('❌' not in ov.fields[0].value, 'обзор: все 11 категорий имеют каналы')

sel = [c for c in view.children if isinstance(c, discord.ui.Select)][0]
check(len(sel.options) == len(LOG_CENTER_ITEMS) == 11, f'в меню {len(sel.options)} категорий')
opts = {o.value for o in sel.options}
check({'mod', 'message', 'welcome', 'ticket-log', 'ai-alerts'} <= opts, 'в меню есть ключевые категории')

# выбор категории → статус-эмбед
view.selected = 'message'
se = view.status_embed()
check('Сообщения' in se.description and '-сообщения' not in se.description and '<#' in se.description,
      'статус: упоминание канала категории')

# кнопка Тест: эмбед уходит в канал категории
btn_test = [c for c in view.children if isinstance(c, discord.ui.Button) and c.custom_id == 'lc:test'][0]
inter = FakeInter(guild, admin)
n_before = len(guild.channels[102].sent)  # -сообщения
run(btn_test.callback(inter))
check(len(guild.channels[102].sent) == n_before + 1, 'тест: сообщение доставлено в -сообщения')
check(inter.response.edited and '✅ Тест отправлен' in inter.response.edited[0].description,
      'тест: статус обновлён с подтверждением')

# удаляем канал -приветствие → статус ❌, кнопка Починить создаёт заново
del guild.channels[105]
view.selected = 'welcome'
se = view.status_embed()
check('❌' in se.description, 'welcome: канал отсутствует -> ❌')
btn_fix = [c for c in view.children if isinstance(c, discord.ui.Button) and c.custom_id == 'lc:fix'][0]
inter2 = FakeInter(guild, admin)
run(btn_fix.callback(inter2))
check(_lc_find_channel(guild, 'welcome') is not None, 'починить: -приветствие создан заново')
check(inter2.response.edited and 'Готово' in inter2.response.edited[0].description,
      'починить: статус обновлён')

# неавторизованный пользователь
simple = FakeMember(11, 'Noob', guild)
simple.guild_permissions = FakePerms()
inter3 = FakeInter(guild, simple)
ok = run(view.interaction_check(inter3))
check(ok is False and inter3.response.sent and 'администраторам' in inter3.response.sent[0],
      'чужак: отказ с эфемерным ответом')

print('== анти-спам аудит-синка (503 Discord) ==')
class _BotWithGuilds:
    def __init__(self, g): self.guilds = [g]
sync_cog = Logs(_BotWithGuilds(guild))
guild.audit_entries = []
errs = run(sync_cog._sync_discord_audit_log())
check(errs == [], 'здоровый сервер -> список ошибок пуст')

class FailAuditGuild(FakeGuild):
    def audit_logs(self, limit=8, action=None, oldest_first=False, **kw):
        raise RuntimeError('503 Service Unavailable: upstream connect error')
bad_guild = FailAuditGuild()
sync_cog2 = Logs(_BotWithGuilds(bad_guild))
errs2 = run(sync_cog2._sync_discord_audit_log())
check(len(errs2) == 1 and '503' in str(errs2[0][1]),
      'падающий audit API -> ошибка ВОЗВРАЩАЕТСЯ циклу (а не спамится в лог)')

print('== цикл аудита запускается один раз (reconnect-safe) ==')
once_cog = Logs(_BotWithGuilds(guild))
run(once_cog.on_ready())
check(once_cog._audit_sync_started is True, 'после первого on_ready цикл отмечен запущенным')
tasks_before = len(asyncio.all_tasks(loop)) if hasattr(asyncio, 'all_tasks') else 0
run(once_cog.on_ready())
tasks_after = len(asyncio.all_tasks(loop)) if hasattr(asyncio, 'all_tasks') else 0
check(tasks_after <= tasks_before + 1, 'второй on_ready НЕ плодит дубли цикла')

# ═══ Свой фон-фото карточек логов (владелец 2026-09-05: «данные в фото
# внутри, а сама фото — как задний фон») ═══
print('== фон-фото карточек логов ==')
from services.log_card import (get_log_cards_cfg, save_log_cards_cfg,  # noqa: E402
                               render_log_card, fetch_bg_direct,
                               get_bg_bytes_sync)
_saved = save_log_cards_cfg(777, {'theme': 'hakumo',
                                  'bg_url': 'https://pin.it/7jxEf3HAx'})
check(_saved.get('bg_url') == 'https://pin.it/7jxEf3HAx',
      'bg_url сохраняется в оформлении логов')
check(get_log_cards_cfg(777).get('bg_url') == 'https://pin.it/7jxEf3HAx',
      'bg_url читается обратно')
check(save_log_cards_cfg(778, {'bg_url': 'http://127.0.0.1/x.png'}).get('bg_url') == '',
      'локальные адреса в bg_url отбрасываются')
check(get_log_cards_cfg(779).get('bg_url') == '',
      'по умолчанию фона-фото нет — звёздный фон')

import io as _bio
from PIL import Image as _PILImage
_bbuf = _bio.BytesIO()
_PILImage.new('RGB', (900, 600), (18, 26, 52)).save(_bbuf, format='PNG')
_ph_bytes = _bbuf.getvalue()
_jpg = render_log_card('mod', 'Выдан мут (чат + войс)',
                       [('Пользователь', 'GhostBlade'),
                        ('Модератор', 'Sonya'), ('Срок', '30 минут')],
                       cat_name='модерация', time_str='20:41 UTC',
                       bg_bytes=_ph_bytes)
check(bool(_jpg) and _jpg[:2] == b'\xff\xd8' and len(_jpg) > 20000,
      'карточка лога с фото-фоном рисуется (JPEG)')
check(render_log_card('mod', 'Т', [('A', 'b')], cat_name='модерация',
                       bg_bytes=b'garbage') is not None,
      'битый фон-фото не роняет карточку — звёздный фон')

check(fetch_bg_direct('') is None and fetch_bg_direct('ftp://x') is None,
      'пустой/не-http фон не качается')
check(get_bg_bytes_sync('') is None, 'пустой bg_url — без загрузки, кэш молчит')

loop.close()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
