"""
WhatsApp transport — обёртка над существующим whatsapp.py.
Не модифицирует whatsapp.py.
"""

import logging
from .base import BaseTransport
from whatsapp import get_provider

logger = logging.getLogger(__name__)


class WhatsAppTransport(BaseTransport):
    def __init__(self):
        self._provider = get_provider()

    def send_message(self, phone: str, text: str) -> bool:
        """Отправить сообщение через GREEN-API."""
        return self._provider.send_message(phone, text)

    def send_to_chat(self, chat_id, text: str) -> bool:
        """WhatsApp не использует chat_id — перенаправляем на send_message."""
        return self.send_message(chat_id, text)
