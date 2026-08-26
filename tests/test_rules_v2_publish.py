# -*- coding: utf-8 -*-
"""«Опубликовать правила красиво» — Components V2 + вебхук (2026-08-26).

Панель публикации — карточки-режимы: «Эмбеды классика» и «Красиво V2»
(кнопка «Опубликовать красиво»). Превью — табы «Эмбеды / Красиво · V2»
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
check('btnPublishRulesV2' in tpl and 'Опубликовать красиво' in tpl,
      'карточка «Красиво V2» с кнопкой «Опубликовать красиво»')
check("publishRules('v2')" in tpl, 'кнопка дёргает публикацию со style=v2')
check('btnPublishRules' in tpl and 'publishRules(\'classic\')' in tpl,
      'карточка «Эмбеды классика» на месте')
check('pvTabEmbed' in tpl and 'pvTabV2' in tpl,
      'табы превью «Эмбеды / Красиво · V2»')
check('pvPaneEmbed' in tpl and 'pvPaneV2' in tpl and 'id="pv2"' in tpl,
      'две панели превью, V2-панель с живым макетом')
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

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
