from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time
import uuid
from collections import Counter, defaultdict, deque
from concurrent.futures import Future, ProcessPoolExecutor
from datetime import date, timedelta
from multiprocessing import get_context
from typing import Any

from faker import Faker
from sqlalchemy import MetaData, Table, create_engine, func, inspect, insert, select, text, tuple_
from sqlalchemy.engine import Connection, Engine

from add_literacy_rate import LITERACY_LOOKUP, NATIONAL_AVG as LITERACY_NATIONAL_AVG, get_literacy_rate
from add_religion import RELIGION_INTERVALS, get_random_religion
from dod import HEALTH_LOOKUP, NATIONAL_AVG as HEALTH_NATIONAL_AVG, fake as dod_fake, get_dod
from validator import Address, User, hash_password


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
    {"state": "Lakshadweep", "weight": 0.0001, "lower": 0.996398, "upper": 1.000000},
]

AGE_10YR_INTERVALS = [
    {"min": 0, "max": 9, "lower": 0.000, "upper": 0.165},
    {"min": 10, "max": 19, "lower": 0.165, "upper": 0.340},
    {"min": 20, "max": 29, "lower": 0.340, "upper": 0.515},
    {"min": 30, "max": 39, "lower": 0.515, "upper": 0.665},
    {"min": 40, "max": 49, "lower": 0.665, "upper": 0.795},
    {"min": 50, "max": 59, "lower": 0.795, "upper": 0.895},
    {"min": 60, "max": 69, "lower": 0.895, "upper": 0.960},
    {"min": 70, "max": 79, "lower": 0.960, "upper": 0.990},
    {"min": 80, "max": 95, "lower": 0.990, "upper": 1.000},
]

USER_INSERT_FIELDS = {
    "username",
    "password_hash",
    "first_name",
    "last_name",
    "dob",
    "age",
    "address_id",
    "religion",
    "dod",
    "literate",
}

_FAKER: Faker | None = None
_PINCODES_BY_STATE: dict[str, list[tuple[str, str, str]]] = {}


def _normalize_state(value: str) -> str:
    value = value.strip().lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    value = re.sub(r"\s+", " ", value)
    if value.startswith("the "):
        value = value[4:]
    return value


def _sample_state() -> str:
    value = random.random()
    for interval in STATE_INTERVALS:
        if interval["lower"] < value <= interval["upper"]:
            return interval["state"]
    return STATE_INTERVALS[0]["state"]


def _sample_age() -> int:
    value = random.random()
    for interval in AGE_10YR_INTERVALS:
        if interval["lower"] < value <= interval["upper"]:
            return random.randint(interval["min"], interval["max"])
    return 25


def _valid_name(generator: Any) -> str:
    for _ in range(100):
        value = generator()
        if 3 <= len(value) <= 20:
            return value
    raise ValueError("Faker did not produce a name that satisfies User validation")


def _dob_for_age(age: int) -> date:
    if _FAKER is None:
        raise RuntimeError("Worker Faker instance was not initialized")

    today = date.today()
    try:
        latest_dob = today.replace(year=today.year - age)
    except ValueError:
        latest_dob = today.replace(year=today.year - age, day=28)
    try:
        earliest_dob = today.replace(year=today.year - age - 1)
    except ValueError:
        earliest_dob = today.replace(year=today.year - age - 1, day=28)

    return _FAKER.date_between_dates(
        date_start=earliest_dob + timedelta(days=1),
        date_end=latest_dob,
    )


def _initialize_worker(pincodes_by_state: dict[str, list[tuple[str, str, str]]]) -> None:
    global _FAKER, _PINCODES_BY_STATE

    seed = int.from_bytes(os.urandom(8), byteorder="big")
    random.seed(seed)
    _FAKER = Faker("en_IN")
    _FAKER.seed_instance(seed)
    dod_fake.seed_instance(seed)
    _PINCODES_BY_STATE = pincodes_by_state


