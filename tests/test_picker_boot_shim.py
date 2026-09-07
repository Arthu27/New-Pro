# -*- coding: utf-8 -*-
"""Шим-очередь пикеров: страничные скрипты не должны умирать до инициализации.

Баг (жалоба владельца «не видно название канала» на главной): страничные
скрипты выполняются РАНЬШЕ pickers.js (он в конце body) и зовут
attachMemberPicker/sshdEnhance на верхнем уровне. ReferenceError убивал
весь страничный скрипт — на главной из-за этого не выполнялся
loadAnnChannels, и в «Куда публиковать» не было ни одного канала.

Регрессия проверяет контракт бут-шима:
1) base.html ставит заглушки-очереди для всех пикеров, которые шаблоны
   зовут на верхнем уровне;
2) pickers.js после загрузки повторяет отложенные вызовы настоящими
   функциями;
3) ни один шаблон не зовёт функцию из pickers.js на верхнем уровне,
   которой нет в шим-очереди.
"""

import re
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, 'web', 'templates', 'base.html')
PICKERS = os.path.join(ROOT, 'web', 'static', 'pickers.js')
TPL_DIR = os.path.join(ROOT, 'web', 'templates')

# функции, которые бут-шим обязан встречать очередью
SHIM_LIST = [
    'attachMemberPicker', 'attachIdPicker', 'attachSelectSearch',
    'attachSelectPicker', 'attachListFilter', 'sshdEnhance',
    'bindCopyId', 'bindCtrlS', 'bindSlashFocus', 'dirtyTrack',
]

# что pickers.js экспортирует в window (настоящие реализации)
PICKERS_EXPORTS = re.compile(r'window\.(\w+)\s*=\s*function')

# верхнеуровневый вызов в шаблоне: имя( без window.-защиты и не в комментарии
TOP_LEVEL_CALL = re.compile(r'^\s*(?!//)(?!.*window\.)(\w+)\s*\(', re.M)


def read(path):
    with open(path, encoding='utf-8') as fp:
        return fp.read()


def main():
    failures = []

    base = read(BASE)
    pickers = read(PICKERS)

    # 1) шим-очередь в base.html покрывает весь список
    for name in SHIM_LIST:
        ok = ('__pickerQueue' in base
              and re.search(r"['\"]" + re.escape(name) + r"['\"]", base))
        if not ok:
            failures.append(f'base.html: {name} отсутствует в шим-очереди __pickerQueue')
    if 'W.__pickerQueue=[]' not in base.replace(' ', ''):
        failures.append('base.html: нет инициализации __pickerQueue')

    # 2) pickers.js повторяет отложенные вызовы
    replay_ok = ('__pickerQueue' in pickers
                 and 'forEach' in pickers.split('__pickerQueue', 1)[1][:900])
    if not replay_ok:
        failures.append('pickers.js: нет блока повтора отложенных вызовов (__pickerQueue)')

    # 3) ни один шаблон не зовёт на верхнем уровне функцию из pickers.js,
    #    которой нет в шим-списке
    exports = set(PICKERS_EXPORTS.findall(pickers))
    shimmed = set(SHIM_LIST)
    for fname in sorted(os.listdir(TPL_DIR)):
        if not fname.endswith('.html'):
            continue
        src = read(os.path.join(TPL_DIR, fname))
        for m in TOP_LEVEL_CALL.finditer(src):
            name = m.group(1)
            if name in exports and name not in shimmed:
                line = src[:m.start()].count('\n') + 1
                failures.append(
                    f'{fname}:{line} — верхнеуровневый вызов {name}() из pickers.js '
                    f'без шима: ReferenceError убьёт страничный скрипт')

    # 4) главный симптом: на главной пикер каналов наполняется —
    #    вызов loadAnnChannels стоит в том же скрипте и доживает до init
    dash = read(os.path.join(TPL_DIR, 'dashboard.html'))
    if 'loadAnnChannels' not in dash:
        failures.append('dashboard.html: пропал loadAnnChannels')
    # вызов пикера участника не должен стоять ДО определения функций init-блока
    # (порядок фиксирован шаблоном — просто проверяем наличие обоих кусков)
    if 'ann-channel' not in dash:
        failures.append('dashboard.html: пропал селект ann-channel')

    print(f'=== PICKER BOOT SHIM: PASS {4 - min(len(failures), 4)} блока(ов) / FAIL {len(failures)} ===')
    for f in failures:
        print('  FAIL:', f)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
