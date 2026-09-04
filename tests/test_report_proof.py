# -*- coding: utf-8 -*-
"""Доказательство из /report → архив демок + канал доказательств.

Заказ владельца 2026-09-04: «доказательство от /report пойдёт» в канал
доказательств. Проверяем сквозняк НАСТОЯЩИМ кодом: report_slash →
ProofCog._create_and_post → маршрут proof_channel → сообщение в канале +
запись в архиве + вечная локальная копия для панели.

Запуск: python3 tests/test_report_proof.py
"""
import asyncio
import json
import os
import sys
import tempfile
from types import SimpleNamespace as NS

os.environ['DB_PATH'] = os.path.join(tempfile.mkdtemp(prefix='rp_db_'), 'bot.db')
os.chdir(tempfile.mkdtemp(prefix='rp_ws_'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.makedirs('data', exist_ok=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from cogs import reports as R
from cogs import proof_cog as P
from services import reports_core as RC
from services import channel_routes as CR

PASS = 0
FAIL = 0


def check(ok, label, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


PROOF_CHANNEL_ID = 1312434963941167134   # канал владельца: «сюда пойдёт»
MOD_CHANNEL_ID = 1001


class FakeCh:
    def __init__(self, cid, name):
        self.id = cid
        self.name = name
        self.mention = f'<#{cid}>'
        self.sent = []

    async def send(self, **kw):
        self.sent.append(kw)
        return NS(id=len(self.sent) + 9000,
                  attachments=[NS(url=f'http://cdn/{self.name}/{len(self.sent)}.png')])


MOD_CH = FakeCh(MOD_CHANNEL_ID, 'модерация')
PROOF_CH = FakeCh(PROOF_CHANNEL_ID, 'доказательства')

guild = NS(id=777, name='Hakumo Test',
           get_channel=lambda cid: {MOD_CHANNEL_ID: MOD_CH,
                                    PROOF_CHANNEL_ID: PROOF_CH}.get(cid),
           get_role=lambda rid: None,
           get_member=lambda uid: None,
           members=[], text_channels=[], roles=[])

# маршрут доказательств — как у владельца
CR.set_route(777, 'proof_channel', PROOF_CHANNEL_ID)
# канал модерации из конфига репортов — карточка жалобы падает сюда
cfg = RC.load_cfg(777)
cfg['channel_id'] = MOD_CHANNEL_ID
RC.save_cfg(777, cfg)

reporter = NS(id=200, display_name='Репортёр', name='Репортёр',
              bot=False, mention='<@200>', display_avatar=NS(url='http://a/2'))
accused = NS(id=300, display_name='Нарушитель', name='Нарушитель',
             bot=False, mention='<@300>', display_avatar=NS(url='http://a/3'))


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *a, **kw):
        self.sent.append((a, kw))


class FakeResp:
    async def defer(self, *a, **kw):
        pass


interaction = NS(guild=guild, user=reporter, response=FakeResp(),
                 followup=FakeFollowup(),
                 channel=NS(id=999, mention='<#999>'),
                 client=None)

attachment = NS(content_type='image/png', filename='screenshot.png',
                size=2048, read=None)


async def _to_file():
    return NS(filename='screenshot.png')
attachment.to_file = _to_file


async def _read():
    return b'PNGDATA' * 100
attachment.read = _read

# настоящий ProofCog — конвейер демок без заглушек
pc = P.ProofCog(bot=None)
cog = R.Reports(bot=NS(get_cog=lambda name: pc if name == 'ProofCog' else None))

run = asyncio.new_event_loop()
run.run_until_complete(cog.report_slash.callback(
    cog, interaction, accused, 'кидает спам скринами',
    proof_file=attachment, proof=''))

print('== Жалоба доставлена ==')
check(len(MOD_CH.sent) == 1, 'карточка жалобы ушла в канал модерации',
      f'→ {len(MOD_CH.sent)}')
_card = MOD_CH.sent[0] if MOD_CH.sent else {}
check(' Новая жалоба' in ((_card.get('embed') or NS(title='')).title or ''),
      'в канале модерации — карточка «Новая жалоба»')

print('== Доказательство из /report → канал доказательств ==')
check(len(PROOF_CH.sent) == 1, 'демка ушла В КАНАЛ ДОКАЗАТЕЛЬСТВ (1312…34)',
      f'→ {len(PROOF_CH.sent)}')
_pmsg = PROOF_CH.sent[0] if PROOF_CH.sent else {}
check((_pmsg.get('embed') or NS(title='')).title and
      'Демка #1' in (_pmsg.get('embed')).title,
      'в канале доказательств — карточка демки #1',
      f'→ {(_pmsg.get("embed") or NS(title="")).title}')
check(_pmsg.get('file') is not None,
      'файл жалобы перезалит в канал доказательств (не только карточка)')

print('== Архив демок ==')
items = P.proof_list(777)
check(len(items) == 1, 'запись в архиве демок появилась', f'→ {len(items)}')
it = items[0] if items else {}
check(it.get('action') == 'репорт', 'действие помечено как «репорт»',
      f'→ {it.get("action")}')
check(str(it.get('user_id')) == '300' and str(it.get('mod_id')) == '200',
      'кого и кто (нарушитель / репортёр) записаны верно',
      f'→ {it.get("user_id")}/{it.get("mod_id")}')
check(it.get('channel_id') == PROOF_CHANNEL_ID,
      'доставка записана в канал владельца (1312434963941167134)',
      f'→ {it.get("channel_id")}')
check((it.get('media') or {}).get('kind') == 'image',
      'вечная локальная копия для панели сохранена',
      f'→ {it.get("media")}')

print('== Ответ репортёру ==')
_fu = interaction.followup.sent[-1][0][0] if interaction.followup.sent else ''
check('Доказательство сохранено' in _fu,
      'репортёру сообщили: доказательство сохранено', f'→ {_fu[:80]}')

print('== Жалоба без вложения не создаёт демок ==')
reporter2 = NS(id=201, display_name='Репортёр2', name='Репортёр2',
               bot=False, mention='<@201>', display_avatar=NS(url='http://a/4'))
interaction2 = NS(guild=guild, user=reporter2, response=FakeResp(),
                  followup=FakeFollowup(),
                  channel=NS(id=999, mention='<#999>'), client=None)
run.run_until_complete(cog.report_slash.callback(
    cog, interaction2, accused, 'без скрина', proof_file=None, proof=''))
check(len(P.proof_list(777)) == 1 and len(PROOF_CH.sent) == 1,
      'без вложения — демка НЕ создаётся',
      f'→ {len(P.proof_list(777))}/{len(PROOF_CH.sent)}')

print('== Падение канала доказательств НЕ ломает жалобу ==')
CR.set_route(777, 'proof_channel', 0)
guild.get_channel = lambda cid: MOD_CH if cid == MOD_CHANNEL_ID else None
reporter3 = NS(id=202, display_name='Репортёр3', name='Репортёр3',
               bot=False, mention='<@202>', display_avatar=NS(url='http://a/5'))
interaction3 = NS(guild=guild, user=reporter3, response=FakeResp(),
                  followup=FakeFollowup(),
                  channel=NS(id=999, mention='<#999>'), client=None)
run.run_until_complete(cog.report_slash.callback(
    cog, interaction3, accused, 'канал демок недоступен',
    proof_file=attachment, proof=''))
check(len(MOD_CH.sent) == 3 and
      'Жалоба отправлена' in interaction3.followup.sent[-1][0][0],
      'жалоба доставлена, даже если демка не записалась',
      f'→ {len(MOD_CH.sent)}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