def _generate_profile() -> dict[str, Any]:
    if _FAKER is None:
        raise RuntimeError("Worker Faker instance was not initialized")

    chosen_state = _sample_state()
    pincode_options = _PINCODES_BY_STATE.get(_normalize_state(chosen_state))
    if not pincode_options:
        raise ValueError(f"No valid pincode/district rows for state {chosen_state!r}")

    district, state_name, pincode = random.choice(pincode_options)
    address = Address(
        city=district.title(),
        state=state_name.title(),
        zip_code=pincode,
    )

    gender = random.choice(["Male", "Female"])
    first_name_generator = (
        _FAKER.first_name_male if gender == "Male" else _FAKER.first_name_female
    )
    first_name = _valid_name(first_name_generator)
    last_name = _valid_name(_FAKER.last_name)

    age = _sample_age()
    dob = _dob_for_age(age)
    religion = get_random_religion()
    dod = get_dod(state=address.state, dob=dob)
    literacy = get_literacy_rate(state=address.state, age=age)
    username = f"user{uuid.uuid4().hex[:16]}"
    password = (
        _FAKER.random_lowercase_letter()
        + _FAKER.random_uppercase_letter()
        + str(random.randint(10000, 99999))
        + "@"
    )

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
        literate=literacy,
    )
    if profile.age != age:
        raise ValueError(f"Generated DOB {dob} did not validate as sampled age {age}")

    return {
        "username": profile.username,
        "password_hash": hash_password(profile.password),
        "first_name": profile.First_name,
        "last_name": profile.Last_name,
        "dob": profile.dob,
        "age": profile.age,
        "religion": profile.religion,
        "dod": profile.dod,
        "literate": profile.literate,
        "_address_key": (
            profile.address.city,
            profile.address.state,
            profile.address.zip_code,
        ),
        "_sampled_state": chosen_state,
        "_address_state": profile.address.state,
        "_religion": profile.religion,
        "_age": profile.age,
        "_dod_probability_state": profile.address.state,
    }


def _generate_batch(count: int) -> list[dict[str, Any]]:
    profiles = []
    for _ in range(count):
        profiles.append(_generate_profile())
    return profiles


def _unique_index_columns(index: dict[str, Any]) -> tuple[str, ...]:
    return tuple(index.get("column_names") or ())


def _has_unique_columns(
    inspector: Any,
    table_name: str,
    schema: str,
    expected: set[str],
) -> bool:
    for constraint in inspector.get_unique_constraints(table_name, schema=schema):
        columns = constraint.get("column_names") or []
        if len(columns) == len(expected) and set(columns) == expected:
            return True
    for index in inspector.get_indexes(table_name, schema=schema):
        columns = _unique_index_columns(index)
        if index.get("unique") and len(columns) == len(expected) and set(columns) == expected:
            return True
    return False


def _check_required_columns(table: Table, insert_fields: set[str]) -> None:
    missing_fields = insert_fields.difference(table.c.keys())
    if missing_fields:
        raise RuntimeError(
            f"{table.name} is missing required insert columns: {', '.join(sorted(missing_fields))}"
        )

    unresolved = []
    for column in table.columns:
        if (
            not column.nullable
            and column.name not in insert_fields
            and column.server_default is None
            and not column.primary_key
        ):
            unresolved.append(column.name)
    if unresolved:
        raise RuntimeError(
            f"{table.name} has required columns with no value or server default: "
            f"{', '.join(sorted(unresolved))}"
        )


