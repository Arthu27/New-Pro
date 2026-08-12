# -*- coding: utf-8 -*-
"""АВТОФИЛЬТР ЧАТА — настоящая автомодерация (PRO).

- 🚫 Запрещённые слова: умный матчинг — регистр, «л33т»-символы (му50р),
  повторы букв (мусооор), залго/диакритика и раздельный ввод (м у с о р)
  нарушителя не спасают, а «архитектура» за слово «хит» не сгорает.
- 🔗 Анти-ссылки: любой линк или инвайт вне whitelist — удаляем.
- 🔠 Анти-капс: доля ЗАГЛАВНЫХ выше порога на достаточно длинных сообщениях.
- 🌊 Анти-флуд: N сообщений за M секунд или N одинаковых подряд →
  очистка последних сообщений автора + таймаут.

Настройки за сервер лежат в data/autofilter_{gid}.json и живо
перечитываются (кеш по mtime): панель /autofilter и /filter пишут
и читают один и тот же файл. Иммунитет: manage_messages, админы,
«иммунные роли» и каналы-исключения из конфига.
"""

from logger import get_logger

_log = get_logger("auto_filter")

import json
import os
import re
import time
import unicodedata
from collections import Counter, deque
from copy import deepcopy
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from logger import get_logger

log = get_logger('auto_filter')

GOLD = 0xD4AF37

FILTER_NAMES = {'words': 'Запрещённые слова', 'links': 'Ссылки',
                'caps': 'Капс', 'flood': 'Флуд/спам'}
ACTION_LABELS = {'delete': 'Удаление сообщения', 'warn': 'Удаление + варн',
                 'timeout': 'Очистка + таймаут'}
FILTER_ACTIONS = {'words': ('delete', 'warn'), 'links': ('delete', 'warn'),
                  'caps': ('delete', 'warn'), 'flood': ('delete', 'warn', 'timeout')}

NOTICE_TEXT = {'words': 'такие слова здесь запрещены 🚫',
               'links': 'ссылки можно только из разрешённого списка 🔗',
               'caps': 'поменьше КАПСА, пожалуйста 🔠',
               'flood': 'флуд/спам запрещён, притормози 🌊'}

MAX_WORDS = 200        # максимум запрещённых слов
MAX_WORD_LEN = 60      # и whitelist-доменов не длиннее
MAX_IDS = 60           # каналов-исключений / иммунных ролей

DEFAULT_FILTER = {
    'enabled': True,
    'words': {'enabled': True, 'action': 'warn', 'list': []},
    'links': {'enabled': False, 'action': 'delete', 'whitelist': []},
    'caps': {'enabled': False, 'action': 'delete', 'percent': 70, 'min_length': 12},
    'flood': {'enabled': True, 'action': 'timeout', 'limit': 5, 'seconds': 5,
              'dupe_count': 3, 'timeout_minutes': 10},
    'ignore_channels': [],
    'immune_roles': [],
}

# Диапазоны числовых параметров (для валидации из панели)
PARAM_RANGES = {('caps', 'percent'): (20, 100), ('caps', 'min_length'): (4, 120),
                ('flood', 'limit'): (3, 15), ('flood', 'seconds'): (2, 30),
                ('flood', 'dupe_count'): (2, 10), ('flood', 'timeout_minutes'): (1, 120)}


# ─────────────────────────────────────────────────────────────
# Чистые функции матчинга (тестируются без discord)
# ─────────────────────────────────────────────────────────────
# «Фолдинг»: кириллица/латиница-омоглифы и л33т складываются в один
# алфавит. Применяется и к тексту, и к слову, поэтому «му50р», «mycop»
# и «мусор» становятся одной строкой и сравниваются честно.
FOLD = str.maketrans({'4': 'a', 'а': 'a', '@': 'a', '^': 'a',
                      '8': 'b', '6': 'b', 'в': 'b',
                      'с': 'c', 's': 'c', '5': 'c', '$': 'c', '¢': 'c',
                      '3': 'e', 'е': 'e', 'ё': 'e', '€': 'e',
                      '9': 'g',
                      'н': 'h',
                      '1': 'i', '|': 'i',
                      'к': 'k',
                      'м': 'm',
                      'о': 'o', '0': 'o',
                      'р': 'p',
                      'т': 't', '7': 't', '+': 't',
                      'х': 'x',
                      'у': 'y'})
