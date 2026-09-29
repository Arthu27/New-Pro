# -*- coding: utf-8 -*-
"""Юнит-тесты бота Мафии: пресеты, жизненный цикл, победы, персистентность."""
from __future__ import annotations

import os
import random
import sys
import tempfile

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

from services.mafia.roles import (  # noqa: E402
    ROLES,
    check_result_for_don,
    check_result_for_sheriff,
    expand_roles,
    preset_for_count,
    preset_summary,
)
from services.mafia.game import (  # noqa: E402
    PHASE_CONFIRM,
    PHASE_ENDED,
    PHASE_LOBBY,
    PHASE_PLAYING,
    PHASE_READY,
    CYCLE_DAY,
    CYCLE_NIGHT,
    CYCLE_VOTE,
    Game,
)
from services.mafia.store import GameStore  # noqa: E402

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


print('\n== 1. Пресеты по ТЗ ==')
expected = {
    6: {'mafia': 1, 'sheriff': 1, 'citizen': 4},
    7: {'mafia': 1, 'sheriff': 1, 'doctor': 1, 'citizen': 4},
    8: {'mafia': 2, 'sheriff': 1, 'doctor': 1, 'citizen': 4},
    9: {'mafia': 2, 'sheriff': 1, 'doctor': 1, 'citizen': 5},
    10: {'mafia': 3, 'sheriff': 1, 'doctor': 1, 'citizen': 5},
    11: {'mafia': 3, 'sheriff': 1, 'doctor': 1, 'citizen': 6},
    12: {'mafia': 3, 'don': 1, 'sheriff': 1, 'doctor': 1, 'citizen': 6},
    13: {'mafia': 3, 'don': 1, 'sheriff': 1, 'doctor': 1, 'courtesan': 1, 'citizen': 6},
    14: {'mafia': 3, 'don': 1, 'sheriff': 1, 'doctor': 1, 'courtesan': 1, 'citizen': 7},
}
# путана только с 13
check('courtesan' not in preset_for_count(12), 'на 12 нет путаны')
check(preset_for_count(13).get('courtesan') == 1, 'на 13 есть путана')
for n, want in expected.items():
    got = preset_for_count(n)
    check(got == want, f'пресет {n}: {got}')
    bag = expand_roles(got)
    check(len(bag) == n, f'expand {n}: длина {len(bag)}')
    check(all(k in ROLES for k in bag), f'expand {n}: все роли известны')
try:
    preset_for_count(5)
    check(False, 'меньше 6 — ValueError')
except ValueError:
    check(True, 'меньше 6 — ValueError')
check('Мафия' in preset_summary(6) and 'Шериф' in preset_summary(6),
      'preset_summary читаемый')


print('\n== 2. Проверки шерифа и дона ==')
short, _ = check_result_for_sheriff('mafia')
check('Мафия' in short, f'шериф vs мафия: {short}')
short, _ = check_result_for_sheriff('don')
check('Мафия' in short, f'шериф vs дон: {short}')
short, _ = check_result_for_sheriff('citizen')
check('Мирный' in short, f'шериф vs мирный: {short}')
short, _ = check_result_for_don('sheriff')
check('Шериф' in short, f'дон vs шериф: {short}')
short, _ = check_result_for_don('mafia')
check('Не шериф' in short, f'дон vs мафия: {short}')


print('\n== 3. Лобби: ведущий исключён, минимум 6 ==')
members = [(100 + i, f'P{i}') for i in range(7)]  # 7 человек + хост в списке
members_with_host = [(1, 'Host')] + members
g = Game.create(guild_id=42, host_id=1, voice_channel_id=9,
                text_channel_id=8, members=members_with_host)
check(1 not in g.players, 'ведущий не в составе')
check(len(g.players) == 7, f'игроков 7 (сейчас {len(g.players)})')
check(g.phase == PHASE_LOBBY, 'фаза lobby')


