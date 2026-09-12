# -*- coding: utf-8 -*-
"""Тесты канальных охранников и прав хелпера.

Запуск: python3 tests/test_channel_guards.py
"""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_guards_')
os.chdir(_TMP)
os.makedirs('data', exist_ok=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.channel_guards import claimed_underage, message_has_media  # noqa: E402
from services.helper_acl_seed import (  # noqa: E402
    HELPER_ROLE_ID, HELPER_ACTIONS, apply_helper_acl_seed,
)

PASS = FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


print('== claimed_underage (<13 удаляем, 13+ нет) ==')
check(claimed_underage('мне 12') == 12, 'мне 12 → 12')
check(claimed_underage('Мне 11 лет') == 11, 'Мне 11 лет → 11')
check(claimed_underage('мне10') == 10, 'мне10 → 10')
check(claimed_underage('я 9') == 9, 'я 9 → 9')
check(claimed_underage('мне есть 12 лет') == 12, 'мне есть 12 лет → 12')
check(claimed_underage('возраст 10') == 10, 'возраст 10 → 10')
check(claimed_underage('возраст:11') == 11, 'возраст:11 → 11')
check(claimed_underage('ему 12 лет уже') == 12, '12 лет → 12')
check(claimed_underage('мне двенадцать') == 12, 'мне двенадцать → 12')
check(claimed_underage('мне одиннадцать лет') == 11, 'мне одиннадцать лет → 11')

# от 13 — НЕ удаляем
check(claimed_underage('мне 13') is None, 'мне 13 → None')
check(claimed_underage('мне 13 лет') is None, 'мне 13 лет → None')
check(claimed_underage('13 лет') is None, '13 лет → None')
check(claimed_underage('мне 14') is None, 'мне 14 → None')
check(claimed_underage('мне 16') is None, 'мне 16 → None')
check(claimed_underage('мне 18') is None, 'мне 18 → None')
check(claimed_underage('мне 18 лет') is None, 'мне 18 лет → None')
check(claimed_underage('18 лет') is None, '18 лет → None')
check(claimed_underage('мне 19') is None, 'мне 19 → None')
check(claimed_underage('мне тринадцать') is None, 'мне тринадцать → None')
check(claimed_underage('мне пятнадцать') is None, 'мне пятнадцать → None')
check(claimed_underage('мне двадцать') is None, 'мне двадцать → None')
check(claimed_underage('привет всем') is None, 'обычный текст → None')
check(claimed_underage('2 года на сервере') is None, '2 года на сервере → None')
check(claimed_underage('2 года') is None, 'голые «2 года» → None')
check(claimed_underage('мне 2 года') == 2, 'мне 2 года → 2')
check(claimed_underage('15 лет') is None, '15 лет → None (от 13 ок)')

check(claimed_underage('') is None, 'пустая строка')
check(claimed_underage(None) is None, 'None')


print('== message_has_media (shape) ==')


class _Att:
    def __init__(self, content_type='', filename=''):
        self.content_type = content_type
        self.filename = filename


class _Emb:
    def __init__(self, image=None, thumbnail=None, video=None):
        self.image = image
        self.thumbnail = thumbnail
        self.video = video


class _Msg:
    def __init__(self, attachments=None, embeds=None):
        self.attachments = attachments or []
        self.embeds = embeds or []


check(message_has_media(_Msg(attachments=[_Att('image/png', 'a.png')])),
      'png вложение → True')
check(message_has_media(_Msg(attachments=[_Att('video/mp4', 'a.mp4')])),
      'mp4 вложение → True')
check(message_has_media(_Msg(attachments=[_Att('', 'shot.JPEG')])),
      'JPEG по имени → True')
check(message_has_media(_Msg(embeds=[_Emb(image=object())])),
      'embed.image → True')
check(not message_has_media(_Msg(attachments=[_Att('text/plain', 'a.txt')])),
      'txt → False')
check(not message_has_media(_Msg()), 'пусто → False')


print('== helper_acl_seed constants ==')
check(HELPER_ROLE_ID == 948969471916249119, 'HELPER_ROLE_ID')
check(HELPER_ACTIONS == ('mute', 'purge'), 'только mute+purge')


print('== helper_acl_seed apply (без MAIN_GUILD) ==')
os.environ.pop('MAIN_GUILD_ID', None)
# без гильдии — мягкий отказ
rep = apply_helper_acl_seed(force=True, guild_id=0)
check(rep.get('applied') is False, 'без guild → not applied')
check('MAIN_GUILD' in (rep.get('reason') or '') or 'guild' in (rep.get('reason') or '').lower(),
      f"reason говорит про guild ({rep.get('reason')})")

# с фейковым guild + sqlite в tmp
os.environ['MAIN_GUILD_ID'] = '111222333444555666'
# permission_acl пишет в data/ через GuildData — в tmp cwd это ок
try:
    from services import permission_acl as pacl
    # очистим
    pacl.save_action_acl(111222333444555666, {
        'ban': ['803553848396349510'],
        'mute': ['803553848396349510'],
        'purge': ['803553848396349510'],
        'warn': ['803553848396349510'],
    })
    pacl.set_rule(111222333444555666, 'modpanel', ['803553848396349510'])
    # сбросить маркер
    import pathlib
    for p in pathlib.Path('data').glob('.helper_acl*'):
        p.unlink(missing_ok=True)
    rep2 = apply_helper_acl_seed(force=True, guild_id=111222333444555666)
    check(rep2.get('applied') is True, f'seed applied ({rep2})')
    acl = pacl.load_action_acl(111222333444555666)
    h = str(HELPER_ROLE_ID)
    check(h in [str(x) for x in acl.get('mute', [])], 'helper в mute')
    check(h in [str(x) for x in acl.get('purge', [])], 'helper в purge')
    check(h not in [str(x) for x in acl.get('ban', [])], 'helper НЕ в ban')
    check(h not in [str(x) for x in acl.get('warn', [])], 'helper НЕ в warn')
    cmd = pacl.load_acl(111222333444555666)
    check(h in [str(x) for x in cmd.get('modpanel', [])], 'helper в cmd modpanel')

    # actions_for_member видит только mute+clear
    from cogs.moderation import actions_for_member, mute_kinds_for

    class _Role:
        def __init__(self, rid):
            self.id = rid

    class _Member:
        def __init__(self, uid, roles):
            self.id = uid
            self.roles = roles
            self.bot = False
            self.guild_permissions = type('P', (), {
                'administrator': False, 'manage_messages': True,
                'moderate_members': False})()

    class _Guild:
        def __init__(self, gid):
            self.id = gid

    g = _Guild(111222333444555666)
    helper_m = _Member(42, [_Role(g.id), _Role(HELPER_ROLE_ID)])
    acts = [a[0] for a in actions_for_member(g, helper_m)]
    check('clear' in acts, f'helper видит clear: {acts}')
    check('mute' in acts, f'helper видит mute: {acts}')
    check('ban' not in acts, f'helper НЕ видит ban: {acts}')
    check('warn' not in acts, f'helper НЕ видит warn: {acts}')
    kinds = [k[0] for k in mute_kinds_for(g.id, helper_m)]
    check(kinds == ['mute_chat'], f'mute kinds только чат: {kinds}')
except Exception as ex:
    import traceback
    traceback.print_exc()
    check(False, f'helper seed integration: {ex}')


print(f'\n=== {PASS} passed, {FAIL} failed ===')
sys.exit(1 if FAIL else 0)
