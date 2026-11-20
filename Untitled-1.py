
import geopandas as gpd
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine

# ----------------------------------
# 1. LOAD ALL DATAMEET SHAPEFILES
# ----------------------------------

root = Path(r"C:\Users\lenovo\credential\maps-master")

shapefiles = list(root.rglob("*.shp"))

print("Shapefiles found:", len(shapefiles))

if not shapefiles:
    raise FileNotFoundError("No shapefiles found!")

frames = []

for file in shapefiles:
    temp = gpd.read_file(file)

    required_columns = ["ST_NAME", "DIST_NAME"]

    if all(col in temp.columns for col in required_columns):
        temp = temp[required_columns].copy()
        frames.append(temp)
    else:
        print("Skipping:", file)

if not frames:
    raise ValueError("No valid district shapefiles found!")

gdf = pd.concat(frames, ignore_index=True)

datameet = gdf.copy()
datameet.columns = ["state", "district"]


# ----------------------------------
# 2. LOAD POSTGRESQL DATA
# ----------------------------------

import os
from dotenv import load_dotenv
from sqlalchemy import URL

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

pincode_df = pd.read_sql("""
    SELECT DISTINCT state_name, district
    FROM all_india_pincodes
    WHERE state_name IS NOT NULL
      AND district IS NOT NULL
""", engine)

pincode_df.columns = ["state", "district"]


# ----------------------------------
# 3. NORMALIZE TEXT
# ----------------------------------

def normalize(series):
    return (
        series.astype(str)
        .str.upper()
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )

for df in [datameet, pincode_df]:
    df["state"] = normalize(df["state"])
    df["district"] = normalize(df["district"])


# ----------------------------------
# 4. STATE ALIASES
# ----------------------------------

state_aliases = {
    "ORISSA": "ODISHA",
    "ANDAMAN & NICOBAR ISLAND": "ANDAMAN AND NICOBAR ISLANDS",
    "ANDAMAN AND NICOBAR ISLAND": "ANDAMAN AND NICOBAR ISLANDS",
    "JAMMU & KASHMIR": "JAMMU AND KASHMIR"
}

datameet["state"] = datameet["state"].replace(state_aliases)
pincode_df["state"] = pincode_df["state"].replace(state_aliases)


# ----------------------------------
# 5. DISTRICT ALIASES
# ----------------------------------

district_aliases = {
    "ANUGUL": "ANGUL",
    "BADGAM": "BUDGAM",
    "AHMADNAGAR": "AHMEDNAGAR",
    "ALLAHABAD": "PRAYAGRAJ",
    "KAWARDHA": "KABIRDHAM",
    "KANCHEEPURAM": "KANCHIPURAM",
    "BANGALORE": "BENGALURU",
    "BARAMULA": "BARAMULLA"
}

datameet["district"] = datameet["district"].replace(
    district_aliases
)


# ----------------------------------
# 6. REMOVE DUPLICATES
# ----------------------------------

datameet = datameet.drop_duplicates(
    subset=["state", "district"]
)

pincode_df = pincode_df.drop_duplicates(
    subset=["state", "district"]
)


# ----------------------------------
# 7. COMPARE DATASETS
# ----------------------------------

comparison = datameet.merge(
    pincode_df,
    on=["state", "district"],
    how="left",
    indicator=True
)

matched = comparison[
    comparison["_merge"] == "both"
]

missing = comparison[
    comparison["_merge"] == "left_only"
]


# ----------------------------------
# 8. DISPLAY REPORT
# ----------------------------------

print("\n========== COMPARISON REPORT ==========")

print("DataMeet districts:", len(datameet))
print("Pincode districts:", len(pincode_df))
print("Matched districts:", len(matched))
print("Unmatched districts:", len(missing))

print("\n========== UNMATCHED DISTRICTS ==========")

print(
    missing[["state", "district"]]
    .to_string(index=False)
)


# ----------------------------------
# 9. SAVE REPORTS
# ----------------------------------

matched[["state", "district"]].to_csv(
    "matched_districts.csv",
    index=False
)

missing[["state", "district"]].to_csv(
    "unmatched_districts.csv",
    index=False
)

print("\nReports saved successfully!")
unmatched_clean = missing.dropna(
    subset=["state", "district"]
).copy()

unmatched_clean["state"] = normalize(unmatched_clean["state"])
unmatched_clean["district"] = normalize(unmatched_clean["district"])

state_report = (
    unmatched_clean
    .groupby("state")
    .size()
    .reset_index(name="unmatched_count")
    .sort_values("unmatched_count", ascending=False)
)

print(state_report.to_string(index=False))

unmatched_clean.to_csv(
    "unmatched_districts_clean.csv",
    index=False
)