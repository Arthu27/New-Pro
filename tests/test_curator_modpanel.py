# -*- coding: utf-8 -*-
"""Куратор+хелпер должен видеть КУРАТОРСКУЮ /modpanel, не хелперскую.

Боевой кейс: у куратора роль 807030… и хелпер 948969… (или mod 803553…).
Хелперские лимиты mute/unmute/clear и узкий ACL mute+purge НЕ должны
схлопывать меню куратора.

Запуск: python3 tests/test_curator_modpanel.py
"""
import json
import os
import shutil
import sys
import tempfile

GID = 1312000000000000099
os.environ['MAIN_GUILD_ID'] = str(GID)

_TMP = tempfile.mkdtemp(prefix='hakumo_cur_panel_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402
config.Config.DB_PATH = os.path.abspath('data/bot.db')
config.Config.MAIN_GUILD_ID = GID

from services.staff_roles import (  # noqa: E402
    KNOWN_CURATOR_ROLE_ID, KNOWN_HELPER_ROLE_ID,
)
from services import staff_limits as SL  # noqa: E402
from services import staff_hierarchy as SH  # noqa: E402
from services import permission_acl as pacl  # noqa: E402
from cogs.moderation import actions_for_member, ModPanelView  # noqa: E402

CURATOR = int(KNOWN_CURATOR_ROLE_ID)
HELPER = int(KNOWN_HELPER_ROLE_ID)
MOD = 803553848396349510

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


class _Role:
    def __init__(self, rid):
        self.id = rid


class _Perms:
    administrator = False
    manage_messages = True
    ban_members = False
    manage_guild = False
    moderate_members = False


class _Member:
    def __init__(self, uid, role_ids, guild=None):
        self.id = uid
        self.bot = False
        self.roles = [_Role(r) for r in role_ids]
        self.guild_permissions = _Perms()
        self.guild = guild


class _Guild:
    def __init__(self, gid):
        self.id = gid
        self.owner_id = 1


# role_map: хелпер как known mod, куратор, классический mod
with open('data/role_map.json', 'w', encoding='utf-8') as fh:
    json.dump({
        str(MOD): 'mod',
        str(CURATOR): 'curator',
    }, fh)

guild = _Guild(GID)

print('== 1. Иерархия: куратор+хелпер = curator ==')
cur_h = _Member(42, [GID, CURATOR, HELPER], guild=guild)
check(SH.best_mapped_tier(cur_h) == 'curator',
      f'best_mapped_tier → curator ({SH.best_mapped_tier(cur_h)})')
check(SH.actor_panel_role(guild, cur_h) == 'curator',
      f'actor_panel_role → curator ({SH.actor_panel_role(guild, cur_h)})')
check(SH.target_panel_role(guild, cur_h) == 'curator',
      'target_panel_role → curator')

print('== 2. Хелперские лимиты НЕ сужают меню куратора ==')
# как helper_acl_seed: mute/unmute/clear/warn на роли хелпера
SL.set_role_limits(GID, HELPER, who='test', mute=3, unmute=3, clear=10, warn=1)
check(SL.role_scoped_actions(GID, [HELPER]) == {'mute', 'unmute', 'clear', 'warn'},
      'хелпер alone → узкое меню')
scoped = SL.role_scoped_actions(GID, [CURATOR, HELPER])
check(scoped is None,
      f'куратор+хелпер → полное меню (None), got={scoped}')
lm, _ = SL.effective_limits(GID, [CURATOR, HELPER])
check(lm.get('mute') == 7,
      f'куратор+хелпер mute=7 тира, не 3 ({lm.get("mute")})')
check(lm.get('warn') == 2,
      f'куратор+хелпер warn=2 ({lm.get("warn")})')

print('== 3. ACL: куратор наследует бан модеров, не теряет из‑за хелпера ==')
# узкий хелперский ACL + бан у модов (кураторского id в ban нет — регресс)
pacl.save_action_acl(GID, {
    'mute': [str(HELPER), str(MOD), str(CURATOR)],
    'purge': [str(HELPER), str(MOD), str(CURATOR)],
    'ban': [str(MOD)],          # куратора нет — раньше бан пропадал из меню
    'warn': [str(HELPER), str(MOD), str(CURATOR)],
    'kick': [str(MOD), str(CURATOR)],
    'timeout': [str(MOD), str(CURATOR)],
    'unban': [str(MOD), str(CURATOR)],
    'vmute': [str(MOD), str(CURATOR)],
})
check(pacl.check_action(GID, cur_h, 'ban') is True,
      'куратор наследует ban у mod (нет своего id в ACL)')
check(pacl.check_action(GID, cur_h, 'mute') is True,
      'куратор может mute')
helper_only = _Member(43, [GID, HELPER], guild=guild)
check(pacl.check_action(GID, helper_only, 'ban') is False,
      'чистый хелпер бан НЕ может')
check(pacl.check_action(GID, helper_only, 'mute') is True,
      'чистый хелпер mute может')
check(pacl.check_action(GID, helper_only, 'warn') is True,
      'чистый хелпер warn может')

print('== 4. actions_for_member: кураторская панель, не хелперская ==')
acts = [a[0] for a in actions_for_member(guild, cur_h)]
check('ban' in acts, f'куратор+хелпер видит ban: {acts}')
check('warn' in acts, f'куратор+хелпер видит warn: {acts}')
check('mute' in acts, f'куратор+хелпер видит mute: {acts}')
check('clear' in acts, f'куратор+хелпер видит clear: {acts}')
check(acts != ['mute', 'unmute', 'clear', 'warn']
      and set(acts) != {'mute', 'unmute', 'clear', 'warn'},
      f'это НЕ хелперское меню: {acts}')

h_acts = [a[0] for a in actions_for_member(guild, helper_only)]
check('ban' not in h_acts, f'хелпер без ban: {h_acts}')
check('mute' in h_acts and 'clear' in h_acts and 'warn' in h_acts,
      f'хелпер видит mute/clear/warn: {h_acts}')

print('== 5. Заголовок /modpanel · Куратор ==')
view = ModPanelView(None, cur_h, actions_for_member(guild, cur_h))
check(view._actor_label == 'куратор',
      f'badge label куратор ({view._actor_label!r})')
emb = view.panel_embed(guild)
check('Куратор' in (emb.title or ''),
      f'title содержит Куратор: {emb.title!r}')

print('== 6. Также с классическим mod-хелпером 803553 ==')
SL.set_role_limits(GID, MOD, who='test', mute=3, unmute=3, clear=10)
cur_mod = _Member(44, [GID, CURATOR, MOD], guild=guild)
acts2 = [a[0] for a in actions_for_member(guild, cur_mod)]
check('ban' in acts2 and 'warn' in acts2,
      f'куратор+mod-роль: полная панель {acts2}')
check(SL.role_scoped_actions(GID, [CURATOR, MOD]) is None
      or 'ban' in (SL.role_scoped_actions(GID, [CURATOR, MOD]) or ()),
      'scoped не схлопнут в helper-only')

print('== 7. Страховка: куратор+хелпер при ошибочном helper-scoped ==')
# Намеренно повесим те же лимиты на роль КУРАТОРА (как будто сид/руками
# скопировали хелперские) + хелпер — меню всё равно не должно быть
# хелперским: есть младшая роль → guard сбрасывает scoped.
SL.set_role_limits(GID, CURATOR, who='test', mute=3, unmute=3, clear=10, warn=1)
acts3 = [a[0] for a in actions_for_member(guild, cur_h)]
check('ban' in acts3 and 'warn' in acts3,
      f'страховка: куратор+хелпер при curator-limits mute/clear → полная '
      f'панель {acts3}')
# Чистый куратор без хелпера — свои mute/clear лимиты ОСТАЮТСЯ (не трогаем)
cur_only = _Member(45, [GID, CURATOR], guild=guild)
acts4 = [a[0] for a in actions_for_member(guild, cur_only)]
check(set(acts4) <= {'mute', 'unmute', 'clear', 'warn'} or 'ban' not in acts4,
      f'чистый куратор со своими mute-лимитами не раздувается: {acts4}')

print('== 8. Админ+хелпер: меню админа, не хелпера ==')
ADMIN_ROLE = 9000000000000000902
with open('data/role_map.json', 'w', encoding='utf-8') as fh:
    json.dump({
        str(MOD): 'mod',
        str(CURATOR): 'curator',
        str(ADMIN_ROLE): 'admin',
    }, fh)
admin_h = _Member(46, [GID, ADMIN_ROLE, HELPER], guild=guild)
check(SH.actor_panel_role(guild, admin_h) == 'admin',
      f'admin+helper actor → admin ({SH.actor_panel_role(guild, admin_h)})')
scoped_ah = SL.role_scoped_actions(GID, [ADMIN_ROLE, HELPER])
check(scoped_ah is None,
      f'admin+helper → полное меню (None), got={scoped_ah}')
acts_ah = [a[0] for a in actions_for_member(guild, admin_h)]
check('ban' in acts_ah and 'warn' in acts_ah,
      f'admin+helper видит полную панель: {acts_ah}')
# Discord Administrator без admin в role_map + helper
class _AdminPerms(_Perms):
    administrator = True


admin_discord = _Member(47, [GID, HELPER], guild=guild)
admin_discord.guild_permissions = _AdminPerms()
check(SH.actor_panel_role(guild, admin_discord) == 'admin',
      f'Discord admin+helper → admin ({SH.actor_panel_role(guild, admin_discord)})')
# Discord Administrator сам по себе прав в ACL не даёт (панель →
# Классические разрешения). Тир «admin» — для иерархии/лимитов; меню
# по ACL остаётся хелперским, пока админ не в role_map / ACL.
acts_ad = [a[0] for a in actions_for_member(guild, admin_discord)]
check('mute' in acts_ad,
      f'Discord admin+helper: ACL хелпера (mute) жив: {acts_ad}')
check(SH.best_mapped_tier(admin_discord) == 'helper',
      'mapped helper = helper, Discord admin выше только в actor_panel_role')

print('== 9. Финальный /modpanel V2 ==')
from cogs.moderation import ModTargetSelect  # noqa: E402
ts = ModTargetSelect(None)
ph = getattr(ts, 'placeholder', None) or ''
check(ph == '', f'placeholder участника пустой: {ph!r}')
from cogs.moderation import ModPanelView, MODPANEL_ACTIONS  # noqa: E402
view = ModPanelView(None, cur_h, list(MODPANEL_ACTIONS))
joined = '\n'.join(
    getattr(k, 'content', '') or ''
    for child in view.children
    for k in list(getattr(child, 'children', []) or []))
check('**Участник**' in joined and 'кого наказать' not in joined,
      'заголовок Участник без дубля в select')
check((getattr(view.target_select, 'placeholder', None) or '') == '',
      f'view select пустой: {getattr(view.target_select, "placeholder", None)!r}')
check('**Действие**' in joined and 'что сделать' not in joined,
      'заголовок Действие без дубля в select')
check((getattr(view.action_select, 'placeholder', None) or '') == '',
      f'action select пустой: {getattr(view.action_select, "placeholder", None)!r}')
check('Hakumo · модерация' not in joined,
      'без футера')
check('Панель модерации' in joined and 'HAKUMO' in joined,
      'шапка Панель модерации / HAKUMO')
check(view.has_components_v2(), 'Components V2 LayoutView')
check('в любом порядке' not in joined.lower(),
      'без «в любом порядке»')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
