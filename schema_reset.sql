-- =============================================
-- Стоматологическая клиника — схема БД
-- =============================================

-- Удаление старых таблиц (если нужна чистая установка)
SET client_encoding = 'UTF8';
DROP TABLE IF EXISTS chat_history CASCADE;
DROP TABLE IF EXISTS appointments CASCADE;
DROP TABLE IF EXISTS clients CASCADE;
DROP TABLE IF EXISTS doctors CASCADE;
DROP TABLE IF EXISTS services CASCADE;
DROP TABLE IF EXISTS admin_users CASCADE;

-- Клиенты
CREATE TABLE clients (
    id          SERIAL PRIMARY KEY,
    phone       VARCHAR(20) UNIQUE NOT NULL,       -- +77771234567
    name        VARCHAR(255),                       -- Имя клиента (заполняется при первом общении)
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- Врачи
CREATE TABLE doctors (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    specialization  VARCHAR(255) NOT NULL,
    experience_years INTEGER DEFAULT 0,
    bio             TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Услуги
CREATE TABLE services (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    price           INTEGER NOT NULL,               -- в тенге
    duration_minutes INTEGER NOT NULL,
    description     TEXT,
    is_active       BOOLEAN DEFAULT TRUE
);

-- Записи на прием
CREATE TABLE appointments (
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

-- Индекс для быстрого поиска записей по дате
CREATE INDEX idx_appointments_date ON appointments(appointment_date);
CREATE INDEX idx_appointments_client ON appointments(client_id);
CREATE INDEX idx_appointments_status ON appointments(status);

-- История чата (для контекста AI)
CREATE TABLE chat_history (
    id          SERIAL PRIMARY KEY,
    phone       VARCHAR(20) NOT NULL,
    role        VARCHAR(20) NOT NULL,               -- 'user' или 'assistant'
    message     TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_chat_history_phone ON chat_history(phone, created_at DESC);

-- Администраторы
CREATE TABLE admin_users (
    id          SERIAL PRIMARY KEY,
    phone       VARCHAR(20) UNIQUE NOT NULL,
    name        VARCHAR(255) NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE
);

-- =============================================
-- Начальные данные
-- =============================================

-- Врачи (замени на своих)
INSERT INTO doctors (name, specialization, experience_years, bio) VALUES
    ('Иванов Алексей Петрович',   'Терапевт',     12, 'Лечение кариеса, пульпита, реставрация зубов'),
    ('Петрова Елена Сергеевна',   'Ортодонт',      8, 'Брекеты, элайнеры, исправление прикуса'),
    ('Сидоров Максим Олегович',   'Хирург',       15, 'Удаление зубов, имплантация'),
    ('Касымова Айгерим Нурлановна','Гигиенист',    5, 'Профессиональная чистка, отбеливание');

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
    ('Имплантация',             250000,  120, 'Установка одного импланта');

-- Администратор (замени на свой номер)
INSERT INTO admin_users (phone, name) VALUES
    ('+77072080253', 'Администратор');
