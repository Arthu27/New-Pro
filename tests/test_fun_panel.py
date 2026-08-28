# -*- coding: utf-8 -*-
"""Развлечения (идеи #186-190).

Хелперы 1:1 cogs/minigames.py и cogs/fun_cog.py: нормализация прогноза
монетки, кламп кубиков 1..5 и сумма при n>1, таблица побед КНБ, двенадцать
ответов шара с тонами, те же десять шуток и двенадцать цитат, разборы
meme/cat/dog и их тексты ошибок. Жребий: боты вне отбора, фильтр роли тем
же выражением, пустые кандидаты — словами команды, offline — честный 409.
Галерея: те же URL, ошибки словами команд. Роли для фильтра без @everyone.

Запуск: python3 tests/test_fun_panel.py
"""
import importlib
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_fun_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'admin'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'

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


from cogs import minigames as MG  # noqa: E402
from cogs import fun_cog as FC  # noqa: E402
from web.routes import fun_panel as FP  # noqa: E402

EMOJI_RE = re.compile('[\\U0001F000-\\U0001FAFF\\u2B00-\\u2BFF\\uFE0F]|[☀-➿]')
FIRST = lambda seq: seq[0]  # noqa: E731
SIX = lambda a, b: 6        # noqa: E731


class FakeMember:
    def __init__(self, name, mid, bot=False, roles=()):
        self.display_name = name
        self.id = mid
        self.bot = bot
        self.roles = list(roles)


class FakeRole:
    def __init__(self, name, rid):
        self.name = name
        self.id = rid


class FakeGuild:
    def __init__(self, gid, members=(), roles=()):
        self.id = gid
        self.members = list(members)
        self.roles = list(roles)


class FakeBot:
    def __init__(self, guilds):
        self.guilds = list(guilds)

    def get_guild(self, gid):
        return next((g for g in self.guilds if g.id == gid), None)


R_EVERYONE = FakeRole('@everyone', 777)
R_MOD = FakeRole('Моды', 201)
R_ADMIN = FakeRole('Админ', 202)
R_EMPTY = FakeRole('Пустая', 203)
M_ANNA = FakeMember('Анна', 1)
M_BOT = FakeMember('FunBot', 2, bot=True)
M_OLEG = FakeMember('Олег', 3, roles=[R_MOD])
M_KATYA = FakeMember('Катя', 4, roles=[R_ADMIN])
G777 = FakeGuild(777,
                 members=[M_ANNA, M_BOT, M_OLEG, M_KATYA],
                 roles=[R_EVERYONE, R_MOD, R_ADMIN, R_EMPTY])
FB = FakeBot([G777])

print('== 1. Монетка 1:1 /coinflip ==')
check(MG.norm_coin_pick('орёл') == 'Орёл', '«орёл» — Орёл')
check(MG.norm_coin_pick('Orel') == 'Орёл', '«Orel» без регистра — Орёл')
check(MG.norm_coin_pick('  ОРЕЛ ') == 'Орёл', 'пробелы и регистр чистятся')
check(MG.norm_coin_pick('решка') == 'Решка', '«решка» — Решка')
check(MG.norm_coin_pick('RESHKA') == 'Решка', '«RESHKA» — Решка')
check(MG.norm_coin_pick('камень') is None, 'постороннее слово — None')
check(MG.norm_coin_pick('') is None and MG.norm_coin_pick(None) is None
      and MG.norm_coin_pick('   ') is None, 'пустота — None')
g = MG.flip_coin('орёл', chooser=FIRST)
check(g == {'result': 'Орёл', 'pick': 'Орёл', 'guessed': True, 'correct': True},
      'прогноз совпал — correct')
g = MG.flip_coin('решка', chooser=FIRST)
check(g['correct'] is False and g['pick'] == 'Решка', 'прогноз мимо — не correct')
g = MG.flip_coin('блабла', chooser=FIRST)
check(g['guessed'] is True and g['pick'] is None and g['correct'] is False,
      'мусорный прогноз засчитан как попытка, но не верный — как в команде')
