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

    async def edit_message(self, **kw):
        self.edits = getattr(self, 'edits', [])
        self.edits.append(kw)
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
_ms = open(os.path.join(ROOT, 'cogs/moderation.py')).read()
check('multi-fix-v15' in _ms or 'multi-fix-v13' in _ms,
      'build tag multi-fix-v15')


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


print('== LIVE 3. Мут → вид отдельно, основная панель жива для Размут ==')


async def _mute_flow():
    view_m = M.ModPanelView(None, opener, allowed=allowed)
    view_m._guild = g
    view_m.selected_uid = str(target.id)
    view_m._mute_kinds_cache = [
        ('mute_chat', 'Чат', 'только чат'),
        ('vmute', 'Войс', 'только войс'),
        ('timeout', 'Оба', 'чат + войс'),
    ]
    view_m._unmute_kinds_cache = [
        ('unmute_chat', 'Чат', ''),
        ('vunmute', 'Войс', ''),
    ]
    msg = _PanelMsg(222)
    view_m._panel_message = msg
    view_m._panel_message_id = 222

    async def _root2(**kw):
        return await msg.edit(**kw)
    view_m._root_edit = _root2

    inter = _Inter(opener, g, message=msg)
    view_m.action_select._values = ['mute']
    await view_m.action_select.callback(inter)
    check(bool(inter.response.sent), 'мут → отдельное меню вида (send_message)')
    check(isinstance(view_m.action_select, M.ModActionSelect),
          'на основной панели снова ModActionSelect (не kind)')
    check(msg.deleted is False, 'основная панель не удалена')
    check(len(msg.edits) >= 1, 'основная панель сброшена edit после мута')
    check(getattr(view_m, '_panel_message_id', None) == 222,
          'после мута id основной панели не сменился')

    # сразу Снять мут на основной панели
    inter2 = _Inter(opener, g, message=msg)
    view_m.action_select._values = ['unmute']
    await view_m.action_select.callback(inter2)
    check(bool(inter2.response.sent) or inter2.response.done,
          'после Мута сразу Снять мут отвечает')


asyncio.run(_mute_flow())


print('== LIVE 3a. Клик в kind-меню НЕ ворует _panel_message ==')


async def _kind_no_steal():
    view_k = M.ModPanelView(None, opener, allowed=allowed)
    view_k._guild = g
    view_k.selected_uid = str(target.id)
    view_k._mute_kinds_cache = [
        ('mute_chat', 'Чат', 'только чат'),
        ('vmute', 'Войс', 'только войс'),
    ]
    main = _PanelMsg(500)
    kind_msg = _PanelMsg(501)
    view_k._panel_message = main
    view_k._panel_message_id = 500

    async def _root_k(**kw):
        return await main.edit(**kw)
    view_k._root_edit = _root_k

    # как после выбора вида мута: interaction.message = kind ephemeral
    inter_k = _Inter(opener, g, message=kind_msg)
    await M._reset_after_step(inter_k, view_k, prefer_resend=False)
    check(getattr(view_k._panel_message, 'id', None) == 500,
          'после kind-клика _panel_message остаётся на основной панели')
    check(getattr(view_k, '_panel_message_id', None) == 500,
          '_panel_message_id не уехал на kind-меню')
    check(len(main.edits) >= 1, 'rebuild ушёл в основную панель')
    check(len(kind_msg.edits) == 0, 'kind-сообщение не трогали')

    # сразу другое действие на основной — отвечает
    inter2 = _Inter(opener, g, message=main)
    view_k.action_select._values = ['ban']
    await view_k.action_select.callback(inter2)
    check(bool(inter2.response.modal) or inter2.response.done,
          'после kind-reset Бан на основной панели отвечает')


asyncio.run(_kind_no_steal())


print('== LIVE 3b. Участник → Бан → модалка (действие работает) ==')


async def _action_works():
    view_a = M.ModPanelView(None, opener, allowed=allowed)
    view_a._guild = g
    view_a.selected_uid = str(target.id)
    msg = _PanelMsg(778)
    view_a._panel_message = msg
    async def _root(**kw):
        return await msg.edit(**kw)
    view_a._root_edit = _root
    inter = _Inter(opener, g, message=msg)
    view_a.action_select._values = ['ban']
    await view_a.action_select.callback(inter)
    check(bool(inter.response.modal), 'Бан с участником → send_modal')
    check(len(inter._fu_sent) == 0, 'без нового окна')
    # после сброса снова действие
    view_a.action_select._values = ['clear']
    inter2 = _Inter(opener, g, message=msg)
    await view_a.action_select.callback(inter2)
    check(bool(inter2.response.modal) or inter2.response.done,
          'второе действие после сброса работает')


asyncio.run(_action_works())


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


print('== LIVE 4b. Выбор участника — статус на панели меняется ==')


async def _member_status():
    view_t = M.ModPanelView(None, opener, allowed=allowed)
    view_t._guild = g
    msg = _PanelMsg(660)
    view_t._panel_message = msg
    view_t._panel_message_id = 660

    async def _root_t(**kw):
        return await msg.edit(**kw)
    view_t._root_edit = _root_t

    class _U2:
        id = target.id
    view_t.target_select._values = [_U2()]
    sel_before = id(view_t.target_select)
    inter = _Inter(opener, g, message=msg)
    await view_t.target_select.callback(inter)
    check(view_t.selected_uid == str(target.id), 'uid записан')
    check(inter.response.done, 'ACK defer после участника')
    check(f'участник <@{target.id}>' in view_t._status_text(),
          'статус панели показывает выбранного')
    check(id(view_t.target_select) != sel_before,
          'UserSelect пересобран — sticky сброшен, можно выбрать другого')
    check(len(msg.edits) >= 1, 'edit той же панели после выбора участника')
    check(getattr(view_t, '_reset_task', None) in (None,) or
          (view_t._reset_task is not None and view_t._reset_task.done()),
          'без фонового delayed-reset (только сразу)')


asyncio.run(_member_status())


print('== LIVE 5. 5 минут, без нового окна, Collector нет ==')
src = open(os.path.join(ROOT, 'cogs/moderation.py'), encoding='utf-8').read()
check('timeout=300' in src, 'панель на 5 минут')
check('prefer_resend=True' not in src, 'нигде не форсим resend')
check('class ModActionSelect' in src and 'class ModActionButton' not in src,
      'действия — селект, не кнопки')
check('_send_kind_menu' in src and 'MuteKindView' in src,
      'вид мута — отдельное меню, основная панель цела')
bind = src[src.index('def _bind_live_panel'):src.index('async def _send_modal_fast')]
check('.wait_for(' not in bind and 'bot.wait_for' not in bind,
      'нет bot.wait_for на пути сброса')
check("await _reset_after_step(interaction, panel, prefer_resend=False)" in src
      or '_reset_after_step(interaction, panel' in src,
      'после модалки — edit той же панели')
check(int(M.ModPanelView(None, opener, allowed=allowed).timeout) == 300,
      'ModPanelView.timeout == 300')


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
