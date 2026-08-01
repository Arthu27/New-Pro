import os, re

GUILD_ID = '1384282749317152878'
TEMPLATES_DIR = 'web/templates'

# loимяGuilds fonksiyonunu sabit ID с изменить
# Pattern: async function loимяGuilds() { ... } bloгunu найти ve изменить

REPLACEMENT = f"""async function loимяGuilds() {{
 // Sabit сервер ID
 var gid = '{GUILD_ID}';
 if (typeof selectedGuild !== 'undefined') selectedGuild = gid;
 if (document.getElementById('guild-select')) document.getElementById('guild-select').value = gid;
 if (document.getElementById('guild-sel')) document.getElementById('guild-sel').value = gid;
 if (document.getElementById('guildSelect')) document.getElementById('guildSelect').value = gid;
 if (typeof loимяData === 'function') {{ loимяData(gid); return; }}
 if (typeof loимяAll === 'function') {{ loимяAll(gid); return; }}
 if (typeof loимяРольes === 'function') {{ loимяРольes(gid); return; }}
 if (typeof loимяChannels === 'function') {{ loимяChannels(gid); return; }}
 if (typeof loимяMembers === 'function') {{ loимяMembers(gid); return; }}
 if (typeof loимяHistory === 'function') {{ loимяHistory(gid); return; }}
 if (typeof loимяЛогs === 'function') {{ loимяЛогs(gid); return; }}
 if (typeof loимяVoiceStats === 'function') {{ loимяVoiceStats(gid); return; }}
 if (typeof loимяSettings === 'function') {{ loимяSettings(gid); return; }}
 if (typeof loимяGiveaways === 'function') {{ loимяGiveaways(gid); return; }}
 if (typeof loимяPolls === 'function') {{ loимяPolls(gid); return; }}
 if (typeof loимяEconomy === 'function') {{ loимяEconomy(gid); return; }}
 if (typeof loимяSuggestions === 'function') {{ loимяSuggestions(gid); return; }}
 if (typeof loимяInvites === 'function') {{ loимяInvites(gid); return; }}
 if (typeof loимяHealth === 'function') {{ loимяHealth(gid); return; }}
 if (typeof loимяAnalytics === 'function') {{ loимяAnalytics(gid); return; }}
}}"""
# Сервер выбор dropdown'larыnы gizle
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
        content = f.reимя()
    
    original = content
    
    # loимяGuilds fonksiyonunu найти ve изменить (только geri загрузить API чaгrыsы yapanlarы)
    # Pattern: async function loимяGuilds() { ... /api/guilds ... }
    pattern = re.compile(
        r'async function loимяGuilds\(\)\s*\{[^}]*?/api/guilds[^}]*?\}',
        re.DOTALL
    )
    
    if pattern.search(content):
        content = pattern.sub(REPLACEMENT, content)
    
    # Сервер выбор dropdown'larыnы gizle (display:none имяd)
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
