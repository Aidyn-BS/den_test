"""
Определение tools (функций) для function calling.
Извлечено из ai_agent.py без изменений.
"""

TOOLS_CLIENT = [
    {
        "type": "function",
        "function": {
            "name": "get_clinic_info",
            "description": "Получить информацию о клинике: адрес, график работы, контакты, правила",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_services",
            "description": "Получить список всех услуг с ценами и длительностью",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_doctors",
            "description": "Получить список врачей с их специализацией и опытом",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_free_slots",
            "description": "Получить свободные временные окна на конкретную дату. Можно указать врача.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Дата в формате YYYY-MM-DD",
                    },
                    "doctor_id": {
                        "type": "integer",
                        "description": "ID врача (необязательно). Если не указан — покажет слоты всех врачей.",
                    },
                },
                "required": ["date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_appointment",
            "description": "Создать запись на прием. Вызывай ТОЛЬКО после подтверждения клиентом. ВАЖНО: Перед вызовом ОБЯЗАТЕЛЬНО вызови get_services() и get_doctors() чтобы узнать правильные ID! Используй ТОЧНЫЕ ID из ответа этих функций.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {"type": "string", "description": "Название услуги (например: 'Профессиональная чистка', 'Лечение кариеса')"},
                    "doctor_name": {"type": "string", "description": "Имя врача (например: 'Касымова Айгерим Нурлановна')"},
                    "date": {"type": "string", "description": "Дата в формате YYYY-MM-DD"},
                    "time": {"type": "string", "description": "Время в формате HH:MM. ВАЖНО: только :00 или :30 (например 09:00, 09:30, 10:00)"},
                    "notes": {"type": "string", "description": "Заметки (необязательно)"},
                    "patient_name": {"type": "string", "description": "Имя пациента, если запись НЕ на самого клиента (ребёнок, родственник). Если не указано — запись на самого клиента."},
                },
                "required": ["service_name", "doctor_name", "date", "time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_combo_appointment",
            "description": "Создать комбо-запись: две услуги подряд у одного врача. Вторая услуга начинается сразу после первой.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name_1": {"type": "string", "description": "Первая услуга"},
                    "service_name_2": {"type": "string", "description": "Вторая услуга"},
                    "doctor_name": {"type": "string", "description": "Имя врача"},
                    "date": {"type": "string", "description": "Дата YYYY-MM-DD"},
                    "time": {"type": "string", "description": "Время начала первой услуги HH:MM"},
                    "patient_name": {"type": "string", "description": "Имя пациента (если не на себя)"},
                },
                "required": ["service_name_1", "service_name_2", "doctor_name", "date", "time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": "Отменить запись. Вызывай ТОЛЬКО после подтверждения клиентом. Обязательно спроси причину отмены перед вызовом.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "integer", "description": "ID записи для отмены"},
                    "reason": {"type": "string", "description": "Причина отмены (например: 'не могу прийти', 'перенесу', 'выбрал другую клинику' и т.д.)"},
                },
                "required": ["appointment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reschedule_appointment",
            "description": "Перенести запись на новую дату/время. Вызывай ТОЛЬКО после подтверждения.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "integer", "description": "ID записи"},
                    "new_date": {"type": "string", "description": "Новая дата YYYY-MM-DD"},
                    "new_time": {"type": "string", "description": "Новое время HH:MM"},
                },
                "required": ["appointment_id", "new_date", "new_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_appointments",
            "description": "Показать предстоящие записи этого клиента",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_client_name",
            "description": "Сохранить или обновить имя клиента. Вызывай когда клиент представился.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Имя клиента"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notify_emergency",
            "description": "Уведомить администратора об экстренном пациенте (острая боль, травма, кровотечение). Вызывай когда клиент сообщает о неотложной ситуации.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "Краткое описание ситуации пациента"},
                },
                "required": ["description"],
            },
        },
    },
]

TOOLS_ADMIN = TOOLS_CLIENT + [
    {
        "type": "function",
        "function": {
            "name": "set_doctor_absence",
            "description": "Отметить врача как недоступного (болезнь, отпуск). Автоматически отменяет все записи в этот период и уведомляет пациентов.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doctor_name": {"type": "string", "description": "Имя врача"},
                    "start_date": {"type": "string", "description": "Начало отсутствия YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "Конец отсутствия YYYY-MM-DD"},
                    "reason": {"type": "string", "description": "Причина: sick (болезнь), vacation (отпуск), other (другое)", "enum": ["sick", "vacation", "other"]},
                },
                "required": ["doctor_name", "start_date", "end_date", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_follow_up",
            "description": "Назначить повторный визит. Пациент получит напоминание за 3 дня.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "integer", "description": "ID завершённой записи"},
                    "follow_up_date": {"type": "string", "description": "Дата повторного визита YYYY-MM-DD"},
                    "notes": {"type": "string", "description": "Заметки (что нужно на повторном визите)"},
                },
                "required": ["appointment_id", "follow_up_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_no_show",
            "description": "Отметить пациента как неявку (no-show). Используй когда пациент не пришёл на приём.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "integer", "description": "ID записи"},
                },
                "required": ["appointment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "block_patient",
            "description": "Заблокировать пациента (бот перестанет отвечать). Используй для злоупотребляющих клиентов.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "Номер телефона пациента (например +77771234567)"},
                    "reason": {"type": "string", "description": "Причина блокировки"},
                },
                "required": ["phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unblock_patient",
            "description": "Разблокировать пациента.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "Номер телефона пациента"},
                },
                "required": ["phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_payment",
            "description": "Записать факт оплаты за приём.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "integer", "description": "ID записи"},
                    "actual_price": {"type": "integer", "description": "Фактическая сумма оплаты в тенге"},
                    "payment_status": {"type": "string", "description": "Статус оплаты", "enum": ["paid", "partial", "refunded"]},
                },
                "required": ["appointment_id", "actual_price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_schedule",
            "description": "Получить все записи на сегодня (для администратора)",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_week_report",
            "description": "Получить записи на текущую неделю (для администратора)",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_month_report",
            "description": "Получить отчет за месяц со статистикой (для администратора)",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "Год (напр. 2026)"},
                    "month": {"type": "integer", "description": "Месяц (1-12)"},
                },
                "required": ["year", "month"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_to_sheets",
            "description": "Экспортировать отчет в Google Sheets",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["day", "week", "month"],
                        "description": "Период: day, week или month",
                    },
                },
                "required": ["period"],
            },
        },
    },
]
