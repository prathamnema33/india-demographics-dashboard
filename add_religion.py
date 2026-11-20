import random
import os
import psycopg2
from dotenv import load_dotenv

RELIGION_INTERVALS = [
    {"religion": "Hinduism", "lower": 0.0, "upper": 0.7980},
    {"religion": "Islam", "lower": 0.7980, "upper": 0.9403},
    {"religion": "Christianity", "lower": 0.9403, "upper": 0.9633},
    {"religion": "Sikhism", "lower": 0.9633, "upper": 0.9805},
    {"religion": "Buddhism", "lower": 0.9805, "upper": 0.9875},
    {"religion": "Jainism", "lower": 0.9875, "upper": 0.9912},
    {"religion": "Others", "lower": 0.9912, "upper": 1.0}
]


def get_random_religion():
    r = random.random()
    for item in RELIGION_INTERVALS:
        if item["lower"] <= r < item["upper"]:
            return item["religion"]
    return "Others"


def update_users_religion():
    load_dotenv()
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "Users"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        port=int(os.getenv("DB_PORT", "8137"))
    )
    with conn:
        with conn.cursor() as cursor:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS religion VARCHAR(50);")
            cursor.execute("SELECT id FROM user_detail WHERE religion IS NULL;")
            rows = cursor.fetchall()
            updates = [(get_random_religion(), row[0]) for row in rows]
            sql = "UPDATE user_detail SET religion = %s WHERE id = %s;"
            cursor.executemany(sql, updates)
    print(f"Updated {len(updates)} rows successfully.")


if __name__ == "__main__":
    update_users_religion()
