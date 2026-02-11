"""
Функции БД для Telegram-интеграции.
Использует пул соединений из db.py.
Отделено от db.py чтобы не модифицировать основной модуль.
"""

import logging
from db import get_conn

logger = logging.getLogger(__name__)


def get_telegram_chat_id(phone: str) -> int | None:
    """Получить Telegram chat_id по номеру телефона."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT telegram_chat_id FROM telegram_users WHERE phone = %s",
                (phone,)
            )
            row = cur.fetchone()
            return row[0] if row else None


def get_phone_by_telegram_chat_id(chat_id: int) -> str | None:
    """Получить номер телефона по Telegram chat_id."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT phone FROM telegram_users WHERE telegram_chat_id = %s",
                (chat_id,)
            )
            row = cur.fetchone()
            return row[0] if row else None


def link_telegram_user(chat_id: int, phone: str, username: str = ""):
    """Привязать Telegram chat_id к номеру телефона."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO telegram_users (telegram_chat_id, phone, username)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (telegram_chat_id)
                   DO UPDATE SET phone = EXCLUDED.phone, username = EXCLUDED.username""",
                (chat_id, phone, username)
            )
    logger.info(f"Linked Telegram chat_id={chat_id} to phone={phone}")
