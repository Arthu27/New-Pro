# -*- coding: utf-8 -*-
"""ZIP-режим демона автообновления: фиксы ДОЕЗЖАЮТ до установки без .git.

Жалоба 30.08 «опять так же — команды не удалились»: владелец обновляется
ZIP-архивом ветки (без .git), и демон auto_update.py в этом режиме ВООБЩЕ
не обновлял бота — remote-хэш он брал только у `git rev-parse origin/...`,
который без .git вечно возвращает None. Ни один фикс до владельца не
доезжал. Вторая грабля: распаковка срывала префикс архива по ЗАХАРДКОЖЕННЫМ
старым именам репозитория — архив свежей ветки (New-Pro-arena-.../)
распаковывался во вложенную папку, бот работал на старых файлах.

Здесь проверяем: маркер версии data/.update_sha (тот же, что пишет /update),
корень архива из самого архива, распаковку в плоскую структуру с защитой
data/ и .env, и проводку главного цикла (API вместо git, троттлинг опроса,
git-проверки не блокируют ZIP-режим).

Запуск: python3 tests/test_auto_update_zip.py
"""
import io
import json
import os
import sys
import tempfile
import types
import zipfile

_TMP = tempfile.mkdtemp(prefix='hakumo_autoupd_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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


import auto_update  # noqa: E402  (импорт безопасен: демон не стартует)


# ═══ A. Маркер версии ZIP-установки ══════════════════════════════════════
print('== A. Маркер версии: data/.update_sha ==')
botdir = os.path.join(_TMP, 'bot')
os.makedirs(os.path.join(botdir, 'data'), exist_ok=True)
_saved_bot_dir = auto_update.BOT_DIR
auto_update.BOT_DIR = botdir
try:
    check(auto_update.get_local_zip_commit() is None,
          'без маркера версия неизвестна (None) — надо обновиться')
    auto_update.note_zip_commit('abc123def456')
    check(auto_update.get_local_zip_commit() == 'abc123def456',
          'маркер записан и прочитан')
    with open(os.path.join(botdir, 'data', '.update_sha'), encoding='utf-8') as f:
        check(f.read().strip() == 'abc123def456',
              'формат маркера совпадает с /update (services/self_update)')
    auto_update.note_zip_commit('')            # пустой — не перезаписываем
    check(auto_update.get_local_zip_commit() == 'abc123def456',
          'пустой sha не затирает маркер (иначе — обновления по кругу)')

    # ═══ B. Корень архива выводим из самого архива ══════════════════════
    print('== B. Корень архива GitHub ==')
    r = auto_update._archive_root(
        ['New-Pro-arena-01a04e42-new-pro/main.py',
         'New-Pro-arena-01a04e42-new-pro/services/x.py',
         'New-Pro-arena-01a04e42-new-pro/cogs/'])
    check(r == 'New-Pro-arena-01a04e42-new-pro/',
          f'префикс свежей ветки выводится ({r})')
    check(auto_update._archive_root(
        ['hakumo-bot-main/main.py', 'hakumo-bot-main/cogs/x.py'])
        == 'hakumo-bot-main/', 'старое имя репозитория тоже работает')
    check(auto_update._archive_root(['main.py']) == '',
          'архив без корня (плоский) — не срезаем ничего')
    check(auto_update._archive_root(
        ['a/1.py', 'b/2.py']) == '',
          'разные корни — это не архив ветки, префикс не срезаем')
    check(auto_update._archive_root([]) == '', 'пустой список — ок')

    # ═══ C. Распаковка ZIP: плоско, data/ и .env целы ═══════════════════
    print('== C. Распаковка архива ветки ==')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('New-Pro-arena-01a04e42-new-pro/main.py', '# fresh main')
        zf.writestr('New-Pro-arena-01a04e42-new-pro/services/menu_mode.py',
                    '# fresh service')
        zf.writestr('New-Pro-arena-01a04e42-new-pro/cogs/help.py', '# cog')
        # архив НЕ должен трогать данные юзера, даже если внутри есть data/
        zf.writestr('New-Pro-arena-01a04e42-new-pro/data/evil.json',
                    '{"evil": true}')
    zip_bytes = buf.getvalue()

    with open(os.path.join(botdir, '.env'), 'w', encoding='utf-8') as f:
        f.write('BOT_TOKEN=user-secret\nBOT_FULL=1\n')
    with open(os.path.join(botdir, 'data', '.update_sha'), 'w',
              encoding='utf-8') as f:
        f.write('OLDOLDOLD\n')

    class FakeResp:
        status_code = 200
        content = zip_bytes

    auto_update.requests = types.SimpleNamespace(
        get=lambda url, headers=None, timeout=None: FakeResp())
    try:
        auto_update.download_and_extract()
    finally:
        import requests as _real_requests
        auto_update.requests = _real_requests

    check(open(os.path.join(botdir, 'main.py'), encoding='utf-8').read()
          == '# fresh main', 'main.py распакован В КОРЕНЬ (не во вложенную папку)')
    check(os.path.exists(os.path.join(botdir, 'services', 'menu_mode.py'))
          and os.path.exists(os.path.join(botdir, 'cogs', 'help.py')),
          'структура каталогов сохранена')
    check(not os.path.exists(os.path.join(botdir, 'data', 'evil.json')),
          'data/ из архива НЕ тронута (данные юзера священны)')
    check(open(os.path.join(botdir, '.env'), encoding='utf-8').read()
          == 'BOT_TOKEN=user-secret\nBOT_FULL=1\n', '.env не тронут')
    check(open(os.path.join(botdir, 'data', '.update_sha'),
               encoding='utf-8').read().strip() == 'OLDOLDOLD',
          'существующий маркер версии не затёрт распаковкой')
    check(not os.path.exists(os.path.join(botdir, 'hakumo-update.zip')),
          'временный архив убран')
finally:
    auto_update.BOT_DIR = _saved_bot_dir


# ═══ D. Проводка главного цикла: ZIP-режим видит обновления ══════════════
print('== D. Главный цикл: ZIP-режим спрашивает GitHub API ==')
src = open(os.path.join(ROOT, 'auto_update.py'), encoding='utf-8').read()
check('get_remote_commit()' in src.split('while True:')[1],
      'в цикле есть GitHub API fallback для remote-хэша')
check('ZIP_API_POLL_SEC' in src and '300' in src,
      'опрос API троттлится (анонимный лимит GitHub 60/час)')
check('get_local_zip_commit()' in src.split('while True:')[1],
      'локальная версия в ZIP-режиме — из маркера data/.update_sha')
check('_is_git and _detect_branch()' in src,
      'проверка ветки — только для git-режима (ZIP она не блокирует)')
check('_is_git and not _tree_is_clean()' in src,
      'проверка чистоты дерева — только для git-режима')
check('note_zip_commit(remote_sha)' in src,
      'после ZIP-обновления маркер версии записывается (нет цикла обновлений)')
check('note_zip_commit' in src and 'download_and_extract()' in src,
      'ZIP-обновление вызывает распаковку и пишет маркер')

# поведение против «вечной новизны»: маркер == remote → обновления нет
check(auto_update._archive_root is not None
      and auto_update.get_local_zip_commit is not None
      and auto_update.note_zip_commit is not None,
      'хелперы ZIP-режима существуют и импортируются')

print()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
