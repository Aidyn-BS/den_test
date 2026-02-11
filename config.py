import os
from dotenv import load_dotenv

load_dotenv()

# --- OpenRouter ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
AI_MODEL = os.getenv("AI_MODEL", "openai/gpt-4o-mini")

# --- Groq (Whisper STT для голосовых сообщений) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# --- GREEN-API (WhatsApp) ---
GREEN_API_INSTANCE_ID = os.getenv("GREEN_API_INSTANCE_ID")
GREEN_API_TOKEN = os.getenv("GREEN_API_TOKEN")

# --- PostgreSQL ---
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "dental_clinic"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "password"),
}

# --- Google ---
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")
GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "google_credentials.json")

# --- Администратор ---
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "+77001234567")

# --- Клиника ---
CLINIC_NAME = os.getenv("CLINIC_NAME", "Стоматология «Улыбка»")
CLINIC_ADDRESS = os.getenv("CLINIC_ADDRESS", "ул. Абая 100, Алматы")
CLINIC_PHONE = os.getenv("CLINIC_PHONE", "+77001234567")

CLINIC_HOURS = {
    "Понедельник": "09:00–18:00",
    "Вторник":     "09:00–18:00",
    "Среда":       "09:00–18:00",
    "Четверг":     "09:00–18:00",
    "Пятница":     "09:00–18:00",
    "Суббота":     "10:00–16:00",
    "Воскресенье": "Выходной",
}

# --- Часовой пояс ---
TIMEZONE = os.getenv("TIMEZONE", "Asia/Almaty")

# --- Напоминания (часы до приема) ---
# 24 часа, 2 часа, и 1 час до приёма
REMINDER_HOURS = [24, 2, 1]
