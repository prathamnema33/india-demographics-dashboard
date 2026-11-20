import random
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy import URL, create_engine, text
from faker import Faker
from sqlalchemy.orm import sessionmaker
from validator import User,Address,hash_password
from dod import get_dod
from add_religion import get_random_religion
fake = Faker("en_IN")

# 1. Pydantic Model Validation


# 2. Database Connection
load_dotenv()
DATABASE_URL = URL.create(
    "postgresql+psycopg2",
    username=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "8137")),
    database=os.getenv("DB_NAME", "Users"),
)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 3. Raw Census & Tech Group Demographic Weights Matrix
# Combines all 28 states and 8 UTs (Weights sum to exactly 1.0)
STATE_INTERVALS = [
    {"state": "Uttar Pradesh", "weight": 0.1703, "lower": 0.000000, "upper": 0.170473},
    {"state": "Bihar", "weight": 0.0929, "lower": 0.170473, "upper": 0.263502},
    {"state": "Maharashtra", "weight": 0.0907, "lower": 0.263502, "upper": 0.354367},
    {"state": "West Bengal", "weight": 0.0704, "lower": 0.354367, "upper": 0.424925},
    {"state": "Madhya Pradesh", "weight": 0.0629, "lower": 0.424925, "upper": 0.487897},
    {"state": "Rajasthan", "weight": 0.0587, "lower": 0.487897, "upper": 0.546683},
    {"state": "Tamil Nadu", "weight": 0.0543, "lower": 0.546683, "upper": 0.601024},
    {"state": "Gujarat", "weight": 0.0520, "lower": 0.601024, "upper": 0.653059},
    {"state": "Karnataka", "weight": 0.0483, "lower": 0.653059, "upper": 0.701389},
    {"state": "Andhra Pradesh", "weight": 0.0376, "lower": 0.701389, "upper": 0.739015},
    {"state": "Odisha", "weight": 0.0324, "lower": 0.739015, "upper": 0.771438},
    {"state": "Jharkhand", "weight": 0.0276, "lower": 0.771438, "upper": 0.799068},
    {"state": "Telangana", "weight": 0.0268, "lower": 0.799068, "upper": 0.825898},
    {"state": "Kerala", "weight": 0.0251, "lower": 0.825898, "upper": 0.851033},
    {"state": "Assam", "weight": 0.0250, "lower": 0.851033, "upper": 0.876045},
    {"state": "Punjab", "weight": 0.0219, "lower": 0.876045, "upper": 0.897966},
    {"state": "Chhattisgarh", "weight": 0.0219, "lower": 0.897966, "upper": 0.919887},
    {"state": "Haryana", "weight": 0.0215, "lower": 0.919887, "upper": 0.941408},
    {"state": "Delhi", "weight": 0.0159, "lower": 0.941408, "upper": 0.957362},
    {"state": "Jammu & Kashmir", "weight": 0.0097, "lower": 0.957362, "upper": 0.967076},
    {"state": "Uttarakhand", "weight": 0.0084, "lower": 0.967076, "upper": 0.975484},
    {"state": "Himachal Pradesh", "weight": 0.0053, "lower": 0.975484, "upper": 0.980786},
    {"state": "Tripura", "weight": 0.0030, "lower": 0.980786, "upper": 0.983788},
    {"state": "Meghalaya", "weight": 0.0024, "lower": 0.983788, "upper": 0.986190},
    {"state": "Manipur", "weight": 0.0023, "lower": 0.986190, "upper": 0.988492},
    {"state": "Nagaland", "weight": 0.0016, "lower": 0.988492, "upper": 0.990093},
    {"state": "Goa", "weight": 0.0011, "lower": 0.990093, "upper": 0.991194},
    {"state": "Arunachal Pradesh", "weight": 0.0011, "lower": 0.991194, "upper": 0.992295},
    {"state": "Puducherry", "weight": 0.0010, "lower": 0.992295, "upper": 0.993296},
    {"state": "Mizoram", "weight": 0.0009, "lower": 0.993296, "upper": 0.994197},
    {"state": "Chandigarh", "weight": 0.0008, "lower": 0.994197, "upper": 0.994998},
    {"state": "Sikkim", "weight": 0.0005, "lower": 0.994998, "upper": 0.995498},
    {"state": "Dadra & Nagar Haveli and Daman & Diu", "weight": 0.0004, "lower": 0.995498, "upper": 0.995898},
    {"state": "Andaman & Nicobar Islands", "weight": 0.0003, "lower": 0.995898, "upper": 0.996198},
    {"state": "Ladakh", "weight": 0.0002, "lower": 0.996198, "upper": 0.996398},
    {"state": "Lakshadweep", "weight": 0.0001, "lower": 0.996398, "upper": 1.000000}
]

