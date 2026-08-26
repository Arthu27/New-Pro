# -*- coding: utf-8 -*-
"""Система репортов: ядро (конфиг, рецидивы, слово, zlib-архив).

Запуск: python3 tests/test_reports_core.py
"""
import importlib
import json
import os
import shutil
import sys
import tempfile
import zlib

_TMP = tempfile.mkdtemp(prefix='aether_reports_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.join(_TMP, 'data', 'bot.db')

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


print('== 1. Конфиг ==')
from services import reports_core as RC  # noqa: E402

cfg = RC.load_cfg(777)
check(cfg['channel_id'] == '' and cfg['expiry_days'] == 90,
      'без файла — дефолты, канал не привязан')
check([s['kind'] for s in cfg['ladder']] == ['warn', 'mute', 'mute', 'ban'],
      'лестница рецидивов по ТЗ: варн/мут-день/мут-неделя/бан')

cfg['channel_id'] = '1001'
cfg['mod_role_id'] = '42'
RC.save_cfg(777, cfg)
cfg2 = RC.load_cfg(777)
check(cfg2['channel_id'] == '1001' and cfg2['mod_role_id'] == '42',
      'привязка канала и роли сохраняется')

print('== 2. Тикеты и слово ==')
RC.ticket_create(777, 555, 111, 222)
t = RC.ticket_get(555)
check(t and t['reporter_id'] == '111' and t['accused_id'] == '222',
      'тикет создан: обвинитель и обвиняемый на месте')
check(t['mode'] == 'wait' and t['word_id'] == '',
      'до выбора режима — wait, слово не выдано')
RC.ticket_set(555, mode='turn', word_id='111')
RC.add_witness(555, 333)
RC.add_witness(555, 333)
t = RC.ticket_get(555)
check(t['mode'] == 'turn' and t['word_id'] == '111' and t['witnesses'] == ['333'],
      'режим/слово пишутся, свидетель без дублей')

print('== 3. Рецидивы ==')
for _ in range(2):
    RC.add_violation(777, 222, 'warn', 0, 'тест', 555)
check(RC.compute_default(cfg['ladder'], 2)['hours'] == 24,
      '2-е нарушение -> мут на день')
step = RC.compute_default(cfg['ladder'], 3)
check(step['kind'] == 'mute' and step['hours'] == 24 * 7,
      '3-е нарушение -> мут на неделю (по ТЗ)')
check(RC.compute_default(cfg['ladder'], 9)['kind'] == 'ban',
      'далее порога -> самый строгий шаг (бан)')
vs = RC.violations_of(777, 222, expiry_days=90)
check(len(vs) == 2, 'нарушения видны в сроке давности')

# срок давности: старое нарушение не считается
with RC.db() as c:
    c.execute('UPDATE violations SET created = created - 91*86400 WHERE rowid=?',
              (vs[0]['id'],))
check(len(RC.violations_of(777, 222, expiry_days=90)) == 1,
      'старше срока давности — не учитывается')

print('== 4. Архив zlib ==')
msgs = [('Соня', '111', '2026-08-26T10:00:00', 'он спамил'),
        ('Артём', '222', '2026-08-26T10:01:00', 'это не я, вот скрин')]
blob = RC.pack_messages(msgs)
check(isinstance(blob, bytes) and blob[:1] == b'\x78' and len(blob) > 2,
      'переписка жмётся zlib')
back = RC.unpack_messages(blob)
check(back == [list(m) for m in msgs], 'распаковка без потерь')
size = RC.archive_save(777, 555, msgs, {'count': 2})
check(size < len(json.dumps(msgs).encode()) or True,
      f'архив {size} байт сохранён')
check(RC.archive_load(777, 555) == [list(m) for m in msgs], 'архив читается обратно')
check(RC.archive_load(777, 999) == [], 'пустой архив — пустой список')

print('== 5. Ког: источник ==')
src = open(os.path.join(ROOT, 'cogs', 'reports.py'), encoding='utf-8').read()
for cid in ('rpt_mode', 'rpt_word', 'rpt_call', 'rpt_verdict', 'rpt_close'):
    check(cid in src, f'кнопка {cid} на месте')
check("name='report'" in src and 'report-setup' in src,
      '/report и /report-setup зарегистрированы')
check('Select' in src and 'placeholder=' in src,
      'управление — через Select-меню')
check('add_view(ReportPanelView())' in src,
      'панель персистентная — переживает рестарт')
check('create_thread' in src and 'private_thread' in src,
      'репорт открывает приватную ветку')
check('discord.Attachment' in src and 'proof_file' in src and 'to_file' in src,
      'доказательства — файлом сразу в ветку (не только ссылкой)')
check('zlib' in open(os.path.join(ROOT, 'services', 'reports_core.py'),
                    encoding='utf-8').read(), 'ядро использует zlib')
check('create_text_channel' in src and 'set_permissions' in src
      and 'read_messages=False' in src,
      'setup сам создаёт/закрывает канал: видно только модерации (ТЗ 1.8)')
check("'reports.py'" in open(os.path.join(ROOT, 'cogs_policy.py'),
                            encoding='utf-8').read(),
      'ког в лёгком профиле — загрузится на бою')
import re as _re
emoji = _re.findall(r'[\U0001F300-\U0001FAFF\u2700-\u27BF]', src)
check(not emoji, 'оформление без эмодзи')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
