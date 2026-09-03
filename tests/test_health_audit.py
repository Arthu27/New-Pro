# -*- coding: utf-8 -*-
"""Глубокий аудит «идеальности» — scripts/check_health.py без FAIL.

Прогоняет аудит отдельным процессом (как владелец на VDS), в изолированном
HOME, и дополнительно проверяет, что аудит РЕАЛЬНО ЛОВИТ проблемы: подсунутый
незащищённый роут обязан уронить проверку (не «резиновая печать»).

Запуск: python3 tests/test_health_audit.py
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OK = 0
FAIL = 0


def check(ok, msg):
    global OK, FAIL
    if ok:
        OK += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg}')


def run_audit(env):
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, 'scripts', 'check_health.py')],
        cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    return proc.returncode, proc.stdout.decode('utf-8', errors='replace')


# Зонд п.3/3 кладёт web/routes/_audit_probe.py. Если прошлый запуск был
# прерван жёстко (kill/сбой), файл мог остаться — тогда аудит п.1 уже
# падает («незащищённый роут») и весь набор краснеет без причины.
# Подчищаем осиротевший зонд ДО чистого прогона.
_STALE_PROBE = os.path.join(ROOT, 'web', 'routes', '_audit_probe.py')
try:
    os.remove(_STALE_PROBE)
except OSError:
    pass


print('[1/3] Чистый прогон scripts/check_health.py (изолированный HOME):')
env = dict(os.environ)
env['HOME'] = tempfile.mkdtemp(prefix='hakumo_health_audit_')
if os.name == 'nt':
    env['USERPROFILE'] = env['HOME']

code, out = run_audit(env)
print(out.rstrip())

matches = re.findall(r'=== PASS (\d+) / FAIL (\d+) ===', out)
inner_pass, inner_fail = (int(matches[-1][0]), int(matches[-1][1])) if matches else (0, -1)

print('\n[2/3] Итог аудита:')
check(code == 0, 'check_health.py завершился с кодом 0 — «всё идеально»')
check(inner_fail == 0, f'FAIL внутри аудита = {inner_fail} (должно быть 0)')
check(inner_pass >= 25,
      f'аудит не «похудел»: {inner_pass} проверок (ожидаю не меньше 25)')
for section in ('[A]', '[B]', '[C]', '[D]', '[E]', '[F]', '[G]', '[H]'):
    check(section in out, f'секция {section} на месте')

print('\n[3/3] Аудит ловит проблемы (зонд: незащищённый роут):')
probe = os.path.join(ROOT, 'web', 'routes', '_audit_probe.py')
try:
    with open(probe, 'w', encoding='utf-8') as fh:
        fh.write(
            '# -*- coding: utf-8 -*-\n\n'
            'def register(ctx):\n'
            '    app = ctx.app\n\n'
            '    @app.route("/api/test-vulnerability", methods=["POST"])\n'
            '    def test_vuln():\n'
            '        return "boom"\n')
    code2, out2 = run_audit(env)
    check(code2 == 1 and '/api/test-vulnerability' in out2,
          'незащищённый роут уронил аудит (защита роутов реально работает)')
finally:
    try:
        os.remove(probe)
    except OSError:
        pass

code3, _ = run_audit(env)
check(code3 == 0, 'после удаления зонда аудит снова зелёный')

print()
print(f'=== PASS {OK} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