# Programmatically build the clean mathematical interval boundaries

RELIGION_INTERVALS = [
    {"religion": "Hinduism", "lower": 0.0, "upper": 0.7980},
    {"religion": "Islam", "lower": 0.7980, "upper": 0.9403},
    {"religion": "Christianity", "lower": 0.9403, "upper": 0.9633},
    {"religion": "Sikhism", "lower": 0.9633, "upper": 0.9805},
    {"religion": "Buddhism", "lower": 0.9805, "upper": 0.9875},
    {"religion": "Jainism", "lower": 0.9875, "upper": 0.9912},
    {"religion": "Others", "lower": 0.9912, "upper": 1}
]

AGE_10YR_INTERVALS = [
    {"min": 0,  "max": 9,  "lower": 0.000, "upper": 0.165},
    {"min": 10, "max": 19, "lower": 0.165, "upper": 0.340},
    {"min": 20, "max": 29, "lower": 0.340, "upper": 0.515},
    {"min": 30, "max": 39, "lower": 0.515, "upper": 0.665},
    {"min": 40, "max": 49, "lower": 0.665, "upper": 0.795},
    {"min": 50, "max": 59, "lower": 0.795, "upper": 0.895},
    {"min": 60, "max": 69, "lower": 0.895, "upper": 0.960},
    {"min": 70, "max": 79, "lower": 0.960, "upper": 0.990},
    {"min": 80, "max": 95, "lower": 0.990, "upper": 1.000}
]
def sample_name_and_gender():
    gender = random.choice(["Male", "Female"])

    if gender == "Male":
        first_name = fake.first_name_male()
    else:
        first_name = fake.first_name_female()

    last_name = fake.last_name()
    print(
        f"[sample_name_and_gender] gender={gender}, "
        f"first_name={first_name}, last_name={last_name}"
    )
    return first_name, last_name, gender


def sample_state():
    r = random.random()
    for entry in STATE_INTERVALS:
        if entry["lower"] < r <= entry["upper"]:
            print(f"[sample_state] r={r}, selected_state={entry['state']}")
            return entry["state"]
    print(f"[sample_state] r={r}, fallback_state={STATE_INTERVALS[0]['state']}")
    return STATE_INTERVALS[0]["state"]





def sample_exact_age():
    r = random.random()
    for entry in AGE_10YR_INTERVALS:
        if entry["lower"] < r <= entry["upper"]:
            age = random.randint(entry["min"], entry["max"])
            print(
                f"[sample_exact_age] r={r}, age_range="
                f"{entry['min']}-{entry['max']}, age={age}"
            )
            return age
    print(f"[sample_exact_age] r={r}, fallback_age=25")
    return 25


