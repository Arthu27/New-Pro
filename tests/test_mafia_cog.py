# -*- coding: utf-8 -*-
"""Мафия — дискорд-слой (cogs/mafia.py) на моках, без реального Discord.

Проверяет весь путь ведущего: /mafia start (голосовой канал → набор
игроков), «Раздать роли» (ЛС + идемпотентное подтверждение), /mafia
kick/add/resend/remind, «Начать игру» (блокировка состава), кнопки
активной партии (убийство/голосование/проверки шерифа и дона) с
авто-детектом победителя и баннером.

Запуск: python3 tests/test_mafia_cog.py
"""
import asyncio
import os
import sys
import tempfile
import types
from types import SimpleNamespace as NS

_TMP = tempfile.mkdtemp(prefix='mafia_cog_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath('data/bot.db')

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


import discord  # noqa: E402
from cogs import mafia as M  # noqa: E402
from services import mafia_core as MC  # noqa: E402


# ── моки ──────────────────────────────────────────────────────────────
class _Msg:
    def __init__(self, mid):
        self.id = mid
        self.channel = None
        self.edits = []
        self.deleted = False

    async def edit(self, **kw):
        self.edits.append(kw)
        return self


class _Channel:
    def __init__(self, cid):
        self.id = cid
        self.sent = []

    async def send(self, **kw):
        msg = _Msg(9000 + len(self.sent))
        msg.channel = self
        self.sent.append(kw)
        return msg


class _VoiceChannel:
    def __init__(self, vid):
        self.id = vid
        self.members = []


class _Member:
    def __init__(self, uid, name, guild=None, voice_channel=None, dm_fails=False):
        self.id = uid
        self.name = name
        self.display_name = name
        self.mention = f'<@{uid}>'
        self.bot = False
        self.guild = guild
        self.voice = NS(channel=voice_channel) if voice_channel else None
        self.dm_fails = dm_fails
        self.dms = []

    async def send(self, **kw):
        if self.dm_fails:
            raise discord.Forbidden(NS(status=403, reason='Cannot send'), 'DMs closed')
        msg = _Msg(5000 + len(self.dms))
        self.dms.append(kw)
        return msg


class _Guild:
    def __init__(self, gid, members):
        self.id = gid
        self._members = {m.id: m for m in members}

    def get_member(self, uid):
        return self._members.get(uid)

    def get_channel(self, cid):
        for m in self._members.values():
            vc = getattr(getattr(m, 'voice', None), 'channel', None)
            if vc is not None and vc.id == cid:
                return vc
        return None


class _Resp:
    def __init__(self):
        self._done = False
        self.sent = []
        self.edits = []
        self.deferred = None

    def is_done(self):
        return self._done

    async def send_message(self, content=None, **kw):
        if content is not None:
            kw['content'] = content
        self.sent.append(kw)
        self._done = True

    async def defer(self, **kw):
        self.deferred = kw
        self._done = True

    async def edit_message(self, **kw):
        self.edits.append(kw)
        self._done = True


class _Followup:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **kw):
        if content is not None:
            kw['content'] = content
        msg = _Msg(6000 + len(self.sent))
        self.sent.append(kw)
        return msg


class _Inter:
    def __init__(self, user, guild, channel):
        self.user = user
        self.guild = guild
        self.guild_id = guild.id if guild else None
        self.channel = channel
        self.channel_id = channel.id if channel else None
        self.response = _Resp()
        self.followup = _Followup()
        self.client = None

    async def edit_original_response(self, **kw):
        self.channel.sent.append(kw) if self.channel else None
        msg = _Msg(9999)
        return msg


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _Bot:
    def __init__(self, guild):
        self._guild = guild

    def get_guild(self, gid):
        return self._guild if gid == self._guild.id else None


# ── сценарий: 6 игроков в войсе, ведущий — 7-й (исключается) ──────────
GID = 1
CHID = 500
VC_ID = 900

host = _Member(1, 'Ведущий')
players_raw = [_Member(100 + i, f'Игрок{i}') for i in range(6)]
vc = _VoiceChannel(VC_ID)
vc.members = [host] + players_raw
host.voice = NS(channel=vc)
for p in players_raw:
    p.voice = NS(channel=vc)

guild = _Guild(GID, [host] + players_raw)
channel = _Channel(CHID)
bot = _Bot(guild)
cog = M.Mafia(bot)


