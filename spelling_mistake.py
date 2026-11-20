import re
import shutil
import unicodedata
from difflib import get_close_matches, SequenceMatcher
from getpass import getpass

import geopandas as gpd
import pandas as pd
from sqlalchemy import URL, create_engine


# =====================================================
# CONFIGURATION
# =====================================================

DISTRICT_GEOJSON = "district_level.geojson"
STATE_GEOJSON = "state_level.geojson"

# The original GeoJSON will be updated after a backup is created.
BACKUP_GEOJSON = "district_level_backup.geojson"

MISSING_REPORT = "missing_in_geojson.csv"
EXTRA_REPORT = "extra_in_geojson.csv"
SUGGESTIONS_REPORT = "spelling_suggestions.csv"
CORRECTIONS_REPORT = "applied_corrections.csv"

# Fuzzy matching threshold. Suggestions below this are not generated.
FUZZY_CUTOFF = 0.70


# =====================================================
# 1. NORMALIZE NAMES
# =====================================================

def normalize_name(name):
    if pd.isna(name):
        return ""

    name = unicodedata.normalize("NFKD", str(name))
    name = "".join(
        char for char in name
        if not unicodedata.combining(char)
    )
    name = name.lower().strip()
    return re.sub(r"[^a-z0-9]", "", name)


# =====================================================
# 2. DATABASE CONNECTION AND DATA
# =====================================================

password = getpass("Enter PostgreSQL password: ")

connection_url = URL.create(
    drivername="postgresql+psycopg2",
    username="postgres",
    password=password,
    host="localhost",
    port=8137,
    database="Users"
)

engine = create_engine(connection_url)

query = """
SELECT DISTINCT
    state_name,
    district
FROM all_india_pincodes
WHERE state_name IS NOT NULL
  AND district IS NOT NULL
ORDER BY state_name, district;
"""

try:
    with engine.connect() as conn:
        db_df = pd.read_sql(query, conn)
    print("\nDatabase connected successfully!")
finally:
    engine.dispose()

print("\n========== DATABASE SUMMARY ==========")
print("Total unique state-district pairs:", len(db_df))
print("Unique states:", db_df["state_name"].nunique())
print(db_df.head(10).to_string(index=False))


# =====================================================
# 3. LOAD GEOJSON FILES
# =====================================================

district_gdf = gpd.read_file(DISTRICT_GEOJSON)
state_gdf = gpd.read_file(STATE_GEOJSON)

print("\n========== GEOJSON SUMMARY ==========")
print("District features:", len(district_gdf))
print("State features:", len(state_gdf))

if "shapeName" not in district_gdf.columns:
    raise KeyError(
        "The district GeoJSON must contain a 'shapeName' column."
    )

if not {"shapeName", "shapeISO"}.issubset(state_gdf.columns):
    raise KeyError(
        "The state GeoJSON must contain 'shapeName' and 'shapeISO'."
    )

if district_gdf.crs is None or state_gdf.crs is None:
    raise ValueError(
        "CRS is missing from one of the GeoJSON files. "
        "Set the correct CRS before running the script."
    )


# =====================================================
# 4. MAP DISTRICTS TO STATES - ONE SPATIAL JOIN ONLY
# =====================================================

district_gdf = district_gdf.to_crs(state_gdf.crs)

# Important:
# Drop old state columns so GeoPandas does not rename the new
# columns to state_name_left/state_name_right during the join.
district_points = district_gdf.drop(
    columns=["state_name", "state_code"],
    errors="ignore"
).copy()

district_points["geometry"] = (
    district_points.geometry.representative_point()
)

states = state_gdf[
    ["shapeName", "shapeISO", "geometry"]
].rename(
    columns={
        "shapeName": "state_name",
        "shapeISO": "state_code"
    }
)

joined = gpd.sjoin(
    district_points,
    states,
    how="left",
    predicate="within"
)

# Keep one joined row for each original district feature.
joined = joined[
    ~joined.index.duplicated(keep="first")
]

# Reindex to ensure values align with the original district rows.
district_gdf["state_name"] = (
    joined["state_name"].reindex(district_gdf.index)
)
district_gdf["state_code"] = (
    joined["state_code"].reindex(district_gdf.index)
)