def _load_schema_and_pincodes(engine: Engine) -> tuple[Table, Table, dict[str, list[tuple[str, str, str]]], bool]:
    with engine.connect() as connection:
        schema = connection.execute(text("SELECT current_schema()")).scalar_one()
        inspector = inspect(connection)
        available_tables = set(inspector.get_table_names(schema=schema))
        required_tables = {"users", "addresses", "all_india_pincodes"}
        missing_tables = required_tables.difference(available_tables)
        if missing_tables:
            raise RuntimeError(
                f"Required tables are missing from schema {schema!r}: "
                f"{', '.join(sorted(missing_tables))}"
            )

        metadata = MetaData()
        users = Table("users", metadata, schema=schema, autoload_with=connection)
        addresses = Table("addresses", metadata, schema=schema, autoload_with=connection)
        pincodes = Table("all_india_pincodes", metadata, schema=schema, autoload_with=connection)

        _check_required_columns(users, USER_INSERT_FIELDS)
        _check_required_columns(addresses, {"city", "state", "zip_code"})

        address_foreign_key = any(
            foreign_key.get("constrained_columns") == ["address_id"]
            and foreign_key.get("referred_table") == "addresses"
            and foreign_key.get("referred_columns") == ["id"]
            for foreign_key in inspector.get_foreign_keys("users", schema=schema)
        )
        if not address_foreign_key:
            raise RuntimeError("users.address_id has no foreign key to addresses.id")

        if not _has_unique_columns(inspector, "users", schema, {"username"}):
            raise RuntimeError("users.username has no unique constraint or unique index")

        has_address_unique_key = _has_unique_columns(
            inspector, "addresses", schema, {"city", "state", "zip_code"}
        )
        for required_column in ("district", "state_name", "pincode"):
            if required_column not in pincodes.c:
                raise RuntimeError(
                    f"all_india_pincodes is missing required column {required_column!r}"
                )

        grouped: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        excluded_rows = 0
        pincode_rows = connection.execute(
            select(pincodes.c.district, pincodes.c.state_name, pincodes.c.pincode)
        )
        for district, state_name, pincode in pincode_rows:
            if district is None or state_name is None or pincode is None:
                excluded_rows += 1
                continue

            district = str(district).strip()
            state_name = str(state_name).strip()
            pincode = str(pincode).strip()
            if (
                not 3 <= len(district) <= 50
                or not 3 <= len(state_name) <= 50
                or re.fullmatch(r"\d{6}", pincode) is None
            ):
                excluded_rows += 1
                continue

            grouped[_normalize_state(state_name)].append((district, state_name, pincode))

    unavailable_states = [
        interval["state"]
        for interval in STATE_INTERVALS
        if not grouped.get(_normalize_state(interval["state"]))
    ]
    if unavailable_states:
        raise RuntimeError(
            "No valid address reference rows for states: "
            + ", ".join(unavailable_states)
        )

    print(
        f"Loaded {sum(map(len, grouped.values())):,} usable pincode rows; "
        f"excluded {excluded_rows:,} rows that cannot satisfy Address validation."
    )
    if not has_address_unique_key:
        print(
            "addresses has no unique (city, state, zip_code) key; "
            "this script uses one parent writer and reuses matching rows."
        )
    return users, addresses, dict(grouped), has_address_unique_key


def _new_username() -> str:
    value = f"user{uuid.uuid4().hex[:16]}"
    if not 3 <= len(value) <= 20:
        raise ValueError("Generated username does not satisfy User length constraints")
    return value


def _ensure_batch_usernames_unique(
    connection: Connection,
    users: Table,
    profiles: list[dict[str, Any]],
) -> None:
    for _ in range(5):
        first_seen: set[str] = set()
        duplicates: set[int] = set()
        for index, profile in enumerate(profiles):
            username = profile["username"]
            if username in first_seen:
                duplicates.add(index)
            else:
                first_seen.add(username)

        existing = set(
            connection.execute(
                select(users.c.username).where(users.c.username.in_(first_seen))
            ).scalars()
        )
        replace_indexes = duplicates.union(
            index
            for index, profile in enumerate(profiles)
            if profile["username"] in existing
        )
        if not replace_indexes:
            return

        for index in replace_indexes:
            profiles[index]["username"] = _new_username()

    raise RuntimeError("Could not produce unique usernames for the current batch")


