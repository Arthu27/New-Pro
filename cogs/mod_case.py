# -*- coding: utf-8 -*-
"""MOD CASE — /case: полная карточка нарушителя одной картинкой.

Собирает воедино всё, что есть о пользователе:
- варны (warnings cog), кейсы и заметки (advanced_mod / data/mod_advanced_data.json)
- демки (proof_cog), тихий мут (mod_plus ghost), текущий таймаут
- риск-скор по формуле warnings (-12/-18/-25)
и рисует премиум PNG-досье в фирменном золотом стиле.
"""

from logger import get_logger

_log = get_logger("mod_case")

from json_store import load_json as _js_load, save_json as _js_save

import io
import json
import os
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from logger import get_logger

log = get_logger("mod_case")

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_OK = True
except Exception:
    _PIL_OK = False

try:
    from cogs import _card_style as CS
except Exception:
    CS = None

try:
    from cogs._menu_bg import load_menu_bg
except Exception:
    load_menu_bg = None

ADV_DATA_PATH = 'data/mod_advanced_data.json'

GOLD = (224, 176, 74, 255)
GOLD_SOFT = (224, 176, 74, 70)
TXT = (240, 236, 228, 255)
TXT2 = (196, 188, 170, 255)
TXT3 = (138, 125, 95, 255)
GREEN = (74, 222, 128, 255)
ORANGE = (243, 156, 18, 255)
RED = (231, 76, 60, 255)
BOX = (255, 255, 255, 10)
BOX_LINE = (224, 176, 74, 55)


# ─────────────────────────────────────────────────────────────
# Данные (чистые функции — тестируются без discord)
# ─────────────────────────────────────────────────────────────
def _load_adv_data() -> dict:
    return _js_load(ADV_DATA_PATH, {}, log=_log)


def _fmt_dt(iso_or_dt) -> str:
    try:
        if isinstance(iso_or_dt, datetime):
            dt = iso_or_dt
        else:
            dt = datetime.fromisoformat(str(iso_or_dt).replace('Z', '+00:00'))
        return dt.strftime('%d.%m.%Y')
    except Exception:
        return '—'


def collect_case(user_id, user_name='', warns=(), cases=(), notes=(), proofs=(),
                 ghost=None, timed_out_until=None, joined_at=None, created_at=None) -> dict:
    """Собрать досье в один словарь (всё уже отфильтровано по юзеру или будет здесь)."""
    warns = list(warns or [])
    cases = [c for c in (cases or []) if str(c.get('user_id')) == str(user_id)]
    notes = list(notes or [])
    proofs = [p for p in (proofs or []) if int(p.get('user_id') or 0) == int(user_id)]

    try:
        from cogs.warnings import _compute_score, _score_text
        score = _compute_score(len(warns), cases)
        score_text = _score_text(score)
    except Exception:
        score = max(0, 100 - len(warns) * 12 - len(cases) * 18)
        score_text = 'Чист' if score >= 60 else ('Под наблюдением' if score >= 30 else 'Опасен')

    ghost_active = bool(ghost)
    ghost_until = _fmt_dt(ghost.get('until') or ghost.get('expires_at') or '') if ghost else None

    def _last(src, reason_key, date_key, extra_key=None):
        if not src:
            return []
        tail = list(src)[-3:]
        out = []
        for it in reversed(tail):
            reason = str(it.get(reason_key) or it.get('note') or '—')[:38]
            date = _fmt_dt(it.get(date_key) or it.get('set_at') or it.get('ts'))
            extra = str(it.get(extra_key) or '') if extra_key else ''
            out.append({'date': date, 'reason': reason, 'extra': extra})
        return out

    return {
        'user_id': int(user_id),
        'user_name': user_name or 'Неизвестно',
        'warns_n': len(warns), 'cases_n': len(cases),
        'notes_n': len(notes), 'proofs_n': len(proofs),
        'score': score, 'score_text': score_text,
        'ghost_active': ghost_active, 'ghost_until': ghost_until,
        'timed_out': bool(timed_out_until),
        'timeout_until': _fmt_dt(timed_out_until) if timed_out_until else None,
        'joined': _fmt_dt(joined_at) if joined_at else '—',
        'created': _fmt_dt(created_at) if created_at else '—',
        'last_warns': _last(warns, 'reason', 'timestamp'),
        'last_proofs': _last(sorted(proofs, key=lambda p: int(p.get('id') or 0)),
                             'reason', 'set_at', 'action'),
    }


# ─────────────────────────────────────────────────────────────
# Рендер карточки
# ─────────────────────────────────────────────────────────────
def _font(bold: bool, size: int):
    if CS is not None:
        try:
            return CS.font(bold, size)
        except Exception as _ex:
            _log.debug("_font(): подавлено: %s", _ex)
    return ImageFont.load_default() if _PIL_OK else None


def _score_color(score: int):
    return GREEN if score >= 60 else (ORANGE if score >= 30 else RED)