g = MG.flip_coin(None, chooser=FIRST)
check(g['guessed'] is False and g['result'] == 'Орёл', 'без прогноза — просто бросок')
ok, err, code, p = FP.coinflip_flow({'pick': 'orel'}, chooser=FIRST)
check(ok and code == 200 and p['status'] == 'Верно!' and p['correct'] is True,
      'флоу: статус словами эмбеда без эмодзи')
ok, err, code, p = FP.coinflip_flow({'pick': '   '})
check(ok and p['guessed'] is False and 'status' not in p,
      'пробельный прогноз снимается — как отсутствие параметра')

print('== 2. Кубики 1:1 /dice ==')
g = MG.roll_dice(3, randint=SIX)
check(g['count'] == 3 and g['results'] == [6, 6, 6]
      and g['faces'] == '⚅ ⚅ ⚅' and g['total'] == 18,
      'три кости: результаты, грани и сумма')
check(g['faces'] == ' '.join(MG._DICE[r] for r in g['results']),
      'грани — из таблицы _DICE кога')
g = MG.roll_dice(0, randint=SIX)
check(g['count'] == 1 and g['total'] is None,
      'ноль костей зажат в одну, суммы нет — как поле эмбеда')
g = MG.roll_dice(9, randint=SIX)
check(g['count'] == 5 and g['total'] == 30, 'девять костей зажато в пять')
ok, err, code, p = FP.dice_flow({'count': 'abc'})
check(not ok and code == 400 and err == FP.ERR_COUNT, 'не число — 400')
ok, err, code, p = FP.dice_flow({}, randint=SIX)
check(ok and p['count'] == 1 and p['results'] == [6], 'по умолчанию одна кость')

print('== 3. КНБ 1:1 /rps ==')
g = MG.play_rps('камень', chooser=FIRST)
check(g['outcome'] == 'draw' and g['result'] == 'Ничья!' and g['color'] == 0xF39C12,
      'камень на камень — ничья с янтарным цветом')
g = MG.play_rps('бумага', chooser=FIRST)
check(g['outcome'] == 'win' and g['result'] == 'Победа!' and g['color'] == 0x2ECC71,
      'бумага бьёт камень — победа с зелёным')
g = MG.play_rps('ножницы', chooser=FIRST)
check(g['outcome'] == 'lose' and g['result'] == 'Поражение!' and g['color'] == 0xE74C3C,
      'ножницы о камень — поражение с красным')
for user in MG.RPS_CHOICES:
    for bot in MG.RPS_CHOICES:
        gg = MG.play_rps(user, chooser=lambda seq, b=bot: seq[seq.index(b)])
        want = ('draw' if user == bot
                else 'win' if MG.RPS_WINS[user] == bot else 'lose')
        if gg['outcome'] != want or gg['bot_choice'] != bot:
            check(False, f'таблица исходов {user}/{bot}')
            break
    else:
        continue
    break
else:
    check(True, 'все девять исходов по таблице RPS_WINS кога')
check(MG.play_rps('камень')['choice_emoji'] == MG.RPS_EMOJIS['камень'],
      'эмодзи хода — из таблицы кога')
try:
    MG.play_rps('камешек')
    check(False, 'чужой выбор должен падать')
except ValueError:
    check(True, 'чужой выбор — ValueError, как choices Discord')
ok, err, code, p = FP.rps_flow({'choice': 'земля'})
check(not ok and code == 400 and err == FP.ERR_RPS, 'флоу режет чужой выбор')
ok, err, code, p = FP.rps_flow({'choice': 'камень'}, chooser=FIRST)
check(ok and p['bot_name'] == 'Камень' and p['result'] == 'Ничья!',
      'флоу отдаёт имена и текст 1:1')

