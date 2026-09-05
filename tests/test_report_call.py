# -*- coding: utf-8 -*-
"""/report = «Позвать модератора» (решение владельца 2026-09-05).

Что изменилось и что проверяем НАСТОЯЩИМ кодом (report_slash):
  • параметров «доказательство» больше НЕТ (ни файла, ни ссылки) — команда
    стала вызовом модератора, а не сбором улик;
  • сигнал уходит карточкой в канал модерации с тегом роли модераторов —
    «он отправит в чат модеров, и там уже разберём всё»;
  • карточка отвечает на вопросы: куда идти, кто вызвал, из-за кого, что
    случилось (+ голосовой канал вызывавшего, если он в войсе);
  • у модераторов на месте кнопки разбора (Принять/Отклонить/Открыть разбор);
  • вызывавшему сразу подтверждают: «Модератор вызван»;
  • дубль-вызов на того же участника — отказ;
  • конвейер демок (ProofCog) из /report больше не дёргается.

Запуск: python3 tests/test_report_call.py
"""
import asyncio
import inspect
import os
import sys
import tempfile
from types import SimpleNamespace as NS

os.environ['DB_PATH'] = os.path.join(tempfile.mkdtemp(prefix='rc_db_'), 'bot.db')
os.chdir(tempfile.mkdtemp(prefix='rc_ws_'))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.makedirs('data', exist_ok=True)

from cogs import reports as R           # noqa: E402
from services import reports_core as RC  # noqa: E402

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


MOD_CHANNEL_ID = 1001


class FakeCh:
    def __init__(self, cid, name):
        self.id = cid
        self.name = name
        self.mention = f'<#{cid}>'
        self.sent = []

    async def send(self, **kw):
        self.sent.append(kw)
        return NS(id=len(self.sent) + 9000)


MOD_CH = FakeCh(MOD_CHANNEL_ID, 'модерация')

MOD_ROLE_ID = 555
MOD_ROLE = NS(id=MOD_ROLE_ID, mention='<@&555>', name='Модерация')

guild = NS(id=777, name='Hakumo Test',
           get_channel=lambda cid: {MOD_CHANNEL_ID: MOD_CH}.get(cid),
           get_role=lambda rid: MOD_ROLE if rid == MOD_ROLE_ID else None,
           get_member=lambda uid: None,
           members=[], text_channels=[], roles=[])

# канал модерации и роль — из конфига репортов (панель / /report-setup)
cfg = RC.load_cfg(777)
cfg['channel_id'] = MOD_CHANNEL_ID
cfg['mod_role_id'] = str(MOD_ROLE_ID)
RC.save_cfg(777, cfg)

reporter = NS(id=200, display_name='Репортёр', name='Репортёр',
              bot=False, mention='<@200>', display_avatar=NS(url='http://a/2'),
              voice=NS(channel=NS(name='Общий')))
accused = NS(id=300, display_name='Нарушитель', name='Нарушитель',
             bot=False, mention='<@300>', display_avatar=NS(url='http://a/3'))


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *a, **kw):
        self.sent.append((a, kw))


class FakeResp:
    def __init__(self):
        self.msgs = []

    async def defer(self, *a, **kw):
        pass

    async def send_message(self, *a, **kw):
        self.msgs.append((a, kw))


cog_names_asked = []


def get_cog(name):
    cog_names_asked.append(name)
    return None


interaction = NS(guild=guild, user=reporter, response=FakeResp(),
                 followup=FakeFollowup(),
                 channel=NS(id=999, mention='<#999>'),
                 client=None)

cog = R.Reports(bot=NS(get_cog=get_cog))
run = asyncio.new_event_loop()

# ── 1. Команда: доказательств больше нет ────────────────────────────────────
print('== 1. Доказательство убрано ==')
sig = inspect.signature(R.Reports.report_slash.callback)
params = [p for p in sig.parameters if p not in ('self', 'interaction')]
check(params == ['user', 'reason'],
      f'у /report ровно два параметра: user и reason (без proof)', f'→ {params}')
check(not any('proof' in p.lower() for p in sig.parameters),
      'ни proof_file, ни proof в сигнатуре')
