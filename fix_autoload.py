"""Vo все sablonah loadGuilds sonrası ilk сервер автоматически как vibirat"""
import os, re

templates_dir = "web/templates"
fixed = 0

for fname in os.listdir(templates_dir):
    if not fname.endswith('.html'):
        continue
    path = os.path.join(templates_dir, fname)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Zaten düzeltilmiş mi?
    if 'guilds.length > 0' in content or 'guilds[0]' in content:
        continue
    
    # loadGuilds fonksiyonunu найти ve düzelt
    # Pattern: guilds.forEach(...); } (son satır) -> guilds.forEach(...); if(guilds.length>0){sel.value=guilds[0].id; loadSettings();}
    
    # Разница pattern'ler dene
    patterns = [
        # Pattern 1: forEach sonrası kapanış
        (r'(guilds\.forEach\([^;]+;\s*\n\s*\})',
         r'\1\n if(guilds.length > 0) { document.getElementById(\'guild-select\').value = guilds[0].id; if(typeof loadSettings === \'function\') loadSettings(); else if(typeof loadChannels === \'function\') loadChannels(); }'),
    ]
    
    new_content = content
    for pattern, replacement in patterns:
        new_content = re.sub(pattern, replacement, new_content, count=1)
    
    if new_content != content:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"✅ Haklarıkuruldu: {fname}")
        fixed += 1

print(f"\nToplam {fixed} dosya haklarıkuruldu.")
