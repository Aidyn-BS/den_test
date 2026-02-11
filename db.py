"""
Все операции с базой данных PostgreSQL.
Используется psycopg2 с пулом соединений (без ORM).
"""

import psycopg2
import psycopg2.extras
import psycopg2.pool
import logging
from contextlib import contextmanager
from datetime import date, time, datetime, timedelta

from config import DB_CONFIG

logger = logging.getLogger(__name__)


# ==================== Connection Pool ====================

_pool = None


def _get_pool():
    """Получить или создать пул соединений (lazy init)."""
    global _pool
    if _pool is None or _pool.closed:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            **DB_CONFIG,
        )
        logger.info("Database connection pool created (min=2, max=10)")
    return _pool


@contextmanager
def get_conn():
    """Контекстный менеджер — берёт соединение из пула и возвращает обратно."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ==================== Клиенты ====================

def get_client(phone: str) -> dict | None:
    """Получить клиента по номеру телефона."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM clients WHERE phone = %s", (phone,))
            return cur.fetchone()


def create_client(phone: str, name: str = None) -> dict:
    """Создать нового клиента."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "INSERT INTO clients (phone, name) VALUES (%s, %s) "
                "ON CONFLICT (phone) DO UPDATE SET name = COALESCE(EXCLUDED.name, clients.name) "
                "RETURNING *",
                (phone, name),
            )
            return cur.fetchone()


def update_client_name(phone: str, name: str) -> dict | None:
    """Обновить имя клиента."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "UPDATE clients SET name = %s, updated_at = NOW() WHERE phone = %s RETURNING *",
                (name, phone),
            )
            return cur.fetchone()


# ==================== Врачи ====================

def get_doctors() -> list[dict]:
    """Получить всех активных врачей (сначала из Google Sheets, fallback на БД)."""
    try:
        import google_config
        doctors = google_config.get_doctors()
        if doctors:
            return doctors
    except Exception as e:
        logger.warning(f"Google Sheets doctors fallback to DB: {e}")

    # Fallback на базу данных
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, name, specialization, experience_years, bio "
                "FROM doctors WHERE is_active = TRUE ORDER BY id"
            )
            return cur.fetchall()


def get_doctor(doctor_id: int) -> dict | None:
    """Получить врача по ID."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM doctors WHERE id = %s AND is_active = TRUE", (doctor_id,))
            return cur.fetchone()


# ==================== Услуги ====================

def get_services() -> list[dict]:
    """Получить все активные услуги (сначала из Google Sheets, fallback на БД)."""
    try:
        import google_config
        services = google_config.get_services()
        if services:
            return services
    except Exception as e:
        logger.warning(f"Google Sheets services fallback to DB: {e}")

    # Fallback на базу данных
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, name, price, duration_minutes, description "
                "FROM services WHERE is_active = TRUE ORDER BY id"
            )
            return cur.fetchall()


def get_service(service_id: int) -> dict | None:
    """Получить услугу по ID."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM services WHERE id = %s AND is_active = TRUE", (service_id,))
            return cur.fetchone()


# ==================== Записи ====================

def get_appointments_by_date(target_date: date) -> list[dict]:
    """Получить все записи на конкретную дату."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.id, a.appointment_date, a.appointment_time, a.status, a.notes,
                       c.name AS client_name, c.phone AS client_phone,
                       d.name AS doctor_name, d.specialization,
                       s.name AS service_name, s.price, s.duration_minutes
                FROM appointments a
                JOIN clients c ON a.client_id = c.id
                JOIN doctors d ON a.doctor_id = d.id
                JOIN services s ON a.service_id = s.id
                WHERE a.appointment_date = %s AND a.status = 'scheduled'
                ORDER BY a.appointment_time
                """,
                (target_date,),
            )
            return cur.fetchall()


def get_appointments_range(start_date: date, end_date: date) -> list[dict]:
    """Получить записи за диапазон дат."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.id, a.appointment_date, a.appointment_time, a.status, a.notes,
                       c.name AS client_name, c.phone AS client_phone,
                       d.name AS doctor_name, d.specialization,
                       s.name AS service_name, s.price, s.duration_minutes
                FROM appointments a
                JOIN clients c ON a.client_id = c.id
                JOIN doctors d ON a.doctor_id = d.id
                JOIN services s ON a.service_id = s.id
                WHERE a.appointment_date BETWEEN %s AND %s
                ORDER BY a.appointment_date, a.appointment_time
                """,
                (start_date, end_date),
            )
            return cur.fetchall()


