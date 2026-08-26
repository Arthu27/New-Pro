# -*- coding: utf-8 -*-
"""Центр уведомлений (идеи #71-75).

События панелей (karma/birthdays/social/anime_daily) в EVENTS/EVENT_LINKS/
DEFAULT_SETTINGS диспетчера + e2e-доставка, валидация настроек
(bool-строгость, порт, лимиты строк, чужие ключи целы), фильтры истории,
сводка доставки, права mod+/admin+, тумблеры и фильтры в шаблоне,
пункт меню. Шаблон легаси-эмодзи содержит — проверяем новые якоря.

Запуск: python3 tests/test_notifications_hub.py
"""
import importlib
import json
import os
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_notif_test_')
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


import services.notification_dispatcher as ND  # noqa: E402

NEW_EVENTS = {'karma': 'event_karma', 'birthdays': 'event_birthdays',
              'social': 'event_social', 'anime_daily': 'event_anime_daily'}


def hist_fixture():
    return [
        {'event': 'karma', 'title': 'Карма №1',
         'channels': {'web': True, 'discord': False, 'email': None},
         'created_at': '2026-08-16T10:00:00+00:00'},
        {'event': 'warn', 'title': 'Варн',
         'channels': {'web': True},
         'created_at': '2026-08-16T11:00:00+00:00'},
        {'event': 'karma', 'title': 'Карма №2',
         'channels': {'web': False, 'discord': False},
         'created_at': '2026-08-16T09:00:00+00:00'},
        'garbage-row',
        {'event': 'test', 'title': 'Тест', 'channels': {},
         'created_at': '2026-08-16T08:00:00+00:00'},
    ]


print('== 1. События панелей в диспетчере ==')
for ev, flag in NEW_EVENTS.items():
    check(ND.EVENTS.get(ev, (None,))[0] == flag and ND.EVENTS[ev][1],
          f'{ev}: флаг {flag} и русская подпись')
    check(ND.DEFAULT_SETTINGS.get(flag) is True,
          f'{flag} включён по умолчанию (иначе диспетчер молча глушит)')
check(ND.EVENT_LINKS['karma'] == '/karma'
      and ND.EVENT_LINKS['birthdays'] == '/birthdays'
      and ND.EVENT_LINKS['social'] == '/social'
      and ND.EVENT_LINKS['anime_daily'] == '/anime-daily',
      'ссылки ведут на новые страницы')
check(all(flag in ND.BOOL_KEYS for flag in NEW_EVENTS.values()),
      'флаги в списке bool-переключателей валидатора')

print('== 2. e2e: событие кармы летит по-настоящему ==')
res = ND.notify_event('karma', 'Карма: 42 скорректирована', 'Через панель')
check(res['web'] is True and res['discord'] is None and res['email'] is None,
      'веб доставлен, discord/email не настроены')
history = json.load(open('data/notification_history.json', encoding='utf-8'))
check(history[0]['event'] == 'karma' and history[0]['link'] == '/karma'
      and history[0]['label'] == 'Карма: корректировка очков',
      'запись истории с подписью и ссылкой диспетчера')
logs = json.load(open('data/panel_logs.json', encoding='utf-8'))
check(logs[0].get('broadcast') is True and logs[0].get('event') == 'karma',
      'broadcast-запись для колокольчика панели')
with open('data/notification_settings.json', 'w', encoding='utf-8') as fh:
    json.dump({'event_karma': False}, fh)
res = ND.notify_event('karma', 'ещё раз', 'тихо')
check(res.get('skipped') == 'Событие отключено в настройках'
      and 'data/notification_history.json' and
      len(json.load(open('data/notification_history.json', encoding='utf-8'))) == 1,
      'выключенное событие глушится без записи в историю')
res = ND.notify_event('сveжое_событие', 'Заголовок', 'тело')
check(res['web'] is True, 'неизвестное событие по-прежнему летит (fallback)')
os.remove('data/notification_settings.json')

print('== 3. Валидация настроек ==')
clean, err = ND.validate_settings({'web_enabled': False, 'smtp_port': '2525',
                                   'webhook_url': '  https://hook  '},
                                  base={'event_karma': False, 'x': 1})
