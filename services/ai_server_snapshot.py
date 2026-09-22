# -*- coding: utf-8 -*-
"""Полный «досье» сервера для Discord AI-чата.

Чтобы ИИ не отвечал «не знаю» про сервер: каналы, роли, правила,
онлайн, войсы, варны, automod/antiraid, свежая модерация.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from logger import get_logger

_log = get_logger('ai_server_snapshot')


def _read_json(path: str, default=None):
    try:
        if os.path.isfile(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as ex:
        _log.debug('read %s: %s', path, ex)
    return default if default is not None else {}


def _rules_list(guild_id: int) -> list[str]:
    for rf in (f'data/rules_{guild_id}.json', 'data/rules.json'):
        data = _read_json(rf, None)
        if not isinstance(data, dict):
            continue
        out = []
        for rule in data.get('rules') or []:
            text = (rule.get('text') or rule.get('title') or '').strip()
            if text:
                out.append(text[:400])
        if out:
            return out[:20]
    return [
        'Правило #1: Уважение — без оскорблений, мата и языка вражды.',
        'Правило #2: Без спама, флуда и рекламы без разрешения.',
        'Правило #3: В голосовых — не мешать другим.',
        'Правило #4: Решения модерации обжалуются через тикеты.',
        'Правило #5: Не распространять личные данные и вредоносные ссылки.',
    ]


def _config_summary(guild_id: int) -> list[str]:
    lines = []
    auto = _read_json(f'data/automod_{guild_id}.json', {})
    if isinstance(auto, dict) and auto:
        enabled = [k for k, v in auto.items()
                   if isinstance(v, (bool, int)) and v and k not in ('guild_id',)]
        lines.append('Automod: ' + (', '.join(enabled[:12]) or 'файл есть, флаги выкл'))
    raid = _read_json(f'data/antiraid_{guild_id}.json', {})
    if isinstance(raid, dict) and raid:
        on = raid.get('enabled', raid.get('on'))
        lines.append(f"Anti-raid: {'вкл' if on else 'выкл/не задано'}")
    warn = _read_json(f'data/warn_config_{guild_id}.json', {})
    if isinstance(warn, dict) and warn:
        thr = warn.get('thresholds') or warn.get('limits') or warn
        if isinstance(thr, dict):
            bits = [f'{k}={v}' for k, v in list(thr.items())[:8]]
            if bits:
                lines.append('Лимиты варнов: ' + ', '.join(bits))
    return lines


def _warn_stats(guild_id: int) -> str:
    wd = _read_json('data/warnings.json', {})
    gw = wd.get(str(guild_id), {}) if isinstance(wd, dict) else {}
    if not isinstance(gw, dict):
        return ''
    total = sum(len(v) if isinstance(v, list) else 0 for v in gw.values())
    return f'Всего активных записей предупреждений: {total}'


def _mod_week(guild_id: int) -> list[str]:
    try:
        from web.routes.analytics_plus import _read_audit, _parse_ts
    except Exception:
        return []
    try:
        cutoff = datetime.now() - timedelta(days=7)
        per_mod: dict[str, int] = {}
        total = 0
        for ev in _read_audit(guild_id) or []:
            if ev.get('category') != 'mod':
                continue
            ts = _parse_ts(ev.get('timestamp'))
            if ts is None or ts < cutoff:
                continue
            total += 1
            mn = str(ev.get('mod_name') or '').strip()
            if mn:
                per_mod[mn] = per_mod.get(mn, 0) + 1
        lines = [f'Мод-действий за 7 дней: {total}']
        for mn, cnt in sorted(per_mod.items(), key=lambda kv: kv[1], reverse=True)[:8]:
            lines.append(f'  {mn}: {cnt}')
        return lines
    except Exception as ex:
        _log.debug('mod_week: %s', ex)
        return []


def find_mentioned_members(guild, question: str, limit: int = 5) -> list[str]:
    """Имена из вопроса → кто это на сервере (display/name)."""
    if not guild or not question:
        return []
    q = question.lower()
    hits = []
    try:
        for m in guild.members:
            if m.bot:
                continue
            names = {m.display_name.lower(), m.name.lower()}
            if m.global_name:
                names.add(str(m.global_name).lower())
            for n in names:
                if len(n) >= 3 and n in q:
                    roles = [r.name for r in m.roles if not r.is_default()][:5]
                    hits.append(
                        f'{m.display_name} (id={m.id}, роли: {", ".join(roles) or "нет"})')
                    break
            if len(hits) >= limit:
                break
    except Exception as ex:
        _log.debug('find_mentioned_members: %s', ex)
    return hits


def build_server_dossier(guild) -> dict[str, Any]:
    """Собрать живой слепок гильдии для промпта."""
    if guild is None:
        return {}
    gid = int(guild.id)
    dossier: dict[str, Any] = {
        'guild_id': gid,
        'guild_name': guild.name,
        'member_count': getattr(guild, 'member_count', None) or len(guild.members),
    }
    try:
        if guild.owner:
            dossier['guild_owner'] = guild.owner.display_name
    except Exception:
        pass

    # Каналы с категориями и id
    ch_lines = []
    try:
        for cat in guild.categories:
            ch_lines.append(f'Категория «{cat.name}»')
            for c in cat.text_channels[:15]:
                ch_lines.append(f'  #{c.name} (id={c.id})')
            for c in cat.voice_channels[:10]:
                ch_lines.append(f'  🔊 {c.name} (id={c.id})')
        orphans_t = [c for c in guild.text_channels if c.category is None][:20]
        orphans_v = [c for c in guild.voice_channels if c.category is None][:10]
        for c in orphans_t:
            ch_lines.append(f'#{c.name} (id={c.id})')
        for c in orphans_v:
            ch_lines.append(f'🔊 {c.name} (id={c.id})')
    except Exception as ex:
        _log.debug('channels: %s', ex)
    dossier['channel_map'] = ch_lines[:60]

    # Роли
    try:
        dossier['roles'] = [
            f'{r.name} (id={r.id})' for r in sorted(
                (r for r in guild.roles if not r.is_default() and not r.managed),
                key=lambda r: r.position, reverse=True)][:40]
    except Exception:
        dossier['roles'] = []

    # Staff
    staff = []
    try:
        for role in guild.roles:
            if role.is_default():
                continue
            if (role.permissions.administrator or role.permissions.kick_members
                    or role.permissions.manage_messages):
                members = [m.display_name for m in role.members if not m.bot][:6]
                if members:
                    staff.append({'name': role.name, 'members': members})
    except Exception:
        pass
    dossier['staff_roles'] = staff[:10]

    # Live status
    try:
        import discord
        online = [m for m in guild.members
                  if not m.bot and m.status != discord.Status.offline]
        in_voice = []
        voice_detail = []
        for vc in guild.voice_channels:
            names = [m.display_name for m in vc.members if not m.bot]
            if names:
                voice_detail.append(f'{vc.name}: {", ".join(names[:8])}')
                in_voice.extend(names)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_joins = [
            m.display_name for m in guild.members
            if (not m.bot and m.joined_at and m.joined_at > cutoff)][:8]
        tickets = [c for c in guild.text_channels if c.name.startswith('ticket-')]
        dossier['server_status'] = {
            'online_count': len(online),
            'online_sample': [m.display_name for m in online[:15]],
            'voice_count': len(in_voice),
            'voice_detail': voice_detail[:10],
            'recent_joins': recent_joins,
            'active_tickets': len(tickets),
            'total_members': dossier['member_count'],
        }
    except Exception as ex:
        _log.debug('status: %s', ex)

    dossier['rules'] = _rules_list(gid)
    dossier['configs'] = _config_summary(gid)
    dossier['warn_stats'] = _warn_stats(gid)
    dossier['mod_week'] = _mod_week(gid)
    return dossier


def dossier_to_prompt_lines(dossier: dict) -> list[str]:
    """Сжать досье в строки system-prompt."""
    if not dossier:
        return []
    lines = [
        '=== ЖИВОЕ ДОСЬЕ СЕРВЕРА (единственный источник фактов о сервере) ===',
        f"Сервер: {dossier.get('guild_name')} (id={dossier.get('guild_id')})",
    ]
    if dossier.get('guild_owner'):
        lines.append(f"Владелец: {dossier['guild_owner']}")
    if dossier.get('member_count') is not None:
        lines.append(f"Участников: {dossier['member_count']}")

    st = dossier.get('server_status') or {}
    if st:
        lines.append(
            f"Сейчас: {st.get('online_count', 0)} в сети, "
            f"{st.get('voice_count', 0)} в голосовых, "
            f"тикетов: {st.get('active_tickets', 0)}.")
        if st.get('online_sample'):
            lines.append('В сети (фрагмент): ' + ', '.join(st['online_sample']))
        if st.get('voice_detail'):
            lines.append('Голосовые: ' + ' | '.join(st['voice_detail']))
        if st.get('recent_joins'):
            lines.append('Зашли за 24ч: ' + ', '.join(st['recent_joins']))

    if dossier.get('channel_map'):
        lines.append('Карта каналов:\n  ' + '\n  '.join(dossier['channel_map'][:50]))
    if dossier.get('roles'):
        lines.append('Роли: ' + ', '.join(dossier['roles'][:35]))
    if dossier.get('staff_roles'):
        bits = [
            f"{r.get('name')}: {', '.join(r.get('members') or [])}"
            for r in dossier['staff_roles'][:8]]
        lines.append('Команда (роль — люди): ' + '; '.join(bits))
    if dossier.get('rules'):
        lines.append('ПРАВИЛА СЕРВЕРА (всегда учитывай):\n  ' +
                     '\n  '.join(dossier['rules'][:15]))
    if dossier.get('configs'):
        lines.append('Настройки защиты: ' + '; '.join(dossier['configs']))
    if dossier.get('warn_stats'):
        lines.append(dossier['warn_stats'])
    if dossier.get('mod_week'):
        lines.append('Модерация:\n  ' + '\n  '.join(dossier['mod_week']))
    if dossier.get('mentioned_members'):
        lines.append('Упомянутые в вопросе участники:\n  ' +
                     '\n  '.join(dossier['mentioned_members']))
    lines.append(
        'Факты о сервере бери ТОЛЬКО из этого досье и хроники ниже. '
        'Если чего-то нет в досье — так и скажи, не выдумывай.')
    return lines
