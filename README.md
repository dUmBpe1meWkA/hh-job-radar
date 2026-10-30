# HH Job Radar

Telegram-бот для поиска подходящих вакансий на hh.ru через официальный HeadHunter API.

Что умеет:

- ищет свежие вакансии по профилям: ИБ, SOC, Linux, junior, стажировка, Python, DevOps;
- фильтрует вакансии под профиль начинающего ИБ-специалиста;
- считает рейтинг 0–100;
- присылает подходящие вакансии в Telegram;
- показывает причину, почему вакансия подходит;
- генерирует сопроводительное письмо;
- умеет отправлять отклик прямо из Telegram через HH OAuth API.

## Важно

Отклик из Telegram работает только после OAuth-авторизации hh и указания ID резюме.

Через API нельзя откликнуться на вакансии с обязательным тестом. В таком случае бот даст ссылку на hh, и отклик нужно отправить вручную.

## 1. Создать Telegram-бота

1. Открой `@BotFather`.
2. Создай бота командой `/newbot`.
3. Сохрани `TELEGRAM_BOT_TOKEN`.
4. Узнай свой `TELEGRAM_CHAT_ID`, например через `@userinfobot`.

## 2. Зарегистрировать приложение HH

1. Открой кабинет разработчика hh: `https://dev.hh.ru/admin`.
2. Создай приложение.
3. Укажи Redirect URI, например:

```text
https://job.your-domain.ru/hh/callback
```

4. Сохрани `HH_CLIENT_ID` и `HH_CLIENT_SECRET`.

## 3. Настроить сервер

Пример для Caddy:

```caddyfile
job.your-domain.ru {
    reverse_proxy 127.0.0.1:8080
}
```

В `docker-compose.yml` порт уже проброшен только на localhost:

```yaml
ports:
  - "127.0.0.1:8080:8080"
```

## 4. Заполнить .env

```bash
cp .env.example .env
nano .env
```

Минимально нужно заполнить:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
HH_USER_AGENT=hh-job-radar/1.0 (your_email@example.com)
HH_CLIENT_ID=...
HH_CLIENT_SECRET=...
HH_REDIRECT_URI=https://job.your-domain.ru/hh/callback
HH_RESUME_ID=...
```

`HH_RESUME_ID` можно не указывать сразу, а потом задать командой в Telegram:

```text
/set_resume <id_резюме>
```

## 5. Запуск через Docker Compose

```bash
docker compose up -d --build
```

Логи:

```bash
docker compose logs -f
```

Проверка callback-сервера:

```bash
curl http://127.0.0.1:8080/health
```

## 6. Подключить HH OAuth

В Telegram напиши боту:

```text
/auth
```

Бот пришлёт ссылку. Открой её, войди в hh, разреши доступ. После редиректа увидишь сообщение:

```text
HH OAuth подключен. Можно вернуться в Telegram и выполнить /status.
```

Проверь:

```text
/status
```

## 7. Найти вакансии вручную

```text
/scan
```

Бот пришлёт карточки с кнопками:

- `✅ Откликнуться` — отправить отклик через API;
- `📝 Письмо` — показать текст сопроводительного письма;
- `🌐 Открыть HH` — открыть вакансию вручную;
- `🚫 Скрыть` — больше не показывать вакансию;
- `☑️ Откликнулся вручную` — отметить, что ты уже откликнулся.

## Настройки поиска

В `.env` можно менять:

```env
AREA=1
MIN_SCORE=65
SCAN_INTERVAL_MINUTES=180
MAX_PAGES_PER_QUERY=2
PER_PAGE=20
PUBLICATION_PERIOD_DAYS=3
```

`AREA=1` — Москва.

`MIN_SCORE=65` — минимальный рейтинг вакансии для отправки в Telegram.

`SCAN_INTERVAL_MINUTES=180` — проверять каждые 3 часа.

## Безопасность

- Не публикуй `.env` в GitHub.
- Не давай никому `HH_CLIENT_SECRET`, `TELEGRAM_BOT_TOKEN`, OAuth-токены и базу `data/job_radar.sqlite3`.
- Лучше держать callback за HTTPS reverse proxy.
- Если токены утекли, перевыпусти Telegram-токен и отзови доступ приложения hh.
