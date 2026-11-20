
import os
from pathlib import Path
from dotenv import load_dotenv

import dash
from dash import dcc, html
from dash.dependencies import Input, Output

import pandas as pd
import plotly.express as px
import geopandas as gpd

from sqlalchemy import create_engine, text, URL


# ==================================================
# 1. DATABASE CONNECTION
# ==================================================

load_dotenv(Path(__file__).resolve().parent / "QueryMate" / ".env")

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD environment variable is missing.")

DATABASE_URL = URL.create(
    "postgresql+psycopg2",
    username=os.getenv("DB_USER", "postgres"),
    password=DB_PASSWORD,
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "8137")),
    database=os.getenv("DB_NAME", "Users"),
)

engine = create_engine(DATABASE_URL)


# ==================================================
# 2. FETCH STATE-WISE DEMOGRAPHIC DATA
# ==================================================

query_state = text("""
    SELECT
        B.state,
        COUNT(A.id) AS population,
        AVG(A.age) AS mean_age
    FROM user_detail AS A
    JOIN addresses AS B
        ON A.address_id = B.id
    GROUP BY B.state
""")


with engine.connect() as conn:
    df = pd.read_sql(query_state, conn)


if df.empty:
    raise ValueError("No demographic data found in the database.")


# ==================================================
# 3. NORMALIZE STATE AND DISTRICT NAMES
# ==================================================

def normalize_names(series):

    return (
        series.astype("string")
        .str.strip()
        .str.upper()
        .str.replace(r"\s+", " ", regex=True)
    )


df["state_key"] = normalize_names(df["state"])


# ==================================================
# 4. PROJECT ROOT
# ==================================================

root = Path(
    r"C:\Users\lenovo\credential\maps-master"
)


# ==================================================
# 5. LOAD DISTRICT SHAPEFILE
# ==================================================

district_files = list(root.rglob("2011_Dist.shp"))

if not district_files:
    raise FileNotFoundError(
        "2011_Dist.shp not found inside maps-master."
    )

district_path = district_files[0]

print("District shapefile:", district_path)

geo_df = gpd.read_file(district_path)


# Validate district columns

required_columns = ["ST_NM", "DISTRICT"]

for col in required_columns:

    if col not in geo_df.columns:

        raise ValueError(
            f"Missing district shapefile column: {col}"
        )


# Convert CRS

geo_df = geo_df.to_crs(epsg=4326)


# Normalize district and state names

geo_df["state_key"] = normalize_names(
    geo_df["ST_NM"]
)

geo_df["district_key"] = normalize_names(
    geo_df["DISTRICT"]
)


# ==================================================
# 6. LOAD INDIA STATE SHAPEFILE
# ==================================================

state_files = list(root.rglob("Admin2.shp"))

if not state_files:
    raise FileNotFoundError(
        "Admin2.shp not found inside maps-master."
    )

state_path = state_files[0]

print("State shapefile:", state_path)

state_geo = gpd.read_file(state_path)


# Detect state-name column automatically

possible_columns = [
    "Name",
    "NAME",
    "ST_NM",
    "STATE",
    "state_name",
    "NAME_1",
    "State"
]

state_column = next(
    (
        col for col in possible_columns
        if col in state_geo.columns
    ),
    None
)

if state_column is None:

    raise ValueError(
        "State name column not found. Available columns: "
        + str(state_geo.columns.tolist())
    )


print("State name column:", state_column)


# Convert CRS

state_geo = state_geo.to_crs(epsg=4326)


# Normalize state names

state_geo["state_key"] = normalize_names(
    state_geo[state_column]
)


# Create unique ID for every state polygon

state_geo = state_geo.reset_index(drop=True)

state_geo["feature_id"] = (
    state_geo.index.astype(str)
)


# ==================================================
# 7. MERGE DISTRICT GEOMETRY WITH DEMOGRAPHICS
# ==================================================

map_df = geo_df.merge(

    df[
        [
            "state",
            "state_key",
            "population",
            "mean_age"
        ]
    ],

    on="state_key",

    how="left",

    validate="many_to_one"
)


# Create unique district polygon IDs

map_df = map_df.reset_index(drop=True)

map_df["feature_id"] = (
    map_df.index.astype(str)
)


# ==================================================
# 8. MERGE STATE GEOMETRY WITH DEMOGRAPHICS
# ==================================================

state_map = state_geo.merge(

    df[
        [
            "state_key",
            "population",
            "mean_age"
        ]
    ],

    on="state_key",

    how="left",

    validate="many_to_one"
)


# ==================================================
# 9. CHECK STATE MATCHING
# ==================================================

unmatched_states = sorted(

    set(state_geo["state_key"].dropna())
    -
    set(df["state_key"].dropna())

)

unmatched_district_states = sorted(

    set(geo_df["state_key"].dropna())
    -
    set(df["state_key"].dropna())

)

print("\n========== DATA CHECK ==========")

print("Database states:", df["state_key"].nunique())

print("State shapefile states:", state_geo["state_key"].nunique())

print("District shapefile states:", geo_df["state_key"].nunique())

print("Unmatched state-map names:", unmatched_states)

