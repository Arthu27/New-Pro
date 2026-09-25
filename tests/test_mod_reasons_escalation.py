# -*- coding: utf-8 -*-
"""Причины модпанели 1.1–1.9 + эскалации без +2.
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
# ярлык селекта — только номер
opts = MR.select_options_data()
check(all(o['label'] == o['value'] == c
          for o, c in zip(opts, codes)), 'label/value = номер')
check(all('Бан' not in o['description'] and 'Варн' not in o['description']
          for o in opts), 'в description нет строк наказания Бан/Варн')
fmt = MR.format_reason('1.9')
check(fmt.startswith('1.9 — ') and 'неадекватное' in fmt.lower(),
      f'format_reason 1.9: {fmt[:60]}…')
check('SoundPad' in MR.text_for('1.7'), '1.7 — SoundPad')
check(MR.resolve_stored_reason('1.2').startswith('1.2 — '),
      'resolve кода → полный текст')
check(len(MR.RULES_NOTES) >= 2, 'есть доп.инфо / авто-варн примечания')

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
# Минимальный stub без полного бота: вызываем _recent_* через класс
import json
from types import SimpleNamespace

# подгружаем только методы счётчиков — через инстанс без bot
sys.path.insert(0, ROOT)
# Импорт moderation тянет discord — ок в venv
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
