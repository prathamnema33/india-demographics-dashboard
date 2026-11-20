import random

import pandas as pd
import psycopg2
import os
from dotenv import load_dotenv


def _load_literacy_lookup():
    data = [
        ("Andhra Pradesh", "State", 72.6, 67.02),
        ("Arunachal Pradesh", "State", 84.2, 65.39),
        ("Assam", "State", 87.0, 72.19),
        ("Bihar", "State", 74.3, 61.80),
        ("Chhattisgarh", "State", 78.5, 70.28),
        ("Goa", "State", 93.6, 88.70),
        ("Gujarat", "State", 84.6, 78.03),
        ("Haryana", "State", 84.8, 75.55),
        ("Himachal Pradesh", "State", 88.8, 82.80),
        ("Jharkhand", "State", 76.7, 66.41),
        ("Karnataka", "State", 82.7, 75.36),
        ("Kerala", "State", 95.3, 94.00),
        ("Madhya Pradesh", "State", 75.2, 69.32),
        ("Maharashtra", "State", 87.3, 82.34),
        ("Manipur", "State", 92.0, 76.94),
        ("Meghalaya", "State", 94.2, 74.43),
        ("Mizoram", "State", 98.2, 91.33),
        ("Nagaland", "State", 95.7, 79.55),
        ("Odisha", "State", 79.0, 72.87),
        ("Punjab", "State", 83.4, 75.84),
        ("Rajasthan", "State", 75.8, 66.11),
        ("Sikkim", "State", 84.7, 81.42),
        ("Tamil Nadu", "State", 85.5, 80.09),
        ("Telangana", "State", 76.9, 66.46),
        ("Tripura", "State", 93.7, 87.22),
        ("Uttar Pradesh", "State", 78.2, 67.68),
        ("Uttarakhand", "State", 83.8, 78.82),
        ("West Bengal", "State", 82.6, 76.26),
        ("Andaman and Nicobar Islands", "Union Territory", 91.1, 86.63),
        ("Chandigarh", "Union Territory", 93.7, 86.05),
        ("Dadra and Nagar Haveli and Daman and Diu", "Union Territory", 87.8, None),
        ("Delhi", "Union Territory", 86.9, 86.21),
        ("Jammu and Kashmir", "Union Territory", 82.0, 67.16),
        ("Ladakh", "Union Territory", 81.0, None),
        ("Lakshadweep", "Union Territory", 97.3, 91.85),
        ("Puducherry", "Union Territory", 92.7, 85.85),
    ]

    df = pd.DataFrame(data, columns=["State_UT", "Type", "PLFS_2023_24", "Census_2011"])
    return dict(zip(df["State_UT"].str.lower(), df["PLFS_2023_24"])), df["PLFS_2023_24"].mean()


LITERACY_LOOKUP, NATIONAL_AVG = _load_literacy_lookup()


def get_literacy_rate(state: str, age: int) -> str:
    if age is None or age < 7:
        return "NA"

    p = LITERACY_LOOKUP.get(state.strip().lower(), NATIONAL_AVG) if state else NATIONAL_AVG
    return "Yes" if random.random() < (p / 100) else "No"


def update_users_literacy():
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
                    SELECT A.id, B.state, A.age
                    FROM user_detail AS A
                    JOIN addresses AS B ON A.address_id = B.id;
                """
            )
            rows = cursor.fetchall()

            updates = [(get_literacy_rate(row[1], row[2]), row[0]) for row in rows]

            sql = "UPDATE users SET literate = %s WHERE id = %s;"
            cursor.executemany(sql, updates)

    print(f"Updated {len(updates)} rows successfully.")

if __name__ == "__main__":
    update_users_literacy()
