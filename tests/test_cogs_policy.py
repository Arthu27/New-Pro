# -*- coding: utf-8 -*-
"""Тесты cogs_policy.py — режим «только модерация» (MOD_ONLY) и точечные
выключатели модулей (DISABLED_COGS / EXTRA_COGS).

Запуск: python3 tests/test_cogs_policy.py
"""
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

from cogs_policy import (
    CORE_COGS, HELPER_COGS, MODERATION_COGS, MOD_ONLY_COGS,
    CORE_ONLY_COGS, TICKET_COGS, AI_CHAT_COGS, MUSIC_COGS, SLIM_COGS,
    LEAN_COGS, MOD_LEAN_COGS, TICKET_LEAN_COGS, AI_LEAN_COGS, WELCOME_LEAN_COGS,
    RETIRED_COGS,
    env_flag, is_helper, select_cog_files, select_from_environment,
    _norm_name, _parse_list,
)

PASS = 0
FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


# Реальный список модулей бота (classic-режим обязан совпадать с ним 1-в-1)
ALL_FILES = sorted(f for f in os.listdir(os.path.join(_REPO, 'cogs'))
                   if f.endswith('.py'))
ALL_SET = set(ALL_FILES)
NON_HELPERS = sorted(f for f in ALL_FILES if f not in HELPER_COGS)


print('\n== 1. Нормализация имён и парсинг списков ==')
check(_norm_name('Music_Cog.py') == 'music_cog', '_norm_name: регистр и .py срезаются')
check(_norm_name(' cogs/Economy_COG ') == 'economy_cog', '_norm_name: путь и пробелы чистятся')
check(_norm_name('cogs.fun_cog') == 'fun_cog', '_norm_name: префикс cogs. срезается')
check(_parse_list('a, b.py ,C') == {'a', 'b', 'c'}, '_parse_list: запятые/пробелы/.py')
check(_parse_list('a;b;;c') == {'a', 'b', 'c'}, '_parse_list: точка с запятой тоже разделитель')
check(_parse_list('') == frozenset() and _parse_list(None) == frozenset(),
      '_parse_list: пустое окружение -> пустое множество')

print('\n== 2. Флаги окружения ==')
check(all(env_flag('X', environ={'X': v}) for v in ('1', 'true', 'YES', 'on', ' Да ')),
      'env_flag: 1/true/yes/on/да — правда')
check(all(not env_flag('X', environ={'X': v}) for v in ('0', 'false', 'no', '', 'off')),
      'env_flag: 0/false/no/пусто — ложь')
check(env_flag('MISSING_FLAG', default=True) is True, 'env_flag: отсутствие -> default')

print('\n== 3. Режим по умолчанию — LEAN (лёгкий боевой состав) ==')
enabled, disabled = select_cog_files(ALL_FILES)
check(set(enabled) == LEAN_COGS, 'lean: без флагов грузится ровно боевой keep-лист')
check(sorted(set(NON_HELPERS) - set(LEAN_COGS)) == disabled,
      'lean: вся «веселуха» — в спящих')
missing_lean = sorted(f for f in LEAN_COGS if f not in ALL_SET)
check(missing_lean == [], f'LEAN_COGS: все файлы на диске {missing_lean}')
for dead in ('economy_cog.py', 'level_cog.py', 'fun_cog.py', 'minigames.py',
             'giveaway.py', 'starboard.py', 'birthday.py', 'karma.py',
             'achievements.py', 'duels.py', 'quiz.py', 'profile.py',
             'leaderboard.py', 'join_to_create.py', 'counting.py',
             'anime_daily.py', 'reminders.py', 'scheduler.py', 'triggers.py',
             'events.py', 'meeting.py', 'reaction_roles_cog.py', 'autorole_join.py'):
    assert dead in disabled, dead
check(True, 'lean: экономика/игры/уровни/ивенты/соц-системы — спят')
for keep in ('moderation.py', 'moderation_cog.py', 'warnings.py',
             'temp_moderation.py', 'proof_cog.py', 'auto_filter.py',
             'antiraid.py', 'verification.py',
             'appeals.py', 'reports.py', 'logs.py', 'log_menu.py',
             'staff_apply.py',
             'music_cog.py', 'voice_commands.py', 'voice_tracker.py',
             'ai_chat.py', 'ai_moderation.py',
             'welcome_cog.py', 'welcome_card.py', 'welcome_pro.py',
             'afk.py', 'help.py', 'cog_manager.py'):
    assert keep in enabled, keep
check(True, 'lean: модерация/репорты/музыка/AI/приветствие/логи/afk — живы')
for asleep in ('tag_jail.py', 'sla_cog.py', 'mod_report.py',
               'health.py', 'feature_flag_cog.py'):
    assert asleep in disabled, asleep
check(True, 'lean: tag_jail/sla/mod_report/health/flags — спят (чистка команд)')
for awake_shield in ('security.py', 'anti_alt.py', 'impersonation.py', 'ai_moderation.py'):
    assert awake_shield in enabled, awake_shield
