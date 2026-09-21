# -*- coding: utf-8 -*-
"""Размут в /modpanel: один пункт → выбор чат / войс. Без авто-срока.

Запуск: python3 tests/test_modpanel_unmute.py
"""
import asyncio
import os
import shutil
import sys
import tempfile
import types

_TMP = tempfile.mkdtemp(prefix='hakumo_unmute_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath('data/bot.db')
os.environ['OWNER_ID'] = '11'

import config  # noqa: E402
config.Config.DB_PATH = os.path.abspath('data/bot.db')

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


from cogs import moderation as M  # noqa: E402
from services.permission_acl import set_action_rule, save_action_acl  # noqa: E402
from services import punish_roles as PR  # noqa: E402

print('== 1. В меню один пункт «Снять мут» и один «Мут» ==')
names = [a[0] for a in M.MODPANEL_ACTIONS]
src = open(os.path.join(ROOT, 'cogs/moderation.py'), encoding='utf-8').read()
check('unmute' in names and 'mute' in names, 'пункты mute и unmute в меню')
check('untimeout' not in names and 'vunmute' not in names
      and 'mute_chat' not in names and 'vmute' not in names
      and 'timeout' not in names,
      'виды мута/размута спрятаны из главного меню')
check('class UnmuteKindSelect' in src and 'class MuteKindSelect' in src,
      'второй селект чат/войс на месте и для мута, и для размута')

print('== 2. Виды размута по разрешениям ==')


class Role:
    def __init__(self, rid):
        self.id = rid


class Member:
    def __init__(self, uid, roles=()):
        self.id = uid
        self.roles = [Role(r) for r in roles]
        self.bot = False


GID = 424280
save_action_acl(GID, {})
set_action_rule(GID, 'mute', [601])
kinds = M.unmute_kinds_for(GID, Member(7, [601]))
check([k[0] for k in kinds] == ['unmute_chat'],
      f'только чат-мут → только «Чат»: {[k[0] for k in kinds]}')
set_action_rule(GID, 'vmute', [601])
kinds = M.unmute_kinds_for(GID, Member(7, [601]))
check([k[0] for k in kinds] == ['unmute_chat', 'vunmute', 'untimeout'],
      f'чат+войс → три варианта: {[k[0] for k in kinds]}')
set_action_rule(GID, 'mute', [])
kinds = M.unmute_kinds_for(GID, Member(7, [601]))
check([k[0] for k in kinds] == ['vunmute'],
      f'только войс → только «Войс»: {[k[0] for k in kinds]}')

print('== 3. unmute_chat не трогает микрофон ==')


class _Role:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name


class _Voice:
    mute = True
    channel = object()


class _Tgt:
    def __init__(self):
        self.id = 3000000000000000300
        self.name = 'T'
        self.display_name = 'T'
        self.mention = '<@3000000000000000300>'
        self.bot = False
        self.roles = []
        self.voice = _Voice()
        self.timed_out_until = object()
        self.edits = []
        self.removed = []
        self.added = []
        self.dms = []
        self.display_avatar = types.SimpleNamespace(url='http://a')

    async def add_roles(self, role, reason=None):
        self.added.append(role.id)

    async def remove_roles(self, role, reason=None):
        self.removed.append(role.id)

    async def edit(self, **kw):
        self.edits.append(kw)

    async def timeout(self, until, reason=None):
        self.timed_out_until = until

    async def send(self, embed=None, **kw):
        self.dms.append(embed)


class _Guild:
    id = GID
    name = 'G'
    owner_id = 1
    icon = None
    me = None
    members = []
    roles = []
    channels = []
    text_channels = []
    voice_channels = []

    def get_member(self, uid):
        return next((m for m in self.members if m.id == uid), None)

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == rid), None)

    def get_channel(self, cid):
        return None


class _Resp:
    def is_done(self):
        return True

    async def defer(self, ephemeral=False):
        pass

    async def send_message(self, **kw):
        self.kw = kw


class _Inter:
    def __init__(self, guild, user):
        self.guild = guild
        self.user = user
        self.response = _Resp()
        self.followup = types.SimpleNamespace(send=lambda **k: None)
        self.channel = None


PR.set_roles(GID, who='t', mute=5001, vmute=5002, ban=5003)
g = _Guild()
r_mute, r_vmute = _Role(5001, 'Мут'), _Role(5002, 'Войс')
g.roles = [r_mute, r_vmute]
tgt = _Tgt()
tgt.roles = [r_mute, r_vmute]
mod = Member(200, [601])
mod.display_name = 'Мод'
g.members = [tgt]
cog = M.Moderation.__new__(M.Moderation)
cog.bot = types.SimpleNamespace(get_cog=lambda n: None, user=types.SimpleNamespace(id=1))

