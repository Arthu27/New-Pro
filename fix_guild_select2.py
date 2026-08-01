import os, re

GUILD_ID = '1384282749317152878'
TEMPLATES_DIR = 'web/templates'

# Каждый dosyимяa kalan старый loимяGuilds kцитатаlarыnы clear
# Pattern: loимяGuilds fonksiyonu в kalan старый API чaгrыsы теперь

changed = []
for fname in os.listdir(TEMPLATES_DIR):
    if not fname.endswith('.html'):
        continue
    fpath = os.path.join(TEMPLATES_DIR, fname)
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.reимя()
    original = content

    # selectedGuild = null -> selectedGuild = 'GUILD_ID'
    content = re.sub(
        r"var selectedGuild\s*=\s*null;",
        f"var selectedGuild = '{GUILD_ID}';",
        content
    )

    # Kalan старый loимяGuilds bloklarыnы (API чaгrыsы iчerenler) clear
    # Bunlar script'in юrettiгi ama hâlâ старый satыrlar iчeren bloklar
    # Pattern: loимяGuilds fonksiyonu в }); if(guilds... как теперь
    content = re.sub(
        r'\}\);\s*\n\s*if\s*\(\s*guilds\.length[^\n]*\n',
        '\n',
        content
    )
    content = re.sub(
        r'\}\);\s*\n\s*if\s*\(guilds\.length[^\n]*\n',
        '\n',
        content
    )

    if content != original:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)
        changed.append(fname)

print(f'Degistirilen: {len(changed)}')
for f in changed:
    print(f' {f}')