check(True, 'lean: ЩИТ проснулся — security/anti-alt/impersonation/ai-moderation в боевом профиле')
check(not any(is_helper(f) for f in enabled), 'lean: хелперы не загружаются никогда')
check(CORE_COGS <= LEAN_COGS and MOD_LEAN_COGS <= LEAN_COGS
      and TICKET_LEAN_COGS <= LEAN_COGS and MUSIC_COGS <= LEAN_COGS
      and AI_LEAN_COGS <= LEAN_COGS and WELCOME_LEAN_COGS <= LEAN_COGS,
      'lean: состав = ядро + модерация + репорты + музыка + AI + приветствие')
check(not set(enabled) & set(disabled)
      and len(enabled) + len(disabled) == len(NON_HELPERS),
      'lean: разбиение без пересечений и потерь')

print('\n== 3.1. BOT_FULL=1 — полный состав (возврат всего) ==')
enabled_f, disabled_f = select_cog_files(ALL_FILES, full=True)
_NON_HELPERS_LIVE = sorted(set(NON_HELPERS) - RETIRED_COGS)
check(enabled_f == _NON_HELPERS_LIVE
      and sorted(disabled_f) == sorted(set(NON_HELPERS) & RETIRED_COGS),
      'full: грузятся все коги кроме хелперов и покоящихся')
check('dm_report.py' in RETIRED_COGS
      and 'dm_report.py' not in enabled_f,
      'покой: dm_report (/report-дубль) не грузится даже в full')
check(not any(is_helper(f) for f in enabled_f), 'full: хелперы не загружаются никогда')

print('\n== 4. Классификация модер-ядра здорова ==')
missing = sorted(f for f in MOD_ONLY_COGS if f not in ALL_SET)
check(missing == [], f'MOD_ONLY_COGS: все файлы существуют на диске (опечаток нет) {missing}')
check(CORE_COGS <= MOD_ONLY_COGS and MODERATION_COGS <= MOD_ONLY_COGS and
      not (CORE_COGS & MODERATION_COGS),
      'списки: core+moderation = mod_only, пересечений нет')
check(not (MOD_ONLY_COGS & HELPER_COGS), 'списки: хелперы не попали в mod_only')
# известные внутренние зависимости ядра (get_cog) — обе стороны живы в MOD_ONLY
for dep in ('warnings.py', 'tag_jail.py', 'impersonation.py', 'mod_kit.py',
            'mod_tools.py', 'mod_case.py', 'auto_filter.py', 'reports.py',
            'logs.py', 'proof_cog.py'):
    assert dep in MOD_ONLY_COGS, dep
check(True, 'ядро самодостаточно: warnings/tag_jail/impersonation/mod_*/reports/logs/proof — в списке')

print('\n== 5. MOD_ONLY=1 — «только модерация» ==')
enabled_m, disabled_m = select_cog_files(ALL_FILES, mod_only=True)
check(set(enabled_m) == MOD_ONLY_COGS, 'mod_only: загружается ровно keep-лист')
check(sorted(set(NON_HELPERS) - set(MOD_ONLY_COGS)) == disabled_m,
      'mod_only: всё остальное — в отключённых')
for fun in ('economy_cog.py', 'music_cog.py', 'fun_cog.py', 'minigames.py',
            'ai_chat.py', 'giveaway.py', 'level_cog.py', 'anime_daily.py',
            'starboard.py', 'welcome_cog.py'):
    assert fun in disabled_m, fun
check(True, 'mod_only: экономика/музыка/игры/AI-чат/раздачи/левелинг — выключены')
for keep in ('moderation.py', 'moderation_cog.py', 'warnings.py', 'temp_moderation.py',
             'antiraid.py', 'security.py', 'verification.py', 'auto_filter.py',
             'ai_moderation.py', 'reports.py', 'logs.py', 'proof_cog.py',
             'help.py', 'cog_manager.py'):
    assert keep in enabled_m, keep
check(True, 'mod_only: наказания/автомод/анти-рейд/репорты/журналы/демки/системное — живы')
check(not set(enabled_m) & set(disabled_m) and
      len(enabled_m) + len(disabled_m) == len(NON_HELPERS),
      'mod_only: разбиение без пересечений и потерь')

print('\n== 5.5 BOT_CORE=1 — «модерация + репорты + логи + AI» ==')
check(CORE_COGS <= CORE_ONLY_COGS and MODERATION_COGS <= CORE_ONLY_COGS
      and TICKET_COGS <= CORE_ONLY_COGS and AI_CHAT_COGS <= CORE_ONLY_COGS,
      'core: = ядро + модерация + репорты + AI-чат')
check(not (MUSIC_COGS & CORE_ONLY_COGS), 'core: музыка выключена (не входит)')
check('music_cog.py' not in CORE_ONLY_COGS and 'economy_cog.py' not in CORE_ONLY_COGS,
      'core: экономика/музыка/веселуха выключены')