def _resolve_addresses(
    connection: Connection,
    addresses: Table,
    profiles: list[dict[str, Any]],
) -> dict[tuple[str, str, str], int]:
    address_keys = list(dict.fromkeys(profile["_address_key"] for profile in profiles))
    if not address_keys:
        return {}

    existing_rows = connection.execute(
        select(
            addresses.c.id,
            addresses.c.city,
            addresses.c.state,
            addresses.c.zip_code,
        )
        .where(
            tuple_(addresses.c.city, addresses.c.state, addresses.c.zip_code).in_(
                address_keys
            )
        )
        .order_by(addresses.c.id)
    )
    address_ids: dict[tuple[str, str, str], int] = {}
    for row in existing_rows:
        key = (row.city, row.state, row.zip_code)
        address_ids.setdefault(key, row.id)

    missing_keys = [key for key in address_keys if key not in address_ids]
    if missing_keys:
        inserted_addresses = connection.execute(
            insert(addresses)
            .values(
                [
                    {"city": city, "state": state, "zip_code": zip_code}
                    for city, state, zip_code in missing_keys
                ]
            )
            .returning(
                addresses.c.id,
                addresses.c.city,
                addresses.c.state,
                addresses.c.zip_code,
            )
        )
        for row in inserted_addresses:
            key = (row.city, row.state, row.zip_code)
            address_ids[key] = row.id

    missing_ids = [key for key in address_keys if key not in address_ids]
    if missing_ids:
        raise RuntimeError(f"Failed to resolve address IDs for {len(missing_ids)} addresses")
    return address_ids


def _insert_batch(
    connection: Connection,
    users: Table,
    addresses: Table,
    profiles: list[dict[str, Any]],
) -> list[str]:
    with connection.begin():
        _ensure_batch_usernames_unique(connection, users, profiles)
        address_ids = _resolve_addresses(connection, addresses, profiles)

        user_rows = [
            {
                "username": profile["username"],
                "password_hash": profile["password_hash"],
                "first_name": profile["first_name"],
                "last_name": profile["last_name"],
                "dob": profile["dob"],
                "age": profile["age"],
                "address_id": address_ids[profile["_address_key"]],
                "religion": profile["religion"],
                "dod": profile["dod"],
                "literate": profile["literate"],
            }
            for profile in profiles
        ]
        connection.execute(insert(users), user_rows)
        usernames = [profile["username"] for profile in profiles]
    return usernames


def _new_stats() -> dict[str, Any]:
    return {
        "state": Counter(),
        "religion": Counter(),
        "age_group": Counter(),
        "literacy_yes": Counter(),
        "literacy_eligible": Counter(),
        "literacy_expected_yes": Counter(),
        "dod_yes": 0,
        "dod_expected": 0.0,
        "dod_total": 0,
    }


def _age_group(age: int) -> str:
    for interval in AGE_10YR_INTERVALS:
        if interval["min"] <= age <= interval["max"]:
            return f"{interval['min']}-{interval['max']}"
    raise ValueError(f"Age {age} is outside configured age intervals")


def _accumulate_stats(stats: dict[str, Any], profiles: list[dict[str, Any]]) -> None:
    for profile in profiles:
        sampled_state = profile["_sampled_state"]
        address_state = profile["_address_state"]
        age = profile["_age"]
        religion = profile["_religion"]

        stats["state"][sampled_state] += 1
        stats["religion"][religion] += 1
        stats["age_group"][_age_group(age)] += 1

        if age >= 7:
            stats["literacy_eligible"][address_state] += 1
            if profile["literate"] == "Yes":
                stats["literacy_yes"][address_state] += 1
            expected_rate = LITERACY_LOOKUP.get(
                address_state.strip().lower(), LITERACY_NATIONAL_AVG
            )
            stats["literacy_expected_yes"][address_state] += expected_rate / 100

        health_score = HEALTH_LOOKUP.get(
            address_state.strip().lower(), HEALTH_NATIONAL_AVG
        )
        stats["dod_expected"] += (1 - health_score / 100) * 0.15
        stats["dod_total"] += 1
        if profile["dod"] is not None:
            stats["dod_yes"] += 1


def _percentage(numerator: float, denominator: float) -> float:
    return (100.0 * numerator / denominator) if denominator else 0.0