def get_client_appointments(phone: str) -> list[dict]:
    """Получить все предстоящие записи клиента."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.id, a.appointment_date, a.appointment_time, a.status, a.notes,
                       d.name AS doctor_name, d.specialization,
                       s.name AS service_name, s.price, s.duration_minutes
                FROM appointments a
                JOIN clients c ON a.client_id = c.id
                JOIN doctors d ON a.doctor_id = d.id
                JOIN services s ON a.service_id = s.id
                WHERE c.phone = %s AND a.status = 'scheduled'
                      AND (a.appointment_date > CURRENT_DATE
                           OR (a.appointment_date = CURRENT_DATE AND a.appointment_time > CURRENT_TIME))
                ORDER BY a.appointment_date, a.appointment_time
                """,
                (phone,),
            )
            return cur.fetchall()


def get_all_upcoming_appointments() -> list[dict]:
    """Получить все предстоящие записи клиники (для админа)."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.id, a.appointment_date, a.appointment_time, a.status, a.notes,
                       c.name AS client_name, c.phone AS client_phone,
                       d.name AS doctor_name, d.specialization,
                       s.name AS service_name, s.price, s.duration_minutes
                FROM appointments a
                JOIN clients c ON a.client_id = c.id
                JOIN doctors d ON a.doctor_id = d.id
                JOIN services s ON a.service_id = s.id
                WHERE a.status = 'scheduled'
                      AND (a.appointment_date > CURRENT_DATE
                           OR (a.appointment_date = CURRENT_DATE AND a.appointment_time > CURRENT_TIME))
                ORDER BY a.appointment_date, a.appointment_time
                LIMIT 50
                """
            )
            return cur.fetchall()


def get_client_history(phone: str) -> list[dict]:
    """Получить историю посещений клиента (прошлые записи)."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.id, a.appointment_date, a.appointment_time, a.status,
                       d.name AS doctor_name, s.name AS service_name
                FROM appointments a
                JOIN clients c ON a.client_id = c.id
                JOIN doctors d ON a.doctor_id = d.id
                JOIN services s ON a.service_id = s.id
                WHERE c.phone = %s AND a.status IN ('completed', 'scheduled')
                ORDER BY a.appointment_date DESC
                LIMIT 10
                """,
                (phone,),
            )
            return cur.fetchall()


def create_appointment(
    client_phone: str,
    doctor_id: int,
    service_id: int,
    appt_date: date,
    appt_time: time,
    notes: str = None,
    patient_name: str = None,
) -> dict | None:
    """Создать новую запись. Возвращает данные записи или None при конфликте."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Получаем client_id
            cur.execute("SELECT id FROM clients WHERE phone = %s", (client_phone,))
            client = cur.fetchone()
            if not client:
                return None

            # Получаем длительность услуги
            cur.execute("SELECT duration_minutes FROM services WHERE id = %s", (service_id,))
            service = cur.fetchone()
            if not service:
                return None

            # Блокируем строки врача на эту дату (защита от двойной записи)
            cur.execute(
                """
                SELECT id FROM appointments
                WHERE doctor_id = %s AND appointment_date = %s AND status = 'scheduled'
                FOR UPDATE
                """,
                (doctor_id, appt_date),
            )

            # Проверяем конфликт времени у врача
            duration = service["duration_minutes"]
            cur.execute(
                """
                SELECT id FROM appointments
                WHERE doctor_id = %s AND appointment_date = %s AND status = 'scheduled'
                      AND appointment_time < (%s::time + make_interval(mins => %s))
                      AND (%s::time < appointment_time + (
                          SELECT make_interval(mins => s.duration_minutes)
                          FROM services s WHERE s.id = appointments.service_id
                      ))
                """,
                (doctor_id, appt_date, appt_time, int(duration), appt_time),
            )
            if cur.fetchone():
                return None  # Конфликт — время занято

            # Создаем запись
            cur.execute(
                """
                INSERT INTO appointments (client_id, doctor_id, service_id,
                    appointment_date, appointment_time, notes, patient_name)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (client["id"], doctor_id, service_id, appt_date, appt_time, notes, patient_name),
            )
            appt = cur.fetchone()

            # Подгружаем полные данные для ответа
            cur.execute(
                """
                SELECT a.id, a.appointment_date, a.appointment_time, a.status,
                       c.name AS client_name, c.phone AS client_phone,
                       d.name AS doctor_name, d.specialization,
                       s.name AS service_name, s.price, s.duration_minutes
                FROM appointments a
                JOIN clients c ON a.client_id = c.id
                JOIN doctors d ON a.doctor_id = d.id
                JOIN services s ON a.service_id = s.id
                WHERE a.id = %s
                """,
                (appt["id"],),
            )
            return cur.fetchone()


