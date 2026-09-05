# -*- coding: utf-8 -*-
"""Скрытый пункт меню не всплывает: сайдбар, поиск, JSON-киты, страховка JS.
Запуск: python3 tests/test_hidden_menu_chrome.py
"""
import os
import re
import shutil
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix='hakumo_chrome_test_')
os.chdir(_TMP)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.makedirs('data', exist_ok=True)

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


from services import panel_menu as PM  # noqa: E402

print('== 1. Скрытый лэйаутом путь пропадает из vis, остаётся в all ==')
allp = PM.all_menu_paths()
check('/lockdown' not in allp, '/lockdown не в MENU — FAB не прячем через panelPathHidden')
check('/warnings' in allp and '/mod-insights' in allp and '/chat' in allp,
      'варны, аналитика и чат — пункты MENU')
owner_vis = PM.visible_paths_for('owner')
check('/warnings' in owner_vis, 'владелец видит /warnings до скрытия')

PM.save_layout(['/warnings', '/mod-insights', '/chat', '/cog-manager'], {})
vis_mod = PM.visible_paths_for('mod')
vis_own = PM.visible_paths_for('owner')
check('/warnings' not in vis_mod and '/warnings' not in vis_own,
      'скрытые варны не в vis ни у мода, ни у владельца')
check('/mod-insights' not in vis_own and '/chat' not in vis_own,
      'скрытые аналитика и чат не в vis владельца')
check('/warnings' in PM.all_menu_paths(), 'скрытый путь всё ещё в all — JS знает, что прятать')
check('/panel-menu' in vis_own, 'защищённый /panel-menu нельзя спрятать')

# поиск страниц 1:1 с сайдбаром
hidden_labels = []
for g in PM.panel_groups_for('owner'):
    for p in g.get('pages', []):
        if p['path'] in ('/warnings', '/mod-insights', '/chat'):
            hidden_labels.append(p['path'])
check(not hidden_labels, f'panel_groups_for не отдаёт скрытые ({hidden_labels})')

print('== 2. JS-страховка: strip + клик + палитра + @-finder ==')
app_js = open(os.path.join(ROOT, 'web/static/app.js'), encoding='utf-8').read()
check('window.stripHiddenMenuLinks' in app_js, 'stripHiddenMenuLinks есть')
check("doc.addEventListener('click'" in app_js and 'panelPathHidden(a.getAttribute' in app_js,
      'клик по скрытой ссылке перехватывается')
check("p === '/lockdown'" in app_js, 'panelPathHidden не прячет /lockdown')
check('paletteInitData();\n    if (window.stripHiddenMenuLinks)' in app_js,
      'strip вызывается после загрузки vis/all')
check("panelPathHidden('/chat')" in app_js, '@-finder не подмешивает каналы, если /chat скрыт')
check('panelPathHidden(it.href)' in app_js, 'удалённый поиск Ctrl+K режет скрытые href')
check("n.link = ''" in app_js and "it.link = ''" in app_js,
      'уведомления и лента активности не ведут в скрытый раздел')

print('== 3. JSON vis/all в base и киоске ==')
base = open(os.path.join(ROOT, 'web/templates/base.html'), encoding='utf-8').read()
kiosk = open(os.path.join(ROOT, 'web/templates/mod_kiosk.html'), encoding='utf-8').read()
check('id="palette-data"' in base and 'id="menu-all-paths"' in base,
      'base.html отдаёт palette-data и menu-all-paths')
check('id="palette-data"' in kiosk and 'id="menu-all-paths"' in kiosk,
      'киоск (без base) тоже отдаёт vis/all — иначе strip там no-op')
check("{% if '/appeals' in panel_visible_paths %}" in kiosk, 'киоск: апелляции за vis')
check("{% if '/security' in panel_visible_paths %}" in kiosk, 'киоск: угроза за vis')

print('== 4. Остаточный хром шаблонов за vis ==')
need = {
    'dashboard.html': "/mod-insights' in panel_visible_paths",
    'ops_center.html': "/konsol' in panel_visible_paths",
    'commands.html': "/cog-manager' in panel_visible_paths",
    'settings.html': "/guardian' in panel_visible_paths",
    'mod_settings.html': "/ladder' in panel_visible_paths",
    'anticrash.html': "/channel-settings' in panel_visible_paths",
    'antiraid.html': "/channel-settings' in panel_visible_paths",
    'pagerduty.html': "/channel-settings' in panel_visible_paths",
    'role_settings.html': "/ladder' in panel_visible_paths",
    'spravka.html': "/bot-stats' in panel_visible_paths",
    'bot_settings.html': "/backups' in panel_visible_paths",
    'users.html': "panelPathHidden('/appeals')",
    'warnings.html': "panelPathHidden('/mod-insights')",
    'guardian.html': "panelPathHidden('/channel-settings')",
}
tpl_dir = os.path.join(ROOT, 'web/templates')
for fn, needle in need.items():
    txt = open(os.path.join(tpl_dir, fn), encoding='utf-8').read()
    check(needle in txt, f'{fn} гейтит {needle.split()[0]}')

print('== 5. Индекс угроз / lockdown не светятся без /security в vis ==')
dash = open(os.path.join(tpl_dir, 'dashboard.html'), encoding='utf-8').read()
settings = open(os.path.join(tpl_dir, 'settings.html'), encoding='utf-8').read()
check("{% if '/security' in panel_visible_paths %}<span class=\"live-chip\" id=\"chipThreat\"" in dash,
      'dashboard: chipThreat только при /security в vis')
check("{% if '/security' in panel_visible_paths %}" in dash and 'id="threatScoreVal"' in dash
      and dash.find("{% if '/security' in panel_visible_paths %}") < dash.find('id="threatScoreVal"'),
      'dashboard: панель «Безопасность» / threatScoreVal за vis')
check("if (!$('threatScoreVal') && !$('chipThreat')) return" in dash,
      'dashboard: loadThreatIndex no-op без DOM')
check("{% set _sec = '/security' in panel_visible_paths %}" in settings
      and "id=\"threat-val\"" in settings
      and settings.find("{% if _sec %}") < settings.find('id="threat-val"'),
      'settings: индекс угрозы / lockdown только при /security')
check("if (!$('threat-val')) return" in settings, 'settings: loadThreat не fetch без DOM')
check("if (ld) ld.addEventListener('click', doLockdown)" in settings,
      'settings: bind lockdown только если кнопка есть')
check("var threatEl = $('ktThreat')" in kiosk and "if (threatEl)" in kiosk,
      'киоск: threat-index не fetch без #ktThreat')
check("$('ktThreat') ? (' · угроза: ' + STATE.threat) : ''" in kiosk,
      'киоск: sit title без «угроза: N», если нет виджета')

print('== 6. Пикеры режут закрытые каналы ==')
pickers = {
    'dashboard.html': 'c.type === \'text\' && !c.hidden',
    'channel_settings.html': '!c.hidden && (c.type === \'text\'',
    'announcements.html': '!channel.hidden && (channel.type === \'text\'',
    'appeals.html': '!c.hidden && (c.type === \'text\' || c.type === \'thread\')',
    'mod_tools.html': 'if (c.hidden) return',
    'logs.html': 'c && !c.hidden && c.id',
}
for fn, needle in pickers.items():
    txt = open(os.path.join(tpl_dir, fn), encoding='utf-8').read()
    check(needle in txt, f'{fn} фильтрует hidden')

print(f'\n=== PASS {PASS} / FAIL {FAIL} ===')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
