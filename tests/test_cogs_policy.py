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
    CORE_ONLY_COGS, TICKET_COGS, AI_CHAT_COGS, VOICE_STATS_COGS, SLIM_COGS,
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
check(_norm_name('Welcome_Cog.py') == 'welcome_cog', '_norm_name: регистр и .py срезаются')
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
# Снятые с эксплуатации коги (тикеты, музыка) удалены с диска целиком —
# RETIRED_COGS пуст: «на покое, но на диске» больше никто не лежит.
check(set(enabled) == LEAN_COGS, 'lean: без флагов грузится ровно боевой keep-лист')
check(set(disabled) == set(NON_HELPERS) - set(enabled)
      and not (set(enabled) & set(disabled)),
      'lean: вся «веселуха» в спящих, без пересечений')
missing_lean = sorted(f for f in LEAN_COGS if f not in ALL_SET)
check(missing_lean == [], f'LEAN_COGS: все файлы на диске {missing_lean}')
# Выключенные модули больше не прячутся в спящих — они физически удалены
# с диска (по решению владельца: «удали сразу всех кого не используем»).
for gone in ('economy_cog.py', 'level_cog.py', 'fun_cog.py', 'minigames.py',
             'giveaway.py', 'starboard.py', 'birthday.py', 'karma.py',
             'duels.py', 'quiz.py', 'profile.py',
             'leaderboard.py', 'join_to_create.py', 'counting.py',
             'anime_daily.py', 'reminders.py', 'scheduler.py', 'triggers.py',
             'events.py', 'meeting.py', 'reaction_roles_cog.py',
             'autorole_join.py', 'weekly_crown.py', 'economy_shop.py',
             'leveling_engagement.py', 'social.py', 'polls.py',
             'suggestions.py', 'tag_jail.py', 'sla_cog.py',
             'lockdown.py', 'night_mode.py', 'media_only.py',
             'rejoin_roles.py', 'report_cog.py', 'staff_shifts.py',
             'verification.py', 'advanced_mod.py', 'mod_case.py',
             'mod_kit.py', 'mod_tools.py', 'proactive_mod.py',
             'dm_report.py', 'invite_tracker.py', 'mod_digest.py',
             'server_template.py', 'ticket.py'):
    assert gone not in ALL_SET, f'{gone} должна быть физически удалена с диска'
check(True, 'lean: экономика/игры/уровни/ивенты/соц-системы — физически удалены')
for keep in ('moderation.py', 'moderation_cog.py', 'warnings.py',
             'temp_moderation.py', 'proof_cog.py', 'auto_filter.py',
             'antiraid.py', 'age_verification.py',
             'appeals.py', 'reports.py', 'logs.py', 'log_menu.py',
             'staff_apply.py',
             'voice_tracker.py',
             'ai_chat.py', 'ai_moderation.py',
             'welcome_cog.py', 'welcome_card.py', 'welcome_pro.py',
             'afk.py', 'help.py', 'cog_manager.py'):
    assert keep in enabled, keep
# Музыка (/play) удалена из проекта 2026-09-01: файлов когов нет на диске,
# в составе они не фигурируют (ни enabled, ни disabled).
for gone_music in ('music_cog.py', 'voice_commands.py'):
    assert gone_music not in enabled and gone_music not in ALL_SET, gone_music
check(True, 'lean: модерация/репорты/AI/приветствие/логи/afk — живы; музыка удалена')
# Старая заглушка verification.py физически удалена — её заменил
# полноценный age_verification.py (карантин + анкета молодых аккаунтов).
assert 'verification.py' not in ALL_SET, 'verification.py должна быть удалена'
assert 'age_verification.py' in enabled, 'age_verification.py должна грузиться'
check(True, 'lean: верификация — age_verification жив, старая заглушка удалена')
for gone in ('tag_jail.py', 'sla_cog.py', 'mod_report.py',
             'health.py', 'feature_flag_cog.py'):
    assert gone not in ALL_SET, f'{gone} должна быть удалена (чистка команд)'
check(True, 'lean: tag_jail/sla/mod_report/health/flags — удалены (чистка команд)')
for awake_shield in ('security.py', 'anti_alt.py', 'impersonation.py', 'ai_moderation.py'):
    assert awake_shield in enabled, awake_shield
check(True, 'lean: ЩИТ проснулся — security/anti-alt/impersonation/ai-moderation в боевом профиле')
check(not any(is_helper(f) for f in enabled), 'lean: хелперы не загружаются никогда')
check(CORE_COGS <= LEAN_COGS and MOD_LEAN_COGS <= LEAN_COGS
      and TICKET_LEAN_COGS <= LEAN_COGS and VOICE_STATS_COGS <= LEAN_COGS
      and AI_LEAN_COGS <= LEAN_COGS and WELCOME_LEAN_COGS <= LEAN_COGS
      and 'voice_tracker.py' in LEAN_COGS,
      'lean: состав = ядро + модерация + репорты + войс-статистика + AI; музыка удалена')
