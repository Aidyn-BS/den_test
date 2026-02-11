"""
Google Sheets — экспорт отчетов с цветовой кодировкой.
Цвета:
- Зелёный = активная запись (scheduled)
- Красный = отменённая запись (cancelled)
- Жёлтый = перенесённая запись (rescheduled)
- Серый = завершённая запись (completed)
"""

import logging
import time as _time
from datetime import datetime, date, time
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import GOOGLE_SHEETS_ID, GOOGLE_CREDENTIALS_PATH

logger = logging.getLogger(__name__)


def _retry_google_api(func, *args, max_retries=3, **kwargs):
    """Обёртка retry для Google Sheets API (429/5xx)."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except HttpError as e:
            if e.resp.status in (429, 500, 503) and attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(f"Google Sheets API {e.resp.status}, retry in {wait}s (attempt {attempt + 1})")
                _time.sleep(wait)
                continue
            raise
    return None

_service = None

# Цвета (RGB 0-1)
COLOR_GREEN = {"red": 0.7, "green": 0.9, "blue": 0.7}   # Светло-зелёный
COLOR_RED = {"red": 0.95, "green": 0.7, "blue": 0.7}    # Светло-красный
COLOR_YELLOW = {"red": 1.0, "green": 0.95, "blue": 0.7}  # Светло-жёлтый
COLOR_GRAY = {"red": 0.8, "green": 0.8, "blue": 0.8}    # Серый


def _get_service():
    """Инициализировать Google Sheets API (singleton)."""
    global _service
    if _service:
        return _service
    try:
        creds = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        _service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        logger.info("Google Sheets API initialized")
        return _service
    except Exception as e:
        logger.warning(f"Google Sheets not available: {e}")
        return None


def _get_sheet_id() -> int | None:
    """Получить ID листа 'Dental clinic'."""
    service = _get_service()
    if not service:
        return None
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=GOOGLE_SHEETS_ID).execute()
        for sheet in spreadsheet.get("sheets", []):
            if sheet["properties"]["title"] == "Dental clinic":
                return sheet["properties"]["sheetId"]
        return 0  # Первый лист по умолчанию
    except Exception as e:
        logger.error(f"Error getting sheet ID: {e}")
        return 0


def add_appointment(appointment: dict) -> bool:
    """Добавить одну запись в Google Sheets с зелёным фоном."""
    service = _get_service()
    if not service:
        return False

    try:
        # Добавляем ID записи для отслеживания
        appt_id = appointment.get("id", "")
        row = [[
            str(appt_id),  # ID записи (скрытый столбец A)
            str(appointment.get("appointment_date", "")),
            str(appointment.get("appointment_time", ""))[:5],
            appointment.get("client_name", "—"),
            appointment.get("client_phone", "—"),
            appointment.get("doctor_name", "—"),
            appointment.get("service_name", "—"),
            str(appointment.get("price", "")),
            "Активна",  # Статус
            datetime.now().strftime("%d.%m.%Y %H:%M"),
        ]]

        # Добавляем строку
        result = _retry_google_api(
            service.spreadsheets().values().append(
                spreadsheetId=GOOGLE_SHEETS_ID,
                range="Dental clinic!A:J",
                valueInputOption="USER_ENTERED",
                body={"values": row},
            ).execute
        )

        # Получаем номер добавленной строки
        updated_range = result.get("updates", {}).get("updatedRange", "")
        if updated_range:
            # Пример: "Dental clinic!A5:J5" -> row 5
            row_num = int(updated_range.split("!")[1].split(":")[0][1:]) - 1
            _color_row(row_num, COLOR_GREEN)

        logger.info(f"Appointment added to Sheets: {appointment.get('client_name')}")
        return True

    except Exception as e:
        logger.error(f"Sheets add appointment error: {e}")
        return False


def _color_row(row_index: int, color: dict) -> bool:
    """Покрасить строку в указанный цвет."""
    service = _get_service()
    if not service:
        return False

    try:
        sheet_id = _get_sheet_id()

        request = {
            "requests": [{
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_index,
                        "endRowIndex": row_index + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 10,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": color
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor"
                }
            }]
        }

        service.spreadsheets().batchUpdate(
            spreadsheetId=GOOGLE_SHEETS_ID,
            body=request
        ).execute()

        return True

    except Exception as e:
        logger.error(f"Error coloring row: {e}")
        return False


def update_appointment_status(appt_id: int, status: str, new_date=None, new_time=None, reason: str = None) -> bool:
    """Обновить статус записи в таблице и изменить цвет строки."""
    service = _get_service()
    if not service:
        return False

    try:
        # Получаем все данные из таблицы
        result = service.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SHEETS_ID,
            range="Dental clinic!A:J",
        ).execute()

        values = result.get("values", [])

        # Ищем строку с нужным ID
        row_index = None
        for i, row in enumerate(values):
            if row and str(row[0]) == str(appt_id):
                row_index = i
                break

        if row_index is None:
            logger.warning(f"Appointment {appt_id} not found in Sheets")
            return False

        # Определяем новый статус и цвет
        if status == "cancelled":
            status_text = "ОТМЕНЕНА"
            color = COLOR_RED
        elif status == "rescheduled":
            status_text = "ПЕРЕНЕСЕНА"
            color = COLOR_YELLOW
            # Обновляем дату и время если указаны
            if new_date and new_time:
                values[row_index][1] = str(new_date)
                values[row_index][2] = str(new_time)[:5] if hasattr(new_time, 'isoformat') else str(new_time)[:5]
        elif status == "completed":
            status_text = "ЗАВЕРШЕНО"
            color = COLOR_GRAY
        else:
            status_text = "Активна"
            color = COLOR_GREEN

        # Обновляем статус в строке
        if len(values[row_index]) >= 9:
            values[row_index][8] = status_text
        else:
            while len(values[row_index]) < 9:
                values[row_index].append("")
            values[row_index][8] = status_text

        # Добавляем причину отмены в колонку K (индекс 10)
        if status == "cancelled" and reason:
            while len(values[row_index]) < 11:
                values[row_index].append("")
            values[row_index][10] = reason

        # Обновляем данные в таблице
        service.spreadsheets().values().update(
            spreadsheetId=GOOGLE_SHEETS_ID,
            range=f"Dental clinic!A{row_index + 1}:K{row_index + 1}",
            valueInputOption="USER_ENTERED",
            body={"values": [values[row_index]]}
        ).execute()

        # Красим строку
        _color_row(row_index, color)

        logger.info(f"Appointment {appt_id} status updated to {status_text}")
        return True

    except Exception as e:
        logger.error(f"Sheets update status error: {e}")
        return False


def export_appointments(appointments: list[dict], title: str) -> bool:
    """Экспортировать список записей в Google Sheets."""
    service = _get_service()
    if not service:
        return False

    try:
        rows = [
            [title, datetime.now().strftime("%d.%m.%Y %H:%M")],
            [],
            ["ID", "Дата", "Время", "Пациент", "Телефон", "Врач", "Услуга", "Цена", "Статус", "Создано"],
        ]

        for a in appointments:
            status = a.get("status", "scheduled")
            if status == "scheduled":
                status_text = "Активна"
            elif status == "cancelled":
                status_text = "ОТМЕНЕНА"
            else:
                status_text = status

            rows.append([
                str(a.get("id", "")),
                str(a.get("appointment_date", "")),
                str(a.get("appointment_time", ""))[:5],
                a.get("client_name", "—"),
                a.get("client_phone", "—"),
                a.get("doctor_name", "—"),
                a.get("service_name", "—"),
                str(a.get("price", "")),
                status_text,
                "",
            ])

        rows.append([])
        rows.append(["", "Итого записей:", len(appointments)])

        service.spreadsheets().values().append(
            spreadsheetId=GOOGLE_SHEETS_ID,
            range="Dental clinic",
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()

        logger.info(f"Appointments exported to Sheets: {len(appointments)} rows")
        return True

    except Exception as e:
        logger.error(f"Sheets export error: {e}")
        return False


def export_month_stats(stats: dict, month_label: str) -> bool:
    """Экспортировать месячный отчет в Google Sheets."""
    service = _get_service()
    if not service:
        return False

    try:
        rows = [
            [f"ОТЧЕТ ЗА {month_label}", datetime.now().strftime("%d.%m.%Y %H:%M")],
            [],
            ["Метрика", "Значение"],
            ["Всего записей", stats.get("total", 0)],
            ["Запланировано", stats.get("scheduled", 0)],
            ["Завершено", stats.get("completed", 0)],
            ["Отменено", stats.get("cancelled", 0)],
            ["Неявки", stats.get("no_show", 0)],
            ["Новых клиентов", stats.get("new_clients", 0)],
            ["Общий доход", f"{stats.get('revenue', 0)} ₸"],
            [],
            ["Топ врачей", "Приемов"],
        ]

        for doc in stats.get("top_doctors", []):
            rows.append([doc["name"], doc["cnt"]])

        service.spreadsheets().values().append(
            spreadsheetId=GOOGLE_SHEETS_ID,
            range="Dental clinic",
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()

        logger.info("Monthly stats exported to Sheets")
        return True

    except Exception as e:
        logger.error(f"Sheets month stats error: {e}")
        return False
