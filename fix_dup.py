import re, os

path = 'C:/Users/İsmininistrator/moebius-bot-main/web/routes_extra.py'

with open(path, encoding='utf-8') as f:
    content = f.read()

original_len = len(content)

# api_guild_channels endpoint'ini bul ve удалить
# Indented version (inside register_extra_routes function)
lines = content.split('\n')
new_lines = []
skip = False
skip_depth = 0
i = 0
removed_blocks = 0

while i < len(lines):
    line = lines[i]
    
    # api_guild_channels decorator'unu bul
    if "@app.route('/api/guild/<guild_id>/channels')" in line and 'def api_guild_channels' in '\n'.join(lines[i:i+5]):
        skip = True
        removed_blocks += 1
        # Bu blogu atla - return jsonify([]) satırına kadar
        while i < len(lines):
            if 'return jsonify([])' in lines[i] and skip:
                i += 1  # return satırını da atla
                skip = False
                break
            i += 1
        continue
    
    new_lines.append(line)
    i += 1

new_content = '\n'.join(new_lines)

if removed_blocks > 0:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"Duzeltildi! {removed_blocks} blok удалено. ({original_len} -> {len(new_content)} karakter)")
else:
    print("Blok не найдено, разница yontem deneniyor...")
    # Более basit: satir satir сканировать
    lines = content.split('\n')
    new_lines = []
    skip_until_empty = False
    
    for j, line in enumerate(lines):
        if "@app.route('/api/guild/<guild_id>/channels')" in line:
            skip_until_empty = True
            removed_blocks += 1
            continue
        if skip_until_empty:
            if line.strip() == '' and j > 0 and 'return jsonify' in lines[j-1]:
                skip_until_empty = False
            continue
        new_lines.append(line)
    
    if removed_blocks > 0:
        new_content = '\n'.join(new_lines)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Yontem 2 с duzeltildi! {removed_blocks} blok удалено.")
    else:
        print("Hic blok не найдено!")
        # Manuel контроль
        count = content.count("api_guild_channels")
        print(f"'api_guild_channels' gecis количество: {count}")
        count2 = content.count("/api/guild/<guild_id>/channels")
        print(f"Route gecis количество: {count2}")
