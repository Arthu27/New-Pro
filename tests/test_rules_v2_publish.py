# -*- coding: utf-8 -*-
"""«Опубликовать правила красиво» — Components V2 + вебхук (2026-08-26).

Кнопка «Красиво (V2)» в редакторе правил: панель собирает одно
V2-сообщение (services/v2_layouts.rules_layout) и отправляет его через
вебхук «Правила сервера» с аватаркой сервера — не голосом бота.
Нет права вебхуков — тем же макетом уходит сообщением бота; библиотека
постарела — классический эмбед. Демо (бот офлайн) честно говорит, что
уйдёт при живом боте.

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

print('== 2. Страница редактора ==')
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
check('btnPublishRulesV2' in tpl and 'Красиво (V2)' in tpl,
      'кнопка «Красиво (V2)» на месте')
check('Components V2' in tpl, 'подпись объясняет формат')
check("publishRules('v2')" in tpl, 'кнопка дёргает публикацию со style=v2')

print('== 3. Публикация: демо честно, исходник честный ==')
# демо: бот офлайн — успех с пояснением про вебхук «Правила сервера»
rules = [{'t': 'Уважение', 'u': ''}, {'t': 'Без спама', 'u': 'https://discord.com/x'}]
r = client.post('/api/guild/777/rules/publish',
                json={'channel_id': '1001', 'rules': rules, 'style': 'v2',
                      'title': 'Правила', 'intro': 'Вступление', 'color': '4f46e5'})
d = r.get_json()
check(r.status_code == 200 and d.get('success') and d.get('demo'),
      'демо-публикация V2 успешна (без бота)')
check('Правила сервера' in d.get('message', ''), 'в сообщении — голос вебхука «Правила сервера»')
check('Components V2' in d.get('message', ''), 'сообщение честно называет формат')

src = open(os.path.join(ROOT, 'web', 'routes', 'tasks_rules.py'), encoding='utf-8').read()
check("style')=='v2'" in src.replace(' ', ''), 'в роуте есть ветка style=v2')
check("create_webhook (name ='Правила сервера'" in src.replace('  ', ' ') or
      "create_webhook(name='Правила сервера'" in src.replace(' ', '') or
      "create_webhook (name ='Правила сервера'" in src,
      'вебхук «Правила сервера» создаётся, если его нет')
check('manage_webhooks' in src, 'нет права вебхуков — честный фолбек голосом бота')
check('avatar_url' in src and 'icon.url' in src.replace(' ', ''),
      'аватарка сообщения — иконка сервера')
check('rules_layout' in src and 'send_v2_or_embed' in src,
      'макет и отправка идут через v2_layouts (с эмбед-фолбеком)')
# правила сохранились автосохранением
saved = json.load(open(os.path.join(_TMP, 'data', 'rules_777.json'), encoding='utf-8'))
check(len(saved) == 2, 'опубликованные правила автосохранены')

# классическая публикация не сломалась
r2 = client.post('/api/guild/777/rules/publish',
                 json={'channel_id': '1001', 'rules': rules,
                       'title': 'Правила', 'intro': '', 'color': '4f46e5'})
d2 = r2.get_json()
check(d2.get('success') and not d2.get('style') == 'v2',
      'классическая публикация работает как раньше')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