def _print_distribution_checks(stats: dict[str, Any], total: int) -> None:
    if not total:
        return

    interval_total = sum(
        item["upper"] - item["lower"] for item in STATE_INTERVALS
    )
    print("Distribution check (observed vs configured target):")
    print("State:")
    for interval in STATE_INTERVALS:
        state = interval["state"]
        observed = stats["state"][state]
        expected = (
            (interval["upper"] - interval["lower"]) / interval_total * 100
        )
        print(
            f"  {state}: {_percentage(observed, total):.2f}% "
            f"vs {expected:.2f}% (n={observed})"
        )

    religion_total = sum(
        item["upper"] - item["lower"] for item in RELIGION_INTERVALS
    )
    print("Religion:")
    for interval in RELIGION_INTERVALS:
        religion = interval["religion"]
        observed = stats["religion"][religion]
        expected = (
            (interval["upper"] - interval["lower"]) / religion_total * 100
        )
        print(
            f"  {religion}: {_percentage(observed, total):.2f}% "
            f"vs {expected:.2f}% (n={observed})"
        )

    print("Age bracket:")
    for interval in AGE_10YR_INTERVALS:
        group = f"{interval['min']}-{interval['max']}"
        observed = stats["age_group"][group]
        expected = (interval["upper"] - interval["lower"]) * 100
        print(
            f"  {group}: {_percentage(observed, total):.2f}% "
            f"vs {expected:.2f}% (n={observed})"
        )

    literacy_eligible = sum(stats["literacy_eligible"].values())
    literacy_yes = sum(stats["literacy_yes"].values())
    literacy_expected = sum(stats["literacy_expected_yes"].values())
    print(
        "Literacy (ages 7+, NA excluded): "
        f"{_percentage(literacy_yes, literacy_eligible):.2f}% Yes "
        f"vs {_percentage(literacy_expected, literacy_eligible):.2f}% "
        f"expected ({literacy_eligible:,} eligible)"
    )
    for state, eligible in sorted(stats["literacy_eligible"].items()):
        expected_yes = stats["literacy_expected_yes"][state]
        observed_yes = stats["literacy_yes"][state]
        print(
            f"  {state}: {_percentage(observed_yes, eligible):.2f}% Yes "
            f"vs {_percentage(expected_yes, eligible):.2f}% expected "
            f"(n={eligible})"
        )

    print(
        "DOD: "
        f"{_percentage(stats['dod_yes'], stats['dod_total']):.2f}% with DOD "
        f"vs {_percentage(stats['dod_expected'], stats['dod_total']):.2f}% "
        f"expected ({stats['dod_total']:,} profiles)"
    )


def _verify_inserted_rows(
    engine: Engine,
    users: Table,
    addresses: Table,
    usernames: list[str],
) -> tuple[int, int]:
    found = 0
    orphaned = 0
    chunk_size = 1000
    with engine.connect() as connection:
        for offset in range(0, len(usernames), chunk_size):
            chunk = usernames[offset : offset + chunk_size]
            found += connection.execute(
                select(func.count())
                .select_from(users)
                .where(users.c.username.in_(chunk))
            ).scalar_one()
            orphaned += connection.execute(
                select(func.count())
                .select_from(users.outerjoin(addresses, users.c.address_id == addresses.c.id))
                .where(users.c.username.in_(chunk), addresses.c.id.is_(None))
            ).scalar_one()
    return found, orphaned


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate validated synthetic user profiles with worker processes."
    )
    parser.add_argument(
        "--total-users",
        type=int,
        default=100_000,
        help="Number of profiles to generate (default: 100000).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=2_000,
        help="Number of profiles per transaction (default: 2000).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Number of generation workers (default: 2).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and validate profiles without inserting rows.",
    )
    parser.add_argument(
        "--check-distributions",
        action="store_true",
        help="Compare generated distributions with configured probabilities.",
    )
    args = parser.parse_args()
    if args.total_users < 1:
        parser.error("--total-users must be at least 1")
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    return args