print('== 4. Магический шар 1:1 /8ball ==')
check(len(MG.EIGHT_BALL) == 12, 'двенадцать ответов')
check(all(tone in ('yes', 'maybe', 'no') for tone in MG.EIGHT_BALL_TONES.values())
      and all(color in MG.EIGHT_BALL_TONES for _, color in MG.EIGHT_BALL),
      'тон заведён для каждого цвета списка')
g = MG.ask_8ball('  Выиграю?  ', chooser=FIRST)
check(g == {'question': 'Выиграю?', 'answer': 'Определённо да!',
            'color': 0x2ECC71, 'tone': 'yes'},
      'первый ответ — зелёное «да», вопрос подрезан')
g = MG.ask_8ball('q', chooser=lambda seq: seq[4])
check(g['tone'] == 'maybe', 'пятый ответ — нейтральный')
g = MG.ask_8ball('q', chooser=lambda seq: seq[8])
check(g['tone'] == 'no', 'девятый ответ — красный')
ok, err, code, p = FP.eightball_flow({'question': '   '})
check(not ok and code == 400 and err == FP.ERR_QUESTION, 'пустой вопрос — 400')

print('== 5. Списки и разборы fun_cog ==')
check(len(FC.JOKES) == 10 and len(FC.QUOTES) == 12, 'десять шуток и двенадцать цитат')
check(FC.random_joke(chooser=FIRST) == FC.JOKES[0]
      and FC.random_quote(chooser=FIRST) == FC.QUOTES[0],
      'рандом по тем же спискам')
check(FC.MEME_URL == 'https://meme-api.com/gimme'
      and FC.CAT_URL == 'https://aws.random.cat/meow'
      and FC.DOG_URL == 'https://dog.ceo/api/breeds/image/random',
      'адреса внешних сервисов прежние')
check(FC.MEME_ERR == 'Не удалось загрузить мем, попробуй ещё!'
      and FC.CAT_ERR == 'Не удалось загрузить кота, попробуй ещё!'
      and FC.DOG_ERR == 'Не удалось загрузить собаку, попробуй ещё!',
      'тексты ошибок словами команд')
m = FC.parse_meme({'url': 'u', 'title': 'T', 'subreddit': 's', 'ups': 5})
check(m == {'title': 'T', 'subreddit': 's', 'ups': 5, 'image': 'u'},
      'мем разобран 1:1')
check(FC.parse_meme({'url': 'u'}) == {'title': 'Случайный мем', 'subreddit': '?',
                                      'ups': 0, 'image': 'u'},
      'дефолты полей мема — как в команде')
check(FC.parse_meme({'title': 'x'}) is None and FC.parse_meme(None) is None,
      'мем без url отбрасывается — как raise в команде')
check(FC.parse_cat({'file': 'f'}) == {'image': 'f', 'text': 'Вот тебе милый котик!'}
      and FC.parse_cat({}) is None, 'кот 1:1')
check(FC.parse_dog({'message': 'm'}) == {'image': 'm', 'text': 'Вот тебе милый пёсик!'}
      and FC.parse_dog({'status': 'ok'}) is None, 'собака 1:1')
ok, err, code, p = FP.joke_flow(chooser=FIRST)
check(ok and p['text'] == FC.JOKES[0] and p['footer'] == 'Смех бесплатный!',
      'флоу шутки: текст и футер команды')
ok, err, code, p = FP.quote_flow(chooser=FIRST)
check(ok and p['text'] == FC.QUOTES[0], 'флоу цитаты')

print('== 6. Жребий 1:1 /random-member ==')
cands = MG.member_candidates(G777)
check([m.display_name for m in cands] == ['Анна', 'Олег', 'Катя'],
      'боты вне отбора — выражение команды')