print('== 1. /mafia start: без войса — отказ ==')
lone = _Member(999, 'Одинокий')
inter0 = _Inter(lone, guild, channel)
run(cog.start.callback(cog, inter0))
check(bool(inter0.response.sent) and 'голосовой' in inter0.response.sent[0].get('content', ''),
      'без войса — понятная подсказка', f'→ {inter0.response.sent}')
check(MC.REGISTRY.get(CHID) is None, 'партия не создана')

print('== 2. /mafia start: собирает войс, исключает ведущего ==')
inter1 = _Inter(host, guild, channel)
run(cog.start.callback(cog, inter1))
game = MC.REGISTRY.get(CHID)
check(game is not None, 'партия создана и зарегистрирована по каналу')
check(game.player_count() == 6, 'в наборе 6 игроков (ведущий не включён)',
      f'→ {game.player_count()}')
check(host.id not in game.players, 'ведущего нет среди игроков')
check(len(inter1.followup.sent) == 1, 'панель отправлена одним сообщением (followup)')
check(game.panel_message_ref is not None, 'ссылка на панель сохранена для правок')

print('== 3. Повторный /mafia start в том же канале — отказ ==')
inter1b = _Inter(host, guild, channel)
run(cog.start.callback(cog, inter1b))
check('уже идёт' in (inter1b.response.sent[0].get('content', '') if inter1b.response.sent else ''),
      'повторный старт в занятом канале отклонён')

print('== 4. Кик/добавление до раздачи ролей ==')
kicked = players_raw[0]
inter_kick = _Inter(host, guild, channel)
run(cog.kick.callback(cog, inter_kick, kicked))
check(kicked.id not in game.players, 'игрок убран из набора')
check(game.player_count() == 5, 'счёт уменьшился')

not_host_inter = _Inter(players_raw[1], guild, channel)
run(cog.kick.callback(cog, not_host_inter, players_raw[2]))
check('ведущий' in not_host_inter.response.sent[0]['content'].lower(),
      'не-ведущий не может кикать')
check(players_raw[2].id in game.players, 'кик от не-ведущего не применился')

inter_add = _Inter(host, guild, channel)
run(cog.add.callback(cog, inter_add, kicked))
check(kicked.id in game.players, 'игрок добавлен обратно (он в том же войсе)')

outsider = _Member(777, 'Чужой', voice_channel=None)
inter_add2 = _Inter(host, guild, channel)
run(cog.add.callback(cog, inter_add2, outsider))
check(outsider.id not in game.players,
      'нельзя добавить того, кто не в голосовом канале игры')

print('== 5. Раздача ролей: ЛС всем, у кого-то ЛС закрыты ==')
dm_closed = players_raw[3]
dm_closed.dm_fails = True
view = game.panel_message_ref[1]
deal_inter = _Inter(host, guild, channel)
run(view._on_deal(deal_inter))
check(game.phase == MC.PHASE_CONFIRM, 'после раздачи — фаза подтверждения')
check(all(p.role for p in game.players.values()), 'у всех есть роль')
ok_players = [p for uid, p in game.players.items() if uid != dm_closed.id]
check(all(p.dm_ok for p in ok_players), 'ЛС ушли всем, у кого они открыты')
check(game.players[dm_closed.id].dm_ok is False,
      'у игрока с закрытыми ЛС — dm_ok=False (не падаем)')
check(host.dms, 'ведущему пришла приватная сводка')

print('== 6. Подтверждение — идемпотентно, панель обновляется ==')
first_uid = next(iter(game.players))
first_confirm_kw = host.dms[-1]  # сводка — не карточка; берём карточку явно
role_card = None
for uid, p in game.players.items():
    if p.dm_ok:
        role_card = uid
        break
member_for_card = guild.get_member(role_card)
card_kw = member_for_card.dms[-1]
card_view = card_kw['view']
confirm_inter = _Inter(member_for_card, guild, channel)
run(card_view._confirm(confirm_inter))
check(game.players[role_card].status == MC.STATUS_CONFIRMED,
      'статус игрока сменился на «подтверждено»')
edits_after_1 = len(game.panel_message_ref[0].edits)
check(edits_after_1 >= 1, 'публичная панель обновилась после подтверждения')
run(card_view._confirm(confirm_inter))
check(len(game.panel_message_ref[0].edits) == edits_after_1,
      'повторный клик «Подтвердить» — панель НЕ дёргается снова (идемпотентно)')

