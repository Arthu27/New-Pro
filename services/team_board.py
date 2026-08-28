# -*- coding: utf-8 -*-
"""Канбан-доска команды модерации (страница /team-board).

JSON-хранилище data/team_board.json:
    {"next_id": N, "tasks": {id: {"id", "title", "status", "priority",
     "assignee", "due", "note", "author", "created", "updated", "order"}}}

Статусы: todo / doing / done. Приоритеты: low / mid / high / urgent.
Доска общая для всех модераторов — как реальный операционный стол команды.
"""
import json
import os
import time
from datetime import datetime

from json_store import load_json, save_json

PATH = 'data/team_board.json'
MAX_TASKS = 300
MAX_TITLE = 120
MAX_NOTE = 500
MAX_ASSIGNEE = 48

STATUSES = ('todo', 'doing', 'done')
PRIORITIES = ('low', 'mid', 'high', 'urgent')

PRIORITY_LABELS = {
    'low': 'Низкий',
    'mid': 'Средний',
    'high': 'Высокий',
    'urgent': 'Срочный',
}
STATUS_LABELS = {
    'todo': 'Очередь',
    'doing': 'В работе',
    'done': 'Готово',
}


def _load_raw() -> dict:
    data = load_json(PATH, {})
    if not isinstance(data, dict):
        return {}
    return data


def _save_raw(data: dict):
    save_json(PATH, data)


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M')


def list_tasks() -> list:
    """Все задачи нормализованные, отсортированные по order внутри статуса."""
    data = _load_raw()
    tasks = data.get('tasks', {})
    out = []
    if not isinstance(tasks, dict):
        return out
    for key, t in tasks.items():
        if not isinstance(t, dict):
            continue
        status = t.get('status', 'todo')
        if status not in STATUSES:
            status = 'todo'
        priority = t.get('priority', 'mid')
        if priority not in PRIORITIES:
            priority = 'mid'
        out.append({
            'id': int(key),
            'title': str(t.get('title', ''))[:MAX_TITLE],
            'status': status,
            'priority': priority,
            'assignee': str(t.get('assignee', '') or '')[:MAX_ASSIGNEE],
            'due': str(t.get('due', '') or ''),
            'note': str(t.get('note', '') or '')[:MAX_NOTE],
            'author': str(t.get('author', '') or '')[:32],
            'created': str(t.get('created', '') or ''),
            'updated': str(t.get('updated', '') or ''),
            'order': int(t.get('order', 0) or 0),
        })
    out.sort(key=lambda x: (STATUSES.index(x['status']), x['order'], -x['id']))
    return out


def board_view() -> dict:
    """Удобная выдача для страницы: колонки + плоский список."""
    tasks = list_tasks()
    columns = {}
    for st in STATUSES:
        columns[st] = {
            'key': st,
            'label': STATUS_LABELS[st],
            'tasks': [t for t in tasks if t['status'] == st],
        }
    counts = {st: len(columns[st]['tasks']) for st in STATUSES}
    return {'columns': columns, 'tasks': tasks, 'counts': counts,
            'statuses': STATUSES, 'priorities': PRIORITIES,
            'priority_labels': PRIORITY_LABELS, 'status_labels': STATUS_LABELS}


def add_task(title, status='todo', priority='mid', assignee='', due='', note='', author=''):
    """Создать задачу. Возвращает (task|None, error|None)."""
    title = ' '.join(str(title or '').split())[:MAX_TITLE]
    if not title:
        return None, 'Пустая задача'
    if status not in STATUSES:
        return None, f'status: только {", ".join(STATUSES)}'
    if priority not in PRIORITIES:
        return None, f'priority: только {", ".join(PRIORITIES)}'
    data = _load_raw()
    tasks = data.get('tasks', {})
    if not isinstance(tasks, dict):
        tasks = {}
    if len(tasks) >= MAX_TASKS:
        return None, f'Лимит: не больше {MAX_TASKS} задач'
    task_id = int(data.get('next_id', 1) or 1)
    existing = {int(k) for k in tasks}
    while task_id in existing:
        task_id += 1
    order = max([int(t.get('order', 0) or 0) for t in tasks.values()
                 if isinstance(t, dict) and t.get('status') == status] or [-1]) + 1
    task = {
        'id': task_id,
        'title': title,
        'status': status,
        'priority': priority,
        'assignee': str(assignee or '')[:MAX_ASSIGNEE],
        'due': str(due or '').strip()[:20],
        'note': str(note or '').strip()[:MAX_NOTE],
        'author': str(author or '')[:32],
        'created': _now(),
        'updated': _now(),
        'order': order,
    }
    tasks[str(task_id)] = task
    data['tasks'] = tasks
    data['next_id'] = task_id + 1
    _save_raw(data)
    return task, None


def update_task(task_id, patch):
    """Патч задачи: title/status/priority/assignee/due/note. Возвращает (task, err)."""
    data = _load_raw()
    tasks = data.get('tasks', {})
    key = str(task_id)
    if not isinstance(tasks, dict) or key not in tasks or not isinstance(tasks[key], dict):
        return None, 'Задача не найдена'
    t = tasks[key]
    allowed = ('title', 'status', 'priority', 'assignee', 'due', 'note')
    for field in allowed:
        if field in patch:
            value = patch[field]
            if field == 'title':
                value = ' '.join(str(value or '').split())[:MAX_TITLE]
                if not value:
                    return None, 'Пустой заголовок'
                t['title'] = value
            elif field == 'status':
                if value not in STATUSES:
                    return None, f'status: только {", ".join(STATUSES)}'
                t['status'] = value
            elif field == 'priority':
                if value not in PRIORITIES:
                    return None, f'priority: только {", ".join(PRIORITIES)}'
                t['priority'] = value
            elif field == 'assignee':
                t['assignee'] = str(value or '')[:MAX_ASSIGNEE]
            elif field == 'due':
                t['due'] = str(value or '').strip()[:20]
            elif field == 'note':
                t['note'] = str(value or '').strip()[:MAX_NOTE]
    t['updated'] = _now()
    tasks[key] = t
    data['tasks'] = tasks
    _save_raw(data)
    return t, None


def reorder(tasks_order):
    """Применить порядок: {status: [id, ...]}. Возвращает (ok, err)."""
    if not isinstance(tasks_order, dict):
        return False, 'нужен объект {status: [ids]}'
    data = _load_raw()
    tasks = data.get('tasks', {})
    if not isinstance(tasks, dict):
        return False, 'хранилище пусто'
    for status, ids in tasks_order.items():
        if status not in STATUSES or not isinstance(ids, list):
            continue
        for idx, task_id in enumerate(ids):
            key = str(task_id)
            if key in tasks and isinstance(tasks[key], dict):
                tasks[key]['status'] = status
                tasks[key]['order'] = idx
                tasks[key]['updated'] = _now()
    data['tasks'] = tasks
    _save_raw(data)
    return True, None


def delete_task(task_id):
    """Удалить задачу. Возвращает (ok, err)."""
    data = _load_raw()
    tasks = data.get('tasks', {})
    key = str(task_id)
    if not isinstance(tasks, dict) or key not in tasks:
        return False, 'Задача не найдена'
    del tasks[key]
    data['tasks'] = tasks
    _save_raw(data)
    return True, None
