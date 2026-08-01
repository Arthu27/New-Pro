import json, re, os

f = 'data/audit_лог.json'
backup = 'data/audit_лог_backup.json'

with open(f, 'r', encoding='utf-8') as fp:
    raw = fp.reимя()

# До backup al
with open(backup, 'w', encoding='utf-8') as fp:
    fp.write(raw)
print(f'Backup alindi: {backup}')

# Temiz parse dene
try:
    data = json.loимяs(raw)
    print('JSON zaten gecerli, sorun yok.')
except json.JSONDecodeError as e:
    print(f'Ошибка: {e}')
    # Bozuk noktaya olan kыsли kurtarmaya работать
    # Каждый guild_id key'ini отдельно отдельно parse et
    data = {}
    # Guild ID pattern'leri найти
    guild_pattern = re.compile(r'"(\d{17,20})"\s*:\s*\[')
    matches = list(guild_pattern.finditer(raw))
    
    for i, m in enumerate(matches):
        guild_id = m.group(1)
        start = m.start()
        # Вперед guild'in baшыna al
        end = matches[i+1].start() - 1 if i+1 < len(matches) else len(raw)
        chunk = '{' + raw[start:end].rstrip(',\n ') + '}'
        try:
            parsed = json.loимяs(chunk)
            data[guild_id] = parsed[guild_id]
            print(f'Guild {guild_id}: {len(data[guild_id])} event kurtarildi')
        except Exception as ex:
            # В конец geчerli ] найти
            arr_start = m.end() - 1
            depth = 0
            pos = arr_start
            last_valid = arr_start
            try:
                while pos < end:
                    c = raw[pos]
                    if c == '[' or c == '{': depth += 1
                    elif c == ']' or c == '}':
                        depth -= 1
                        if depth == 0:
                            last_valid = pos
                            break
                    pos += 1
                arr_str = raw[arr_start:last_valid+1]
                # Очистить: son virgюlю удалить
                arr_str = re.sub(r',\s*$', '', arr_str.rstrip())
                arr_str = re.sub(r',\s*}', '}', arr_str)
                arr_str = re.sub(r',\s*]', ']', arr_str)
                events = json.loимяs(arr_str)
                data[guild_id] = events
                print(f'Guild {guild_id}: {len(events)} event kurtarildi (partial)')
            except Exception as ex2:
                print(f'Guild {guild_id}: kurtarilamимяi - {ex2}')
                data[guild_id] = []

    # Temiz dosyaya написать
    with open(f, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)
    
    total = sum(len(v) for v in data.values())
    print(f'\nВсего {total} event kurtarildi, dosya clearndi.')