print('\n== 4. Раздача + подтверждение + старт ==')
g = Game.create(42, 1, 9, 8, [(100 + i, f'P{i}') for i in range(6)])
counts = g.deal(rng=random.Random(7))
check(g.phase == PHASE_CONFIRM, 'после deal — confirm')
check(sum(counts.values()) == 6, 'пресет на 6')
check(all(p.role for p in g.players.values()), 'у всех роли')
check(not any(p.confirmed for p in g.players.values()), 'никто не подтвердил')
token = g.deal_token
uids = list(g.players.keys())
# повторное подтверждение
check(g.confirm(uids[0], token) is True, 'первое подтверждение')
check(g.confirm(uids[0], token) is False, 'повтор не меняет')
for uid in uids[1:]:
    g.confirm(uid, token)
check(g.phase == PHASE_READY, 'все подтвердили → ready')
check(g.all_confirmed(), 'all_confirmed')
g.start()
check(g.phase == PHASE_PLAYING, 'start → playing')
check(g.cycle == CYCLE_NIGHT and g.day_number == 1,
      f'start → ночь 1 (cycle={g.cycle}, day={g.day_number})')


print('\n== 5. Перераздача инвалидирует старый токен ==')
g2 = Game.create(43, 1, 9, 8, [(200 + i, f'Q{i}') for i in range(6)])
g2.deal(rng=random.Random(1))
old = g2.deal_token
uid0 = next(iter(g2.players))
g2.confirm(uid0, old)
g2.deal(rng=random.Random(2))
check(g2.deal_token != old, 'новый deal_token')
try:
    g2.confirm(uid0, old)
    check(False, 'старый токен отвергнут')
except RuntimeError:
    check(True, 'старый токен отвергнут')
check(not g2.players[uid0].confirmed, 'после перераздачи confirmed сброшен')


print('\n== 6. Исключение / добавление до старта сбрасывает раздачу ==')
g3 = Game.create(44, 1, 9, 8, [(300 + i, f'R{i}') for i in range(6)])
g3.deal(rng=random.Random(3))
kick = next(iter(g3.players))
g3.exclude_player(kick)
check(g3.phase == PHASE_LOBBY, 'exclude → lobby')
check(all(p.role is None for p in g3.players.values()), 'роли сброшены')
g3.add_player(999, 'Newbie')
check(999 in g3.players, 'add_player')
check(len(g3.players) == 6, 'снова 6 после exclude+add')


print('\n== 7. Победа города (мафия выбита) ==')
g4 = Game.create(45, 1, 9, 8, [(400 + i, f'T{i}') for i in range(6)])
g4.deal(rng=random.Random(11))
for p in g4.players.values():
    p.confirmed = True
g4.phase = PHASE_READY
g4.start()
mafia = [p for p in g4.players.values() if p.role == 'mafia']
check(len(mafia) == 1, f'в пресете 6 ровно 1 мафия ({len(mafia)})')
g4.vote_out(mafia[0].user_id)
check(g4.winner == 'town', f'победа города (winner={g4.winner})')
check(g4.phase == PHASE_ENDED, 'фаза ended')


print('\n== 8. Победа мафии (равные живые) ==')
# 6 игроков: 1 мафия + 5 города. Убиваем городских пока 1:1.
g5 = Game.create(46, 1, 9, 8, [(500 + i, f'M{i}') for i in range(6)])
# принудительно раздаём известные роли
g5.deal_token = 'forced'
roles = ['mafia', 'sheriff', 'citizen', 'citizen', 'citizen', 'citizen']
for p, r in zip(g5.players.values(), roles):
    p.role = r
    p.confirmed = True
g5.phase = PHASE_READY
g5.start()
town = [p for p in g5.players.values() if p.role != 'mafia']
# убиваем 4 мирных → остаётся 1 мафия + 1 мирный → победа мафии
for p in town[:4]:
    g5.kill(p.user_id)
