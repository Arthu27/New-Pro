# -*- coding: utf-8 -*-
"""Components V2 + вебхуки (заказ владельца 2026-08-26: «заучите V2»).

Discord Components V2 — новый формат сообщений блоками вместо эмбедов.
discord.py 2.6+ отдаёт его через LayoutView; библиотека сама ставит флаг
is_components_v2 и в Messageable.send, и в Webhook.send.

Правила игры в проекте:
- каждый макет строится дважды: V2-раскладка + классический эмбед-фолбек;
- send_v2_or_embed шлёт V2, при ошибке/недоступности — эмбед;
- гивки (старт и финал) уже уходят через V2;
- вебхук из панели умеет style='v2' — «правила от имени сервера».

Запуск: python3 tests/test_v2_layouts.py
"""
import asyncio
import importlib
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

_TMP = tempfile.mkdtemp(prefix='aether_v2_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'test123'
os.environ['MAIN_GUILD_ID'] = '777'
os.environ['DEMO_MODE'] = '1'

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


print('== 1. Библиотека и конструкторы ==')
import discord  # noqa: E402
from services import v2_layouts as L  # noqa: E402

check(hasattr(discord.ui, 'LayoutView') and hasattr(discord.ui, 'TextDisplay'),
      'discord.py отдаёт Components V2 (LayoutView/TextDisplay)')
check(L.v2_available() is True, 'v2_available() = True')

ends = datetime.now() + timedelta(hours=5)
v = L.giveaway_start_layout('Nitro', 2, ends, footer='Демо • ID 1')
check(v is not None and v.has_components_v2(), 'старт гивки — V2-раскладка')
box = v.children[0]
check(isinstance(box, discord.ui.Container), 'раскладка в контейнере с акцентом')
kids = [type(c).__name__ for c in box.children]
check('TextDisplay' in kids and 'Separator' in kids, f'блоки внутри: {sorted(set(kids))}')
check(any(f'<t:{int(ends.timestamp())}:R>' in getattr(c, 'content', '')
          for c in box.children), 'таймер Discord <t:...:R> в тексте')

e = L.giveaway_start_embed('Nitro', 2, ends, footer='ID 1')
check(isinstance(e, discord.Embed) and len(e.fields) >= 2, 'фолбек-эмбед старта собран')

print('== 2. Финал гивки и правила ==')
ve = L.giveaway_end_layout('Nitro', ['<@1>', '<@2>'], footer='Демо')
check(ve.has_components_v2(), 'финал гивки — V2')
ve0 = L.giveaway_end_layout('Nitro', [])
check(ve0.has_components_v2(), 'финал без участников — тоже V2 (честная заглушка)')
ee = L.giveaway_end_embed('Nitro', ['<@1>'])
check(ee.color.value == 0xF0CD7A, 'фолбек-эмбед финала золотой')

rules = [('Уважение', 'Без оскорблений и травли'), ('Без спама', 'Флуд запрещён'),
         ('Голосовые', 'Не шуметь')]
vr = L.rules_layout('Правила сервера', rules, footer='Модератор решает')
check(vr.has_components_v2(), 'правила — V2-раскладка')
n_texts = sum(1 for c in vr.children[0].children if type(c).__name__ == 'TextDisplay')
check(n_texts >= 5, f'правила: заголовок + 3 пункта + футер ({n_texts} текст-блоков)')
er = L.rules_embed('Правила сервера', rules)
check(len(er.fields) == 3, 'фолбек правил — эмбед с 3 полями')

print('== 3. send_v2_or_embed: V2, фолбек, ошибка → эмбед ==')


class FakeTarget:
    def __init__(self, fail_first=False):
        self.calls = []
        self.fail_first = fail_first

    async def send(self, **kw):
        self.calls.append(kw)
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError('клиент не поддержал V2')
        return 'sent'


async def _run():
    t = FakeTarget()
    msg = await L.send_v2_or_embed(t, view=L.giveaway_start_layout('N', 1, ends),
                                   embed=L.giveaway_start_embed('N', 1, ends))
    assert 'view' in t.calls[0] and 'embed' not in t.calls[0], t.calls
    check(msg == 'sent', 'V2-путь: отправлена только раскладка (без эмбеда)')

    t2 = FakeTarget()
    await L.send_v2_or_embed(t2, view=None, embed=e)
    check('embed' in t2.calls[0] and 'view' not in t2.calls[0],
          'нет V2 → уходит классический эмбед')

    L.V2_AVAILABLE = False
    t3 = FakeTarget()
    await L.send_v2_or_embed(t3, view=L.giveaway_start_layout('N', 1, ends), embed=e)
    check('embed' in t3.calls[0], 'библиотека «постарела» → фолбек-эмбед')
    L.V2_AVAILABLE = True

    t4 = FakeTarget(fail_first=True)
    await L.send_v2_or_embed(t4, view=L.giveaway_start_layout('N', 1, ends), embed=e)
    check(len(t4.calls) == 2 and 'embed' in t4.calls[1],
          'V2 отклонён клиентом → вторая попытка эмбедом')

asyncio.run(_run())

print('== 4. Гивки бота и вебхук панели ==')
gsrc = open(os.path.join(ROOT, 'cogs', 'giveaway.py'), encoding='utf-8').read()
check('giveaway_start_layout' in gsrc and 'send_v2_or_embed' in gsrc,
      'старт гивки в боте идёт через V2 с фолбеком')
check('giveaway_end_layout' in gsrc, 'финал гивки — тоже V2')
check('fallback_view=view' in gsrc, 'кнопка «Участвовать» живёт и в V2, и в фолбеке')

wsrc = open(os.path.join(ROOT, 'web', 'routes', 'guild_extra.py'), encoding='utf-8').read()
check("style=='v2'" in wsrc.replace(' ', ''),
      'вебхук панели умеет отправлять V2-сообщения (style=v2)')
check('rules_layout' in wsrc and 'rules_embed' in wsrc,
      '«правила от имени сервера» идут с эмбед-фолбеком')

tpl = open(os.path.join(ROOT, 'web', 'templates', 'webhooks.html'), encoding='utf-8').read()
check('Components V2' in tpl and 'v2-demo' in tpl,
      'на странице вебхуков есть живое превью V2-сообщений')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
