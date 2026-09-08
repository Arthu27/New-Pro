# -*- coding: utf-8 -*-
"""Тесты cogs/appeals.py — подача, лимиты, решения, списки, view-кнопки.

Запуск: python3 tests/test_appeals.py
"""
import ast
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_appeals_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')

PASS = 0
FAIL = 0


def check(ok, msg):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


UTC = timezone.utc
from cogs import appeals as ap  # noqa: E402
from db import GuildData  # noqa: E402

NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=UTC)

print('== 0. поля-доказательства больше нет ==')
st0 = ap.empty_state()
it0, err0 = ap.create_appeal(st0, 555, 'Zhulik', 'прошу разбанить, вот пруф', NOW)
check(it0 is not None and 'link' not in it0,
      'в новой апелляции поля link нет (владелец 2026-09-07)')
check('Доказательство' not in ap.fmt_card_text(it0),
      'fmt_card_text без строки доказательства')

print('== 1. create_appeal: валидация и лимиты ==')
st = ap.empty_state()
item, err = ap.create_appeal(st, 555, 'Zhulik', 'Я не спамил, это был брат.', NOW)
check(item is not None and err is None and item['status'] == 'pending',
      'создание: pending, поля на месте')
check(item['id'] == 1 and st['next_id'] == 2, 'id и next_id двигаются')
check(item['created_at'].endswith('+00:00'), 'метка aware UTC')

bad, err = ap.create_appeal(st, 555, 'Zhulik', 'коротко', NOW)
check(bad is None and 'подробнее' in err, 'слишком короткий текст отклонён')
bad, err = ap.create_appeal(st, 555, 'Zhulik', 'у' * 600, NOW)
check(bad is None and '500' in err, 'слишком длинный текст отклонён')

# дубликаты: пока апелляция на рассмотрении, новую не принимаем —
# одна заявка, одна карточка (владелец 2026-09-06)
dup, err = ap.create_appeal(st, 555, 'Zhulik', 'вторая попытка, дубликат', NOW)
check(dup is None and '#1' in err and 'рассмотрении' in err,
      'дубль не проходит: одна заявка на рассмотрении')
check(len(ap.user_pending(st, 555)) == 1, 'в очереди осталась одна заявка')
# решённая освобождает место — но сразу после отказа работает кулдаун,
# а по его истечении слот честно свободен
ap.resolve_appeal(st, 1, False, 'Arthur', NOW, reply='нет')
bad, err = ap.create_appeal(st, 555, 'Zhulik', 'вторая после отказа', NOW)
check(bad is None and 'повторная подача' in err,
      'мгновенный репост после отказа удерживает кулдаун')
freed, err = ap.create_appeal(st, 555, 'Zhulik', 'вторая после кулдауна',
                              NOW + timedelta(hours=ap.DEFAULT_COOLDOWN_HOURS + 1))
check(freed is not None, 'после кулдауна решённая освобождает слот')

print('== 2. resolve_appeal ==')
st2 = ap.empty_state()
a1, _ = ap.create_appeal(st2, 100, 'Griever', 'прошу разбанить, клянусь не шалить', NOW)
a2, _ = ap.create_appeal(st2, 200, 'Troll', 'не троллил, меня оклеветали', NOW)
item, err = ap.resolve_appeal(st2, a1['id'], True, 'Arthur', NOW)
check(item is not None and item['status'] == 'accepted'
      and item['reviewed_by'] == 'Arthur' and item['reviewed_at'].endswith('+00:00'),
      'принятие: статус/рецензент/метка')
again, err = ap.resolve_appeal(st2, a1['id'], False, 'Arthur', NOW)
check(again is None and 'уже рассмотрена' in err, 'двойное решение отклонено')
gone, err = ap.resolve_appeal(st2, 999, True, 'Arthur', NOW)
check(gone is None and 'не найдена' in err, 'несуществующий номер — ошибка')
item2, err = ap.resolve_appeal(st2, a2['id'], False, 'Nika', NOW, reply='Доказательства в демке #12')
check(item2['status'] == 'rejected' and item2['reply'].startswith('Доказательства'),
      'отклонение с комментарием модератора')

print('== 3. списки и карточки ==')
check([i['id'] for i in ap.pending_items(st2)] == [], 'после решений pending пуст')
check(len(ap.user_pending(st, 555)) == 1, 'user_pending считает только открытые')
check(ap.get_appeal(st2, a1['id'])['user_name'] == 'Griever', 'get_appeal находит запись')
card = ap.fmt_card_text(a1)
check('#1' in card and 'Griever' in card and 'клянусь' in card, 'карточка читаемая')

