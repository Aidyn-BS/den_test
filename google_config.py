# -*- coding: utf-8 -*-
"""
Google Sheets как источник настроек клиники.
Позволяет владельцам клиник самостоятельно менять:
- Информацию о клинике (название, адрес, телефон)
- Часы работы
- Услуги и цены
- Врачей

Кэширование: 15 минут (900 секунд)
"""

import logging
import time
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import GOOGLE_SHEETS_ID, GOOGLE_CREDENTIALS_PATH

logger = logging.getLogger(__name__)

# Кэширование
_cache = {}
_cache_time = {}
CACHE_TTL = 900  # 15 минут

_service = None


def _get_service():
    """Инициализировать Google Sheets API (singleton)."""
    global _service
    if _service:
        return _service
    try:
        creds = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        _service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        logger.info("Google Sheets Config API initialized")
        return _service
    except Exception as e:
        logger.warning(f"Google Sheets Config not available: {e}")
        return None


def _get_cached(key: str):
    """Получить значение из кэша если не истекло."""
    if key in _cache and key in _cache_time:
        if time.time() - _cache_time[key] < CACHE_TTL:
            return _cache[key]
    return None


def _set_cache(key: str, value):
    """Сохранить значение в кэш."""
    _cache[key] = value
    _cache_time[key] = time.time()


def clear_cache():
    """Очистить весь кэш (для принудительного обновления)."""
    global _cache, _cache_time
    _cache = {}
    _cache_time = {}
    logger.info("Config cache cleared")


# ============================================================
# НАСТРОЙКИ КЛИНИКИ
# ============================================================

def get_clinic_settings() -> dict:
    """
    Получить настройки клиники из листа "Настройки".
    Формат листа:
    | Параметр | Значение |
    | Название клиники | ... |
    | Адрес | ... |
    | Телефон | ... |
    | Телефон админа | ... |
    """
    cached = _get_cached("clinic_settings")
    if cached:
        return cached

    service = _get_service()
    if not service:
        return _get_default_clinic_settings()

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SHEETS_ID,
            range="Настройки!A:B",
        ).execute()

        values = result.get("values", [])
        settings = {}

        for row in values:
            if len(row) >= 2:
                key = row[0].strip().lower()
                value = row[1].strip()

                if "название" in key:
                    settings["name"] = value
                elif "адрес" in key:
                    settings["address"] = value
                elif "админ" in key:
                    settings["admin_phone"] = value
                elif "телефон" in key:
                    settings["phone"] = value

        # Заполняем пустые значения дефолтами
        defaults = _get_default_clinic_settings()
        for k, v in defaults.items():
            if k not in settings or not settings[k]:
                settings[k] = v

        _set_cache("clinic_settings", settings)
        logger.info(f"Clinic settings loaded from Sheets: {settings.get('name')}")
        return settings

    except Exception as e:
        logger.warning(f"Error loading clinic settings: {e}")
        return _get_default_clinic_settings()


def _get_default_clinic_settings() -> dict:
    """Дефолтные настройки из config.py."""
    from config import CLINIC_NAME, CLINIC_ADDRESS, CLINIC_PHONE, ADMIN_PHONE
    return {
        "name": CLINIC_NAME,
        "address": CLINIC_ADDRESS,
        "phone": CLINIC_PHONE,
        "admin_phone": ADMIN_PHONE,
    }


# ============================================================
# ЧАСЫ РАБОТЫ
# ============================================================

def get_clinic_hours() -> dict:
    """
    Получить часы работы из листа "Часы работы".
    Формат листа:
    | День | Время |
    | Понедельник | 09:00–18:00 |
    | ... | ... |
    | Воскресенье | Выходной |
    """
    cached = _get_cached("clinic_hours")
    if cached:
        return cached

    service = _get_service()
    if not service:
        return _get_default_clinic_hours()

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SHEETS_ID,
            range="Часы работы!A:B",
        ).execute()

        values = result.get("values", [])
        hours = {}

        for row in values:
            if len(row) >= 2:
                day = row[0].strip()
                time_str = row[1].strip()

                # Пропускаем заголовок
                if day.lower() in ["день", "day"]:
                    continue

                hours[day] = time_str

        if not hours:
            return _get_default_clinic_hours()

        _set_cache("clinic_hours", hours)
        logger.info("Clinic hours loaded from Sheets")
        return hours

    except Exception as e:
        logger.warning(f"Error loading clinic hours: {e}")
        return _get_default_clinic_hours()


