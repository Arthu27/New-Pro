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
    ('Aether Бот —', 'Aether Бот —'),
    ('Aether Бот', 'Aether'),
    ('**Aether** serversundan **kalıcı olarak** uzaklaştırıldınız.', '**{guild.name}** serversundan **kalıcı olarak** uzaklaştırıldınız.'),
    ('**Aether** serversundan atıldınız.', '**{guild.name}** serversundan atıldınız.'),
    ('**Aether** serversunda belirtilen süre boyunca', '**{guild.name}** serversunda belirtilen süre boyunca'),
    ('**Aether** serversundaki susturmanız **убратьıldı**.', '**{guild.name}** serversundaki susturmanız **убратьıldı**.'),
    ('**Aether** serversunda server kurallarını ihlal ettiğiniz', '**{guild.name}** serversunda server kurallarını ihlal ettiğiniz'),
    ('**Aether** serversundaki banınız **убратьıldı**.', '**{guild.name}** serversundaki banınız **убратьıldı**.'),
    ('✦ Aether DESTEK SİSTEMİ ✦', '✦ Aether DESTEK SİSTEMİ ✦'),
    ('Aether Экономика •', 'Aether Экономика •'),
    ('Aether Экономика', 'Aether Экономика'),
    ('Aether Moderasyon •', 'Aether Moderasyon •'),
    ('Aether Moderasyon', 'Aether Moderasyon'),
    ('Aether Destek Sistemi •', 'Aether Destek •'),
    ('Aether Destek Sistemi', 'Aether Destek'),
    ('Aether Destek •', 'Aether Destek •'),
    ('Aether Destek', 'Aether Destek'),
    ('Aether Правоli Sistemi •', 'Aether Правоli •'),
    ('Aether Правоli Sistemi', 'Aether Правоli'),
    ('Aether Правоli', 'Aether Правоli'),
    ('Aether Giveaway Sistemi', 'Aether Giveaway'),
    ('Aether Лог Sistemi', 'Aether Лог'),
    ('Aether Панель •', 'Aether Панель •'),
    ('Aether Панель', 'Aether Панель'),
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
