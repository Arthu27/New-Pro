# -*- coding: utf-8 -*-
"""Развлечения (идеи #186-190): игровая комната /fun в браузере.

Логика 1:1 cogs/minigames.py и cogs/fun_cog.py — панель зовёт сами хелперы
когов: монетка с нормализацией прогноза (orel/орел/орёл → «Орёл», иначе
«Неверно!»), кубики с клампом 1..5 и суммой только при n>1, КНБ с таблицей
побед кога, шар с теми же двенадцатью ответами и тонами, шутки и цитаты из
тех же десяти/двенадцати строк. Ничего не переизобретено.

«Угадай число» живёт в памяти бота (active_guesses кога): панель честно не
делает вид, что владеет этим состоянием, — игра остаётся в Discord через
/guess-start и /guess, о чём страница прямо говорит.

Жребий (random-member) и список ролей работают на живом кэше гильдии
(bot_instance): корутин нет, loop не нужен; без бота — честный 409 «Бот не
работает», без заглушек. Фильтр по роли — то же выражение команды, пустой
список кандидатов — её же словами: «Подходящих участников не найдено!».

Галерея (мем/кот/собака) ходит в те же внешние API теми же URL через
синхронный fetch_json (aiohttp в Flask-потоке не живёт, таймаут тот же —
10 секунд); при недоступности сервиса — ровно тексты ошибок команд:
«Не удалось загрузить мем, попробуй ещё!» и т.д.

Игры ничего не хранят и не меняют, поэтому всё — mod+.
"""
import json
import urllib.request

from logger import get_logger

from cogs import minigames as MG
from cogs import fun_cog as FC
from web.routes._common import (
    render_template, session, request, jsonify,
)

_log = get_logger("fun_panel")

ERR_BOT = 'Бот не работает'
ERR_GUILD = 'Сервер не найден'
ERR_ROLE = 'Роль не найдена'
ERR_COUNT = 'Количество должно быть числом'
ERR_RPS = 'Выбери камень, бумагу или ножницы'
ERR_QUESTION = 'Вопрос пустой'
ERR_KIND = 'Неизвестный вид галереи'
ERR_CANDIDATES = 'Подходящих участников не найдено!'  # слова /random-member
JOKE_FOOTER = 'Смех бесплатный!'                      # футер !joke

_GALLERY = {
    'meme': (FC.MEME_URL, FC.parse_meme, FC.MEME_ERR),
    'cat': (FC.CAT_URL, FC.parse_cat, FC.CAT_ERR),
    'dog': (FC.DOG_URL, FC.parse_dog, FC.DOG_ERR),
}