def main() -> int:
    args = _parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Set it in the environment; do not put credentials in this file."
        )

    engine = create_engine(
        database_url,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
        hide_parameters=True,
    )
    started_at = time.perf_counter()
    inserted_count = 0
    generated_count = 0
    committed_batches = 0
    distribution_stats = _new_stats()
    inserted_usernames: list[str] = []
    users: Table | None = None
    addresses: Table | None = None
    try:
        users, addresses, pincodes_by_state, _ = _load_schema_and_pincodes(engine)
        batch_count = (args.total_users + args.batch_size - 1) // args.batch_size
        max_in_flight = max(1, args.workers * 2)
        pending: deque[tuple[int, Future[list[dict[str, Any]]]]] = deque()
        next_batch = 0

        with ProcessPoolExecutor(
            max_workers=args.workers,
            mp_context=get_context("spawn"),
            initializer=_initialize_worker,
            initargs=(pincodes_by_state,),
        ) as executor:
            while next_batch < batch_count or pending:
                while next_batch < batch_count and len(pending) < max_in_flight:
                    batch_size = min(
                        args.batch_size,
                        args.total_users - next_batch * args.batch_size,
                    )
                    future = executor.submit(
                        _generate_batch,
                        batch_size,
                    )
                    pending.append((next_batch + 1, future))
                    next_batch += 1

                batch_number, future = pending.popleft()
                try:
                    profiles = future.result()
                except Exception as exc:
                    print(
                        f"Batch {batch_number} generation failed: {exc}",
                        file=sys.stderr,
                    )
                    raise

                generated_count += len(profiles)
                _accumulate_stats(distribution_stats, profiles)

                if args.dry_run:
                    print(
                        f"Dry-run validated batch {batch_number}/{batch_count}: "
                        f"{generated_count:,}/{args.total_users:,} profiles."
                    )
                    continue

                try:
                    with engine.connect() as writer:
                        names = _insert_batch(writer, users, addresses, profiles)
                except Exception as exc:
                    print(
                        f"Batch {batch_number} failed and was rolled back: {exc}",
                        file=sys.stderr,
                    )
                    raise

                inserted_usernames.extend(names)
                inserted_count += len(names)
                committed_batches += 1
                elapsed = time.perf_counter() - started_at
                throughput = inserted_count / elapsed if elapsed else 0.0
                print(
                    f"Committed batch {batch_number}/{batch_count}: "
                    f"{inserted_count:,}/{args.total_users:,} users "
                    f"({throughput:,.1f} users/s)."
                )

        if args.dry_run:
            print("Dry-run complete; no rows were inserted.")
        else:
            verified_count, orphaned_count = _verify_inserted_rows(
                engine, users, addresses, inserted_usernames
            )
            print(
                f"Verification: {verified_count:,}/{inserted_count:,} inserted users found; "
                f"{orphaned_count:,} orphaned address references."
            )
            if verified_count != inserted_count or orphaned_count:
                raise RuntimeError("Post-insert verification failed")

        if args.check_distributions:
            _print_distribution_checks(distribution_stats, generated_count)
        return 0
    except Exception:
        if inserted_usernames and users is not None and addresses is not None:
            try:
                verified_count, orphaned_count = _verify_inserted_rows(
                    engine, users, addresses, inserted_usernames
                )
                print(
                    f"Verification after failure: {verified_count:,}/"
                    f"{inserted_count:,} committed users found; "
                    f"{orphaned_count:,} orphaned address references."
                )
            except Exception as verification_error:
                print(
                    f"Verification after failure also failed: {verification_error}",
                    file=sys.stderr,
                )
        raise
    finally:
        elapsed = time.perf_counter() - started_at
        throughput = (inserted_count if not args.dry_run else generated_count) / elapsed if elapsed else 0.0
        print(
            f"Run summary: inserted={inserted_count:,}, "
            f"committed_batches={committed_batches:,}, "
            f"elapsed={elapsed:.1f}s, throughput={throughput:,.1f} users/s."
        )
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
