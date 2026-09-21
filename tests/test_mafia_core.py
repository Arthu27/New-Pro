# -*- coding: utf-8 -*-
"""Мафия — ядро игры (пресеты, раздача ролей, победа). Чистая логика,
без discord (см. tests/test_mafia_cog.py для дискорд-слоя).

Запуск: python3 tests/test_mafia_core.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


from services import mafia_core as MC  # noqa: E402

print('== 1. Пресеты по числу игроков (ТЗ, раздел 2) ==')
check(MC.preset_for_count(5) is None, '< 6 игроков — набирать нельзя')
check(MC.roles_for_preset(MC.preset_for_count(6), 6) ==
      {MC.MAFIA: 1, MC.SHERIFF: 1, MC.CIVILIAN: 4},
      '6 игроков: 1 мафия, 1 шериф, 4 мирных')
check(MC.roles_for_preset(MC.preset_for_count(7), 7) ==
      {MC.MAFIA: 1, MC.SHERIFF: 1, MC.DOCTOR: 1, MC.CIVILIAN: 4},
      '7 игроков: + доктор, 4 мирных')
r89 = MC.roles_for_preset(MC.preset_for_count(8), 8)
check(r89[MC.MAFIA] == 2 and r89[MC.PUTANA] == 1 and r89[MC.CIVILIAN] == 3,
      '8 игроков: 2 мафии, путана, 3 мирных', f'→ {r89}')
r9 = MC.roles_for_preset(MC.preset_for_count(9), 9)
check(r9[MC.CIVILIAN] == 4, '9 игроков (тот же пресет): 4 мирных', f'→ {r9}')
r1011 = MC.roles_for_preset(MC.preset_for_count(10), 10)
check(r1011[MC.MAFIA] == 3 and r1011[MC.CIVILIAN] == 4,
      '10 игроков: 3 мафии, 4 мирных', f'→ {r1011}')
r12 = MC.roles_for_preset(MC.preset_for_count(12), 12)
check(r12[MC.MAFIA] == 3 and r12[MC.DON] == 1 and r12[MC.CIVILIAN] == 5,
      '12 игроков: 3 мафии + дон, 5 мирных', f'→ {r12}')
r20 = MC.roles_for_preset(MC.preset_for_count(20), 20)
check(r20[MC.DON] == 1 and r20[MC.CIVILIAN] == 13,
      '20 игроков (тот же 12+ пресет): состав активных не растёт, мирных больше',
      f'→ {r20}')

print('== 2. Раздача ролей — случайно, но точно по составу ==')
players = [f'p{i}' for i in range(12)]
mapping = MC.assign_roles(players, MC.preset_for_count(12))
check(set(mapping.keys()) == set(players), 'все игроки получили роль')
counts = {}
for role in mapping.values():
    counts[role] = counts.get(role, 0) + 1
check(counts.get(MC.MAFIA) == 3 and counts.get(MC.DON) == 1
      and counts.get(MC.SHERIFF) == 1 and counts.get(MC.DOCTOR) == 1
      and counts.get(MC.PUTANA) == 1 and counts.get(MC.CIVILIAN) == 5,
      'состав ролей совпадает с пресетом 12+', f'→ {counts}')

# перемешивание реально работает (не всегда один и тот же порядок)
import random as _r
seen = set()
for seed in range(8):
    m = MC.assign_roles(players, MC.preset_for_count(12), rng=_r.Random(seed))
    seen.add(tuple(m[p] for p in players))
check(len(seen) > 1, 'раздача рандомизирована (разные seed — разные раскладки)')

print('== 3. Победа: мирные ==')
roles6 = {'a': MC.MAFIA, 'b': MC.SHERIFF, 'c': MC.CIVILIAN, 'd': MC.CIVILIAN,
         'e': MC.CIVILIAN, 'f': MC.CIVILIAN}
check(MC.check_winner(roles6, {'a', 'b', 'c', 'd', 'e', 'f'}) is None,
      'мафия жива, перекоса нет — игра продолжается')
check(MC.check_winner(roles6, {'b', 'c', 'd', 'e', 'f'}) == 'good',
      'мафию исключили — мирные победили')

print('== 4. Победа: мафия по соотношению (включая шерифа/доктора) ==')
roles_ratio = {'m1': MC.MAFIA, 'm2': MC.MAFIA, 'sh': MC.SHERIFF,
              'doc': MC.DOCTOR, 'c1': MC.CIVILIAN, 'c2': MC.CIVILIAN}
check(MC.check_winner(roles_ratio, set(roles_ratio)) is None,
      '2 мафии vs 4 «мирных» (шериф+доктор+2 мирных) — мафия не выигрывает')
check(MC.check_winner(roles_ratio, {'m1', 'm2', 'sh', 'doc'}) == 'mafia',
      '2 мафии vs 2 «мирных» (2:2, шериф+доктор считаются) — мафия победила')
roles_don = {'m1': MC.MAFIA, 'don': MC.DON, 'c1': MC.CIVILIAN}
check(MC.check_winner(roles_don, set(roles_don)) == 'mafia',
      'дон считается мафией: 2 мафии (вкл. дона) vs 1 мирный — мафия победила')

print('== 5. MafiaGame: сквозной цикл партии ==')
g = MC.MafiaGame(1001, guild_id=1, channel_id=42, voice_channel_id=99,
                host_id=777, host_name='Ведущий')
for i in range(6):
    ok = g.add_player(700 + i, f'Игрок{i}')
    check(ok, f'игрок {i} добавлен в набор')
check(not g.add_player(777, 'Ведущий'),
      'ведущего в игроки не добавить (сам себя исключает)')
check(g.add_player(700, 'Дубль') is False,
      'повторное добавление того же uid — no-op')
check(g.player_count() == 6, 'в наборе 6 игроков')
check(g.suggested_preset() == MC.preset_for_count(6),
      'авто-пресет по текущему числу игроков')

mapping = g.deal()
check(g.phase == MC.PHASE_CONFIRM, 'после раздачи — фаза подтверждения')
check(all(p.role for p in g.players.values()), 'у всех игроков есть роль')
check(all(p.status == MC.STATUS_PENDING for p in g.players.values()),
      'все статусы — «ожидает подтверждения»')
check(g.confirmed_count() == 0, 'подтверждений пока 0')

first_uid = next(iter(g.players))
check(g.confirm(first_uid) is True, 'первое подтверждение — статус сменился')
check(g.confirm(first_uid) is False,
      'повторный клик «Подтвердить» — идемпотентно, без второго события')
check(g.confirmed_count() == 1, 'подтверждений 1 после дедупликации повтора')
check(not g.all_confirmed(), 'не все подтвердили — рано начинать')

for uid in g.players:
    g.confirm(uid)
check(g.all_confirmed(), 'все подтвердили участие')

try:
    g2 = MC.MafiaGame(1002, 1, 42, 99, 777, 'Ведущий')
    for i in range(6):
        g2.add_player(800 + i, f'X{i}')
    g2.start()
    check(False, 'старт без раздачи ролей должен упасть')
except ValueError:
    check(True, 'нельзя начать игру, если роли не разданы/не все подтвердили')

g.start()
check(g.phase == MC.PHASE_ACTIVE, 'игра активна — состав зафиксирован')

print('== 6. Активная фаза: устранения и авто-детект победителя ==')
mafia_uid = next(uid for uid, p in g.players.items() if p.role == MC.MAFIA)
sheriff_uid = next(uid for uid, p in g.players.items() if p.role == MC.SHERIFF)
civ_uids = [uid for uid, p in g.players.items() if p.role == MC.CIVILIAN]

is_mafia = g.sheriff_check(mafia_uid)
check(is_mafia is True, 'шериф проверил мафию — ответ «мафия»')
is_mafia2 = g.sheriff_check(civ_uids[0])
check(is_mafia2 is False, 'шериф проверил мирного — ответ «мирный»')

winner = g.eliminate(civ_uids[0], 'Исключён голосованием')
check(winner is None, 'исключили мирного — игра продолжается (1 мафия vs 4 живых)')
winner = g.eliminate(mafia_uid, 'Мафия устранена')
check(winner == 'good' and g.winner == 'good' and g.phase == MC.PHASE_ENDED,
      'мафии не осталось — мирные победили, фаза «ended»')
check(g.eliminate(sheriff_uid, 'ещё раз') == 'good',
      'после конца партии повторный eliminate не переигрывает исход')

print('== 7. Активная фаза: победа мафии по соотношению ==')
g3 = MC.MafiaGame(1003, 1, 43, 98, 900, 'Ведущий2')
for i in range(6):
    g3.add_player(910 + i, f'Y{i}')
g3.deal()
for uid in g3.players:
    g3.confirm(uid)
g3.start()
mafia3 = next(uid for uid, p in g3.players.items() if p.role == MC.MAFIA)
sheriff3 = next(uid for uid, p in g3.players.items() if p.role == MC.SHERIFF)
civs3 = [uid for uid, p in g3.players.items() if p.role == MC.CIVILIAN]
# живых мирных 5 (sheriff+4 civ) vs 1 мафия — снесём 3 мирных (останется sheriff+1 civ = 2)
for uid in civs3[:3]:
    w = g3.eliminate(uid, 'Мафия убила ночью')
    check(w is None, 'соотношение ещё не 1:1/выше — партия идёт')
w_final = g3.eliminate(civs3[3], 'Мафия убила ночью')
check(w_final == 'mafia' and g3.winner == 'mafia',
      '1 мафия vs 1 «мирный» (шериф) — мафия победила по соотношению')

print('== 8. Реестр партий: одна игра на канал ==')
reg = MC.GameRegistry()
a = MC.MafiaGame(reg.next_id(), 1, 100, 1, 1, 'H')
reg.set(100, a)
check(reg.get(100) is a, 'партия найдена по channel_id')
check(reg.get(999) is None, 'в другом канале партии нет')
reg.remove(100)
check(reg.get(100) is None, 'после remove партия исчезает')
ids = {reg.next_id() for _ in range(5)}
check(len(ids) == 5, 'next_id уникален на каждый вызов')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