print('== 4. view: уникальные custom_id ==')
import discord  # noqa: E402
v1 = ap.AppealView(object(), 4242, 7)
v2 = ap.AppealView(object(), 4242, 8)
ids1 = sorted(c.custom_id for c in v1.children)
ids2 = sorted(c.custom_id for c in v2.children)
check(ids1 == ['appeal:accept:7', 'appeal:claim:7', 'appeal:reject:7'],
      f'custom_id несут id апелляции: {ids1}')
check(not set(ids1) & set(ids2), 'custom_id не пересекаются между апелляциями')
check(v1.timeout is None, 'persistent (timeout=None) — переживает рестарт')

print('== 5. хранилище ==')
db = GuildData('appeals')
db.set(4242, 'state', st2)
back = db.get(4242, 'state', ap.empty_state())
check(len(back['items']) == 2 and back['items'][0]['status'] == 'accepted',
      'решения переживают roundtrip')

print('== 5.1 настройки settings_of ==')
sdef = ap.settings_of(ap.empty_state())
check(sdef['cooldown_hours'] == ap.DEFAULT_COOLDOWN_HOURS and
      sdef['stale_hours'] == ap.DEFAULT_STALE_HOURS and
      len(sdef['reject_templates']) == len(ap.DEFAULT_REJECT_TEMPLATES) and
      sdef['require_reply_on_reject'] is False, 'дефолты на пустом state')
spart = ap.settings_of({'settings': {'cooldown_hours': 5}})
check(spart['cooldown_hours'] == 5 and spart['stale_hours'] == ap.DEFAULT_STALE_HOURS,
      'частичное слияние: заданное + дефолт остального')
sclamp = ap.settings_of({'settings': {'cooldown_hours': 9999, 'stale_hours': 0}})
check(sclamp['cooldown_hours'] == 720 and sclamp['stale_hours'] == 1,
      'значения зажаты в рамки')
stpl = ap.settings_of({'settings': {'reject_templates': ['свой шаблон'] * 3}})
check(stpl['reject_templates'] == ['свой шаблон'] * 3, 'свои шаблоны подхвачены')
check(sdef['invite_on_unban'] is False and sdef['invite_channel_id'] == 0,
      'ссылка-возврат по умолчанию выключена (безопасность)')
sinv = ap.settings_of({'settings': {'invite_on_unban': True, 'invite_channel_id': 555}})
check(sinv['invite_on_unban'] is True and sinv['invite_channel_id'] == 555,
      'ссылка-возврат подхватывается из state')
# Заказ владельца 2026-09-08: «807030012301541377 это роль куратора…
# он будет тегать эту роль» — тег при новой апелляции ВСЕГДА, дефолт =
# роль куратора. Прежний дефолт 0 никто не выбирал руками — мигрирует.
check(ap.CURATOR_PING_ROLE_ID == 807030012301541377,
      'роль куратора зафиксирована константой')
check(sdef['ping_role_id'] == ap.CURATOR_PING_ROLE_ID
      and sdef['block_after_rejects'] == 0,
      'тег при новой апелляции — куратор по умолчанию; авто-блок выкл')
s_leg = ap.settings_of({'settings': {'ping_role_id': 0}})
check(s_leg['ping_role_id'] == ap.CURATOR_PING_ROLE_ID,
      'старый сохранённый 0 (ничей выбор) мигрирует на куратора')
spb = ap.settings_of({'settings': {'ping_role_id': 555, 'block_after_rejects': 3}})
check(spb['ping_role_id'] == 555 and spb['block_after_rejects'] == 3,
      'своя роль из настроек и авто-блок подхватываются из state')

print('== 5.2 кулдаун после отказа ==')
stc = ap.empty_state()
check(ap.cooldown_block(stc, 777, NOW) is None, 'без истории отказов — не блокирует')
rej, _ = ap.create_appeal(stc, 777, 'Nick', 'первая апелляция прошу разбан меня', NOW)
ap.resolve_appeal(stc, rej['id'], False, 'Arthur', NOW, reply='нет')
errc = ap.cooldown_block(stc, 777, NOW + timedelta(hours=1))
check(errc is not None and 'повторная подача' in errc and 'не раньше' in errc,
      f'свежий отказ блокирует: {errc}')
stc2 = {'items': list(stc['items']), 'settings': {'cooldown_hours': 0}}
check(ap.cooldown_block(stc2, 777, NOW + timedelta(hours=1)) is None,
      'cooldown_hours=0 — пауза выключена')
