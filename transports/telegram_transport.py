"""
Telegram transport — python-telegram-bot (polling mode).
Маппинг: Telegram chat_id <-> phone через таблицу telegram_users.
"""

import logging
import os
import threading

from .base import BaseTransport

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


class TelegramTransport(BaseTransport):
    def __init__(self):
        self._app = None
        self._running = False

    def send_message(self, phone: str, text: str) -> bool:
        """Отправить сообщение по номеру телефона (ищем chat_id в БД)."""
        if not self._app:
            return False
        try:
            import telegram_db
            chat_id = telegram_db.get_telegram_chat_id(phone)
            if not chat_id:
                logger.debug(f"No Telegram chat_id for phone {phone}")
                return False
            return self.send_to_chat(chat_id, text)
        except Exception as e:
            logger.error(f"Telegram send_message error: {e}")
            return False

    def send_to_chat(self, chat_id, text: str) -> bool:
        """Отправить сообщение в Telegram чат."""
        if not self._app:
            return False
        try:
            import asyncio
            coro = self._app.bot.send_message(chat_id=chat_id, text=text)
            asyncio.run_coroutine_threadsafe(coro, self._get_loop()).result(timeout=10)
            return True
        except Exception as e:
            logger.error(f"Telegram send_to_chat error: {e}")
            return False

    def _get_loop(self):
        """Получить event loop бота."""
        if hasattr(self, '_loop') and self._loop:
            return self._loop
        return None

    def start_polling(self):
        """Запустить Telegram бота в polling mode (вызывать в отдельном потоке)."""
        if not TELEGRAM_BOT_TOKEN:
            logger.info("TELEGRAM_BOT_TOKEN not set, Telegram bot disabled")
            return

        try:
            from telegram import Update
            from telegram.ext import (
                ApplicationBuilder, CommandHandler, MessageHandler,
                filters, ContextTypes, ConversationHandler,
            )
        except ImportError:
            logger.warning("python-telegram-bot not installed, Telegram bot disabled")
            return

        import asyncio
        import db
        import telegram_db

        WAITING_PHONE = 1

        async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Команда /start — просим телефон для привязки."""
            chat_id = update.effective_chat.id
            # Проверяем, привязан ли уже
            phone = telegram_db.get_phone_by_telegram_chat_id(chat_id)
            if phone:
                await update.message.reply_text(
                    f"Вы уже привязаны к номеру {phone}.\n"
                    "Просто напишите сообщение — я помогу с записью!"
                )
                return ConversationHandler.END

            await update.message.reply_text(
                "Добро пожаловать в стоматологию «Улыбка»! 🦷\n\n"
                "Для начала работы привяжите ваш номер телефона.\n"
                "Отправьте номер в формате: +77001234567"
            )
            return WAITING_PHONE

        async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Получить и привязать телефон."""
            raw = update.message.text.strip()
            # Нормализация: убираем пробелы, скобки, дефисы
            phone = raw.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

            # Если начинается с 8 — заменяем на +7
            if phone.startswith("8") and len(phone) == 11:
                phone = "+7" + phone[1:]
            # Если начинается с 7 без + — добавляем +
            elif phone.startswith("7") and len(phone) == 11:
                phone = "+" + phone

            if not phone.startswith("+") or len(phone) < 11:
                await update.message.reply_text(
                    "Неверный формат. Отправьте номер в формате: +77001234567"
                )
                return WAITING_PHONE

            chat_id = update.effective_chat.id
            username = update.effective_user.username or ""

            # Убедимся что клиент есть в БД
            if not db.get_client(phone):
                db.create_client(phone)

            telegram_db.link_telegram_user(chat_id, phone, username)
            logger.info(f"Telegram: linked chat_id={chat_id} to phone={phone} (raw: {raw})")

            await update.message.reply_text(
                f"Номер {phone} привязан!\n"
                "Теперь вы можете записаться на приём прямо здесь. Просто напишите!"
            )
            return ConversationHandler.END

        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """Обработка текстовых сообщений — пересылка в AI-агента."""
            chat_id = update.effective_chat.id
            phone = telegram_db.get_phone_by_telegram_chat_id(chat_id)

            if not phone:
                await update.message.reply_text(
                    "Сначала привяжите номер телефона.\n"
                    "Нажмите /start для начала."
                )
                return

            text = update.message.text
            if not text:
                return

            # Обрабатываем через AI-агента
            from agents.agent import process_message
            try:
                answer = process_message(phone, text, source="telegram")
                await update.message.reply_text(answer)
            except Exception as e:
                logger.error(f"Telegram AI error: {e}", exc_info=True)
                await update.message.reply_text(
                    "Извините, произошла ошибка. Попробуйте написать ещё раз."
                )

        async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await update.message.reply_text("Отменено. Нажмите /start чтобы начать заново.")
            return ConversationHandler.END

        def _run_bot():
            """Запуск бота в отдельном event loop."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop

            app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
            self._app = app

            conv_handler = ConversationHandler(
                entry_points=[CommandHandler("start", start_command)],
                states={
                    WAITING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
                },
                fallbacks=[CommandHandler("cancel", cancel)],
            )

            app.add_handler(conv_handler)
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

            logger.info("Telegram bot started (polling)")
            loop.run_until_complete(app.run_polling(drop_pending_updates=True))

        thread = threading.Thread(target=_run_bot, daemon=True)
        thread.start()
        self._running = True
        logger.info("Telegram polling thread started")
