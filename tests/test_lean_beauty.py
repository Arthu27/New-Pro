# -*- coding: utf-8 -*-
"""Страж красоты LEAN-состава: каждая команда — с описанием, по-русски,
без турецкого мусора и чужих брендов; Hakumo-кит эмбедов на месте.

Запуск: python3 tests/test_lean_beauty.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


for k in ('BOT_FULL', 'MOD_ONLY', 'BOT_SLIM', 'BOT_CORE', 'DISABLED_COGS', 'EXTRA_COGS'):
    os.environ.pop(k, None)

print('== 1. У каждой LEAN-команды есть красивое русское описание ==')
import cogs_policy as CP  # noqa: E402
from services import command_registry as CR  # noqa: E402

data = CR.catalog(force=True)
# Заказ владельца «как можно меньше»: боевое меню — 6 команд
# (modpanel, апелляция, update, afk, report, my-violations). Сетап-команды
# убраны в панель, /afk-remove удалён (AFK спадает авто), музыка снесена.
check(data['total'] == 6, f'lean-каталог собран ({data["total"]} команд после чистки)')
placeholder = [c['name'] for c in data['commands'] if c['desc'] == 'Описание скоро появится']
check(not placeholder, f'без описания не осталось ни одной команды {placeholder[:6]}')
non_ru = [c['name'] for c in data['commands']
          if not re.search('[а-яА-ЯёЁ]', c['desc'])]
check(not non_ru, f'описания по-русски у всех {non_ru[:6]}')

print('== 2. Hakumo-кит эмбедов ==')
from cogs import embed_utils as EU  # noqa: E402

for name in ('hakumo_embed', 'reply', 'bar', 'plural', 'fmt_duration',
             'mod_dm_embed', 'KINDS', 'GOLD', 'Hakumo_footer'):
    check(hasattr(EU, name), f'embed_utils экспортирует {name}')
check(len(EU.KINDS) >= 12, f'типов оформления KINDS ≥ 12 ({len(EU.KINDS)})')
import discord  # noqa: E402
e = EU.hakumo_embed('music', 'Тест', 'описание',
                    fields=[('Поле', 'значение', True)])
check(isinstance(e, discord.Embed) and e.description == 'описание'
      and e.fields and e.color.value == EU.GOLD,
      'hakumo_embed собирает фирменный эмбед')
check(EU.plural(1, 'трек', 'трека', 'треков') == 'трек'
      and EU.plural(3, 'трек', 'трека', 'треков') == 'трека'
      and EU.plural(7, 'трек', 'трека', 'треков') == 'треков'
      and EU.plural(11, 'трек', 'трека', 'треков') == 'треков',
      'плюрализация русского языка верна')
check(EU.fmt_duration(3723) == '1 ч 2 мин' and EU.fmt_duration(0) == '0 мин',
      'fmt_duration форматирует длительность')
check(EU.bar(0.5) == '██████░░░░░░' and EU.bar(1.0) == '█' * 12, 'прогресс-бар')

print('== 3. Турецкий мусор истреблён в боевых модулях ==')
TR = re.compile(r'(?i)\b(yardim|tekrar|hepsini|kullan\w*|ayarlar|guncel\w*|'
                r'yaz\b|ses\w*ten|benimle|yan\w*daki|listele\w*|kisiy\w*|'
                r'arka\w*as\w*|toplanti|haftalik|rapor-ayar|istatistik\b|'
                r'skoru\b|userya|bilgi\b)\b')
bad = []
for fn in sorted(CP.LEAN_COGS):
    src = open(os.path.join(ROOT, 'cogs', fn), encoding='utf-8').read()
    for i, line in enumerate(src.splitlines(), 1):
        if TR.search(line):
            bad.append(f'{fn}:{i}: {line.strip()[:70]}')
check(not bad, f'турецких слов-обрывков в lean-когах нет {bad[:4]}')

print('== 4. Чужие бренды вычищены ==')
junk = []
for fn in sorted(os.listdir(os.path.join(ROOT, 'cogs'))):
    if not fn.endswith('.py'):
        continue
    src = open(os.path.join(ROOT, 'cogs', fn), encoding='utf-8').read()
    if 'Aether' in src or 'AETHER' in src:
        junk.append(fn)
check(not junk, f'старый бренд Aether не встречается (бренд — Hakumo) {junk}')

print('== 5. Голос: трекер жив, музыкальные команды удалены ==')
# music_cog.py удалён вместе с системой /play (2026-09-01) — проверяем лишь
# голосовой трекер, который остаётся боевым (статистика времени в голосе).
check(not os.path.exists(os.path.join(ROOT, 'cogs', 'music_cog.py')),
      'music_cog.py физически удалён (система /play снесена)')
tracker = open(os.path.join(ROOT, 'cogs', 'voice_tracker.py'), encoding='utf-8').read()
check('on_voice_state_update' in tracker and 'def voice_seconds' in tracker,
      'голосовой трекер считает время (команды удалены, трекинг жив)')
check('voicetime' not in tracker and 'voiceleaderboard' not in tracker,
      'команды голосовой статистики удалены владельцем')
cogmgr = open(os.path.join(ROOT, 'cogs', 'cog_manager.py'), encoding='utf-8').read()
check('BOT_FULL' in cogmgr and 'Спят по профилю' in cogmgr,
      'менеджер модулей честно показывает спящие по профилю')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