def cancel_appointment(appointment_id: int, client_phone: str = None, reason: str = None) -> dict | None:
    """Отменить запись. Если client_phone указан — проверяет принадлежность."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if client_phone:
                cur.execute(
                    """
                    UPDATE appointments SET status = 'cancelled',
                           cancellation_reason = %s, updated_at = NOW()
                    WHERE id = %s AND status = 'scheduled'
                          AND client_id = (SELECT id FROM clients WHERE phone = %s)
                    RETURNING *
                    """,
                    (reason, appointment_id, client_phone),
                )
            else:
                cur.execute(
                    """
                    UPDATE appointments SET status = 'cancelled',
                           cancellation_reason = %s, updated_at = NOW()
                    WHERE id = %s AND status = 'scheduled'
                    RETURNING *
                    """,
                    (reason, appointment_id),
                )
            return cur.fetchone()


def reschedule_appointment(
    appointment_id: int, new_date: date, new_time: time, client_phone: str = None
) -> dict | None:
    """Перенести запись на новую дату/время."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Получаем текущую запись
            if client_phone:
                cur.execute(
                    """
                    SELECT a.*, s.duration_minutes FROM appointments a
                    JOIN services s ON a.service_id = s.id
                    WHERE a.id = %s AND a.status = 'scheduled'
                          AND a.client_id = (SELECT id FROM clients WHERE phone = %s)
                    """,
                    (appointment_id, client_phone),
                )
            else:
                cur.execute(
                    """
                    SELECT a.*, s.duration_minutes FROM appointments a
                    JOIN services s ON a.service_id = s.id
                    WHERE a.id = %s AND a.status = 'scheduled'
                    """,
                    (appointment_id,),
                )
            appt = cur.fetchone()
            if not appt:
                return None

            # Блокируем строки врача на новую дату (защита от двойной записи)
            cur.execute(
                """
                SELECT id FROM appointments
                WHERE doctor_id = %s AND appointment_date = %s AND status = 'scheduled'
                FOR UPDATE
                """,
                (appt["doctor_id"], new_date),
            )

            # Проверяем конфликт на новое время
            cur.execute(
                """
                SELECT id FROM appointments
                WHERE doctor_id = %s AND appointment_date = %s AND status = 'scheduled'
                      AND id != %s
                      AND appointment_time < (%s::time + make_interval(mins => %s))
                      AND (%s::time < appointment_time + (
                          SELECT make_interval(mins => s.duration_minutes)
                          FROM services s WHERE s.id = appointments.service_id
                      ))
                """,
                (appt["doctor_id"], new_date, appointment_id,
                 new_time, int(appt["duration_minutes"]), new_time),
            )
            if cur.fetchone():
                return {"error": "conflict"}  # Конфликт

            # Сохраняем старые дату/время для уведомления
            old_date = appt["appointment_date"]
            old_time = appt["appointment_time"]

            cur.execute(
                """
                UPDATE appointments
                SET appointment_date = %s, appointment_time = %s,
                    reminder_24h_sent = FALSE, reminder_2h_sent = FALSE,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (new_date, new_time, appointment_id),
            )
            updated = cur.fetchone()
            if updated:
                updated["old_date"] = old_date
                updated["old_time"] = old_time
            return updated


def get_doctor_schedule(doctor_id: int, day_of_week: int) -> dict | None:
    """Получить расписание врача на конкретный день недели (0=Пн, 6=Вс).
    Возвращает {'start_time': time, 'end_time': time} или None если не работает.
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT start_time, end_time FROM doctor_schedules
                WHERE doctor_id = %s AND day_of_week = %s AND is_active = TRUE
                """,
                (doctor_id, day_of_week),
            )
            return cur.fetchone()


def is_doctor_absent(doctor_id: int, target_date: date) -> bool:
    """Проверить, отсутствует ли врач (болезнь/отпуск) на указанную дату."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM doctor_absences
                WHERE doctor_id = %s AND start_date <= %s AND end_date >= %s
                """,
                (doctor_id, target_date, target_date),
            )
            return cur.fetchone() is not None


def get_free_slots(target_date: date, doctor_id: int = None) -> list[dict]:
    """Получить свободные временные слоты на дату.
    Использует индивидуальное расписание врачей (doctor_schedules).
    Если у врача нет записи в doctor_schedules — fallback на часы клиники.
    """
    # Загружаем часы работы клиники (fallback)
    try:
        import google_config
        clinic_hours = google_config.get_clinic_hours()
    except Exception:
        from config import CLINIC_HOURS
        clinic_hours = CLINIC_HOURS

    day_names_ru = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    day_idx = target_date.weekday()
    day_name = day_names_ru[day_idx]
    clinic_hours_str = clinic_hours.get(day_name, "Выходной")

    logger.info(f"get_free_slots: date={target_date}, day={day_name}, clinic_hours={clinic_hours_str}, doctor_id={doctor_id}")

    # Парсим дефолтные часы клиники
    clinic_start_h, clinic_start_m = 9, 0
    clinic_end_h, clinic_end_m = 18, 0
    clinic_is_open = clinic_hours_str != "Выходной"
    if clinic_is_open:
        try:
            start_str, end_str = clinic_hours_str.replace("–", "-").split("-")
            clinic_start_h, clinic_start_m = map(int, start_str.strip().split(":"))
            clinic_end_h, clinic_end_m = map(int, end_str.strip().split(":"))
        except (ValueError, AttributeError):
            pass

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Получаем занятые слоты
            query = """
                SELECT a.appointment_time, s.duration_minutes, d.name AS doctor_name, d.id AS doctor_id
                FROM appointments a
                JOIN services s ON a.service_id = s.id
                JOIN doctors d ON a.doctor_id = d.id
                WHERE a.appointment_date = %s AND a.status = 'scheduled'
            """
            params = [target_date]
            if doctor_id:
                query += " AND a.doctor_id = %s"
                params.append(doctor_id)

            cur.execute(query, params)
            busy = cur.fetchall()

            if busy:
                logger.info(f"get_free_slots: found {len(busy)} busy appointments")
            else:
                logger.info(f"get_free_slots: no busy appointments found")

            # Получаем врачей
            if doctor_id:
                cur.execute("SELECT id, name FROM doctors WHERE id = %s AND is_active = TRUE", (doctor_id,))
            else:
                cur.execute("SELECT id, name FROM doctors WHERE is_active = TRUE ORDER BY id")
            doctors = cur.fetchall()

            # Получаем индивидуальные расписания на этот день недели
            cur.execute(
                """
                SELECT doctor_id, start_time, end_time FROM doctor_schedules
                WHERE day_of_week = %s AND is_active = TRUE
                """,
                (day_idx,),
            )
            schedules = {row["doctor_id"]: row for row in cur.fetchall()}

            # Получаем отсутствующих врачей на эту дату
            cur.execute(
                """
                SELECT DISTINCT doctor_id FROM doctor_absences
                WHERE start_date <= %s AND end_date >= %s
                """,
                (target_date, target_date),
            )
            absent_ids = {row["doctor_id"] for row in cur.fetchall()}

    # Генерируем слоты по 30 минут для каждого врача
    slots = []
    for doc in doctors:
        doc_id = doc["id"]

        # Пропускаем отсутствующих врачей
        if doc_id in absent_ids:
            logger.info(f"get_free_slots: Dr. {doc['name']} absent on {target_date}")
            continue

        # Определяем рабочие часы врача
        if doc_id in schedules:
            sched = schedules[doc_id]
            doc_start = sched["start_time"]
            doc_end = sched["end_time"]
        elif clinic_is_open:
            doc_start = time(clinic_start_h, clinic_start_m)
            doc_end = time(clinic_end_h, clinic_end_m)
        else:
            # Клиника закрыта и нет индивидуального расписания
            continue

        current = doc_start
        while current < doc_end:
            is_free = True
            for b in busy:
                if b["doctor_id"] != doc_id:
                    continue
                busy_start = b["appointment_time"]
                busy_end_dt = datetime.combine(target_date, busy_start) + timedelta(minutes=b["duration_minutes"])
                busy_end = busy_end_dt.time()
                slot_end_dt = datetime.combine(target_date, current) + timedelta(minutes=30)
                slot_end = slot_end_dt.time()

                if not (slot_end <= busy_start or current >= busy_end):
                    is_free = False
                    break

            if is_free:
                slots.append({
                    "doctor_id": doc_id,
                    "doctor_name": doc["name"],
                    "time": current.strftime("%H:%M"),
                })

            next_dt = datetime.combine(target_date, current) + timedelta(minutes=30)
            current = next_dt.time()

    logger.info(f"get_free_slots: returning {len(slots)} free slots")
    return slots


def set_doctor_absence(doctor_id: int, start_date: date, end_date: date, reason: str = "sick") -> dict:
    """Установить период отсутствия врача (болезнь/отпуск).
    Возвращает: {absence_id, cancelled_count, affected_patients: [{phone, name, appt}]}
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Создаём запись об отсутствии
            cur.execute(
                """
                INSERT INTO doctor_absences (doctor_id, start_date, end_date, reason)
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (doctor_id, start_date, end_date, reason),
            )
            absence_id = cur.fetchone()["id"]

            # Находим затронутые записи (scheduled, в период отсутствия)
            cur.execute(
                """
                SELECT a.id, a.appointment_date, a.appointment_time,
                       c.phone AS client_phone, c.name AS client_name,
                       s.name AS service_name, a.google_calendar_event_id
                FROM appointments a
                JOIN clients c ON a.client_id = c.id
                JOIN services s ON a.service_id = s.id
                WHERE a.doctor_id = %s AND a.status = 'scheduled'
                      AND a.appointment_date BETWEEN %s AND %s
                """,
                (doctor_id, start_date, end_date),
            )
            affected = cur.fetchall()

            # Массово отменяем
            cur.execute(
                """
                UPDATE appointments SET status = 'cancelled',
                       cancellation_reason = %s, updated_at = NOW()
                WHERE doctor_id = %s AND status = 'scheduled'
                      AND appointment_date BETWEEN %s AND %s
                """,
                (f"Врач недоступен: {reason}", doctor_id, start_date, end_date),
            )
            cancelled_count = cur.rowcount

            return {
                "absence_id": absence_id,
                "cancelled_count": cancelled_count,
                "affected_patients": affected,
            }


def update_appointment_calendar_id(appointment_id: int, event_id: str):
    """Сохранить Google Calendar event ID для записи."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE appointments SET google_calendar_event_id = %s WHERE id = %s",
                (event_id, appointment_id),
            )


def get_appointment_by_id(appointment_id: int) -> dict | None:
    """Получить запись по ID с полными данными."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.*, c.name AS client_name, c.phone AS client_phone,
                       d.name AS doctor_name, s.name AS service_name,
                       s.price, s.duration_minutes
                FROM appointments a
                JOIN clients c ON a.client_id = c.id
                JOIN doctors d ON a.doctor_id = d.id
                JOIN services s ON a.service_id = s.id
                WHERE a.id = %s
                """,
                (appointment_id,),
            )
            return cur.fetchone()


