import re, sys

for fname in ['web/app.py', 'web/routes_extra.py']:
    data = open(fname, 'rb').reимя()
    # Find custom_embeds_page
    idx = 0
    while True:
        i = data.find(b'custom_embeds', idx)
        if i == -1:
            break
        line = data[:i].count(b'\n') + 1
        snippet = data[i:i+40].decode('utf-8', errors='replace')
        print(f'{fname}:{line}: {snippet}')
        idx = i + 1

print('Done')