check(g5.winner == 'mafia', f'победа мафии при 1:1 (winner={g5.winner})')
check(len(g5.alive_mafia()) == 1 and len(g5.alive_town()) == 1,
      'живые 1 мафия / 1 город')


print('\n== 9. Проверки во время игры ==')
g6 = Game.create(47, 1, 9, 8, [(600 + i, f'C{i}') for i in range(8)])
g6.deal_token = 'x'
roles8 = ['mafia', 'mafia', 'sheriff', 'doctor', 'courtesan',
          'citizen', 'citizen', 'citizen']
for p, r in zip(g6.players.values(), roles8):
    p.role = r
    p.confirmed = True
g6.phase = PHASE_READY
g6.start()
sher_target = next(p for p in g6.players.values() if p.role == 'mafia')
rec = g6.sheriff_check(sher_target.user_id)
check('Мафия' in rec['result'], f'шериф видит мафию: {rec["result"]}')
don_target = next(p for p in g6.players.values() if p.role == 'sheriff')
rec2 = g6.don_check(don_target.user_id)
check('Шериф' in rec2['result'], f'дон видит шерифа: {rec2["result"]}')


print('\n== 10. Персистентность store ==')
td = tempfile.mkdtemp(prefix='mafia_test_')
# подменяем DATA_DIR через модуль
import services.mafia.store as st  # noqa: E402
old_dir = st.DATA_DIR
st.DATA_DIR = td
try:
    store = GameStore()
    g7 = Game.create(99, 1, 9, 8, [(700 + i, f'S{i}') for i in range(6)])
    g7.deal(rng=random.Random(5))
    store.set(g7)
    path = os.path.join(td, 'mafia_99.json')
    check(os.path.isfile(path), 'файл mafia_99.json создан')
    store2 = GameStore()
    n = store2.restore_all()
    check(n == 1, f'restore_all → {n}')
    got = store2.get(99)
    check(got is not None and got.game_id == g7.game_id, 'игра восстановлена')
    check(got.deal_token == g7.deal_token, 'deal_token сохранён')
    check(len(got.players) == 6, 'игроки на месте')
    store2.clear(99, archive=True)
    check(store2.get(99) is None, 'clear убрал активную')
finally:
    st.DATA_DIR = old_dir


print('\n== 11. Ког: /mafia меню ==')
import asyncio  # noqa: E402
import discord  # noqa: E402
from discord.ext import commands  # noqa: E402


async def _load_cog():
    bot = commands.Bot(command_prefix='!', intents=discord.Intents.none(),
                       help_command=None)
    await bot.load_extension('cogs.mafia')
    cmds = [c for c in bot.tree.get_commands() if c.name == 'mafia']
    cog = bot.get_cog('mafia')
    is_group = bool(cmds) and isinstance(cmds[0], discord.app_commands.Group)
    await bot.close()
    return bool(cmds), cog is not None, is_group

has_cmd, ok, is_group = asyncio.run(_load_cog())
check(ok, 'cog mafia загружен')
check(has_cmd, '/mafia в дереве')
check(not is_group, '/mafia — одна команда с меню, не группа подкоманд')

# меню содержит все действия ТЗ
from cogs.mafia import MafiaActionSelect  # noqa: E402
sel = MafiaActionSelect()
opts = {o.value for o in sel.options}
check(opts == {'start', 'deal', 'sync', 'status', 'panel', 'resend', 'add', 'cancel', 'presets'},
      f'меню действий: {sorted(opts)}')
# 🤍 / › как у демок
check(all(o.label.startswith('›') or '🤍' in o.label for o in sel.options),
      f'лейблы › : {[o.label for o in sel.options][:3]}')
check(all(getattr(o, 'emoji', None) is not None for o in sel.options),
      'у каждого пункта есть emoji')