_src = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'cogs', 'reports.py'), encoding='utf-8').read()
check('ProofCog' not in _src,
      'конвейер демок (ProofCog) из /report удалён из кода')

# ── 2. Вызов уходит в канал модерации ───────────────────────────────────────
print('== 2. Сигнал в чат модеров ==')
run.run_until_complete(cog.report_slash.callback(
    cog, interaction, accused, 'ломают игру, спамят и орут'))
check(len(MOD_CH.sent) == 1, 'карточка вызова ушла в канал модерации',
      f'→ {len(MOD_CH.sent)}')
card = MOD_CH.sent[0] if MOD_CH.sent else {}
_emb = card.get('embed')
check(_emb is not None and 'Вызов модератора' in (_emb.title or ''),
      'заголовок карточки — «Вызов модератора»', f'→ {getattr(_emb, "title", None)}')
check((card.get('content') or '').strip() == '<@&555>',
      'в content — только тег роли модераторов (живой пуш)',
      f'→ {card.get("content")!r}')
_am = card.get('allowed_mentions')
check(_am is not None and getattr(_am, 'roles', None) not in (True, False, None)
      and MOD_ROLE in list(getattr(_am, 'roles', []) or []),
      'AllowedMentions.roles — конкретная роль модеров, не «все роли»',
      f'→ {getattr(_am, "roles", None)!r}')
check('rcard_accept' in [b.custom_id for b in card.get('view').children]
      and 'rcard_reject' in [b.custom_id for b in card.get('view').children]
      and 'rcard_thread' in [b.custom_id for b in card.get('view').children],
      'у модераторов кнопки разбора: Принять / Отклонить / Открыть разбор')

# ── 3. Карточка отвечает на вопросы модератора ──────────────────────────────
print('== 3. Красивая карточка ==')
def _blob(emb):
    if emb is None:
        return ''
    parts = [emb.title or '', emb.description or '']
    for f in getattr(emb, 'fields', []) or []:
        parts.append(getattr(f, 'name', '') or '')
        parts.append(getattr(f, 'value', '') or '')
    return '\n'.join(parts)
desc = _blob(_emb)
check('<#999>' in desc and 'Куда идти' in desc,
      'карточка говорит, куда идти (канал вызова)')
check('Общий' in desc and 'Голосовой' in desc,
      'голосовой канал вызывавшего указан (куда зайти)')
check('<@200>' in desc and 'Кто вызвал' in desc, 'кто вызвал')
check('<@300>' in desc and 'Из-за кого' in desc, 'из-за кого')
check('ломают игру' in desc and 'Что случилось' in desc, 'что случилось')

# ── 4. Ответ вызывавшему ────────────────────────────────────────────────────
print('== 4. Ответ вызывавшему ==')
_fu = interaction.followup.sent[-1][0][0] if interaction.followup.sent else ''
check('Модератор вызван' in _fu and '<#1001>' in _fu,
      'подтверждение: «Модератор вызван», сигнал в канале модерации',
      f'→ {_fu[:80]}')
check('Доказательство' not in _fu, 'в ответе нет ни слова про доказательства')

# тикет привязан к карточке (разбор в канале работает)
check(RC.ticket_get(9001) is not None
      and RC.ticket_get(9001).get('kind') == 'card',
      'вызов записан в очередь (тикет карточки создан)')

# ── 5. Дубль-вызов на того же ───────────────────────────────────────────────
print('== 5. Антидубль ==')
interaction2 = NS(guild=guild, user=reporter, response=FakeResp(),
                  followup=FakeFollowup(),
                  channel=NS(id=999, mention='<#999>'), client=None)
run.run_until_complete(cog.report_slash.callback(
    cog, interaction2, accused, 'ещё раз'))
check(len(MOD_CH.sent) == 1 and interaction2.followup.sent,
      'дубль-вызов на того же участника не создаёт вторую карточку')

# ── 6. ProofCog не дёргается ────────────────────────────────────────────────
check('ProofCog' not in cog_names_asked,
      'бот даже не спрашивают про ProofCog — демки из /report убраны',
      f'→ {cog_names_asked}')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
