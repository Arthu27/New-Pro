import os, re

GUILD_ID = '1384282749317152878'
TEMPLATES_DIR = 'web/templates'

# Her dosyada kalan eski loadGuilds kalıntılarını clear
# Pattern: loadGuilds fonksiyonu içinde kalan eski API çağrısı artıkları

changed = []
for fname in os.listdir(TEMPLATES_DIR):
    if not fname.endswith('.html'):
        continue
    fpath = os.path.join(TEMPLATES_DIR, fname)
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content

    # selectedGuild = null -> selectedGuild = 'GUILD_ID'
    content = re.sub(
        r"var selectedGuild\s*=\s*null;",
        f"var selectedGuild = '{GUILD_ID}';",
        content
    )

    # Kalan eski loadGuilds bloklarını (API çağrısı içerenler) clear
    # Bunlar script'in ürettiği ama hâlâ eski satırlar içeren bloklar
    # Pattern: loadGuilds fonksiyonu içinde });  if(guilds... gibi artıklar
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
    print(f'  {f}')
