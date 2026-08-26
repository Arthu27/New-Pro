# -*- coding: utf-8 -*-
"""Публикация правил через webhook — Components V2 (2026-08-26).

Панель публикации — карточки-режимы: «Эмбеды» и «Webhook V2»
(кнопки «Опубликовать»). Превью — табы «Эмбеды / Webhook · V2»
с живым V2-макетом. У каждого правила до двух ссылок (u + u2), обе
уходят в одном сообщении: классика — «[открыть] · [ещё ссылка]»,
V2 — «[Подробнее] · [Ещё]». V2-сообщение собирает
services/v2_layouts.rules_layout и отправляет через вебхук
«Правила сервера» с аватаркой сервера; нет права вебхуков — тем же
макетом голосом бота; библиотека постарела — классический эмбед.
Демо (бот офлайн) честно говорит, что уйдёт при живом боте.

Запуск: python3 tests/test_rules_v2_publish.py
"""
import importlib
import json
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_rules_v2_')
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


print('== 1. Макет правил со вступлением ==')
from services import v2_layouts as L  # noqa: E402

vr = L.rules_layout('Правила сервера', ['Один', 'Два'], footer='ножка',
                    intro='Нарушение ведёт к наказанию')
check(vr.has_components_v2(), 'V2-раскладка собирается')
texts = [getattr(c, 'content', '') for c in vr.children[0].children
         if type(c).__name__ == 'TextDisplay']
check(any('Нарушение ведёт' in t for t in texts), 'вступление попало в макет')

print('== 2. Страница редактора: табы, карточки, вторая ссылка ==')
appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()
with client.session_transaction() as s:
    s.clear()
    s['logged_in'] = True
    s['username'] = 'owner'
    s['role'] = 'owner'

resp = client.get('/rules-editor')
check(resp.status_code == 200, 'страница открывается')
tpl = resp.get_data(as_text=True)
check('btnPublishRulesV2' in tpl and 'Webhook <span class="pub-tag new">V2</span>' in tpl,
      'карточка «Webhook V2» на месте')
check('Опубликовать красиво' not in tpl and 'Красиво' not in tpl,
      'никаких «красиво» в подписях')
check('> Опубликовать\n' in tpl or '> Опубликовать <' in tpl,
      'кнопки называются просто «Опубликовать»')
check("publishRules('v2')" in tpl, 'кнопка дёргает публикацию со style=v2')
check('btnPublishRules' in tpl and 'publishRules(\'classic\')' in tpl,
      'карточка «Эмбеды классика» на месте')
check('pvTabEmbed' in tpl and 'pvTabV2' in tpl and 'Webhook · V2' in tpl,
      'табы превью «Эмбеды / Webhook · V2»')
check('pvPaneEmbed' in tpl and 'pvPaneV2' in tpl and 'id="pv2"' in tpl,
      'две панели превью, V2-панель с живым макетом')
check('pv2HookName' in tpl and 'Правила сервера' in tpl,
      'в V2-превью видно имя вебхука «Правила сервера»')
check('Вебхук' in tpl and 'pv2ColorBar' in tpl,
      'бейдж «Вебхук» и цветная полоса в V2-превью')
check('renderPreviewV2' in tpl, 'живой V2-превью перерисовывается')
check('data-field="u2"' in tpl and 'Вторая ссылка' in tpl,
      'у правила есть инпут второй ссылки')
check('pub-channel' in tpl, 'панель публикации с выбором канала')

print('== 3. Вторая ссылка: нормализация и обе ветки публикации ==')
src = open(os.path.join(ROOT, 'web', 'routes', 'tasks_rules.py'),
           encoding='utf-8').read()
flat = src.replace(' ', '')
check("r.get('u2')orr.get('url2')orr.get('link2')" in flat,
      '_norm_rule понимает u2/url2/link2 (легаси-поля тоже)')
check("[ещё ссылка](" in src, 'классика: вторая ссылка в том же эмбеде')
check('[Подробнее](' in src and '[Ещё](' in src,
      'V2: обе ссылки одной строкой «[Подробнее] · [Ещё]»')
check("'u2'insafewhere" in flat or "('u2','втораяссылка')" in flat
      or "('u2', 'вторая ссылка')" in src,
      'валидация чистит и вторую ссылку')
check("forfin('u','u2','img','thumb')" in flat,
      '_normalize_rules_urls доклеивает https:// и второй ссылке')

print('== 4. Публикация: демо честно, исходник честный ==')
# демо: бот офлайн — успех с пояснением про вебхук «Правила сервера»
rules = [{'t': 'Уважение', 'u': '', 'u2': ''},
         {'t': 'Без спама', 'u': 'https://discord.com/x',
          'u2': 'discord.com/rules'}]
