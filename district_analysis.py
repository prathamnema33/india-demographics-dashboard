import os
from dotenv import load_dotenv
import geopandas as gpd
import pandas as pd
from pathlib import Path

# Change this to your extracted Districts folder
folder = Path(r"C:\Users\lenovo\credential\maps-master\Districts")

# Find shapefiles
shapefiles = list(folder.rglob("*.shp"))

print("Shapefiles found:", shapefiles)

# Read the first shapefile
gdf = gpd.read_file(shapefiles[0])

# Display available columns
print(gdf.columns)

# Display first 5 records
print(gdf.head())
districts = gdf[["ST_NM", "DISTRICT"]].drop_duplicates()

print("Total districts:", len(districts))

print(
    districts.groupby("ST_NM")["DISTRICT"]
    .nunique()
    .sort_values(ascending=False)
)
from sqlalchemy import URL, create_engine
import pandas as pd

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

# Normalize names before comparison
def normalize(series):
    return series.str.upper().str.strip()

datameet = districts.copy()

datameet["state"] = normalize(datameet["ST_NM"])
datameet["district"] = normalize(datameet["DISTRICT"])

pincode_df["state"] = normalize(pincode_df["state_name"])
pincode_df["district"] = normalize(pincode_df["district"])

# Find district combinations in DataMeet but not in your database
missing = datameet.merge(
    pincode_df[["state", "district"]],
    on=["state", "district"],
    how="left",
    indicator=True
)

missing = missing[missing["_merge"] == "left_only"]

print("Districts not found in pincode data:")
print(missing[["state", "district"]])