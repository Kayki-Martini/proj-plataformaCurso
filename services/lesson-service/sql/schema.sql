CREATE TABLE IF NOT EXISTS lessons (
    id SERIAL PRIMARY KEY,
    course_id INTEGER NOT NULL,
    title VARCHAR(150) NOT NULL,
    description TEXT NOT NULL,
    type VARCHAR(20) NOT NULL,
    order_index INTEGER NOT NULL,
    release_week INTEGER NOT NULL,
    duration_minutes INTEGER NOT NULL,
    price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    content TEXT,
    cards_json TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_course_order UNIQUE (course_id, order_index)
);

CREATE INDEX IF NOT EXISTS idx_lessons_course ON lessons(course_id);
