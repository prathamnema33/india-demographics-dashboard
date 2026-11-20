import os
from dotenv import load_dotenv
import pandas as pd
import geopandas as gpd
from sqlalchemy import URL, create_engine

# Database connection
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

# Load GeoJSON
geo_df = gpd.read_file("district_level.geojson")

# Normalize names
def normalize_name(name):
    return str(name).strip().lower().replace("&", "and")

geo_df["district_key"] = geo_df["shapeName"].apply(normalize_name)

# Fix Lakshadweep temporarily
geo_df["state_key"] = None

# Load state GeoJSON
state_geo = gpd.read_file("state_level.geojson")
state_geo["state_key"] = state_geo["shapeName"].apply(normalize_name)

# Spatial join
district_points = geo_df[["geometry"]].copy()
district_points["geometry"] = district_points.geometry.representative_point()

joined = gpd.sjoin(
    district_points,
    state_geo[["state_key", "geometry"]],
    how="left",
    predicate="within"
)

geo_df["state_key"] = joined["state_key"].values

# Manual temporary assignment
geo_df.loc[
    geo_df["district_key"] == "lakshadweep",
    "state_key"
] = "lakshadweep"

# Load database districts
db_df = pd.read_sql("""
    SELECT DISTINCT state, city
    FROM addresses
    WHERE state IS NOT NULL
      AND city IS NOT NULL
""", engine)

db_df["state_key"] = db_df["state"].apply(normalize_name)
db_df["district_key"] = db_df["city"].apply(normalize_name)

# Compare pairs
geo_pairs = set(zip(geo_df["state_key"], geo_df["district_key"]))
db_pairs = set(zip(db_df["state_key"], db_df["district_key"]))

print("\n========== DISTRICT COMPARISON ==========")
print("GeoJSON districts:", len(geo_pairs))
print("Database districts:", len(db_pairs))
print("Missing in database:", len(geo_pairs - db_pairs))
print("Missing in GeoJSON:", len(db_pairs - geo_pairs))

print("\nMissing in database:")
for item in sorted(geo_pairs - db_pairs):
    print(item)

print("\nMissing in GeoJSON:")
for item in sorted(db_pairs - geo_pairs):
    print(item)

print("=========================================")