# публичное лобби — только Участвовать/Выйти
from cogs.mafia import PublicLobbyView, HostToolsView, HostPanelView  # noqa: E402
pub_labels = {i.label for i in PublicLobbyView(1).children if hasattr(i, 'label')}
check(pub_labels == {'Участвовать', 'Выйти'}, f'публичные кнопки: {pub_labels}')
check('Анонс' not in pub_labels and 'Старт' not in pub_labels, 'нет анонс/старт у участников')
host_labels = {i.label for i in HostToolsView(1).children if hasattr(i, 'label')}
check('Раздать роли' in host_labels, f'хост-панель: {host_labels}')
# сводка ведущего — мало кнопок, без убийства/шерифа/дона
panel_labels = {i.label for i in HostPanelView().children if hasattr(i, 'label')}
check('Убийство мафии' not in panel_labels, f'нет ручного убийства: {panel_labels}')
check('Проверка шерифа' not in panel_labels and 'Проверка дона' not in panel_labels,
      f'нет ручных проверок: {panel_labels}')
check('Начать / Дальше' in panel_labels and 'Отменить игру' in panel_labels,
      f'есть Дальше+Отмена: {panel_labels}')
check('Очистить сообщения' in panel_labels, 'есть очистка сообщений')
check(len(panel_labels) <= 5, f'мало кнопок ({len(panel_labels)}): {panel_labels}')

# стикеры + V2 как демка
from services.mafia.ui_v2 import (  # noqa: E402
    sticker, role_sticker, build_mafia_lobby_items, build_mafia_closed_items,
    build_mafia_menu_items, V2_AVAILABLE as _MV2,
)
check(sticker('join') is not None and sticker('courtesan') is not None, 'стикеры join+путана')
check(role_sticker('courtesan') is not None, 'role_sticker путана')
if _MV2:
    from discord import ui as _dui  # noqa: E402
    _row = _dui.ActionRow()
    lobby_items = build_mafia_lobby_items(body='**Ведущий** · <@1>', action_row=_row)
    check(lobby_items and len(lobby_items) == 1, 'лобби — один чёрный контейнер')
    closed_items = build_mafia_closed_items(body='x', note='закрыто')
    check(closed_items and len(closed_items) == 1, 'закрытое лобби V2')
    menu_items = build_mafia_menu_items(body='меню', select_row=_row)
    check(menu_items and len(menu_items) == 1, 'меню ведущего — один контейнер')
check('_lobby_closed_kwargs' in open(
    os.path.join(_REPO, 'cogs/mafia.py'), encoding='utf-8').read(),
    'закрытие лобби через V2-карточку')

# старт только из войса ведущего — без Event-панели / signups
src = open(os.path.join(_REPO, 'cogs/mafia.py'), encoding='utf-8').read()
check('PublicLobbyView' in src and 'mafia:public:join' in src, 'public join custom_id')
check('EventPanel' not in open(
    os.path.join(_REPO, 'services/event_voice_bot.py'), encoding='utf-8').read()
    or 'EventPanel снят' in open(
        os.path.join(_REPO, 'services/event_voice_bot.py'), encoding='utf-8').read(),
    'event-bot без EventPanel (или снят)')
check('async def start_from_event' not in src, 'нет start_from_event')
check('event_voice_channel_id' not in src, 'нет фолбэка на Event-войс')
start_opt = next(o for o in MafiaActionSelect().options if o.value == 'start')
check('Участвовать' in (start_opt.description or '') or 'набора' in (start_opt.description or '').lower(),
      f'start desc: {start_opt.description}')

# lobby empty roster copy
from cogs.mafia import lobby_embed, lobby_body_md  # noqa: E402
empty = Game.create(1, 10, 99, 88, [])
emb = lobby_embed(empty)
check('Участвовать' in emb.fields[0].value or 'Участвовать' in (emb.footer.text or ''),
      'лобби зовёт Участвовать')
