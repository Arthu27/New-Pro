# -*- coding: utf-8 -*-
"""Медиа-доказательства: файл через бота → диск → просмотр в панели.

Проверяем: определение типа медиа, безопасные имена, локальное хранилище
(сохранение/чтение/удаление), потолок размера, страницу «Каналы и маршруты»
(view=mod+, edit=admin+), API маршрутов (4 системы) и отдачу файла
/proof-media/<id> прямо в панель.

Запуск: python3 tests/test_proof_media.py
"""
import asyncio
import io
import json
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_proofmedia_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')
os.environ['DEMO_MODE'] = '1'
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['PANEL_USER'] = 'owner'
os.environ['PANEL_PASSWORD'] = 'preview123'
os.environ['MAIN_GUILD_ID'] = '987654321098765432'

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


GID = '987654321098765432'

print('== помощники медиа ==')
from cogs.proof_cog import (  # noqa: E402
    _media_kind, _media_safe_name, proof_save_media, proof_media_abspath,
    proof_delete_media, proof_add, proof_update, proof_get,
    LOCAL_MEDIA_MAX, MEDIA_DIR)

check(_media_kind('proof.png') == 'image' and _media_kind('clip.MP4') == 'video',
      'тип по расширению: png=фото, MP4=видео')
check(_media_kind('file', 'image/jpeg') == 'image'
      and _media_kind('file', 'video/webm') == 'video',
      'тип по content-type работает')
check(_media_kind('notes.txt') is None and _media_kind('x.exe') is None,
      'неизвестные типы не считаются медиа')
name = _media_safe_name(GID, 7, '../../../etc/passwd.png')
check(name == f'{GID}_7.png' and '/' not in name,
      f'имя файла безопасно ({name}) — путь отрезан')

print('== локальное хранилище ==')
media = proof_save_media(GID, 1, 'clip.mp4', b'video-bytes-0123456789',
                         'video/mp4')
check(media and media['kind'] == 'video' and media['size'] == len(b'video-bytes-0123456789'),
      'видео сохранено локально (kind/size верные)')
check(media and os.path.isfile(media['file']), 'файл реально на диске')
big = proof_save_media(GID, 2, 'huge.mp4', b'x' * (LOCAL_MEDIA_MAX + 1))
check(big is None, 'файл сверх лимита не сохраняется')
bad = proof_save_media(GID, 3, 'doc.txt', b'hello')
check(bad is None, 'текстовый файл в медиа не пишется')

entry = proof_add(GID, 111, 'Нарушитель', 222, 'mod.anna', 'бан', 'читы')
proof_update(GID, entry['id'], media=media)
loaded = proof_get(GID, entry['id'])
check(proof_media_abspath(loaded) == os.path.abspath(media['file']),
      'abspath достаёт файл записи (внутри MEDIA_DIR)')
check(proof_delete_media(GID, loaded) is True
      and not os.path.exists(media['file']),
      'удаление демки чистит файл с диска')

print('== хранилище маршрутов ==')
from services import channel_routes as CHR  # noqa: E402

check(len(CHR.ROUTE_SPECS) >= 4, f'маршрутов в спецификации: {len(CHR.ROUTE_SPECS)}')
keys = [s['key'] for s in CHR.ROUTE_SPECS]
check('proof_channel' in keys and 'appeals_channel' in keys
      and 'welcome_channel' in keys and 'tagjail_channel' in keys,
      f'все 4 маршрута на месте {keys}')
check(CHR.get_route(GID, 'proof_channel') == 0, 'по умолчанию маршрут пуст (авто)')
check(CHR.set_route(GID, 'proof_channel', 456789), 'маршрут записан')
check(CHR.get_route(GID, 'proof_channel') == 456789, 'маршрут читается')
check(CHR.set_route(GID, 'proof_channel', 0) and CHR.get_route(GID, 'proof_channel') == 0,
      'маршрут очищается (0 = авто)')
check(CHR.set_route(GID, 'not_a_route', 1) is False, 'чужой ключ не пишется')

# бот: выборочный канал из маршрутов побеждает автосоздание
print('== бот читает маршрут ==')
from cogs.proof_cog import ProofCog  # noqa: E402


class _Ch:
    id = 456789


class _G:
    id = int(GID)

    def get_channel(self, cid):
        return _Ch() if cid == 456789 else None


CHR.set_route(GID, 'proof_channel', 456789)
got = asyncio.run(ProofCog._proof_channel(object.__new__(ProofCog), _G()))
check(getattr(got, 'id', None) == 456789,
      'proof-канал берётся из «Каналов и маршрутов», а не автосоздаётся')
CHR.set_route(GID, 'proof_channel', 0)

# ── панель ──────────────────────────────────────────────────────────────────
print('== панель: страница и API ==')
from web.app import app as flask_app  # noqa: E402

client = flask_app.test_client()


def login_as(role):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'proof-T'
        s['role'] = role


login_as('owner')
r = client.get('/channel-settings')
check(r.status_code == 200, f'/channel-settings открывается ({r.status_code})')
body = r.get_data(as_text=True)
check('Каналы и маршруты' in body and '/api/channel-routes' in body
      and '/api/channels' in body,
      'страница собирает маршруты и список каналов')
check('Просмотр: Мод+' in body and 'Изменение: Админ' in body,
      'категории доступа подписаны на странице')

