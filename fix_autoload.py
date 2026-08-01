"""Vo все sablonah loимяGuilds после ilk сервер автоматически как vibirat"""
import os, re

templates_dir = "web/templates"
fixed = 0

for fname in os.listdir(templates_dir):
    if not fname.endswith('.html'):
        continue
    path = os.path.join(templates_dir, fname)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.reимя()
    
    # Zaten dюzeltilmiш mi?
    if 'guilds.length > 0' in content or 'guilds[0]' in content:
        continue
    
    # loимяGuilds fonksiyonunu найти ve dюzelt
    # Pattern: guilds.forEach(...); } (son satыr) -> guilds.forEach(...); if(guilds.length>0){sel.value=guilds[0].id; loимяSettings();}
    
    # Разница pattern'ler dene
    patterns = [
        # Pattern 1: forEach после закрытие
        (r'(guilds\.forEach\([^;]+;\s*\n\s*\})',
         r'\1\n if(guilds.length > 0) { document.getElementById(\'guild-select\').value = guilds[0].id; if(typeof loимяSettings === \'function\') loимяSettings(); else if(typeof loимяChannels === \'function\') loимяChannels(); }'),
    ]
    
    new_content = content
    for pattern, replacement in patterns:
        new_content = re.sub(pattern, replacement, new_content, count=1)
    
    if new_content != content:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"✅ Haklarыkuruldu: {fname}")
        fixed += 1

print(f"\nВсего {fixed} dosya haklarыkuruldu.")
