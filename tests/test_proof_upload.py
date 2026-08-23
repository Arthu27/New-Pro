# -*- coding: utf-8 -*-
"""Прямая загрузка демок из панели + белый список «без демки».

Проверяем:
- cogs.proof_cog белый список: add/remove/дедуп/лимит, is_whitelisted
  (сам модератор или через роль);
- require_proof: белый список освобождает от обязательной демки (раньше —
  только картинка/видео/ссылка), логика отказа для обычных не сломана;
- POST /api/proofs/upload: прямая загрузка файла (фото/видео) БЕЗ ссылки —
  запись создаётся, файл сохраняется локально и отдаётся через /proof-media;
  не-медиа отклоняются без мусорных записей;
- API белого списка: чтение mod+, запись admin+, валидация kind/id;
- шаблон /proofs: форма загрузки (accept=image/*,video/*), блок белого
  списка, кнопки с type=, без эмодзи.

Запуск: python3 tests/test_proof_upload.py
"""
import asyncio
import io
import json
import os
import re
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='aether_proof_upload_')
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


# ═══ 1. Белый список «без демки» (чистые функции) ════════════════════════
print('== белый список: CRUD ==')
from cogs.proof_cog import (proof_whitelist, proof_whitelist_add,  # noqa: E402
                            proof_whitelist_remove, proof_is_whitelisted,
                            require_proof, is_media_attachment)

G1 = 555000111222333444
wl = proof_whitelist(G1)
check(wl == {'users': [], 'roles': []}, 'изначально белый список пуст')

wl = proof_whitelist_add(G1, 'user', 111222333444555666)
wl = proof_whitelist_add(G1, 'user', 111222333444555666)  # дубль
check(wl['users'] == [111222333444555666], 'участник добавлен, дубль схлопнут')
wl = proof_whitelist_add(G1, 'role', 999888777666555444)
check(wl['roles'] == [999888777666555444], 'роль добавлена')

check(proof_is_whitelisted(G1, user_id=111222333444555666),
      'модератор в списке → освобождён')
check(proof_is_whitelisted(G1, user_id=1, role_ids=[2, 999888777666555444]),
      'роль модератора в списке → освобождён')
check(not proof_is_whitelisted(G1, user_id=777, role_ids=[888]),
      'чужой модератор → демку просят как раньше')
check(not proof_is_whitelisted(G1), 'без ID вообще — не освобождён')

wl = proof_whitelist_remove(G1, 'user', 111222333444555666)
check(wl['users'] == [] and not proof_is_whitelisted(G1, user_id=111222333444555666),
      'участник убран — освобождение пропало')
wl = proof_whitelist_remove(G1, 'role', 999888777666555444)
check(wl == {'users': [], 'roles': []}, 'роль убрана — список снова пуст')

# ═══ 2. require_proof: белый список снимает обязаловку ═══════════════════
print('== require_proof: освобождение ==')


class _Followup:
    def __init__(self):
        self.sent = []

    async def send(self, *a, **k):
        self.sent.append(k)


class _Response:
    def __init__(self):
        self.msgs = []

    async def send_message(self, *a, **k):
        self.msgs.append(k)


class _Role:
    def __init__(self, rid):
        self.id = rid


class _Member:
    def __init__(self, mid, roles=()):
        self.id = mid
        self.roles = [_Role(r) for r in roles]


class _Guild:
    def __init__(self, gid):
        self.id = gid


class _Inter:
    def __init__(self, gid, member=None):
        self.followup = _Followup()
        self.response = _Response()
        self.guild = _Guild(gid)
        self.user = member


loop = asyncio.new_event_loop()

# доверенный модератор (по ID) — демка не требуется
proof_whitelist_add(G1, 'user', 100000000000000001)
i = _Inter(G1, _Member(100000000000000001))
ok = loop.run_until_complete(require_proof(i, attachment=None, action_ru='бан'))
check(ok is True and not i.followup.sent and not i.response.msgs,
      'модератор из белого списка: наказание без демки разрешено, отказа нет')

# доверенная роль — тоже освобождает
proof_whitelist_add(G1, 'role', 100000000000000002)
i = _Inter(G1, _Member(555, roles=[100000000000000002]))
ok = loop.run_until_complete(require_proof(i, attachment=None, action_ru='мут'))
check(ok is True, 'модератор с белой ролью: наказание без демки разрешено')

# обычный модератор без файла — как раньше: отказ
i = _Inter(G1, _Member(333000333000333000))
ok = loop.run_until_complete(require_proof(i, attachment=None, action_ru='бан'))
check(ok is False and (i.followup.sent or i.response.msgs),
      'не в списке и без демки: отказ «требуется доказательство» (как раньше)')


class _Att:
    def __init__(self, ct):
        self.content_type = ct
        self.filename = 'shot.png'


i = _Inter(G1, _Member(333000333000333000))
ok = loop.run_until_complete(
    require_proof(i, attachment=_Att('image/png'), action_ru='бан'))
check(ok is True and is_media_attachment(_Att('image/png')),
      'картинка во вложении — демка принята (старая логика цела)')

# ═══ 3. Панельный API: прямая загрузка файла ═════════════════════════════
print('== API: /api/proofs/upload ==')
from web.app import app as flask_app  # noqa: E402

client = flask_app.test_client()


def login_as(role):
    with client.session_transaction() as s:
        s.clear()
        s['logged_in'] = True
        s['username'] = 'proof-T'
        s['role'] = role


