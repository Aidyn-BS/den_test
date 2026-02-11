"""
Фоновые задачи:
  - Напоминания клиентам (за 24ч, 2ч, 1ч)
  - Автозавершение записей (через 1 час после приёма)
  - Ежедневный отчет администратору в 09:00
"""

import logging
import os
from datetime import date, datetime, timedelta

import pytz
from apscheduler.schedulers.background import BackgroundScheduler

import db
import google_calendar
import google_sheets
from whatsapp import get_provider
from config import ADMIN_PHONE, TIMEZONE, REMINDER_HOURS, DB_CONFIG

logger = logging.getLogger(__name__)


def send_reminders():
    """Проверить и отправить напоминания клиентам."""
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    logger.info(f"Checking reminders at {now.strftime('%Y-%m-%d %H:%M:%S')} ({TIMEZONE})")

    wp = get_provider()

    for hours in REMINDER_HOURS:
        appointments = db.get_appointments_for_reminder(hours)
        logger.info(f"  {hours}h reminder: found {len(appointments)} appointments")

        for appt in appointments:
            if hours >= 24:
                text = (
                    f"🔔 *Напоминание о записи!*\n\n"
                    f"Завтра у вас прием:\n"
                    f"🕐 Время: {str(appt['appointment_time'])[:5]}\n"
                    f"👨‍⚕️ Врач: {appt['doctor_name']}\n"
                    f"🦷 Услуга: {appt['service_name']}\n\n"
                    f"Если не можете прийти — напишите нам заранее."
                )
            elif hours >= 2:
                text = (
                    f"🔔 *Прием через {hours} часа!*\n\n"
                    f"🕐 Время: {str(appt['appointment_time'])[:5]}\n"
                    f"👨‍⚕️ Врач: {appt['doctor_name']}\n\n"
                    f"Ждём вас! Приезжайте немного раньше."
                )
            else:
                text = (
                    f"🔔 *Прием через 1 час!*\n\n"
                    f"🕐 Время: {str(appt['appointment_time'])[:5]}\n"
                    f"👨‍⚕️ Врач: {appt['doctor_name']}\n"
                    f"📍 Не забудьте взять документы!\n\n"
                    f"До встречи!"
                )

            sent = wp.send_message(appt["client_phone"], text)
            if sent:
                db.mark_reminder_sent(appt["id"], hours)
                logger.info(f"Reminder ({hours}h) sent to {appt['client_phone']}")


def complete_appointments():
    """Автоматически завершить записи, которые прошли более 1 часа назад."""
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    logger.info(f"Checking appointments to complete at {now.strftime('%H:%M')}")

    appointments = db.get_appointments_to_complete()

    if not appointments:
        logger.info("  No appointments to complete")
        return

    logger.info(f"  Found {len(appointments)} appointments to mark as completed")

    for appt in appointments:
        # Обновляем статус в БД
        if db.mark_appointment_completed(appt["id"]):
            # Обновляем цвет в Google Calendar (серый)
            if appt.get("google_calendar_event_id"):
                google_calendar.complete_event(appt["google_calendar_event_id"])

            # Обновляем статус в Google Sheets (серый фон)
            google_sheets.update_appointment_status(appt["id"], "completed")

            logger.info(f"  Appointment {appt['id']} marked as completed")


def _send_to_all_admins(msg: str):
    """Отправить сообщение всем активным админам."""
    from agents.notifications import send_to_all_admins
    send_to_all_admins(msg)


def send_daily_report():
    """Отправить всем админам список записей на сегодня (каждый день в 09:00)."""
    today = date.today()

    appointments = db.get_appointments_by_date(today)

    if not appointments:
        _send_to_all_admins(f"📅 *Записи на {today.strftime('%d.%m.%Y')}*\n\nНа сегодня записей нет.")
        return

    text = f"📅 *Записи на сегодня ({today.strftime('%d.%m.%Y')}):*\n\n"

    for i, appt in enumerate(appointments, 1):
        text += (
            f"{i}. ⏰ {str(appt['appointment_time'])[:5]}\n"
            f"   👤 {appt.get('client_name', '—')} ({appt.get('client_phone', '')})\n"
            f"   👨‍⚕️ {appt['doctor_name']}\n"
            f"   🦷 {appt['service_name']}\n\n"
        )

    text += f"*Итого: {len(appointments)} записей*"

    _send_to_all_admins(text)
    logger.info(f"Daily report sent: {len(appointments)} appointments")


def sync_prices_from_sheets():
    """Синхронизировать услуги из Google Sheets в БД."""
    try:
        import google_config
        google_config.clear_cache()  # Сбросить кэш для свежих данных
        services = google_config.get_services()
        if services:
            updated = db.sync_services_from_list(services)
            logger.info(f"Sheets sync: {len(services)} services loaded, {updated} updated in DB")
        else:
            logger.warning("Sheets sync: Google Sheets returned empty, DB not updated")
    except Exception as e:
        logger.error(f"Sheets sync error: {e}")


