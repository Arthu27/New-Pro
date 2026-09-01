# -*- coding: utf-8 -*-
"""Про-аналитика: экспорт отчёта — РЕАЛЬНЫЕ данные, не заглушка.

Регресс (2026-09-01): /api/analytics/export отдавал захардкоженные фейковые
строки «01.01.2026,Вопрос,Закрыт,2.5» в любом режиме — владелец скачивал
выдуманный CSV. Теперь эндпоинт читает те же data/ai_tickets_*.json, что и
страница про-аналитики, и фильтрует по периоду/категории/модератору.

Запуск: python3 tests/test_adv_analytics_export.py
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_TMP = tempfile.mkdtemp(prefix='hakumo_adv_export_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ.pop('DEMO_MODE', None)
os.environ.setdefault('PANEL_USER', 'owner')
os.environ.setdefault('PANEL_PASSWORD', 'test123')

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


# ── 1. Засеваем реальный файл тикетов ──────────────────────────────────
now = datetime.now(timezone.utc)
tickets = {
    'T-1': {'category': 'Жалоба', 'status': 'closed', 'closed_by': 'Анна',
            'created_at': (now - timedelta(days=2, hours=6)).isoformat(),
            'closed_at': (now - timedelta(days=2, hours=3)).isoformat()},
    'T-2': {'category': 'Вопрос', 'status': 'open', 'closed_by': '',
            'created_at': (now - timedelta(days=1)).isoformat(),
            'closed_at': None},
    # старый тикет (90 дней назад) — за период 30 дней НЕ должен попасть
    'T-3': {'category': 'Жалоба', 'status': 'closed', 'closed_by': 'Пётр',
            'created_at': (now - timedelta(days=90)).isoformat(),
            'closed_at': (now - timedelta(days=89)).isoformat()},
}
with open('data/ai_tickets_777.json', 'w', encoding='utf-8') as f:
    json.dump(tickets, f, ensure_ascii=False)

from web.app import app  # noqa: E402

client = app.test_client()
with client.session_transaction() as s:
    s['logged_in'] = True
    s['role'] = 'owner'
    s['username'] = 'owner'

print('== 2. Экспорт CSV — реальные строки ==')
r = client.post('/api/analytics/export', json={'period': 30, 'format': 'csv'})
check(r.status_code == 200, f'эндпоинт живой (код {r.status_code})')
body = r.get_data(as_text=True)
check('T-1' in body and 'T-2' in body, 'в CSV попали реальные тикеты периода')
check('T-3' not in body, 'старый тикет за границей периода отсечён')
check('01.01.2026' not in body and '2.5' not in body,
      'фейковой заглушки («01.01.2026…2.5») в отчёте больше нет')
check('Жалоба' in body and 'Вопрос' in body, 'категории из данных присутствуют')
check('text/csv' in r.headers.get('Content-Type', ''), 'mimetype — CSV')
check('attachment' in r.headers.get('Content-Disposition', ''),
      'файл отдаётся как вложение (attachment)')

print('== 3. Фильтры — как на странице ==')
r2 = client.post('/api/analytics/export',
                 json={'period': 30, 'format': 'csv', 'category': 'Вопрос'})
b2 = r2.get_data(as_text=True)
check('T-2' in b2 and 'T-1' not in b2, 'фильтр по категории работает')

r3 = client.post('/api/analytics/export',
                 json={'period': 30, 'format': 'csv', 'moderator': 'Анна'})
b3 = r3.get_data(as_text=True)
check('T-1' in b3 and 'T-2' not in b3, 'фильтр по модератору работает')

print('== 4. Неподдерживаемый формат — честный 501 ==')
r4 = client.post('/api/analytics/export', json={'format': 'pdf'})
check(r4.status_code == 501, f'pdf не выдумываем (код {r4.status_code})')

shutil.rmtree(_TMP, ignore_errors=True)
print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
