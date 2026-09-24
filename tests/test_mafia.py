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
    8: {'mafia': 2, 'sheriff': 1, 'doctor': 1, 'courtesan': 1, 'citizen': 3},
    9: {'mafia': 2, 'sheriff': 1, 'doctor': 1, 'courtesan': 1, 'citizen': 4},
    10: {'mafia': 3, 'sheriff': 1, 'doctor': 1, 'courtesan': 1, 'citizen': 4},
    11: {'mafia': 3, 'sheriff': 1, 'doctor': 1, 'courtesan': 1, 'citizen': 5},
    12: {'mafia': 3, 'don': 1, 'sheriff': 1, 'doctor': 1, 'courtesan': 1, 'citizen': 5},
    14: {'mafia': 3, 'don': 1, 'sheriff': 1, 'doctor': 1, 'courtesan': 1, 'citizen': 7},
}
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
opts = {o.value for o in MafiaActionSelect().options}
check(opts == {'start', 'deal', 'sync', 'status', 'panel', 'resend', 'add', 'cancel', 'presets'},
      f'меню действий: {sorted(opts)}')

# публичное лобби — только Участвовать/Выйти
from cogs.mafia import PublicLobbyView, HostToolsView  # noqa: E402
pub_labels = {i.label for i in PublicLobbyView(1).children if hasattr(i, 'label')}
check(pub_labels == {'Участвовать', 'Выйти'}, f'публичные кнопки: {pub_labels}')
check('Анонс' not in pub_labels and 'Старт' not in pub_labels, 'нет анонс/старт у участников')
host_labels = {i.label for i in HostToolsView(1).children if hasattr(i, 'label')}
check('Раздать роли' in host_labels, f'хост-панель: {host_labels}')

# стикеры ролей включая путану
from services.mafia.ui_v2 import sticker, role_sticker  # noqa: E402
check(sticker('join') is not None and sticker('courtesan') is not None, 'стикеры join+путана')
check(role_sticker('courtesan') is not None, 'role_sticker путана')

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


print('\n== 12. LEAN + KEEP_SLASH ==')
from cogs_policy import LEAN_COGS  # noqa: E402
import slash_budget  # noqa: E402
check('mafia.py' in LEAN_COGS, 'mafia.py в LEAN_COGS')
check('mafia' in slash_budget.KEEP_SLASH, 'mafia в KEEP_SLASH')


print(f'\nИтого: {PASS} PASS / {FAIL} FAIL')
sys.exit(1 if FAIL else 0)
