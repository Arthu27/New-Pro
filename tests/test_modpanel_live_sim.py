# -*- coding: utf-8 -*-
"""Живая симуляция /modpanel multi-use-v8 — без реального Discord.

Прогоняет сценарии модератора end-to-end на моках:
  участник → действие → модалка → снова то же действие
  без нового окна (followup.send панели не вызывается)
  селект пересобран на том же message.id

Запуск: python3 tests/test_modpanel_live_sim.py
"""
import asyncio
import os
import shutil
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix='hakumo_live_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath('data/bot.db')
os.environ['OWNER_ID'] = '11'

import config  # noqa: E402
config.Config.DB_PATH = os.path.abspath('data/bot.db')

PASS = FAIL = 0
LOG = []


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
        LOG.append(('PASS', msg))
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')
        LOG.append(('FAIL', msg, extra))


from cogs import moderation as M  # noqa: E402
from services import punish_roles as PR  # noqa: E402


class _Member:
    def __init__(self, uid, guild=None, roles=None):
        self.id = uid
        self.name = f'u{uid}'
        self.display_name = self.name
        self.global_name = self.name
        self.guild = guild
        self.roles = roles or []
        self.mention = f'<@{uid}>'


class _Guild:
    def __init__(self, gid):
        self.id = gid
        self.members = []
        self.channels = []
        self.threads = []
        self.roles = []

    def get_member(self, uid):
        for m in self.members:
            if m.id == int(uid):
                return m
        return None


class _PanelMsg:
    def __init__(self, mid):
        self.id = mid
        self.edits = []
        self.attachments = []
        self.deleted = False

    async def edit(self, **kw):
        self.edits.append(kw)
        return self

    async def delete(self):
        self.deleted = True


class _Resp:
    def __init__(self):
        self.done = False
        self.modal = []
        self.sent = []
        self.deferred = False

    def is_done(self):
        return self.done

    async def send_modal(self, modal):
        self.modal.append(modal)
        self.done = True

    async def send_message(self, **kw):
        self.sent.append(kw)
        self.done = True

    async def defer(self, **kw):
        self.deferred = True
        self.done = True


class _Inter:
    def __init__(self, user, guild, message=None):
        self.user = user
        self.guild = guild
        self.guild_id = guild.id
        self.response = _Resp()
        self.message = message or _PanelMsg(9001)
        self.created_at = __import__('discord').utils.utcnow()
        self._fu_sent = []

        async def _fu_send(**kw):
            msg = _PanelMsg(7000 + len(self._fu_sent))
            self._fu_sent.append(kw)
            return msg

        self.followup = types.SimpleNamespace(send=_fu_send)

    async def edit_original_response(self, **kw):
        self.message.edits.append(kw)
        return self.message


# ── setup guild / ACL ──────────────────────────────────────────────
g = _Guild(424280)
opener = _Member(100, g)
target = _Member(3000000000000000300, g)
g.members = [opener, target]

PR.set_roles(g.id, mute=5001, vmute=5002, ban=5003)

# cache mute kinds so mute path works
allowed = [a for a in M.MODPANEL_ACTIONS
           if a[0] in ('mute', 'unmute', 'clear', 'ban', 'warn')]

print('== LIVE 1. Открытие панели: followup сохранён, одно сообщение ==')
view = M.ModPanelView(None, opener, allowed=allowed)
view._guild = g
view._mod_followup = None  # как до open — потом выставим
panel_msg = _PanelMsg(111)
view._panel_message = panel_msg
view._mod_followup = object()  # есть, но prefer_resend=False

async def _root(**kw):
    return await panel_msg.edit(**kw)

view._root_edit = _root
check(view.action_select is not None, 'есть action_select (не кнопки)')
check(not getattr(view, 'action_buttons', None),
      'action_buttons пусто — без кнопок')
check('multi-fix-v9' in open(os.path.join(ROOT, 'cogs/moderation.py')).read(),
      'build tag multi-use-v9')


print('== LIVE 2. Участник → Бан → модалка; то же сообщение; без нового окна ==')


async def _ban_twice():
    view.selected_uid = str(target.id)
    # 1-й бан
    inter1 = _Inter(opener, g, message=panel_msg)
    view.action_select._values = ['ban']
    sel_id_1 = id(view.action_select)
    await view.action_select.callback(inter1)
    check(bool(inter1.response.modal), '1-й Бан → send_modal')
    check(len(inter1._fu_sent) == 0, '1-й Бан: followup панели НЕ слали')
    check(panel_msg.deleted is False, 'панель не удалена')
    check(len(panel_msg.edits) >= 1, 'после модалки — edit той же панели')
    check(id(view.action_select) != sel_id_1,
          'селект пересобран (тот же пункт снова кликабелен)')
    check(view.selected_uid == str(target.id), 'участник сохранён')
    check(view.pending_action is None, 'pending сброшен после шага')
    check(view._panel_message is panel_msg
          or getattr(view._panel_message, 'id', None) == 111,
          'остаёмся на message id=111')

    edits_after_1 = len(panel_msg.edits)
    fu_before = len(inter1._fu_sent)

    # 2-й бан (тот же пункт) — Discord шлёт callback только после rebuild
    inter2 = _Inter(opener, g, message=panel_msg)
    view.action_select._values = ['ban']
    sel_id_2 = id(view.action_select)
    await view.action_select.callback(inter2)
    check(bool(inter2.response.modal), '2-й Бан → снова send_modal')
    check(len(inter2._fu_sent) == 0, '2-й Бан: нового окна нет')
    check(panel_msg.deleted is False, 'панель всё ещё не удалена')
    check(len(panel_msg.edits) > edits_after_1,
          '2-й шаг снова edit того же сообщения')
    check(id(view.action_select) != sel_id_2,
          'после 2-го шага селект снова свежий')
    check(view.selected_uid == str(target.id), 'участник всё ещё в памяти')