# ==================== История чата ====================

def save_message(phone: str, role: str, message: str):
    """Сохранить сообщение в историю чата."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_history (phone, role, message) VALUES (%s, %s, %s)",
                (phone, role, message),
            )


def get_chat_history(phone: str, limit: int = 20) -> list[dict]:
    """Получить последние N сообщений из истории чата."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT role, message FROM (
                    SELECT role, message, created_at
                    FROM chat_history WHERE phone = %s
                    ORDER BY created_at DESC LIMIT %s
                ) sub ORDER BY created_at ASC
                """,
                (phone, limit),
            )
            return cur.fetchall()


# ==================== Контекст клиента (оптимизация) ====================

def get_client_context(phone: str) -> dict:
    """Загрузить весь контекст клиента за одно соединение.
    Возвращает: {client, is_admin, history, upcoming, chat_history}
    Заменяет 4+ отдельных вызова: get_client, is_admin, get_client_history, get_client_appointments, get_chat_history.
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Клиент
            cur.execute("SELECT * FROM clients WHERE phone = %s", (phone,))
            client = cur.fetchone()

            # 2. Администратор? (таблица admin_users + fallback на ADMIN_PHONE)
            cur.execute(
                "SELECT 1 FROM admin_users WHERE phone = %s AND is_active = TRUE",
                (phone,),
            )
            admin = cur.fetchone() is not None
            if not admin:
                from config import ADMIN_PHONE
                admin = (phone == ADMIN_PHONE)

            # 3. История посещений (последние 5)
            visit_history = []
            if client:
                cur.execute(
                    """
                    SELECT a.appointment_date, a.status,
                           d.name AS doctor_name, s.name AS service_name
                    FROM appointments a
                    JOIN doctors d ON a.doctor_id = d.id
                    JOIN services s ON a.service_id = s.id
                    WHERE a.client_id = %s AND a.status IN ('completed', 'scheduled')
                    ORDER BY a.appointment_date DESC LIMIT 5
                    """,
                    (client["id"],),
                )
                visit_history = cur.fetchall()

            # 4. Предстоящие записи
            upcoming = []
            if client:
                cur.execute(
                    """
                    SELECT a.id, a.appointment_date, a.appointment_time, a.status,
                           d.name AS doctor_name, s.name AS service_name
                    FROM appointments a
                    JOIN doctors d ON a.doctor_id = d.id
                    JOIN services s ON a.service_id = s.id
                    WHERE a.client_id = %s AND a.status = 'scheduled'
                          AND (a.appointment_date > CURRENT_DATE
                               OR (a.appointment_date = CURRENT_DATE AND a.appointment_time > CURRENT_TIME))
                    ORDER BY a.appointment_date, a.appointment_time
                    """,
                    (client["id"],),
                )
                upcoming = cur.fetchall()

            # 5. История чата
            history_limit = 20 if admin else 10
            cur.execute(
                """
                SELECT role, message FROM (
                    SELECT role, message, created_at
                    FROM chat_history WHERE phone = %s
                    ORDER BY created_at DESC LIMIT %s
                ) sub ORDER BY created_at ASC
                """,
                (phone, history_limit),
            )
            chat_history = cur.fetchall()

            return {
                "client": client,
                "is_admin": admin,
                "visit_history": visit_history,
                "upcoming": upcoming,
                "chat_history": chat_history,
            }