check('никого' in lobby_body_md(empty).lower() or 'Участвовать' in lobby_body_md(empty),
      'пустой состав явно')


print('\n== 12. Event-бот грузит mafia ==')
_ev = open(os.path.join(_REPO, 'services/event_voice_bot.py'), encoding='utf-8').read()
check('cogs import mafia' in _ev or 'from cogs.mafia' in _ev
      or 'from cogs import mafia' in _ev,
      'event-bot импортирует cogs.mafia')
check(os.path.isfile(os.path.join(_REPO, 'cogs/mafia.py')),
      'cogs/mafia.py на месте')


print('\n== 13. Авто-цикл ночь → день → голос ==')
g7 = Game.create(48, 1, 9, 8, [(700 + i, f'A{i}') for i in range(6)])
roles6 = ['mafia', 'sheriff', 'doctor', 'citizen', 'citizen', 'citizen']
g7.deal_token = 'auto'
for p, r in zip(g7.players.values(), roles6):
    p.role = r
    p.confirmed = True
g7.phase = PHASE_READY
g7.start()
check(g7.cycle == CYCLE_NIGHT, 'старт → ночь')
check(g7.night_queue and g7.night_queue[0]['step'] == 'kill',
      f'очередь начинается с мафии: {[s["step"] for s in g7.night_queue]}')
mafia_p = next(p for p in g7.players.values() if p.role == 'mafia')
sher_p = next(p for p in g7.players.values() if p.role == 'sheriff')
doc_p = next(p for p in g7.players.values() if p.role == 'doctor')
citizens = [p for p in g7.players.values() if p.role == 'citizen']
victim = citizens[0]
# шериф раньше мафии — нельзя
try:
    g7.submit_night_action(sher_p.user_id, 'sheriff', mafia_p.user_id)
    check(False, 'шериф не ходит раньше мафии')
except RuntimeError:
    check(True, 'шериф не ходит раньше мафии')
# очередь: мафия → доктор → шериф
g7.submit_night_action(mafia_p.user_id, 'kill', victim.user_id)
check(g7.night_step_ready(), 'шаг мафии готов')
g7.advance_night_step()
check(g7.current_night_step()['step'] == 'heal', 'следующий — доктор')
g7.submit_night_action(doc_p.user_id, 'heal', victim.user_id)
g7.advance_night_step()
check(g7.current_night_step()['step'] == 'sheriff', 'потом шериф')
g7.submit_night_action(sher_p.user_id, 'sheriff', mafia_p.user_id)
g7.advance_night_step()
check(g7.night_ready(), 'очередь ночи закрыта')
rep = g7.resolve_night()
check(rep['saved'] is True and rep['killed_id'] is None, f'спасён: {rep}')
check('целилась' in rep['report'] and 'Доктор спас' in rep['report'],
      f'классический отчёт спасения: {rep["report"][:120]}')
check(victim.display_name in rep['report'], 'в отчёте имя жертвы')
g7.begin_day()
check(g7.cycle == CYCLE_DAY, 'день')
g7.begin_vote()
check(g7.cycle == CYCLE_VOTE, 'голос')
check(g7.vote_order and g7.current_voter_id() == g7.vote_order[0],
      'голос по очереди — первый в списке')
# чужой голос раньше очереди — нельзя
second = g7.vote_order[1]
try:
    g7.submit_vote(second, mafia_p.user_id)
    check(False, 'нельзя голосовать вне очереди')
except RuntimeError:
    check(True, 'нельзя голосовать вне очереди')
# все по порядку
for uid in list(g7.vote_order):
    if uid == mafia_p.user_id:
        g7.submit_vote(uid, 0)
    else:
        g7.submit_vote(uid, mafia_p.user_id)
check(g7.vote_ready(), 'все проголосовали по очереди')
vrep = g7.resolve_vote()
check(vrep['eliminated_id'] == mafia_p.user_id, f'изгнали мафию: {vrep}')
check(g7.winner == 'town', f'победа города после голоса: {g7.winner}')
check('изгнал' in vrep['report'].lower() or 'Изгнал' in vrep['report'],
      f'отчёт голоса: {vrep["report"]}')