print("Unmatched district-map names:", unmatched_district_states)

print("Total district polygons:", len(geo_df))

print("================================\n")


# ==================================================
# 10. INITIALIZE DASH
# ==================================================

app = dash.Dash(__name__)


# State dropdown options

state_options = [

    {
        "label": state,
        "value": state_key
    }

    for state, state_key in (

        df[
            ["state", "state_key"]
        ]

        .drop_duplicates()

        .sort_values("state")

        .itertuples(index=False, name=None)

    )

]


# ==================================================
# 11. DASHBOARD LAYOUT
# ==================================================

app.layout = html.Div(

    style={

        "fontFamily": "Arial",

        "padding": "20px",

        "backgroundColor": "#f8fafc"

    },

    children=[

        # Dashboard heading

        html.H1(

            "India Demographics Dashboard",

            style={

                "textAlign": "center",

                "color": "#1e293b"

            }

        ),


        html.P(

            "Explore state-wise demographics using interactive maps.",

            style={

                "textAlign": "center",

                "color": "#64748b"

            }

        ),


        # Dropdown section

        html.Div(

            style={

                "width": "45%",

                "margin": "auto"

            },

            children=[


                # Metric dropdown

                html.Label("Select Demographic Metric"),

                dcc.Dropdown(

                    id="metric-dropdown",

                    options=[

                        {
                            "label": "Total Population",
                            "value": "population"
                        },

                        {
                            "label": "Average Age",
                            "value": "mean_age"
                        }

                    ],

                    value="population",

                    clearable=False

                ),


                html.Br(),


                # State dropdown

                html.Label("Select State"),

                dcc.Dropdown(

                    id="States",

                    options=state_options,

                    value=None,

                    placeholder="All States",

                    clearable=True

                ),


                # District dropdown container

                html.Div(

                    id="district-dropdown-container",

                    style={

                        "display": "none"

                    },

                    children=[

                        html.Br(),

                        html.Label("Select District"),

                        dcc.Dropdown(

                            id="district-dropdown",

                            options=[],

                            value=None,

                            placeholder="Select a District",

                            clearable=True

                        )

                    ]

                )

            ]

        ),


        html.Br(),


        # Interactive map

        dcc.Graph(

            id="india-state-map",

            style={

                "height": "750px"

            }

        )

    ]

)


# ==================================================
# 12. CALLBACK: UPDATE DISTRICT DROPDOWN
# ==================================================

@app.callback(

    Output("district-dropdown", "options"),

    Output("district-dropdown", "value"),

    Output("district-dropdown-container", "style"),

    Input("States", "value")

)

def update_district_dropdown(selected_state):


    # No state selected

    if not selected_state:

        return (

            [],

            None,

            {"display": "none"}

        )


    # Filter districts for selected state

    filtered_districts = geo_df[

        geo_df["state_key"] == selected_state

    ][

        ["DISTRICT", "district_key"]

    ].drop_duplicates()


    # Dropdown options

    options = [

        {

            "label": row["DISTRICT"],

            "value": row["district_key"]

        }

        for _, row in (

            filtered_districts

            .sort_values("DISTRICT")

            .iterrows()

        )

    ]


    return (

        options,

        None,

        {"display": "block"}

    )


# ==================================================
# 13. CALLBACK: UPDATE MAP
# ==================================================


from dash import Input, Output
import pandas as pd
import plotly.express as px
from sqlalchemy import text


