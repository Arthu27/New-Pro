# -*- coding: utf-8 -*-
"""Проверка «дружбы» файлов: порты, хосты и вызовы между компонентами.

Запуск:  python3 scripts/check_files.py        (Linux/macOS)
         python scripts\check_files.py         (Windows VDS)

Скрипт СТАТИЧЕСКИЙ: не запускает бота, не лезет в сеть, ничего не меняет.
Проверяет, что все файлы проекта «рукопожимаются» в обе стороны —
writer ↔ reader, вызов ↔ маршрут, батник ↔ Python:

  [A] Порт панели один и тот же во всех местах:
      config.py (PORT) → main.py (PANEL_PORT) → gunicorn (WEB_BIND) →
      docker-compose (ports + healthcheck) → setup_panel_tunnel.bat →
      quick-туннель → .env.example → ai_chat self-call.
  [B] Origin-политика: service→service вызовы только на 127.0.0.1
      (никаких http://localhost — на Windows localhost = ::1 = IPv6,
      а панель слушает IPv4: отсюда «dial tcp [::1]:5001: refused»).
  [C] main.py ↔ services/named_tunnel.py: каждая вызываемая функция
      существует, и весь критичный набор API реально используется.
  [D] scripts/setup_panel_tunnel.bat ↔ Python: батник пишет конфиг,
      который Python-модуль умеет читать (public_url/heal/regex пути),
      имена tunnnel-creds.json / WEB_BEHIND_PROXY / systemprofile совпадают.
  [E] Маршруты: каждый внутренний URL-вызов имеет живой @app.route
      (/health, /api/guild/<guild_id>/health); WS-порт совпадает.
  [F] .env.example: все ключи, которые читает код, задокументированы.
  [G] Конфиги туннеля на диске (VDS-режим): ingress ведёт на
      127.0.0.1:<порт панели>, tunnel_url.txt совпадает с конфигом.
  [H] Синтаксис ключевых файлов (py_compile).

Итог: строка «=== PASS N / FAIL M ===» и код выхода (0 — всё дружит).
Живое соединение бот↔панель проверяет отдельно scripts/check_connection.py.
"""
import importlib.util
import os
import py_compile
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

OK = 0
FAIL = 0
SKIP = 0