missing_core = sorted(f for f in CORE_ONLY_COGS if f not in ALL_SET)
check(missing_core == [], f'CORE_ONLY_COGS: все файлы на диске {missing_core}')
enabled_c, disabled_c = select_cog_files(ALL_FILES, core=True)
check(set(enabled_c) == CORE_ONLY_COGS, 'core: загружается ровно keep-лист')
for fun in ('economy_cog.py', 'music_cog.py', 'fun_cog.py', 'level_cog.py',
            'giveaway.py', 'minigames.py', 'voice_commands.py', 'starboard.py'):
    assert fun in disabled_c, fun
check(True, 'core: экономика/музыка/игры/левелинг — выключены')
for keep in ('moderation.py', 'reports.py', 'sla_cog.py', 'staff_apply.py',
             'logs.py', 'log_menu.py', 'ai_chat.py', 'ai_moderation.py',
             'help.py', 'cog_manager.py'):
    assert keep in enabled_c, keep
check(True, 'core: модерация/репорты/логи/AI/системное — живы')
check(not set(enabled_c) & set(disabled_c)
      and len(enabled_c) + len(disabled_c) == len(NON_HELPERS),
      'core: разбиение без пересечений и потерь')

print('\n== 6. DISABLED_COGS / EXTRA_COGS ==')
e2, d2 = select_cog_files(ALL_FILES, full=True, disabled='Music_Cog.py, giveaway')
check('music_cog.py' in d2 and 'giveaway.py' in d2 and
      len(e2) == len(NON_HELPERS) - 2 - len(RETIRED_COGS),
      'DISABLED_COGS: работает в полном режиме, имена нечувствительны к виду')
e2l, d2l = select_cog_files(ALL_FILES, disabled='music_cog')
check('music_cog.py' in d2l and 'moderation.py' in e2l,
      'DISABLED_COGS: работает и поверх LEAN (выключает даже боевой модуль)')
e3, d3 = select_cog_files(ALL_FILES, mod_only=True, disabled='logs,ticket.py')
check('logs.py' in d3 and 'ticket.py' in d3,
      'DISABLED_COGS: может выключить даже модер-модуль (приоритет над keep)')
e4, d4 = select_cog_files(ALL_FILES, mod_only=True, extra='economy_cog, level_cog.py')
check('economy_cog.py' in e4 and 'level_cog.py' in e4 and 'music_cog.py' in d4,
      'EXTRA_COGS: возвращает отдельные модули поверх MOD_ONLY')
e5, _ = select_cog_files(ALL_FILES, mod_only=True, extra='_card_style,icons')
check('_card_style.py' not in e5 and 'icons.py' not in e5,
      'EXTRA_COGS: хелпер силой не включить')

print('\n== 7. Чтение из окружения ==')
env = {'MOD_ONLY': '1', 'EXTRA_COGS': 'fun_cog', 'DISABLED_COGS': '  minigames  '}
ee, de = select_from_environment(ALL_FILES, environ=env)
check('fun_cog.py' in ee and 'minigames.py' in de and 'economy_cog.py' in de,
      'select_from_environment: MOD_ONLY+EXTRA+DISABLED работают вместе')
ee2, de2 = select_from_environment(ALL_FILES, environ={})
check(set(ee2) == LEAN_COGS and sorted(set(NON_HELPERS) - LEAN_COGS) == de2,
      'select_from_environment: пустое окружение -> LEAN (лёгкий состав по умолчанию)')
ee3, de3 = select_from_environment(ALL_FILES, environ={'BOT_FULL': '1'})
check(ee3 == sorted(set(NON_HELPERS) - RETIRED_COGS)
      and de3 == sorted(set(NON_HELPERS) & RETIRED_COGS),
      'select_from_environment: BOT_FULL=1 -> полный состав (покой на месте)')
ee4, de4 = select_from_environment(ALL_FILES, environ={'EXTRA_COGS': 'economy_cog, quiz'})
check('economy_cog.py' in ee4 and 'quiz.py' in ee4 and 'fun_cog.py' in de4,
      'select_from_environment: EXTRA_COGS точечно будит модули поверх LEAN')

print('\n== 8. Интеграция с main.py ==')
with open(os.path.join(_REPO, 'main.py'), encoding='utf-8') as fp:
    main_src = fp.read()
check('from cogs_policy import select_from_environment' in main_src,
      'main.py: load_cogs использует select_from_environment')
check('SKIP_COGS' not in main_src, 'main.py: старый локальный SKIP_COGS убран (единый источник — cogs_policy)')
with open(os.path.join(_REPO, '.env.example'), encoding='utf-8') as fp:
    env_doc = fp.read()
check('BOT_FULL=0' in env_doc and 'MOD_ONLY=0' in env_doc and 'BOT_CORE=0' in env_doc
      and 'DISABLED_COGS' in env_doc and 'EXTRA_COGS' in env_doc,
      '.env.example: режим модулей задокументирован (BOT_FULL/MOD_ONLY/DISABLED/EXTRA)')

print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