def generate_random_profile() -> Optional[User]:

    chosen_state = sample_state()
    first_name, last_name, gender = sample_name_and_gender()

    religion = get_random_religion()
    age = sample_exact_age()
    print(
        "[generate_random_profile] "
        f"chosen_state={chosen_state}, first_name={first_name}, "
        f"last_name={last_name}, gender={gender}, religion={religion}, age={age}"
    )

    # Generate DOB according to sampled age
    today = datetime.today().date()

    try:
        latest_dob = today.replace(year=today.year - age)
    except ValueError:
        latest_dob = today.replace(year=today.year - age, day=28)

    try:
        earliest_dob = today.replace(year=today.year - age - 1)
    except ValueError:
        earliest_dob = today.replace(year=today.year - age - 1, day=28)

    from datetime import date

    dob = fake.date_between_dates(
        date_start=earliest_dob + timedelta(days=1),
        date_end=latest_dob
    )
    print(
        "[generate_random_profile] "
        f"today={today}, earliest_dob={earliest_dob}, "
        f"latest_dob={latest_dob}, dob={dob}"
    )

    db = SessionLocal()

    try:
        query = text("""
        SELECT district, state_name, pincode
        FROM all_india_pincodes
        WHERE LOWER(TRIM(state_name)) = LOWER(TRIM(:state_param))
        ORDER BY RANDOM()
        LIMIT 1
    """)

        result = db.execute(
        query,
        {"state_param": chosen_state}
    ).fetchone()
        print(f"[generate_random_profile] address_query_result={result}")

        if result is None:
            print(f"No address found for {chosen_state}")
            return None

        # Map database columns to Pydantic Address fields
        address = Address(
        city=result.district.title(),
        state=result.state_name.title(),
        zip_code=str(result.pincode).zfill(6)
    )
        print(f"[generate_random_profile] address={address}")

        username = fake.unique.bothify(
        text="user####??"
    ).lower()
        print(f"[generate_random_profile] username={username}")

        password = (
    fake.random_lowercase_letter()
    + fake.random_uppercase_letter()
    + str(random.randint(10000, 99999))
    + "@"
)
        # Generate DOD only after DOB
        dod=get_dod(state=address.state,dob=dob)
        from add_literacy_rate import get_literacy_rate
        literacy=get_literacy_rate(state=address.state,age=age)


        profile = User(
        username=username,
        password=password,
        First_name=first_name,
        Last_name=last_name,
        dob=dob,
        age=age,
        address=address,
        religion=religion,
        Gender=gender,
        dod=dod,
        literate=literacy
    )
        print(
            "[generate_random_profile] profile="
            f"{profile.model_dump(exclude={'password'})}"
        )

        return profile

    except Exception as e:
        print(f"Pipeline error: {e}")
        return None

    finally:
        db.close()



def insert_user(profile, db):

    # Step 1: Check existing address
    address_query = text("""
        SELECT id
        FROM addresses
        WHERE city = :city
          AND state = :state
          AND zip_code = :zip_code
        LIMIT 1
    """)

    address_result = db.execute(
        address_query,
        {
            "city": profile.address.city,
            "state": profile.address.state,
            "zip_code": profile.address.zip_code
        }
    ).fetchone()

    if address_result:
        address_id = address_result.id

    else:
        insert_address = text("""
            INSERT INTO addresses (city, state, zip_code)
            VALUES (:city, :state, :zip_code)
            RETURNING id
        """)

        address_id = db.execute(
            insert_address,
            {
                "city": profile.address.city,
                "state": profile.address.state,
                "zip_code": profile.address.zip_code
            }
        ).scalar_one()

    # Step 2: Hash password
    hashed_password = hash_password(profile.password)

    # Step 3: Insert user
    insert_user_query = text("""
        INSERT INTO user_detail (
            username,
            password_hash,
            first_name,
            last_name,
            dob,
            age,
            address_id,
            religion,
            dod,
            literate
        )
        VALUES (
            :username,
            :password_hash,
            :first_name,
            :last_name,
            :dob,
            :age,
            :address_id,
            :religion,
            :dod,
            :literate
        )
    """)

    db.execute(
        insert_user_query,
        {
            "username": profile.username,
            "password_hash": hashed_password,
            "first_name": profile.First_name,
            "last_name": profile.Last_name,
            "dob": profile.dob,
            "age": profile.age,
            "address_id": address_id,
            "religion": profile.religion,
            "dod": profile.dod,
            "literate": profile.literate
        }
    )


if __name__ == "__main__":
    for i in range(10000):
        db = SessionLocal()
        try:
            profile = generate_random_profile()
            if profile:
                with db.begin():
                    insert_user(profile, db)

                print(f"User {i+1} inserted successfully!")
            else:
                print("Profile generation failed.")
        except Exception as e:
            print("Insertion failed:", repr(e))
        finally:
            db.close()