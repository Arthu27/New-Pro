import os, re

GUILD_ID = '1384282749317152878'
TEMPLATES_DIR = 'web/templates'

# loadGuilds fonksiyonunu sabit ID с изменить
# Pattern: async function loadGuilds() { ... } bloğunu найти ve изменить

REPLACEMENT = f"""async function loadGuilds() {{
 // Sabit сервер ID
 var gid = '{GUILD_ID}';
 if (typeof selectedGuild !== 'undefined') selectedGuild = gid;
 if (document.getElementById('guild-select')) document.getElementById('guild-select').value = gid;
 if (document.getElementById('guild-sel')) document.getElementById('guild-sel').value = gid;
 if (document.getElementById('guildSelect')) document.getElementById('guildSelect').value = gid;
 if (typeof loadData === 'function') {{ loadData(gid); return; }}
 if (typeof loadAll === 'function') {{ loadAll(gid); return; }}
 if (typeof loadRoles === 'function') {{ loadRoles(gid); return; }}
 if (typeof loadChannels === 'function') {{ loadChannels(gid); return; }}
 if (typeof loadMembers === 'function') {{ loadMembers(gid); return; }}
 if (typeof loadHistory === 'function') {{ loadHistory(gid); return; }}
 if (typeof loadLogs === 'function') {{ loadLogs(gid); return; }}
 if (typeof loadVoiceStats === 'function') {{ loadVoiceStats(gid); return; }}
 if (typeof loadSettings === 'function') {{ loadSettings(gid); return; }}
 if (typeof loadGiveaways === 'function') {{ loadGiveaways(gid); return; }}
 if (typeof loadPolls === 'function') {{ loadPolls(gid); return; }}
 if (typeof loadEconomy === 'function') {{ loadEconomy(gid); return; }}
 if (typeof loadSuggestions === 'function') {{ loadSuggestions(gid); return; }}
 if (typeof loadInvites === 'function') {{ loadInvites(gid); return; }}
 if (typeof loadHealth === 'function') {{ loadHealth(gid); return; }}
 if (typeof loadAnalytics === 'function') {{ loadAnalytics(gid); return; }}
}}"""
# Сервер выбор dropdown'larını gizle
HIDE_SELECT = [
    r'<select[^>]*id=["\']guild-select["\'][^>]*>.*?</select>',
    r'<select[^>]*id=["\']guild-sel["\'][^>]*>.*?</select>',
    r'<select[^>]*id=["\']guildSelect["\'][^>]*>.*?</select>',
]

changed = []
for fname in os.listdir(TEMPLATES_DIR):
    if not fname.endswith('.html'):
        continue
    fpath = os.path.join(TEMPLATES_DIR, fname)
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # loadGuilds fonksiyonunu найти ve изменить (только geri загрузить API çağrısı yapanları)
    # Pattern: async function loadGuilds() { ... /api/guilds ... }
    pattern = re.compile(
        r'async function loadGuilds\(\)\s*\{[^}]*?/api/guilds[^}]*?\}',
        re.DOTALL
    )
    
    if pattern.search(content):
        content = pattern.sub(REPLACEMENT, content)
    
    # Сервер выбор dropdown'larını gizle (display:none add)
    for pat in HIDE_SELECT:
        content = re.sub(
            pat,
            lambda m: m.group(0).replace('<select', '<select style="display:none"'),
            content,
            flags=re.DOTALL | re.IGNORECASE
        )
    
    if content != original:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)
        changed.append(fname)

print(f'Degistirilen dosyalar ({len(changed)}):')
for f in changed:
    print(f' - {f}')
