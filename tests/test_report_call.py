# -*- coding: utf-8 -*-
"""/report = «Позвать модератора», форма-модалка Components V2.

Что изменилось и что проверяем НАСТОЯЩИМ кодом (ReportModal/_deliver_report):
  • /report больше не принимает параметров — сразу открывает модалку
    с полями: «Выберите нарушителя» (UserSelect), «На кого жалоба?»
    (Пользователь/Стафф), «Где происходило нарушение?» (Чат/Войс),
    «Причина жалобы» (текст);
  • сигнал уходит V2-карточкой (Components V2, чёрный блок) в канал
    модерации, тег роли модераторов — отдельным сообщением (живой пуш);
  • карточка отвечает на вопросы: куда идти, кто вызвал, из-за кого, что
    случилось, категория (пользователь/стафф), место нарушения
    (+ голосовой канал вызывавшего, если он в войсе);
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


def _walk(item, out):
    """Собрать все вложенные компоненты V2-карточки (Container/ActionRow)."""
    out.append(item)
    for child in (getattr(item, 'children', None) or []):
        _walk(child, out)
    return out


def _card_text(view):
    parts = []
    for it in _walk(view, []):
        if type(it).__name__ == 'TextDisplay':
            parts.append(getattr(it, 'content', '') or '')
    return '\n'.join(parts)


def _card_buttons(view):
    return [it for it in _walk(view, []) if type(it).__name__ == 'Button']


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
        self.modal = None
        self._done = False

    def is_done(self):
        return self._done

    async def defer(self, *a, **kw):
        self._done = True

    async def send_message(self, *a, **kw):
        self._done = True
        self.msgs.append((a, kw))

    async def send_modal(self, modal):
        self._done = True
        self.modal = modal


cog_names_asked = []


def get_cog(name):
    cog_names_asked.append(name)
    return None


def make_interaction():
    return NS(guild=guild, user=reporter, response=FakeResp(),
             followup=FakeFollowup(),
             channel=NS(id=999, mention='<#999>'),
             client=None)


cog = R.Reports(bot=NS(get_cog=get_cog))
run = asyncio.new_event_loop()


async def _submit(target, reason, against='user', location='chat'):
    """Открыть /report (модалка), заполнить поля, отправить."""
    inter = make_interaction()
    await cog.report_slash.callback(cog, inter)
    check(inter.response.modal is not None,
          '/report открывает модалку (send_modal)')
    modal = inter.response.modal
    modal.target_select._values = [target]
    modal.against_select._values = [against]
    modal.location_select._values = [location]
    modal.reason_input._value = reason
    inter2 = make_interaction()
    await modal.on_submit(inter2)
    return inter2


# ── 1. Команда: без параметров, модалка вместо них ─────────────────────────
print('== 1. /report — модалка, без proof и без параметров ==')
sig = inspect.signature(R.Reports.report_slash.callback)
params = [p for p in sig.parameters if p not in ('self', 'interaction')]
check(params == [], f'у /report нет параметров — форма модалкой', f'→ {params}')
_src = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'cogs', 'reports.py'), encoding='utf-8').read()
check('ProofCog' not in _src,
      'конвейер демок (ProofCog) из /report удалён из кода')
check('discord.ui.Label' in _src and 'discord.ui.UserSelect' in _src,
      'модалка использует Components V2 (Label + UserSelect/Select)')
check('Выберите нарушителя' in _src and 'На кого жалоба?' in _src
      and 'Где происходило нарушение?' in _src and 'Причина жалобы' in _src,
      'все 4 поля формы на месте')

# ── 2. Вызов уходит в канал модерации ───────────────────────────────────────
print('== 2. Сигнал в чат модеров (V2-карточка + отдельный пинг) ==')
inter_final = run.run_until_complete(
    _submit(accused, 'ломают игру, спамят и орут'))
check(len(MOD_CH.sent) == 2,
      'карточка + отдельный пинг ушли в канал модерации',
      f'→ {len(MOD_CH.sent)}')
card = MOD_CH.sent[0]
ping_msg = MOD_CH.sent[1]
check('view' in card and 'embed' not in card,
      'карточка — V2 view, без classic embed', f'→ {card.keys()}')
check((ping_msg.get('content') or '').strip() == '<@&555>',
      'пинг — только тег роли модераторов (живой пуш)',
      f'→ {ping_msg.get("content")!r}')
_am = ping_msg.get('allowed_mentions')
check(_am is not None and getattr(_am, 'roles', None) not in (True, False, None)
      and MOD_ROLE in list(getattr(_am, 'roles', []) or []),
      'AllowedMentions.roles — конкретная роль модеров, не «все роли»',
      f'→ {getattr(_am, "roles", None)!r}')
_view = card.get('view')
_btn_ids = [b.custom_id for b in _card_buttons(_view)]
check('rcard_accept' in _btn_ids and 'rcard_reject' in _btn_ids
      and 'rcard_thread' in _btn_ids,
      'у модераторов кнопки разбора: Принять / Отклонить / Открыть разбор',
      f'→ {_btn_ids}')

# ── 3. Карточка отвечает на вопросы модератора ──────────────────────────────
print('== 3. Красивая V2-карточка ==')
desc = _card_text(_view)
check('Вызов модератора' in desc, 'заголовок карточки — «Вызов модератора»')
check('<#999>' in desc and 'Откуда вызов' in desc,
      'карточка говорит, откуда пришёл вызов')
check('Общий' in desc and 'войсе' in desc,
      'голосовой канал вызывавшего указан (куда зайти)')
check('<@200>' in desc and 'Кто вызвал' in desc, 'кто вызвал')
check('<@300>' in desc and 'Из-за кого' in desc, 'из-за кого')
check('ломают игру' in desc and 'Что случилось' in desc, 'что случилось')
check('Обычный участник' in desc and 'Категория' in desc,
      'категория «на кого жалоба» — обычный участник')
check('Чат' in desc and 'Где произошло' in desc,
      'место нарушения — чат')

# ── 3b. Жалоба на стафф — визуально выделена ────────────────────────────────
print('== 3b. Жалоба на стафф — предупреждение и другой акцент ==')
staff_target = NS(id=301, display_name='Модератор Б', name='Модератор Б',
                  bot=False, mention='<@301>', display_avatar=NS(url='http://a/4'))
run.run_until_complete(
    _submit(staff_target, 'грубит участникам', against='staff', location='voice'))
card2 = MOD_CH.sent[-2]
view2 = card2.get('view')
desc2 = _card_text(view2)
check('Состав модерации' in desc2 and '⚠️' in desc2,
      'жалоба на стафф — явное предупреждение в карточке')
check(getattr(view2, '_accent', None) == 0xF39C12,
      'жалоба на стафф — другой (оранжевый) акцент', f'→ {view2._accent:#x}')
check('Голосовой канал' in desc2, 'место нарушения — войс, как выбрано в форме')

# ── 4. Ответ вызывавшему ────────────────────────────────────────────────────
print('== 4. Ответ вызывавшему ==')
_fu = inter_final.followup.sent[-1][0][0] if inter_final.followup.sent else ''
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
before = len(MOD_CH.sent)
inter_dup = run.run_until_complete(
    _submit(accused, 'ещё раз'))
check(len(MOD_CH.sent) == before and inter_dup.followup.sent,
      'дубль-вызов на того же участника не создаёт вторую карточку')
check('жди' in (inter_dup.followup.sent[-1][0][0] if inter_dup.followup.sent else ''),
      'дубль объясняется отказом, а не тихим падением')

# ── 6. ProofCog не дёргается, на себя/бота нельзя ───────────────────────────
print('== 6. Валидация и отсутствие demo-конвейера ==')
check('ProofCog' not in cog_names_asked,
      'бот даже не спрашивают про ProofCog — демки из /report убраны',
      f'→ {cog_names_asked}')

before_self = len(MOD_CH.sent)
inter_self = run.run_until_complete(_submit(reporter, 'на себя'))
_self_msg = inter_self.followup.sent[-1][0][0] if inter_self.followup.sent else ''
check('нельзя' in _self_msg, 'на себя жаловаться нельзя', f'→ {_self_msg!r}')
check(len(MOD_CH.sent) == before_self,
      'жалоба на себя не создаёт карточку в канале модерации')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
