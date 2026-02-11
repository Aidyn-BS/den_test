"""
Главный AI-цикл: process_message + _call_openrouter.
Извлечено из ai_agent.py.
"""

import json
import logging
import time as _time

import requests

import db
from config import OPENROUTER_API_KEY, AI_MODEL

from .prompts import build_system_prompt, append_client_context
from .tools import TOOLS_ADMIN, TOOLS_CLIENT
from .functions import execute_function
from .notifications import notify_admin_api_down

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def process_message(phone: str, user_message: str, source: str = "whatsapp") -> str:
    """
    Принимает номер и текст сообщения.
    Возвращает текстовый ответ от AI-агента.
    """
    # Убедимся, что клиент есть в БД
    if not db.get_client(phone):
        db.create_client(phone)

    # Сохраняем входящее сообщение
    db.save_message(phone, "user", user_message)

    # Загружаем весь контекст за одно соединение
    ctx = db.get_client_context(phone)
    admin = ctx["is_admin"]

    logger.info(f"Processing message: phone={phone}, is_admin={admin}, source={source}")

    # Собираем системный промпт + контекст клиента
    system_prompt = build_system_prompt(phone, admin)
    system_prompt = append_client_context(system_prompt, ctx, phone, admin)

    tools = TOOLS_ADMIN if admin else TOOLS_CLIENT
    logger.info(f"Tools count: {len(tools)} ({'ADMIN' if admin else 'CLIENT'})")

    # Формируем messages для API
    messages = [{"role": "system", "content": system_prompt}]
    for msg in ctx["chat_history"]:
        messages.append({"role": msg["role"], "content": msg["message"]})

    # Защита от переполнения контекста (~1 токен = 2 символа для русского)
    MAX_CONTEXT_CHARS = 16000
    total_chars = sum(len(m.get("content", "")) for m in messages)
    while total_chars > MAX_CONTEXT_CHARS and len(messages) > 2:
        removed = messages.pop(1)  # Удаляем старейшее (после system prompt)
        total_chars -= len(removed.get("content", ""))

    # Цикл function calling (максимум 5 итераций)
    for iteration in range(5):
        response = _call_openrouter(messages, tools)

        if not response:
            answer = "Извините, произошла техническая ошибка. Попробуйте написать ещё раз."
            break

        choice = response["choices"][0]["message"]

        # Если AI хочет вызвать функцию
        if choice.get("tool_calls"):
            messages.append(choice)

            for tool_call in choice["tool_calls"]:
                func_name = tool_call["function"]["name"]
                func_args = json.loads(tool_call["function"]["arguments"])

                logger.info(f"AI calls: {func_name}({func_args})")

                result = execute_function(func_name, func_args, phone, admin)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": result,
                })

            continue  # Следующая итерация — AI сформулирует ответ

        # AI вернул текстовый ответ — готово
        answer = choice.get("content", "").strip()
        break
    else:
        answer = "Извините, не удалось обработать запрос. Попробуйте ещё раз."

    # Сохраняем ответ в историю
    db.save_message(phone, "assistant", answer)

    return answer


def _call_openrouter(messages: list, tools: list) -> dict | None:
    """Вызвать OpenRouter API с retry и уведомлением админа при отказе."""
    for attempt in range(3):
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": AI_MODEL,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "temperature": 0.3,
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.Timeout:
            logger.warning(f"OpenRouter timeout (attempt {attempt + 1}/3)")
            if attempt < 2:
                _time.sleep(2)
                continue
        except requests.exceptions.HTTPError as e:
            logger.error(f"OpenRouter HTTP error: {e}")
            if attempt < 2 and e.response is not None and e.response.status_code >= 500:
                _time.sleep(2)
                continue
            break
        except Exception as e:
            logger.error(f"OpenRouter API error: {e}")
            break

    # Все попытки исчерпаны — уведомить админа
    notify_admin_api_down()
    return None
