# -*- coding: utf-8 -*-
"""voice_stay_health: Discord-truth vs zombie is_connected."""
import math
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


from services import voice_stay_health as H  # noqa: E402


print('== voice_client_alive ==')


class _VC:
    def __init__(self, connected=True, latency=0.05, channel_id=1):
        self._c = connected
        self.latency = latency
        self.channel = types.SimpleNamespace(id=channel_id)
        self.guild = object()

    def is_connected(self):
        return self._c


check(H.voice_client_alive(_VC()), 'alive ok')
check(not H.voice_client_alive(_VC(connected=False)), 'dead if not connected')
check(not H.voice_client_alive(_VC(latency=float('inf'))), 'dead if latency inf')
check(not H.voice_client_alive(_VC(latency=90.0)), 'dead if latency >60')

print('== really_in_channel zombie ==')


class _Mem:
    def __init__(self, ch_id=None):
        if ch_id is None:
            self.voice = None
        else:
            self.voice = types.SimpleNamespace(
                channel=types.SimpleNamespace(id=ch_id))


class _Guild:
    def __init__(self, me_ch=None):
        self.me = _Mem(me_ch)
        self.id = 1

    def get_member(self, _uid):
        return self.me


class _User:
    id = 42


class _Client:
    def __init__(self, vc=None, me_ch=None):
        self.user = _User()
        self.voice_clients = [vc] if vc else []
        g = _Guild(me_ch)
        self.guilds = [g]
        if vc is not None:
            vc.guild = g
        self._ch = types.SimpleNamespace(guild=g, id=99)

    def get_channel(self, cid):
        return self._ch


# healthy: discord + lib
vc = _VC(channel_id=99)
c = _Client(vc=vc, me_ch=99)
ok, _, why = H.really_in_channel(c, 99)
check(ok and why == 'ok', f'healthy → ok ({why})')

# latency high but Discord in + connected → still ok (не штормить)
vc_lat = _VC(channel_id=99, latency=float('inf'))
c_lat = _Client(vc=vc_lat, me_ch=99)
ok_lat, _, why_lat = H.really_in_channel(c_lat, 99)
check(ok_lat and why_lat == 'ok-latency-high',
      f'latency inf + discord in → ok-latency-high ({why_lat})')

# zombie: lib says in, discord voice=None
vc2 = _VC(channel_id=99)
c2 = _Client(vc=vc2, me_ch=None)
ok2, _, why2 = H.really_in_channel(c2, 99)
check(not ok2 and 'zombie' in why2, f'zombie detected ({why2})')

# out: both out
c3 = _Client(vc=None, me_ch=None)
ok3, _, why3 = H.really_in_channel(c3, 99)
check(not ok3 and why3 == 'out', f'both out ({why3})')

# soft reconnect
check(H.needs_soft_reconnect(0, 1000) is False, 'no soft if never joined')
check(H.needs_soft_reconnect(1, 1 + H.SOFT_RECONNECT_SEC + 1),
      'soft after interval')

print('== wiring in main + event ==')
main = open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read()
ev = open(os.path.join(ROOT, 'services/event_voice_bot.py'), encoding='utf-8').read()
check('really_in_channel' in main and 'force=True' in main,
      'main uses Discord-truth + force')
check('soft-reconnect' in main, 'main soft-reconnect')
check('really_in_channel' in ev and 'force=True' in ev,
      'event uses Discord-truth + force')
check('timeout=90' in main and 'timeout=90' in ev, 'connect timeout=90')
check("VOICE_SILENCE_PING') or '1'" in main
      or "VOICE_SILENCE_PING') or \"1\"" in main
      or "or '1').strip()" in main,
      'silence keepalive default ON in main')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