WORD_CHARS = r'0-9a-zа-яё'
SEPARATORS = r'[^0-9a-zа-яё]{0,3}'          # «м у с о р» / «м-у-с-о-р»
LINK_RE = re.compile(r'(?:https?://[^\s<>\)\]]+|www\.[^\s<>\)\]]+'
                     r'|(?:discord\.gg|discord(?:app)?\.com/invite)/[A-Za-z0-9-]+)',
                     re.IGNORECASE)


def normalize_text(text: str) -> str:
    """Нижний регистр, срез диакритики/залго, схлопывание повторов букв."""
    if not text:
        return ''
    t = unicodedata.normalize('NFKD', str(text))
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    t = t.casefold()
    t = re.sub(r'(.)\1{2,}', r'\1', t)          # мусооооор → мусор
    return t


def fold_text(text: str) -> str:
    """Нормализация + фолдинг омоглифов/л33та (пробелы и пунктуация остаются)."""
    return normalize_text(text).translate(FOLD)


def squash(text: str) -> str:
    """Только «словные» символы после фолдинга — для эвристик обхода фильтра."""
    return re.sub(r'[^0-9a-zа-яё]', '', fold_text(text))


def _evasion_re(word_norm: str):
    """Регекс слова с опциональными разделителями и границами слова."""
    w = squash(word_norm)
    if not w:
        return None
    body = SEPARATORS.join(re.escape(c) for c in w)
    return re.compile(r'(?<![' + WORD_CHARS + '])' + body + r'(?![' + WORD_CHARS + '])')


def find_bad_word(text: str, words):
    """Первое сработавшее слово из списка или None.

    Текст и слово складываются в общий алфавит (фолдинг), потому ни л33т,
    ни вставки пробелов/пунктуации между буквами не спасают; при этом
    короткое слово не сгорает внутри длинного («хит» ⊄ «архитектура»).
    """
    ft = fold_text(text)
    if not ft or not words:
        return None
    for raw in words:
        wsq = squash(raw)
        if not wsq:
            continue
        rx = _evasion_re(wsq)
        if rx is not None and rx.search(ft):
            return raw
    return None


def extract_links(text: str):
    """Все URL/инвайты из сообщения (схема, www или discord-invite)."""
    if not text:
        return []
    return LINK_RE.findall(str(text))


def link_allowed(link: str, whitelist) -> bool:
    """Ссылка разрешена, если содержит любой домен из whitelist."""
    l = str(link).lower()
    return any(w and w.lower() in l for w in (whitelist or []))


def caps_ratio(text: str) -> float:
    """Процент заглавных среди букв, у которых вообще есть регистр."""
    letters = [c for c in str(text) if c.lower() != c.upper()]
    if not letters:
        return 0.0
    up = sum(1 for c in letters if c.upper() == c and c.lower() != c)
    return 100.0 * up / len(letters)


def classify_message(cfg: dict, text: str) -> list:
    """Список нарушений {'filter', 'detail'} для текста по конфигу."""
    out = []
    if not cfg.get('enabled', True):
        return out
    w = cfg.get('words', {})
    if w.get('enabled') and w.get('list'):
        hit = find_bad_word(text, w['list'])
        if hit:
            out.append({'filter': 'words', 'detail': hit})
    l = cfg.get('links', {})
    if l.get('enabled'):
        bad = [u for u in extract_links(text) if not link_allowed(u, l.get('whitelist'))]
        if bad:
            out.append({'filter': 'links', 'detail': bad[0]})
    c = cfg.get('caps', {})
    if c.get('enabled'):
        text = str(text or '')
        if len(text) >= int(c.get('min_length', 12)) \
                and caps_ratio(text) >= int(c.get('percent', 70)):
            out.append({'filter': 'caps', 'detail': f'{caps_ratio(text):.0f}% заглавных'})
    return out