asyncio.run(_ban_twice())


print('== LIVE 3. Мут: подменю вида, основная панель не resend ==')


async def _mute_flow():
    view_m = M.ModPanelView(None, opener, allowed=allowed)
    view_m._guild = g
    view_m.selected_uid = str(target.id)
    # подставим kinds вручную (как кэш при открытии)
    view_m._mute_kinds_cache = [
        ('mute_chat', 'Чат', 'только чат'),
        ('vmute', 'Войс', 'только войс'),
        ('timeout', 'Оба', 'чат + войс'),
    ]
    msg = _PanelMsg(222)
    view_m._panel_message = msg
    view_m._mod_followup = types.SimpleNamespace(send=lambda **kw: None)

    async def _root2(**kw):
        return await msg.edit(**kw)
    view_m._root_edit = _root2

    inter = _Inter(opener, g, message=msg)
    view_m.action_select._values = ['mute']
    await view_m.action_select.callback(inter)
    # подменю вида — send_message (отдельное короткое меню, не «вторая панель»)
    check(bool(inter.response.sent) or bool(inter.response.modal)
          or inter.response.done,
          'мут с несколькими видами — ACK (подменю или модалка)')
    check(msg.deleted is False, 'основная панель не удалена после мута')
    # followup новой ГЛАВНОЙ панели не должен уходить через _resend
    # (prefer_resend=False); подменю может быть response.send_message
    check(len(inter._fu_sent) == 0,
          'главная панель не ушла через followup.send')


asyncio.run(_mute_flow())


print('== LIVE 4. Действие без участника → потом участник ==')


async def _order():
    view_o = M.ModPanelView(None, opener, allowed=allowed)
    view_o._guild = g
    view_o._mute_kinds_cache = [('timeout', 'Оба', '')]
    msg = _PanelMsg(333)
    view_o._panel_message = msg

    async def _root3(**kw):
        return await msg.edit(**kw)
    view_o._root_edit = _root3

    inter_a = _Inter(opener, g, message=msg)
    view_o.action_select._values = ['mute']
    await view_o.action_select.callback(inter_a)
    check(view_o.pending_action == 'mute', 'действие запомнено без участника')
    check(inter_a.response.done, 'ACK без модалки')
    check(not inter_a.response.modal, 'модалки ещё нет')

    class _U:
        id = target.id
    view_o.target_select._values = [_U()]
    inter_b = _Inter(opener, g, message=msg)
    await view_o.target_select.callback(inter_b)
    check(view_o.selected_uid == str(target.id), 'участник записан')
    check(bool(inter_b.response.modal) or bool(inter_b.response.sent)
          or inter_b.response.done,
          'после участника (pending был) — запуск действия')


asyncio.run(_order())


print('== LIVE 5. prefer_resend=False по умолчанию; Collector нет ==')
src = open(os.path.join(ROOT, 'cogs/moderation.py'), encoding='utf-8').read()
check('prefer_resend=False' in src, 'сброс без нового окна по умолчанию')
check(src.count('prefer_resend=True') == 0, 'нигде не форсим resend')
check('class ModActionSelect' in src and 'class ModActionButton' not in src,
      'действия — селект, не кнопки')
bind = src[src.index('def _bind_live_panel'):src.index('async def _send_modal_fast')]
check('.wait_for(' not in bind and 'bot.wait_for' not in bind,
      'нет bot.wait_for на пути сброса')
check("await _reset_after_step(interaction, panel, prefer_resend=False)" in src,
      'после модалки — edit той же панели')


print('== LIVE 6. Серия: clear → ban → clear на одном message ==')


async def _series():
    view_s = M.ModPanelView(None, opener, allowed=allowed)
    view_s._guild = g
    view_s.selected_uid = str(target.id)
    msg = _PanelMsg(444)
    view_s._panel_message = msg

    async def _root4(**kw):
        return await msg.edit(**kw)
    view_s._root_edit = _root4

    for act in ('clear', 'ban', 'clear'):
        inter = _Inter(opener, g, message=msg)
        view_s.action_select._values = [act]
        await view_s.action_select.callback(inter)
        check(bool(inter.response.modal) or inter.response.done,
              f'серия «{act}» — ACK/модалка')
        check(len(inter._fu_sent) == 0, f'серия «{act}» — без нового окна')
        check(msg.deleted is False, f'серия «{act}» — панель на месте')
        check(getattr(view_s._panel_message, 'id', None) == 444,
              f'серия «{act}» — тот же id=444')

    check(len(msg.edits) >= 3, f'серия: ≥3 edit на одном msg ({len(msg.edits)})')


asyncio.run(_series())

print(f'\n=== LIVE SIM PASS {PASS} / FAIL {FAIL} ===')
out = os.path.join(ROOT, '..', 'opt', 'cursor', 'artifacts')
# write summary to artifacts if possible
art = '/opt/cursor/artifacts'
try:
    os.makedirs(art, exist_ok=True)
    with open(f'{art}/modpanel-live-sim.txt', 'w') as f:
        f.write(f'PASS={PASS} FAIL={FAIL}\n')
        for row in LOG:
            f.write('|'.join(map(str, row)) + '\n')
except Exception as e:
    print('artifact skip:', e)

shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
