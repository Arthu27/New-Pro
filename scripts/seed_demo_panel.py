# -*- coding: utf-8 -*-
"""Посев демо-данных для живой демонстрации панели (guild 777).

Пишет только в data/ (gitignored). Удалить демо-данные: rm файлы ниже
или запустить reset_server_data.py.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

os.makedirs('data', exist_ok=True)

NOW = datetime.now(timezone.utc)


def iso(days_ago=0, hour=12, minute=0):
    dt = NOW - timedelta(days=days_ago)
    dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return dt.isoformat()


def iso_recent(minutes_ago=0):
    """Свежая UTC-метка «N минут назад» — чтобы «Модерация сегодня» была живой
    в любом часовом поясе владельца (не уезжала на завтра)."""
    return (NOW - timedelta(minutes=minutes_ago)).isoformat()


GID = '987654321098765432'

# ── 1. Варны ─────────────────────────────────────────────────────────────
warnings = {
    GID: {
        '523456789012345678': [
            {'reason': 'Оскорбления участников в общем чате', 'moderator': 'artem.mods', 'timestamp': iso(6, 18, 40)},
            {'reason': 'Разжигание конфликта после предупреждения', 'moderator': 'sonya.staff', 'timestamp': iso(2, 21, 15)},
        ],
        '723456789012345679': [
            {'reason': 'Спам ссылками на сторонний сервер', 'moderator': 'artem.mods', 'timestamp': iso(5, 15, 5)},
            {'reason': 'Массовые упоминания в неположенном канале', 'moderator': 'sonya.staff', 'timestamp': iso_recent(38)},
        ],
        '823456789012345680': [
            {'reason': 'Токсичность в голосовом чате', 'moderator': 'lina.mod', 'timestamp': iso(12, 11, 30)},
            {'reason': 'Оскорбления в адрес модерации', 'moderator': 'artem.mods', 'timestamp': iso(8, 19, 50)},
            {'reason': 'Реклама в личных сообщениях', 'moderator': 'sonya.staff', 'timestamp': iso(4, 13, 20)},
            {'reason': 'Обход мьюта вторым аккаунтом', 'moderator': 'lina.mod', 'timestamp': iso(1, 22, 45)},
        ],
        '923456789012345681': [
            {'reason': 'Неуважение к правилам сервера', 'moderator': 'artem.mods', 'timestamp': iso(3, 17, 10)},
        ],
        '623456789012345678': [
            {'reason': 'Массовые упоминания модераторов', 'moderator': 'sonya.staff', 'timestamp': iso(1, 9, 55)},
        ],
    }
}

# ── 2. Журнал модерации (audit) ─────────────────────────────────────────
A = lambda **kw: dict(category='mod', **kw)  # noqa: E731
audit = {
    GID: [
        A(action='ban', user_name='toxicguy', mod_name='lina.mod',
          reason='Неоднократные оскорбления после бана', timestamp=iso_recent(7)),
        A(action='mute', user_name='spammer_228', mod_name='artem.mods',
          reason='Флуд в общем чате', timestamp=iso_recent(26)),
        A(action='warn', user_name='newbie_gg', mod_name='sonya.staff',
          reason='Реклама в профиле', timestamp=iso_recent(48)),
        A(action='kick', user_name='alt_account1', mod_name='lina.mod',
          reason='Подозрение на обход мьюта', timestamp=iso_recent(71)),
        A(action='timeout', user_name='loud_voice', mod_name='lina.mod',
          reason='Микрофон-спам в голосовом чате', timestamp=iso_recent(133)),
        A(action='unmute', user_name='caps_forever', mod_name='artem.mods',
          reason='Таймаут истёк — доступ возвращён', timestamp=iso_recent(182)),
        A(action='mute', user_name='caps_forever', mod_name='artem.mods',
          reason='Анти-капс: сплошной капс в новостях', timestamp=iso(1, 21, 15)),
        A(action='unban', user_name='toxicguy', mod_name='lina.mod',
          reason='Апелляция принята — испытательный срок', timestamp=iso(1, 20, 30)),
        A(action='ban', user_name='raid_bot', mod_name='artem.mods',
          reason='Рейд-волна: массовый вход ботов', timestamp=iso(1, 19, 5)),
        A(action='warn', user_name='toxicguy', mod_name='sonya.staff',
          reason='Повторное нарушение после апелляции', timestamp=iso(2, 17, 45)),
        A(action='timeout', user_name='loud_voice', mod_name='lina.mod',
          reason='Музыка поверх голосового чата', timestamp=iso(2, 16, 20)),
        A(action='kick', user_name='nsfw_poster', mod_name='artem.mods',
          reason='Контент 18+ в общих каналах', timestamp=iso(3, 23, 10)),
        A(action='mute', user_name='ping_spammer', mod_name='sonya.staff',
          reason='Массовые пинги модерации', timestamp=iso(3, 14, 0)),
        A(action='warn', user_name='invite_hunter', mod_name='lina.mod',
          reason='Приглашения на сторонние серверы', timestamp=iso(4, 19, 35)),
        A(action='ban', user_name='scam_links', mod_name='artem.mods',
          reason='Фишинговые ссылки в ЛС', timestamp=iso(4, 12, 50)),
        A(action='unmute', user_name='caps_forever', mod_name='artem.mods',
          reason='Срок мьюта истёк', timestamp=iso(5, 10, 0)),
        A(action='mute', user_name='voice_troll', mod_name='sonya.staff',
          reason='Звуковые эффекты в голосовом чате', timestamp=iso(5, 21, 40)),
        A(action='warn', user_name='spammer_228', mod_name='lina.mod',
          reason='Спам реакциями', timestamp=iso(6, 15, 25)),
        A(action='kick', user_name='dehoisted', mod_name='artem.mods',
          reason='Ник со спецсимволами для обхода списка', timestamp=iso(6, 13, 5)),
        A(action='ban', user_name='toxicguy', mod_name='lina.mod',
          reason='Первое нарушение после испытательного срока', timestamp=iso(7, 20, 15)),
        A(action='warn', user_name='loud_voice', mod_name='sonya.staff',
          reason='Повтор: музыка в голосовом чате', timestamp=iso(7, 18, 0)),
        A(action='timeout', user_name='nsfw_poster', mod_name='artem.mods',
          reason='Повторный контент 18+', timestamp=iso(7, 12, 45)),
        # Волна событий для живых графиков (теплокарта, ритм по дням)
        A(action='warn', user_name='emoji_spam', mod_name='lina.mod',
          reason='Флуд эмодзи в обсуждениях', timestamp=iso(0, 1, 20)),
        A(action='mute', user_name='night_flooder', mod_name='sonya.staff',
          reason='Ночной флуд в чатах', timestamp=iso(0, 3, 45)),
        A(action='kick', user_name='sleeper_alt', mod_name='artem.mods',
          reason='Спящий аккаунт с рекламой в профиле', timestamp=iso(0, 7, 15)),
        A(action='warn', user_name='tag_abuser', mod_name='lina.mod',
          reason='Тег 18+ в нике (Tag Jail)', timestamp=iso(0, 11, 30)),
        A(action='mute', user_name='voice_raider', mod_name='sonya.staff',
          reason='Захват голосового канала', timestamp=iso(0, 14, 5)),
        A(action='timeout', user_name='emoji_spam', mod_name='artem.mods',
          reason='Повторный флуд эмодзи', timestamp=iso(0, 17, 55)),
        A(action='ban', user_name='raid_alt_2', mod_name='lina.mod',
          reason='Участник рейд-волны', timestamp=iso(1, 0, 40)),
        A(action='warn', user_name='offtopic_king', mod_name='sonya.staff',
          reason='Офтоп в новостном канале', timestamp=iso(1, 6, 10)),
        A(action='mute', user_name='ping_chain', mod_name='artem.mods',
          reason='Цепочка пингов всей модерации', timestamp=iso(1, 9, 25)),
        A(action='kick', user_name='nsfw_alt', mod_name='lina.mod',
          reason='Обход бана вторым аккаунтом', timestamp=iso(1, 13, 50)),
        A(action='warn', user_name='spoiler_man', mod_name='sonya.staff',
          reason='Спойлеры без тега в киночате', timestamp=iso(1, 16, 35)),
        A(action='mute', user_name='music_abuser', mod_name='artem.mods',
          reason='Громкость бота на максимум', timestamp=iso(1, 21, 5)),
        A(action='unban', user_name='raid_alt_2', mod_name='lina.mod',
          reason='Апелляция: ложное срабатывание анти-рейда', timestamp=iso(2, 2, 30)),
        A(action='warn', user_name='caps_forever', mod_name='sonya.staff',
          reason='Снова капс в чате', timestamp=iso(2, 8, 45)),
        A(action='timeout', user_name='night_flooder', mod_name='artem.mods',
          reason='Флуд продолжается ночью', timestamp=iso(2, 15, 20)),
        A(action='kick', user_name='scam_buyer', mod_name='lina.mod',
          reason='Покупка аккаунтов на сервере', timestamp=iso(2, 19, 10)),
        A(action='warn', user_name='dehoisted', mod_name='sonya.staff',
          reason='Снова спецсимволы в нике', timestamp=iso(3, 4, 55)),
        A(action='mute', user_name='voice_raider', mod_name='artem.mods',
          reason='Повторный захват войса', timestamp=iso(3, 10, 15)),
        A(action='ban', user_name='phish_king', mod_name='lina.mod',
          reason='Фишинговая рассылка в ЛС', timestamp=iso(3, 18, 40)),
        A(action='warn', user_name='newbie_gg', mod_name='sonya.staff',
          reason='Реклама в статусе профиля', timestamp=iso(4, 5, 25)),
        A(action='kick', user_name='alt_account1', mod_name='artem.mods',
          reason='Подтверждён обход мьюта', timestamp=iso(4, 12, 0)),
        A(action='mute', user_name='ping_spammer', mod_name='lina.mod',
          reason='Пинги в нерабочее время', timestamp=iso(4, 20, 35)),
        A(action='warn', user_name='invite_hunter', mod_name='sonya.staff',
          reason='Массовые приглашения', timestamp=iso(5, 2, 50)),
        A(action='timeout', user_name='emoji_spam', mod_name='artem.mods',
          reason='Третий заход с эмодзи', timestamp=iso(5, 9, 5)),
        A(action='ban', user_name='spammer_228', mod_name='lina.mod',
          reason='Исчерпан лимит предупреждений', timestamp=iso(5, 16, 45)),
        A(action='warn', user_name='offtopic_king', mod_name='sonya.staff',
          reason='Офтоп в правилах', timestamp=iso(6, 7, 30)),
        A(action='kick', user_name='sleeper_alt', mod_name='artem.mods',
          reason='Повторная регистрация', timestamp=iso(6, 14, 15)),
        A(action='mute', user_name='music_abuser', mod_name='lina.mod',
          reason='Музыка в голосовом во время собрания', timestamp=iso(6, 22, 40)),
    ]
}

# ── 3. История решений (mod_data) ───────────────────────────────────────
mod_data = {'case': {GID: [
    {'user_id': '823456789012345680', 'mod_id': 'lina.mod', 'action': 'mute',
     'reason': 'Обход мьюта вторым аккаунтом', 'duration_minutes': 720, 'timestamp': iso(1, 22, 45)},
    {'user_id': '523456789012345678', 'mod_id': 'sonya.staff', 'action': 'warn',
     'reason': 'Разжигание конфликта после предупреждения', 'timestamp': iso(2, 21, 15)},
    {'user_id': '723456789012345679', 'mod_id': 'artem.mods', 'action': 'mute',
     'reason': 'Спам ссылками на сторонний сервер', 'duration_minutes': 120, 'timestamp': iso(5, 15, 5)},
    {'user_id': '823456789012345680', 'mod_id': 'artem.mods', 'action': 'warn',
     'reason': 'Оскорбления в адрес модерации', 'timestamp': iso(8, 19, 50)},
]}}

# ── 3b. Исторические события за 90 дней (для календаря активности) ───────
import random as _rnd
_rnd.seed(777)
HIST_USERS = ['toxicguy', 'spammer_228', 'caps_forever', 'voice_troll', 'night_flooder',
              'emoji_spam', 'invite_hunter', 'offtopic_king', 'nsfw_poster', 'ping_spammer',
              'dehoisted', 'music_abuser', 'scam_links', 'sleeper_alt', 'tag_abuser']
HIST_MODS = ['artem.mods', 'sonya.staff', 'lina.mod']
HIST_ACTIONS = [('warn', 'Нарушение правил чата', 34), ('mute', 'Флуд в общем канале', 22),
                ('timeout', 'Спам в течение часа', 9), ('kick', 'Повторное нарушение', 13),
                ('ban', 'Систематические нарушения', 8), ('unmute', 'Срок мьюта истёк', 5),
                ('unban', 'Апелляция принята', 3)]
# веса через повторение
HIST_POOL = []
for act, reason, weight in HIST_ACTIONS:
    HIST_POOL += [(act, reason)] * weight

hist = []
for days_ago in range(89, 7, -1):
    d = NOW - timedelta(days=days_ago)
    wd = d.weekday()  # 0=пн
    if wd >= 5:  # выходные — спокойнее
        n = _rnd.choices([0, 1, 2, 3], weights=[30, 40, 22, 8])[0]
    else:
        n = _rnd.choices([0, 1, 2, 3, 4], weights=[16, 30, 30, 16, 8])[0]
    for _ in range(n):
        act, reason = _rnd.choice(HIST_POOL)
        hour = _rnd.choices([10, 12, 14, 16, 18, 19, 20, 21, 22, 23], weights=[5, 6, 8, 10, 12, 14, 13, 10, 8, 5])[0]
        minute = _rnd.randint(0, 59)
        dt = d.replace(hour=hour, minute=minute, second=0, microsecond=0)
        hist.append(A(action=act, user_name=_rnd.choice(HIST_USERS),
                      mod_name=_rnd.choice(HIST_MODS), reason=reason,
                      timestamp=dt.isoformat()))

audit[GID] = hist + audit[GID]
# ── 4. Доказательства (демки) ───────────────────────────────────────────
proofs = {'next': 6, 'items': {
    '1': {'id': 1, 'user_id': 823456789012345680, 'user_name': 'toxicguy',
          'mod_name': 'lina.mod', 'action': 'бан',
          'reason': 'Скриншот оскорблений в чате',
          'link': 'https://discord.com/channels/777/112233/445566',
          'url': '', 'set_at': iso(0, 22, 10)},
    '2': {'id': 2, 'user_id': 523456789012345678, 'user_name': 'spammer_228',
          'mod_name': 'artem.mods', 'action': 'мут',
          'reason': 'Видео с флудом в общем чате',
          'link': 'https://discord.com/channels/777/112233/445567',
          'url': '', 'set_at': iso(0, 20, 5)},
    '3': {'id': 3, 'user_id': 923456789012345681, 'user_name': 'newbie_gg',
          'mod_name': 'sonya.staff', 'action': 'варн',
          'reason': 'Реклама в профиле — скриншот',
          'link': '', 'url': '', 'set_at': iso(0, 18, 40)},
    '4': {'id': 4, 'user_id': 623456789012345678, 'user_name': 'alt_account1',
          'mod_name': 'lina.mod', 'action': 'кик',
          'reason': 'Совпадение IP с заблокированным аккаунтом',
          'link': 'https://discord.com/channels/777/112233/445568',
          'url': '', 'set_at': iso(0, 12, 25)},
    '5': {'id': 5, 'user_id': 823456789012345680, 'user_name': 'toxicguy',
          'mod_name': 'artem.mods', 'action': 'тихий мут',
          'reason': 'Попытки продолжить флуд — журнал ghost-контура',
          'link': '', 'url': '', 'set_at': iso(2, 17, 45)},
}}

# ── 5. Пороги авто-наказаний ────────────────────────────────────────────
warn_config = {'steps': [
    {'count': 3, 'action': 'mute', 'duration': 1, 'unit': 'hour'},
    {'count': 5, 'action': 'kick'},
    {'count': 7, 'action': 'ban'},
]}

# ── 6. Логи входа в панель ──────────────────────────────────────────────
login_log = [
    {'username': 'artem.mods', 'role': 'mod', 'avatar': '', 'discord_id': '111111111111111111',
     'timestamp': iso(0, 9, 5)},
    {'username': 'sonya.staff', 'role': 'admin', 'avatar': '', 'discord_id': '222222222222222222',
     'timestamp': iso(0, 11, 30)},
    {'username': 'lina.mod', 'role': 'mod', 'avatar': '', 'discord_id': '333333333333333333',
     'timestamp': iso(1, 10, 12)},
    {'username': 'artem.mods', 'role': 'mod', 'avatar': '', 'discord_id': '111111111111111111',
     'timestamp': iso(1, 20, 45)},
    {'username': 'max.admin', 'role': 'admin', 'avatar': '', 'discord_id': '444444444444444444',
     'timestamp': iso(2, 14, 20)},
    {'username': 'lina.mod', 'role': 'mod', 'avatar': '', 'discord_id': '333333333333333333',
     'timestamp': iso(3, 9, 55)},
]

# ── 7. Лента активности панели (broadcast) ──────────────────────────────
panel_logs = [
    {'username': 'system', 'role': 'owner', 'action': 'Бэкап создан',
     'detail': 'Ежедневный архив данных — 14 МБ', 'ts': int(NOW.timestamp()) - 3600 * 4, 'broadcast': True},
    {'username': 'system', 'role': 'owner', 'action': 'Обновление политики',
     'detail': 'Автофильтр: добавлены 3 слова в чёрный список', 'ts': int(NOW.timestamp()) - 3600 * 26, 'broadcast': True},
    {'username': 'system', 'role': 'owner', 'action': 'Рейд-тревога',
     'detail': 'Анти-рейд: волна из 9 входов за 10 секунд', 'ts': int(NOW.timestamp()) - 3600 * 49, 'broadcast': True},
    {'username': 'system', 'role': 'owner', 'action': 'Апелляция решена',
     'detail': 'Апелляция #12 принята модератором lina.mod', 'ts': int(NOW.timestamp()) - 3600 * 72, 'broadcast': True},
]

# ── 8. Канбан-доска команды ─────────────────────────────────────────────
team_board = {'next_id': 6, 'tasks': {
    '1': {'id': 1, 'title': 'Разобрать апелляцию toxicguy — запросить контекст у lina.mod',
          'status': 'doing', 'priority': 'urgent', 'assignee': 'artem.mods',
          'due': 'до 19.08', 'note': 'Есть скриншоты в доказательствах #5.',
          'author': 'lina.mod', 'created': '2026-08-16 14:20', 'updated': '2026-08-18 09:10', 'order': 0},
    '2': {'id': 2, 'title': 'Обновить чёрный список автофильтра (новый спам-домен)',
          'status': 'doing', 'priority': 'high', 'assignee': 'sonya.staff',
          'due': '', 'note': 'Домен видели в трёх тикетах за сутки.',
          'author': 'artem.mods', 'created': '2026-08-17 11:05', 'updated': '2026-08-18 08:40', 'order': 1},
    '3': {'id': 3, 'title': 'Проверить волну входов с 17.08 — отчёт по анти-рейду',
          'status': 'todo', 'priority': 'mid', 'assignee': 'artem.mods',
          'due': 'до 21.08', 'note': '12 входов за 2 минуты, возможно фолс-позитив.',
          'author': 'sonya.staff', 'created': '2026-08-17 22:30', 'updated': '2026-08-17 22:30', 'order': 0},
    '4': {'id': 4, 'title': 'Созвониться по правилам войса — обсудить музыку в чатах',
          'status': 'todo', 'priority': 'low', 'assignee': 'lina.mod',
          'due': '', 'note': '',
          'author': 'artem.mods', 'created': '2026-08-18 09:00', 'updated': '2026-08-18 09:00', 'order': 1},
    '5': {'id': 5, 'title': 'Проверить тикеты без ответа старше 24 часов',
          'status': 'done', 'priority': 'high', 'assignee': 'sonya.staff',
          'due': 'до 18.08', 'note': 'Закрыто: 3 тикета отвечены, 1 эскалирован.',
          'author': 'lina.mod', 'created': '2026-08-17 12:15', 'updated': '2026-08-18 10:20', 'order': 0},
}}


# ── Демо-каналы: аккуратная структура с категориями и порядком ────────────
demo_channels = [
    {'id': '1001', 'name': 'Информация', 'type': 'category', 'position': 0,
     'category': None, 'category_id': None, 'category_pos': -1,
     'topic': '', 'nsfw': False, 'slowmode': 0, 'bitrate': 0, 'user_limit': 0,
     'news': False, 'stage': False, 'forum': False, 'connected': 0,
     'created_at': '2025-11-02T10:00:00+00:00', 'mention': ''},
    {'id': '1002', 'name': 'announcements', 'type': 'text', 'position': 0,
     'category': 'Информация', 'category_id': '1001', 'category_pos': 0,
     'topic': 'Новости сервера, анонсы ивентов и обновления бота',
     'nsfw': False, 'slowmode': 10, 'bitrate': 0, 'user_limit': 0,
     'news': True, 'stage': False, 'forum': False, 'connected': 0,
     'created_at': '2025-11-02T10:05:00+00:00', 'mention': ''},
    {'id': '1003', 'name': 'rules', 'type': 'text', 'position': 1,
     'category': 'Информация', 'category_id': '1001', 'category_pos': 0,
     'topic': 'Правила сервера — обязательны к прочтению',
     'nsfw': False, 'slowmode': 0, 'bitrate': 0, 'user_limit': 0,
     'news': False, 'stage': False, 'forum': False, 'connected': 0,
     'created_at': '2025-11-02T10:06:00+00:00', 'mention': ''},
    {'id': '1004', 'name': 'updates', 'type': 'text', 'position': 2,
     'category': 'Информация', 'category_id': '1001', 'category_pos': 0,
     'topic': 'Что изменилось в панели и на сервере',
     'nsfw': False, 'slowmode': 0, 'bitrate': 0, 'user_limit': 0,
     'news': False, 'stage': False, 'forum': False, 'connected': 0,
     'created_at': '2025-12-15T12:00:00+00:00', 'mention': ''},
    {'id': '2001', 'name': 'Общение', 'type': 'category', 'position': 1,
     'category': None, 'category_id': None, 'category_pos': -1,
     'topic': '', 'nsfw': False, 'slowmode': 0, 'bitrate': 0, 'user_limit': 0,
     'news': False, 'stage': False, 'forum': False, 'connected': 0,
     'created_at': '2025-11-02T10:10:00+00:00', 'mention': ''},
    {'id': '2002', 'name': 'general', 'type': 'text', 'position': 0,
     'category': 'Общение', 'category_id': '2001', 'category_pos': 1,
     'topic': 'Основной чат сервера — обо всём',
     'nsfw': False, 'slowmode': 0, 'bitrate': 0, 'user_limit': 0,
     'news': False, 'stage': False, 'forum': False, 'connected': 0,
     'created_at': '2025-11-02T10:11:00+00:00', 'mention': ''},
    {'id': '2003', 'name': 'memes', 'type': 'text', 'position': 1,
     'category': 'Общение', 'category_id': '2001', 'category_pos': 1,
     'topic': 'Мемы и картинки — без оскорблений',
     'nsfw': False, 'slowmode': 0, 'bitrate': 0, 'user_limit': 0,
     'news': False, 'stage': False, 'forum': False, 'connected': 0,
     'created_at': '2025-11-03T09:20:00+00:00', 'mention': ''},
    {'id': '2004', 'name': 'offtop', 'type': 'text', 'position': 2,
     'category': 'Общение', 'category_id': '2001', 'category_pos': 1,
     'topic': 'Разговоры не по теме сервера',
     'nsfw': False, 'slowmode': 5, 'bitrate': 0, 'user_limit': 0,
     'news': False, 'stage': False, 'forum': False, 'connected': 0,
     'created_at': '2025-11-03T09:21:00+00:00', 'mention': ''},
    {'id': '3001', 'name': 'Голосовые', 'type': 'category', 'position': 2,
     'category': None, 'category_id': None, 'category_pos': -1,
     'topic': '', 'nsfw': False, 'slowmode': 0, 'bitrate': 0, 'user_limit': 0,
     'news': False, 'stage': False, 'forum': False, 'connected': 0,
     'created_at': '2025-11-02T10:15:00+00:00', 'mention': ''},
    {'id': '3002', 'name': 'Общий войс', 'type': 'voice', 'position': 0,
     'category': 'Голосовые', 'category_id': '3001', 'category_pos': 2,
     'topic': '', 'nsfw': False, 'slowmode': 0, 'bitrate': 64, 'user_limit': 0,
     'news': False, 'stage': False, 'forum': False, 'connected': 4,
     'created_at': '2025-11-02T10:16:00+00:00', 'mention': ''},
    {'id': '3003', 'name': 'Игровой', 'type': 'voice', 'position': 1,
     'category': 'Голосовые', 'category_id': '3001', 'category_pos': 2,
     'topic': '', 'nsfw': False, 'slowmode': 0, 'bitrate': 96, 'user_limit': 8,
     'news': False, 'stage': False, 'forum': False, 'connected': 3,
     'created_at': '2025-11-05T18:30:00+00:00', 'mention': ''},
    {'id': '3004', 'name': 'Вечерний эфир', 'type': 'voice', 'position': 2,
     'category': 'Голосовые', 'category_id': '3001', 'category_pos': 2,
     'topic': 'Еженедельные обсуждения с командой', 'nsfw': False,
     'slowmode': 0, 'bitrate': 64, 'user_limit': 25,
     'news': False, 'stage': True, 'forum': False, 'connected': 0,
     'created_at': '2026-01-12T19:00:00+00:00', 'mention': ''},
    {'id': '4001', 'name': 'Модерация', 'type': 'category', 'position': 3,
     'category': None, 'category_id': None, 'category_pos': -1,
     'topic': '', 'nsfw': False, 'slowmode': 0, 'bitrate': 0, 'user_limit': 0,
     'news': False, 'stage': False, 'forum': False, 'connected': 0,
     'created_at': '2025-11-02T10:20:00+00:00', 'mention': ''},
    {'id': '4002', 'name': 'mod-chat', 'type': 'text', 'position': 0,
     'category': 'Модерация', 'category_id': '4001', 'category_pos': 3,
     'topic': 'Внутренний чат модераторов', 'nsfw': False, 'slowmode': 0,
     'bitrate': 0, 'user_limit': 0, 'news': False, 'stage': False,
     'forum': False, 'connected': 0,
     'created_at': '2025-11-02T10:21:00+00:00', 'mention': ''},
    {'id': '4003', 'name': 'mod-log', 'type': 'text', 'position': 1,
     'category': 'Модерация', 'category_id': '4001', 'category_pos': 3,
     'topic': 'Автоматический журнал действий модерации', 'nsfw': False,
     'slowmode': 0, 'bitrate': 0, 'user_limit': 0, 'news': False,
     'stage': False, 'forum': False, 'connected': 0,
     'created_at': '2025-11-02T10:22:00+00:00', 'mention': ''},
    {'id': '5001', 'name': 'welcome', 'type': 'text', 'position': 0,
     'category': None, 'category_id': None, 'category_pos': -1,
     'topic': 'Приветствия новых участников', 'nsfw': False, 'slowmode': 0,
     'bitrate': 0, 'user_limit': 0, 'news': False, 'stage': False,
     'forum': False, 'connected': 0,
     'created_at': '2025-11-02T10:25:00+00:00', 'mention': ''},
]

demo_rules = [
    {'t': 'Будьте вежливы и уважайте других участников — без оскорблений и травли.',
     'u': 'https://discord.com/guidelines', 'img': '', 'thumb': ''},
    {'t': 'Никакого спама, флуда и капса в текстовых каналах.', 'u': '', 'img': '', 'thumb': ''},
    {'t': 'Запрещены NSFW-материалы, шок-контент и ссылки на вредоносные ресурсы.',
     'u': '', 'img': '', 'thumb': ''},
    {'t': 'Реклама других серверов — только с разрешения администрации.',
     'u': '', 'img': 'https://cdn.discordapp.com/attachments/0000/example_rules.png', 'thumb': ''},
    {'t': 'Спорные ситуации решайте через тикеты, а не в общем чате.',
     'u': 'https://support.discord.com/hc/ru', 'img': '', 'thumb': ''},
    {'t': 'Следуйте указаниям модераторов — их решения можно обжаловать через апелляции.',
     'u': '', 'img': '', 'thumb': 'https://cdn.discordapp.com/attachments/0000/example_thumb.png'},
]

demo_xp = {
    '1': {'name': 'sonya.staff', 'xp': 8420, 'level': 28, 'avatar': 'https://cdn.discordapp.com/embed/avatars/1.png'},
    '2': {'name': 'artem.mods', 'xp': 7630, 'level': 24, 'avatar': 'https://cdn.discordapp.com/embed/avatars/2.png'},
    '3': {'name': 'lina.mod', 'xp': 6890, 'level': 21, 'avatar': 'https://cdn.discordapp.com/embed/avatars/3.png'},
    '4': {'name': 'max.gg', 'xp': 5210, 'level': 17, 'avatar': 'https://cdn.discordapp.com/embed/avatars/4.png'},
    '5': {'name': 'dasha.live', 'xp': 4470, 'level': 15, 'avatar': 'https://cdn.discordapp.com/embed/avatars/5.png'},
    '6': {'name': 'kolyan.tv', 'xp': 3150, 'level': 11, 'avatar': 'https://cdn.discordapp.com/embed/avatars/0.png'},
    '7': {'name': 'nastya.chat', 'xp': 2480, 'level': 9, 'avatar': 'https://cdn.discordapp.com/embed/avatars/2.png'},
    '8': {'name': 'vanya.voice', 'xp': 1730, 'level': 7, 'avatar': 'https://cdn.discordapp.com/embed/avatars/3.png'},
}
demo_leveling = {
    'enabled': True, 'notify': True, 'notify_channel': '4002',
    'xp_min': 15, 'xp_max': 25, 'cooldown': 60,
    'level_message': '{user} достиг уровня {level}!',
}

# ── Заявки в команду (панель /staff-apps) ────────────────────────────────
staff_apps = {
    'app-9001': {
        'app_id': 'app-9001',
        'user_id': '623456789012345678',
        'display_name': 'kira.moon',
        'username': 'kira.moon',
        'avatar': 'https://cdn.discordapp.com/embed/avatars/5.png',
        'role': 'Хелпер',
        'status': 'pending',
        'guild_id': GID,
        'timestamp': iso(0, 16, 40),
        'answers': {
            'yas': 19,
            'activity': '3-4 часа',
            'tecrube': 'Модерировала два сервера по 3k участников, знаю баны/мьюты/логи.',
            'why': 'Люблю это сообщество и хочу помогать новичкам освоиться.',
            'ekstra': 'Готова выходить на вечерние смены.',
        },
    },
    'app-9002': {
        'app_id': 'app-9002',
        'user_id': '723456789012345679',
        'display_name': 'max.storm',
        'username': 'max.storm',
        'avatar': 'https://cdn.discordapp.com/embed/avatars/1.png',
        'role': 'Модератор',
        'status': 'pending',
        'guild_id': GID,
        'timestamp': iso(1, 18, 5),
        'answers': {
            'yas': 22,
            'activity': '5+ часов',
            'tecrube': 'Год опыта модерации, вёл тикеты и разбирал апелляции.',
            'why': 'Вижу, что сервер растёт — хочу помогать держать порядок.',
            'ekstra': '',
        },
    },
    'app-9003': {
        'app_id': 'app-9003',
        'user_id': '823456789012345680',
        'display_name': 'lena.fox',
        'username': 'lena.fox',
        'avatar': 'https://cdn.discordapp.com/embed/avatars/4.png',
        'role': 'Хелпер',
        'status': 'approved',
        'guild_id': GID,
        'timestamp': iso(3, 12, 20),
        'reviewed_by': 'sonya.staff',
        'review_note': 'Добро пожаловать в команду!',
        'answers': {
            'yas': 18,
            'activity': '2-3 часа',
            'tecrube': 'Помогала в игровом комьюнити, вела FAQ.',
            'why': 'Хочу сделать сервер уютнее для новичков.',
            'ekstra': '',
        },
    },
    'app-9004': {
        'app_id': 'app-9004',
        'user_id': '923456789012345681',
        'display_name': 'dima.ghost',
        'username': 'dima.ghost',
        'avatar': 'https://cdn.discordapp.com/embed/avatars/2.png',
        'role': 'Модератор',
        'status': 'rejected',
        'guild_id': GID,
        'timestamp': iso(4, 21, 10),
        'reviewed_by': 'artem.mods',
        'review_note': 'Пока рано — возвращайся с опытом.',
        'answers': {
            'yas': 15,
            'activity': '1 час',
            'tecrube': 'Не модерю, но хочу научиться.',
            'why': 'Кажется, это круто.',
            'ekstra': '',
        },
    },
}

files = {
    'data/warnings.json': warnings,
    'data/audit_log.json': audit,
    'data/mod_data.json': mod_data,
    f'data/modproof_{GID}.json': proofs,
    f'data/warn_config_{GID}.json': warn_config,
    'data/login_log.json': login_log,
    'data/panel_logs.json': panel_logs,
    'data/team_board.json': team_board,
    'data/staff_apps.json': staff_apps,
    'data/demo_channels.json': demo_channels,
    'data/hidden_channels.json': {},
    f'data/rules_{GID}.json': demo_rules,
    f'data/xp_{GID}.json': demo_xp,
    f'data/leveling_{GID}.json': demo_leveling,
}

for path, payload in files.items():
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print('записано:', path)

# ── Смены персонала: то же хранилище, что у бота (GuildData) ───────────
# Живая смена «прямо сейчас» + вечное расписание — страница сразу живая.
try:
    import sys as _sys
    import os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    from datetime import timedelta, timezone as _tz
    from db import GuildData

    _t3 = _tz(timedelta(hours=3))          # пояс демо-сервера (UTC+3)
    _now3 = datetime.now(_t3)
    _start3 = (_now3 - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    _end3 = (_now3 + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    _fmt = lambda d: d.strftime('%H:%M')
    _shifts = {
        'live': {'user_id': '1001', 'weekday': _now3.weekday(),
                 'start': _fmt(_start3), 'end': _fmt(_end3),
                 'added_by': 'panel:owner', 'added_at': iso(0, 12, 0)},
        'd1': {'user_id': '1001', 'weekday': 0, 'start': '18:00', 'end': '22:00', 'added_by': 'panel:owner'},
        'd2': {'user_id': '1002', 'weekday': 1, 'start': '18:00', 'end': '22:00', 'added_by': 'panel:owner'},
        'd3': {'user_id': '1003', 'weekday': 2, 'start': '16:00', 'end': '20:00', 'added_by': 'panel:owner'},
        'd4': {'user_id': '1004', 'weekday': 3, 'start': '18:00', 'end': '22:00', 'added_by': 'panel:owner'},
        'd5': {'user_id': '1005', 'weekday': 4, 'start': '20:00', 'end': '00:00', 'added_by': 'panel:owner'},
        'd6': {'user_id': '1006', 'weekday': 5, 'start': '12:00', 'end': '16:00', 'added_by': 'panel:owner'},
        'd7': {'user_id': '1002', 'weekday': 5, 'start': '16:00', 'end': '20:00', 'added_by': 'panel:owner'},
        'd8': {'user_id': '1003', 'weekday': 6, 'start': '14:00', 'end': '18:00', 'added_by': 'panel:owner'},
    }
    _ss = GuildData('staff_shifts')
    _ss.set(GID, 'settings', {'channel_id': 4002, 'tz_offset': 3})
    _ss.set(GID, 'shifts', _shifts)
    print('записано: смены персонала (%d смен)' % len(_shifts))
except Exception as _ex:
    print('смены персонала не засеяны:', _ex)

# ── Заметки участников (страница /member-notes) ──
try:
    _notes = {
        '1001': {'name': 'Sonya', 'avatar': 'https://cdn.discordapp.com/embed/avatars/1.png',
                 'notes': [
                     {'id': 'n1', 'note': 'Ведёт ночные смены дежурств, надёжная.', 'author': 'artem.mods',
                      'timestamp': iso(2, 20, 15)},
                     {'id': 'n2', 'note': 'Помогла с набором модераторов — поблагодарить.', 'author': 'lina.mod',
                      'timestamp': iso(5, 11, 0)}]},
        '1002': {'name': 'Artem', 'avatar': 'https://cdn.discordapp.com/embed/avatars/2.png',
                 'notes': [
                     {'id': 'n3', 'note': 'Отвечает за варн-конфиг. Согласовывать пороги с ним.', 'author': 'owner',
                      'timestamp': iso(1, 16, 45)}]},
        '1003': {'name': 'Lina', 'avatar': 'https://cdn.discordapp.com/embed/avatars/3.png',
                 'notes': [
                     {'id': 'n4', 'note': 'Обрабатывает тикеты в утренние часы.', 'author': 'artem.mods',
                      'timestamp': iso(3, 9, 30)},
                     {'id': 'n5', 'note': 'На испытательном сроке до конца месяца.', 'author': 'owner',
                      'timestamp': iso(6, 18, 0)}]},
    }
    with open('data/member_notes.json', 'w', encoding='utf-8') as _f:
        json.dump(_notes, _f, ensure_ascii=False, indent=2)
    print('записано: заметки участников (%d)' % len(_notes))
except Exception as _ex:
    print('заметки не засеяны:', _ex)

# ── Наблюдение (watchlist) — в mod_data.json рядом с кейсами ──
try:
    _md = json.load(open('data/mod_data.json', encoding='utf-8'))
    _md['watchlist'] = {GID: {
        '823456789012345680': {'reason': 'Снял мьют вторым аккаунтом', 'added_by': 'lina.mod',
                               'timestamp': iso(1, 20, 0)},
        '623456789012345678': {'reason': 'Пограничный капс-спам, смотрим', 'added_by': 'sonya.staff',
                               'timestamp': iso(3, 14, 30)},
        '923456789012345681': {'reason': 'Ночной флудер, возможен обход бана', 'added_by': 'artem.mods',
                               'timestamp': iso(4, 2, 10)},
    }}
    with open('data/mod_data.json', 'w', encoding='utf-8') as _f:
        json.dump(_md, _f, ensure_ascii=False, indent=2)
    print('записано: watchlist (3 участника)')
except Exception as _ex:
    print('watchlist не засеян:', _ex)

# ── Цветные роли: демо-палитра ──
try:
    _palette = [
        {'name': 'Красный', 'hex': '#ef4444', 'emoji': ''},
        {'name': 'Синий', 'hex': '#3b82f6', 'emoji': ''},
        {'name': 'Зелёный', 'hex': '#22c55e', 'emoji': ''},
        {'name': 'Фиолетовый', 'hex': '#a855f7', 'emoji': ''},
    ]
    with open('data/color_roles_%s.json' % GID, 'w', encoding='utf-8') as _f:
        json.dump(_palette, _f, ensure_ascii=False, indent=2)
    print('записано: палитра цветных ролей (%d)' % len(_palette))
except Exception as _ex:
    print('палитра не засеяна:', _ex)

# ── DM-разговоры для страницы «Чат» ──
try:
    _dm_log = {
        '823456789012345680': [
            {'content': 'Привет, почему меня замутили?', 'author': 'toxicguy', 'bot': False,
             'timestamp': iso(1, 21, 5)},
            {'content': 'Обход мьюта вторым аккаунтом. Подробности в тикете.', 'author': 'Aether', 'bot': True,
             'timestamp': iso(1, 21, 7)},
        ],
        '723456789012345679': [
            {'content': 'Я не спамил голосовым ботом, честно!', 'author': 'voice_troll', 'bot': False,
             'timestamp': iso(2, 19, 40)},
            {'content': 'Логи говорят иначе. Апелляция — через /appeal.', 'author': 'Aether', 'bot': True,
             'timestamp': iso(2, 19, 44)},
        ],
    }
    with open('data/dm_log.json', 'w', encoding='utf-8') as _f:
        json.dump(_dm_log, _f, ensure_ascii=False, indent=2)
    print('записано: DM-разговоры (%d)' % len(_dm_log))
except Exception as _ex:
    print('DM-лог не засеян:', _ex)

# ── Приглашения: лидерборд и свежие входы ──
try:
    _lb = [
        {'name': 'sonya.staff', 'joins': 14, 'leaves': 2},
        {'name': 'artem.mods', 'joins': 11, 'leaves': 1},
        {'name': 'lina.mod', 'joins': 8, 'leaves': 0},
        {'name': 'max.gg', 'joins': 5, 'leaves': 3},
    ]
    with open('data/invites_%s.json' % GID, 'w', encoding='utf-8') as _f:
        json.dump({'leaderboard': _lb, 'total_joins': 38, 'total_leaves': 6}, _f, ensure_ascii=False, indent=2)
    _joins = []
    for i in range(10):
        _joins.append({'user': 'newbie_%02d' % i, 'inviter': _lb[i % len(_lb)]['name'],
                       'timestamp': iso(i, 12, 0)})
    with open('data/invite_joins_%s.json' % GID, 'w', encoding='utf-8') as _f:
        json.dump(_joins, _f, ensure_ascii=False, indent=2)
    print('записано: приглашения (лидерборд %d + %d входов)' % (len(_lb), len(_joins)))
except Exception as _ex:
    print('приглашения не засеяны:', _ex)

# ── Рейтинги: сообщения и балансы демо-участников (реальные имена) ──
try:
    _lb_members = [('1001', 'Sonya', 'sonya.staff', 1850),
                   ('1002', 'Artem', 'artem.mods', 1640),
                   ('1003', 'Lina', 'lina.mod', 1320),
                   ('1004', 'Max', 'max.gg', 980),
                   ('1005', 'Dasha', 'dasha.live', 760),
                   ('1006', 'Kolyan', 'kolyan.tv', 540),
                   ('1007', 'Nastya', 'nastya.chat', 430),
                   ('1008', 'Vanya', 'vanya.dev', 310)]
    _lb = {'messages': {uid: str(cnt) for uid, _nm, _lg, cnt in _lb_members}}
    with open('data/leaderboard_%s.json' % GID, 'w', encoding='utf-8') as _f:
        json.dump(_lb, _f, ensure_ascii=False, indent=2)
    _eco = {uid: {'balance': 1500 + i * 1800, 'bank': 2500 + i * 3200}
            for i, (uid, _nm, _lg, _cnt) in enumerate(_lb_members)}
    with open('data/economy_%s.json' % GID, 'w', encoding='utf-8') as _f:
        json.dump(_eco, _f, ensure_ascii=False, indent=2)
    print('записано: рейтинги (сообщения 8 + балансы 8)')
except Exception as _ex:
    print('рейтинги не засеяны:', _ex)

# ── Карта имён: uid → имя для логов (вместо голых ID) ──
try:
    _names_map = {
        '823456789012345680': 'toxicguy',
        '523456789012345678': 'spammer_228',
        '723456789012345679': 'voice_troll',
        '923456789012345681': 'night_flooder',
        '623456789012345678': 'caps_forever',
        '623456789012345679': 'loud_voice',
        '823456789012345679': 'offtopic_king',
        '423456789012345678': 'emoji_spam',
    }
    with open('data/member_names_%s.json' % GID, 'w', encoding='utf-8') as _f:
        json.dump(_names_map, _f, ensure_ascii=False, indent=2)
    print('записано: карта имён участников (%d пар)' % len(_names_map))
except Exception as _ex:
    print('карта имён не засеяна:', _ex)

# ── Маппинг Discord-ролей → роли панели (включая Куратора) ──
try:
    _role_map = {'9001': 'owner', '9002': 'admin', '9003': 'mod', '9013': 'curator'}
    with open('data/role_map.json', 'w', encoding='utf-8') as _f:
        json.dump(_role_map, _f, ensure_ascii=False, indent=2)
    print('записано: маппинг ролей панели (owner/admin/mod/curator)')
except Exception as _ex:
    print('маппинг ролей не засеян:', _ex)

# ── Демо-тикеты для Про-аналитики (файл, который читает /api/analytics/advanced) ──
try:
    _cats = ['Модерация', 'Техподдержка', 'Жалобы', 'Другое']
    _mods = ['sonya.staff', 'artem.mods', 'lina.mod', None]
    _users = ['toxicguy', 'spammer_228', 'caps_forever', 'night_flooder', 'emoji_spam']
    _tk = {}
    for i in range(26):
        days_ago = (i * 5) % 30
        opened = NOW - timedelta(days=days_ago, hours=i % 9)
        closed = opened + timedelta(hours=1 + (i % 30))
        status = 'closed' if i % 4 else 'open'
        _tk['tk-demo-%02d' % i] = {
            'created_at': opened.isoformat(),
            'closed_at': closed.isoformat() if status == 'closed' else None,
            'status': status,
            'category': _cats[i % len(_cats)],
            'closed_by': _mods[i % len(_mods)] if status == 'closed' else None,
            'user_name': _users[i % len(_users)],
            'description': 'Демо-обращение №%d для Про-аналитики' % (i + 1),
        }
    with open('data/ai_tickets_demo.json', 'w', encoding='utf-8') as _f:
        json.dump(_tk, _f, ensure_ascii=False, indent=2)
    print('записано: демо-тикеты для Про-аналитики (%d шт)' % len(_tk))
except Exception as _ex:
    print('демо-тикеты не засеяны:', _ex)

# ── Антифейк: конфиг + страйки рекламы (файлы кога) ──
try:
    _af_cfg = {
        GID: {'enabled': True, 'action': 'strip', 'log_channel_id': 1002,
              'check_join': True, 'check_update': True, 'check_ads': True,
              'threshold': 0.85, 'protected_names': ['Aether', 'Владелец', 'Администратор', 'Куратор', 'Модератор'],
              'exempt_staff': True, 'dm_notify': True, 'strike_timeout': True}}
    with open('data/antifake.json', 'w', encoding='utf-8') as _f:
        json.dump(_af_cfg, _f, ensure_ascii=False, indent=2)
    _t = time.time()
    _af_strikes = {GID: {
        '1004': [_t - 3600, _t - 86400 * 2, _t - 86400 * 5],          # 3 шт → порог
        '1005': [_t - 7200],                                            # 1 активный
        '1007': [_t - 86400 * 10, _t - 86400 * 20],                     # оба протухли
        '888888888888888888': [_t - 1800],                               # покинувший сервер
    }}
    with open('data/antifake_strikes.json', 'w', encoding='utf-8') as _f:
        json.dump(_af_strikes, _f, ensure_ascii=False, indent=2)
    print('записано: антифейк (конфиг + страйки 4 участников)')
except Exception as _ex:
    print('антифейк не засеян:', _ex)

# ── Голос и сообщения модеров (для профи-статистики /mod-history) ──
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + os.sep + '..')
    from db import GuildData as _GD
    import random as _rnd2
    _rnd2.seed(777)
    _mods = [('1001', 'Sonya', 'sonya.staff', 'https://cdn.discordapp.com/embed/avatars/1.png'),
             ('1002', 'Artem', 'artem.mods', 'https://cdn.discordapp.com/embed/avatars/2.png'),
             ('1003', 'Lina', 'lina.mod', 'https://cdn.discordapp.com/embed/avatars/3.png')]
    _today = datetime.now(timezone.utc).date()
    _voice = _GD('voice_stats')
    _msgs = _GD('mod_activity')
    for uid, name, login, avatar in _mods:
        daily = {}
        total_s = 0
        for d in range(7):
            dkey = (_today - timedelta(days=d)).strftime('%Y-%m-%d')
            secs = _rnd2.randint(1800, 9000) * (1 if _rnd2.random() > 0.25 else 0)
            daily[dkey] = secs
            total_s += secs
        _voice.set(GID, uid, {'name': name, 'avatar': avatar,
                              'total_seconds': total_s, 'daily': daily})
        mdays = {}
        for d in range(7):
            dkey = (_today - timedelta(days=d)).strftime('%Y-%m-%d')
            mdays[dkey] = _rnd2.randint(40, 220)
        _msgs.set(GID, uid, {'name': name, 'days': mdays})
    print('записано: голос и сообщения модеров (3 × 7 дней)')
except Exception as _ex:
    print('голос/сообщения модеров не засеяны:', _ex)

# ── Учётка владельца панели: консистентна с env, под который стартует демо ──
try:
    from werkzeug.security import generate_password_hash as _wz_gen
    _u = (os.environ.get('PANEL_USER', 'owner') or 'owner').strip() or 'owner'
    _p = (os.environ.get('PANEL_PASSWORD', 'preview123') or 'preview123').strip() or 'preview123'
    with open('data/panel_credentials.json', 'w', encoding='utf-8') as _f:
        json.dump({'user': _u, 'password_hash': _wz_gen(_p)}, _f, ensure_ascii=False)
    _txt = 'data/panel_credentials.txt'
    if os.path.exists(_txt):
        os.remove(_txt)
    print(f'записано: демо-учётка панели ({_u})')
except Exception as _ex:
    print('учётка панели не засеяна:', _ex)

print('Готово. Демо-данные в data/ (gitignored).')