r = client.post('/api/guild/777/rules/publish',
                json={'channel_id': '1001', 'rules': rules, 'style': 'v2',
                      'title': 'Правила', 'intro': 'Вступление', 'color': '4f46e5'})
d = r.get_json()
check(r.status_code == 200 and d.get('success') and d.get('demo'),
      'демо-публикация V2 успешна (без бота)')
check('Правила сервера' in d.get('message', ''), 'в сообщении — голос вебхука «Правила сервера»')
check('Components V2' in d.get('message', ''), 'сообщение честно называет формат')

check("style')=='v2'" in flat, 'в роуте есть ветка style=v2')
check("create_webhook (name ='Правила сервера'" in src.replace('  ', ' ') or
      "create_webhook(name='Правила сервера'" in flat or
      "create_webhook (name ='Правила сервера'" in src,
      'вебхук «Правила сервера» создаётся, если его нет')
check('manage_webhooks' in src, 'нет права вебхуков — честный фолбек голосом бота')
check('нет права «Управлять вебхуками»' in src,
      'фолбек объясняет причину и как починить')
check('Опубликовать эмбедами' in tpl, 'кнопки различаются: классика — «Опубликовать эмбедами»')
check('avatar_url' in src and 'icon.url' in flat,
      'аватарка сообщения — иконка сервера')
check('rules_layout' in src and 'send_v2_or_embed' in src,
      'макет и отправка идут через v2_layouts (с эмбед-фолбеком)')
# правила с u2 сохранились автосохранением — вторая ссылка прижилась
saved = json.load(open(os.path.join(_TMP, 'data', 'rules_777.json'),
                       encoding='utf-8'))
check(len(saved) == 2, 'опубликованные правила автосохранены')
check(saved[1].get('u2') == 'https://discord.com/rules',
      'u2 без протокола сохранилась с https://')

# классическая публикация не сломалась и тоже знает u2
r2 = client.post('/api/guild/777/rules/publish',
                 json={'channel_id': '1001', 'rules': rules,
                       'title': 'Правила', 'intro': '', 'color': '4f46e5'})
d2 = r2.get_json()
check(d2.get('success') and d2.get('style') != 'v2',
      'классическая публикация работает как раньше')

print('== 5. Гейт доступа: кнопка «Согласен с правилами» ==')
from services import rules_gate as G  # noqa: E402

check(G.GATE_BUTTON_ID == 'aether_rules_gate', 'custom_id кнопки стабильный (переживает рестарт)')
gv = G.gate_layout()
check(gv.has_components_v2(), 'V2-макет гейта собирается')
btns = [c for c in gv.walk_children() if type(c).__name__ == 'Button']
check(len(btns) == 1 and btns[0].custom_id == G.GATE_BUTTON_ID,
      'в макете одна кнопка с тем же custom_id')
fb = G.RulesGateView()
fbbtn = [c for c in fb.children if type(c).__name__ == 'Button'][0]
check(fb.timeout is None and fbbtn.custom_id == G.GATE_BUTTON_ID,
      'классический фолбек — персистентная вью с той же кнопкой')

class _FakeBot:
    def __init__(self): self.views = []
    def add_view(self, v): self.views.append(v)
fb_bot = _FakeBot()
G.register(fb_bot); G.register(fb_bot)
check(len(fb_bot.views) == 1, 'register() дважды — вью одна (guard)')

import tempfile as _tf, shutil as _sh2  # noqa: E402
_tmp2 = _tf.mkdtemp(prefix='aether_gate_')
_oldcwd = os.getcwd(); os.chdir(_tmp2)
G.save_gate_config('777', '555', True)
cfg = G.load_gate_config('777')
check(cfg == {'role_id': '555', 'enabled': True}, 'конфиг гейта сохраняется и читается')
os.chdir(_oldcwd); _sh2.rmtree(_tmp2, ignore_errors=True)

check('rules-gate' in tpl and 'Согласен с правилами' in tpl,
      'в панели есть чекбокс гейта и подпись')
check('rules-gate-role' in tpl, 'выбор роли за согласие в панели')
check('v2p-btn' in tpl, 'мок-кнопка в V2-превью')
gsrc = open(os.path.join(ROOT, 'web', 'routes', 'tasks_rules.py'),
            encoding='utf-8').read()
check('send_gate_message' in gsrc and "get ('gate')" in gsrc.replace(' ', ' '),
      'публикация принимает gate и ставит сообщение с кнопкой')
check('rules_gate' in open(os.path.join(ROOT, 'main.py'), encoding='utf-8').read(),
      'кнопка регистрируется при старте бота (main.py)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