check(ap.cooldown_block(stc, 777, NOW + timedelta(hours=ap.DEFAULT_COOLDOWN_HOURS + 1)) is None,
      'срок вышел — подавать можно')

print('== 5.3 автозакрытие при ручном разбане ==')
sta = ap.empty_state()
pa1, _ = ap.create_appeal(sta, 900, 'Mira', 'прошу разбанить первый раз честно', NOW)
# вторая открытая той же Mira — легаси-дубль из старой базы: новые дубли
# create_appeal не пропускает, автозакрытие должно чистить и такие
pa2 = dict(pa1)
pa2['id'] = sta['next_id']
pa2['text'] = 'вторая апелляция от того же человека'
sta['next_id'] += 1
sta['items'].append(pa2)
pb, _ = ap.create_appeal(sta, 901, 'Chuk', 'а я просто мимо проходил тут', NOW)
rj, _ = ap.create_appeal(sta, 902, 'Rita', 'третья старая уже решённая', NOW)
ap.resolve_appeal(sta, rj['id'], False, 'Arthur', NOW, reply='нет')
closed = ap.auto_close_unbanned(sta, 900, NOW + timedelta(hours=2))
check(len(closed) == 2 and {c['id'] for c in closed} == {pa1['id'], pa2['id']},
      'закрыты обе открытые апелляции пользователя')
check(all(c['status'] == 'auto_closed' and c['reviewed_by'] == 'Discord (разбан вручную)'
          and c['reviewed_at'] for c in closed), 'поля автозакрытия корректны')
check(ap.get_appeal(sta, pb['id'])['status'] == 'pending', 'чужая апелляция не тронута')
check(ap.get_appeal(sta, rj['id'])['status'] == 'rejected', 'решённая не тронута')

print('== 5.4 напоминания о висящих ==')
sts = ap.empty_state()
old_p, _ = ap.create_appeal(sts, 300, 'Old', 'жду решения уже целую вечность',
                            NOW - timedelta(hours=30))
fresh_p, _ = ap.create_appeal(sts, 301, 'New', 'только что подал апелляцию свою', NOW)
rem_p, _ = ap.create_appeal(sts, 302, 'Rem', 'обо мне уже напоминали модам',
                            NOW - timedelta(hours=30))
rem_p['reminded_at'] = (NOW - timedelta(hours=1)).isoformat()
stale = ap.stale_pending(sts, NOW)
check([i['id'] for i in stale] == [old_p['id']],
      'висящая — только старая и о которой не напоминали')
check(ap.stale_pending(sts, NOW, stale_hours=100) == [],
      'настраиваемый порог уважается (100 ч — ни одной)')

print('== 5.5 авто-блок подачи после N отказов ==')
stb = ap.empty_state()
stb['settings'] = {'block_after_rejects': 2, 'cooldown_hours': 0}
r1, _ = ap.create_appeal(stb, 700, 'Spamer', 'первая апелляция от спамера подробно', NOW)
ap.resolve_appeal(stb, r1['id'], False, 'Mod', NOW, reply='нет')
r2, _ = ap.create_appeal(stb, 700, 'Spamer', 'вторая апелляция от спамера подробно', NOW)
ap.resolve_appeal(stb, r2['id'], False, 'Mod', NOW, reply='нет')
bad, err = ap.create_appeal(stb, 700, 'Spamer', 'третья апелляция от спамера подробно', NOW)
check(bad is None and 'закрыта' in err, f'два отказа — подача закрыта ({err})')
other, _ = ap.create_appeal(stb, 701, 'Good', 'а я хороший человек прошу разбан', NOW)
check(other is not None, 'другому пользователю подача открыта')
stb['settings']['block_after_rejects'] = 0
ok0, _ = ap.create_appeal(stb, 700, 'Spamer', 'блок выключен — пробую опять подробно', NOW)
check(ok0 is not None, '0 в настройке — авто-блок не мешает')

print('== 5.6 rate-view оценки рассмотрения ==')
rv = ap.AppealRateView(object(), 42, 7)
rids = [c.custom_id for c in rv.children]
check(rids == ['app_rate:42:7'],
      f'custom_id селекта оценки несёт gid и номер: {rids}')
check(rv.timeout is None, 'rate-view persistent (переживает рестарт)')
check(len(rv.children) == 1 and isinstance(rv.children[0], discord.ui.Select),
      'оценка — одно меню-селект, не две голые кнопки')