class FloodTracker:
    """Память флуда: (сервер, юзер) → очередь (время, текст)."""

    def __init__(self):
        self._q = {}

    def reset(self):
        self._q.clear()

    def hit(self, gid, uid, content, limit, seconds, dupe_count, now=None):
        """'flood' — много сообщений за окно; 'dupe' — одинаковые подряд; None."""
        now = time.time() if now is None else now
        key = (int(gid), int(uid))
        dq = self._q.setdefault(key, deque(maxlen=60))
        dq.append((now, str(content or '')))
        while dq and now - dq[0][0] > seconds:
            dq.popleft()
        win = list(dq)
        if dupe_count and dupe_count >= 2:
            counts = Counter(squash(c) or '∅' for _, c in win)
            if counts.get(squash(content) or '∅', 0) >= dupe_count:
                dq.clear()
                return 'dupe'
        if len(win) >= limit:
            dq.clear()
            return 'flood'
        return None


def is_ignored_channel(cfg: dict, channel_id, parent_id=None) -> bool:
    ignored = {str(x) for x in cfg.get('ignore_channels', [])}
    if str(channel_id) in ignored:
        return True
    return bool(parent_id) and str(parent_id) in ignored


# ─────────────────────────────────────────────────────────────
# Конфиг: файл, кеш по mtime, валидация
# ─────────────────────────────────────────────────────────────
_CFG_CACHE = {}   # gid -> (mtime, cfg)


def cfg_path(gid) -> str:
    return os.path.join('data', f'autofilter_{int(gid)}.json')


def has_word_chars(text: str) -> bool:
    """В слове есть хоть одна буква/цифра ДО фолдинга («$$$» — не слово)."""
    return bool(re.search(r'[0-9a-zа-яё]', normalize_text(text)))


def sanitize_words(words, limit=MAX_WORDS) -> list:
    """Чистим список: strip, без пустых/дублей, с лимитами."""
    out, seen = [], set()
    for raw in (words or []):
        w = str(raw).strip()[:MAX_WORD_LEN]
        if not w or not has_word_chars(w):
            continue
        key = normalize_text(w)
        if key in seen:
            continue
        seen.add(key)
        out.append(w)
        if len(out) >= limit:
            break
    return out


def _sanitize_ids(ids) -> list:
    out = []
    for raw in (ids or []):
        s = str(raw).strip()
        if s.isdigit() and s not in out:
            out.append(s)
        if len(out) >= MAX_IDS:
            break
    return out


def merge_config(saved: dict) -> dict:
    """Defaults, на которые мягко наложено сохранённое (типы приводятся)."""
    cfg = deepcopy(DEFAULT_FILTER)
    if not isinstance(saved, dict):
        return cfg
    cfg['enabled'] = bool(saved.get('enabled', cfg['enabled']))
    for f in FILTER_NAMES:
        src = saved.get(f) or {}
        if not isinstance(src, dict):
            continue
        dst = cfg[f]
        dst['enabled'] = bool(src.get('enabled', dst['enabled']))
        act = str(src.get('action', dst['action']))
        dst['action'] = act if act in FILTER_ACTIONS[f] else dst['action']
        for key, (lo, hi) in PARAM_RANGES.items():
            if key[0] != f:
                continue
            try:
                dst[key[1]] = max(lo, min(hi, int(src.get(key[1], dst[key[1]]))))
            except (TypeError, ValueError) as _ex:
                _log.debug("merge_config(): подавлено: %s", _ex)
    cfg['words']['list'] = sanitize_words((saved.get('words') or {}).get('list'))
    cfg['links']['whitelist'] = [w.lower() for w in
                                 sanitize_words((saved.get('links') or {}).get('whitelist'), limit=50)]
    cfg['ignore_channels'] = _sanitize_ids(saved.get('ignore_channels'))
    cfg['immune_roles'] = _sanitize_ids(saved.get('immune_roles'))
    return cfg


def validate_config(data: dict):
    """Строгая проверка от панели → (cfg, errors). Слова/ids — мягко чистятся."""
    errors = []
    data = data if isinstance(data, dict) else {}
    for f in FILTER_NAMES:
        act = ((data.get(f) or {}).get('action'))
        if act is not None and act not in FILTER_ACTIONS[f]:
            errors.append(f'{f}: недопустимое действие «{act}»')
    for (f, key), (lo, hi) in PARAM_RANGES.items():
        raw = (data.get(f) or {}).get(key)
        if raw is None:
            continue
        try:
            v = int(raw)
        except (TypeError, ValueError):
            errors.append(f'{f}.{key}: нужно число от {lo} до {hi}')
            continue
        if not (lo <= v <= hi):
            errors.append(f'{f}.{key}: {v} вне диапазона {lo}–{hi}')
    return merge_config(data), errors


