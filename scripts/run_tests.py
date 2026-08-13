#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Регрессионный прогон всех тестов Aether (MOEBIUS).

    python3 scripts/run_tests.py           # прогон + сводка
    python3 scripts/run_tests.py -v        # + полный вывод упавших наборов

Каждый тест — самостоятельный скрипт, печатающий '=== PASS N / FAIL M ==='
и возвращающий ненулевой код при падениях. Скрипт считает итоги по всем
наборам и завершается кодом 1, если хоть один упал (годится для CI).
"""
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE_RE = re.compile(r'=== PASS (\d+) / FAIL (\d+) ===')


def find_tests():
    tests_dir = os.path.join(ROOT, 'tests')
    return sorted(
        os.path.join(tests_dir, f) for f in os.listdir(tests_dir)
        if f.startswith('test_') and f.endswith('.py'))


def run_one(path):
    started = time.time()
    proc = subprocess.run(
        [sys.executable, path], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    out = proc.stdout.decode('utf-8', errors='replace')
    passed = failed = None
    for m in LINE_RE.finditer(out):
        passed, failed = int(m.group(1)), int(m.group(2))
    return {
        'path': path,
        'passed': passed,
        'failed': failed,
        'exit': proc.returncode,
        'secs': time.time() - started,
        'out': out,
    }


def main():
    verbose = '-v' in sys.argv
    tests = find_tests()
    if not tests:
        print('Тестов не найдено в tests/')
        return 1

    total_p = total_f = 0
    broken = []
    print(f'Прогоняем {len(tests)} наборов из tests/…\n')
    for path in tests:
        r = run_one(path)
        name = os.path.basename(path)
        if r['passed'] is None:
            broken.append((name, 'нет итоговой строки === PASS/FAIL ===', r))
            print(f'  💥 {name:<38} НЕТ СВОДКИ (exit {r["exit"]})')
            continue
        total_p += r['passed']
        total_f += r['failed']
        if r['failed'] or r['exit']:
            broken.append((name, f"{r['failed']} падений, exit {r['exit']}", r))
            print(f'  ❌ {name:<38} PASS {r["passed"]:>4} / FAIL {r["failed"]:>2} '
                  f'({r["secs"]:.1f}s)')
        else:
            print(f'  ✅ {name:<38} PASS {r["passed"]:>4} ({r["secs"]:.1f}s)')

    print('\n' + '═' * 56)
    print(f'ИТОГО: {len(tests)} наборов · {total_p} проверок · '
          f'{total_f + sum(1 for _, _, r in broken if r["passed"] is None)} проблем')
    if broken:
        print('═' * 56)
        print('УПАЛО:')
        for name, why, r in broken:
            print(f'  - {name}: {why}')
        if verbose:
            for name, _why, r in broken:
                print(f'\n── вывод {name} (хвост) ──')
                print('\n'.join(r['out'].splitlines()[-40:]))
        print('═' * 56)
        return 1
    print('ВСЁ ЗЕЛЁНОЕ ✅')
    print('═' * 56)
    return 0


if __name__ == '__main__':
    sys.exit(main())