@app.callback(
    Output("india-state-map", "figure"),

    Input("metric-dropdown", "value"),
    Input("States", "value"),
    Input("district-dropdown", "value")
)
def update_map(selected_metric, selected_state, selected_district):

    # ------------------------------------------
    # 1. VALIDATE SELECTED METRIC
    # ------------------------------------------

    allowed_metrics = ["population", "mean_age"]

    if selected_metric not in allowed_metrics:
        return px.scatter(title="Please select a valid metric")

    # ------------------------------------------
    # 2. FETCH STATE-WISE DATA FROM DATABASE
    # ------------------------------------------

    state_query = text("""
        SELECT
            LOWER(TRIM(B.state)) AS state_key,
            MAX(TRIM(B.state)) AS state,
            COUNT(A.id) AS population,
            AVG(A.age) AS mean_age

        FROM user_detail AS A

        INNER JOIN addresses AS B
            ON A.address_id = B.id

        WHERE B.state IS NOT NULL

        GROUP BY LOWER(TRIM(B.state))
    """)

    state_data = pd.read_sql_query(
        state_query,
        engine
    )

    # ------------------------------------------
    # 3. CASE 1: NO STATE SELECTED
    # SHOW COMPLETE INDIA MAP
    # ------------------------------------------

    if not selected_state:

        filtered_state_map = state_map.copy()

        # Normalize state names
        filtered_state_map["state_key"] = (
            filtered_state_map["state_key"]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        # Merge database statistics with state boundaries
        filtered_state_map = filtered_state_map.drop(
            columns=["population", "mean_age"],
            errors="ignore"
        )

        filtered_state_map = filtered_state_map.merge(
            state_data[
                ["state_key", "population", "mean_age"]
            ],
            on="state_key",
            how="left"
        )

        filtered_state_map = filtered_state_map.dropna(
            subset=[selected_metric]
        )

        if filtered_state_map.empty:
            return px.scatter(
                title="No state demographic data available"
            )

        fig = px.choropleth(
            filtered_state_map,

            geojson=filtered_state_map.__geo_interface__,

            locations="feature_id",
            featureidkey="properties.feature_id",

            color=selected_metric,

            color_continuous_scale="Plasma",

            hover_name=state_column,

            hover_data={
                "population": True,
                "mean_age": ":.2f",
                "feature_id": False
            },

            labels={
                "population": "Population",
                "mean_age": "Average Age"
            },

            title=f"India State-wise {selected_metric.replace('_', ' ').title()}"
        )

        fig.update_geos(
            fitbounds="locations",
            visible=False
        )

        fig.update_layout(
            title_x=0.5,
            height=750,
            margin=dict(
                r=0,
                t=60,
                l=0,
                b=0
            ),
            paper_bgcolor="#f8fafc"
        )

        return fig

    # ------------------------------------------
    # 4. FETCH DISTRICT-WISE DATA
    # FOR THE SELECTED STATE
    # ------------------------------------------

    district_query = text("""
        SELECT
            LOWER(TRIM(B.state)) AS state_key,
            LOWER(TRIM(B.city)) AS district_key,

            MAX(TRIM(B.state)) AS state,
            MAX(TRIM(B.city)) AS district,

            COUNT(A.id) AS population,
            AVG(A.age) AS mean_age

        FROM user_detail AS A

        INNER JOIN addresses AS B
            ON A.address_id = B.id

        WHERE
            LOWER(TRIM(B.state)) = :selected_state

            AND B.city IS NOT NULL

        GROUP BY
            LOWER(TRIM(B.state)),
            LOWER(TRIM(B.city))
    """)

    district_data = pd.read_sql_query(
        district_query,
        engine,
        params={
            "selected_state": selected_state.strip().lower()
        }
    )

    # ------------------------------------------
    # 5. CASE 2: STATE SELECTED
    # SHOW ALL DISTRICTS OF THAT STATE
    # ------------------------------------------

    filtered_df = map_df.copy()

    # Normalize geographic boundary names
    filtered_df["state_key"] = (
        filtered_df["state_key"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    filtered_df["district_key"] = (
        filtered_df["district_key"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    # Filter selected state
    filtered_df = filtered_df[
        filtered_df["state_key"] == selected_state.strip().lower()
    ].copy()

    # Remove old demographic columns
    filtered_df = filtered_df.drop(
        columns=["population", "mean_age"],
        errors="ignore"
    )

    # Join district statistics with geographic boundaries
    filtered_df = filtered_df.merge(
        district_data[
            [
                "state_key",
                "district_key",
                "population",
                "mean_age"
            ]
        ],
        on=["state_key", "district_key"],
        how="left"
    )

    # ------------------------------------------
    # 6. CASE 3: DISTRICT SELECTED
    # SHOW ONLY SELECTED DISTRICT
    # ------------------------------------------

    if selected_district:

        selected_district = selected_district.strip().lower()

        filtered_df = filtered_df[
            filtered_df["district_key"] == selected_district
        ].copy()

    # ------------------------------------------
    # 7. REMOVE MISSING VALUES
    # ------------------------------------------

    filtered_df = filtered_df.dropna(
        subset=[selected_metric]
    )

    if filtered_df.empty:

        return px.scatter(
            title="No matching geographic data available"
        )

    # ------------------------------------------
    # 8. DYNAMIC MAP TITLE
    # ------------------------------------------

    if selected_district:

        district_name = filtered_df["DISTRICT"].iloc[0]

        title_text = (
            f"{selected_metric.replace('_', ' ').title()} "
            f"in {district_name}"
        )

    else:

        title_text = (
            f"District-wise {selected_metric.replace('_', ' ').title()} "
            f"in {selected_state.title()}"
        )

    # ------------------------------------------
    # 9. CREATE DISTRICT CHOROPLETH
    # ------------------------------------------

    fig = px.choropleth(
        filtered_df,

        geojson=filtered_df.__geo_interface__,

        locations="feature_id",
        featureidkey="properties.feature_id",

        color=selected_metric,

        color_continuous_scale="Plasma",

        hover_name="DISTRICT",

        hover_data={
            "ST_NM": True,
            "population": True,
            "mean_age": ":.2f",
            "feature_id": False
        },

        labels={
            "ST_NM": "State",
            "DISTRICT": "District",
            "population": "Population",
            "mean_age": "Average Age"
        },

        title=title_text
    )

    # ------------------------------------------
    # 10. MAP DESIGN AND ZOOM
    # ------------------------------------------

    fig.update_geos(
        fitbounds="locations",
        visible=False
    )

    fig.update_layout(
        title_x=0.5,
        height=750,

        margin=dict(
            r=0,
            t=60,
            l=0,
            b=0
        ),

        paper_bgcolor="#f8fafc"
    )

    return fig



# ==================================================
# 14. RUN APPLICATION
# ==================================================

if __name__ == "__main__":

    app.run(debug=True)
