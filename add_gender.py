import random as rnd
import os
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_batch
from faker.providers.person.en_IN import Provider as EnInPersonProvider

all_male_name = set(EnInPersonProvider.first_names_male)

def add_gender(first_name: str) -> str:
    if rnd.random() > 0.001:
        return 'Male' if first_name in all_male_name else 'Female'
    return 'Others'

load_dotenv()
conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME", "Users"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD"),
    port=int(os.getenv("DB_PORT", "8137")),
)

with conn:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT first_name, id
            FROM user_detail;
            """
        )
        # Everything below must stay indented inside 'with conn.cursor() as cursor:'
        rows = cursor.fetchall()
        updates = [(add_gender(row[0]), row[1]) for row in rows]

        sql = "UPDATE user_detail SET gender = %s WHERE id = %s;"
        execute_batch(cursor, sql, updates, page_size=1000)

print(f"Updated {len(updates)} rows successfully.")
conn.close()
