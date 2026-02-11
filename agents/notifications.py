"""
Уведомления администраторам и пациентам.
Извлечено из ai_agent.py. Единая точка отправки уведомлений.
Используется и в agents/functions.py, и в scheduler.py.
"""

import logging

import db
from transports import get_transport

logger = logging.getLogger(__name__)


def _send_to_phone(phone: str, msg: str):
    """Отправить сообщение по номеру телефона через ВСЕ доступные каналы (WhatsApp + Telegram)."""
    # WhatsApp — основной канал
    try:
        get_transport("whatsapp").send_message(phone, msg)
    except Exception as e:
        logger.error(f"WhatsApp send error for {phone}: {e}")

    # Telegram — дополнительный канал (если пользователь привязал аккаунт)
    try:
        import telegram_db
        chat_id = telegram_db.get_telegram_chat_id(phone)
        if chat_id:
            get_transport("telegram").send_to_chat(chat_id, msg)
    except Exception as e:
        logger.debug(f"Telegram send skipped for {phone}: {e}")


def send_to_all_admins(msg: str, exclude_phone: str = None):
    """Отправить сообщение всем активным админам через все каналы."""
    admin_phones = db.get_all_admin_phones()
    for phone in admin_phones:
        if phone != exclude_phone:
            _send_to_phone(phone, msg)


def notify_admin_new_appointment(appt: dict, exclude_phone: str = None):
    """Уведомить всех админов о новой записи."""
    msg = (
        f"📌 *Новая запись!*\n\n"
        f"Клиент: {appt.get('client_name', '—')}\n"
        f"Тел: {appt.get('client_phone', '—')}\n"
        f"Врач: {appt.get('doctor_name', '—')}\n"
        f"Услуга: {appt.get('service_name', '—')}\n"
        f"Дата: {appt.get('appointment_date')}\n"
        f"Время: {str(appt.get('appointment_time', ''))[:5]}\n"
        f"Цена: {appt.get('price', '—')} ₸"
    )
    send_to_all_admins(msg, exclude_phone=exclude_phone)


def notify_admin_cancellation(appointment_id: int, exclude_phone: str = None, reason: str = None):
    """Уведомить всех админов об отмене."""
    appt = db.get_appointment_by_id(appointment_id)
    if not appt:
        return
    # Причина: из аргумента или из БД
    cancel_reason = reason or appt.get("cancellation_reason")
    msg = (
        f"❌ *Запись отменена*\n\n"
        f"Клиент: {appt.get('client_name', '—')}\n"
        f"Было: {appt.get('appointment_date')} в {str(appt.get('appointment_time', ''))[:5]}\n"
        f"Услуга: {appt.get('service_name', '—')}"
    )
    if cancel_reason:
        msg += f"\nПричина: {cancel_reason}"
    send_to_all_admins(msg, exclude_phone=exclude_phone)


def notify_admin_reschedule(appointment_id: int, new_date, new_time, old_date=None, old_time=None, exclude_phone: str = None):
    """Уведомить всех админов о переносе."""
    appt = db.get_appointment_by_id(appointment_id)
    if not appt:
        return
    was_date = old_date or "—"
    was_time = str(old_time or "—")[:5]
    msg = (
        f"📅 *Запись перенесена*\n\n"
        f"Клиент: {appt.get('client_name', '—')}\n"
        f"Тел: {appt.get('client_phone', '—')}\n"
        f"Было: {was_date} в {was_time}\n"
        f"Стало: {new_date} в {str(new_time)[:5]}\n"
        f"Услуга: {appt.get('service_name', '—')}"
    )
    send_to_all_admins(msg, exclude_phone=exclude_phone)


def notify_patient_cancellation(appt: dict):
    """Уведомить пациента что админ отменил его запись."""
    patient_phone = appt.get("client_phone")
    if not patient_phone:
        return
    msg = (
        f"Здравствуйте! Сообщаем, что ваша запись была отменена администратором.\n\n"
        f"📋 *Отменённая запись:*\n"
        f"Врач: {appt.get('doctor_name', '—')}\n"
        f"Услуга: {appt.get('service_name', '—')}\n"
        f"Дата: {appt.get('appointment_date')}\n"
        f"Время: {str(appt.get('appointment_time', ''))[:5]}\n\n"
        f"Если хотите записаться на другое время — просто напишите нам!"
    )
    _send_to_phone(patient_phone, msg)


def notify_patient_reschedule(appointment_id: int, new_date, new_time, old_date=None, old_time=None):
    """Уведомить пациента что админ перенёс его запись."""
    appt = db.get_appointment_by_id(appointment_id)
    if not appt:
        return
    patient_phone = appt.get("client_phone")
    if not patient_phone:
        return
    was_date = old_date or "—"
    was_time = str(old_time or "—")[:5]
    msg = (
        f"Здравствуйте! Сообщаем, что ваша запись была перенесена.\n\n"
        f"📋 *Было:* {was_date} в {was_time}\n"
        f"📋 *Стало:* {new_date} в {str(new_time)[:5]}\n"
        f"Врач: {appt.get('doctor_name', '—')}\n"
        f"Услуга: {appt.get('service_name', '—')}\n\n"
        f"Если это время вам не подходит — напишите нам, и мы подберём другое!"
    )
    _send_to_phone(patient_phone, msg)


def notify_admin_api_down():
    """Уведомить всех админов что AI-сервис недоступен."""
    try:
        send_to_all_admins(
            "⚠️ *ВНИМАНИЕ:* AI-сервис (OpenRouter) недоступен.\n"
            "Бот не может обрабатывать сообщения пациентов.\n"
            "Проверьте баланс и статус API.")
    except Exception:
        pass
