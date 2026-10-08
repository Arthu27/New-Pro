# -*- coding: utf-8 -*-
"""Voice stay: voice_targets + backoff + instance lock + davey в deps.

Запуск: python3 tests/test_voice_stay_fix.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_vstay_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== 1. voice_targets DB ==')
from services import voice_targets as VT  # noqa: E402
VT.ensure_table()
VT.set_target('main', 111, 222)
check(VT.get_target('main', 111) == 222, 'set/get target')
check(VT.list_targets('main') == [(111, 222)], 'list targets')
VT.clear_target('main', 111)
check(VT.get_target('main', 111) is None, 'clear = intentional leave')
# pending seed (guild=0) — раньше отбрасывался → event targets=[]
VT.set_target('event', 0, 1550986919981351043)
check(VT.get_target('event', 0) == 1550986919981351043,
      'pending guild=0 seed сохраняется')
check((0, 1550986919981351043) in VT.list_targets('event'),
      'pending в list_targets')
VT.clear_target('event', 0)

print('== 2. instance_lock ==')
from services import instance_lock as IL  # noqa: E402
check(IL.acquire('testbot') is True, 'first acquire OK')
# тот же PID — файл перезапишется; симулируем чужой живой PID
path = IL._lock_path('testbot2')
with open(path, 'w') as f:
    f.write(str(os.getpid()))  # свой PID — acquire всё равно ок
check(IL.acquire('testbot2') is True, 'same PID re-acquire OK')
IL.release('testbot')
IL.release('testbot2')

print('== 3. requirements: davey + PyNaCl ==')
req = open(os.path.join(ROOT, 'requirements.txt'), encoding='utf-8').read()
check('davey' in req, 'davey в requirements')
check('PyNaCl' in req, 'PyNaCl в requirements')
check('discord.py==2.7' in req or 'discord.py>=2.6' in req,
      'discord.py 2.6+')

print('== 4. voice_stay controller wiring ==')
vs = open(os.path.join(ROOT, 'services/voice_stay.py'), encoding='utf-8').read()
check('exponential' in vs.lower() or '_BACKOFF' in vs, 'backoff есть')
check('_BACKOFF_MAX = 300' in vs, 'max backoff 5 мин')
check('_WATCHDOG_SEC = 45' in vs, 'watchdog 45с')
check('force=True' in vs and 'disconnect(force=True)' in vs,
      'force disconnect для zombie')
check('timeout=30' in vs and 'reconnect=True' in vs, 'connect timeout=30 reconnect')
check('self_deaf=True' in vs, 'self_deaf')
check('soft-reconnect' in vs, 'soft-reconnect')
check('really_in_channel' in vs, 'Discord-truth')
check('await self._resolve_pending_targets()' in vs, 'async pending resolve')
check("reason='on_ready-fallback'" in open(
    os.path.join(ROOT, 'services/event_voice_bot.py'), encoding='utf-8').read()
    or 'on_ready-fallback' in open(
        os.path.join(ROOT, 'services/event_voice_bot.py'), encoding='utf-8').read(),
    'event on_ready fallback join')

print('== 5. main + event используют контроллер ==')
main = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
ev = open(os.path.join(ROOT, 'services/event_voice_bot.py'), encoding='utf-8').read()
check('voice_stay' in main and '_get_voice_ctrl' in main,
      'main → VoiceStayController')
check('instance_lock' in main, 'main instance_lock')
check('_get_event_ctrl' in ev and 'voice_stay' in ev,
      'event → VoiceStayController')
vs_full = open(os.path.join(ROOT, 'services/voice_stay.py'), encoding='utf-8').read()
check('SilenceAudioSource' in vs_full, 'looping silence source')
check('self_mute=False' in vs_full, 'connect без self_mute (UDP keepalive)')
check('silence_keepalive_enabled' in vs_full, 'silence auto/on gate')
check("or 'auto')" in vs_full or "or 'auto').strip()" in vs_full,
      'silence default auto (opus → ON)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
