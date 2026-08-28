# -*- coding: utf-8 -*-
"""П.7 стабильность (долгая дистанция): РЕАЛЬНЫЙ сервер панели на 40 секунд.

Запускаем настоящий Flask-сервер (как в бою) в отдельном процессе, логинимся,
снимаем RSS директивно из /proc. 40 секунд непрерывного поллинга горячих
эндпоинтов панели (симулирует бесконечно открытую страницу с живой статистикой).

PASS-границы:
- <1% ответов 5xx;
- ни одного Traceback в stderr процесса;
- рост суммарной RSS сервера < 25 МБ за всё время;
- сервер завершается без зомби (graceful SIGTERM за 5с).
"""
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
import signal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 5093
PASS = 0
FAIL = 0


def check(ok, msg, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {detail}')


def rss_kb(pid):
    try:
        with open(f'/proc/{pid}/status') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1])
    except FileNotFoundError:
        return 0
    return 0


TMP = tempfile.mkdtemp(prefix='soak_')
server_code = r"""
import os, sys, tempfile
os.chdir(sys.argv[1])
os.environ.setdefault('PANEL_USER','admin')
os.environ.setdefault('PANEL_PASSWORD','test123')
os.environ['MAIN_GUILD_ID']='777'
sys.path.insert(0, r'%s')
import web.app as a
a.app.run(host='127.0.0.1', port=%d, debug=False, use_reloader=False)
""" % (ROOT, PORT)

proc = subprocess.Popen(
    [sys.executable, '-c', server_code, TMP],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

try:
    # ждём подъём сервера
    up = False
    for _ in range(60):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health', timeout=1)
            up = True
            break
        except urllib.error.HTTPError:
            up = True   # /health 503 = сервер уже слушает
            break
        except Exception:
            if proc.poll() is not None:
                break
            time.sleep(0.5)
    check(up, 'сервер поднялся и слушает порт')

    # логин
    cookie = None
    try:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **kw):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        data = urllib.parse.urlencode({'username': 'admin', 'password': 'test123'}).encode()
        req = urllib.request.Request(f'http://127.0.0.1:{PORT}/login', data=data)
        try:
            resp = opener.open(req, timeout=5)
        except urllib.error.HTTPError as e:   # 302 без авторедиректа — это ответ
            resp = e
        cookie = resp.headers.get('Set-Cookie', '').split(';')[0]
        # redirect → следуем
        u2 = urllib.request.Request(f'http://127.0.0.1:{PORT}/dashboard')
        if cookie:
            u2.add_header('Cookie', cookie)
        r2 = urllib.request.urlopen(u2, timeout=5)
        logged = r2.status == 200 and b'hakumo_theme' in r2.read()
    except Exception as e:
        logged = False
    check(logged, 'логин и вход в панель по-настоящему')

    print('== 40 секунд непрерывного поллинга ==')
    rss_samples = [(0.0, rss_kb(proc.pid))]
    err5xx = 0
    total = 0
    t0 = time.time()
    last_sample = t0
    HOT = [ '/api/guild/777/member-card/suggest?q=%40',
            '/health',
            '/static/pickers.js' ]
    permitted = {200, 503}   # health оффлайн честно 503
    while time.time() - t0 < 40:
        for path in HOT:
            req = urllib.request.Request(f'http://127.0.0.1:{PORT}{path}')
            if cookie:
                req.add_header('Cookie', cookie)
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    total += 1
                    if r.status not in permitted:
                        err5xx += 1
            except urllib.error.HTTPError as e:
                total += 1
                if e.code not in permitted:
                    err5xx += 1
            except Exception:
                err5xx += 1
                total += 1
        now = time.time()
        if now - last_sample >= 5:
            rss_samples.append((now - t0, rss_kb(proc.pid)))
            last_sample = now
        if proc.poll() is not None:
            break
    rss_samples.append((time.time() - t0, rss_kb(proc.pid)))

    check(proc.poll() is None, 'сервер жив после поллинга')
    check(total >= 150, f'выполнено запросов: {total} (>=150)')
    ratio = err5xx / max(total, 1)
    check(ratio < 0.01, f'5xx доля {ratio*100:.2f}% (<1%), ошибок {err5xx}/{total}')
    growth = (rss_samples[-1][1] - rss_samples[0][1]) / 1024
    check(growth < 25, f'RSS рост {growth:.1f} МБ (<25): ' +
                       '→'.join(f'{s//1024}' for _, s in rss_samples))
finally:
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
            dead = True
        except subprocess.TimeoutExpired:
            proc.kill()
            dead = False
    else:
        dead = True
check(dead, 'сервер остановлен (не зомби)')
err_tail = (proc.stderr.read() or '').encode() if proc.stderr else b''
tracebacks = err_tail.count(b'Traceback')
check(tracebacks == 0, f'stderr без traceback ({tracebacks})')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