check(MG.member_candidates(G777, R_MOD) == [M_OLEG], 'фильтр роли тем же выражением')
check(MG.member_candidates(G777, R_EMPTY) == [], 'пустая роль — нет кандидатов')
cands, chosen = MG.pick_random_member(G777, chooser=FIRST)
check(chosen is M_ANNA and len(cands) == 3, 'выбор детерминирован инжекцией')
cands, chosen = MG.pick_random_member(G777, R_EMPTY)
check(chosen is None and cands == [], 'без кандидатов — (пусто, None)')
ok, err, code, p = FP.random_member_flow(lambda: None, '777')
check(not ok and code == 409 and err == 'Бот не работает', 'без бота — 409')
ok, err, code, p = FP.random_member_flow(lambda: FB, '999')
check(not ok and code == 404 and err == FP.ERR_GUILD, 'чужой сервер — 404')
ok, err, code, p = FP.random_member_flow(lambda: FB, '777', chooser=FIRST)
check(ok and p['member'] == {'name': 'Анна', 'id': '1'} and p['candidates'] == 3
      and p['role'] is None, 'жребий без фильтра')
ok, err, code, p = FP.random_member_flow(lambda: FB, '777', role_id='201')
check(ok and p['member']['name'] == 'Олег' and p['candidates'] == 1
      and p['role'] == {'id': '201', 'name': 'Моды'}, 'жребий с фильтром роли')
ok, err, code, p = FP.random_member_flow(lambda: FB, '777', role_id='203')
check(not ok and code == 404 and err == 'Подходящих участников не найдено!',
      'пустой список — словами команды')
ok, err, code, p = FP.random_member_flow(lambda: FB, '777', role_id='999')
check(not ok and code == 404 and err == FP.ERR_ROLE, 'нет такой роли — 404')
ok, err, code, p = FP.random_member_flow(lambda: FB, '777', role_id='бла')
check(not ok and code == 400 and err == FP.ERR_ROLE, 'битый id роли — 400')
ok, err, code, p = FP.random_member_flow(lambda: FB, '777', role_id='0',
                                         chooser=FIRST)
check(ok and p['candidates'] == 3, 'нулевой id — как отсутствие фильтра')

print('== 7. Галерея 1:1 !meme/!cat/!dog ==')
ok, err, code, p = FP.gallery_flow('meme', fetch=lambda url: {
    'url': 'u', 'title': 't', 'subreddit': 's', 'ups': 3})
check(ok and p == {'kind': 'meme', 'title': 't', 'subreddit': 's', 'ups': 3,
                   'image': 'u'}, 'мем через инжекцию')
ok, err, code, p = FP.gallery_flow('meme', fetch=lambda url: None)
check(not ok and code == 502 and err == 'Не удалось загрузить мем, попробуй ещё!',
      'сбой мема — словами команды')
ok, err, code, p = FP.gallery_flow('cat', fetch=lambda url: {'file': 'f'})
check(ok and p == {'kind': 'cat', 'image': 'f', 'text': 'Вот тебе милый котик!'},
      'кот через инжекцию')
ok, err, code, p = FP.gallery_flow('cat', fetch=lambda url: None)
check(not ok and code == 502 and err == FC.CAT_ERR, 'сбой кота — словами команды')
ok, err, code, p = FP.gallery_flow('dog', fetch=lambda url: {'status': 'fail'})
check(not ok and code == 502 and err == FC.DOG_ERR,
      'dog.ceo без message — ошибка команды')
ok, err, code, p = FP.gallery_flow('bird', fetch=lambda url: {})
check(not ok and code == 400 and err == FP.ERR_KIND, 'чужой вид — 400')

print('== 8. Живые роли для фильтра ==')
ok, err, code, p = FP.roles_flow(lambda: None, '777')
check(not ok and code == 409 and err == 'Бот не работает', 'роли без бота — 409')
ok, err, code, p = FP.roles_flow(lambda: FB, '999')
check(not ok and code == 404 and err == FP.ERR_GUILD, 'роли чужого сервера — 404')
ok, err, code, p = FP.roles_flow(lambda: FB, '777')
check(ok and p['roles'] == [{'id': '201', 'name': 'Моды'},
                            {'id': '202', 'name': 'Админ'},
                            {'id': '203', 'name': 'Пустая'}],
      'роли без @everyone, в порядке кэша')