# Lakshadweep can fail the spatial join because it is an island group.
lakshadweep_mask = (
    district_gdf["shapeName"]
    .fillna("")
    .str.strip()
    .str.lower()
    .eq("lakshadweep")
)

district_gdf.loc[ lakshadweep_mask, "state_name"] = "Lakshadweep"
district_gdf.loc[ lakshadweep_mask, "state_code"] = "IN-LD"

print("\n========== SPATIAL JOIN SUMMARY ==========")
print("Joined columns:", joined.columns.tolist())
print("Unmatched districts:", district_gdf["state_name"].isna().sum())

unmatched = district_gdf.loc[
    district_gdf["state_name"].isna(),
    "shapeName"
]
if not unmatched.empty:
    print("Districts not mapped to a state:")
    print(unmatched.to_string(index=False))


# =====================================================
# 5. NORMALIZE DATABASE AND GEOJSON NAMES
# =====================================================

db_df["state_norm"] = db_df["state_name"].apply(normalize_name)
db_df["district_norm"] = db_df["district"].apply(normalize_name)

district_gdf["state_norm"] = (
    district_gdf["state_name"].apply(normalize_name)
)
district_gdf["district_norm"] = (
    district_gdf["shapeName"].apply(normalize_name)
)


# =====================================================
# 6. CREATE STATE-DISTRICT PAIR SETS
# =====================================================

db_pairs = set(
    zip(db_df["state_norm"], db_df["district_norm"])
)

geo_pairs = set(
    zip(
        district_gdf["state_norm"],
        district_gdf["district_norm"]
    )
)

exact_matches = db_pairs & geo_pairs
missing_geojson = db_pairs - geo_pairs
extra_geojson = geo_pairs - db_pairs

print("\n========== COMPARISON SUMMARY ==========")
print("Database pairs:", len(db_pairs))
print("GeoJSON pairs:", len(geo_pairs))
print("Exact matches:", len(exact_matches))
print("Missing in GeoJSON:", len(missing_geojson))
print("Extra in GeoJSON:", len(extra_geojson))


# =====================================================
# 7. CREATE LOOKUP DICTIONARIES
# =====================================================

db_lookup = {
    (row["state_norm"], row["district_norm"]):
    (row["state_name"], row["district"])
    for _, row in db_df.iterrows()
}

geo_lookup = {
    (row["state_norm"], row["district_norm"]):
    (row["state_name"], row["shapeName"])
    for _, row in district_gdf.iterrows()
}


# =====================================================
# 8. PRINT MISSING DISTRICTS
# =====================================================

print("\n========== MISSING IN GEOJSON ==========")

for pair in sorted(missing_geojson):
    state, district = db_lookup[pair]
    print(f"{state} -> {district}")


# =====================================================
# 9. PRINT EXTRA GEOJSON DISTRICTS
# =====================================================

print("\n========== EXTRA GEOJSON DISTRICTS ==========")

for pair in sorted(extra_geojson):
    state, district = geo_lookup[pair]
    print(f"{state} -> {district}")


# =====================================================
# 10. FUZZY SPELLING MATCHING
# =====================================================

print("\n========== POSSIBLE SPELLING MISMATCHES ==========")

suggestions_report = []

for state_norm, district_norm in sorted(missing_geojson):

    db_state, db_district = db_lookup[
        (state_norm, district_norm)
    ]

    # Only compare districts in the same state.
    candidates = [
        geo_district
        for geo_state, geo_district in extra_geojson
        if geo_state == state_norm
    ]

    suggestions = get_close_matches(
        district_norm,
        candidates,
        n=3,
        cutoff=FUZZY_CUTOFF
    )

    print(f"\nDatabase: {db_state} -> {db_district}")

    if suggestions:
        for suggestion in suggestions:
            geo_state, geo_district = geo_lookup[
                (state_norm, suggestion)
            ]

            print(
                f"GeoJSON suggestion: "
                f"{geo_state} -> {geo_district}"
            )

            suggestions_report.append({
                "database_state": db_state,
                "database_district": db_district,
                "geojson_state": geo_state,
                "geojson_district": geo_district
            })
    else:
        print("No similar district found")


# =====================================================
# 11. SAVE COMPARISON REPORTS
# =====================================================

missing_report = pd.DataFrame(
    [
        {
            "state": db_lookup[pair][0],
            "database_district": db_lookup[pair][1]
        }
        for pair in sorted(missing_geojson)
    ],
    columns=["state", "database_district"]
)

