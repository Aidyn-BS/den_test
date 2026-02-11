# Деплой на Amvera

## Шаг 1: Подготовка Google Credentials

Файл `google_credentials.json` нельзя коммитить в git. Вместо этого передаём его через переменную окружения в base64.

**PowerShell (Windows):**
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("google_credentials.json"))
```

**Linux/Mac:**
```bash
base64 -w 0 google_credentials.json
```

Скопируйте результат — это значение для `GOOGLE_CREDENTIALS_B64`.

## Шаг 2: Создание PostgreSQL в Amvera

1. В панели Amvera создайте PostgreSQL сервис
2. Запишите: Host, Port, User, Password
3. Подключитесь и выполните `schema.sql`:
   ```bash
   psql -h <host> -U postgres -d dental_clinic -f schema.sql
   ```

## Шаг 3: Загрузка на GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/ваш-логин/dental-bot.git
git push -u origin main
```

## Шаг 4: Создание проекта в Amvera

1. Создайте проект (тип: **Docker**)
2. Подключите GitHub репозиторий или используйте Amvera Git:
   ```bash
   git remote add amvera https://git.amvera.ru/ваш-логин/dental-bot.git
   git push amvera main
   ```

## Шаг 5: Переменные окружения

В панели Amvera → Проект → Переменные:

```
# AI
OPENROUTER_API_KEY=sk-or-...
AI_MODEL=openai/gpt-4o-mini

# WhatsApp (GREEN-API)
GREEN_API_INSTANCE_ID=...
GREEN_API_TOKEN=...

# PostgreSQL (из шага 2)
DB_HOST=...
DB_PORT=5432
DB_NAME=dental_clinic
DB_USER=postgres
DB_PASSWORD=...

# Google (credentials как base64 — см. Шаг 1)
GOOGLE_CREDENTIALS_B64=...
GOOGLE_CALENDAR_ID=...@group.calendar.google.com
GOOGLE_SHEETS_ID=...

# Telegram
TELEGRAM_BOT_TOKEN=...

# Клиника
ADMIN_PHONE=+77072080253
CLINIC_NAME=Стоматология «Улыбка»
CLINIC_ADDRESS=ул. Абая 100, Алматы
CLINIC_PHONE=+77074519193
TIMEZONE=Asia/Almaty

# Опционально
GROQ_API_KEY=... (для голосовых сообщений)
```

## Шаг 6: Webhook GREEN-API

После деплоя установите Webhook URL в green-api.com:
```
https://ваш-проект.amvera.io/webhook
```

## Проверка

1. Health check: `https://ваш-проект.amvera.io/health`
2. Логи: панель Amvera → Проект → Логи
3. Отправьте сообщение боту в WhatsApp
4. Отправьте /start боту в Telegram

## Обновление

```bash
git add .
git commit -m "Update"
git push amvera main
```

Amvera автоматически пересоберёт и перезапустит.