print('== 9. API и права ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as sess:
        sess.clear()
        sess['logged_in'] = True
        sess['username'] = 'admin'
        sess['role'] = role


check(client.get('/fun').status_code in (302, 401, 403), 'гостю страница закрыта')
check(client.post('/api/guild/777/fun/coinflip', json={}).status_code
      in (302, 401, 403), 'гостю API закрыто')
login('uye')
check(client.get('/fun').status_code == 302, 'uye не играет')
check(client.post('/api/guild/777/fun/rps', json={'choice': 'камень'})
      .status_code == 403, 'uye не дерётся в КНБ')
login('mod')
page = client.get('/fun')
check(page.status_code == 200
      and 'Развлечения' in page.get_data(as_text=True), 'mod открывает страницу')
d = client.post('/api/guild/777/fun/coinflip', json={}).get_json()
check(d['success'] and d['result'] in ('Орёл', 'Решка') and d['guessed'] is False,
      'монетка через API')
d = client.post('/api/guild/777/fun/dice', json={'count': 3}).get_json()
check(d['success'] and len(d['results']) == 3
      and d['total'] == sum(d['results']) and all(1 <= r <= 6 for r in d['results']),
      'кубики через API')
r = client.post('/api/guild/777/fun/dice', json={'count': 'x'})
check(r.status_code == 400 and r.get_json()['error'] == FP.ERR_COUNT,
      'битое число кубиков — 400')
d = client.post('/api/guild/777/fun/rps', json={'choice': 'ножницы'}).get_json()
check(d['success'] and d['outcome'] in ('win', 'draw', 'lose')
      and d['bot_choice'] in MG.RPS_CHOICES, 'КНБ через API')
r = client.post('/api/guild/777/fun/rps', json={'choice': ''})
check(r.status_code == 400 and r.get_json()['error'] == FP.ERR_RPS,
      'пустой выбор КНБ — 400')
r = client.post('/api/guild/777/fun/eightball', json={'question': ''})
check(r.status_code == 400 and r.get_json()['error'] == FP.ERR_QUESTION,
      'пустой вопрос — 400')
d = client.post('/api/guild/777/fun/eightball', json={'question': 'Да?'}).get_json()
check(d['success'] and d['answer'] in [a for a, _ in MG.EIGHT_BALL]
      and d['tone'] in ('yes', 'maybe', 'no'), 'шар через API')
d = client.post('/api/guild/777/fun/joke', json={}).get_json()
check(d['success'] and d['text'] in FC.JOKES and d['footer'] == 'Смех бесплатный!',
      'шутка через API из списка кога')
d = client.post('/api/guild/777/fun/quote', json={}).get_json()
check(d['success'] and d['text'] in FC.QUOTES, 'цитата через API из списка кога')
appmod.bot_instance = FB
try:
    d = client.get('/api/guild/777/fun/roles').get_json()
    check(d['success'] and [r['id'] for r in d['roles']] == ['201', '202', '203'],
          'роли через API без @everyone')
    r = client.post('/api/guild/777/fun/random-member', json={'role_id': '201'})
    d = r.get_json()
    check(r.status_code == 200 and d['member']['name'] == 'Олег'
          and d['candidates'] == 1, 'жребий через API с фильтром')
    r = client.post('/api/guild/777/fun/random-member', json={'role_id': '203'})
    check(r.status_code == 404
          and r.get_json()['error'] == 'Подходящих участников не найдено!',
          'пустой жребий через API')
    appmod.bot_instance = None
    r = client.get('/api/guild/777/fun/roles')
    check(r.status_code == 409 and r.get_json()['error'] == 'Бот не работает',
          'роли без бота — 409 через API')
    r = client.post('/api/guild/777/fun/random-member', json={})
    check(r.status_code == 409 and r.get_json()['error'] == 'Бот не работает',
          'жребий без бота — 409 через API')
finally:
    appmod.bot_instance = None
real_fetch = FP.fetch_json
try:
    FP.fetch_json = lambda url, timeout=10: {'url': 'u2', 'title': 'tt'}
    d = client.post('/api/guild/777/fun/gallery', json={'kind': 'meme'}).get_json()
    check(d['success'] and d['image'] == 'u2' and d['title'] == 'tt',
          'галерея через API с подменённым fetch')
    FP.fetch_json = lambda url, timeout=10: None
    r = client.post('/api/guild/777/fun/gallery', json={'kind': 'dog'})
    check(r.status_code == 502 and r.get_json()['error'] == FC.DOG_ERR,
          'сбой галереи — словами команды через API')
    r = client.post('/api/guild/777/fun/gallery', json={'kind': 'bird'})
    check(r.status_code == 400 and r.get_json()['error'] == FP.ERR_KIND,
          'чужой вид галереи — 400 через API')
finally:
    FP.fetch_json = real_fetch

print('== 10. Шаблон, коги, меню, регистрация ==')
tpl = open(os.path.join(ROOT, 'web/templates/fun.html'), encoding='utf-8').read()
check(not EMOJI_RE.search(tpl), 'в шаблоне нет эмодзи')
src = open(os.path.join(ROOT, 'web/routes/fun_panel.py'), encoding='utf-8').read()
check(not EMOJI_RE.search(src), 'в модуле панели нет эмодзи')
base_tpl = open(os.path.join(ROOT, 'web', 'templates', 'base.html'), encoding='utf-8').read()
check('data-theme="light"' in base_tpl, 'светлая тема учтена (общий shell)')
check('localhost' not in tpl and '127.0.0.1' not in tpl, 'без локальных адресов')
for fid in ('fnPick', 'fnCoinGo', 'fnCoinRes', 'fnDiceN', 'fnDiceGo', 'fnDiceRes',
            'fnRpsRes', 'fnBallQ', 'fnBallGo', 'fnBallRes', 'fnJokeGo',
            'fnQuoteGo', 'fnTextRes', 'fnRole', 'fnMemberGo', 'fnMemberRes',
            'fnMemberHint', 'fnMemeGo', 'fnCatGo', 'fnDogGo', 'fnGal',
            'fnGalImg', 'fnGalCap', 'fnGalMsg'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
for choice in ('камень', 'бумага', 'ножницы'):
    check(f'data-choice="{choice}"' in tpl, f'кнопка {choice} на месте')
for path in ("'/coinflip'", "'/dice'", "'/rps'", "'/eightball'", "'/joke'",
             "'/quote'", "'/roles'", "'/random-member'", "'/gallery'"):
    check(path in tpl, f'путь {path} в шаблоне')
check(hasattr(MG, 'MiniGames') and callable(MG.setup), 'ког minigames цел')
check(hasattr(FC, 'FunCog') and callable(FC.setup), 'ког fun_cog цел')
check(FP.MG is MG and FP.FC is FC, 'панель зовёт сами модули когов, не копии')
import services.panel_menu as PM
comm_pages = [pg['path'] for g in PM.MENU if g['key'] == 'community'
              for pg in g['pages']]
check('/fun' in comm_pages, 'пункт меню «Развлечения» в «Сообществе»')
check(PM.PAGE_COGS.get('/fun') == ('minigames', 'fun_cog'), 'коги привязаны')
ext = open(os.path.join(ROOT, 'web/routes_extra.py'), encoding='utf-8').read()
check(ext.count('fun_panel') >= 1, 'модуль зарегистрирован в routes_extra')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
