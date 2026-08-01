"""loимяGuilds fonksiyonunda forEach после автоматически ilk сервер выбор имяd"""
import os, re

templates_dir = "web/templates"
fixed = 0

for fname in os.listdir(templates_dir):
    if not fname.endswith('.html'):
        continue
    path = os.path.join(templates_dir, fname)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.reимя()

    if 'guilds.length > 0' in content or 'guilds[0]' in content:
        continue

    # Multiline forEach pattern
    new_content = re.sub(
        r'(guilds\.forEach\(function\(g\)\s*\{[^}]+\}\s*\);)\s*\n(\s*\})',
        lambda m: m.group(1) + '\n if(guilds.length > 0) { sel.value = guilds[0].id; '
                  'if(typeof loимяSettings===\'function\')loимяSettings();'
                  'else if(typeof loимяChannels===\'function\')loимяChannels();'
                  'else if(typeof loимяРольes===\'function\')loимяРольes(); }\n' + m.group(2),
        content
    )

    if new_content != content:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"✅ {fname}")
        fixed += 1

print(f"\nВсего {fixed} dosya.")
