"""
WhatsApp интеграция через GREEN-API (green-api.com).
"""

import requests
import logging

from config import GREEN_API_INSTANCE_ID, GREEN_API_TOKEN

logger = logging.getLogger(__name__)

# URL берётся из .env или собирается из instance ID
import os
GREEN_API_URL = os.getenv(
    "GREEN_API_URL",
    f"https://{GREEN_API_INSTANCE_ID[:4]}.api.greenapi.com" if GREEN_API_INSTANCE_ID else "https://api.green-api.com"
)


def normalize_phone(phone: str) -> str:
    """Приводит номер к формату +7XXXXXXXXXX."""
    phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if phone.endswith("@c.us"):
        phone = "+" + phone.replace("@c.us", "")
    if not phone.startswith("+"):
        phone = "+" + phone
    return phone


class GreenAPIProvider:
    """https://green-api.com — WhatsApp API для СНГ."""

    def __init__(self):
        self.instance_id = GREEN_API_INSTANCE_ID
        self.token = GREEN_API_TOKEN
        self.base_url = GREEN_API_URL
        logger.info(f"[GREEN-API] URL: {self.base_url}, instance: {self.instance_id}")

    def _url(self, method: str) -> str:
        return f"{self.base_url}/waInstance{self.instance_id}/{method}/{self.token}"

    def send_message(self, phone: str, text: str) -> bool:
        """Отправить текстовое сообщение."""
        try:
            chat_id = phone.lstrip("+") + "@c.us"
            resp = requests.post(
                self._url("sendMessage"),
                json={"chatId": chat_id, "message": text},
                timeout=10,
            )
            resp.raise_for_status()
            logger.info(f"[GREEN-API] Sent to {phone}")
            return True
        except Exception as e:
            logger.error(f"[GREEN-API] Send error: {e}")
            return False

    def parse_webhook(self, data: dict) -> dict | None:
        """Извлекает телефон, текст и тип из webhook GREEN-API.
        Поддерживает: текст, голосовые, фото, документы, видео.
        """
        try:
            type_msg = data.get("typeWebhook")
            if type_msg != "incomingMessageReceived":
                return None

            msg_data = data.get("messageData", {})
            type_message = msg_data.get("typeMessage", "")
            sender = data.get("senderData", {}).get("chatId", "")
            phone = normalize_phone(sender)
            id_message = data.get("idMessage", "")

            # Текстовые сообщения
            if type_message in ("textMessage", "extendedTextMessage"):
                text_data = msg_data.get("textMessageData") or msg_data.get("extendedTextMessageData")
                if not text_data:
                    return None
                text = text_data.get("textMessage") or text_data.get("text", "")
                return {"phone": phone, "text": text.strip(), "id_message": id_message, "type": "text"}

            # Голосовые сообщения
            if type_message in ("audioMessage", "voiceMessage"):
                file_data = msg_data.get("fileMessageData", {})
                download_url = file_data.get("downloadUrl", "")
                return {
                    "phone": phone, "text": "", "id_message": id_message,
                    "type": "audio", "download_url": download_url,
                }

            # Фото, видео, документы
            if type_message in ("imageMessage", "videoMessage", "documentMessage"):
                file_data = msg_data.get("fileMessageData", {})
                caption = file_data.get("caption", "")
                return {
                    "phone": phone, "text": caption, "id_message": id_message,
                    "type": "media", "download_url": file_data.get("downloadUrl", ""),
                }

            # Остальные типы (стикеры, контакты, локация и т.д.) — игнорируем
            return None

        except Exception as e:
            logger.error(f"[GREEN-API] Parse error: {e}")
            return None


def get_provider():
    """Получить WhatsApp провайдера."""
    return GreenAPIProvider()