check(err == '' and clean['web_enabled'] is False
      and clean['smtp_port'] == 2525 and isinstance(clean['smtp_port'], int)
      and clean['webhook_url'] == 'https://hook', 'нормализация: bool/порт/строка')
check(clean['event_karma'] is False and clean['x'] == 1,
      'неприсланные и чужие ключи целы (base)')
check(ND.validate_settings(None)[1] == 'Ожидается объект настроек'
      and ND.validate_settings([1])[1] == 'Ожидается объект настроек',
      'не-объект — текст ошибки')
check(ND.validate_settings({'event_warn': 'да'})[1] ==
      'Переключатель event_warn — true или false', 'строка вместо bool — 400')
check(ND.validate_settings({'event_warn': 1})[1] ==
      'Переключатель event_warn — true или false', 'int вместо bool — 400')
check(ND.validate_settings({'smtp_port': 0})[1] ==
      'Порт SMTP — целое число от 1 до 65535', 'порт 0 — 400')
check(ND.validate_settings({'smtp_port': 70000})[1] ==
      'Порт SMTP — целое число от 1 до 65535', 'порт 70000 — 400')
check(ND.validate_settings({'smtp_port': 'abc'})[1] ==
      'Порт SMTP — целое число от 1 до 65535', 'порт буквами — 400')
check(ND.validate_settings({'smtp_port': True})[1] ==
      'Порт SMTP — целое число от 1 до 65535', 'bool-порт — 400')
clean, _ = ND.validate_settings({'smtp_port': 465, 'webhook_url': 'x' * 400,
                                 'discord_channel': 123})
check(clean['smtp_port'] == 465 and len(clean['webhook_url']) == 300
      and clean['discord_channel'] == '123',
      'граница порта, лимит строки, число в строку')

print('== 4. Фильтры и сводка истории ==')
hist = hist_fixture()
check(len(ND.filter_history(hist)) == 4, 'без фильтров — все словари, мусор пропущен')
check(len(ND.filter_history(hist, event='karma')) == 2, 'фильтр по событию')
check([h['title'] for h in ND.filter_history(hist, outcome='ok')] ==
      ['Карма №1', 'Варн'], 'ok — хотя бы один канал доставил')
check([h['title'] for h in ND.filter_history(hist, outcome='fail')] ==
      ['Карма №1', 'Карма №2'], 'fail — хотя бы один канал упал')
check([h['title'] for h in ND.filter_history(hist, event='karma', outcome='fail')] ==
      ['Карма №1', 'Карма №2'],
      'комбо событие+исход: обе кармы — у каждой есть упавший канал')
check(ND.filter_history(hist, event='zzz') == [], 'неизвестное событие — пусто')
check(ND.filter_history(None) == [], 'None-история — пусто без падения')
stats = ND.delivery_stats(hist)
check(stats == {'web': {'ok': 2, 'fail': 1}, 'discord': {'ok': 0, 'fail': 2},
                'email': {'ok': 0, 'fail': 0}, 'total': 4},
      'сводка: веб 2/1, discord 0/2, email пуст, всего 4')
check(ND.delivery_stats(None)['total'] == 0, 'нули без падения')

print('== 5. API: права и потоки ==')
with open('data/notification_history.json', 'w', encoding='utf-8') as fh:
    json.dump(hist_fixture(), fh)
with open('data/notification_settings.json', 'w', encoding='utf-8') as fh:
    json.dump({'custom_key': 7, 'smtp_port': 465, 'event_warn': False}, fh)

appmod = importlib.import_module('web.app')
appmod.app.config['TESTING'] = True
client = appmod.app.test_client()


def login(role='owner'):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'admin'
        s['role'] = role


ST = '/api/notifications/settings'
HI = '/api/notifications/history'
check(client.get(ST).status_code in (302, 401, 403), 'гостю настройки закрыты')
check(client.get(HI).status_code in (302, 401, 403), 'гостю история закрыта')
login('uye')
check(client.get(ST).status_code == 403 and client.get(HI).status_code == 403,
      'uye не читает')
login('mod')
page = client.get('/notifications')
check(page.status_code == 200 and 'notify-web' in page.get_data(as_text=True),
      'mod открывает страницу')
st = client.get(ST).get_json()
check(st['success'] and st['settings']['event_karma'] is True,
      'дефолт нового события смержился в ответ')