# ==================== Администраторы ====================

def is_admin(phone: str) -> bool:
    """Проверить, является ли номер администратором."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM admin_users WHERE phone = %s AND is_active = TRUE",
                (phone,),
            )
            return cur.fetchone() is not None


def get_all_admin_phones() -> list[str]:
    """Получить список телефонов всех активных админов."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT phone FROM admin_users WHERE is_active = TRUE")
            phones = [row[0] for row in cur.fetchall()]
    # Fallback на ADMIN_PHONE если таблица пустая
    if not phones:
        from config import ADMIN_PHONE
        phones = [ADMIN_PHONE]
    return phones


# ==================== Напоминания ====================

def get_appointments_for_reminder(hours_before: int) -> list[dict]:
    """Получить записи, для которых нужно отправить напоминание."""
    from config import TIMEZONE

    # Определяем какое поле использовать для отслеживания
    if hours_before >= 24:
        reminder_field = "reminder_24h_sent"
    elif hours_before >= 2:
        reminder_field = "reminder_2h_sent"
    else:
        reminder_field = "reminder_1h_sent"

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Проверяем и добавляем колонку reminder_1h_sent если нужно (для обратной совместимости)
            if hours_before == 1:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'appointments' AND column_name = 'reminder_1h_sent'
                """)
                if not cur.fetchone():
                    # Колонка не существует - добавляем её
                    cur.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS reminder_1h_sent BOOLEAN DEFAULT FALSE")
                    conn.commit()
                    logger.info("Added reminder_1h_sent column to appointments table")

            # ВАЖНО: Используем часовой пояс для правильного сравнения времени
            cur.execute(
                f"""
                SELECT a.id, a.appointment_date, a.appointment_time,
                       c.name AS client_name, c.phone AS client_phone,
                       d.name AS doctor_name, s.name AS service_name
                FROM appointments a
                JOIN clients c ON a.client_id = c.id
                JOIN doctors d ON a.doctor_id = d.id
                JOIN services s ON a.service_id = s.id
                WHERE a.status = 'scheduled'
                      AND a.{reminder_field} = FALSE
                      AND (a.appointment_date + a.appointment_time)
                          BETWEEN (NOW() AT TIME ZONE %s) + make_interval(hours => %s) - interval '10 minutes'
                          AND (NOW() AT TIME ZONE %s) + make_interval(hours => %s) + interval '10 minutes'
                """,
                (TIMEZONE, hours_before, TIMEZONE, hours_before),
            )
            result = cur.fetchall()
            if result:
                logger.info(f"Found {len(result)} appointments for {hours_before}h reminder")
            return result


def mark_reminder_sent(appointment_id: int, hours_before: int):
    """Пометить, что напоминание отправлено."""
    if hours_before >= 24:
        field = "reminder_24h_sent"
    elif hours_before >= 2:
        field = "reminder_2h_sent"
    else:
        field = "reminder_1h_sent"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE appointments SET {field} = TRUE WHERE id = %s",
                (appointment_id,),
            )


def get_appointments_to_complete() -> list[dict]:
    """Получить записи, которые прошли более 1 часа назад и нужно отметить как завершённые."""
    from config import TIMEZONE

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.id, a.google_calendar_event_id,
                       c.name AS client_name, c.phone AS client_phone,
                       d.name AS doctor_name, s.name AS service_name
                FROM appointments a
                JOIN clients c ON a.client_id = c.id
                JOIN doctors d ON a.doctor_id = d.id
                JOIN services s ON a.service_id = s.id
                WHERE a.status = 'scheduled'
                      AND (a.appointment_date + a.appointment_time) < (NOW() AT TIME ZONE %s) - interval '1 hour'
                """,
                (TIMEZONE,),
            )
            return cur.fetchall()


