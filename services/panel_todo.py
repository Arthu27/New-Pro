# -*- coding: utf-8 -*-
"""Общий список задач команды (страница /todo в панели).

Простое JSON-хранилище data/panel_todo.json:
    [{"id": 1736..., "text": "...", "done": false,
      "author": "Owner", "created": "2026-08-12 13:20"}, ...]

Задачи шарятся между всеми, у кого есть доступ к странице (owner).
"""
import json
import os
import time
from datetime import datetime

from json_store import load_json, save_json

PATH = 'data/panel_todo.json'
MAX_TASKS = 200
MAX_TEXT = 140


def _load() -> list:
    return load_json(PATH, [])


def _save(tasks: list):
    save_json(PATH, tasks[:MAX_TASKS])


def list_tasks() -> list:
    """Новые сверху; done-флаг приводится к bool."""
    out = []
    for t in _load():
        if not isinstance(t, dict):
            continue
        out.append({'id': int(t.get('id', 0) or 0),
                    'text': str(t.get('text', ''))[:MAX_TEXT],
                    'done': bool(t.get('done')),
                    'author': str(t.get('author', '')),
                    'created': str(t.get('created', ''))})
    return out


def add_task(text: str, author: str = '') -> dict:
    text = ' '.join(str(text or '').split())[:MAX_TEXT]
    if not text:
        raise ValueError('Пустая задача')
    tasks = list_tasks()
    if len(tasks) >= MAX_TASKS:
        raise ValueError(f'Лимит: не больше {MAX_TASKS} задач')
    task_id = int(time.time() * 1000)
    existing = {t['id'] for t in tasks}
    while task_id in existing:          # две задачи за одну миллисекунду
        task_id += 1
    task = {'id': task_id, 'text': text, 'done': False,
            'author': str(author or '')[:32],
            'created': datetime.now().strftime('%Y-%m-%d %H:%M')}
    tasks.insert(0, task)
    _save(tasks)
    return task


def _mutate(tid, fn) -> bool:
    try:
        want = int(tid)
    except (TypeError, ValueError):
        return False          # None/мусор вместо id — не 500, а «не найдена»
    tasks = list_tasks()
    for i, t in enumerate(tasks):
        if t['id'] == want:
            fn(tasks, i)
            _save(tasks)
            return True
    return False


def toggle_task(tid) -> bool:
    return _mutate(tid, lambda ts, i: ts[i].__setitem__('done', not ts[i]['done']))


def delete_task(tid) -> bool:
    return _mutate(tid, lambda ts, i: ts.pop(i))