src_m = open(os.path.join(_REPO, 'cogs/mafia.py'), encoding='utf-8').read()
check('set_voice_night_mute' in src_m and 'on_night_started' in src_m,
      'войс-мут + авто-ночь в cog')
check('NightActionView' in src_m and 'VoteSelectView' in src_m,
      'ЛС-ходы ролей и голосование')
check('cleanup_game_messages' in src_m and 'Очистить сообщения' in src_m,
      'очистка сообщений в конце')
check('send_night_step_dms' in src_m and 'send_current_vote_dm' in src_m,
      'ночь и голос по очереди в cog')
check('relay_mafia_chat' in src_m and 'send_mafia_briefing' in src_m
      and 'Написать семье' in src_m,
      'мафия знает семью + чат')
# ночью мафию тоже мутим — иначе мирные видят, кто «семья» в войсе
_mute_fn = src_m.split('async def set_voice_night_mute', 1)[1].split(
    'async def ', 1)[0]
check('is_mafia_team' not in _mute_fn, 'ночной мут без исключения для мафии')
check('_apply_voice_mute_member' in src_m and 'voice_states' in src_m,
      'ночь = мут через voice_states + apply')
check('_members_in_voice_channel' in src_m and 'fetch_member' in _mute_fn,
      'мут не зависит от Members intent')
check('on_voice_state_update' in src_m, 'домут при входе в войс ночью')
check('can_doctor_self_heal' in open(
    os.path.join(_REPO, 'services/mafia/game.py'), encoding='utf-8').read(),
      'самохил доктора в game')


print('\n== 14. Семья мафии + самохил доктора ==')
g8 = Game.create(49, 1, 9, 8, [(800 + i, f'B{i}') for i in range(8)])
roles8b = ['mafia', 'mafia', 'sheriff', 'doctor', 'courtesan',
           'citizen', 'citizen', 'citizen']
g8.deal_token = 'fam'
for p, r in zip(g8.players.values(), roles8b):
    p.role = r
    p.confirmed = True
g8.phase = PHASE_READY
team = g8.mafia_team()
check(len(team) == 2, f'семья из 2: {len(team)}')
from cogs.mafia import role_dm_embed  # noqa: E402
emb = role_dm_embed(g8, team[0])
check('Ваша семья' in (emb.description or ''), 'в DM роли — список семьи')
check(all(str(t.user_id) in (emb.description or '') for t in team),
      'оба мафии в списке семьи')
# самохил
g8.start()
doc = next(p for p in g8.players.values() if p.role == 'doctor')
check(g8.can_doctor_self_heal() is True, 'самохил доступен в ночь 1')
# пройти очередь до heal
while g8.current_night_step() and g8.current_night_step()['step'] != 'heal':
    step = g8.current_night_step()
    for uid in step['actors']:
        g8.submit_night_action(uid, 'skip')
    g8.advance_night_step()
check(g8.current_night_step()['step'] == 'heal', 'шаг доктора')
g8.submit_night_action(doc.user_id, 'heal', doc.user_id)
check(g8.doctor_last_self_heal_day == 1, 'записан самохил ночи 1')
# добить ночь и начать ночь 2
g8.night_step = len(g8.night_queue)
g8.resolve_night()
g8.begin_day()
g8.begin_night()
check(g8.day_number == 2, f'ночь 2 (day={g8.day_number})')
check(g8.can_doctor_self_heal() is False, 'ночь 2 — самохил на кулдауне')
# ночь 3 — снова можно
g8.night_step = len(g8.night_queue)
g8.resolve_night()
g8.begin_day()
g8.begin_night()
check(g8.day_number == 3 and g8.can_doctor_self_heal() is True,
      'ночь 3 — самохил снова можно')