check(not set(enabled) & set(disabled)
      and len(enabled) + len(disabled) == len(NON_HELPERS),
      'lean: разбиение без пересечений и потерь')

print('\n== 3.1. BOT_FULL=1 — полный состав (возврат всего) ==')
enabled_f, disabled_f = select_cog_files(ALL_FILES, full=True)
_NON_HELPERS_LIVE = sorted(set(NON_HELPERS) - RETIRED_COGS)
check(enabled_f == _NON_HELPERS_LIVE
      and sorted(disabled_f) == sorted(set(NON_HELPERS) & RETIRED_COGS),
      'full: грузятся все коги кроме хелперов и покоящихся')
check('dm_report.py' not in ALL_SET
      and 'dm_report.py' not in enabled_f,
      'удалён: dm_report (/report-дубль) больше нет на диске')
check(not any(is_helper(f) for f in enabled_f), 'full: хелперы не загружаются никогда')

print('\n== 4. Классификация модер-ядра здорова ==')
missing = sorted(f for f in MOD_ONLY_COGS if f not in ALL_SET)
check(missing == [], f'MOD_ONLY_COGS: все файлы существуют на диске (опечаток нет) {missing}')
check(CORE_COGS <= MOD_ONLY_COGS and MODERATION_COGS <= MOD_ONLY_COGS and
      not (CORE_COGS & MODERATION_COGS),
      'списки: core+moderation = mod_only, пересечений нет')
check(not (MOD_ONLY_COGS & HELPER_COGS), 'списки: хелперы не попали в mod_only')
# внутренние зависимости ядра (get_cog) — живые стороны в MOD_ONLY.
# tag_jail/mod_kit/mod_tools/mod_case физически удалены (чистка выключенных).
for dep in ('warnings.py', 'impersonation.py', 'auto_filter.py', 'reports.py',
            'logs.py', 'proof_cog.py', 'mod_plus.py', 'moderation_cog.py'):
    assert dep in MOD_ONLY_COGS or dep in HELPER_COGS, dep
for gone in ('tag_jail.py', 'mod_kit.py', 'mod_tools.py', 'mod_case.py'):
    assert gone not in ALL_SET, f'{gone} должна быть удалена'
check(True, 'ядро самодостаточно: warnings/impersonation/automod/reports/logs/proof — в списке')

print('\n== 5. MOD_ONLY=1 — «только модерация» ==')
enabled_m, disabled_m = select_cog_files(ALL_FILES, mod_only=True)
check(set(enabled_m) == MOD_ONLY_COGS, 'mod_only: загружается ровно keep-лист')
check(sorted(set(NON_HELPERS) - set(MOD_ONLY_COGS)) == disabled_m,
      'mod_only: всё остальное — в отключённых')
# Выключенные весёлые модули физически удалены с диска; в mod_only они
# не фигурируют вовсе (ни в enabled, ни среди файлов).
for fun in ('economy_cog.py', 'fun_cog.py', 'minigames.py',
            'giveaway.py', 'level_cog.py', 'anime_daily.py', 'starboard.py'):
    assert fun not in enabled_m and fun not in ALL_SET, fun
# AI-чат/приветствие живут на диске, но в mod_only отключены; музыка удалена с диска.
for off_now in ('ai_chat.py', 'welcome_cog.py'):
    assert off_now in disabled_m, off_now
for gone_music in ('music_cog.py', 'voice_commands.py'):
    assert gone_music not in ALL_SET, gone_music
