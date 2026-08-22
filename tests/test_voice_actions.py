# -*- coding: utf-8 -*-
"""Голосовой контроль (/войс, ПКМ-меню войса): мут / размут / кик из войса.

Проверяем:
1. ПКМ-меню «Войс-мут», «Войс-размут», «Кик из войса» + /войс в дереве.
2. _voice_action: vmute → mute=True, vkick → move_to(None), vunmute → mute=False;
   дело сохраняется, подтверждение уходит модератору.
3. ReasonModal с require_proof: без доказательства handler не вызывается,
   со ссылкой — вызывается (передаёт reason + proof).

Запуск: python3 tests/test_voice_actions.py
"""
import asyncio, os, sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.makedirs('data', exist_ok=True)

import config
config.Config.DB_PATH = os.path.abspath('data/bot.db')

import discord
from discord import app_commands

from cogs.mod_tools import ModTools, ReasonModal

PASS = 0; FAIL = 0
def check(ok, msg):
    global PASS, FAIL
    if ok: PASS += 1; print(f'  PASS: {msg}')
    else: FAIL += 1; print(f'  FAIL: {msg}')

run = asyncio.new_event_loop().run_until_complete

# ── фейки ──
class FakeTree:
    def __init__(self): self.cmds = []
    def add_command(self, cmd): self.cmds.append(cmd)
    def remove_command(self, *a, **k): pass

class FakeMcog:
    def __init__(self): self.cases = []; self.logged = 0
    def save_case(self, gid, action, uid, mid, reason):
        self.cases.append((action, uid, reason)); return 1
    async def send_log(self, guild, e): self.logged += 1

class FakeBot:
    def __init__(self):
        self.tree = FakeTree()
        self._cogs = {'Moderation': FakeMcog()}
    def get_cog(self, name): return self._cogs.get(name)

class FakeMember:
    def __init__(self, uid, name):
        self.id = uid; self.name = name; self.display_name = name
        self.mention = f'<@{uid}>'; self.mute = None; self.moved = 'SENTINEL'
    async def edit(self, **kw):
        if 'mute' in kw: self.mute = kw['mute']
    async def move_to(self, ch, reason=None):
        self.moved = ch

class FakeResp:
    def __init__(self): self.sent = []; self.deferred = False
    def is_done(self): return True
    async def defer(self, ephemeral=False): self.deferred = True
    async def send_message(self, **kw): self.sent.append(kw)
    async def send(self, **kw): self.sent.append(kw)

class FakeInter:
    def __init__(self):
        self.guild = type('G', (), {'id': 777, 'name': 'G'})()
        self.user = FakeMember(99, 'Mod')
        self.response = FakeResp(); self.followup = FakeResp()

bot = FakeBot()
cog = ModTools(bot)

print('== 1. ПКМ-меню и /войс зарегистрированы ==')
ctx_names = [c.name for c in bot.tree.cmds if isinstance(c, app_commands.ContextMenu)]
check(all(n in ctx_names for n in ('Войс-мут', 'Войс-размут', 'Кик из войса')),
      f'ПКМ-меню войса на месте ({sorted(ctx_names)})')
slash_names = [c.name for c in getattr(ModTools, '__cog_app_commands__', [])]
check('войс' in slash_names, '/войс в коге (добавится в дерево через add_cog)')

print('== 2. _voice_action: действия ==')
m = FakeMember(1, 'Noisy')
inter_vmute = FakeInter()
run(cog._voice_action(inter_vmute, m, 'vmute', 'орал в войсе', 'https://x/p.png'))
check(m.mute is True, 'vmute → mute=True')
check(bot._cogs['Moderation'].cases[-1][0] == 'vmute', 'vmute → дело записано')
check(any('Войс-мут выдан' in getattr(k.get('embed'), 'description', '')
          for k in inter_vmute.followup.sent),
      'vmute → модератору ушло подтверждение')

m2 = FakeMember(2, 'Loud')
run(cog._voice_action(FakeInter(), m2, 'vkick', 'рейд войса', 'https://x/v.mp4'))
check(m2.moved is None, 'vkick → move_to(None) (отключён от канала)')

m3 = FakeMember(3, 'Quiet'); m3.mute = True
run(cog._voice_action(FakeInter(), m3, 'vunmute', '', None))
check(m3.mute is False, 'vunmute → mute=False')

print('== 3. ReasonModal: обязательное доказательство ==')
calls = []
async def handler(inter, reason, proof):
    calls.append((reason, proof))

def _set_val(modal, reason_val, proof_val):
    modal.reason = type('T', (), {'value': reason_val})()
    modal.proof = type('T', (), {'value': proof_val})()

rm = ReasonModal("Войс-мут: X", handler, require_proof=True)
_set_val(rm, 'шум', '')
run(rm.on_submit(FakeInter()))
check(calls == [], 'без доказательства handler НЕ вызван')

rm2 = ReasonModal("Войс-мут: X", handler, require_proof=True)
_set_val(rm2, 'шум', 'https://x/p.png')
run(rm2.on_submit(FakeInter()))
check(calls == [('шум', 'https://x/p.png')], 'со ссылкой handler вызван (reason + proof)')

os.system('rm -rf data')
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
