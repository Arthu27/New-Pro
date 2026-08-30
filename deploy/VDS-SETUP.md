# Бот на VDS: стабильность и автозапуск

## Почему бот «отключается со временем»

1. **Короткие переподключения — это НОРМА.** Discord сам рвёт связь
   (раз в сутки-двое), discord.py тут же переподключается сам. Теперь это
   видно в логе: `[СЕТЬ] Соединение потеряно` → `[СЕТЬ] восстановлено`.
2. **Бот лежит офлайн надолго — НЕ норма.** Значит умер сам процесс:
   нехватка памяти (OOM-killer), краш, перезагрузка VDS. Без автозапуска
   он сам не встанет — это и лечится ниже.

## Вариант 1 (просто): start.sh с авто-поднятием

`./start.sh` теперь сам поднимает бота через 5 секунд после любого падения
(внутри main.py — свой цикл переподключения к Discord с паузой 5→60 сек).
Минус: если сам `start.sh` закрыли или VDS перезагрузили — ничего не
поднимет. Поэтому для VDS рекомендуется вариант 2.

## Вариант 2 (правильно): systemd-служба

Положи бота, например, в `/opt/hakumo`, один раз запусти `./start.sh`
(создаст .venv и поставит зависимости), затем:

```bash
sudo cp deploy/hakumo.service /etc/systemd/system/hakumo.service
# открой файл и поправь WorkingDirectory под свой путь
sudo systemctl daemon-reload
sudo systemctl enable --now hakumo
```

Всё: бот стартует при загрузке VDS и поднимается через 5 секунд после
любого падения. Логи службы:

```bash
journalctl -u hakumo -f          # живой поток
journalctl -u hakumo --since today | grep -i сеть
```

## Как понять, от чего падало

```bash
# убил ли OOM-killer (нехватка RAM — самая частая причина на VDS):
dmesg -T | grep -i -E "oom|killed process"
free -h                          # сколько памяти сейчас
df -h                            # не переполнен ли диск (логи бота ротируются сами: 10МБ x 5)
```

Если OOM убивает регулярно — возьми VDS с большим RAM или включи своп:
```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## Бот не выходит в сеть на VDS (всё стартует, но «Cannot connect to host discord.com»)

При старте бот сам делает TCP-проверку `discord.com:443` и `gateway.discord.gg:443`
и пишет результат в лог:

- `[СЕТЬ] Доступ к Discord есть (...)` — сеть в порядке, проблема в токене/правах;
- `[СЕТЬ] НЕТ ДОСТУПА к Discord (...)` — сервер физически не достаёт Discord.

Быстрая проверка прямо на VDS:

```bash
# Linux:
curl -sS -o /dev/null -w '%{http_code}\n' https://discord.com/api/v10/gateway   # ждём 401
# Windows VDS (PowerShell):
Test-NetConnection discord.com -Port 443
```

Если соединения нет — Discord блокируется на уровне хостера/фаервола
(частый случай для некоторых дата-центров). Лечение:

1. открыть исходящий TCP **443** в брандмауэре VDS (`ufw allow out 443` /
   правило в Windows Firewall / у провайдера в панели);
2. если Discord заблокирован у хостера целиком — поднять на сервере VPN
   или прокси (например, WireGuard к узлу с доступом) — дискорд-шлюз
   пойдёт через него;
3. убедиться, что у VDS вообще есть интернет и верные DNS
   (`ping discord.com`, `nslookup discord.com`).

Логи старта на Windows-сервере пишутся и в файл: запускайте через
`start_bot.bat` (консоль копируется в `logs\start_console.log`), а фатальные
ошибки самого раннего старта — в `logs\fatal_start.log`.