r = client.get('/api/channel-routes')
d = r.get_json()
check(r.status_code == 200 and d.get('success') and len(d.get('routes') or []) >= 4,
      'API маршрутов отдаёт все системы')
rkeys = [x['key'] for x in d['routes']]
check(set(keys) <= set(rkeys), f'API содержит все ключи {rkeys}')

r = client.post('/api/channel-routes/proof_channel',
                data=json.dumps({'channel_id': '777111'}), content_type='application/json')
check(r.status_code == 200 and r.get_json().get('success'),
      'owner (admin+) меняет маршрут доказательств')
check(CHR.get_route(GID, 'proof_channel') == 777111,
      'запись через API попала в хранилище бота')

r = client.post('/api/channel-routes/tagjail_channel',
                data=json.dumps({'channel_id': '888222'}), content_type='application/json')
tj = json.load(open('data/tag_jail.json', encoding='utf-8')) \
    if os.path.exists('data/tag_jail.json') else {}
check(r.status_code == 200
      and (tj.get(GID) or {}).get('log_channel_id') == 888222,
      'маршрут tag jail пишется в конфиг кога')

r = client.post('/api/channel-routes/appeals_channel',
                data=json.dumps({'channel_id': '999333'}), content_type='application/json')
from db import GuildData  # noqa: E402
ap = GuildData('appeals').get(int(GID), 'state', {}) or {}
check(r.status_code == 200 and int(ap.get('log_channel_id') or 0) == 999333,
      'маршрут апелляций пишется в их state (то же хранилище, что читает бот)')

r = client.post('/api/channel-routes/nope',
                data=json.dumps({'channel_id': '1'}), content_type='application/json')
check(r.status_code == 404, 'чужой маршрут → 404')
r = client.post('/api/channel-routes/proof_channel',
                data=json.dumps({'channel_id': 'abc'}), content_type='application/json')
check(r.status_code == 400, 'мусорный ID → 400')
CHR.set_route(GID, 'proof_channel', 0)

print('== доступ по категориям ==')
login_as('mod')
r = client.get('/channel-settings')
check(r.status_code == 200, 'мод видит страницу маршрутов')
check('disabled' in r.get_data(as_text=True), 'моду селекты показаны выключенными')
r = client.post('/api/channel-routes/proof_channel',
                data=json.dumps({'channel_id': '1'}), content_type='application/json')
check(r.status_code in (401, 403), f'мод НЕ может менять маршруты ({r.status_code})')
r = client.get('/api/channel-routes')
check(r.status_code == 200, 'мод читает маршруты')

print('== медиа в панели ==')
media2 = proof_save_media(GID, 42, 'proof.png', b'\x89PNG\r\n\x1a\nfakeimg', 'image/png')
e2 = proof_add(GID, 555, 'Читер', 222, 'mod.anna', 'кик', 'рейд')
proof_update(GID, e2['id'], media=media2)

r = client.get('/api/proofs')
d = r.get_json()
items = (d or {}).get('items') or []
mine = [x for x in items if x.get('id') == e2['id']]
check(bool(mine) and mine[0].get('media_url') == f'/proof-media/{e2["id"]}',
      'API демок отдаёт media_url для просмотра в панели')
check(bool(mine) and mine[0].get('media', {}).get('kind') == 'image',
      'тип медиа доезжает до карточки')

r = client.get(f'/proof-media/{e2["id"]}')
check(r.status_code == 200 and r.get_data() == b'\x89PNG\r\n\x1a\nfakeimg',
      'файл отдаётся прямо в панель (байты совпадают)')
check('image' in (r.headers.get('Content-Type') or ''),
      f"content-type медиа верный ({r.headers.get('Content-Type')})")
r = client.get('/proof-media/999999')
check(r.status_code == 404, 'чужой номер медиа → 404')

login_as('owner')
r = client.delete(f'/api/proofs/{e2["id"]}')
check(r.status_code == 200 and r.get_json().get('success'),
      'админ удаляет демку через панель')
check(not os.path.exists(media2['file']),
      'файл демки стёрт с диска при удалении из панели')

print('== шаблоны ==')
tpl = open(os.path.join(ROOT, 'web', 'templates', 'proofs.html'), encoding='utf-8').read()
check('pf-modal-video' in tpl and '<video' in tpl and 'data-vfull' in tpl,
      'лайтбокс умеет видео')
check('data-mtype' in tpl and 'fa-film' in tpl, 'фильтр фото/видео в тулбаре')
check('silentGuard' in tpl, 'тихое обновление сохранено')
check('media_url' in tpl, 'карточка берёт локальное медиа')
tpl2 = open(os.path.join(ROOT, 'web', 'templates', 'channel_settings.html'),
            encoding='utf-8').read()
check('chsList' in tpl2 and 'chsSave' in tpl2 and 'CAN_EDIT' in tpl2,
      'страница маршрутов: список, сохранение, разграничение прав')
check('localhost' not in tpl2 and '127.0.0.1' not in tpl2,
      'без локальных ссылок в шаблоне')

print('== меню/роуты ==')
from services.panel_menu import panel_groups_for  # noqa: E402
paths = [p['path'] for g in panel_groups_for('owner') for p in g['pages']]
check('/channel-settings' in paths, 'пункт «Каналы» в меню')
check(len(paths) == 126, f'в меню 126 страниц ({len(paths)})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
