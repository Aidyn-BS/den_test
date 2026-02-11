"""
Централизованная валидация данных перед мутациями (без LLM).
Извлечено из ai_agent.py: проверки дат, времени, поиск врачей/услуг.
"""

import logging
from datetime import date, time, datetime, timedelta

import pytz

from config import TIMEZONE

logger = logging.getLogger(__name__)


def validate_appointment_time(appt_date: date, appt_time: time) -> dict:
    """Валидация даты и времени записи.

    Returns:
        {"valid": bool, "error": str | None, "corrected_time": time | None}
    """
    tz = pytz.timezone(TIMEZONE)
    now_local = datetime.now(tz).replace(tzinfo=None)

    # Дата/время не в прошлом
    appt_datetime = datetime.combine(appt_date, appt_time)
    if appt_datetime < now_local:
        return {"valid": False, "error": "Невозможно записаться на прошедшую дату/время. Пожалуйста, выберите будущую дату.", "corrected_time": None}

    # Не дальше 60 дней
    if appt_date > (now_local + timedelta(days=60)).date():
        return {"valid": False, "error": "Запись возможна максимум на 60 дней вперёд.", "corrected_time": None}

    # Время должно быть на 30-минутных интервалах
    corrected_time = None
    if appt_time.minute not in (0, 30):
        original_time_str = appt_time.strftime('%H:%M')
        if appt_time.minute < 15:
            corrected_time = time(appt_time.hour, 0)
        elif appt_time.minute < 45:
            corrected_time = time(appt_time.hour, 30)
        else:
            new_hour = appt_time.hour + 1
            if new_hour >= 18:
                return {
                    "valid": False,
                    "error": f"Время {original_time_str} некорректно. Записи принимаются строго на :00 или :30 минут (например 15:00 или 15:30).",
                    "corrected_time": None,
                }
            corrected_time = time(new_hour, 0)
        logger.info(f"Time rounded from {original_time_str} to {corrected_time.strftime('%H:%M')}")

    return {"valid": True, "error": None, "corrected_time": corrected_time}


def validate_reschedule_time(new_date: date, new_time: time) -> dict:
    """Валидация даты/времени для переноса записи.

    Returns:
        {"valid": bool, "error": str | None, "corrected_time": time | None}
    """
    tz = pytz.timezone(TIMEZONE)
    now_local = datetime.now(tz).replace(tzinfo=None)

    new_datetime = datetime.combine(new_date, new_time)
    if new_datetime < now_local:
        return {"valid": False, "error": "Невозможно перенести на прошедшую дату/время. Выберите будущую дату.", "corrected_time": None}

    if new_date > (now_local + timedelta(days=60)).date():
        return {"valid": False, "error": "Перенос возможен максимум на 60 дней вперёд.", "corrected_time": None}

    # Время на 30-минутных интервалах (как в validate_appointment_time)
    corrected_time = None
    if new_time.minute not in (0, 30):
        original_time_str = new_time.strftime('%H:%M')
        if new_time.minute < 15:
            corrected_time = time(new_time.hour, 0)
        elif new_time.minute < 45:
            corrected_time = time(new_time.hour, 30)
        else:
            new_hour = new_time.hour + 1
            if new_hour >= 18:
                return {
                    "valid": False,
                    "error": f"Время {original_time_str} некорректно. Записи принимаются строго на :00 или :30 минут.",
                    "corrected_time": None,
                }
            corrected_time = time(new_hour, 0)
        logger.info(f"Reschedule time rounded from {original_time_str} to {corrected_time.strftime('%H:%M')}")

    return {"valid": True, "error": None, "corrected_time": corrected_time}


def find_doctor_by_name(doctor_name: str, doctors: list) -> dict | None:
    """Найти врача по имени (нечёткий поиск)."""
    for d in doctors:
        if doctor_name.lower() in d["name"].lower() or d["name"].lower() in doctor_name.lower():
            return d
    return None


def find_service_by_name(service_name: str, services: list) -> dict | None:
    """Найти услугу по названию (нечёткий поиск)."""
    for s in services:
        if service_name.lower() in s["name"].lower() or s["name"].lower() in service_name.lower():
            return s
    return None