def read(path):
    """Текст файла (от корня репозитория), '' если файла нет."""
    try:
        with open(os.path.join(ROOT, path), encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except OSError:
        return ''


def check(ok, msg, fix=''):
    global OK, FAIL
    if ok:
        OK += 1
        print(f'  [OK]   {msg}')
    else:
        FAIL += 1
        print(f'  [FAIL] {msg}')
        if fix:
            print(f'         → {fix}')


def skip(msg):
    global SKIP
    SKIP += 1
    print(f'  [SKIP] {msg} — файла нет, нечего проверять')


def _env_value(key):
    """Значение из .env (мини-парсер, окружение не трогаем)."""
    try:
        with open(os.path.join(ROOT, '.env'), encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return os.environ.get(key, '')


def _effective_port(default_port):
    """Порт панели так же, как его вычисляет main.py: PANEL_PORT → PORT."""
    for key in ('PANEL_PORT', 'PORT'):
        raw = _env_value(key)
        if raw:
            try:
                return int(str(raw).split('#', 1)[0].strip())
            except ValueError:
                continue
    return default_port


print('=' * 68)
print(' Проверка «дружбы» файлов Hakumo (порты / хосты / вызовы / маршруты)')
print('=' * 68)

# ── A. Порт панели один и тот же везде ──────────────────────────────────────
print('\n[A] Порт панели:')
src_config = read('config.py')
src_main = read('main.py')
src_gunicorn = read('web/gunicorn_conf.py')
src_bat = read('scripts/setup_panel_tunnel.bat').replace('\r\n', '\n')
src_dc = read('docker-compose.yml')
src_envex = read('.env.example')
src_aichat = read('web/routes/ai_chat.py')

m = re.search(r'PORT\s*:\s*int\s*=\s*_env_int\(\s*["\']PORT["\']\s*,\s*(\d+)', src_config)
default_port = int(m.group(1)) if m else None
check(default_port is not None,
      f'config.py: PORT по умолчанию = {default_port}',
      'не найден «PORT: int = _env_int("PORT", N)» — проверь config.py')

eff_port = _effective_port(default_port or 5001)
print(f'         (эффективный порт с учётом .env/PANEL_PORT: {eff_port})')

if default_port:
    spots = [
        ('main.py: fallback порта', re.search(r'_port\s*=\s*_port\s*or\s*(\d+)', src_main)),
        ('web/gunicorn_conf.py: WEB_BIND', re.search(r"'0\.0\.0\.0:(\d+)'", src_gunicorn)),
        ('docker-compose.yml: ports', re.search(r'"(\d+):(\d+)"', src_dc)),
        ('docker-compose.yml: healthcheck', re.search(r"http://(?:localhost|127\.0\.0\.1):(\d+)/health", src_dc)),
        ('setup_panel_tunnel.bat: PANEL_PORT', re.search(r'set PANEL_PORT=(\d+)', src_bat)),
        ('main.py: quick-туннель --url', re.search(r'--url", "http://127\.0\.0\.1:(\d+)"', src_main)),
        ('.env.example: PANEL_PORT', re.search(r'PANEL_PORT[=#]\s*(\d+)', src_envex)),
    ]
    for name, mm in spots:
        # ports "X:Y" — совпадать должен и внешний, и внутренний
        vals = (mm.group(1), mm.group(2)) if name.startswith('docker-compose.yml: ports') \
            else ((mm.group(1),) if mm else ())
        check(bool(vals) and all(int(v) == default_port for v in vals),
              f'{name} = {default_port}',
              f'ожидаю {default_port} — поправь, иначе компоненты стучатся в разные порты')
    # config.py: WEB_BIND строится из того же PORT (дружба по построению)
    check('0.0.0.0:{PORT}' in src_config,
          'config.py: WEB_BIND = f"0.0.0.0:{PORT}" (тот же PORT)')
    # ai_chat: порт self-call берётся из PANEL_PORT/PORT, а не из константы
    check(('PANEL_PORT' in src_aichat and '127.0.0.1' in src_aichat
            and 'http://localhost' not in src_aichat),
          'web/routes/ai_chat.py: self-call на 127.0.0.1:<PANEL_PORT/PORT>',
          'порт self-call должен браться из PANEL_PORT/PORT, как у самого сервера')

# ── B. Origin-политика: service→service только 127.0.0.1 ────────────────────
print('\n[B] Origin-политика (127.0.0.1 вместо localhost):')
check('service: http://127.0.0.1:' in src_bat
      and 'service: http://localhost:' not in src_bat,
      'setup_panel_tunnel.bat: ingress пишется с http://127.0.0.1:PORT',
      'замени service: http://localhost:... на http://127.0.0.1:...')
check('http://localhost' not in src_dc,
      'docker-compose.yml: healthcheck ходит на 127.0.0.1',
      'в healthcheck замени localhost на 127.0.0.1')
check('"--url", "http://127.0.0.1' in src_main
      and '--url", "http://localhost' not in src_main,
      'main.py: quick-туннель стартует на 127.0.0.1')
check('http://localhost' not in src_aichat,
      'web/routes/ai_chat.py: self-call без localhost')
# Браузерные ссылки (README, подсказки в консоли) localhost разрешён —
# это человек открывает в своём браузере, а не сервис стучится к сервису.

# ── C. main.py ↔ services/named_tunnel.py ───────────────────────────────────
print('\n[C] main.py ↔ services/named_tunnel.py:')
sys.path.insert(0, ROOT)
try:
    spec = importlib.util.spec_from_file_location(
        'named_tunnel_check', os.path.join(ROOT, 'services', 'named_tunnel.py'))
    nt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nt)
    check(True, 'services/named_tunnel.py импортируется без побочек')
except Exception as ex:  # noqa: BLE001
    nt = None
    check(False, 'services/named_tunnel.py импортируется без побочек', f'ошибка: {ex}')

if nt is not None:
    used = set(re.findall(r'_nt\.(\w+)\s*\(', src_main))
    check(bool(used), f'main.py вызывает {len(used)} функций named_tunnel')
    for name in sorted(used):
        check(hasattr(nt, name),
              f'_nt.{name}() из main.py существует в named_tunnel.py',
              f'в services/named_tunnel.py нет функции {name} — main.py упадёт')
    # Обратное направление («туда-сюда»): критичный набор API туннеля
    # обязан использоваться — иначе сайдкар тихо теряет часть функций.
    for name in ('find_config', 'public_url', 'remember_url', 'export_portable',
                 'ensure_binary', 'ensure_credentials', 'runtime_config',
                 'heal_all_origins'):
        check(name in used,
              f'named_tunnel.{name}() реально вызывается из main.py',
              f'функция есть, но main.py её не зовёт — сайдкар потерял шаг')
    # Пара writer↔reader: main.py читает tunnel_url.txt тем же именем,
    # под которым named_tunnel его пишет.
    check('tunnel_url.txt' in src_main and nt.URL_FILE == 'tunnel_url.txt',
          'tunnel_url.txt: main.py читает файл с тем же именем, что пишет named_tunnel')

# ── D. setup_panel_tunnel.bat ↔ Python ──────────────────────────────────────
print('\n[D] scripts/setup_panel_tunnel.bat ↔ Python:')
m_tname = re.search(r'set TNAME=(\S+)', src_bat)
check(m_tname and nt is not None and m_tname.group(1) == nt.TUNNEL_NAME,
      f'имя туннеля совпадает: bat TNAME == named_tunnel.TUNNEL_NAME '
      f'({m_tname.group(1) if m_tname else "?"})',
      'bat и Python должны звать туннель одинаково — иначе создадут два разных')
hosts = dict(re.findall(r'set (HOST[123])=(\S+)', src_bat))
check(len(hosts) == 3, f'bat привязывает 3 хоста: {", ".join(hosts.values())}')

# Рендерим ТОТ конфиг, который реально напишет батник (echo-строки с %VAR%),
# и прогоняем его через Python-читателей — writer ↔ reader в обе стороны.
rendered = []
for line in src_bat.split('\n'):
    mm = re.match(r'^(?:>>?)\s*"%CFG%"\s*echo(?:\s+(.*))?$', line.strip())
    if not mm:
        continue
    body = (mm.group(1) or '').strip()
    if body == '(':
        rendered.append('')
        continue
    body = re.sub(r'%USERPROFILE%', '/home/u', body)
    body = re.sub(r'%PANEL_PORT%', str(default_port or 5001), body)
    body = re.sub(r'%HOST[123]%', lambda h: hosts.get(h.group(0)[1:-1], h.group(0)), body)
    body = re.sub(r'%TID%', 'tid-check', body)
    rendered.append(body)
rendered_cfg = '\n'.join(rendered) + '\n'
check(len(rendered) >= 8, f'из bat собран конфиг туннеля ({len(rendered)} строк)',
      'не нашёл блок записи config.yml в батнике — проверь секцию [5/6]')
if len(rendered) >= 8 and nt is not None:
    with tempfile.NamedTemporaryFile('w', suffix='.yml', delete=False,
                                     encoding='utf-8') as tmp:
        tmp.write(rendered_cfg)
        tmp_path = tmp.name
    try:
        check(nt.public_url(tmp_path) == 'https://' + hosts.get('HOST1', ''),
              f'named_tunnel.public_url() читает конфиг батника: https://{hosts.get("HOST1", "")}',
              'public_url() не нашёл hostname — формат config.yml разъехался')
        check(re.search(r'(?m)^credentials-file:\s*\S+\s*$', rendered_cfg) is not None,
              'строка credentials-file из батника совпадает с regex runtime_config()',
              'runtime_config() не найдёт ключ — проверь формат строки в батнике')
        check('http://localhost' not in rendered_cfg,
              'конфиг, который пишет батник, уже без localhost')
        check(nt.heal_localhost_origins(tmp_path) is False,
              'heal_localhost_origins(): свежему конфигу батника чинить нечего')
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

src_nt = read('services/named_tunnel.py')
check('tunnel-creds.json' in src_bat and 'tunnel-creds.json' in src_nt,
      'tunnel-creds.json: батник копирует ключ под тем именем, которое ищет Python')
check('WEB_BEHIND_PROXY=1' in src_bat and 'WEB_BEHIND_PROXY' in read('web/app.py'),
      'WEB_BEHIND_PROXY: батник включает — web/app.py читает')
check('.cloudflared' in src_bat and "'.cloudflared', 'config.yml'" in src_nt,
      'путь ~/.cloudflared/config.yml: батник пишет — find_config() ищет там же')
check('systemprofile' in src_bat and 'systemprofile' in src_nt,
      'профиль службы (systemprofile\\.cloudflared): батник и _sync_service_profile() совпадают')

# ── E. Маршруты: вызов ↔ живой route ────────────────────────────────────────
print('\n[E] Внутренние вызовы ↔ маршруты Flask:')
src_app = read('web/app.py')
src_community = read('web/routes/community.py')
src_checkconn = read('scripts/check_connection.py')
check(re.search(r"@app\s*\.\s*route\s*\(\s*['\"]/health['\"]", src_app) is not None,
      "маршрут /health существует (его зовут docker healthcheck и check_connection)",
      'добавь @app.route("/health") в web/app.py')
check(re.search(r"route\s*\(\s*['\"]/api/guild/<guild_id>/health['\"]", src_community) is not None,
      "маршрут /api/guild/<guild_id>/health существует (его зовёт ai_chat self-call)",
      'проверь web/routes/community.py')
check('/api/guild/' in src_aichat and 'health' in src_aichat,
      'ai_chat зовёт существующий шаблон URL /api/guild/…/health')
ws_main = re.search(r"WS_PORT[^\n]*or\s*(\d+)", src_main)
ws_conn = re.search(r"WS_PORT[^\n]*or\s*(\d+)", src_checkconn)
check(ws_main and ws_conn and ws_main.group(1) == ws_conn.group(1),
      f'WebSocket-порт одинаков: main.py и check_connection.py = {ws_main.group(1) if ws_main else "?"}',
      'дефолты WS_PORT разъехались — live-обновления панели будут «не туда»')

# ── F. .env.example ↔ код (туда-сюда) ───────────────────────────────────────
print('\n[F] .env.example документирует ключи, которые читает код:')
env_code = {
    'PANEL_PORT': 'main.py',
    'PANEL_PROCESS': 'main.py',
    'WEB_BIND': 'web/gunicorn_conf.py',
    'WEB_BEHIND_PROXY': 'web/app.py',
    'TUNNEL_AUTOSTART': 'main.py',
    'TUNNEL_PROTOCOL': 'main.py',
    'QUICK_TUNNEL': 'main.py',
    'DISABLE_TUNNEL': 'main.py / docker-compose',
    'WS_PORT': 'main.py',
    'WEB_WORKERS': 'web/gunicorn_conf.py',
    'WEB_TIMEOUT': 'web/gunicorn_conf.py',
}
all_src = src_main + src_gunicorn + read('web/app.py') + src_dc
for key, where in env_code.items():
    check(key in src_envex and key in all_src,
          f'{key}  ({where})',
          f'ключ читается кодом, но не описан в .env.example (или наоборот)')

# ── G. Конфиги туннеля на диске (VDS-режим) ─────────────────────────────────
print('\n[G] Конфиги туннеля на диске:')
disk_cfgs = [
    ('scripts/config.yml', os.path.join(ROOT, 'scripts', 'config.yml')),
    ('~/.cloudflared/config.yml', os.path.join(os.path.expanduser('~'), '.cloudflared', 'config.yml')),
    ('scripts/.hakumo_tunnel_runtime.yml', os.path.join(ROOT, 'scripts', '.hakumo_tunnel_runtime.yml')),
]
found_cfg = None
for label, path in disk_cfgs:
    if not os.path.isfile(path):
        skip(label)
        continue
    found_cfg = found_cfg or path
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            text = fh.read()
    except OSError as ex:
        check(False, f'{label} читается', f'ошибка: {ex}')
        continue
    services = re.findall(r'(?m)^\s*-?\s*service:\s*(\S+)', text)
    http_origins = [s for s in services if s.startswith('http://')]
    check(bool(http_origins), f'{label}: есть ingress-правила ({len(http_origins)} http)')
    for svc in http_origins:
        mm = re.match(r'http://([^:/]+):?(\d+)?', svc)
        host, port = (mm.group(1), mm.group(2)) if mm else ('?', '?')
        check(host == '127.0.0.1',
              f'{label}: origin {svc} — хост 127.0.0.1',
              'замени на http://127.0.0.1:... (localhost на Windows = ::1 = IPv6). '
              'Бот тоже чинит это сам при старте (heal_all_origins).')
        if port:
            check(int(port) == eff_port,
                  f'{label}: origin порт {port} == порту панели {eff_port}',
                  f'порт в ingress ({port}) не совпадает с PANEL_PORT/PORT ({eff_port}) — '
                  'туннель стучится не в тот порт')
# tunnel_url.txt ↔ public_url(config): writer и reader согласованы
url_txt = os.path.join(ROOT, 'tunnel_url.txt')
if os.path.isfile(url_txt) and found_cfg and nt is not None:
    try:
        with open(url_txt, encoding='utf-8', errors='replace') as fh:
            saved = fh.read().strip()
        expected = nt.public_url(found_cfg)
        check(saved == expected,
              f'tunnel_url.txt ({saved}) == public_url(config.yml) ({expected})',
              'ссылка в tunnel_url.txt протухла — бот перепишет при следующем старте')
    except OSError:
        skip('tunnel_url.txt ↔ config.yml')
else:
    skip('tunnel_url.txt ↔ config.yml (нужно оба файла)')

# ── H. Синтаксис ключевых файлов ────────────────────────────────────────────
print('\n[H] Синтаксис:')
for path in ('main.py', 'config.py', 'services/named_tunnel.py',
             'web/gunicorn_conf.py', 'web/wsgi.py',
             'web/routes/ai_chat.py', 'web/routes/community.py'):
    try:
        py_compile.compile(os.path.join(ROOT, path), doraise=True)
        check(True, f'{path} компилируется')
    except Exception as ex:  # noqa: BLE001
        check(False, f'{path} компилируется', f'{ex}')

# ── Итог ────────────────────────────────────────────────────────────────────
print()
print('=' * 68)
print(f' ИТОГ: PASS {OK} / FAIL {FAIL}' + (f' / SKIP {SKIP}' if SKIP else ''))
print('=' * 68)
print('=== PASS %d / FAIL %d ===' % (OK, FAIL))
sys.exit(1 if FAIL else 0)
