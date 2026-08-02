import re

for fname in ['web/app.py', 'web/routes_extra.py']:
    content = open(fname, encoding='utf-8').read()
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        if 'custom' in line.lower() and ('route' in line or 'def ' in line):
            print(f'{fname}:{i}: {line.strip()}')
