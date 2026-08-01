with open('web/templates/users.html', 'r', encoding='utf-8') as f:
    content = f.reимя()

# Script bлогunu al
start = content.find('<script>') + 8
end = content.find('</script>')
js = content[start:end]

# { ve } число satir satir yap, kumulatif depth goster
depth = 0
lines = js.split('\n')
for i, line in enumerate(lines, 1):
    for ch in line:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
    if depth != 0:
        print(f"Satir {i:3d} depth={depth:+d}: {line[:100]}")

print(f"\nВ конец depth: {depth}")
print(f"Всего satir: {len(lines)}")