def load_config(gid) -> dict:
    """Конфиг сервера (живой пересчёт по mtime — правки панели подхватываются)."""
    gid = int(gid)
    p = cfg_path(gid)
    try:
        st = os.stat(p)
        mt = (st.st_mtime_ns, st.st_size)
    except OSError:
        mt = None
    cached = _CFG_CACHE.get(gid)
    if cached and cached[0] == mt:
        return deepcopy(cached[1])
    saved = {}
    if mt is not None:
        try:
            with open(p, encoding='utf-8') as fp:
                saved = json.load(fp)
        except Exception as e:
            log.warning(f'AutoFilter: битый конфиг {p}: {e} — берём дефолты')
    cfg = merge_config(saved)
    _CFG_CACHE[gid] = (mt, cfg)
    return deepcopy(cfg)


def save_config(gid, cfg: dict):
    os.makedirs('data', exist_ok=True)
    p = cfg_path(int(gid))
    with open(p, 'w', encoding='utf-8') as fp:
        json.dump(merge_config(cfg), fp, indent=2, ensure_ascii=False)
    _CFG_CACHE.pop(int(gid), None)


# ─────────────────────────────────────────────────────────────
# Ког
# ─────────────────────────────────────────────────────────────
class AutoFilter(commands.Cog):
    """🧹 Автофильтр чата: слова, ссылки, капс, флуд."""

    filter = app_commands.Group(name='filter',
                                description='Автофильтр чата: настройка и проверка',
                                guild_only=True)

    def __init__(self, bot):
        self.bot = bot
        self.tracker = FloodTracker()

    # ── инфраструктура ────────────────────────────────────────
    def _card(self, title: str, desc: str, color=None) -> discord.Embed:
        e = discord.Embed(title=title, description=desc,
                          color=color if color is not None else GOLD,
                          timestamp=datetime.now(timezone.utc).replace(tzinfo=None))
        e.set_footer(text='Aether AutoFilter')
        return e

    def _is_immune(self, message, cfg) -> bool:
        """Бот, мод (manage_messages), иммунная роль или канал-исключение."""
        ch = message.channel
        if is_ignored_channel(cfg, getattr(ch, 'id', 0), getattr(ch, 'parent_id', None)):
            return True
        m = message.author
        perms = getattr(m, 'guild_permissions', None)
        if perms and (getattr(perms, 'manage_messages', False)
                      or getattr(perms, 'administrator', False)):
            return True
        immune = set(map(str, cfg.get('immune_roles') or []))
        return any(str(getattr(r, 'id', '')) in immune for r in getattr(m, 'roles', []))

    async def _modlog(self, guild, title, fields, color=None):
        try:
            from cogs import logs
            ch = await logs.ensure_log_channel(guild, 'модерация')
            if not ch:
                return
            emb = logs._styled_log_embed(guild, 'модерация', title, fields=fields, color=color)
            await logs._safe_send(ch, embed=emb)
        except Exception as e:
            log.warning(f'AutoFilter: лог не ушёл: {e}')

    async def _add_warn(self, member, reason):
        """Стандартный варн через ког warnings (с логом и скорингом)."""
        try:
            cog = self.bot.get_cog('warnings')
            if cog is None:
                log.warning('AutoFilter: ког warnings не найден — варн пропущен')
                return
            mod = getattr(member.guild, 'me', None) or self.bot.user
            await cog.add_warning(member, mod, reason)
        except Exception as e:
            log.warning(f'AutoFilter: не удалось выдать варн: {e}')

    # ── основной слушатель ────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if getattr(message.author, 'bot', True) or not message.guild:
            return
        if not isinstance(message.author, discord.Member):
            return
        cfg = load_config(message.guild.id)
        if not cfg['enabled'] or self._is_immune(message, cfg):
            return

        violations = classify_message(cfg, message.content or '')
        flood_kind = None
        if cfg['flood']['enabled']:
            f = cfg['flood']
            flood_kind = self.tracker.hit(message.guild.id, message.author.id,
                                          message.content, f['limit'], f['seconds'],
                                          f['dupe_count'])
        if not violations and not flood_kind:
            return
        await self._punish(message, cfg, violations, flood_kind)

    async def _punish(self, message, cfg, violations, flood_kind):
        author = message.author
        if flood_kind:
            fname, action = 'flood', cfg['flood']['action']
            detail = 'Одинаковые сообщения подряд' if flood_kind == 'dupe' \
                else f'Больше {cfg["flood"]["limit"]} сообщений за {cfg["flood"]["seconds"]} сек'
        else:
            fname = violations[0]['filter']
            action = cfg[fname]['action']
            detail = violations[0]['detail']

        try:
            await message.delete()
        except Exception as _ex:
            _log.debug("_punish(): подавлено: %s", _ex)
        try:
            await message.channel.send(f'{author.mention} {NOTICE_TEXT[fname]}', delete_after=6)
        except Exception as _ex:
            _log.debug("_punish(): подавлено: %s", _ex)

        if flood_kind and action == 'timeout':
            try:  # зачистка последних сообщений автора в этом канале
                await message.channel.purge(limit=60, check=lambda m: m.author == author,
                                            bulk=True)
            except Exception as _ex:
                _log.debug("_punish(): подавлено: %s", _ex)
            try:
                await author.timeout(timedelta(minutes=cfg['flood']['timeout_minutes']),
                                     reason=f'Автофильтр: флуд ({detail})')
            except Exception as e:
                log.warning(f'AutoFilter: таймаут не выдан: {e}')

        if action in ('warn', 'timeout'):
            await self._add_warn(author, f'Автофильтр · {FILTER_NAMES[fname]}: {detail}')

        text_preview = (message.content or '')[:200] or '—'
        await self._modlog(message.guild, f'Автофильтр: {FILTER_NAMES[fname]}',
                           [('Участник', f'{author.mention} ({author.id})'),
                            ('Канал', getattr(message.channel, 'mention', '—')),
                            ('Совпадение', str(detail)[:120]),
                            ('Действие', ACTION_LABELS[action]),
                            ('Текст', f'```{text_preview}```'.replace('`', 'ʼ'))],
                           color=0xE67E22)

    # ── /filter … ─────────────────────────────────────────────
    def _status_embed(self, cfg) -> discord.Embed:
        lines = []
        for f, name in FILTER_NAMES.items():
            part = cfg[f]
            st = '🟢' if part['enabled'] else '🔴'
            extra = ''
            if f == 'words':
                extra = f" · слов: **{len(part['list'])}**"
            elif f == 'links':
                extra = f" · whitelist: **{len(part['whitelist'])}**"
            elif f == 'caps':
                extra = f" · ≥{part['percent']}% от {part['min_length']} симв."
            elif f == 'flood':
                extra = f" · {part['limit']} сообщ / {part['seconds']} сек"
            lines.append(f"{st} **{name}** — {ACTION_LABELS[part['action']]}{extra}")
        state = '🛡 Включён' if cfg['enabled'] else '⏸ На паузе'
        e = self._card(f'🧹 Автофильтр чата — {state}', '\n'.join(lines))
        if cfg['ignore_channels']:
            e.add_field(name='Каналы-исключения', value=', '.join(f'<#{i}>' for i in cfg['ignore_channels']) or '—',
                        inline=False)
        return e

    @filter.command(name='status', description='Текущие настройки автофильтра чата')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def filter_status(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=self._status_embed(load_config(interaction.guild_id)), ephemeral=True)

    @filter.command(name='add', description='Добавить запрещённое слово/фразу')
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(word='Слово или фраза (до 60 символов)')
    async def filter_add(self, interaction: discord.Interaction, word: str):
        cfg = load_config(interaction.guild_id)
        word = word.strip()[:MAX_WORD_LEN]
        if not has_word_chars(word):
            return await interaction.response.send_message(
                '❌ В слове должна быть хоть одна буква или цифра.', ephemeral=True)
        words = cfg['words']['list']
        if normalize_text(word) in [normalize_text(w) for w in words]:
            return await interaction.response.send_message(
                f'ℹ️ Слово `{word}` уже в списке.', ephemeral=True)
        if len(words) >= MAX_WORDS:
            return await interaction.response.send_message(
                f'❌ Лимит: не больше {MAX_WORDS} слов.', ephemeral=True)
        words.append(word)
        save_config(interaction.guild_id, cfg)
        await interaction.response.send_message(
            embed=self._card('🚫 Слово добавлено',
                             f'`{word}` — теперь под фильтром. Всего слов: **{len(words)}**'),
            ephemeral=True)

    @filter.command(name='remove', description='Убрать слово из запрещённых')
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(word='Слово из списка')
    async def filter_remove(self, interaction: discord.Interaction, word: str):
        cfg = load_config(interaction.guild_id)
        before = len(cfg['words']['list'])
        key = normalize_text(word)
        cfg['words']['list'] = [w for w in cfg['words']['list'] if normalize_text(w) != key]
        if len(cfg['words']['list']) == before:
            return await interaction.response.send_message(
                f'ℹ️ Слово `{word}` не найдено в списке.', ephemeral=True)
        save_config(interaction.guild_id, cfg)
        await interaction.response.send_message(
            embed=self._card('🗑 Слово убрано', f'`{word}` больше не фильтруется. '
                             f'Осталось слов: **{len(cfg["words"]["list"])}**'),
            ephemeral=True)

    @filter.command(name='words', description='Показать список запрещённых слов')
    @app_commands.checks.has_permissions(manage_messages=True)
    async def filter_words(self, interaction: discord.Interaction):
        words = load_config(interaction.guild_id)['words']['list']
        body = '\n'.join(f'`{i + 1}.` {w}' for i, w in enumerate(words[:80])) or '_Список пуст._'
        if len(words) > 80:
            body += f'\n…и ещё {len(words) - 80}'
        await interaction.response.send_message(
            embed=self._card(f'🚫 Запрещённые слова ({len(words)})', body), ephemeral=True)

    @filter.command(name='toggle', description='Включить/выключить фильтр или всю систему')
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(target='Что переключаем')
    @app_commands.choices(target=[
        app_commands.Choice(name='Весь автофильтр', value='main'),
        app_commands.Choice(name='Слова', value='words'),
        app_commands.Choice(name='Ссылки', value='links'),
        app_commands.Choice(name='Капс', value='caps'),
        app_commands.Choice(name='Флуд', value='flood')])
    async def filter_toggle(self, interaction: discord.Interaction, target: str):
        cfg = load_config(interaction.guild_id)
        if target == 'main':
            cfg['enabled'] = not cfg['enabled']
            state = '🛡 включён' if cfg['enabled'] else '⏸ на паузе'
        else:
            cfg[target]['enabled'] = not cfg[target]['enabled']
            state = '🟢 включён' if cfg[target]['enabled'] else '🔴 выключен'
        save_config(interaction.guild_id, cfg)
        name = 'Автофильтр' if target == 'main' else f'Фильтр «{FILTER_NAMES[target]}»'
        await interaction.response.send_message(
            embed=self._card('⚙️ Переключено', f'{name} теперь **{state}**.'), ephemeral=True)

    @filter.command(name='test', description='Сухая проверка: сработал бы фильтр на этот текст?')
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(text='Текст для проверки (никого не наказывает)')
    async def filter_test(self, interaction: discord.Interaction, text: str):
        cfg = load_config(interaction.guild_id)
        v = classify_message(cfg, text)
        if not v:
            desc = '✅ Чисто — ни один фильтр не сработал.'
        else:
            desc = '\n'.join(f'🚨 **{FILTER_NAMES[x["filter"]]}** — совпадение: `{x["detail"]}`' for x in v)
        await interaction.response.send_message(
            embed=self._card('🧪 Проверка текста', desc), ephemeral=True)

    @filter.command(name='ignore', description='Добавить/убрать канал из исключений фильтра')
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(channel='Канал (по умолчанию текущий)')
    async def filter_ignore(self, interaction: discord.Interaction,
                            channel: discord.TextChannel = None):
        channel = channel or interaction.channel
        cfg = load_config(interaction.guild_id)
        ids = cfg['ignore_channels']
        cid = str(channel.id)
        if cid in ids:
            ids.remove(cid)
            msg = f'{channel.mention} снова под защитой фильтра 🛡'
        else:
            if len(ids) >= MAX_IDS:
                return await interaction.response.send_message(
                    f'❌ Лимит исключений: {MAX_IDS}.', ephemeral=True)
            ids.append(cid)
            msg = f'{channel.mention} добавлен в исключения — фильтр там молчит 🤫'
        save_config(interaction.guild_id, cfg)
        await interaction.response.send_message(
            embed=self._card('🎯 Каналы-исключения', msg), ephemeral=True)


async def setup(bot):
    await bot.add_cog(AutoFilter(bot))
