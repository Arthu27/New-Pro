#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reset_server_data.py — ПОЛНАЯ ОЧИСТКА данных бота перед переездом на новый сервер.

Что удаляется (всё пересоздаётся при запуске бота):
  • data/          — все файлы и подпапки (логи, варны, тикеты, XP, балансы, обучение AI,
                     автомод/антирейд-конфиги СТАРОГО сервера, бэкапы и т.д.)
  • logs/          — bot.log, bot_errors.log и прочие лог-файлы
  • tunnel_url.txt — ссылка туннеля (сгенерируется заново)
  • __pycache__ / *.pyc — кэш Python

Что НЕ трогается: .env (токен и MAIN_GUILD_ID), код бота, config/ticket_config_example.json

Опции:
  --keep-auth   сохранить ДОСТУП К ПАНЕЛИ (panel_credentials, members, tokens, 2fa)
  --yes         не спрашивать подтверждение
  --dry-run     только показать, что будет удалено

Запуск:  python reset_server_data.py --yes
"""
import os, sys, shutil, glob

BASE = os.path.dirname(os.path.abspath(__file__))

# Файлы доступа к панели (сохраняются с --keep-auth)
AUTH_FILES = {
    'panel_credentials.json', 'panel_credentials.txt',
    'members.json', 'tokens.json', '2fa_secrets.json',
}

def rel(p):
    return os.path.relpath(p, BASE)

def collect(keep_auth=False):
    """Список (путь, описание) на удаление."""
    targets = []
    data_dir = os.path.join(BASE, 'data')
    if os.path.isdir(data_dir):
        for entry in sorted(os.listdir(data_dir)):
            full = os.path.join(data_dir, entry)
            if keep_auth and entry in AUTH_FILES:
                continue
            if os.path.isdir(full):
                targets.append((full, f'папка data/{entry}/ ({len(os.listdir(full))} элементов)'))
            else:
                targets.append((full, f'файл data/{entry}'))
    logs_dir = os.path.join(BASE, 'logs')
    if os.path.isdir(logs_dir):
        for entry in sorted(os.listdir(logs_dir)):
            full = os.path.join(logs_dir, entry)
            if os.path.isfile(full):
                targets.append((full, f'лог logs/{entry}'))
    tun = os.path.join(BASE, 'tunnel_url.txt')
    if os.path.isfile(tun):
        targets.append((tun, 'tunnel_url.txt'))
    for pyc in glob.glob(os.path.join(BASE, '**', '__pycache__'), recursive=True):
        if '.venv' in pyc or 'node_modules' in pyc:
            continue
        targets.append((pyc, 'кэш ' + rel(pyc)))
    return targets

def main():
    keep_auth = '--keep-auth' in sys.argv
    assume_yes = '--yes' in sys.argv
    dry_run = '--dry-run' in sys.argv

    targets = collect(keep_auth)
    print('═' * 60)
    print('  СБРОС ДАННЫХ AETHER — переезд на новый сервер')
    print('═' * 60)
    if not targets:
        print('Уже чисто — удалять нечего.')
    else:
        print(f'Будет удалено: {len(targets)} объектов\n')
        for path, desc in targets:
            print(f'  ✗ {desc}')
        if keep_auth:
            kept = sorted(AUTH_FILES & set(os.listdir(os.path.join(BASE, 'data'))) ) if os.path.isdir(os.path.join(BASE, 'data')) else []
            if kept:
                print('\nСохранится доступ к панели (--keep-auth): ' + ', '.join(kept))
    print('\n.env (TOKEN, MAIN_GUILD_ID) НЕ удаляется.')

    if dry_run:
        print('\n[--dry-run] Ничего не удалено.')
        return
    if not assume_yes:
        print('\n"yes" + Enter для подтверждения: ', end='')
        if input().strip().lower() != 'yes':
            print('Отменено.')
            return

    done, failed = 0, []
    for path, desc in targets:
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            done += 1
        except Exception as e:
            failed.append((desc, e))
    print(f'\nУдалено: {done}/{len(targets)}')
    for desc, e in failed:
        print(f'  ! не удалось {desc}: {e}')

    print('\n' + '─' * 60)
    print('  ДАЛЬШЕ — ЧЕК-ЛИСТ ПЕРЕЕЗДА:')
    print('  1) В .env впиши MAIN_GUILD_ID=<ID нового сервера>')
    print('     (сервер → ПКМ → «Копировать ID сервера»; режим разработчика)')
    print('     Несколько серверов: EXTRA_GUILD_IDS=111,222')
    print('  2) Пригласи бота на новый сервер (OAuth2 → права бота)')
    print('  3) Запусти бота — slash-команды и панель подхватят новый сервер')
    print('  4) В панели заново: «Доступ к панели» (маппинг ролей),')
    print('     автомод, варн-правила, ticket-категория (они были привязаны')
    print('     к старому серверу и удалены вместе с данными)')
    print('─' * 60)

if __name__ == '__main__':
    main()
