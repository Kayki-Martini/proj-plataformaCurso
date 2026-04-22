CREATE TABLE IF NOT EXISTS enrollments (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    course_title VARCHAR(150) NOT NULL,
    cpf VARCHAR(14) NOT NULL,
    group_number INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    enrolled_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    final_delivery_deadline TIMESTAMP NOT NULL,
    access_expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_course UNIQUE (user_id, course_id)
);

CREATE INDEX IF NOT EXISTS idx_enrollments_user ON enrollments(user_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_course ON enrollments(course_id);

