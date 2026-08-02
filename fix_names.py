import os, re

files = [
    'cogs/embed_utils.py', 'cogs/moderation.py', 'cogs/warnings.py',
    'cogs/ticket.py', 'cogs/staff_apply.py', 'cogs/verification.py',
    'cogs/giveaway.py', 'cogs/fun.py', 'cogs/minigames.py',
    'cogs/economy_cmds.py', 'cogs/invite_tracker.py', 'cogs/automod.py',
    'cogs/logs.py', 'cogs/advanced_mod.py', 'cogs/duty.py',
    'cogs/birthday.py', 'cogs/events.py', 'cogs/stats.py',
    'cogs/health.py', 'cogs/utility.py', 'cogs/info_tools.py',
]

replacements = [
    ('Aether Bot —', 'Aether Bot —'),
    ('Aether Bot', 'Aether'),
    ('**Aether** сервер **постоянный как** uzaklaшtыrыldыnыz.', '**{guild.name}** сервер **постоянный как** uzaklaшtыrыldыnыz.'),
    ('**Aether** сервер выгнанnыz.', '**{guild.name}** сервер выгнанnыz.'),
    ('**Aether** сервер belirtilen длительность bиграca', '**{guild.name}** сервер belirtilen длительность bиграca'),
    ('**Aether** сервер susturmanыz **удалено**.', '**{guild.name}** сервер susturmanыz **удалено**.'),
    ('**Aether** сервер сервер правил нарушение ettiгiniz', '**{guild.name}** сервер сервер правил нарушение ettiгiniz'),
    ('**Aether** сервер banыnыz **удалено**.', '**{guild.name}** сервер banыnыz **удалено**.'),
    ('✦ Aether ПОДДЕРЖКА СИСТЕМА ✦', '✦ Aether ПОДДЕРЖКА СИСТЕМА ✦'),
    ('Aether Ekonomi •', 'Aether Ekonomi •'),
    ('Aether Ekonomi', 'Aether Ekonomi'),
    ('Aether Moderasyon •', 'Aether Moderasyon •'),
    ('Aether Moderasyon', 'Aether Moderasyon'),
    ('Aether Поддержка Система •', 'Aether Поддержка •'),
    ('Aether Поддержка Система', 'Aether Поддержка'),
    ('Aether Поддержка •', 'Aether Поддержка •'),
    ('Aether Поддержка', 'Aether Поддержка'),
    ('Aether Администратор Система •', 'Aether Администратор •'),
    ('Aether Администратор Система', 'Aether Администратор'),
    ('Aether Администратор', 'Aether Администратор'),
    ('Aether Giveaway Система', 'Aether Giveaway'),
    ('Aether Лог Система', 'Aether Лог'),
    ('Aether Panel •', 'Aether Panel •'),
    ('Aether Panel', 'Aether Panel'),
    ("f'Aether •", "f'Aether •"),
    ('"Aether •', '"Aether •'),
    ("'Aether •", "'Aether •"),
    ('Aether • ', 'Aether • '),
    ('Aether\n', 'Aether\n'),
    ('Aether"', 'Aether"'),
    ("Aether'", "Aether'"),
]

for filepath in files:
    if not os.path.exists(filepath):
        continue
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content
    for old, new in replacements:
        content = content.replace(old, new)
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'Updated: {filepath}')
    else:
        print(f'No change: {filepath}')

print('Done.')
