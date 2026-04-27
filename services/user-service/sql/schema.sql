CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    auth_user_id VARCHAR(50) NOT NULL UNIQUE,
    cpf VARCHAR(14) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    whatsapp VARCHAR(30),
    telegram VARCHAR(60),
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    education_level VARCHAR(40) NOT NULL DEFAULT 'medio',
    last_activity_at TIMESTAMP,
    last_activity_source VARCHAR(80),
    persistence_expires_at TIMESTAMP,
    persistence_status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_students_auth_user_id ON students(auth_user_id);
CREATE INDEX IF NOT EXISTS idx_students_cpf ON students(cpf);
