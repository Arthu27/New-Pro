# -*- coding: utf-8 -*-
"""Посев демо-данных для живой демонстрации панели (guild 777).

Пишет только в data/ (gitignored). Удалить демо-данные: rm файлы ниже
или запустить reset_server_data.py.
"""
import json
import os
from datetime import datetime, timedelta, timezone

os.makedirs('data', exist_ok=True)

NOW = datetime.now(timezone.utc)


def iso(days_ago=0, hour=12, minute=0):
    dt = NOW - timedelta(days=days_ago)
    dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return dt.isoformat()


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
          reason='Неоднократные оскорбления после бана', timestamp=iso(0, 22, 10)),
        A(action='mute', user_name='spammer_228', mod_name='artem.mods',
          reason='Флуд в общем чате', timestamp=iso(0, 20, 5)),
        A(action='warn', user_name='newbie_gg', mod_name='sonya.staff',
          reason='Реклама в профиле', timestamp=iso(0, 18, 40)),
        A(action='kick', user_name='alt_account1', mod_name='lina.mod',
          reason='Подозрение на обход мьюта', timestamp=iso(0, 12, 25)),
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
     'reason': 'Обход мьюта вторым аккаунтом', 'timestamp': iso(1, 22, 45)},
    {'user_id': '523456789012345678', 'mod_id': 'sonya.staff', 'action': 'warn',
     'reason': 'Разжигание конфликта после предупреждения', 'timestamp': iso(2, 21, 15)},
    {'user_id': '723456789012345679', 'mod_id': 'artem.mods', 'action': 'warn',
     'reason': 'Спам ссылками на сторонний сервер', 'timestamp': iso(5, 15, 5)},
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
    'Будьте вежливы и уважайте других участников — без оскорблений и травли.',
    'Никакого спама, флуда и капса в текстовых каналах.',
    'Запрещены NSFW-материалы, шок-контент и ссылки на вредоносные ресурсы.',
    'Реклама других серверов — только с разрешения администрации.',
    'Спорные ситуации решайте через тикеты, а не в общем чате.',
    'Следуйте указаниям модераторов — их решения можно обжаловать через апелляции.',
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

files = {
    'data/warnings.json': warnings,
    'data/audit_log.json': audit,
    'data/mod_data.json': mod_data,
    f'data/modproof_{GID}.json': proofs,
    f'data/warn_config_{GID}.json': warn_config,
    'data/login_log.json': login_log,
    'data/panel_logs.json': panel_logs,
    'data/team_board.json': team_board,
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
print('Готово. Демо-данные в data/ (gitignored).')
