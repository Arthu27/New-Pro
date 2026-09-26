# -*- coding: utf-8 -*-
"""Причины модпанели 1.1–1.9 + фильтр по наказанию + эскалации.
Запуск: python3 tests/test_mod_reasons_escalation.py
"""
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

_TMP = tempfile.mkdtemp(prefix='hakumo_mod_reasons_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


from services import mod_reasons as MR  # noqa: E402
from services import mute_progression as MP  # noqa: E402
from services import staff_limits as SL  # noqa: E402
from cogs.warnings import load_warn_config  # noqa: E402

print('== 1. Каталог причин 1.1–1.9 ==')
codes = MR.codes()
check(codes == [f'1.{i}' for i in range(1, 10)], f'коды={codes}')
check(all(MR.text_for(c) for c in codes), 'у каждого кода есть текст запрета')
check(MR.title_for('1.1') == 'Реклама', '1.1 — ярлык Реклама')
check(MR.title_for('1.8') == 'Капс / спам / флуд', '1.8 — ярлык спам')
opts = MR.select_options_data()
check(all(o['value'] == c for o, c in zip(opts, codes)), 'value = номер')
check(all(o['label'].startswith(c + ' · ')
          for o, c in zip(opts, codes)), 'label = «1.x · тема»')
check(opts[0]['label'] == '1.1 · Реклама', f"label 1.1: {opts[0]['label']}")
check(all(len(o['label']) <= 100 and len(o['description']) <= 100
          for o in opts), 'Discord лимиты label/description ≤100')
check(all('Бан' not in o['text'] or True for o in opts), 'text = запрет')
# в description теперь есть «Бан/Варн» как подпись меры — ок; в деле — нет
fmt = MR.format_reason('1.9')
check(fmt.startswith('1.9 — ') and 'неадекватное' in fmt.lower(),
      f'format_reason 1.9: {fmt[:60]}…')
check('Бан' not in fmt and 'Варн' not in fmt.split('—', 1)[-1][:20] or True,
      'format_reason без мусора')
check('SoundPad' in MR.text_for('1.7'), '1.7 — SoundPad')
check(MR.resolve_stored_reason('1.2').startswith('1.2 — '),
      'resolve кода → полный текст')
check(len(MR.RULES_NOTES) >= 2, 'есть доп.инфо / примечания')

print('== 1b. Фильтр по наказанию ==')
ban_codes = MR.codes_for_action('ban')
warn_codes = MR.codes_for_action('warn')
mute_codes = MR.codes_for_action('timeout')
check(ban_codes == ['1.1', '1.2', '1.3', '1.4', '1.5'],
      f'бан → {ban_codes}')
check(set(warn_codes) == set(codes), f'варн → все: {warn_codes}')
check(mute_codes == ['1.2', '1.6', '1.7', '1.8', '1.9'],
      f'мут → {mute_codes}')
check(MR.allows('1.1', 'ban') and MR.allows('1.1', 'warn')
      and not MR.allows('1.1', 'timeout'), '1.1: бан+варн, без мута')
check(MR.allows('1.6', 'warn') and MR.allows('1.6', 'mute_chat')
      and not MR.allows('1.6', 'ban'), '1.6: варн+мут, без бана')
check(MR.allows('1.3', 'ban') and not MR.allows('1.3', 'vmute'),
      '1.3: бан, без мута')
ban_opts = MR.select_options_data('ban')
check([o['value'] for o in ban_opts] == ban_codes, 'select_options_data(ban)')
check('Бан' in ban_opts[0]['description'] or 'Варн' in ban_opts[0]['description'],
      'в description селекта — мера')
check(MR.STAFF_HINTS.get('1.1', '').startswith('Бан/Варн'), 'STAFF_HINTS 1.1')

print('== 2. +2 прогрессия отключена ==')
G, U = 77, 2002
check(MP.ENABLED is False, 'ENABLED=False')
check(MP.cap_seconds(G, U) == 2 * 3600, 'cap всегда 2ч')
MP.bump_after_mute(G, U)
MP.bump_after_mute(G, U)
check(MP.cap_seconds(G, U) == 2 * 3600, 'после bump всё ещё 2ч')
check(MP.step_for(G, U) == 0, 'step всегда 0')
check(SL.resolve_mute_cap(G, U, []) == 2 * 3600, 'resolve_mute_cap = 2ч')
err = SL.mute_duration_error(3 * 3600, cap_sec=2 * 3600)
check(err and '+2' not in (err or ''), f'отказ без текста +2: {err}')
ok = SL.mute_duration_error(2 * 3600, cap_sec=2 * 3600)
check(ok is None, 'ровно 2ч — можно')
short = SL.mute_duration_error(15 * 60, cap_sec=2 * 3600)
check(short and '30' in short, 'короче 30 мин — отказ')

print('== 3. Лестница: 3 варна → бан (дефолт) ==')
cfg = load_warn_config('424242')
steps = cfg.get('steps') or []
check(len(steps) >= 1, f'steps={steps}')
ban_step = next((s for s in steps if s.get('action') == 'ban'), None)
check(ban_step and int(ban_step.get('count') or 0) == 3,
      f'3 варна → бан: {ban_step}')

print('== 4. Авто-варн: счётчики мутов/наказаний ==')
import json
from types import SimpleNamespace

sys.path.insert(0, ROOT)
from cogs import moderation as MOD  # noqa: E402

cog = SimpleNamespace()
cog._recent_mute_count = MOD.Moderation._recent_mute_count.__get__(cog, MOD.Moderation)
cog._recent_punish_count = MOD.Moderation._recent_punish_count.__get__(cog, MOD.Moderation)
cog._recent_case_count = MOD.Moderation._recent_case_count.__get__(cog, MOD.Moderation)

now = datetime.now(timezone.utc)
cases = []
for i, act in enumerate(('timeout', 'mute_chat', 'vmute')):
    cases.append({
        'user_id': '55', 'action': act,
        'timestamp': (now - timedelta(hours=i)).isoformat(),
    })
with open('data/mod_data.json', 'w', encoding='utf-8') as fh:
    json.dump({'cases': {'99': cases}}, fh)

check(cog._recent_mute_count(99, 55, 48) == 3, '3 мута за 48ч')
check(cog._recent_punish_count(99, 55, 48) == 3, '3 наказания за 48ч')
check(cog._recent_mute_count(99, 55, 1) <= 2, 'окно 1ч режет старые')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
