# -*- coding: utf-8 -*-
"""Телефонные оверлеи не должны перекрывать кнопки на компьютере.

После адаптации панели под телефон (гамбургер, бэкдроп сайдбара,
keyboard-open, ящики чата) полноэкранные слои и overflow-x:clip
утекали на широкий экран — клики «пропадали». Эти проверки держат
телефонный UX, но требуют, чтобы опасные правила жили только внутри
max-width media.

Запуск: python3 tests/test_desktop_click_overlays.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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


def strip_comments(src):
    return re.sub(r'/\*.*?\*/', '', src, flags=re.S)


def extract_media(src, query_substr):
    """Вернуть тела всех @media, чей заголовок содержит query_substr."""
    src = strip_comments(src)
    bodies = []
    i = 0
    while True:
        m = re.search(r'@media[^{]*\{', src[i:])
        if not m:
            break
        start = i + m.start()
        header_end = i + m.end()
        header = src[start:header_end]
        depth = 1
        j = header_end
        while j < len(src) and depth:
            if src[j] == '{':
                depth += 1
            elif src[j] == '}':
                depth -= 1
            j += 1
        body = src[header_end:j - 1]
        if query_substr in header:
            bodies.append(body)
        i = j
    return bodies


def top_level(src):
    """CSS без комментариев и без @media/@supports/@keyframes блоков."""
    src = strip_comments(src)
    out = []
    i = 0
    n = len(src)
    while i < n:
        m = re.search(r'@(?:media|supports|keyframes|property)[^{]*\{', src[i:])
        if not m:
            out.append(src[i:])
            break
        out.append(src[i:i + m.start()])
        depth = 1
        j = i + m.end()
        while j < n and depth:
            if src[j] == '{':
                depth += 1
            elif src[j] == '}':
                depth -= 1
            j += 1
        i = j
    return ''.join(out)


CSS = open(os.path.join(ROOT, 'web', 'static', 'style.css'), encoding='utf-8').read()
APP = open(os.path.join(ROOT, 'web', 'static', 'app.js'), encoding='utf-8').read()
GUARD = open(os.path.join(ROOT, 'web', 'static', 'click-guard.js'), encoding='utf-8').read()
CHAT = open(os.path.join(ROOT, 'web', 'templates', 'chat.html'), encoding='utf-8').read()

print('== 1. overflow-x: clip только на телефоне ==')
top = top_level(CSS)
check('overflow-x: clip' not in top and 'overflow-x:clip' not in top.replace(' ', ''),
      'на широком экране html/body не режут overflow-x clip')
phone_1080 = '\n'.join(extract_media(CSS, 'max-width: 1080px'))
check('overflow-x: clip' in phone_1080,
      'на ≤1080 overflow-x: clip остаётся (телефон не скроллится вбок)')

print('== 2. бэкдроп сайдбара не ловит клики на компе ==')
check('.sidebar-backdrop.show' not in top,
      'глобального .sidebar-backdrop.show нет')
check('pointer-events: auto' in phone_1080 and '.sidebar-backdrop.show' in phone_1080,
      'на ≤1080 открытый бэкдроп кликабелен')
desk_1081 = '\n'.join(extract_media(CSS, 'min-width: 1081px'))
check('.sidebar-backdrop' in desk_1081 and 'pointer-events: none' in desk_1081,
      'на ≥1081 бэкдроп выключен даже с классом .show')
check('.mobile-menu { display: none; }' in desk_1081.replace('\n', ' ') or
      '.mobile-menu { display: none; }' in desk_1081,
      'гамбургер скрыт на широком экране')

print('== 3. keyboard-open не душит кнопки на компе ==')
check('body.keyboard-open' not in top,
      'keyboard-open не действует вне media')
phone_860 = '\n'.join(extract_media(CSS, 'max-width: 860px'))
check('body.keyboard-open' in phone_860 and 'pointer-events: none' in phone_860,
      'на ≤860 клавиатура прячет нижнее меню и FAB')
check("matchMedia('(max-width: 860px)')" in APP,
      'JS вешает keyboard-open только на ≤860')
check("matchMedia('(max-width: 1080px)')" in APP,
      'JS закрывает сайдбар, когда ширина >1080')

print('== 4. чат-ящики: бэкдроп только на узком экране ==')
chat_styles = '\n'.join(re.findall(r'<style[^>]*>(.*?)</style>', CHAT, re.S))
chat_top = top_level(chat_styles)
check('.chat-drawer-backdrop.show' not in chat_top,
      'глобального .chat-drawer-backdrop.show нет')
chat_1120 = '\n'.join(extract_media(chat_styles, 'max-width: 1120px'))
check('.chat-drawer-backdrop.show' in chat_1120,
      'на ≤1120 бэкдроп ящика участников/каналов показывается')
check('window.__chatCloseDrawers = close' in CHAT,
      '__chatCloseDrawers определён (выбор канала закрывает ящик)')
check("matchMedia('(max-width: 820px)')" in CHAT and
      "matchMedia('(max-width: 1120px)')" in CHAT,
      'кнопки каналов/участников открывают ящики только на телефоне')
check("matchMedia('(min-width: 1121px)')" in CHAT,
      'на широком экране ящики чата закрываются')

print('== 5. click-guard не пробрасывает клик сквозь открытый оверлей ==')
check('.sidebar-backdrop.show' in GUARD, 'гард знает бэкдроп сайдбара')
check('.chat-drawer-backdrop.show' in GUARD, 'гард знает бэкдроп чата')
check('.fab.backdrop.show' in GUARD, 'гард знает бэкдроп FAB')

print('== 6. скобки на месте ==')
check(CSS.count('{') == CSS.count('}'),
      f'style.css скобки {CSS.count("{")}/{CSS.count("}")}')
check(chat_styles.count('{') == chat_styles.count('}'),
      f'chat.html <style> скобки {chat_styles.count("{")}/{chat_styles.count("}")}')
check(CHAT.rstrip().endswith('{% endblock %}'),
      'chat.html не обрезан')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
