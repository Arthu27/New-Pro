# Музыка в голосовом канале Discord (Embedded App / Activity)

Встроенная музыкальная панель, которая открывается внутри голосового канала
как «Активность» (как YouTube Together / Watch Together). Она управляет тем же
плеером бота, что и веб-панель `/music` и команды бота.

## Как это устроено

- **Фронтенд** — `web/static/activity/music/` (`index.html`, `app.js`,
  `style.css`) + вендореный SDK `web/static/activity/vendor/sdk.global.js`
  (`@discord/embedded-app-sdk`, собран в один файл esbuild'ом — без CDN).
- **Бэкенд** — `web/routes/music_activity.py`:
  - `GET /api/activity/music/config` — client_id и redirect_uri для фронтенда;
  - `POST /api/activity/music/token` — обмен OAuth-кода на access_token;
  - `GET /api/activity/music/state` — состояние плеера сервера;
  - `POST /api/activity/music/control` — pause/resume/skip/shuffle/clear/
    volume/leave (та же логика, что `/api/music/control`).

## Шаг 1. Приложение в Discord Developer Portal

1. Зайди на https://discord.com/developers/applications и создай приложение
   (или открой уже существующее приложение бота).
2. Слева выбери **«Activities»** (Embedded App SDK / Activities).
   Если раздела нет — включи его кнопкой **Enable** на вкладке Activities.
3. В поле **Target URL** укажи адрес страницы панели, например:
   `https://<ваш-домен>/static/activity/music/index.html`
   (замени `<ваш-домен>` на реальный публичный HTTPS-адрес панели).

> Страница должна быть доступна по **HTTPS** и публично (Discord грузит её в
> iframe). Для локальной разработки подойдёт туннель (Cloudflare Tunnel,
> ngrok и т.п.), проксирующий порт панели (по умолчанию 5001).

## Шаг 2. OAuth2

1. В том же приложении открой **«OAuth2»**.
2. В **Redirects** добавь:
   `https://<ваш-домен>/api/activity/music/token`
3. На вкладке **«General Information»** скопируй **CLIENT ID** и
   **CLIENT SECRET**.

## Шаг 3. Настройка `.env`

```ini
ACTIVITY_CLIENT_ID=<CLIENT_ID>
ACTIVITY_CLIENT_SECRET=<CLIENT_SECRET>
ACTIVITY_REDIRECT_URI=https://<ваш-домен>/api/activity/music/token
```

Перезапусти панель.

## Шаг 4. Открыть активность в войсе

1. Убедись, что бот запущен с музыкой. По умолчанию (полный режим,
   все флаги в `0`) музыка уже работает — ничего менять не надо. Если у
   тебя лёгкий профиль, музыку вернёт **`BOT_SLIM=1`** (модерация +
   тикеты + музыка) или точечно `EXTRA_COGS=music_cog,voice_commands,voice_tracker`.
   Не используй `MOD_ONLY=1`/`BOT_CORE=1` — они музыку выключают.
2. Зайди в голосовой канал, нажми на иконку **«Ракета» / Активности**
   (Activities) и выбери своё приложение.
3. Откроется панель: текущий трек, пауза/пропуск, очередь, громкость,
   перемешать/очистить/отключить бота.

## Права

Управление панелью (пауза, пропуск, громкость и т.д.) доступно любому
участнику сервера, у которого прошла OAuth-проверка. Если нужно ограничить
(например, только модераторам) — добавь проверку роли в
`web/routes/music_activity.py` (функции `_activity_user`/`activity_music_control`).

## Примечания

- SDK вендорен локально (CSP панели без внешних CDN сохраняется).
- Страница активности — единственная, которой разрешено встраивание в Discord
  (`frame-ancestors https://discord.com …`); остальная панель по-прежнему
  защищена от кликджекинга.
- Демо-предпросмотр: при `DEMO_MODE=1` эндпоинты активности отвечают
  демо-плейлистом без реального Discord.