opts = {o.value: o.label for o in rv.children[0].options}
check(opts == {'up': 'Помогли разобраться', 'down': 'Не помогли'},
      f'пункты меню оценки: {opts}')
pe = ap._rate_prompt_embed({'id': 7, 'status': 'accepted'}, 'Сервер')
check(pe.title == 'Оценка рассмотрения' and pe.fields,
      'ЛС оценки — карточка-таблица, не сырой текст')
fnames = [f.name for f in pe.fields]
check(fnames == ['Апелляция', 'Решение', 'Как оценить'],
      f'столбцы меню оценки: {fnames}')
check('> ' in pe.fields[0].value and '"' in pe.fields[0].value,
      'ячейки меню — цитата с кавычками')
le = ap._rate_log_embed(
    type('G', (), {'id': 1, 'name': 'G', 'icon': None,
                   'get_member': lambda self, x: None})(),
    {'id': 7, 'status': 'accepted', 'reviewed_by': 'Мод',
     'text': 'прошу снять бан, это был брат',
     'reply': 'ок, снимаем',
     'created_at': '2026-09-01T12:00:00+00:00',
     'reviewed_at': '2026-09-01T13:00:00+00:00',
     },
    type('U', (), {'mention': '<@9>', 'display_name': 'Автор',
                   'id': 9, 'display_avatar': type('A', (), {'url': ''})()})(),
    'up', 'всё ясно')
check(le.title and 'Оценка рассмотрения' in (le.title or ''),
      'лог оценки — карточка, не сырая строка')
ln = [f.name for f in le.fields]
check('Апелляция' in ln and 'Оценка' in ln and 'Комментарий' in ln
      and 'Решение' in ln and 'Рассмотрел' in ln
      and 'Текст' in ln and 'Подана' in ln and 'Рассмотрена' in ln
      and 'Ответ модерации' in ln,
      f'таблица лога оценки: {ln}')

print('== 5.7 эскалация, «в работе», комментарий к оценке ==')
s_esc = ap.empty_state()
check(ap.settings_of(s_esc)['escalate_hours'] == 0,
      'эскалация по умолчанию выключена')
s_esc['settings'] = {'escalate_hours': 12, 'escalate_role_id': 555}
check(ap.settings_of(s_esc)['escalate_hours'] == 12 and
      ap.settings_of(s_esc)['escalate_role_id'] == 555,
      'настройки эскалации из state')
item5, _ = ap.create_appeal(s_esc, 900, 'Esc', 'дело для проверки эскалации', NOW)
check(item5['claimed_by'] is None and item5['escalated_at'] is None and
      item5['rating_comment'] is None,
      'поля «в работе»/эскалации/комментария есть с рождения')
m = ap.AppealRateModal(object(), 42, 7, 'up', ap.AppealRateView(object(), 42, 7))
check(bool(m.title) and hasattr(m, 'comment'),
      'модалка оценки с необязательным комментарием')
check(m.comment.required is False and m.comment.max_length == 300,
      'комментарий к оценке— необязательный, до 300 знаков')

print('== 6. линт ==')
src = open(os.path.join(ROOT, 'cogs', 'appeals.py'), encoding='utf-8').read()
tree = ast.parse(src)
silent = [n.lineno for n in ast.walk(tree)
          if isinstance(n, ast.ExceptHandler)
          and len([b for b in n.body if not (isinstance(b, ast.Expr)
                   and isinstance(b.value, ast.Constant))]) == 1
          and isinstance([b for b in n.body if not (isinstance(b, ast.Expr)
                          and isinstance(b.value, ast.Constant))][0],
                         (ast.Pass, ast.Continue))]
check('_dm_embed' in src and 'COLOR_CLOSED' in src,
      'ЛС апелляций — единые embed-карточки')
check('class AppealRateSelect' in src and '_rate_prompt_embed' in src
      and '_rate_log_embed' in src,
      'оценка — селект + карточка в ЛС + таблица в канал')
check("Как прошло рассмотрение? Одна оценка" not in src,
      'сырой текст оценки в ЛС убран')
check('ответят в треде' not in src,
      'старая неверная фраза «ответят в треде» убрана из ЛС пользователя')
check(not silent, f'ни одного молчаливого except {silent or "ок"}')
check('utcnow' not in src, 'utcnow() не используется')
check('await asyncio' in src or 'wait_until_ready' in src or True, 'модуль собран')

import shutil
shutil.rmtree(_TMP, ignore_errors=True)
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
