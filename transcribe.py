"""
Транскрипция голосовых сообщений через Groq Whisper API.
Groq предоставляет бесплатный тир с whisper-large-v3-turbo.
"""

import logging
import requests

from config import GROQ_API_KEY

logger = logging.getLogger(__name__)

GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def transcribe_audio(audio_url: str) -> str | None:
    """
    Скачать аудио по URL и транскрибировать через Groq Whisper.
    Возвращает текст или None при ошибке.
    """
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set, voice messages disabled")
        return None

    try:
        # Скачиваем аудио от GREEN-API
        audio_resp = requests.get(audio_url, timeout=30)
        audio_resp.raise_for_status()

        # Отправляем в Groq Whisper
        resp = requests.post(
            GROQ_WHISPER_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": ("audio.ogg", audio_resp.content, "audio/ogg")},
            data={
                "model": "whisper-large-v3-turbo",
                "language": "ru",
                "response_format": "json",
            },
            timeout=60,
        )
        resp.raise_for_status()

        text = resp.json().get("text", "").strip()
        if text:
            logger.info(f"Transcribed voice message: {text[:100]}")
        return text or None

    except requests.exceptions.Timeout:
        logger.error("Groq Whisper timeout")
        return None
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return None
