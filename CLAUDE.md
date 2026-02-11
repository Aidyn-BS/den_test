# CLAUDE.md — Инструкции для работы с проектом

## Обзор

Бот стоматологической клиники «Улыбка». Пациенты записываются на приём, админы управляют расписанием — через WhatsApp (GREEN-API) и Telegram (python-telegram-bot).

**Стек:** Python 3.11, Flask, PostgreSQL, OpenRouter API (GPT-4o-mini), GREEN-API, python-telegram-bot, Google Calendar, Google Sheets, APScheduler, Groq Whisper

## Архитектура

```
WhatsApp / Telegram сообщение
           ↓
   Transport Layer (transports/)
   ├─ whatsapp_transport.py  ← GREEN-API webhook
   └─ telegram_transport.py  ← python-telegram-bot polling
           ↓
   Нормализованное сообщение: {phone, text, source}
           ↓
   main.py (дедупликация, rate-limit, per-phone lock)
           ↓
   AI Agent (1 LLM-вызов с function calling)
   ├─ agents/prompts.py     → системные промпты
   ├─ agents/tools.py       → определения tools
   ├─ agents/functions.py   → execute_function, _call_function
   ├─ agents/validator.py   → валидация перед мутациями (без LLM)
   └─ agents/notifications.py → уведомления админам
           ↓
   Transport Layer → ответ пользователю
```

**Принцип:** 1 LLM-вызов на сообщение. Function calling сам определяет intent и выбирает функции. LLM сам формирует человеческий ответ. Дополнительные LLM-вызовы не нужны.

## Структура файлов

```
project/
├── agents/                     # AI-логика (разбита из ai_agent.py)
│   ├── __init__.py             # экспорт process_message()
│   ├── agent.py                # главный цикл: LLM + function calling loop
│   ├── prompts.py              # build_system_prompt(), _append_client_context()
│   ├── tools.py                # TOOLS_CLIENT, TOOLS_ADMIN
│   ├── functions.py            # execute_function(), _call_function()
│   ├── validator.py            # валидация данных перед мутациями (без LLM)
│   └── notifications.py        # _send_to_all_admins(), уведомления
│
├── transports/                 # Абстракция мессенджеров
│   ├── __init__.py             # get_transport(source)
│   ├── base.py                 # BaseTransport (ABC)
│   ├── whatsapp_transport.py   # обёртка над whatsapp.py
│   └── telegram_transport.py   # python-telegram-bot
│
├── main.py                     # Flask + webhook + запуск Telegram polling
├── db.py                       # НЕ ТРОГАТЬ — PostgreSQL
├── telegram_db.py              # DB-функции для Telegram (telegram_users)
├── config.py                   # НЕ ТРОГАТЬ — конфигурация
├── whatsapp.py                 # НЕ ТРОГАТЬ — GREEN-API клиент
├── google_calendar.py          # НЕ ТРОГАТЬ
├── google_sheets.py            # НЕ ТРОГАТЬ
├── google_config.py            # НЕ ТРОГАТЬ
├── transcribe.py               # НЕ ТРОГАТЬ — Groq Whisper
├── scheduler.py                # минимальные изменения (импорт notifications)
├── schema.sql                  # + таблица telegram_users
└── CLAUDE.md                   # этот файл
```

## Модули agents/ — что где

### agents/agent.py — главный AI-цикл
- `process_message(phone, text, source="whatsapp") → str`
- Загружает контекст: `db.get_client_context(phone)`
- Собирает промпт: `prompts.build_system_prompt()` + `prompts.append_client_context()`
- Выбирает tools: `TOOLS_ADMIN if admin else TOOLS_CLIENT`
- Цикл function calling (max 5 итераций)
- Сохраняет в chat_history
- Retry 3 раза при ошибке API

### agents/prompts.py — все промпты
- `build_system_prompt(phone, is_admin) → str` — извлечено из ai_agent.py:30-155
- `append_client_context(prompt, context, phone, is_admin) → str` — извлечено из ai_agent.py:158-245
- Промпты остаются ТОЧНО как сейчас — не менять формулировки

### agents/tools.py — определения function calling
- `TOOLS_CLIENT` — 11 функций для пациентов (извлечено из ai_agent.py:252-450)
- `TOOLS_ADMIN` — CLIENT + 8 админских (извлечено из ai_agent.py:450-547)

### agents/functions.py — выполнение функций
- `execute_function(name, args, phone, is_admin) → str` — из ai_agent.py:554-561
- `_call_function(name, args, phone, is_admin) → dict` — из ai_agent.py:564-1098
- Перед мутациями вызывает `validator.validate_*()`
- Google Calendar/Sheets интеграция остаётся здесь

