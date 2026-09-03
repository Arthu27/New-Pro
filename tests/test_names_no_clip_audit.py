# -*- coding: utf-8 -*-
"""Названия в панели нигде не режутся многоточием (аудит «везде»).

Жалоба владельца (2026-09): «не показ названия … таких везде» — имена
каналов, ролей, участников и серверов обрезались эллипсисом и были видны
только при наведении/выделении. После правок имена переносятся
(white-space:normal + overflow-wrap:anywhere) либо несут title с полным
именем.

Правило аудита: перечисленные селекторы (это блоки с ИМЕНАМИ) не должны
содержать тройку обрезки (nowrap + hidden + ellipsis) и должны уметь
переносить текст.

Запуск: python3 tests/test_names_no_clip_audit.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = 0
FAIL = 0
CLIP = ('text-overflow', 'ellipsis', 'white-space: nowrap', 'white-space:nowrap')


def check(cond, label, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  PASS: {label}')
    else:
        FAIL += 1
        print(f'  FAIL: {label} {extra}')


def rule_of(text, sel):
    """Возвращает CSS-правило, начинающееся с селектора sel, или ''."""
    pos = 0
    while True:
        i = text.find(sel, pos)
        if i < 0:
            return ''
        # не захватывать префикс другого класса (напр. .log-user vs .log-user-wrap)
        nxt = text[i + len(sel):i + len(sel) + 1]
        if nxt not in (' ', '\t', '{', '\n', '.', ':', '>'):
            pos = i + 1
            continue
        head = text[i + len(sel):]
        j = head.find('{')
        if j < 0 or any(ch in head[:j] for ch in '{}'):
            pos = i + 1
            continue
        end = text.find('}', i + len(sel) + j)
        return text[i:end + 1]


def check_no_clip(path, selector, label):
    s = open(os.path.join(ROOT, path), encoding='utf-8').read()
    r = rule_of(s, selector)
    check(bool(r), f'{label}: правило найдено')
    if r:
        ok = not any(c in r for c in CLIP) and 'overflow-wrap' in r
        check(ok, f'{label}: нет обрезки, есть перенос', f'→ {r[:110]}')


print('== style.css: имена в карточках/списках ==')
for sel, label in [
    ('.g-name', 'имя сервера (g-name)'),
    ('.member-name', 'имя участника (member-name)'),
    ('.member-username', '@username (member-username)'),
    ('.bd-item-name', 'имя в списке (bd-item-name)'),
    ('.pf-lb-cap', 'подпись-имя (pf-lb-cap)'),
    ('.sshd-lbl', 'подпись строки выбора (sshd-lbl)'),
]:
    check_no_clip('web/static/style.css', sel, label)

print('== chat.html: каналы, участники, меншены ==')
for sel, label in [
    ('.ch-item .ch-name', 'имя канала в чате'),
    ('.member-name', 'имя участника в списке чата'),
    ('.mention-name', 'имя в меншен-попапе'),
]:
    check_no_clip('web/templates/chat.html', sel, label)

print('== страничные списки ==')
for path, sel, label in [
    ('web/templates/role_permissions.html', '.role-name', 'имя роли (роли-права)'),
    ('web/templates/role_permissions.html', '.cmd-name', 'имя команды'),
    ('web/templates/role_permissions.html', '.act-name', 'имя действия'),
    ('web/templates/panel_menu.html', '.pname', 'имя пункта меню (редактор меню)'),
    ('web/templates/member_apply.html', '.sname', 'имя сервера в заявке'),
    ('web/templates/mod_center.html', '.mod-bar-name', 'имя модератора (mod_center)'),
    ('web/templates/voice_stats.html', '.vc-name', 'имя в voice_stats'),
    ('web/templates/afk_list.html', '.afk-name', 'имя в afk_list'),
    ('web/templates/message_logs.html', '.log-user', 'имя в message_logs'),
    ('web/templates/anticrash.html', '.ac-key', 'имя в anticrash'),
    ('web/templates/mod_kiosk.html', '.k-feed-row .copy b', 'имя в ленте mod_kiosk'),
    ('web/templates/konsol.html', '.kn-name', 'имя в konsol'),
]:
    check_no_clip(path, sel, label)

print('== title с полным именем на динамических строках ==')
ch = open(os.path.join(ROOT, 'web/templates/guardian.html'), encoding='utf-8').read()
check('title="\' + esc(r.name) + \'">' in ch,
      'guardian: роль с title полного имени')
ac = open(os.path.join(ROOT, 'web/templates/anticrash.html'), encoding='utf-8').read()
check('title="${esc(b.module)}"' in ac and 'title="${esc(t.name)}"' in ac,
      'anticrash: модуль/правило с title')
ko = open(os.path.join(ROOT, 'web/templates/konsol.html'), encoding='utf-8').read()
check('title="${esc(l.name)}"' in ko, 'konsol: строка с title')

print()
print(f'=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