def render_case_card(d: dict, avatar_img=None) -> io.BytesIO:
    """Нарисовать PNG-досье. avatar_img — PIL.Image или None."""
    W, H = 1200, 830
    if load_menu_bg is not None:
        try:
            bg = load_menu_bg(W, H, 'gold').convert('RGBA')
        except Exception:
            bg = Image.new('RGBA', (W, H), (24, 22, 16, 255))
    else:
        bg = Image.new('RGBA', (W, H), (24, 22, 16, 255))

    ov = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    do = ImageDraw.Draw(ov)
    do.rounded_rectangle((28, 28, W - 28, H - 28), radius=26, fill=(14, 13, 10, 215))
    do.rounded_rectangle((28, 28, W - 28, H - 28), radius=26, outline=(224, 176, 74, 90), width=2)
    bg = Image.alpha_composite(bg, ov)
    dr = ImageDraw.Draw(bg, 'RGBA')

    f_title = _font(True, 40)
    f_h = _font(True, 46)
    f_val = _font(True, 34)
    f_txt = _font(False, 24)
    f_small = _font(False, 19)
    f_lbl = _font(True, 18)

    # шапка
    dr.text((70, 58), 'КАРТОЧКА НАРУШИТЕЛЯ', font=f_title, fill=GOLD)
    dr.line((70, 116, W - 70, 116), fill=GOLD_SOFT, width=2)

    # аватар с золотым кольцом
    ax, ay, ar = 70, 140, 68
    dr.ellipse((ax - 4, ay - 4, ax + ar * 2 + 4, ay + ar * 2 + 4), outline=GOLD, width=3)
    if avatar_img is not None:
        try:
            av = avatar_img.convert('RGBA').resize((ar * 2, ar * 2))
            mask = Image.new('L', (ar * 2, ar * 2), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, ar * 2, ar * 2), fill=255)
            bg.paste(av, (ax, ay), mask)
        except Exception:
            avatar_img = None
    if avatar_img is None:
        dr.ellipse((ax, ay, ax + ar * 2, ay + ar * 2), fill=(42, 38, 28, 255))
        initial = (d['user_name'] or '?')[:1].upper()
        bb = dr.textbbox((0, 0), initial, font=f_h)
        dr.text((ax + ar - (bb[2] - bb[0]) // 2, ay + ar - (bb[3] - bb[1]) // 2),
                initial, font=f_h, fill=GOLD)

    # имя / id / даты
    nx = ax + ar * 2 + 28
    dr.text((nx, 150), d['user_name'][:26], font=f_h, fill=TXT)
    dr.text((nx, 208), f"ID: {d['user_id']}", font=f_txt, fill=TXT2)
    dr.text((nx, 244), f"На сервере с {d['joined']} · аккаунт от {d['created']}", font=f_small, fill=TXT3)

    # скор-кольцо справа
    cx, cy, rr = W - 170, 205, 66
    score = int(d['score'])
    col = _score_color(score)
    dr.arc((cx - rr, cy - rr, cx + rr, cy + rr), start=-90, end=270, fill=(70, 66, 56, 255), width=12)
    if score > 0:
        dr.arc((cx - rr, cy - rr, cx + rr, cy + rr), start=-90, end=-90 + int(360 * score / 100),
               fill=col, width=12)
    bb = dr.textbbox((0, 0), str(score), font=f_h)
    dr.text((cx - (bb[2] - bb[0]) // 2, cy - 26 - (bb[3]) // 2), str(score), font=f_h, fill=col)
    bb = dr.textbbox((0, 0), '/ 100', font=f_small)
    dr.text((cx - (bb[2] - bb[0]) // 2, cy + 16), '/ 100', font=f_small, fill=TXT3)
    st = d['score_text']
    bb = dr.textbbox((0, 0), st, font=f_txt)
    dr.text((cx - (bb[2] - bb[0]) // 2, cy + rr + 16), st, font=f_txt, fill=col)

    # сетка статусов 3×2
    stats = [
        ('ВАРНЫ', str(d['warns_n'])),
        ('НАКАЗАНИЯ', str(d['cases_n'])),
        ('ЗАМЕТКИ', str(d['notes_n'])),
        ('ДЕМКИ', str(d['proofs_n'])),
        ('ТИХИЙ МУТ', ('до ' + d['ghost_until']) if d['ghost_active'] and d['ghost_until']
         else ('АКТИВЕН' if d['ghost_active'] else '—')),
        ('ТАЙМАУТ', ('до ' + d['timeout_until']) if d['timed_out'] and d['timeout_until'] else '—'),
    ]
    gx, gy, gw, gh, gap = 70, 330, 343, 92, 22
    for i, (lbl, val) in enumerate(stats):
        x = gx + (i % 3) * (gw + gap)
        y = gy + (i // 3) * (gh + gap)
        dr.rounded_rectangle((x, y, x + gw, y + gh), radius=16, fill=BOX, outline=BOX_LINE, width=1)
        dr.text((x + 18, y + 14), lbl, font=f_lbl, fill=TXT3)
        vc = col if lbl in ('ТИХИЙ МУТ', 'ТАЙМАУТ') and val not in ('—',) else TXT
        dr.text((x + 18, y + gh - 46), val, font=f_val, fill=vc)

    # списки: варны и демки
    ly = 560
    dr.text((70, ly), 'ПОСЛЕДНИЕ ВАРНЫ', font=f_lbl, fill=GOLD)
    dr.text((W // 2 + 30, ly), 'ПОСЛЕДНИЕ ДЕМКИ', font=f_lbl, fill=GOLD)
    lw = d.get('last_warns') or []
    lp = d.get('last_proofs') or []
    for k, w in enumerate(lw):
        dr.text((70, ly + 34 + k * 32), f"• [{w['date']}] {w['reason']}", font=f_txt, fill=TXT2)
    for k, p in enumerate(lp):
        action = f"{p['extra']}: " if p['extra'] else ''
        dr.text((W // 2 + 30, ly + 34 + k * 32), f"• [{p['date']}] {action}{p['reason']}",
                font=f_txt, fill=TXT2)
    if not lw:
        dr.text((70, ly + 34), 'Чисто ✨', font=f_txt, fill=GREEN)
    if not lp:
        dr.text((W // 2 + 30, ly + 34), 'Демок нет', font=f_txt, fill=TXT3)

    dr.text((70, H - 62), f"Aether ModKit · досье от {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')}",
            font=f_small, fill=TXT3)

    buf = io.BytesIO()
    bg.convert('RGB').save(buf, format='PNG', optimize=True)
    buf.seek(0)
    return buf


# ═══ Регрессия рендера видна в tests/test_case_status.py ═══


class ModCase(commands.Cog):
    """Карточка нарушителя (/case)."""

    def __init__(self, bot):
        self.bot = bot

    def _get_warns(self, gid, uid):
        wc = self.bot.get_cog('warnings')
        if wc is not None and hasattr(wc, '_get_warns'):
            try:
                return wc._get_warns(gid, uid)
            except Exception as _ex:
                _log.debug("_get_warns(): подавлено: %s", _ex)
        try:  # фолбэк на JSON-зеркало
            mirror = _js_load('data/warnings.json', {}, log=_log)
            return (mirror.get(str(gid), {}) or {}).get(str(uid), []) or []
        except Exception as _ex:
            _log.debug("_get_warns(): подавлено: %s", _ex)
        return []

    @app_commands.command(name='case',
                          description='Карточка нарушителя: варны, демки, заметки, статусы — одной картинкой')
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(user='Кого проверяем',
                           public='Показать всем в канале (по умолчанию только вам)')
    async def case(self, interaction: discord.Interaction,
                   user: discord.Member, public: bool = False):
        await interaction.response.defer(ephemeral=not public)
        gid, uid = interaction.guild.id, user.id

        warns = self._get_warns(gid, uid)
        adv = _load_adv_data()
        cases = (adv.get('case') or {}).get(str(gid), []) or []
        notes = ((adv.get('notes') or {}).get(str(gid), {}) or {}).get(str(uid), []) or []
        try:
            from cogs.proof_cog import proof_list
            proofs = proof_list(gid, user_id=uid)
        except Exception:
            proofs = []
        ghost = None
        try:
            from cogs.mod_plus import ghost_entries
            ghost = ghost_entries(gid).get(str(uid))
        except Exception as _ex:
            _log.debug("case(): подавлено: %s", _ex)

        timed = getattr(user, 'timed_out_until', None)
        if timed is not None and timed < datetime.now(timezone.utc):
            timed = None

        d = collect_case(uid, getattr(user, 'display_name', str(user)),
                         warns=warns, cases=cases, notes=notes, proofs=proofs,
                         ghost=ghost, timed_out_until=timed,
                         joined_at=getattr(user, 'joined_at', None),
                         created_at=getattr(user, 'created_at', None))

        avatar_img = None
        if _PIL_OK:
            try:
                raw = await user.display_avatar.read()
                avatar_img = Image.open(io.BytesIO(raw))
            except Exception:
                avatar_img = None

        if not _PIL_OK:
            e = discord.Embed(title=f"🧾 {d['user_name']} — досье", color=0xD4AF37,
                              timestamp=datetime.now(timezone.utc).replace(tzinfo=None))
            e.description = (f"Риск: **{d['score']}/100** ({d['score_text']})\n"
                             f"Варны **{d['warns_n']}** · наказания **{d['cases_n']}** · "
                             f"заметки **{d['notes_n']}** · демки **{d['proofs_n']}**\n"
                             f"Тихий мут: **{'да' if d['ghost_active'] else 'нет'}** · "
                             f"таймаут: **{'да' if d['timed_out'] else 'нет'}**")
            return await interaction.followup.send(embed=e, ephemeral=not public)

        buf = await __import__('asyncio').to_thread(render_case_card, d, avatar_img)
        await interaction.followup.send(
            file=discord.File(buf, filename=f'case_{uid}.png'), ephemeral=not public)
        log.info(f'[case] {interaction.user} запросил досье {user} ({uid})')


async def setup(bot):
    await bot.add_cog(ModCase(bot))
