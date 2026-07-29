import os, glob

total = 0
details = []
for f in sorted(glob.glob('cogs/*.py')):
    src = open(f, encoding='utf-8-sig').read()
    cnt = src.count('@app_commands.command(')
    if cnt > 0:
        details.append((cnt, os.path.basename(f)))
        total += cnt

for cnt, name in sorted(details, reverse=True):
    print(f'{cnt:3d}  {name}')
print(f'\nTOPLAM: {total}')
