import json
d = json.load(open('data/members.json', encoding='utf-8'))
print(f"{'Discord ID':<22} {'Имя':<25} {'Паrole':<20} {'Роль'}")
print("-" * 80)
for k, v in d.items():
    print(f"{k:<22} {v.get('display_name','?'):<25} {v.get('password','?'):<20} {v.get('role','uye')}")
