from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from .models import Base
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Use SQLite for now; you can switch to PostgreSQL by changing the URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./submissions.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# check_same_thread is a SQLite-only option
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# Create engine and session
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
def init_db():
    Base.metadata.create_all(bind=engine)
    # Add ownership to existing installations without deleting anonymous history.
    # Those rows stay inaccessible until the configured owner first signs in.
    with engine.begin() as connection:
        schema = inspect(connection)
        if "auth_provider" not in {column["name"] for column in schema.get_columns("users")}:
            connection.execute(text("ALTER TABLE users ADD COLUMN auth_provider VARCHAR(20) NOT NULL DEFAULT 'google'"))
        if "blocked_at" not in {column["name"] for column in schema.get_columns("users")}:
            connection.execute(text("ALTER TABLE users ADD COLUMN blocked_at TIMESTAMP"))
        if "verified_at" not in {column["name"] for column in schema.get_columns("email_credentials")}:
            connection.execute(text("ALTER TABLE email_credentials ADD COLUMN verified_at TIMESTAMP"))
        if "local_access_approved_at" not in {column["name"] for column in schema.get_columns("owner_account")}:
            connection.execute(text("ALTER TABLE owner_account ADD COLUMN local_access_approved_at TIMESTAMP"))
        if not any(index["unique"] and index["column_names"] == ["email"] for index in schema.get_indexes("email_verifications")):
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_email_verifications_email ON email_verifications(email)"))
        for table in ("submissions", "sample_answers", "chat_conversations"):
            if "user_id" not in {column["name"] for column in schema.get_columns(table)}:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id VARCHAR(36) REFERENCES users(id)"))
                connection.execute(text(f"CREATE INDEX ix_{table}_user_id ON {table} (user_id)"))


def get_db():
    with SessionLocal() as db:
        yield db