def mark_appointment_completed(appointment_id: int) -> bool:
    """Отметить запись как завершённую."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE appointments SET status = 'completed', updated_at = NOW() WHERE id = %s AND status = 'scheduled'",
                (appointment_id,),
            )
            return cur.rowcount > 0


# ==================== Follow-up ====================

def schedule_follow_up(appointment_id: int, follow_up_date: date, notes: str = None) -> bool:
    """Установить дату повторного визита для записи."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE appointments SET follow_up_date = %s, follow_up_notes = %s
                WHERE id = %s AND status IN ('completed', 'scheduled')
                """,
                (follow_up_date, notes, appointment_id),
            )
            return cur.rowcount > 0


def get_upcoming_follow_ups(days_ahead: int = 3) -> list[dict]:
    """Получить follow-up записи, до которых осталось N дней."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.id, a.follow_up_date, a.follow_up_notes,
                       c.phone AS client_phone, c.name AS client_name,
                       d.name AS doctor_name, s.name AS service_name
                FROM appointments a
                JOIN clients c ON a.client_id = c.id
                JOIN doctors d ON a.doctor_id = d.id
                JOIN services s ON a.service_id = s.id
                WHERE a.follow_up_date IS NOT NULL
                      AND a.follow_up_date BETWEEN CURRENT_DATE AND CURRENT_DATE + %s
                      AND a.status = 'completed'
                """,
                (days_ahead,),
            )
            return cur.fetchall()


# ==================== No-show ====================

def mark_no_show(appointment_id: int) -> bool:
    """Отметить запись как неявку (no-show)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE appointments SET status = 'no_show', updated_at = NOW() WHERE id = %s AND status = 'scheduled'",
                (appointment_id,),
            )
            return cur.rowcount > 0


