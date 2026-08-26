# -*- coding: utf-8 -*-
"""Гейт доступа по правилам: кнопка «Согласен с правилами».

Под публикацией правил (вебхук V2 или эмбеды) бот ставит короткое
сообщение с зелёной кнопкой. Участник читает правила, жмёт — бот
выдаёт роль (по умолчанию «Участник», настраивается в панели), и
каналы, открытые этой роли, становятся видны.

Права каналов настраивает админ Discord: у @everyone закрыть
«Просмотр канала», роли — разрешить. Бот каналы сам не перекраивает.

Кнопка персистентная (custom_id GATE_BUTTON_ID) — переживает
перезапуск бота: вью регистрируется в main.py через register(bot).
"""
import json
import os

from logger import get_logger

_log = get_logger('rules_gate')

import discord
import discord.ui as ui
from discord import SeparatorSpacing

GATE_BUTTON_ID = 'aether_rules_gate'
DEFAULT_ROLE_NAME = 'Участник'


# ── конфиг в data/rules_meta_<gid>.json ─────────────────────────────
def _meta_path(guild_id) -> str:
    return f'data/rules_meta_{guild_id}.json'


def load_gate_config(guild_id) -> dict:
    try:
        with open(_meta_path(guild_id), encoding='utf-8') as f:
            m = json.load(f)
        return {'role_id': str(m.get('gate_role_id') or ''),
                'enabled': bool(m.get('gate_enabled'))}
    except Exception:
        return {'role_id': '', 'enabled': False}


def save_gate_config(guild_id, role_id: str = '', enabled: bool = False) -> None:
    path = _meta_path(guild_id)
    meta = {}
    try:
        with open(path, encoding='utf-8') as f:
            meta = json.load(f)
        if not isinstance(meta, dict):
            meta = {}
    except Exception:
        meta = {}
    meta['gate_enabled'] = bool(enabled)
    meta['gate_role_id'] = str(role_id or '')
    os.makedirs('data', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


# ── роль за согласие ────────────────────────────────────────────────
async def ensure_gate_role(guild, role_id: str = ''):
    """Найти роль по id (или имени «Участник»); нет — создать."""
    if role_id and str(role_id).isdigit():
        role = guild.get_role(int(role_id))
        if role is not None:
            return role
    role = discord.utils.get(guild.roles, name=DEFAULT_ROLE_NAME)
    if role is not None:
        return role
    me = getattr(guild, 'me', None)
    if me is not None and me.guild_permissions.manage_roles:
        try:
            role = await guild.create_role(name=DEFAULT_ROLE_NAME,
                                           reason='Гейт правил Aether')
            print(f"[ПРАВИЛА] Создана роль «{DEFAULT_ROLE_NAME}» для гейта")
            return role
        except Exception as ex:
            _log.warning("ensure_gate_role(): создать роль не вышло: %s", ex)
    return None


# ── нажатие кнопки ──────────────────────────────────────────────────
async def handle_gate(interaction) -> None:
    cfg = load_gate_config(interaction.guild_id)
    role = await ensure_gate_role(interaction.guild, cfg.get('role_id', ''))
    member = interaction.user
    if role is None:
        await interaction.response.send_message(
            '❌ Роль доступа не найдена: попросите админа создать роль '
            f'«{DEFAULT_ROLE_NAME}» или выдать боту право «Управлять ролями».',
            ephemeral=True)
        return
    if role in getattr(member, 'roles', []):
        await interaction.response.send_message(
            '✅ Вы уже согласились с правилами — доступ открыт.',
            ephemeral=True)
        return
    try:
        await member.add_roles(role, reason='Согласие с правилами (кнопка)')
    except Exception as ex:
        _log.warning("handle_gate(): выдать роль не вышло: %s", ex)
        await interaction.response.send_message(
            '❌ Не получилось выдать роль: она выше роли бота? '
            'Попросите админа проверить права.',
            ephemeral=True)
        return
    print(f"[ПРАВИЛА] {member} согласился с правилами — роль «{role.name}»")
    await interaction.response.send_message(
        f'✅ Правила приняты — добро пожаловать! Роль «{role.name}» выдана.',
        ephemeral=True)


class RulesGateView(ui.View):
    """Классическая вьюха-фолбек с той же кнопкой (custom_id общий)."""

    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label='Согласен с правилами', emoji='✅',
               style=discord.ButtonStyle.success, custom_id=GATE_BUTTON_ID)
    async def agree(self, interaction, button):
        await handle_gate(interaction)


def gate_layout() -> 'ui.LayoutView':
    """V2-макет сообщения-гейта: текст + зелёная кнопка."""
    view = ui.LayoutView(timeout=None)
    view.add_item(ui.Container(
        ui.TextDisplay('## Доступ к серверу\n'
                       'Прочитайте правила выше и подтвердите согласие — '
                       'каналы сервера откроются.'),
        ui.Separator(spacing=SeparatorSpacing.large),
        ui.ActionRow(ui.Button(label='Согласен с правилами', emoji='✅',
                               style=discord.ButtonStyle.success,
                               custom_id=GATE_BUTTON_ID)),
        accent_colour=discord.Colour(0x22C55E),
    ))
    return view


def gate_embed() -> discord.Embed:
    return discord.Embed(
        title='Доступ к серверу',
        description='Прочитайте правила выше и подтвердите согласие — '
                    'каналы сервера откроются.',
        colour=0x22C55E)


async def send_gate_message(channel) -> None:
    """Поставить сообщение с кнопкой согласия (V2, фолбек — эмбед)."""
    from services.v2_layouts import send_v2_or_embed
    await send_v2_or_embed(channel, view=gate_layout(), embed=gate_embed(),
                           fallback_view=RulesGateView())


# ── регистрация персистентной вью ───────────────────────────────────
_registered = False


def register(bot) -> None:
    """Зарегистрировать кнопку (один раз за жизнь процесса).

    Персистентная вью диспатчится по custom_id — закрывает и кнопку
    в V2-макетах, и в классическом фолбеке."""
    global _registered
    if _registered:
        return
    bot.add_view(RulesGateView())
    _registered = True
    print('[ПРАВИЛА] Гейт-кнопка «Согласен с правилами» зарегистрирована')