extra_report = pd.DataFrame(
    [
        {
            "state": geo_lookup[pair][0],
            "geojson_district": geo_lookup[pair][1]
        }
        for pair in sorted(extra_geojson)
    ],
    columns=["state", "geojson_district"]
)

suggestions_df = pd.DataFrame(
    suggestions_report,
    columns=[
        "database_state",
        "database_district",
        "geojson_state",
        "geojson_district"
    ]
)

missing_report.to_csv(MISSING_REPORT, index=False)
extra_report.to_csv(EXTRA_REPORT, index=False)
suggestions_df.to_csv(SUGGESTIONS_REPORT, index=False)

print("\n========== REPORT SUMMARY ==========")
print("Exact matches:", len(exact_matches))
print("Missing in GeoJSON:", len(missing_geojson))
print("Extra in GeoJSON:", len(extra_geojson))
print("Spelling suggestions:", len(suggestions_df))

print("\nReports generated:")
print("1.", MISSING_REPORT)
print("2.", EXTRA_REPORT)
print("3.", SUGGESTIONS_REPORT)


# =====================================================
# 12. APPLY BEST SPELLING SUGGESTIONS
# =====================================================

corrections = []

if suggestions_df.empty:
    print("\nNo spelling suggestions available. GeoJSON not changed.")

else:
    suggestions_df["similarity"] = suggestions_df.apply(
        lambda row: SequenceMatcher(
            None,
            normalize_name(row["database_district"]),
            normalize_name(row["geojson_district"])
        ).ratio(),
        axis=1
    )

    # Highest similarity first.
    suggestions_df = suggestions_df.sort_values(
        "similarity",
        ascending=False
    )

    # One best candidate per database district.
    best_matches = suggestions_df.drop_duplicates(
        subset=["database_state", "database_district"],
        keep="first"
    ).copy()

    # Do not assign one GeoJSON district to multiple DB districts.
    best_matches = best_matches.drop_duplicates(
        subset=["geojson_state", "geojson_district"],
        keep="first"
    ).copy()

    corrected_gdf = district_gdf.copy()

    for _, row in best_matches.iterrows():

        state_norm = normalize_name(row["geojson_state"])
        district_norm = normalize_name(row["geojson_district"])

        mask = (
            corrected_gdf["state_name"].apply(normalize_name)
            == state_norm
        ) & (
            corrected_gdf["shapeName"].apply(normalize_name)
            == district_norm
        )

        if mask.sum() == 1:
            old_name = corrected_gdf.loc[
                mask, "shapeName"
            ].iloc[0]

            new_name = row["database_district"]

            corrected_gdf.loc[mask, "shapeName"] = new_name

            corrections.append({
                "state": row["database_state"],
                "old_name": old_name,
                "new_name": new_name,
                "similarity": round(row["similarity"], 3)
            })

        else:
            print(
                "Could not uniquely identify:",
                row["geojson_state"],
                row["geojson_district"],
                "| matching features:",
                int(mask.sum())
            )

    correction_report = pd.DataFrame(
        corrections,
        columns=["state", "old_name", "new_name", "similarity"]
    )

    correction_report.to_csv(CORRECTIONS_REPORT, index=False)

    if corrections:
        # Create a backup once before updating the original file.
        if not shutil.os.path.exists(BACKUP_GEOJSON):
            shutil.copy2(DISTRICT_GEOJSON, BACKUP_GEOJSON)
            print("\nBackup created:", BACKUP_GEOJSON)

        # Update the original district GeoJSON.
        corrected_gdf.to_file(
            DISTRICT_GEOJSON,
            driver="GeoJSON"
        )

        print("\n========== CORRECTION SUMMARY ==========")
        print("Suggestions found:", len(suggestions_df))
        print("Best matches selected:", len(best_matches))
        print("Corrections applied:", len(corrections))
        print("\nApplied corrections:")
        print(correction_report.to_string(index=False))

        print("\nUpdated GeoJSON:", DISTRICT_GEOJSON)
        print("Backup GeoJSON:", BACKUP_GEOJSON)

    else:
        print("\nNo corrections were applied. GeoJSON was not changed.")

print("\nCorrection report:", CORRECTIONS_REPORT)
print("\nProcess completed.")