def get_today_unconfirmed() -> list[dict]:
    """Получить сегодняшние завершённые по времени записи, ещё не отмеченные (для подтверждения админом)."""
    from config import TIMEZONE
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.id, a.appointment_date, a.appointment_time,
                       c.name AS client_name, c.phone AS client_phone,
                       d.name AS doctor_name, s.name AS service_name
                FROM appointments a
                JOIN clients c ON a.client_id = c.id
                JOIN doctors d ON a.doctor_id = d.id
                JOIN services s ON a.service_id = s.id
                WHERE a.appointment_date = CURRENT_DATE
                      AND a.status = 'scheduled'
                      AND (a.appointment_date + a.appointment_time) < (NOW() AT TIME ZONE %s) - interval '30 minutes'
                ORDER BY a.appointment_time
                """,
                (TIMEZONE,),
            )
            return cur.fetchall()


# ==================== Блок-лист ====================

def block_client(phone: str, reason: str = None) -> bool:
    """Заблокировать клиента."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE clients SET is_blocked = TRUE, block_reason = %s WHERE phone = %s",
                (reason, phone),
            )
            return cur.rowcount > 0


def unblock_client(phone: str) -> bool:
    """Разблокировать клиента."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE clients SET is_blocked = FALSE, block_reason = NULL WHERE phone = %s",
                (phone,),
            )
            return cur.rowcount > 0


def is_client_blocked(phone: str) -> bool:
    """Проверить, заблокирован ли клиент."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT is_blocked FROM clients WHERE phone = %s",
                (phone,),
            )
            row = cur.fetchone()
            return row[0] if row else False


