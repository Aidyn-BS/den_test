-- =============================================
-- Стоматологическая клиника — схема БД
-- Безопасна для повторного запуска (IF NOT EXISTS)
-- Для полного сброса используй schema_reset.sql
-- =============================================

SET client_encoding = 'UTF8';

-- Клиенты
CREATE TABLE IF NOT EXISTS clients (
    id          SERIAL PRIMARY KEY,
    phone       VARCHAR(20) UNIQUE NOT NULL,       -- +77771234567
    name        VARCHAR(255),                       -- Имя клиента (заполняется при первом общении)
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- Врачи
CREATE TABLE IF NOT EXISTS doctors (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    specialization  VARCHAR(255) NOT NULL,
    experience_years INTEGER DEFAULT 0,
    bio             TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Услуги
CREATE TABLE IF NOT EXISTS services (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    price           INTEGER NOT NULL,               -- в тенге
    duration_minutes INTEGER NOT NULL,
    description     TEXT,
    is_active       BOOLEAN DEFAULT TRUE
);

-- Записи на прием
CREATE TABLE IF NOT EXISTS appointments (
    id                          SERIAL PRIMARY KEY,
    client_id                   INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    doctor_id                   INTEGER NOT NULL REFERENCES doctors(id),
    service_id                  INTEGER NOT NULL REFERENCES services(id),
    appointment_date            DATE NOT NULL,
    appointment_time            TIME NOT NULL,
    status                      VARCHAR(20) DEFAULT 'scheduled'
                                CHECK (status IN ('scheduled','completed','cancelled','no_show')),
    notes                       TEXT,
    google_calendar_event_id    VARCHAR(255),
    reminder_24h_sent           BOOLEAN DEFAULT FALSE,
    reminder_2h_sent            BOOLEAN DEFAULT FALSE,
    reminder_1h_sent            BOOLEAN DEFAULT FALSE,
    created_at                  TIMESTAMP DEFAULT NOW(),
    updated_at                  TIMESTAMP DEFAULT NOW()
);

-- Индексы (IF NOT EXISTS не поддерживается для индексов в старых версиях PG,
-- поэтому используем DO блок)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_appointments_date') THEN
        CREATE INDEX idx_appointments_date ON appointments(appointment_date);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_appointments_client') THEN
        CREATE INDEX idx_appointments_client ON appointments(client_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_appointments_status') THEN
        CREATE INDEX idx_appointments_status ON appointments(status);
    END IF;
END $$;

-- История чата (для контекста AI)
CREATE TABLE IF NOT EXISTS chat_history (
    id          SERIAL PRIMARY KEY,
    phone       VARCHAR(20) NOT NULL,
    role        VARCHAR(20) NOT NULL,               -- 'user' или 'assistant'
    message     TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_chat_history_phone') THEN
        CREATE INDEX idx_chat_history_phone ON chat_history(phone, created_at DESC);
    END IF;
END $$;

-- Администраторы
CREATE TABLE IF NOT EXISTS admin_users (
    id          SERIAL PRIMARY KEY,
    phone       VARCHAR(20) UNIQUE NOT NULL,
    name        VARCHAR(255) NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE
);

-- Индивидуальное расписание врачей (day_of_week: 0=Пн, 6=Вс)
CREATE TABLE IF NOT EXISTS doctor_schedules (
    id          SERIAL PRIMARY KEY,
    doctor_id   INTEGER NOT NULL REFERENCES doctors(id),
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    start_time  TIME NOT NULL,
    end_time    TIME NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    UNIQUE(doctor_id, day_of_week)
);

-- Болезнь / отпуск врачей
CREATE TABLE IF NOT EXISTS doctor_absences (
    id          SERIAL PRIMARY KEY,
    doctor_id   INTEGER NOT NULL REFERENCES doctors(id),
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL,
    reason      VARCHAR(50) DEFAULT 'sick',
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Добавляем колонку причины отмены (если ещё нет)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'appointments' AND column_name = 'cancellation_reason') THEN
        ALTER TABLE appointments ADD COLUMN cancellation_reason VARCHAR(255);
    END IF;
END $$;

-- Имя пациента (для записи ребёнка/другого члена семьи)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'appointments' AND column_name = 'patient_name') THEN
        ALTER TABLE appointments ADD COLUMN patient_name VARCHAR(255);
    END IF;
END $$;

-- Повторный визит (follow-up)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'appointments' AND column_name = 'follow_up_date') THEN
        ALTER TABLE appointments ADD COLUMN follow_up_date DATE;
        ALTER TABLE appointments ADD COLUMN follow_up_notes TEXT;
    END IF;
END $$;

-- Реальный платёж
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'appointments' AND column_name = 'actual_price') THEN
        ALTER TABLE appointments ADD COLUMN actual_price INTEGER;
        ALTER TABLE appointments ADD COLUMN payment_status VARCHAR(20) DEFAULT 'pending'
            CHECK (payment_status IN ('pending', 'paid', 'partial', 'refunded'));
    END IF;
END $$;

-- Блок-лист клиентов
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'clients' AND column_name = 'is_blocked') THEN
        ALTER TABLE clients ADD COLUMN is_blocked BOOLEAN DEFAULT FALSE;
        ALTER TABLE clients ADD COLUMN block_reason TEXT;
    END IF;
END $$;

-- =============================================
-- Начальные данные (ON CONFLICT — не перезаписывает)
-- =============================================

-- Врачи (замени на своих)
INSERT INTO doctors (name, specialization, experience_years, bio) VALUES
    ('Иванов Алексей Петрович',   'Терапевт',     12, 'Лечение кариеса, пульпита, реставрация зубов'),
    ('Петрова Елена Сергеевна',   'Ортодонт',      8, 'Брекеты, элайнеры, исправление прикуса'),
    ('Сидоров Максим Олегович',   'Хирург',       15, 'Удаление зубов, имплантация'),
    ('Касымова Айгерим Нурлановна','Гигиенист',    5, 'Профессиональная чистка, отбеливание')
ON CONFLICT DO NOTHING;

-- Услуги (замени цены на свои)
INSERT INTO services (name, price, duration_minutes, description) VALUES
    ('Консультация',              5000,   30, 'Осмотр, диагностика, план лечения'),
    ('Профессиональная чистка',  15000,   60, 'Ультразвуковая чистка + Air Flow'),
    ('Лечение кариеса',          25000,   45, 'Пломбирование одного зуба'),
    ('Удаление зуба',            20000,   30, 'Простое удаление'),
    ('Сложное удаление',         35000,   60, 'Удаление зуба мудрости'),
    ('Отбеливание',              40000,   90, 'Профессиональное отбеливание ZOOM'),
    ('Установка коронки',       120000,   90, 'Металлокерамическая коронка'),
    ('Установка виниров',       150000,   60, 'Один винир E-max'),
    ('Имплантация',             250000,  120, 'Установка одного импланта')
ON CONFLICT DO NOTHING;

-- Telegram пользователи (привязка chat_id к номеру телефона)
CREATE TABLE IF NOT EXISTS telegram_users (
    telegram_chat_id BIGINT PRIMARY KEY,
    phone VARCHAR(20) REFERENCES clients(phone),
    username VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индекс для поиска telegram chat_id по номеру телефона
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_telegram_users_phone') THEN
        CREATE INDEX idx_telegram_users_phone ON telegram_users(phone);
    END IF;
END $$;

-- Администратор (замени на свой номер)
INSERT INTO admin_users (phone, name) VALUES
    ('+77072080253', 'Администратор')
ON CONFLICT (phone) DO NOTHING;