check(True, 'mod_only: экономика/игры/раздачи/левелинг/музыка удалены; AI/приветствие — выключены')
for keep in ('moderation.py', 'moderation_cog.py', 'warnings.py', 'temp_moderation.py',
             'antiraid.py', 'security.py', 'age_verification.py', 'auto_filter.py',
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
check('voice_tracker.py' not in CORE_ONLY_COGS and 'music_cog.py' not in CORE_ONLY_COGS,
      'core: музыка не входит в ядро (фича удалена)')
check('economy_cog.py' not in CORE_ONLY_COGS,
      'core: экономика/веселуха выключены')
missing_core = sorted(f for f in CORE_ONLY_COGS if f not in ALL_SET)
check(missing_core == [], f'CORE_ONLY_COGS: все файлы на диске {missing_core}')
enabled_c, disabled_c = select_cog_files(ALL_FILES, core=True)
check(set(enabled_c) == CORE_ONLY_COGS, 'core: загружается ровно keep-лист')
# Удалённые весёлые модули не существуют на диске вовсе; живые «несердцевинные»
# (приветствие) в core-режиме отключены; музыка удалена с диска.
for gone in ('economy_cog.py', 'fun_cog.py', 'level_cog.py',
             'giveaway.py', 'minigames.py', 'starboard.py',
             'music_cog.py', 'voice_commands.py'):
    assert gone not in ALL_SET, gone
assert 'welcome_cog.py' in disabled_c, 'welcome_cog.py'
check(True, 'core: экономика/игры/левелинг/музыка удалены; приветствие выключено')
for keep in ('moderation.py', 'reports.py', 'staff_apply.py',
             'logs.py', 'log_menu.py', 'ai_chat.py', 'ai_moderation.py',
             'help.py', 'cog_manager.py'):
    assert keep in enabled_c, keep
check(True, 'core: модерация/репорты/логи/AI/системное — живы')
check(not set(enabled_c) & set(disabled_c)
      and len(enabled_c) + len(disabled_c) == len(NON_HELPERS),
      'core: разбиение без пересечений и потерь')

print('\n== 6. DISABLED_COGS / EXTRA_COGS ==')
e2, d2 = select_cog_files(ALL_FILES, full=True, disabled='Welcome_Cog.py, afk')
# welcome_cog жив в FULL — попадает в disabled по флагу; afk тоже выключается.
check('welcome_cog.py' in d2 and 'afk.py' in d2 and
      len(e2) == len(NON_HELPERS) - len(RETIRED_COGS) - 2,
      'DISABLED_COGS: работает в полном режиме, имена нечувствительны к виду')
e2l, d2l = select_cog_files(ALL_FILES, disabled='afk')
check('afk.py' in d2l and 'moderation.py' in e2l,
      'DISABLED_COGS: работает и поверх LEAN (выключает даже боевой модуль)')
e3, d3 = select_cog_files(ALL_FILES, mod_only=True, disabled='logs,appeals')
check('logs.py' in d3 and 'appeals.py' in d3,
      'DISABLED_COGS: может выключить даже модер-модуль/хелпер (приоритет над keep)')
# Удалённые модули (музыка) на диске отсутствуют — EXTRA их не возвращает;
# проверяем точечный возврат на живых спящих модулях.
e4, d4 = select_cog_files(ALL_FILES, mod_only=True, extra='welcome_cog.py, afk')
check('welcome_cog.py' in e4 and 'afk.py' in e4 and 'ai_chat.py' in d4,
      'EXTRA_COGS: возвращает отдельные живые модули поверх MOD_ONLY')
e4m, d4m = select_cog_files(ALL_FILES, mod_only=True, extra='music_cog')
check('music_cog.py' not in e4m and 'music_cog.py' not in d4m,
      'EXTRA_COGS: удалённый модуль (music_cog) не воскресает — файла нет')
e5, _ = select_cog_files(ALL_FILES, mod_only=True, extra='_card_style,icons')
check('_card_style.py' not in e5 and 'icons.py' not in e5,
      'EXTRA_COGS: хелпер силой не включить')

print('\n== 7. Чтение из окружения ==')
env = {'MOD_ONLY': '1', 'EXTRA_COGS': 'welcome_cog', 'DISABLED_COGS': '  afk  '}
ee, de = select_from_environment(ALL_FILES, environ=env)
check('welcome_cog.py' in ee and 'afk.py' in de and 'ai_chat.py' in de,
      'select_from_environment: MOD_ONLY+EXTRA+DISABLED работают вместе')
ee2, de2 = select_from_environment(ALL_FILES, environ={})
check(set(ee2) == LEAN_COGS and set(de2) == (set(NON_HELPERS) - LEAN_COGS),
      'select_from_environment: пустое окружение -> LEAN (лёгкий состав по умолчанию)')
ee3, de3 = select_from_environment(ALL_FILES, environ={'BOT_FULL': '1'})
check(ee3 == sorted(set(NON_HELPERS) - RETIRED_COGS)
      and de3 == sorted(set(NON_HELPERS) & RETIRED_COGS),
      'select_from_environment: BOT_FULL=1 -> полный состав (покой на месте)')
ee4, de4 = select_from_environment(ALL_FILES, environ={'EXTRA_COGS': 'welcome_cog'})
check('welcome_cog.py' in ee4 and 'music_cog.py' not in de4 and 'music_cog.py' not in ee4,
      'select_from_environment: EXTRA_COGS будит живой модуль; удалённая музыка не фигурирует')

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
