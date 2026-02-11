"""
Выполнение функций (function calling).
Извлечено из ai_agent.py: execute_function, _call_function.
"""

import json
import logging
from datetime import date, time, datetime, timedelta

import pytz

import db
import google_calendar
import google_sheets
from config import (
    TIMEZONE, CLINIC_NAME, CLINIC_ADDRESS, CLINIC_PHONE, CLINIC_HOURS,
)
from transports import get_transport
from . import validator
from . import notifications

logger = logging.getLogger(__name__)


def execute_function(name: str, args: dict, phone: str, is_admin: bool) -> str:
    """Вызвать функцию и вернуть результат как строку JSON."""
    try:
        result = _call_function(name, args, phone, is_admin)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"Function {name} error: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _call_function(name: str, args: dict, phone: str, is_admin: bool) -> dict:
    """Внутренняя логика вызова функций."""
    tz = pytz.timezone(TIMEZONE)
    today = datetime.now(tz).date()

    if name == "get_clinic_info":
        hours = "\n".join(f"{d}: {h}" for d, h in CLINIC_HOURS.items())
        return {
            "name": CLINIC_NAME,
            "address": CLINIC_ADDRESS,
            "phone": CLINIC_PHONE,
            "hours": hours,
            "cancellation_policy": "Отмена не позднее чем за 2 часа до приема",
        }

    elif name == "get_services":
        services = db.get_services()
        logger.info(f"get_services: loaded {len(services)} services")
        return {"services": services}

    elif name == "get_doctors":
        doctors = db.get_doctors()
        return {"doctors": doctors}

    elif name == "get_free_slots":
        target = date.fromisoformat(args["date"])
        doctor_id = args.get("doctor_id")
        slots = db.get_free_slots(target, doctor_id)
        if not slots:
            return {"message": "На эту дату нет свободных окон", "slots": []}
        return {"date": str(target), "slots": slots}

    elif name == "create_appointment":
        # Админ НЕ может записать сам себя как пациента
        if is_admin and not args.get("patient_name"):
            return {"error": "Вы администратор. Записи создаются только для пациентов. Укажите имя и телефон пациента."}

        # Убедимся, что клиент существует
        client = db.get_client(phone)
        if not client:
            db.create_client(phone)

        appt_date = date.fromisoformat(args["date"])
        appt_time = time.fromisoformat(args["time"])

        # Валидация через validator
        v = validator.validate_appointment_time(appt_date, appt_time)
        if not v["valid"]:
            return {"error": v["error"]}
        if v["corrected_time"]:
            appt_time = v["corrected_time"]

        # Найти врача по имени
        doctor_name = args.get("doctor_name", "")
        doctors = db.get_doctors()
        doctor = validator.find_doctor_by_name(doctor_name, doctors)
        if not doctor:
            return {"error": f"Врач '{doctor_name}' не найден. Доступные врачи: {', '.join(d['name'] for d in doctors)}"}

        # Найти услугу по названию
        service_name = args.get("service_name", "")
        services = db.get_services()
        service = validator.find_service_by_name(service_name, services)
        if not service:
            return {"error": f"Услуга '{service_name}' не найдена. Доступные услуги: {', '.join(s['name'] for s in services)}"}

        logger.info(f"Creating appointment: doctor={doctor['name']} (id={doctor['id']}), service={service['name']} (id={service['id']})")

        appt = db.create_appointment(
            client_phone=phone,
            doctor_id=doctor["id"],
            service_id=service["id"],
            appt_date=appt_date,
            appt_time=appt_time,
            notes=args.get("notes"),
            patient_name=args.get("patient_name"),
        )

        if not appt:
            return {"error": "Не удалось создать запись. Возможно, это время уже занято."}

        # Google Calendar
        event_id = google_calendar.create_event(appt)
        if event_id:
            db.update_appointment_calendar_id(appt["id"], event_id)

        # Google Sheets — автоматически добавляем запись
        google_sheets.add_appointment(appt)

        # Уведомить админа (исключая текущего, если он сам админ)
        notifications.notify_admin_new_appointment(appt, exclude_phone=phone if is_admin else None)

        result = {
            "success": True,
            "appointment_id": appt["id"],
            "doctor": appt["doctor_name"],
            "service": appt["service_name"],
            "date": str(appt["appointment_date"]),
            "time": str(appt["appointment_time"])[:5],
            "price": appt["price"],
        }
        if appt.get("patient_name"):
            result["patient_name"] = appt["patient_name"]
        return result

    elif name == "create_combo_appointment":
        # Админ НЕ может записать сам себя
        if is_admin and not args.get("patient_name"):
            return {"error": "Вы администратор. Записи создаются только для пациентов. Укажите имя и телефон пациента."}

        client = db.get_client(phone)
        if not client:
            db.create_client(phone)

        appt_date = date.fromisoformat(args["date"])
        appt_time_1 = time.fromisoformat(args["time"])

        # Валидация через validator (дата, 60 дней, :00/:30)
        v = validator.validate_appointment_time(appt_date, appt_time_1)
        if not v["valid"]:
            return {"error": v["error"]}
        if v["corrected_time"]:
            appt_time_1 = v["corrected_time"]

        # Находим врача
        doctor_name = args.get("doctor_name", "")
        doctors = db.get_doctors()
        doctor = validator.find_doctor_by_name(doctor_name, doctors)
        if not doctor:
            return {"error": f"Врач '{doctor_name}' не найден"}

        # Находим обе услуги
        services = db.get_services()
        service_1 = validator.find_service_by_name(args.get("service_name_1", ""), services)
        service_2 = validator.find_service_by_name(args.get("service_name_2", ""), services)

        if not service_1:
            return {"error": f"Услуга 1 '{args.get('service_name_1')}' не найдена"}
        if not service_2:
            return {"error": f"Услуга 2 '{args.get('service_name_2')}' не найдена"}

        patient_name = args.get("patient_name")

        # Создаём первую запись
        appt1 = db.create_appointment(
            client_phone=phone, doctor_id=doctor["id"], service_id=service_1["id"],
            appt_date=appt_date, appt_time=appt_time_1, patient_name=patient_name,
        )
        if not appt1:
            return {"error": "Не удалось создать первую запись — время занято."}

        # Рассчитываем время второй услуги
        appt_time_2_dt = datetime.combine(appt_date, appt_time_1) + timedelta(minutes=service_1["duration_minutes"])
        appt_time_2 = appt_time_2_dt.time()

        # Создаём вторую запись
        appt2 = db.create_appointment(
            client_phone=phone, doctor_id=doctor["id"], service_id=service_2["id"],
            appt_date=appt_date, appt_time=appt_time_2, patient_name=patient_name,
        )
        if not appt2:
            # Откатываем первую
            db.cancel_appointment(appt1["id"], reason="Комбо-запись: вторая услуга не влезла")
            return {"error": f"Первая услуга записана, но для второй ({service_2['name']}) нет места в {appt_time_2.strftime('%H:%M')}. Запись отменена."}

        # Google Calendar + Sheets
        for appt in [appt1, appt2]:
            event_id = google_calendar.create_event(appt)
            if event_id:
                db.update_appointment_calendar_id(appt["id"], event_id)
            google_sheets.add_appointment(appt)

        notifications.notify_admin_new_appointment(appt1, exclude_phone=phone if is_admin else None)
        notifications.notify_admin_new_appointment(appt2, exclude_phone=phone if is_admin else None)

        total_price = (appt1.get("price", 0) or 0) + (appt2.get("price", 0) or 0)
        total_minutes = (service_1["duration_minutes"]) + (service_2["duration_minutes"])

        return {
            "success": True,
            "combo": True,
            "appointment_1": {"id": appt1["id"], "service": appt1["service_name"], "time": str(appt1["appointment_time"])[:5]},
            "appointment_2": {"id": appt2["id"], "service": appt2["service_name"], "time": str(appt2["appointment_time"])[:5]},
            "doctor": doctor["name"],
            "date": str(appt_date),
            "total_price": total_price,
            "total_minutes": total_minutes,
        }

    elif name == "cancel_appointment":
        appt_id = args["appointment_id"]
        reason = args.get("reason")
        client_phone = phone if not is_admin else None

        logger.info(f"CANCEL: appointment_id={appt_id}, is_admin={is_admin}, client_phone={client_phone}")

        # Проверяем существует ли запись вообще
        existing = db.get_appointment_by_id(appt_id)
        if existing:
            logger.info(f"CANCEL: Found appointment id={appt_id}, status={existing.get('status')}, client={existing.get('client_name')}")
        else:
            logger.warning(f"CANCEL: Appointment id={appt_id} NOT FOUND in DB!")

        # Получаем данные записи ДО отмены (для уведомления пациента)
        appt_before = existing if is_admin else None

        result = db.cancel_appointment(appt_id, client_phone, reason=reason)

        # Если не удалось и это админ — попробуем найти правильную активную запись
        if not result and is_admin:
            logger.warning(f"CANCEL FAILED for id={appt_id}, trying to find correct active appointment...")
            active_appts = db.get_all_upcoming_appointments()
            if active_appts and len(active_appts) == 1:
                correct_id = active_appts[0]["id"]
                logger.info(f"CANCEL AUTO-FIX: Found 1 active appointment, real id={correct_id}")
                appt_before = db.get_appointment_by_id(correct_id)
                result = db.cancel_appointment(correct_id, None, reason=reason)
                if result:
                    appt_id = correct_id

        if not result:
            logger.warning(f"CANCEL FAILED FINAL: id={appt_id}")
            return {"error": f"Запись id={appt_id} не найдена или уже отменена. Вызови get_my_appointments чтобы получить актуальные ID."}

        # Отметить в календаре как отменённое (красный цвет) + причина
        if result.get("google_calendar_event_id"):
            google_calendar.cancel_event(result["google_calendar_event_id"], reason=reason)

        # Обновить статус в Google Sheets + причина
        google_sheets.update_appointment_status(appt_id, "cancelled", reason=reason)

        # Уведомить админа (исключая текущего, если он сам админ) + причина
        notifications.notify_admin_cancellation(appt_id, exclude_phone=phone if is_admin else None, reason=reason)

        # Если админ отменил — уведомить пациента
        if is_admin and appt_before and appt_before.get("client_phone"):
            notifications.notify_patient_cancellation(appt_before)

        return {"success": True, "message": "Запись отменена"}

    elif name == "reschedule_appointment":
        appt_id = args["appointment_id"]
        new_date = date.fromisoformat(args["new_date"])
        new_time = time.fromisoformat(args["new_time"])

        # Валидация через validator
        v = validator.validate_reschedule_time(new_date, new_time)
        if not v["valid"]:
            return {"error": v["error"]}
        if v["corrected_time"]:
            new_time = v["corrected_time"]

        client_phone = phone if not is_admin else None

        result = db.reschedule_appointment(appt_id, new_date, new_time, client_phone)

        if not result:
            return {"error": "Запись не найдена или не принадлежит этому клиенту. Вызови get_my_appointments чтобы получить актуальный список записей."}

        if isinstance(result, dict) and result.get("error") == "conflict":
            return {"error": f"Время {new_time.strftime('%H:%M')} на {new_date.strftime('%d.%m.%Y')} уже занято. Предложи клиенту другое время или покажи свободные слоты через get_free_slots."}

        # Обновить в календаре (жёлтый цвет)
        if result.get("google_calendar_event_id"):
            google_calendar.update_event(
                result["google_calendar_event_id"], new_date, new_time
            )

        # Обновить статус в Google Sheets
        google_sheets.update_appointment_status(appt_id, "rescheduled", new_date, new_time)

        # Уведомить админа (передаём старые дату/время)
        old_date = result.get("old_date")
        old_time = result.get("old_time")
        notifications.notify_admin_reschedule(appt_id, new_date, new_time, old_date, old_time, exclude_phone=phone if is_admin else None)

        # Если админ перенёс — уведомить пациента
        if is_admin:
            notifications.notify_patient_reschedule(appt_id, new_date, new_time, old_date, old_time)

        return {
            "success": True,
            "new_date": str(new_date),
            "new_time": str(new_time)[:5],
        }

    elif name == "get_my_appointments":
        if is_admin:
            appts = db.get_all_upcoming_appointments()
            if not appts:
                return {"message": "В клинике нет предстоящих записей пациентов."}
            for a in appts:
                a["appointment_id"] = a.pop("id")
            ids = [a["appointment_id"] for a in appts]
            logger.info(f"ADMIN get_my_appointments: returning {len(appts)} appointments, IDs: {ids}")
            return {
                "info": f"Записи пациентов клиники. Для отмены используй appointment_id из списка ниже. ID записей: {ids}",
                "clinic_appointments": appts,
                "total": len(appts),
            }
        else:
            appts = db.get_client_appointments(phone)
            if not appts:
                return {"message": "У вас нет предстоящих записей"}
            for a in appts:
                a["appointment_id"] = a.pop("id")
            return {"appointments": appts}

    elif name == "save_client_name":
        client_name = args["name"]
        client = db.get_client(phone)
        if client:
            db.update_client_name(phone, client_name)
        else:
            db.create_client(phone, client_name)
        return {"success": True, "name": client_name}

    elif name == "notify_emergency":
        client = db.get_client(phone)
        client_name = client.get("name", "—") if client else "—"
        notifications.send_to_all_admins(
            f"🚨 *ЭКСТРЕННЫЙ ПАЦИЕНТ!*\n\n"
            f"Клиент: {client_name} ({phone})\n"
            f"Ситуация: {args.get('description', '—')}\n\n"
            f"Требуется срочный приём!")
        return {"success": True, "message": "Администратор уведомлён о вашей ситуации."}

    # ---------- Админские функции ----------

    elif name == "set_doctor_absence":
        if not is_admin:
            return {"error": "Эта функция доступна только администратору"}

        doctor_name = args.get("doctor_name", "")
        doctors = db.get_doctors()
        doctor = validator.find_doctor_by_name(doctor_name, doctors)
        if not doctor:
            return {"error": f"Врач '{doctor_name}' не найден"}

        start = date.fromisoformat(args["start_date"])
        end = date.fromisoformat(args["end_date"])
        reason = args.get("reason", "sick")

        result = db.set_doctor_absence(doctor["id"], start, end, reason)

        # Уведомляем затронутых пациентов
        affected = result.get("affected_patients", [])
        if affected:
            transport = get_transport("whatsapp")
            reason_text = {"sick": "по болезни", "vacation": "по причине отпуска", "other": "по уважительной причине"}.get(reason, "")
            for patient in affected:
                transport.send_message(patient["client_phone"],
                    f"Уважаемый(ая) {patient.get('client_name', 'клиент')}!\n\n"
                    f"К сожалению, ваша запись на {patient['appointment_date']} в {str(patient['appointment_time'])[:5]} "
                    f"({patient['service_name']}) отменена {reason_text}.\n\n"
                    f"Напишите нам, чтобы записаться к другому врачу или на другую дату.")

                if patient.get("google_calendar_event_id"):
                    google_calendar.cancel_event(patient["google_calendar_event_id"])

        return {
            "success": True,
            "doctor": doctor["name"],
            "period": f"{start} — {end}",
            "reason": reason,
            "cancelled_appointments": result["cancelled_count"],
            "patients_notified": len(affected),
        }

    elif name == "schedule_follow_up":
        if not is_admin:
            return {"error": "Только для администратора"}
        appt_id = args["appointment_id"]
        fu_date = date.fromisoformat(args["follow_up_date"])
        notes = args.get("notes")
        ok = db.schedule_follow_up(appt_id, fu_date, notes)
        if not ok:
            return {"error": "Запись не найдена или не завершена"}
        return {"success": True, "appointment_id": appt_id, "follow_up_date": str(fu_date)}

    elif name == "mark_no_show":
        if not is_admin:
            return {"error": "Только для администратора"}
        appt_id = args["appointment_id"]
        ok = db.mark_no_show(appt_id)
        if not ok:
            return {"error": "Запись не найдена или уже не scheduled"}
        google_sheets.update_appointment_status(appt_id, "cancelled")
        return {"success": True, "message": f"Запись {appt_id} отмечена как неявка (no-show)"}

    elif name == "block_patient":
        if not is_admin:
            return {"error": "Только для администратора"}
        target_phone = args["phone"]
        reason = args.get("reason", "")
        ok = db.block_client(target_phone, reason)
        if not ok:
            return {"error": f"Клиент с номером {target_phone} не найден"}
        return {"success": True, "message": f"Клиент {target_phone} заблокирован"}

    elif name == "unblock_patient":
        if not is_admin:
            return {"error": "Только для администратора"}
        target_phone = args["phone"]
        ok = db.unblock_client(target_phone)
        if not ok:
            return {"error": f"Клиент с номером {target_phone} не найден"}
        return {"success": True, "message": f"Клиент {target_phone} разблокирован"}

    elif name == "record_payment":
        if not is_admin:
            return {"error": "Только для администратора"}
        appt_id = args["appointment_id"]
        actual_price = args["actual_price"]
        pay_status = args.get("payment_status", "paid")
        ok = db.record_payment(appt_id, actual_price, pay_status)
        if not ok:
            return {"error": "Запись не найдена"}
        return {"success": True, "appointment_id": appt_id, "actual_price": actual_price, "payment_status": pay_status}

    elif name == "get_today_schedule":
        appts = db.get_appointments_by_date(today)
        return {"date": str(today), "count": len(appts), "appointments": appts}

    elif name == "get_week_report":
        end = today + timedelta(days=7)
        appts = db.get_appointments_range(today, end)
        return {"from": str(today), "to": str(end), "count": len(appts), "appointments": appts}

    elif name == "get_month_report":
        year = args.get("year", today.year)
        month = args.get("month", today.month)
        stats = db.get_month_stats(year, month)
        return {"year": year, "month": month, "stats": stats}

    elif name == "export_to_sheets":
        period = args.get("period", "day")
        if period == "day":
            appts = db.get_appointments_by_date(today)
            google_sheets.export_appointments(appts, f"Записи за {today}")
        elif period == "week":
            end = today + timedelta(days=7)
            appts = db.get_appointments_range(today, end)
            google_sheets.export_appointments(appts, f"Записи {today}–{end}")
        elif period == "month":
            stats = db.get_month_stats(today.year, today.month)
            month_names = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                           "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
            google_sheets.export_month_stats(stats, f"{month_names[today.month]} {today.year}")
        return {"success": True, "message": f"Отчет ({period}) экспортирован в Google Sheets"}

    return {"error": f"Неизвестная функция: {name}"}
