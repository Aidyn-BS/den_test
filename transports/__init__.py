"""
Transport layer — абстракция мессенджеров.
"""

from .whatsapp_transport import WhatsAppTransport
from .telegram_transport import TelegramTransport


_transports = {}


def get_transport(source: str = "whatsapp"):
    """Получить transport по источнику сообщения."""
    if source not in _transports:
        if source == "whatsapp":
            _transports[source] = WhatsAppTransport()
        elif source == "telegram":
            _transports[source] = TelegramTransport()
        else:
            raise ValueError(f"Unknown transport: {source}")
    return _transports[source]