def _get_default_clinic_hours() -> dict:
    """Дефолтные часы работы из config.py."""
    from config import CLINIC_HOURS
    return CLINIC_HOURS


# ============================================================
# УСЛУГИ
# ============================================================

def get_services() -> list[dict]:
    """
    Получить услуги из листа "Услуги".
    Формат листа:
    | ID | Название | Цена | Длительность (мин) | Описание | Активна |
    | 1 | Консультация | 5000 | 30 | ... | Да |
    """
    cached = _get_cached("services")
    if cached:
        return cached

    service = _get_service()
    if not service:
        return None  # Fallback на БД

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SHEETS_ID,
            range="Услуги!A:H",
        ).execute()

        values = result.get("values", [])
        services = []

        if not values:
            return None

        header = values[0]
        header_len = len(header)

        for row in values[1:]:  # Пропускаем заголовок
            # Если данные сдвинуты (больше столбцов чем в заголовке) — выравниваем
            offset = len(row) - header_len if len(row) > header_len else 0
            r = row[offset:]

            if len(r) >= 5:
                # Проверяем активность
                is_active = True
                if len(r) >= 6:
                    active_str = r[5].strip().lower()
                    is_active = active_str in ["да", "yes", "true", "1", "активна"]

                if not is_active:
                    continue

                try:
                    services.append({
                        "id": int(r[0]) if r[0] else len(services) + 1,
                        "name": r[1].strip(),
                        "price": int(r[2].replace(" ", "").replace(",", "").replace("₸", "")),
                        "duration_minutes": int(r[3]) if r[3] else 30,
                        "description": r[4].strip() if len(r) > 4 else "",
                    })
                except (ValueError, IndexError) as e:
                    logger.warning(f"Skipping invalid service row: {row}, error: {e}")
                    continue

        if services:
            _set_cache("services", services)
            logger.info(f"Services loaded from Sheets: {len(services)} items")
            return services
        else:
            return None  # Fallback на БД

    except Exception as e:
        logger.warning(f"Error loading services: {e}")
        return None  # Fallback на БД


# ============================================================
# ВРАЧИ
# ============================================================

def get_doctors() -> list[dict]:
    """
    Получить врачей из листа "Врачи".
    Формат листа:
    | ID | ФИО | Специализация | Опыт (лет) | Описание | Активен |
    | 1 | Иванов А.П. | Терапевт | 12 | ... | Да |
    """
    cached = _get_cached("doctors")
    if cached:
        return cached

    service = _get_service()
    if not service:
        return None  # Fallback на БД

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SHEETS_ID,
            range="Врачи!A:F",
        ).execute()

        values = result.get("values", [])
        doctors = []

        for row in values[1:]:  # Пропускаем заголовок
            if len(row) >= 3:
                # Проверяем активность
                is_active = True
                if len(row) >= 6:
                    active_str = row[5].strip().lower()
                    is_active = active_str in ["да", "yes", "true", "1", "активен"]

                if not is_active:
                    continue

                try:
                    doctors.append({
                        "id": int(row[0]) if row[0] else len(doctors) + 1,
                        "name": row[1].strip(),
                        "specialization": row[2].strip(),
                        "experience_years": int(row[3]) if len(row) > 3 and row[3] else 0,
                        "bio": row[4].strip() if len(row) > 4 else "",
                    })
                except (ValueError, IndexError) as e:
                    logger.warning(f"Skipping invalid doctor row: {row}, error: {e}")
                    continue

        if doctors:
            _set_cache("doctors", doctors)
            logger.info(f"Doctors loaded from Sheets: {len(doctors)} items")
            return doctors
        else:
            return None  # Fallback на БД

    except Exception as e:
        logger.warning(f"Error loading doctors: {e}")
        return None  # Fallback на БД
