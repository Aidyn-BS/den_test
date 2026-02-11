"""
Базовый класс транспорта (ABC).
"""

from abc import ABC, abstractmethod


class BaseTransport(ABC):
    @abstractmethod
    def send_message(self, phone: str, text: str) -> bool:
        """Отправить сообщение по номеру телефона."""
        ...

    @abstractmethod
    def send_to_chat(self, chat_id, text: str) -> bool:
        """Отправить сообщение в конкретный чат (chat_id)."""
        ...