ok, text = asyncio.run(cog.apply_panel_action(
    g, tgt, 'unmute_chat', reason='тест', actor='Панель'))
check(ok, 'unmute_chat выполнен', f'→ {text}')
check(5001 in tgt.removed, 'роль чат-мута снята')
check(not any(e.get('mute') is False for e in tgt.edits),
      'микрофон не открывали (это войс-размут)')

print('== 4. Владельца бота нельзя замьютить ==')
owner = _Tgt()
owner.id = 11
owner.bot = False
check(M._is_untouchable(g, owner), 'владелец бота в неприкасаемых')
check(not M._is_untouchable(g, tgt), 'обычный участник — можно наказывать')

print('== 5. Модалка мута без авто-срока ==')
src = open(os.path.join(ROOT, 'cogs/moderation.py'), encoding='utf-8').read()
check("placeholder=\"30, 60, 2ч\"" in src and 'default="60"' not in src
      and "default='60м'" not in src and "default='60'" not in src,
      'в поле срока нет заранее стоящих 60 минут')
check("placeholder='30, 60, 2ч'" in src,
      'ПКМ-мут тоже без авто-срока, только подсказка')

print('== 6. Бан: роль есть — комнаты не обходим по одной ==')
check('Semaphore' in src and "_punish_role(guild,'ban')" in src.replace(' ', ''),
      'изоляция комнат: параллельно, и пропускается если есть роль бана')
check('pending_action' in src,
      'панель помнит действие (порядок выбора свободный)')
check('thinking=False' in src, 'ack без спиннера «думает…»')
check('_root_edit' in src, 'сброс меню через токен /modpanel — тот же пункт снова кликается')

print('== 7. Порядок любой + повтор того же наказания ==')
set_action_rule(GID, 'timeout', [601])
set_action_rule(GID, 'mute', [601])
set_action_rule(GID, 'vmute', [601])
opener = Member(7, [601])
g7 = types.SimpleNamespace(id=GID, name='G', icon=None, owner_id=1,
                           get_member=lambda uid: None)


class _PMsg:
    def __init__(self):
        self.edits = []

    async def edit(self, **kw):
        self.edits.append(kw)


class _PResp:
    def __init__(self):
        self.done = False
        self.modal = []
        self.edits = []
        self.sent = []

    def is_done(self):
        return self.done

    async def edit_message(self, **kw):
        self.edits.append(kw)
        self.done = True

    async def send_modal(self, modal):
        self.modal.append(modal)
        self.done = True

    async def send_message(self, **kw):
        self.sent.append(kw)
        self.done = True

    async def defer(self, **kw):
        self.done = True


class _PInter:
    def __init__(self, user, guild):
        self.user = user
        self.guild = guild
        self.guild_id = guild.id
        self.response = _PResp()
        self.message = _PMsg()

        async def _fu(**kw):
            self.response.sent.append(kw)
        self.followup = types.SimpleNamespace(send=_fu)

    async def edit_original_response(self, **kw):
        self.message.edits.append(kw)


allowed = [a for a in M.MODPANEL_ACTIONS
           if a[0] in ('mute', 'unmute', 'clear')]
view = M.ModPanelView(cog, opener, allowed=allowed)
old_sel = view.action_select
inter = _PInter(opener, g7)
# эфемерка уже с баннером — refresh должен KEEP attachments, не File
class _Att:
    filename = 'hakumo_modpanel_banner_v15.png'
inter.message.attachments = [_Att()]
view.action_select._values = ['mute']
asyncio.run(view.action_select.callback(inter))
check(view.pending_action == 'mute' and not inter.response.modal,
      'действие без участника — запомнили, модалку не открыли')
# без участника: только ACK (defer), без rebuild LayoutView
check(inter.response.done,
      'действие без участника — ACK defer (<3с), без тяжёлого edit')

# теперь человек → выбор вида мута или кнопка формы
view.selected_uid = '3000000000000000300'
inter2 = _PInter(opener, g7)
asyncio.run(view.target_select.callback(inter2))
check(bool(inter2.response.modal) or bool(inter2.response.sent)
      or inter2.response.done,
      'после участника (действие уже выбрано) — вид мута / кнопка / ACK')

