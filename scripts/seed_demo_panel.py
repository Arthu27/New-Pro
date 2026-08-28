# -*- coding: utf-8 -*-
"""Посев ДЕМО-данных для витрины панели (выдуманный сервер 987654321098765432).

Нужен только для предпросмотра без бота (start_panel --demo / .bat demo).
В боевом запуске НЕ используется: панель показывает реальные данные бота.

Защита от случайного запуска: без DEMO_MODE=1 (или --force) скрипт отказывается
писать, чтобы выдуманные данные не смешивались с реальными (жалоба владельца:
«панель грузит фейк и чужой сервер»).

Убрать уже записанные демо-данные:  python scripts/seed_demo_panel.py --clean
(полный сброс всех данных — reset_server_data.py).
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

# ID серверов-заглушек демо-превью (этот скрипт + scripts/demo_panel.py + тесты)
_DEMO_GIDS = ('987654321098765432', '777', '4242')

# Демо-персонажи посева (для --clean): узнаём их след в общих файлах панели
_DEMO_USERNAMES = {
    'artem.mods', 'sonya.staff', 'lina.mod', 'max.admin',
    'kira.moon', 'max.storm', 'lena.fox', 'dima.ghost',
    'kira.watch', 'ivan.flood',
}
_DEMO_DISCORD_IDS = {'111111111111111111', '222222222222222222',
                     '333333333333333333', '444444444444444444'}


def _truth(v):
    return str(v or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _strip_guild(obj):
    """Вырезать из JSON-структуры ключи и записи демо-серверов (in-place)."""
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            v = obj[k]
            if k in _DEMO_GIDS or (isinstance(v, dict)
                                   and str(v.get('guild_id')) in _DEMO_GIDS):
                del obj[k]
            else:
                _strip_guild(v)
    elif isinstance(obj, list):
        obj[:] = [x for x in obj
                  if not (isinstance(x, dict)
                          and str(x.get('guild_id')) in _DEMO_GIDS)]
        for x in obj:
            _strip_guild(x)


def clean_demo_data():
    """--clean: убрать демо-данные из data/, оставив данные настоящих серверов."""
    removed = []

    # 1. Файлы, целиком привязанные к демо-серверу — удаляем
    gid_files = []
    for gid in _DEMO_GIDS:
        gid_files += [
            f'data/modproof_{gid}.json', f'data/warn_config_{gid}.json',
            f'data/starboard_settings_{gid}.json', f'data/ticket_notify_{gid}.json',
            f'data/rules_{gid}.json', f'data/xp_{gid}.json',
            f'data/leveling_{gid}.json', f'data/antiraid_{gid}.json',
            f'data/security_{gid}.json', f'data/guardian_{gid}.json',
        ]
    gid_files += ['data/demo_channels.json', 'data/demo_cog_states.json']
    for path in gid_files:
        if os.path.exists(path):
            os.remove(path)
            removed.append(path)

    # 1b. Демо-скриншоты доказательств
    import glob as _glob
    for gid in _DEMO_GIDS:
        for path in _glob.glob(f'data/uploads/proofs/{gid}_*.png'):
            os.remove(path)
            removed.append(path)

    # 2. Общие JSON-файлы: вырезаем только демо-GID, реальное не трогаем
    shared = ['data/warnings.json', 'data/audit_log.json', 'data/mod_data.json',
              'data/channel_routes.json', 'data/tag_jail.json',
              'data/night_summary.json', 'data/staff_apps.json',
              'data/discord_audit_cache.json', 'data/audit_seen.json']
    for path in shared:
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            _strip_guild(payload)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            removed.append(path + ' (демо-GID вырезан)')
        except Exception as ex:
            print(f'  не смог почистить {path}: {ex}')

    # 3. Списки панели без привязки к серверу: вырезаем демо-персонажей
    path = 'data/login_log.json'
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                rows = json.load(f)
            if isinstance(rows, list):
                rows = [r for r in rows if not (
                    str(r.get('discord_id')) in _DEMO_DISCORD_IDS
                    or str(r.get('username')) in _DEMO_USERNAMES)]
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(rows, f, ensure_ascii=False, indent=2)
                removed.append(path + ' (демо-входы вырезаны)')
        except Exception as ex:
            print(f'  не смог почистить {path}: {ex}')

    # 4. Канбан: посевные задачи — id 1..5 (next_id=6), реальные идут после
    path = 'data/team_board.json'
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                board = json.load(f)
            tasks = board.get('tasks') or {}
            for tid in [k for k in tasks if str(k).isdigit() and int(k) < 6]:
                del tasks[tid]
                removed.append(f'{path} задача #{tid}')
            board['next_id'] = max([int(k) for k in tasks if str(k).isdigit()]
                                   or [0]) + 1
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(board, f, ensure_ascii=False, indent=2)
        except Exception as ex:
            print(f'  не смог почистить {path}: {ex}')

    # 5. Конфиги, которые посев перезаписал целиком (канал 4005 — выдуманный)
    path = 'data/anticrash_config.json'
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                ac = json.load(f)
            if not (set(ac) - {'log_channel_id'}):
                os.remove(path)
                removed.append(path)
        except Exception as ex:
            print(f'  не смог почистить {path}: {ex}')

    # 6. SQLite-хранилища когов (shifts, counting, welcome_pro и др.):
    #    все записи демо-серверов одним DELETE
    try:
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from config import Config
        import sqlite3
        db_path = Config.DB_PATH
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            try:
                cur = conn.execute(
                    "DELETE FROM guild_data WHERE CAST(guild_id AS TEXT) IN "
                    + ','.join('?' * len(_DEMO_GIDS)), _DEMO_GIDS)
                conn.commit()
                if cur.rowcount:
                    removed.append(f'{db_path} (записей демо-GID: {cur.rowcount})')
            finally:
                conn.close()
    except Exception as ex:
        print(f'  sqlite-очистка пропущена: {ex}')

    if removed:
        print('Убраны демо-данные:')
        for item in removed:
            print('  -', item)
    else:
        print('Демо-данных не найдено — чистить нечего.')
    print('Готово. Реальные данные (другие серверы, доступы к панели) не тронуты.')


if '--clean' in sys.argv:
    clean_demo_data()
    sys.exit(0)

# Гард: посев только при явном демо-режиме. Без него скрипт молча перезаписывал
# боевой data/ выдумками — именно так панель получала «фейк и чужой сервер».
if not _truth(os.environ.get('DEMO_MODE')) and '--force' not in sys.argv:
    print('ОТКАЗ: это посев ВЫДУМАННЫХ данных (демо-витрина панели).')
    print('Боевой панели он не нужен — запусти панель обычно: ./start_panel.sh')
    print('Если правда нужен предпросмотр: DEMO_MODE=1 python scripts/seed_demo_panel.py')
    print('Убрать уже записанные демо-данные:  python scripts/seed_demo_panel.py --clean')
    sys.exit(1)

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
          'media': {'file': f'data/uploads/proofs/{GID}_1.png', 'kind': 'image',
                    'name': 'chat-screenshot.png', 'size': 0, 'ctype': 'image/png'},
          'url': '', 'set_at': iso(0, 22, 10)},
    '2': {'id': 2, 'user_id': 523456789012345678, 'user_name': 'spammer_228',
          'mod_name': 'artem.mods', 'action': 'мут',
          'reason': 'Видео с флудом в общем чате',
          'link': 'https://discord.com/channels/777/112233/445567',
          'url': '', 'set_at': iso(0, 20, 5)},
    '3': {'id': 3, 'user_id': 923456789012345681, 'user_name': 'newbie_gg',
          'mod_name': 'sonya.staff', 'action': 'варн',
          'reason': 'Реклама в профиле — скриншот',
          'media': {'file': f'data/uploads/proofs/{GID}_3.png', 'kind': 'image',
                    'name': 'profile-screenshot.png', 'size': 0, 'ctype': 'image/png'},
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
    {'id': '4004', 'name': '-доказательства', 'type': 'text', 'position': 2,
     'category': 'Модерация', 'category_id': '4001', 'category_pos': 3,
     'topic': 'Демки к наказаниям: кто, кого, за что + фото/видео', 'nsfw': False,
     'slowmode': 0, 'bitrate': 0, 'user_limit': 0, 'news': False, 'stage': False,
     'forum': False, 'connected': 0,
     'created_at': '2025-11-02T10:25:00+00:00', 'mention': ''},
    {'id': '4005', 'name': '-защита', 'type': 'text', 'position': 3,
     'category': 'Модерация', 'category_id': '4001', 'category_pos': 3,
     'topic': 'Тревоги Щита сервера: остановленные атаки, меры, подозрительные боты',
     'nsfw': False, 'slowmode': 0, 'bitrate': 0, 'user_limit': 0, 'news': False,
     'stage': False, 'forum': False, 'connected': 0,
     'created_at': '2025-11-02T10:26:00+00:00', 'mention': ''},
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
    'data/channel_routes.json': {GID: {'proof_channel': 4004,
                              'guardian_channel': 4005}},
    'data/tag_jail.json': {GID: {'log_channel_id': 4003}},
    'data/hidden_channels.json': {},
    # Зала славы, ночной итог и призыв в тикеты — живые каналы сразу на месте
    f'data/starboard_settings_{GID}.json': {'channel_id': 2003, 'emoji': '⭐', 'min_stars': 3},
    'data/night_summary.json': {GID: {'enabled': True, 'channel_id': 1004,
                                'tz_offset': 3, 'last_date': ''}},
    f'data/ticket_notify_{GID}.json': {'notify_channel_id': 4002},
    f'data/rules_{GID}.json': demo_rules,
    f'data/xp_{GID}.json': demo_xp,
    f'data/leveling_{GID}.json': demo_leveling,
    # Защита: анти-рейд, авто-сканер и анти-краш — живые страницы сразу
    f'data/antiraid_{GID}.json': {
        'join_raid': True, 'bot_protection': True, 'webhook_protection': True,
        'delete_protection': True, 'age_filter': True,
        'min_age': 5, 'join_threshold': 5, 'join_window': 10,
        'raid_action': 'alert', 'alert_channel_id': '4003',
        'whitelist': [],
        'recent_events': [
            {'type': 'join_raid', 'count': 7, 'window': 10, 'threshold': 5,
             'last_user': 'raid.bot_447', 'timestamp': iso(1, 3, 12)},
            {'type': 'young_account', 'user_tag': 'newbie_22',
             'user_id': '723456789012345679', 'account_age_days': 2,
             'timestamp': iso(2, 9, 40)},
        ],
    },
    f'data/security_{GID}.json': {
        'ai_spam': True, 'fake_account': True, 'link_scanner': True,
        'new_account_days': 7, 'new_account_action': 'warn',
        'log_channel': 4003,
    },
    'data/anticrash_config.json': {'log_channel_id': 4005},
}

for path, payload in files.items():
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print('записано:', path)

# ── Щит сервера (анти-нюк): живой конфиг + пара инцидентов ──────────────
try:
    import sys as _gs
    import time as _gt
    import os as _go
    _gs.path.insert(0, _go.path.dirname(_go.path.dirname(_go.path.abspath(__file__))))
    from cogs import guardian as _GD

    _gc = _GD.guardian_default()
    # демо: kira.watch — единственная (кроме владельца), кто может звать ботов
    _gc['bot_whitelist_users'] = ['823456789012345680']
    _gc['incidents'] = [
        {'ts': int(_gt.time() - 5 * 3600), 'event': 'channel_delete',
         'label': 'Удаление каналов', 'actor_id': '923456789012345681',
         'actor_name': 'dima.ghost', 'action': 'strip',
         'action_label': 'Снять все роли', 'applied': 'снято ролей: 2',
         'detail': 'канал «offtop»'},
        {'ts': int(_gt.time() - 26 * 3600), 'event': 'bot_add',
         'label': 'Добавление ботов', 'actor_id': '823456789012345680',
         'actor_name': 'kira.watch', 'action': 'kick',
         'action_label': 'Кикнуть с сервера', 'applied': 'кикнут',
         'detail': 'бот «raidb0t» — кикнут автоматически'},
        {'ts': int(_gt.time() - 50 * 3600), 'event': 'webhook_create',
         'label': 'Создание вебхуков', 'actor_id': '623456789012345678',
         'actor_name': 'ivan.flood', 'action': 'alert',
         'action_label': 'Только тревога в лог', 'applied': '—',
         'detail': 'канал «general»'},
    ]
    with open(f'data/guardian_{GID}.json', 'w', encoding='utf-8') as _gf:
        json.dump(_gc, _gf, ensure_ascii=False, indent=2)
    print('записано: Щит сервера (%d инцидентов)' % len(_gc['incidents']))
except Exception as _ex:
    print('Щит не засеян:', _ex)

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

    # Считалка с живым прогрессом и дайджест модерации — каналы сразу на месте
    _cnt = GuildData('counting')
    _cst = _cnt.get(GID, 'state', {}) or {}
    _cst.update({'channel_id': 2004, 'next': 137, 'best': 412,
                 'last_user': 1007, 'last_user_name': 'count_master', 'fails': 3})
    _cnt.set(GID, 'state', _cst)
    GuildData('mod_digest').set(GID, 'settings', {'channel_id': 4003})
    print('записано: каналы считалки и дайджеста модерации')
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
            {'content': 'Обход мьюта вторым аккаунтом. Подробности в тикете.', 'author': 'Hakumo', 'bot': True,
             'timestamp': iso(1, 21, 7)},
        ],
        '723456789012345679': [
            {'content': 'Я не спамил голосовым ботом, честно!', 'author': 'voice_troll', 'bot': False,
             'timestamp': iso(2, 19, 40)},
            {'content': 'Логи говорят иначе. Апелляция — через /appeal.', 'author': 'Hakumo', 'bot': True,
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
              'threshold': 0.85, 'protected_names': ['Hakumo', 'Владелец', 'Администратор', 'Куратор', 'Модератор'],
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

# ── Апелляции: очередь + история (та же схема хранения, что у кога) ──
# Без этого посева страница /appeals выглядит пустой: живые апелляции шлёт
# только бот через /appeal, а в демо бота нет — засеваем правдоподобные.
try:
    from db import GuildData as _GDA
    from cogs import appeals as _AP

    _ap = _AP.empty_state()

    def _mk(days_ago, hour, uid, name, text, link=None):
        _dt = (NOW - timedelta(days=days_ago)).replace(hour=hour, minute=0,
                                                      second=0, microsecond=0)
        _item, _err = _AP.create_appeal(_ap, uid, name, text, _dt, link=link)
        return _item

    def _res(days_ago, hour, uid, name, text, accept, who, reply):
        _it = _mk(days_ago + 1, hour, uid, name, text)
        _rv = (NOW - timedelta(days=days_ago)).replace(hour=hour, minute=30,
                                                      second=0, microsecond=0)
        _AP.resolve_appeal(_ap, _it['id'], accept, who, _rv, reply=reply)

    # очередь: три свежих, одна с ссылкой-доказательством
    _mk(0, 11, '523456789012345678', 'NightHawk_77',
        'Меня замутили на сутки за «флуд», но я просто отвечал троим подряд '
        'в приветственном канале — в логах видно, что сообщения были по делу. '
        'Прошу снять мут и предупреждение.')
    _mk(1, 19, '723456789012345679', 'Кипарис',
        'Бан за ссылки — это был не спам, а ссылка на наш общий документ '
        'с гайдом по ивенту, модератор мог принять за рекламу. '
        'Прикладываю скрин переписки с согласованием.',
        link='https://i.imgur.com/demo-appeal-proof.png')
    _mk(2, 14, '823456789012345670', 'turbo.fox',
        'Сняли роль ивентёра без объяснений, хотя нарушений я не допускал. '
        'Если решение не изменится — прошу хотя бы комментарий, за что именно.')

    # история: две принятых, две отклонённых — с датами и решателями
    _res(2, 16, '923456789012345671', 'ModeRox',
         'Варн за токсичность выписали по шутке в закрытом голосовом — '
         'договорились с ребятами, что не в обиду, скрин подтверждения есть.',
         True, 'sonya.staff',
         'Контекст учтён, варн снят. О шутках договаривайтесь заранее.')
    _res(3, 13, '103456789012345672', 'mirage_q',
         'Ограничили по возрасту — документы прислал позже, модерация '
         'не успела посмотреть. Прошу вернуть доступ к торговым каналам.',
         True, 'owner', 'Данные проверены, ограничения сняты.')
    _res(4, 18, '113456789012345673', 'aka.shock',
         'Требую снять бан, бот точно ошибся — я не флудил капсом, '
         'у меня просто залипла клавиша Shift.',
         False, 'artem.mods',
         'В логах 14 сообщений капсом подряд после предупреждения. В отказе.')
    _res(5, 12, '123456789012345674', 'ЛетучийГолландец',
         'Снимите мут за «провокации» — меня спровоцировали первым, '
         'а сообщения удалили до скриншотов.',
         False, 'sonya.staff',
         'Подтверждений в архиве экспорта не нашлось. Решение остаётся.')

    _ap['log_channel_id'] = 1003   # демо-канал из списка /api/guild/.../channels
    _ap['appearance'] = {'mode': 'auto', 'theme': 'violet', 'url': ''}
    _GDA('appeals').set(GID, 'state', _ap)
    print('записано: апелляции (%d записей: 3 в очереди, 4 закрытых)' % len(_ap['items']))
except Exception as _ex:
    print('апелляции не засеяны:', _ex)

# ── Лог-карточки: явный дефолт (фирменная тема Hakumo, включены) ──
try:
    from services import log_card as _LC
    _LC.save_log_cards_cfg(GID, {'enabled': True, 'theme': 'hakumo', 'accent': ''})
    print('записано: оформление лог-карточек (Hakumo Gold)')
except Exception as _ex:
    print('лог-карточки не засеяны:', _ex)

# ── Карточка приветствия: авто-картинка в фирменной теме ──
try:
    from services import welcome_card_gen as _WCG
    _WCG.save_appearance(GID, {'mode': 'auto', 'theme': 'hakumo', 'url': ''})
    print('записано: оформление карточки приветствия (Hakumo Gold)')
except Exception as _ex:
    print('карточка приветствия не засеяна:', _ex)

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

# ── Медиа-демки: два «скриншота-доказательства» на диск ──
# Панель (/proofs) показывает их прямо на месте — как живые файлы из /proof.
try:
    from PIL import Image as _PI, ImageDraw as _PD
    _mdir = 'data/uploads/proofs'
    os.makedirs(_mdir, exist_ok=True)

    def _proof_png(path, title, lines, accent=(216, 169, 78)):
        img = _PI.new('RGB', (640, 360), (18, 17, 21))
        d = _PD.Draw(img)
        d.rectangle([0, 0, 639, 44], fill=(24, 22, 28))
        d.rectangle([0, 0, 6, 44], fill=accent)
        d.text((20, 14), title, fill=(232, 224, 208))
        y = 66
        for who, txt in lines:
            d.ellipse([18, y + 2, 46, y + 30], fill=(45, 42, 52))
            d.text((58, y), who, fill=(122, 200, 150))
            d.text((58, y + 16), txt, fill=(206, 198, 182))
            y += 46
        d.rectangle([0, 328, 639, 359], fill=(24, 22, 28))
        d.text((20, 338), 'Hakumo · доказательство из демо-посева', fill=(140, 132, 118))
        img.save(path, 'PNG')
        return os.path.getsize(path)

    _s1 = _proof_png(
        os.path.join(_mdir, f'{GID}_1.png'),
        '#общий · сервер Hakumo',
        [('toxicguy', 'да кто вы такие вообще, *цензура*'),
         ('night_fox', 'спокойнее, правила читал?'),
         ('toxicguy', 'заткнись, *цензура*'),
         ('lina.mod', 'Достаточно. Фиксирую.')],
        accent=(231, 76, 60))
    _s2 = _proof_png(
        os.path.join(_mdir, f'{GID}_3.png'),
        'профиль newbie_gg',
        [('статус', 'ВСТУПАЙ! discord.gg/чужой-сервер'),
         ('о себе', 'раздаю нитро — ссылка в статусе'),
         ('sonya.staff', 'Реклама в профиле. Варн.')])
    # размеры файлов — в записи демок (панель покажет на бейдже)
    for _pid, _size in ((1, _s1), (3, _s2)):
        _pp = f'data/modproof_{GID}.json'
        with open(_pp, 'r', encoding='utf-8') as _f:
            _pd = json.load(_f)
        _it = (_pd.get('items') or {}).get(str(_pid))
        if _it and _it.get('media'):
            _it['media']['size'] = _size
            with open(_pp, 'w', encoding='utf-8') as _f:
                json.dump(_pd, _f, ensure_ascii=False, indent=2)
    print('записано: медиа-демки (2 PNG в data/uploads/proofs)')
except Exception as _ex:
    print('медиа-демки не засеяны:', _ex)

# ── Канал приветствий: hub-страница «Каналы и маршруты» живая ──
try:
    from db import GuildData as _GDW
    _wp = _GDW('welcome_pro').get(GID, 'settings', {}) or {}
    _wp.update({'enabled': True, 'channel_id': 5001})
    _GDW('welcome_pro').set(GID, 'settings', _wp)
    print('записано: канал приветствий (welcome PRO → 5001)')
except Exception as _ex:
    print('приветствия не засеяны:', _ex)

# ── Состояния модулей: демо-витрина снова «всё включено» ─────────────────
# Клики по тумблерам в менеджере модулей запоминаются в demo_cog_states.json;
# при пересеве сбрасываем — иначе витрина остаётся в прошлых переключениях.
try:
    with open('data/demo_cog_states.json', 'w', encoding='utf-8') as _f:
        _f.write('{}\n')
    print('записано: состояния модулей (по умолчанию всё включено)')
except Exception as _ex:
    print('состояния модулей не сброшены:', _ex)

print('Готово. Демо-данные в data/ (gitignored).')
