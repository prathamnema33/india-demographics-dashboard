
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, URL

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = URL.create(
    drivername="postgresql+psycopg2",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    database=os.getenv("DB_NAME")
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)


def test_connection():
    try:
        with engine.connect() as connection:
            print("PostgreSQL connection successful!")
            return True
    except Exception as error:
        print("Database connection failed:", error)
        return False