# наоборот: сначала человек, потом действие
view2 = M.ModPanelView(cog, opener, allowed=allowed)
view2.selected_uid = '3000000000000000300'
inter3 = _PInter(opener, g7)
view2.action_select._values = ['mute']
asyncio.run(view2.action_select.callback(inter3))
check(bool(inter3.response.modal) or bool(inter3.response.sent)
      or inter3.response.done,
      'сначала участник, потом действие — ACK (вид мута / кнопка формы)')

# ModTargetSelect: ACK + uid в памяти (без фонового rebuild — гонка с Действием)
view3 = M.ModPanelView(cog, opener, allowed=allowed)
view3._guild = g7
inter4 = _PInter(opener, g7)

class _User:
    id = 3000000000000000300
view3.target_select._values = [_User()]
asyncio.run(view3.target_select.callback(inter4))
check(view3.selected_uid == '3000000000000000300' and inter4.response.done,
      'выбор участника: ACK defer + uid в памяти')
check(getattr(view3, '_reset_task', None) in (None,) or
      (view3._reset_task is not None and view3._reset_task.done()),
      'после участника НЕТ фонового rebuild (не ломает Действие)')

# действие после участника — модалка
view3b = M.ModPanelView(cog, opener, allowed=allowed)
view3b._guild = g7
view3b.selected_uid = '3000000000000000300'
msg_b = _PMsg(); msg_b.id = 56; msg_b.attachments = []
view3b._panel_message = msg_b
async def _edit_b(**kw):
    return await msg_b.edit(**kw)
view3b._root_edit = _edit_b
inter_act = _PInter(opener, g7)
inter_act.message = msg_b
view3b.action_select._values = ['ban']
asyncio.run(view3b.action_select.callback(inter_act))
check(bool(inter_act.response.modal),
      'после участника действие Бан → send_modal (работает)')

# повтор выбора: rebuild даёт НОВЫЙ селект (Discord снова шлёт callback)
old = id(view2.action_select)
view2._rebuild(g7)
check(id(view2.action_select) != old,
      'после шага селект наказаний собирается заново — можно выбрать то же')

print('== 8. Серия действий: uid сохраняется, селект обновляется, клик отменяет reset ==')
view4 = M.ModPanelView(cog, opener, allowed=allowed)
view4.selected_uid = '3000000000000000300'
view4._guild = g7
edits = []

async def _root(**kw):
    edits.append(kw)

view4._root_edit = _root

async def _series():
    # короткий delay для теста
    inter5 = _PInter(opener, g7)
    view4.action_select._values = ['mute']
    # подменим schedule на быстрый delay через прямой вызов после callback
    await view4.action_select.callback(inter5)
    # callback ставит delay=1.5 — ускорим: отменим и поставим 0.05
    M._cancel_panel_reset(view4)
    M._schedule_panel_reset(inter5, view4, clear_pending=True, delay=0.05)
    check(view4._reset_task is not None and not view4._reset_task.done(),
          'после действия запланирован сброс селектов (серия)')
    sel_before = id(view4.action_select)
    await view4._reset_task
    check(id(view4.action_select) != sel_before,
          'после сброса — новый action_select (тот же пункт снова кликабелен)')
    check(view4.selected_uid == '3000000000000000300',
          'участник остаётся в памяти — серия без повторного выбора')
    check(view4.pending_action is None,
          'pending сброшен после действия — готов к новому пункту')
    check(bool(edits) or bool(getattr(inter5.message, 'edits', None)),
          'сброс пушит edit панели (message.edit / _root_edit)')

    # клик отменяет незавершённый reset (без гонки)
    view5 = M.ModPanelView(cog, opener, allowed=allowed)
    view5.selected_uid = '3000000000000000300'
    view5._guild = g7
    view5._root_edit = _root
    gen0 = int(getattr(view5, '_reset_gen', 0) or 0)
    M._schedule_panel_reset(inter5, view5, clear_pending=True, delay=5.0)
    task_long = view5._reset_task
    check(task_long is not None and not task_long.done(),
          'длинный reset task создан')
    inter6 = _PInter(opener, g7)
    view5.action_select._values = ['clear']
    await view5.action_select.callback(inter6)
    check(int(view5._reset_gen) > gen0,
          'клик «Действие» поднимает поколение / отменяет старый reset')
    check(view5._reset_task is not task_long,
          'старый длинный reset заменён (не конкурирует с новым кликом)')
    # дождаться, пока цикл доставит CancelledError старому task
    try:
        await asyncio.wait_for(task_long, timeout=0.5)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    check(task_long.cancelled() or task_long.done(),
          'старый длинный reset отменён кликом')