# ==================== Платежи ====================

def record_payment(appointment_id: int, actual_price: int, payment_status: str = "paid") -> bool:
    """Записать факт оплаты."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE appointments SET actual_price = %s, payment_status = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (actual_price, payment_status, appointment_id),
            )
            return cur.rowcount > 0


# ==================== Синхронизация цен ====================

def sync_services_from_list(services_data: list[dict]) -> int:
    """Синхронизировать услуги из списка (Google Sheets). Возвращает кол-во обновлённых."""
    updated = 0
    sheet_ids = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            for s in services_data:
                sheet_ids.append(s["id"])
                cur.execute(
                    """
                    INSERT INTO services (id, name, price, duration_minutes, description, is_active)
                    VALUES (%s, %s, %s, %s, %s, TRUE)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        price = EXCLUDED.price,
                        duration_minutes = EXCLUDED.duration_minutes,
                        description = EXCLUDED.description,
                        is_active = TRUE
                    """,
                    (s["id"], s["name"], s["price"], s["duration_minutes"], s.get("description", "")),
                )
                updated += cur.rowcount

            # Деактивировать услуги которых нет в Google Sheets
            if sheet_ids:
                cur.execute(
                    "UPDATE services SET is_active = FALSE WHERE id != ALL(%s) AND is_active = TRUE",
                    (sheet_ids,)
                )
                deactivated = cur.rowcount
                if deactivated:
                    logger.info(f"Deactivated {deactivated} services not in Sheets")
    return updated


# ==================== Очистка ====================

def cleanup_old_chat_history(days: int = 90) -> int:
    """Удалить сообщения из chat_history старше N дней. Возвращает количество удалённых."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM chat_history WHERE created_at < NOW() - make_interval(days => %s)",
                (days,),
            )
            deleted = cur.rowcount
            if deleted:
                logger.info(f"Cleaned up {deleted} old chat messages (>{days} days)")
            return deleted


# ==================== Отчеты ====================

def get_month_stats(year: int, month: int) -> dict:
    """Статистика за месяц."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Общее количество
            cur.execute(
                "SELECT COUNT(*) AS total FROM appointments WHERE appointment_date BETWEEN %s AND %s",
                (start, end - timedelta(days=1)),
            )
            total = cur.fetchone()["total"]

            # По статусам
            cur.execute(
                """
                SELECT status, COUNT(*) AS cnt FROM appointments
                WHERE appointment_date BETWEEN %s AND %s
                GROUP BY status
                """,
                (start, end - timedelta(days=1)),
            )
            by_status = {r["status"]: r["cnt"] for r in cur.fetchall()}

            # Новые клиенты
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM clients WHERE created_at BETWEEN %s AND %s",
                (start, end),
            )
            new_clients = cur.fetchone()["cnt"]

            # Общий доход (только завершенные + запланированные)
            cur.execute(
                """
                SELECT COALESCE(SUM(s.price), 0) AS revenue
                FROM appointments a
                JOIN services s ON a.service_id = s.id
                WHERE a.appointment_date BETWEEN %s AND %s
                      AND a.status IN ('completed', 'scheduled')
                """,
                (start, end - timedelta(days=1)),
            )
            revenue = cur.fetchone()["revenue"]

            # Топ врачей
            cur.execute(
                """
                SELECT d.name, COUNT(*) AS cnt
                FROM appointments a JOIN doctors d ON a.doctor_id = d.id
                WHERE a.appointment_date BETWEEN %s AND %s AND a.status != 'cancelled'
                GROUP BY d.name ORDER BY cnt DESC LIMIT 5
                """,
                (start, end - timedelta(days=1)),
            )
            top_doctors = cur.fetchall()

            return {
                "total": total,
                "scheduled": by_status.get("scheduled", 0),
                "completed": by_status.get("completed", 0),
                "cancelled": by_status.get("cancelled", 0),
                "no_show": by_status.get("no_show", 0),
                "new_clients": new_clients,
                "revenue": int(revenue),
                "top_doctors": top_doctors,
            }
