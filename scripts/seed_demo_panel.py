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

files = {
    'data/warnings.json': warnings,
    'data/audit_log.json': audit,
    'data/mod_data.json': mod_data,
    f'data/modproof_{GID}.json': proofs,
    f'data/warn_config_{GID}.json': warn_config,
    'data/login_log.json': login_log,
    'data/panel_logs.json': panel_logs,
}

for path, payload in files.items():
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print('записано:', path)
print('Готово. Демо-данные в data/ (gitignored).')