asyncio.run(_series())

print('== 9. Сброс правит живое сообщение клика + resend fallback ==')

class _PanelMsg:
    def __init__(self, mid, *, fail_edit=False):
        self.id = mid
        self.edits = []
        self.attachments = []
        self.deleted = False
        self._fail_edit = fail_edit

    async def edit(self, **kw):
        if self._fail_edit:
            raise RuntimeError('edit fail')
        self.edits.append(kw)
        return self

    async def delete(self):
        self.deleted = True


class _FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, **kw):
        msg = _PanelMsg(999)
        self.sent.append(kw)
        return msg


async def _msg_identity():
    view = M.ModPanelView(cog, opener, allowed=allowed)
    view.selected_uid = '3000000000000000300'
    view._guild = g7
    shown = _PanelMsg(111)
    stale = _PanelMsg(222)  # устаревшая ссылка — клик на другом msg
    view._panel_message = stale
    async def _root(**kw):
        return await stale.edit(**kw)
    view._root_edit = _root
    inter = _PInter(opener, g7)
    # interaction.message = то, на чём кликнули (видимая панель)
    inter.message = shown
    sel_before = id(view.action_select)
    await M._silent_reset_panel(inter, view)
    check(id(view.action_select) != sel_before, 'reset пересобрал селект')
    check(len(shown.edits) == 1, 'edit ушёл в interaction.message (клик)')
    check(len(stale.edits) == 0, 'устаревший _panel_message не трогали')
    check(view._panel_message is shown or getattr(view._panel_message, 'id', None) == 111,
          'панель привязана к живому сообщению клика')
    # второй «клик» того же действия — новый select примет callback
    view.action_select._values = ['mute']
    inter2 = _PInter(opener, g7)
    inter2.message = shown
    await view.action_select.callback(inter2)
    check(bool(inter2.response.modal) or bool(inter2.response.sent)
          or inter2.response.done,
          'после сброса второе действие снова ACK/модалка')

    # resend отключён — новое окно больше не создаём
    view_r = M.ModPanelView(cog, opener, allowed=allowed)
    view_r.selected_uid = '3000000000000000300'
    view_r._guild = g7
    broken = _PanelMsg(333, fail_edit=True)
    view_r._panel_message = broken
    fu = _FakeFollowup()
    view_r._mod_followup = fu
    ok = await M._resend_fresh_panel(view_r)
    check(ok is False, 'resend отключён — всегда False')
    check(not broken.deleted, 'старую эфемерку НЕ удаляем')
    check(len(fu.sent) == 0, 'followup.send новой панели нет')

    # _reset_after_step — edit той же панели, НЕ новое окно
    view_a = M.ModPanelView(cog, opener, allowed=allowed)
    view_a.selected_uid = '3000000000000000300'
    view_a._guild = g7
    view_a.pending_action = 'mute'
    live = _PanelMsg(444)
    view_a._panel_message = live
    fu2 = _FakeFollowup()
    view_a._mod_followup = fu2
    inter_a = _PInter(opener, g7)
    inter_a.message = live
    await M._reset_after_step(inter_a, view_a, prefer_resend=False)
    check(view_a.pending_action is None, 'после шага pending сброшен')
    check(len(fu2.sent) == 0, 'без новой эфемерки — только edit той же панели')
    check(len(live.edits) == 1, 'селекты сброшены edit на том же сообщении')
    check(view_a.selected_uid == '3000000000000000300',
          'участник сохранён для серии действий')
    check(getattr(view_a._panel_message, 'id', None) == 444,
          'остаёмся на том же сообщении панели')
    check(int(getattr(view_a, 'timeout', 0) or 0) == 300,
          'панель живёт 5 минут (timeout=300)')

asyncio.run(_msg_identity())

print('== 10. Нет Collector / нового окна; kind на той же панели ==')
src = open(M.__file__, encoding='utf-8').read()
bind = src[src.index('def _bind_live_panel'):src.index('async def _send_modal_fast')]
check('.wait_for(' not in bind and 'bot.wait_for' not in bind,
      'reset-хелперы без bot.wait_for')
check('_send_kind_menu' in src and 'MuteKindView' in src,
      'вид мута — отдельное меню MuteKindView')
check('multi-fix-v13' in src, 'build=multi-fix-v13 в логе открытия')
check('resend disabled' in src or 'return False' in src[src.index('async def _resend_fresh_panel'):
                                                          src.index('def _cancel_panel_reset')],
      'resend заглушка — новое окно запрещено')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