print('\n== 15. Мут войса (mock API) ==')
from unittest.mock import AsyncMock, MagicMock  # noqa: E402
from cogs.mafia import Mafia  # noqa: E402


async def _voice_mute_mock():
    bot = MagicMock()
    cog = Mafia(bot)
    g9 = Game.create(77, 900, 555, 88, [(901, 'P1'), (902, 'P2')])
    g9.phase = PHASE_PLAYING
    g9.cycle = CYCLE_NIGHT
    check(cog._voice_mute_wanted(g9, 900, night=True) is None, 'ведущий без мута')
    check(cog._voice_mute_wanted(g9, 901, night=True) is True, 'ночь — игрок мут')
    check(cog._voice_mute_wanted(g9, 901, night=False) is False, 'день — игрок говорит')
    member = MagicMock()
    member.id = 901
    member.bot = False
    ch = MagicMock()
    ch.id = 555
    vs = MagicMock()
    vs.channel = ch
    vs.mute = False
    guild = MagicMock()
    guild.voice_states = {901: vs}
    member.guild = guild
    member.voice = vs
    member.edit = AsyncMock()
    ok = await cog._apply_voice_mute_member(
        g9, member, night=True, reason='test-night')
    check(ok, 'edit(mute=True) вызван')
    member.edit.assert_called_once_with(mute=True, reason='test-night')
    return True


asyncio.run(_voice_mute_mock())


print('\n== 16. Сервер семьи мафии ==')
from services.mafia import family_guild as FG  # noqa: E402
check(FG.DEFAULT_FAMILY_GUILD_ID == 1554581698946277538, 'guild id семьи')
check(FG.family_guild_id() == 1554581698946277538, 'env/default family guild')
src_m2 = open(os.path.join(_REPO, 'cogs/mafia.py'), encoding='utf-8').read()
check('create_invites_for_team' in src_m2 and 'evict_mafia_family' in src_m2,
      'инвайт всей семье + выгон в cog')
check('Войти к семье' in src_m2, 'кнопка инвайта в ЛС')
check('on_member_join' in src_m2 and 'kick_if_not_mafia' in src_m2,
      'чужих с сервера семьи кикаем')
check('_iter_guild_voice_states' in src_m2, 'безопасный voice_states')
check('cleanup_game_messages' in src_m2 and 'purge' in src_m2,
      'purge сообщений бота в конце')
fg_src = open(os.path.join(_REPO, 'services/mafia/family_guild.py'),
              encoding='utf-8').read()
check('create_invites_for_team' in fg_src and 'asyncio.sleep' in fg_src,
      'инвайты с паузой от rate-limit')
check('kick_if_not_mafia' in fg_src and 'allowed_mafia_ids' in fg_src,
      'allowlist семьи на сервере')
# сериализация полей семьи
gfam = Game.create(50, 1, 9, 8, [(1, 'a'), (2, 'b'), (3, 'c'), (4, 'd'),
                                  (5, 'e'), (6, 'f')])
gfam.mafia_family_ids = [1, 2]
gfam.mafia_invite_codes = ['abc', 'def']
d = gfam.to_dict()
gfam2 = Game.from_dict(d)
check(gfam2.mafia_family_ids == [1, 2], 'persist family ids')
check(gfam2.mafia_invite_codes == ['abc', 'def'], 'persist invite codes')
_night_body = src_m2.split('async def on_night_started', 1)[1].split(
    'async def ', 1)[0]
check('send_mafia_night_chat' not in _night_body,
      'ночь без повторной панели чата')
_after_n = src_m2.split('async def after_night_action', 1)[1].split(
    'async def ', 1)[0]
check('announce(' not in _after_n, 'шаги ночи без публичного спама')


print(f'\nИтого: {PASS} PASS / {FAIL} FAIL')
sys.exit(1 if FAIL else 0)
