from datetime import date
import random

import pandas as pd
import psycopg2
import os
from dotenv import load_dotenv
from faker import Faker

fake = Faker("en_IN")


def _load_health_lookup():
    health_data = [
        ("Kerala", 82.20),
        ("Mizoram", 75.77),
        ("Tamil Nadu", 72.42),
        ("Tripura", 70.16),
        ("Telangana", 69.96),
        ("Andhra Pradesh", 69.95),
        ("Maharashtra", 69.14),
        ("Dadra and Nagar Haveli and Daman and Diu", 66.19),
        ("Gujarat", 63.59),
        ("Himachal Pradesh", 63.17),
        ("Chandigarh", 62.53),
        ("Punjab", 58.08),
        ("Karnataka", 57.93),
        ("West Bengal", 56.71),
        ("Sikkim", 55.53),
        ("Goa", 53.68),
        ("Lakshadweep", 51.88),
        ("Puducherry", 50.83),
        ("Chhattisgarh", 50.70),
        ("Delhi", 49.85),
        ("Haryana", 49.26),
        ("Assam", 47.74),
        ("Jharkhand", 47.55),
        ("Jammu and Kashmir", 47.00),
        ("Ladakh", 47.00),
        ("Andaman and Nicobar Islands", 44.74),
        ("Odisha", 44.31),
        ("Uttarakhand", 44.21),
        ("Meghalaya", 43.05),
        ("Rajasthan", 41.33),
        ("Madhya Pradesh", 36.72),
        ("Manipur", 34.26),
        ("Arunachal Pradesh", 33.91),
        ("Bihar", 31.00),
        ("Uttar Pradesh", 30.57),
        ("Nagaland", 27.00),
    ]

    df = pd.DataFrame(health_data, columns=["State_UT", "Health_Index_Score"])
    return dict(zip(df["State_UT"].str.lower(), df["Health_Index_Score"])), df["Health_Index_Score"].mean()


HEALTH_LOOKUP, NATIONAL_AVG = _load_health_lookup()


def get_dod(state: str, dob) -> str:
    p = HEALTH_LOOKUP.get(state.strip().lower(), NATIONAL_AVG) if state else NATIONAL_AVG

    death_probability = (1 - (p / 100)) * 0.15

    if random.random() < death_probability:
        return str(fake.date_between_dates(date_start=dob, date_end=date.today()))
    return None


def update_users_dod():
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
                    SELECT A.id, B.state, A.dob
                    FROM user_detail AS A
                    JOIN addresses AS B ON A.address_id = B.id;
                """
            )
            rows = cursor.fetchall()

            updates = [(get_dod(row[1], row[2]), row[0]) for row in rows]

            sql = "UPDATE user_detail SET dod = %s WHERE id = %s;"
            cursor.executemany(sql, updates)

    print(f"Updated {len(updates)} rows successfully.")

if __name__ == "__main__":
    update_users_dod()
