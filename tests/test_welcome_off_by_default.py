# -*- coding: utf-8 -*-
"""Директива: авто-приветствия новых участников ВЫКЛЮЧЕНЫ по умолчанию.

Владелец позже сам включит и настроит в панели. Контракт:
1. welcome_card: DEFAULT_CFG — enabled/welcome/goodbye = False. При этом
   saved-конфиг с явным True (человек включил) продолжает работать.
2. welcome_pro: DEFAULT_SETTINGS['enabled'] — False.
3. welcome_cog: на голом сервере (без конфига панели и без !setwelcome)
   на join ничего не отправляется.
4. Обработчики on_member_join в welcome_* уважают гейт enabled/конфига
   (код проверяет флаг ДО отправки).
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = 0
FAIL = 0


def check(ok, msg, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {msg}')
    else:
        FAIL += 1
        print(f'  FAIL: {msg} {detail}')


def default_flags(path, var):
    tree = ast.parse(open(path, encoding='utf-8').read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == var and isinstance(node.value, ast.Dict):
                    out = {}
                    for k, v in zip(node.value.keys, node.value.values):
                        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                            out[k.value] = v.value
                    return out
    return {}


print('== welcome_card / welcome_pro: все авто-флаги False ==')
cfg_c = default_flags(os.path.join(ROOT, 'cogs/welcome_card.py'), 'DEFAULT_CFG')
check(cfg_c.get('enabled') is False, f'welcome_card.DEFAULT_CFG enabled={cfg_c.get("enabled")} (нужно False)')
check(cfg_c.get('welcome') is False and cfg_c.get('goodbye') is False,
      f'welcome_card welcome/goodbye выключены по умолчанию ({cfg_c.get("welcome")}/{cfg_c.get("goodbye")})')
cfg_p = default_flags(os.path.join(ROOT, 'cogs/welcome_pro.py'), 'DEFAULT_SETTINGS')
check(cfg_p.get('enabled') is False, f'welcome_pro DEFAULT_SETTINGS enabled={cfg_p.get("enabled")}')
check(cfg_p.get('dm_enabled') is False, 'welcome_pro DM-приветствия выключены по умолчанию')

print('== welcome_cog: без конфигов — тишина ==')
src = open(os.path.join(ROOT, 'cogs/welcome_cog.py'), encoding='utf-8').read()
check('if not sec :' in src or 'if not sec:' in src, 'panel-ветка возвращается без конфига')
check('if self .welcome_channel_id' in src or 'if self.welcome_channel_id' in src,
      'legacy-ветка гейтится наличием канала')
# оба гейта идут ДО channel.send — там просто return на пустом конфиге
send_idx = src.find('await channel .send')
if send_idx < 0:
    send_idx = src.find('await channel.send')
gate_idx = src.find('_panel_section')
check(0 < gate_idx < send_idx or send_idx < 0,
      'конфиг-гейт идёт перед отправкой (нет отправки без явных настроек)')

print('== гейт enabled ДО _send_card в welcome_card ==')
wc = open(os.path.join(ROOT, 'cogs/welcome_card.py'), encoding='utf-8').read()
join_txt = wc[wc.index('def on_member_join'):]
gate_pos = join_txt.find("'enabled'") if "'enabled'" in join_txt else join_txt.find('get(\'enabled\'')
any_gate = "'enabled'" in join_txt or 'enabled' in join_txt
check(any_gate, 'on_member_join читает флаг enabled до отправки карточки')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
sys.exit(1 if FAIL else 0)
