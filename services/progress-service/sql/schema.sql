CREATE TABLE IF NOT EXISTS progress_entries (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    course_id INTEGER NOT NULL,
    lesson_id INTEGER NOT NULL,
    completed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_lesson UNIQUE (user_id, lesson_id)
);

CREATE INDEX IF NOT EXISTS idx_progress_user ON progress_entries(user_id);
CREATE INDEX IF NOT EXISTS idx_progress_course ON progress_entries(course_id);