def fetch_json(url, timeout=10):
    """Синхронный аналог FunCog._fetch_json для Flask-потока: dict или None."""
    try:
        req = urllib.request.Request(
            url, headers={'User-Agent': 'Aether-Panel/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode('utf-8'))
    except Exception as _ex:
        _log.debug("fetch_json(%s): подавлено: %s", url, _ex)
        return None


def coinflip_flow(data, chooser=None):
    """Подброс монетки 1:1 /coinflip; статус — словами эмбеда без эмодзи."""
    pick = (data or {}).get('pick')
    if pick is not None:
        pick = str(pick).strip() or None
    game = MG.flip_coin(pick, chooser=chooser)
    payload = {'result': game['result'], 'guessed': game['guessed']}
    if game['guessed']:
        payload['pick'] = game['pick']
        payload['correct'] = game['correct']
        payload['status'] = 'Верно!' if game['correct'] else 'Неверно!'
    return True, '', 200, payload


def dice_flow(data, randint=None):
    """Бросок 1:1 /dice: кламп 1..5 внутри хелпера, сумма при n>1."""
    raw = (data or {}).get('count', 1)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return False, ERR_COUNT, 400, None
    return True, '', 200, MG.roll_dice(n, randint=randint)


def rps_flow(data, chooser=None):
    """Партия 1:1 /rps; выбор вне списка Discord choices отклоняем сами."""
    choice = str((data or {}).get('choice') or '').strip()
    if choice not in MG.RPS_CHOICES:
        return False, ERR_RPS, 400, None
    return True, '', 200, MG.play_rps(choice, chooser=chooser)


def eightball_flow(data, chooser=None):
    """Ответ шара 1:1 /8ball; вопрос обязателен, как параметр команды."""
    q = str((data or {}).get('question') or '').strip()
    if not q:
        return False, ERR_QUESTION, 400, None
    return True, '', 200, MG.ask_8ball(q, chooser=chooser)


def joke_flow(chooser=None):
    """Шутка из того же списка !joke; футер — тоже его."""
    return True, '', 200, {'text': FC.random_joke(chooser=chooser),
                           'footer': JOKE_FOOTER}


def quote_flow(chooser=None):
    """Цитата из того же списка !quote."""
    return True, '', 200, {'text': FC.random_quote(chooser=chooser)}


def roles_flow(bot_lookup, gid):
    """Роли сервера для фильтра жребия; @everyone (id == id гильдии) не даём."""
    bot = bot_lookup()
    if bot is None:
        return False, ERR_BOT, 409, None
    guild = bot.get_guild(int(gid))
    if guild is None:
        return False, ERR_GUILD, 404, None
    roles = [{'id': str(r.id), 'name': r.name}
             for r in guild.roles if r.id != guild.id]
    return True, '', 200, {'roles': roles}


def random_member_flow(bot_lookup, gid, role_id=None, chooser=None):
    """Жребий 1:1 /random-member на живом кэше гильдии."""
    bot = bot_lookup()
    if bot is None:
        return False, ERR_BOT, 409, None
    guild = bot.get_guild(int(gid))
    if guild is None:
        return False, ERR_GUILD, 404, None
    role = None
    if role_id not in (None, '', 0, '0'):
        try:
            rid = int(role_id)
        except (TypeError, ValueError):
            return False, ERR_ROLE, 400, None
        role = next((r for r in guild.roles if r.id == rid), None)
        if role is None:
            return False, ERR_ROLE, 404, None
    candidates, chosen = MG.pick_random_member(guild, role, chooser=chooser)
    if chosen is None:
        return False, ERR_CANDIDATES, 404, None
    return True, '', 200, {
        'member': {'name': chosen.display_name, 'id': str(chosen.id)},
        'candidates': len(candidates),
        'role': {'id': str(role.id), 'name': role.name} if role else None,
    }


def gallery_flow(kind, fetch=None):
    """Мем/кот/собака через те же URL и разбор, что у !meme/!cat/!dog."""
    key = str(kind or '').strip()
    spec = _GALLERY.get(key)
    if spec is None:
        return False, ERR_KIND, 400, None
    url, parser, err_text = spec
    item = parser((fetch or fetch_json)(url))
    if item is None:
        return False, err_text, 502, None
    return True, '', 200, {'kind': key, **item}


def register(ctx):
    app = ctx.app
    login_required = ctx.login_required
    role_required = ctx.role_required
    active_guild_id = ctx.active_guild_id

    def _bot():
        import web.app as appmod
        return appmod.bot_instance

    def _json():
        return request.get_json(silent=True) or {}

    def _reply(result):
        ok, err, code, payload = result
        if not ok:
            return jsonify({'success': False, 'error': err}), code
        return jsonify({'success': True, **payload})

    @app.route('/fun')
    @login_required
    @role_required('mod')
    def fun_page():
        return render_template('fun.html', role=session.get('role'),
                               username=session.get('username'),
                               guild_id=active_guild_id())

    @app.route('/api/guild/<gid>/fun/coinflip', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_fun_coinflip(gid):
        return _reply(coinflip_flow(_json()))

    @app.route('/api/guild/<gid>/fun/dice', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_fun_dice(gid):
        return _reply(dice_flow(_json()))

    @app.route('/api/guild/<gid>/fun/rps', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_fun_rps(gid):
        return _reply(rps_flow(_json()))

    @app.route('/api/guild/<gid>/fun/eightball', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_fun_eightball(gid):
        return _reply(eightball_flow(_json()))

    @app.route('/api/guild/<gid>/fun/joke', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_fun_joke(gid):
        return _reply(joke_flow())

    @app.route('/api/guild/<gid>/fun/quote', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_fun_quote(gid):
        return _reply(quote_flow())

    @app.route('/api/guild/<gid>/fun/roles')
    @login_required
    @role_required('mod')
    def api_fun_roles(gid):
        return _reply(roles_flow(_bot, gid))

    @app.route('/api/guild/<gid>/fun/random-member', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_fun_random_member(gid):
        return _reply(random_member_flow(_bot, gid, _json().get('role_id')))

    @app.route('/api/guild/<gid>/fun/gallery', methods=['POST'])
    @login_required
    @role_required('mod')
    def api_fun_gallery(gid):
        return _reply(gallery_flow(_json().get('kind'), fetch=fetch_json))