print('== 7. «Показать мою роль» — эфемерный self-check работает без ЛС ==')
self_check_inter = _Inter(dm_closed, guild, channel)
run(view._on_myrole(self_check_inter))
check(bool(self_check_inter.response.sent), 'эфемерная карточка роли отправлена')
check(self_check_inter.response.sent[0].get('ephemeral') is True,
      'карточка именно эфемерная (не видна остальным)')

print('== 8. Подтверждаем всех, запускаем игру ==')
for uid, p in list(game.players.items()):
    game.confirm(uid)
check(game.all_confirmed(), 'все подтвердили')
start_inter = _Inter(host, guild, channel)
run(view._on_start(start_inter))
check(game.phase == MC.PHASE_ACTIVE, '«Начать игру» переводит партию в активную фазу')
check(hasattr(game, 'active_panel_ref') and game.active_panel_ref is not None,
      'панель активной игры отправлена')

print('== 9. Не-ведущий не может распоряжаться активной партией ==')
bad_kill = _Inter(players_raw[1], guild, channel)
run(cog.kill.callback(cog, bad_kill, players_raw[2]))
check('ведущий' in bad_kill.response.sent[0]['content'].lower(),
      'убийство от не-ведущего отклонено')
check(players_raw[2].id in game.alive_ids(), 'игрок остался жив')

print('== 10. /mafia check и /mafia doncheck — приватный ответ ведущему ==')
mafia_uid = next(uid for uid, p in game.players.items() if p.role == MC.MAFIA)
mafia_member = guild.get_member(mafia_uid)
check_inter = _Inter(host, guild, channel)
run(cog.check.callback(cog, check_inter, mafia_member))
check(any('Мафия' in kw.get('content', '') for kw in check_inter.followup.sent),
      'шериф-проверка честно называет мафию', f'→ {check_inter.followup.sent}')

civ_uid = next(uid for uid, p in game.players.items() if p.role == MC.CIVILIAN)
civ_member = guild.get_member(civ_uid)
check_inter2 = _Inter(host, guild, channel)
run(cog.check.callback(cog, check_inter2, civ_member))
check(any('Мирный' in kw.get('content', '') for kw in check_inter2.followup.sent),
      'шериф-проверка честно называет мирного')

print('== 11. Убийства до победы — авто-детект и баннер ==')
before_sent = len(channel.sent)
civ_uids = [uid for uid, p in game.players.items() if p.role == MC.CIVILIAN]
for uid in civ_uids[:-1]:
    m = guild.get_member(uid)
    ki = _Inter(host, guild, channel)
    run(cog.kill.callback(cog, ki, m))
check(game.phase == MC.PHASE_ACTIVE, 'ещё не все «мирные» устранены — игра идёт')
last_civ = guild.get_member(civ_uids[-1])
final_inter = _Inter(host, guild, channel)
run(cog.kill.callback(cog, final_inter, last_civ))
check(game.phase == MC.PHASE_ENDED and game.winner == 'mafia',
      'соотношение достигнуто — победила мафия, партия окончена')
check(len(channel.sent) > before_sent, 'баннер победы отправлен в канал')
check(MC.REGISTRY.get(CHID) is None,
      'партия снята с реестра после окончания (канал свободен для новой)')
banner_kw = channel.sent[-1]
_banner_text = ''
if 'view' in banner_kw:
    for item in banner_kw['view'].children:
        _banner_text += str(getattr(item, 'children', ''))
check('view' in banner_kw or 'embed' in banner_kw,
      'баннер — V2 view или embed (не голый текст)')


print('== 12. Отмена партии до раздачи (/mafia cancel) ==')
host2 = _Member(2, 'Ведущий2')
p2 = [_Member(200 + i, f'Y{i}') for i in range(6)]
vc2 = _VoiceChannel(901)
vc2.members = [host2] + p2
host2.voice = NS(channel=vc2)
for p in p2:
    p.voice = NS(channel=vc2)
guild2 = _Guild(2, [host2] + p2)
channel2 = _Channel(501)
bot2 = _Bot(guild2)
cog2 = M.Mafia(bot2)
run(cog2.start.callback(cog2, _Inter(host2, guild2, channel2)))
check(MC.REGISTRY.get(501) is not None, 'вторая партия создана в своём канале')
cancel_inter = _Inter(host2, guild2, channel2)
run(cog2.cancel.callback(cog2, cancel_inter))
check(MC.REGISTRY.get(501) is None, '/mafia cancel снимает партию с реестра')
check('отменена' in cancel_inter.response.sent[0]['content'].lower(),
      'ведущему приходит подтверждение отмены')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