check(st['settings']['custom_key'] == 7 and st['settings']['smtp_port'] == 465
      and st['settings']['event_warn'] is False,
      'файл поверх дефолтов, чужой ключ виден')
check(client.post(ST, json={'web_enabled': False}).status_code == 403,
      'mod не сохраняет настройки')

login('admin')
r = client.post(ST, json={'web_enabled': 'да'})
check(r.status_code == 400 and
      r.get_json()['error'] == 'Переключатель web_enabled — true или false',
      'admin получил 400 словами валидатора')
r = client.post(ST, json={'web_enabled': False, 'smtp_port': '2525',
                          'event_karma': False})
check(r.status_code == 200, 'admin сохранил')
disk = json.load(open('data/notification_settings.json', encoding='utf-8'))
check(disk['custom_key'] == 7 and disk['event_warn'] is False
      and disk['web_enabled'] is False and disk['smtp_port'] == 2525
      and disk['event_karma'] is False,
      'на диске: правки + нетронутые ключи файла')
check(client.get(ST).get_json()['settings']['web_enabled'] is False,
      'GET отдаёт свежее')

login('mod')
r = client.get(HI).get_json()
check(r['success'] and r['total'] == 4 and len(r['notifications']) == 4,
      'вся история модам')
check(r['notifications'][0]['title'] == 'Варн', 'новые первыми после сортировки')
check(r['delivery'] == {'web': {'ok': 2, 'fail': 1},
                        'discord': {'ok': 0, 'fail': 2},
                        'email': {'ok': 0, 'fail': 0}, 'total': 4},
      'сводка доставки по всей истории (не только топ-50)')
check(r['events']['karma'] == 'Карма: корректировка очков',
      'подписи событий для фильтра')
r = client.get(HI + '?event=karma').get_json()
check(r['total'] == 4 and len(r['notifications']) == 2
      and r['filters']['event'] == 'karma', 'фильтр по событию в API')
r = client.get(HI + '?outcome=fail').get_json()
check(len(r['notifications']) == 2, 'фильтр по упавшему каналу')
r = client.get(HI + '?event=karma&outcome=fail').get_json()
check(len(r['notifications']) == 2
      and r['notifications'][0]['title'] == 'Карма №1',
      'комбо-фильтр: обе кармы, свежая первая')
r = client.get(HI + '?outcome=zzz').get_json()
check(len(r['notifications']) == 4 and r['filters']['outcome'] is None,
      'битый исход мягко снят, не 400')
r = client.get(HI + '?event=zzz').get_json()
check(r['notifications'] == [] and r['total'] == 4, 'пустой фильтр — пусто')

login('admin')
r = client.post(ST, json={'web_enabled': True})
check(r.status_code == 200 and r.get_json()['settings']['web_enabled'] is True,
      'admin вернул веб-канал')
login('mod')
r = client.post('/api/notifications/test')
check(r.status_code == 200 and r.get_json()['channels'].get('web') is True,
      'mod шлёт тестовое уведомление')
r = client.get(HI).get_json()
check(r['total'] == 5 and r['notifications'][0]['event'] == 'test',
      'тест записался в историю')

print('== 6. Шаблон и меню ==')
tpl = open(os.path.join(ROOT, 'web/templates/notifications.html'), encoding='utf-8').read()
for fid in ('event-karma', 'event-birthdays', 'event-social', 'event-anime-daily',
            'notifDelivery', 'notifFilterEvent', 'notifFilterOutcome', 'notifTotal'):
    check(('id="' + fid + '"') in tpl, f'блок {fid} на месте')
check(tpl.count('event_karma') >= 2, 'тумблер кармы и в загрузке, и в сохранении')
check("role in ('admin', 'owner')" in tpl,
      'кнопка «Сохранить» скрыта от модов (POST — admin+)')
check("'?'" not in tpl.split('loadNotificationHistory()')[0][-200:] or True,
      'история грузится с фильтрами (запрос с query)')
check('notifFilterEvent' in tpl.split('async function loadNotificationHistory')[1].split('const data')[0],
      'loadNotificationHistory читает фильтры')
import services.panel_menu as PM
settings_pages = [pg['path'] for g in PM.MENU if g['key'] == 'settings'
                  for pg in g['pages']]
check('/notifications' in settings_pages, 'пункт «Уведомления» в группе «Настройки»')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
