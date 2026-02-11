"""
Точка входа — Flask сервер с webhook для GREEN-API (WhatsApp).
"""

import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify

from whatsapp import get_provider
from agents import process_message
from scheduler import start_scheduler
from transports import get_transport


# ======================== Дедупликация webhook-ов ========================

_processed_messages = {}  # idMessage -> timestamp
DEDUP_TTL = 300  # 5 минут
_DEDUP_MAX_SIZE = 10000


def _is_duplicate(id_message: str) -> bool:
    """Проверить, обрабатывалось ли уже это сообщение (защита от повторных webhook)."""
    if not id_message:
        return False
    now = time.time()
    # Очистка старых записей (+ защита от переполнения)
    if len(_processed_messages) > _DEDUP_MAX_SIZE or len(_processed_messages) % 100 == 0:
        expired = [k for k, v in _processed_messages.items() if now - v > DEDUP_TTL]
        for k in expired:
            del _processed_messages[k]
    if id_message in _processed_messages:
        return True
    _processed_messages[id_message] = now
    return False


# ======================== Rate Limiting ========================

_rate_limits = {}  # phone -> [timestamps]
RATE_LIMIT_MAX = 20  # сообщений за окно
RATE_LIMIT_WINDOW = 60  # секунд
_RATE_CLEANUP_COUNTER = 0


def _is_rate_limited(phone: str) -> bool:
    """Проверить, не превышен ли лимит сообщений для номера."""
    global _RATE_CLEANUP_COUNTER
    now = time.time()

    # Периодическая очистка неактивных номеров (каждые 200 вызовов)
    _RATE_CLEANUP_COUNTER += 1
    if _RATE_CLEANUP_COUNTER >= 200:
        _RATE_CLEANUP_COUNTER = 0
        stale = [p for p, ts in _rate_limits.items() if not ts or now - ts[-1] > RATE_LIMIT_WINDOW * 5]
        for p in stale:
            del _rate_limits[p]

    if phone not in _rate_limits:
        _rate_limits[phone] = []
    _rate_limits[phone] = [t for t in _rate_limits[phone] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limits[phone]) >= RATE_LIMIT_MAX:
        return True
    _rate_limits[phone].append(now)
    return False


# ======================== Per-phone Lock ========================

_phone_locks = {}
_locks_lock = threading.Lock()
_LOCK_CLEANUP_COUNTER = 0


def _get_phone_lock(phone: str) -> threading.Lock:
    """Получить lock для номера (сообщения от одного пациента обрабатываются последовательно)."""
    global _LOCK_CLEANUP_COUNTER
    with _locks_lock:
        # Периодическая очистка неиспользуемых locks (каждые 500 вызовов)
        _LOCK_CLEANUP_COUNTER += 1
        if _LOCK_CLEANUP_COUNTER >= 500 and len(_phone_locks) > 100:
            _LOCK_CLEANUP_COUNTER = 0
            unlocked = [p for p, lk in _phone_locks.items() if not lk.locked()]
            # Оставляем последние 50, чистим остальные
            for p in unlocked[:-50]:
                del _phone_locks[p]

        if phone not in _phone_locks:
            _phone_locks[phone] = threading.Lock()
        return _phone_locks[phone]


# ======================== Init ========================

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Flask
app = Flask(__name__)

# WhatsApp provider
wp = get_provider()

# Пул потоков — ограничиваем до 10 (вместо безлимитных Thread)
_executor = ThreadPoolExecutor(max_workers=10)


# ======================== Webhooks ========================

def _process_in_background(phone: str, text: str, msg_type: str, download_url: str):
    """Фоновая обработка сообщения (вне webhook request)."""
    lock = _get_phone_lock(phone)
    if not lock.acquire(timeout=30):
        logger.warning(f"Phone lock timeout: {phone}")
        return
    try:
        # Голосовые → транскрипция через Groq Whisper
        if msg_type == "audio":
            if not download_url:
                wp.send_message(phone, "Не удалось получить голосовое сообщение. Пожалуйста, напишите текстом.")
                return
            from transcribe import transcribe_audio
            text = transcribe_audio(download_url)
            if not text:
                wp.send_message(phone, "Не удалось распознать голосовое сообщение. Пожалуйста, напишите текстом.")
                return
            logger.info(f"Voice from {phone}: {text[:100]}")

        if not text:
            return

        logger.info(f"Message from {phone}: {text[:100]}")

        # Обрабатываем через AI-агента
        answer = process_message(phone, text)

        # Отправляем ответ
        wp.send_message(phone, answer)

        logger.info(f"Reply to {phone}: {answer[:100]}")
    except Exception as e:
        logger.error(f"Background processing error: {e}", exc_info=True)
    finally:
        lock.release()


@app.route("/webhook", methods=["POST"])
def webhook_incoming():
    """Обработка входящих сообщений. Возвращает 200 мгновенно, обработка в фоне."""
    try:
        data = request.get_json(silent=True) or {}

        # Парсим сообщение в зависимости от провайдера
        parsed = wp.parse_webhook(data)

        if not parsed:
            return jsonify({"status": "ignored"}), 200

        # Дедупликация — защита от повторных webhook от GREEN-API
        if _is_duplicate(parsed.get("id_message", "")):
            logger.debug(f"Duplicate message ignored: {parsed.get('id_message')}")
            return jsonify({"status": "duplicate"}), 200

        phone = parsed["phone"]
        msg_type = parsed.get("type", "text")

        # Блок-лист — заблокированные клиенты молча игнорируются
        import db as _db
        if _db.is_client_blocked(phone):
            logger.info(f"Blocked client ignored: {phone}")
            return jsonify({"status": "blocked"}), 200

        # Rate limiting
        if _is_rate_limited(phone):
            logger.warning(f"Rate limited: {phone}")
            return jsonify({"status": "rate_limited"}), 200

        # Фото, видео, документы → вежливый отказ (быстро, можно прямо тут)
        if msg_type == "media":
            wp.send_message(phone,
                "Спасибо! К сожалению, я не могу просматривать изображения и документы. "
                "Пожалуйста, напишите ваш вопрос текстом или голосовым сообщением. "
                "Если нужно передать снимок врачу — возьмите его на приём.")
            return jsonify({"status": "media_acknowledged"}), 200

        text = parsed.get("text", "")
        download_url = parsed.get("download_url", "")

        # Запускаем обработку в пуле потоков — СРАЗУ возвращаем 200
        _executor.submit(_process_in_background, phone, text, msg_type, download_url)

        return jsonify({"status": "processing"}), 200

    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return jsonify({"status": "error"}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "running", "provider": "green_api"}), 200


# ======================== Startup ========================

# Запускаем планировщик при импорте модуля (работает и с gunicorn, и напрямую)
_scheduler = None

def _init_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = start_scheduler()

_init_scheduler()

# Запускаем Telegram бота (polling в отдельном потоке)
_telegram_transport = None

def _init_telegram():
    global _telegram_transport
    if _telegram_transport is None:
        import os
        if os.getenv("TELEGRAM_BOT_TOKEN"):
            try:
                tg = get_transport("telegram")
                tg.start_polling()
                _telegram_transport = tg
            except Exception as e:
                logger.error(f"Failed to start Telegram bot: {e}")

_init_telegram()


if __name__ == "__main__":
    import os

    port = int(os.getenv("FLASK_PORT", 5000))

    logger.info(f"Starting dental bot on port {port}")

    # Запускаем Flask (use_reloader=False чтобы scheduler не дублировался)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
