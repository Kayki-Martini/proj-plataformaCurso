CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    course_id INTEGER NOT NULL,
    lesson_id INTEGER,
    course_title VARCHAR(150) NOT NULL,
    lesson_title VARCHAR(150),
    amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    currency VARCHAR(10) NOT NULL DEFAULT 'BRL',
    status VARCHAR(20) NOT NULL DEFAULT 'paid',
    provider VARCHAR(50) NOT NULL DEFAULT 'credit_card',
    card_holder_name VARCHAR(150),
    card_brand VARCHAR(30),
    card_last_four VARCHAR(4),
    external_reference VARCHAR(100),
    paid_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_course ON payments(course_id);
CREATE INDEX IF NOT EXISTS idx_payments_lesson ON payments(lesson_id);