def send_follow_up_reminders():
    """Напомнить пациентам о повторных визитах (за 3 дня)."""
    try:
        follow_ups = db.get_upcoming_follow_ups(days_ahead=3)
        if not follow_ups:
            return
        wp = get_provider()
        for fu in follow_ups:
            wp.send_message(fu["client_phone"],
                f"🔔 *Напоминание о повторном визите*\n\n"
                f"Вам назначен повторный приём на *{fu['follow_up_date']}*.\n"
                f"Врач: {fu['doctor_name']}\n"
                f"Услуга: {fu['service_name']}\n"
                f"{('Заметка: ' + fu['follow_up_notes']) if fu.get('follow_up_notes') else ''}\n\n"
                f"Напишите нам чтобы записаться на удобное время!")
            logger.info(f"Follow-up reminder sent to {fu['client_phone']}")
    except Exception as e:
        logger.error(f"Follow-up reminder error: {e}")


def send_evening_confirmation():
    """Вечерний отчёт админу: записи на сегодня, которые нужно подтвердить (no-show?)."""
    try:
        unconfirmed = db.get_today_unconfirmed()
        if not unconfirmed:
            return
        wp = get_provider()
        text = "📋 *Подтвердите посещения за сегодня:*\n\n"
        for u in unconfirmed:
            text += (
                f"• ID {u['id']}: {str(u['appointment_time'])[:5]} — "
                f"{u.get('client_name', '—')} ({u['service_name']})\n"
            )
        text += "\nОтметьте no-show если пациент не пришёл."
        _send_to_all_admins(text)
        logger.info(f"Evening confirmation sent: {len(unconfirmed)} unconfirmed")
    except Exception as e:
        logger.error(f"Evening confirmation error: {e}")


def cleanup_chat_history():
    """Удалить сообщения старше 90 дней."""
    try:
        deleted = db.cleanup_old_chat_history(days=90)
        if deleted:
            logger.info(f"Chat history cleanup: removed {deleted} old messages")
    except Exception as e:
        logger.error(f"Chat history cleanup error: {e}")


def start_scheduler():
    """Запустить фоновый планировщик.
    При наличии SQLAlchemy — использует PostgreSQL jobstore (защита от дублирования при нескольких инстансах).
    """
    tz = pytz.timezone(TIMEZONE)

    # Пытаемся использовать PostgreSQL jobstore для защиты от дублей
    jobstores = {}
    try:
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        db_url = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG.get('port', 5432)}/{DB_CONFIG['dbname']}"
        jobstores["default"] = SQLAlchemyJobStore(url=db_url)
        logger.info("Scheduler using PostgreSQL jobstore (instance-safe)")
    except ImportError:
        logger.info("SQLAlchemy not installed, using in-memory jobstore")
    except Exception as e:
        logger.warning(f"Failed to init PostgreSQL jobstore: {e}, using in-memory")

    scheduler = BackgroundScheduler(timezone=tz, jobstores=jobstores)

    # Ежедневный отчет в 09:00
    scheduler.add_job(
        send_daily_report,
        "cron",
        hour=9,
        minute=0,
        id="daily_report", replace_existing=True,
    )

    # Проверка напоминаний каждые 5 минут
    scheduler.add_job(
        send_reminders,
        "interval",
        minutes=5,
        id="reminders", replace_existing=True,
    )

    # Автозавершение записей каждые 10 минут
    scheduler.add_job(
        complete_appointments,
        "interval",
        minutes=10,
        id="complete_appointments", replace_existing=True,
    )

    # Очистка старой истории чата — каждый день в 03:00
    scheduler.add_job(
        cleanup_chat_history,
        "cron",
        hour=3,
        minute=0,
        id="cleanup_chat_history", replace_existing=True,
    )

    # Синхронизация услуг из Google Sheets — раз в день в 4:00
    scheduler.add_job(
        sync_prices_from_sheets,
        "cron",
        hour=4,
        minute=0,
        id="sync_prices", replace_existing=True,
    )

    # Принудительная синхронизация при запуске
    sync_prices_from_sheets()

    # Напоминания о повторных визитах — каждый день в 10:00
    scheduler.add_job(
        send_follow_up_reminders,
        "cron",
        hour=10,
        minute=0,
        id="follow_up_reminders", replace_existing=True,
    )

    # Вечерний отчёт для подтверждения посещений — 19:00
    scheduler.add_job(
        send_evening_confirmation,
        "cron",
        hour=19,
        minute=0,
        id="evening_confirmation", replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started: report 09:00, reminders 5min, complete 10min, cleanup 03:00, "
                "follow-up 10:00, sheets-sync 04:00, confirm 19:00")
    return scheduler
