#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор docs/MODULES.md — каталог когов из их docstring-ов.

    python3 scripts/gen_module_docs.py            # напечатать в stdout
    python3 scripts/gen_module_docs.py --write    # записать docs/MODULES.md

Каталог группируется по cogs_policy: Системные / Модерация (MOD_ONLY) /
Комьюнити и развлечения / Хелперы. Держать CATEGORY-списки актуальными —
задача cogs_policy.py, так что каталог устаревает только по описаниям.
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('DB_PATH', os.path.join('/tmp', 'gen_docs_bot.db'))


def first_line(path):
    """Первая строка docstring модуля (или имя файла, если docstring пуст)."""
    try:
        tree = ast.parse(open(path, encoding='utf-8').read())
        doc = ast.get_docstring(tree) or ''
    except SyntaxError:
        doc = ''
    lines = [l.strip() for l in doc.splitlines() if l.strip()]
    return lines[0] if lines else os.path.basename(path)[:-3]


def build():
    from cogs_policy import CORE_COGS, MODERATION_COGS, HELPER_COGS
    rows = []
    for fn in sorted(os.listdir(os.path.join(ROOT, 'cogs'))):
        if not fn.endswith('.py'):
            continue
        title = first_line(os.path.join(ROOT, 'cogs', fn))
        if fn in HELPER_COGS:
            group = 'Хелперы (импортируются)'
        elif fn in CORE_COGS:
            group = 'Системные'
        elif fn in MODERATION_COGS:
            group = 'Модерация (MOD_ONLY)'
        else:
            group = 'Комьюнити и развлечения'
        rows.append((group, fn[:-3], title))

    order = ['Системные', 'Модерация (MOD_ONLY)',
             'Комьюнити и развлечения', 'Хелперы (импортируются)']
    out = ['# Каталог модулей бота', '',
           'Автогенерация из docstring-ов когов (`cogs/*.py`). Обновить:',
           '`python3 scripts/gen_module_docs.py --write`.', '']
    for g in order:
        items = [r for r in rows if r[0] == g]
        out.append(f'## {g} — {len(items)}')
        out.append('')
        out.append('| Модуль | Что делает |')
        out.append('| --- | --- |')
        for _g, name, title in items:
            out.append(f'| `{name}` | {title.replace("|", "/") or "—"} |')
        out.append('')
    out.append(f'**Всего:** {len(rows)} файлов в `cogs/`.')
    return '\n'.join(out) + '\n'


def main():
    text = build()
    if '--write' in sys.argv:
        path = os.path.join(ROOT, 'docs', 'MODULES.md')
        with open(path, 'w', encoding='utf-8') as fp:
            fp.write(text)
        print(f'записано: {path}')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
