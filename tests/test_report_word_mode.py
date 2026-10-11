# -*- coding: utf-8 -*-
"""«Дать слово» должно включать mode=manual — иначе word_id игнорируется."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(tempfile.mkdtemp(prefix='rep_word_'))
os.makedirs('data', exist_ok=True)
os.environ['DB_PATH'] = os.path.abspath(os.path.join('data', 'bot.db'))
sys.path.insert(0, ROOT)

from services import reports_core as RC  # noqa: E402
from cogs import reports as R  # noqa: E402

PASS = FAIL = 0


def check(ok, msg, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {extra}')


print('== word mode ==')
RC.ticket_create(1, 900, 111, 222, kind='card')
# как после открытия разбора
RC.ticket_set(900, mode='manual', word_id='')
t = RC.ticket_get(900)
check((t or {}).get('mode') == 'manual', 'после открытия разбора mode=manual')

# симулируем выбор «дать слово» обвиняемому
RC.ticket_set(900, mode='manual', word_id='222')
t = RC.ticket_get(900)
check(t.get('word_id') == '222' and t.get('mode') == 'manual',
      'дать слово ставит word_id и mode=manual')

# фильтр: при wait+word_id раньше ломалось — теперь speaker = word_id
t_wait = dict(t, mode='wait', word_id='222', reporter_id='111')
speaker = str(t_wait.get('word_id') or t_wait.get('reporter_id') or '')
check(speaker == '222', 'даже при mode=wait учитываем word_id')

body = R._razbor_table(t)
check('Разбор вызова' in body and 'Слово' in body and '<@222>' in body,
      'таблица разбора содержит слово')
check('rpt_action' in open(os.path.join(ROOT, 'cogs', 'reports.py'),
                            encoding='utf-8').read(),
      'панель разбора — V2 select rpt_action')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
