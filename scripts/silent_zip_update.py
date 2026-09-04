# -*- coding: utf-8 -*-
"""Обновление кода для update_silent.bat (когда git недоступен).

Два режима:

--pending   применить архив, который бот скачал и проверил ДО выключения
            (data/.update_pending.zip). Это основной путь: заказ владельца —
            «не выключайся, пока не скачается новая версия», значит к моменту
            перезапуска архив уже лежит на диске и проверен.
без флага   скачать архив ветки самим. Запасной путь — нужен, чтобы
            update_silent.bat и update.bat работали и при ручном запуске,
            когда бот архив не готовил.

В обоих случаях кладутся ТОЛЬКО изменённые файлы (данные, .env, .venv и .git
не трогаются). Пауз и перезапуска здесь нет — их делает вызвавшее окно
обновлятора. Код выхода: 0 — обновление применено (или применять было нечего),
1 — не вышло (тогда старый код остаётся как есть).
"""
import json
import os
import shutil
import sys
import tempfile


def _stage(SU, bot_dir, zip_path, root, rel, sha, branch):
    """Разложить архив по файлам и запомнить применённую версию."""
    ok, err, stats = SU.stage_update(zip_path, bot_dir, root, rel,
                                     0, sha or '', branch or '')
    if not ok:
        print(f"  обновление: замена файлов не удалась: {err}")
        return 1
    if sha:
        SU.note_applied_sha(bot_dir, sha)
    print(f"  обновление: обновлено {stats.get('copied', 0)} файлов, "
          f"убрано устаревших {stats.get('removed', 0)}")
    return 0


def apply_pending(SU, bot_dir):
    """Применить архив, скачанный ботом до перезапуска.

    Возвращает 0 — применили, 1 — применили с ошибкой, None — готового
    архива нет (вызвавший код тогда качает сам).
    """
    zip_path, root, rel = SU.load_pending(bot_dir)
    if not zip_path:
        return None
    _z, meta_path = SU.pending_paths(bot_dir)
    sha = branch = ''
    try:
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)
        sha = str(meta.get('sha') or '')
        branch = str(meta.get('branch') or '')
    except (OSError, ValueError, json.JSONDecodeError) as ex:
        print(f"  обновление: описание архива не читается: {ex}")
    print("  обновление: применяю архив, скачанный ботом до перезапуска...")
    rc = _stage(SU, bot_dir, zip_path, root, rel, sha, branch)
    SU.clear_pending(bot_dir)
    return rc


def download_and_apply(SU, bot_dir, branch):
    """Запасной путь: скачать архив ветки самим."""
    tmp = tempfile.mkdtemp(prefix='hakumo_dl_')
    try:
        ok, err, zip_path = SU.download_zip(tmp)
        if not ok:
            print(f"  обновление: скачивание не удалось: {err}")
            return 1
        ok, err, meta = SU.verify_zip(zip_path)
        if not ok:
            print(f"  обновление: архив не прошёл проверку: {err}")
            return 1
        _pairs, root, rel = meta
        return _stage(SU, bot_dir, zip_path, root, rel, '', branch)
    except Exception as ex:  # noqa: BLE001
        print(f"  обновление: непредвиденная ошибка: {ex}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    sys.path.insert(0, os.getcwd())
    try:
        from services import self_update as SU
    except Exception as ex:  # noqa: BLE001
        print(f"  обновление: не удалось импортировать self_update: {ex}")
        return 1

    bot_dir = os.getcwd()
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    branch = args[0] if args else 'main'

    if '--pending' in sys.argv:
        rc = apply_pending(SU, bot_dir)
        if rc is not None:
            return rc
        print("  обновление: готового архива нет — качаю сам")
    return download_and_apply(SU, bot_dir, branch)


if __name__ == '__main__':
    sys.exit(main())