### agents/validator.py — централизованная валидация (БЕЗ LLM)
Извлечь из функций в agents/functions.py все проверки в отдельные методы:
- `validate_appointment_time(date, time, timezone) → ValidationResult`
  - Дата не в прошлом
  - Не дальше 60 дней
  - Время на :00 или :30
  - Округление к ближайшему слоту
- `validate_cancellation(appointment, timezone) → ValidationResult`
  - Минимум за 2 часа до приёма
- `validate_reschedule(appointment, new_date, new_time, timezone) → ValidationResult`
  - Те же правила что для создания + проверка существующей записи
- `find_doctor_by_name(name, doctors) → doctor | None`
- `find_service_by_name(name, services) → service | None`

**ValidationResult:** `{"valid": bool, "error": str | None, "corrected_time": str | None}`

### agents/notifications.py — все уведомления
- `send_to_all_admins(message)` — из ai_agent.py + scheduler.py (общий код)
- `notify_admin_new_appointment(appt)`
- `notify_admin_cancellation(appt, reason)`
- `notify_admin_reschedule(appt_id, new_date, new_time, old_date, old_time)`
- `notify_patient_cancellation(appt)`
- `notify_patient_reschedule(appt_id, new_date, new_time, old_date, old_time)`
- `notify_admin_api_down()`
- `notify_emergency(phone, message)`

## Transport Layer

### transports/base.py
```python
from abc import ABC, abstractmethod

class BaseTransport(ABC):
    @abstractmethod
    def send_message(self, phone: str, text: str) -> bool: ...

    @abstractmethod
    def send_to_chat(self, chat_id, text: str) -> bool: ...
```

### transports/whatsapp_transport.py
- Обёртка над существующим `whatsapp.py` (не модифицировать whatsapp.py)
- `send_message(phone, text)` → вызывает `whatsapp.get_provider().send_message()`

### transports/telegram_transport.py
- `python-telegram-bot` (async, polling mode)
- Маппинг: Telegram chat_id ↔ phone через таблицу `telegram_users`
- /start — просит телефон для привязки
- Все текстовые сообщения → `agents.process_message(phone, text, "telegram")`
- Ответ обратно в Telegram чат

### Новая таблица в schema.sql
```sql
CREATE TABLE IF NOT EXISTS telegram_users (
    telegram_chat_id BIGINT PRIMARY KEY,
    phone VARCHAR(20) REFERENCES clients(phone),
    username VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Ограничения по ролям

### Patient
| Действие | Ограничение |
|----------|-------------|
| get_services, get_doctors, get_clinic_info, get_free_slots | Все данные |
| get_my_appointments | **Только свои** (WHERE phone = ?) |
| create_appointment, create_combo_appointment | Только для себя |
| cancel_appointment, reschedule_appointment | **Только свои**, за 2+ часа |
| save_client_name | Только своё имя |
| notify_emergency | Уведомление админу |

### Admin
| Действие | Ограничение |
|----------|-------------|
| Все функции пациента | Без ограничений по phone |
| get_today_schedule, get_week_report, get_month_report | Все записи |
| set_doctor_absence, block/unblock_patient | Любые данные |
| record_payment, mark_no_show, schedule_follow_up | Любая запись |
| export_to_sheets | Полный экспорт |

Роль определяется в `db.get_client_context()` → `is_admin`.
Tools фильтруются: `TOOLS_ADMIN if admin else TOOLS_CLIENT`.
Админские функции в functions.py проверяют `is_admin` перед выполнением.

## Правила

### Неприкосновенные файлы
`db.py`, `whatsapp.py`, `google_calendar.py`, `google_sheets.py`, `google_config.py`, `transcribe.py`, `config.py` — НЕ модифицировать.

### Сохранение багфиксов
- Все бизнес-правила из ai_agent.py → `agents/validator.py` (строки 605-628: слоты, 60 дней, 2ч отмена)
- Row-level locking → остаётся в `db.py`
- Дедупликация, rate-limit, per-phone locks → остаются в `main.py`
- Retry логика OpenRouter (3 попытки) → остаётся в `agents/agent.py`
- Context overflow protection (MAX_CONTEXT_CHARS=16000) → остаётся в `agents/agent.py`

### Инкрементальная миграция
1. Создать `agents/` — перенести код из `ai_agent.py` без изменений логики
2. Создать `transports/` — обёртка над whatsapp.py + новый Telegram
3. В `main.py` сменить import: `from agents import process_message`
4. Тестировать каждый модуль
5. Старый `ai_agent.py` переименовать в `ai_agent.py.bak` (не удалять сразу)