login_as('mod')
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64
r = client.post('/api/proofs/upload', data={
    'file': (io.BytesIO(PNG), 'screen.png', 'image/png'),
    'user_id': '123456789012345678',
    'user_name': 'Тест Нарушитель',
    'action': 'варн',
    'reason': 'токсик в чате',
}, content_type='multipart/form-data')
d = r.get_json()
check(r.status_code == 200 and d.get('success') is True and isinstance(d.get('id'), int),
      f'загрузка png: запись создана (#{d.get("id")})')
check(d.get('media_url', '').startswith('/proof-media/'),
      'загрузка png: отдан локальный media_url')
pid = d['id']

r = client.get('/api/proofs')
d = r.get_json()
item = [x for x in d.get('items', []) if x.get('id') == pid]
check(r.status_code == 200 and item and item[0].get('media', {}).get('kind') == 'image',
      'в ленте демка есть, тип — фото')
check(item and item[0].get('user_id') == '123456789012345678'
      and item[0].get('reason') == 'токсик в чате'
      and item[0].get('action') == 'варн',
      'в ленте сохранены участник/причина/наказание')

r = client.get(f'/proof-media/{pid}')
check(r.status_code == 200 and r.get_data().startswith(b'\x89PNG'),
      'файл смотрится прямо из панели (/proof-media отдаёт байты)')

# не-медиа: отказ без мусорной записи
total_before = len(client.get('/api/proofs').get_json().get('items', []))
r = client.post('/api/proofs/upload', data={
    'file': (io.BytesIO(b'echo hello'), 'virus.exe', 'application/octet-stream'),
    'user_id': '123456789012345678',
    'action': 'варн',
}, content_type='multipart/form-data')
total_after = len(client.get('/api/proofs').get_json().get('items', []))
check(r.status_code == 400 and total_after == total_before,
      'exe-файл: отклонён, пустых записей не осталось')

r = client.post('/api/proofs/upload', data={
    'file': (io.BytesIO(PNG), 'screen.png', 'image/png'),
    'user_id': 'не-цифры',
    'action': 'варн',
}, content_type='multipart/form-data')
check(r.status_code == 400, 'кривой ID участника: 400')

r = client.post('/api/proofs/upload', data={
    'user_id': '123456789012345678',
    'action': 'варн',
}, content_type='multipart/form-data')
check(r.status_code == 400, 'без файла: 400 (просят выбрать)')

# видео тоже можно
r = client.post('/api/proofs/upload', data={
    'file': (io.BytesIO(b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 32), 'clip.mp4', 'video/mp4'),
    'user_id': '123456789012345678',
    'action': 'бан',
    'reason': 'рейд',
}, content_type='multipart/form-data')
d2 = r.get_json()
check(r.status_code == 200 and d2.get('success') is True,
      'загрузка mp4-видео: создано')
r = client.get('/api/proofs')
item2 = [x for x in r.get_json().get('items', []) if x.get('id') == d2.get('id')]
check(item2 and item2[0].get('media', {}).get('kind') == 'video',
      'в ленте видео-демка с типом «видео»')

# ═══ 4. API белого списка: права и валидация ═════════════════════════════
print('== API: /api/proof-whitelist ==')
login_as('mod')
r = client.get('/api/proof-whitelist')
check(r.status_code == 200 and r.get_json().get('success') is True,
      'чтение белого списка — mod+')
r = client.post('/api/proof-whitelist', json={'kind': 'user', 'id': '123456789012345678'})
check(r.status_code == 403, f'запись в белый список модератором — 403 ({r.status_code})')

login_as('owner')
r = client.post('/api/proof-whitelist', json={'kind': 'user', 'id': '777000111222333444'})
d = r.get_json()
check(r.status_code == 200 and '777000111222333444' in d.get('users', []),
      'владелец добавил участника')
r = client.post('/api/proof-whitelist', json={'kind': 'user', 'id': '777000111222333444'})
d = r.get_json()
check(len([u for u in d.get('users', []) if u == '777000111222333444']) == 1,
      'дубль через API схлопнут')
r = client.post('/api/proof-whitelist', json={'kind': 'robot', 'id': '1'})
check(r.status_code == 400, 'неверный kind — 400')
r = client.post('/api/proof-whitelist', json={'kind': 'user', 'id': 'abc'})
check(r.status_code == 400, 'неверный id — 400')
r = client.open('/api/proof-whitelist', method='DELETE',
                json={'kind': 'user', 'id': '777000111222333444'})
d = r.get_json()
check(r.status_code == 200 and '777000111222333444' not in d.get('users', []),
      'удаление из белого списка работает')

# ═══ 5. Шаблон: форма загрузки + чистота ═════════════════════════════════
print('== шаблон /proofs ==')
html = open(os.path.join(ROOT, 'web', 'templates', 'proofs.html'),
            encoding='utf-8').read()
check('id="pf-add-form"' in html and 'accept="image/*,video/*"' in html,
      'форма прямой загрузки с accept фото/видео')
check('id="pf-wl-panel"' in html and 'Белый список' in html
      and 'data-wldel' in html,
      'блок белого списка с добавлением/удалением')
check('/api/proofs/upload' in html and '/api/proof-whitelist' in html,
      'JS страницы ходит в новые API')
check(not re.search(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u23E9-\u23FF]', html),
      'без эмодзи (аудит)')
bad_btn = [b for b in re.findall(r'<button\b[^>]*>', html) if 'type=' not in b]
check(not bad_btn, f'все кнопки с type= ({len(bad_btn)} без)')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
