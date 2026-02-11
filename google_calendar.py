"""
Google Calendar — создание/обновление/удаление событий.
Цветовая кодировка:
- Зелёный (10) = активная запись
- Красный (11) = отменённая запись
- Жёлтый (5) = перенесённая запись
- Серый (8) = завершённая запись
"""

import logging
import time as _time
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import GOOGLE_CALENDAR_ID, GOOGLE_CREDENTIALS_PATH, TIMEZONE

logger = logging.getLogger(__name__)


def _retry_google_api(func, *args, max_retries=3, **kwargs):
    """Обёртка retry для Google API с exponential backoff (429/5xx)."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except HttpError as e:
            if e.resp.status in (429, 500, 503) and attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(f"Google API {e.resp.status}, retry in {wait}s (attempt {attempt + 1})")
                _time.sleep(wait)
                continue
            raise
    return None

_service = None

# Цвета Google Calendar
COLOR_ACTIVE = "10"      # Зелёный (Basil)
COLOR_CANCELLED = "11"   # Красный (Tomato)
COLOR_RESCHEDULED = "5"  # Жёлтый (Banana)
COLOR_COMPLETED = "8"    # Серый (Graphite)


def _get_service():
    """Инициализировать Google Calendar API (singleton)."""
    global _service
    if _service:
        return _service
    try:
        creds = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        _service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        logger.info("Google Calendar API initialized")
        return _service
    except Exception as e:
        logger.warning(f"Google Calendar not available: {e}")
        return None


def create_event(appointment: dict) -> str | None:
    """Создать событие в Google Calendar. Возвращает event_id."""
    service = _get_service()
    if not service:
        return None

    try:
        start_dt = datetime.combine(
            appointment["appointment_date"],
            appointment["appointment_time"],
        )
        end_dt = start_dt + timedelta(minutes=appointment.get("duration_minutes", 30))

        event = {
            "summary": f"{appointment.get('service_name', 'Прием')} — {appointment.get('client_name', 'Клиент')}",
            "description": (
                f"Пациент: {appointment.get('client_name', '—')}\n"
                f"Телефон: {appointment.get('client_phone', '—')}\n"
                f"Услуга: {appointment.get('service_name', '—')}\n"
                f"Цена: {appointment.get('price', '—')} ₸\n"
                f"Статус: Активна"
            ),
            "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE},
            "end":   {"dateTime": end_dt.isoformat(),   "timeZone": TIMEZONE},
            "location": "Стоматологическая клиника",
            "colorId": COLOR_ACTIVE,  # Зелёный
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 24 * 60},
                    {"method": "popup", "minutes": 120},
                ],
            },
        }

        result = _retry_google_api(
            service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute
        )

        event_id = result.get("id")
        logger.info(f"Calendar event created: {event_id}")
        return event_id

    except Exception as e:
        logger.error(f"Calendar create error: {e}")
        return None


def update_event(event_id: str, new_date, new_time, duration: int = 30) -> bool:
    """Обновить дату/время события и пометить как перенесённое (жёлтый)."""
    service = _get_service()
    if not service or not event_id:
        return False

    try:
        start_dt = datetime.combine(new_date, new_time)
        end_dt = start_dt + timedelta(minutes=duration)

        # Получаем текущее событие чтобы обновить описание
        current = _retry_google_api(
            service.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute
        )

        # Обновляем описание со статусом
        description = current.get("description", "")
        if "Статус:" in description:
            description = description.rsplit("Статус:", 1)[0] + "Статус: Перенесена"
        else:
            description += "\nСтатус: Перенесена"

        _retry_google_api(
            service.events().patch(
                calendarId=GOOGLE_CALENDAR_ID,
                eventId=event_id,
                body={
                    "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE},
                    "end":   {"dateTime": end_dt.isoformat(),   "timeZone": TIMEZONE},
                    "colorId": COLOR_RESCHEDULED,
                    "description": description,
                },
            ).execute
        )

        logger.info(f"Calendar event updated (rescheduled): {event_id}")
        return True

    except Exception as e:
        logger.error(f"Calendar update error: {e}")
        return False


def cancel_event(event_id: str, appointment: dict = None, reason: str = None) -> bool:
    """Отметить событие как отменённое (красный цвет, зачёркнутый текст)."""
    service = _get_service()
    if not service or not event_id:
        return False

    try:
        current = _retry_google_api(
            service.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute
        )

        summary = current.get("summary", "")
        if not summary.startswith("[ОТМЕНЕНО]"):
            summary = f"[ОТМЕНЕНО] {summary}"

        description = current.get("description", "")
        if "Статус:" in description:
            description = description.rsplit("Статус:", 1)[0] + "Статус: ОТМЕНЕНА"
        else:
            description += "\nСтатус: ОТМЕНЕНА"

        if reason:
            description += f"\nПричина отмены: {reason}"

        _retry_google_api(
            service.events().patch(
                calendarId=GOOGLE_CALENDAR_ID, eventId=event_id,
                body={"summary": summary, "description": description, "colorId": COLOR_CANCELLED},
            ).execute
        )

        logger.info(f"Calendar event cancelled (marked red): {event_id}")
        return True

    except Exception as e:
        logger.error(f"Calendar cancel error: {e}")
        return False


def complete_event(event_id: str) -> bool:
    """Отметить событие как завершённое (серый цвет)."""
    service = _get_service()
    if not service or not event_id:
        return False

    try:
        current = _retry_google_api(
            service.events().get(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute
        )

        summary = current.get("summary", "")
        if not summary.startswith("[ЗАВЕРШЕНО]"):
            summary = f"[ЗАВЕРШЕНО] {summary}"

        description = current.get("description", "")
        if "Статус:" in description:
            description = description.rsplit("Статус:", 1)[0] + "Статус: ЗАВЕРШЕНО"
        else:
            description += "\nСтатус: ЗАВЕРШЕНО"

        _retry_google_api(
            service.events().patch(
                calendarId=GOOGLE_CALENDAR_ID, eventId=event_id,
                body={"summary": summary, "description": description, "colorId": COLOR_COMPLETED},
            ).execute
        )

        logger.info(f"Calendar event completed (marked gray): {event_id}")
        return True

    except Exception as e:
        logger.error(f"Calendar complete error: {e}")
        return False


def delete_event(event_id: str) -> bool:
    """Удалить событие из календаря (используй cancel_event вместо этого)."""
    service = _get_service()
    if not service or not event_id:
        return False

    try:
        service.events().delete(
            calendarId=GOOGLE_CALENDAR_ID, eventId=event_id
        ).execute()
        logger.info(f"Calendar event deleted: {event_id}")
        return True

    except Exception as e:
        logger.error(f"Calendar delete error: {e}")
        return False
