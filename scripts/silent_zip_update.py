# -*- coding: utf-8 -*-
"""Запасное обновление для update_silent.bat (когда git недоступен).

Качает архив ветки, проверяет целостность и кладёт ТОЛЬКО изменённые файлы
(данные/.env/.venv/.git не трогаются). Без пауз и перезапуска — их делает
вызвавшее окно обновлятора. Код выхода: 0 — обновление применено (или нечего
было применять), 1 — не вышло (тогда старый бот продолжает работать).
"""
import os
import sys
import tempfile
import shutil


def main() -> int:
    sys.path.insert(0, os.getcwd())
    try:
        from services import self_update as SU
    except Exception as ex:  # noqa: BLE001
        print(f"  zip: не удалось импортировать self_update: {ex}")
        return 1

    bot_dir = os.getcwd()
    branch = (sys.argv[1] if len(sys.argv) > 1 else 'main')
    tmp = tempfile.mkdtemp(prefix='hakumo_dl_')
    try:
        ok, err, zip_path = SU.download_zip(tmp)
        if not ok:
            print(f"  zip: скачивание не удалось: {err}")
            return 1
        ok, err, meta = SU.verify_zip(zip_path)
        if not ok:
            print(f"  zip: архив не прошёл проверку: {err}")
            return 1
        _pairs, root, rel = meta
        ok, err, stats = SU.stage_update(zip_path, bot_dir, root, rel,
                                         0, '', branch)
        if not ok:
            print(f"  zip: замена файлов не удалась: {err}")
            return 1
        print(f"  zip: обновлено {stats.get('copied', 0)} файлов, "
              f"убрано устаревших {stats.get('removed', 0)}")
        return 0
    except Exception as ex:  # noqa: BLE001
        print(f"  zip: непредвиденная ошибка: {ex}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
