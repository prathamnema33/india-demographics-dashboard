import json
import os
from pathlib import Path
import re
import unicodedata
import dash
from dash import dcc, html, Input, Output, State
import geopandas as gpd
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import URL, create_engine, text
from dotenv import load_dotenv
from querymate_client import QueryMateAPIError, create_session
from querymate_chat import handle_chat_message


# ============================================================
# 1. CONFIGURATION
# ============================================================
BASE_DIR = Path(__file__).resolve().parent

STATE_GEOJSON = Path(
    os.getenv("STATE_GEOJSON_PATH", BASE_DIR / "state_level.geojson")
)
DISTRICT_GEOJSON = Path(
    os.getenv("DISTRICT_GEOJSON_PATH", BASE_DIR / "district_level.geojson")
)

# Reuse the backend's local DB settings when running the dashboard, while
# preserving environment-variable overrides for deployment.
load_dotenv(BASE_DIR / "QueryMate" / ".env")

for path in (STATE_GEOJSON, DISTRICT_GEOJSON):
    if not path.is_file():
        raise FileNotFoundError(f"GeoJSON file not found: {path}")

DB_PASSWORD = os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise RuntimeError(
        "DB_PASSWORD environment variable is missing. Set it before starting the app."
    )

engine = create_engine(
    URL.create(
        "postgresql+psycopg2",
        username=os.getenv("DB_USER", "postgres"),
        password=DB_PASSWORD,
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "8137")),
        database=os.getenv("DB_NAME", "Users"),
    ),
    pool_pre_ping=True,
)


# ============================================================
# 2. NORMALIZE NAMES
# ============================================================
def normalize_name(value):
    if pd.isna(value):
        return ""

    value = unicodedata.normalize("NFKD", str(value).strip().lower())
    value = "".join(
        ch for ch in value if not unicodedata.combining(ch)
    )
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)

    return re.sub(r"\s+", " ", value).strip()


STATE_ALIASES = {
    "orissa": "odisha",
    "uttaranchal": "uttarakhand",
    "pondicherry": "puducherry",
    "nct of delhi": "delhi",
}


def state_key(value):
    key = normalize_name(value)
    return STATE_ALIASES.get(key, key)


DISTRICT_ALIASES = {
    ("madhya pradesh", "narsimhapur"): "narsinghpur",
}


# ============================================================
# 3. LOAD & SIMPLIFY GEOMETRIES
# ============================================================
state_geo = (
    gpd.read_file(STATE_GEOJSON)
    .to_crs(epsg=4326)
    .reset_index(drop=True)
)

if "shapeName" not in state_geo.columns:
    raise ValueError("State GeoJSON must contain a 'shapeName' field.")

state_geo["geometry"] = state_geo["geometry"].simplify(
    tolerance=0.001,
    preserve_topology=True,
)
state_geo["state_name"] = state_geo["shapeName"].astype(str)
state_geo["state_key"] = state_geo["state_name"].map(state_key)

if "shapeISO" in state_geo.columns:
    state_geo["feature_id"] = state_geo["shapeISO"].fillna("").astype(str).str.strip()
else:
    state_geo["feature_id"] = ""

if (
    state_geo["feature_id"].eq("").any()
    or state_geo["feature_id"].duplicated().any()
):
    state_geo["feature_id"] = [
        f"state_{i}" for i in range(len(state_geo))
    ]


district_geo = (
    gpd.read_file(DISTRICT_GEOJSON)
    .to_crs(epsg=4326)
    .reset_index(drop=True)
)

if "shapeName" not in district_geo.columns:
    raise ValueError("District GeoJSON must contain a 'shapeName' field.")

district_geo["geometry"] = district_geo["geometry"].simplify(
    tolerance=0.0008,
    preserve_topology=True,
)
district_geo["DISTRICT"] = district_geo["shapeName"].astype(str)
district_geo["district_key"] = district_geo["DISTRICT"].map(normalize_name)
district_geo["feature_id"] = [
    f"district_{i}" for i in range(len(district_geo))
]


# Spatial join: assign each district to its parent state.
district_projected = district_geo.to_crs(epsg=6933)
state_projected = state_geo.to_crs(epsg=6933)

state_rep_pts = (
    state_projected.geometry.representative_point().to_crs(epsg=4326)
)
state_geo["label_lon"] = state_rep_pts.x
state_geo["label_lat"] = state_rep_pts.y

dist_rep_pts_proj = district_projected.geometry.representative_point()
dist_rep_pts = dist_rep_pts_proj.to_crs(epsg=4326)

district_geo["label_lon"] = dist_rep_pts.x
district_geo["label_lat"] = dist_rep_pts.y

points = gpd.GeoDataFrame(
    {"feature_id": district_geo["feature_id"].values},
    geometry=dist_rep_pts_proj,
    crs=district_projected.crs,
)

joined = gpd.sjoin(
    points,
    state_projected[["state_key", "state_name", "geometry"]],
    how="left",
    predicate="within",
)

joined = (
    joined[~joined.index.duplicated(keep="first")]
    .reindex(district_geo.index)
)

district_geo["state_key"] = joined["state_key"].to_numpy()
district_geo["state_name"] = joined["state_name"].to_numpy()

# Lakshadweep may not be assigned by the spatial join because of its
# island geometry/location, so handle it explicitly.
lakshadweep_mask = district_geo["district_key"].eq("lakshadweep")
district_geo.loc[lakshadweep_mask, "state_key"] = "lakshadweep"
district_geo.loc[lakshadweep_mask, "state_name"] = "Lakshadweep"


# ============================================================
# 4. READ DATABASE DATA
# ============================================================
STATE_SQL = text(
    """
    SELECT
        B.state AS state,
        COUNT(A.id) AS population,
        SUM(A.age) AS total_age
    FROM user_detail AS A
    INNER JOIN addresses AS B ON A.address_id = B.id
    WHERE B.state IS NOT NULL and A.dod is NULL
    GROUP BY B.state
    """
)

DISTRICT_SQL = text(
    """
    SELECT
        B.state AS state,
        B.city AS district,
        COUNT(A.id) AS population,
        SUM(A.age) AS total_age
    FROM user_detail AS A
    INNER JOIN addresses AS B ON A.address_id = B.id
    WHERE B.state IS NOT NULL
      AND B.city IS NOT NULL 
      and A.dod is NULL
    GROUP BY B.state, B.city
    """
)

religion_query = """
SELECT
    A.state,
    A.city,

    COUNT(*) FILTER (
        WHERE B.religion = 'Christianity'
    ) AS Christianity,

    COUNT(*) FILTER (
        WHERE B.religion = 'Islam'
    ) AS Islam,

    COUNT(*) FILTER (
        WHERE B.religion = 'Sikhism'
    ) AS Sikhism,

    COUNT(*) FILTER (
        WHERE B.religion = 'Buddhism'
    ) AS Buddhism,

    COUNT(*) FILTER (
        WHERE B.religion = 'Hinduism'
    ) AS Hinduism,

    COUNT(*) FILTER (
        WHERE B.religion = 'Jainism'
    ) AS Jainism,

    COUNT(*) FILTER (
        WHERE B.religion = 'Others'
    ) AS Others

FROM user_detail AS B

JOIN addresses AS A
    ON B.address_id = A.id

GROUP BY A.state, A.city;
"""

with engine.connect() as conn:
    state_data = pd.read_sql_query(STATE_SQL, conn)
    district_data = pd.read_sql_query(DISTRICT_SQL, conn)
    religion_data = pd.read_sql_query(religion_query, conn)


if not religion_data.empty:

    religion_data["state_key"] = (
        religion_data["state"].map(state_key)
    )

    religion_data["district_key"] = (
        religion_data["city"].map(normalize_name)
    )
    print("Religion DataFrame Columns:")
    print(religion_data.columns.tolist())

    print(religion_data.head())
    religion_data = religion_data.melt(
    id_vars=["state", "city", "state_key", "district_key"],
    value_vars=[
        "christianity",
        "islam",
        "sikhism",
        "buddhism",
        "hinduism",
        "jainism",
        "others"
    ],
    var_name="Religion",
    value_name="population"
)

# Capitalize religion names for display
    religion_data["Religion"] = religion_data["Religion"].str.capitalize()

# Ensure population is numeric
    religion_data["population"] = pd.to_numeric(
    religion_data["population"], errors="coerce"
).fillna(0)

else:
    religion_data = pd.DataFrame(
        columns=[
            "state", "city", "state_key",
            "district_key", "religion", "population"
        ]
    )

if not state_data.empty:
    state_data["state_key"] = state_data["state"].map(state_key)

    state_data = state_data.groupby(
        "state_key",
        as_index=False,
    ).agg(
        population=("population", "sum"),
        total_age=("total_age", "sum"),
    )

    state_data["mean_age"] = (
        state_data["total_age"] / state_data["population"]
    ).round(1)
else:
    state_data = pd.DataFrame(
        columns=["state_key", "population", "total_age", "mean_age"]
    )


if not district_data.empty:
    district_data["state_key"] = district_data["state"].map(state_key)
    district_data["district_key"] = district_data["district"].map(
        normalize_name
    )

    district_data["district_key"] = district_data.apply(
        lambda row: DISTRICT_ALIASES.get(
            (row["state_key"], row["district_key"]),
            row["district_key"],
        ),
        axis=1,
    )

    district_data = district_data.groupby(
        ["state_key", "district_key"],
        as_index=False,
    ).agg(
        population=("population", "sum"),
        total_age=("total_age", "sum"),
    )

    district_data["mean_age"] = (
        district_data["total_age"] / district_data["population"]
    ).round(1)
else:
    district_data = pd.DataFrame(
        columns=[
            "state_key",
            "district_key",
            "population",
            "total_age",
            "mean_age",
        ]
    )

    

# Join database values to geographic polygons.
state_map = state_geo.merge(state_data, on="state_key", how="left")
district_map = district_geo.merge(
    district_data,
    on=["state_key", "district_key"],
    how="left",
)

state_map["region_label"] = state_map["state_name"]
district_map["region_label"] = (
    district_map["DISTRICT"]
    + " ("
    + district_map["state_name"].fillna("")
    + ")"
)

for dataframe in (state_map, district_map):
    dataframe["pop_display"] = (
        dataframe["population"].fillna(0).astype(int)
    )
    dataframe["age_display"] = dataframe["mean_age"].map(
        lambda value: (
            f"{value:.1f} yrs" if pd.notna(value) else "No data"
        )
    )

state_geojson_dict = json.loads(
    state_map[["feature_id", "geometry"]].to_json()
)
all_districts_geojson_dict = json.loads(
    district_map[["feature_id", "geometry"]].to_json()
)


def get_bounds_center_zoom(geodataframe):
    if geodataframe.empty:
        return {"lat": 22.8, "lon": 82.8}, 4.1

    minx, miny, maxx, maxy = geodataframe.total_bounds
    center_lon = (minx + maxx) / 2
    center_lat = (miny + maxy) / 2
    max_span = max(maxx - minx, maxy - miny)

    zoom = (
        6.0
        if max_span <= 0
        else float(np.clip(np.log2(360.0 / max_span) - 1.0, 4.0, 8.5))
    )

    return {"lat": center_lat, "lon": center_lon}, zoom


# ============================================================
# 5. DASH APP LAYOUT
# ============================================================
app = dash.Dash(__name__)
app.title = "India Demographics Map"

state_options = [{"label": "All India", "value": "ALL"}] + [
    {"label": row.state_name, "value": row.state_key}
    for row in (
        state_geo[["state_name", "state_key"]]
        .drop_duplicates()
        .sort_values("state_name")
        .itertuples()
    )
]

app.layout = html.Div(
    style={
        "fontFamily": "sans-serif",
        "padding": "10px 18px",
        "width": "100%",
        "boxSizing": "border-box",
        "backgroundColor": "#f8fafc",
    },
    children=[
        # Controls Bar
        html.Div(
            style={
                "display": "flex",
                "gap": "20px",
                "marginBottom": "10px",
                "alignItems": "center",
                "flexWrap": "wrap",
                "backgroundColor": "#ffffff",
                "padding": "10px 16px",
                "borderRadius": "8px",
                "boxShadow": "0 1px 3px rgba(0,0,0,0.08)",
            },
            children=[
                html.H3(
                    "India Demographics Map",
                    style={"margin": "0 12px 0 0", "color": "#0f172a"},
                ),
                html.Div(
                    style={"width": "250px"},
                    children=[
                        dcc.Dropdown(
                            id="state-dropdown",
                            options=state_options,
                            value="ALL",
                            clearable=False,
                        )
                    ],
                ),
                dcc.RadioItems(
                    id="granularity-selector",
                    options=[
                        {"label": " States (36)", "value": "STATE"},
                        {
                            "label": " All Districts (~750)",
                            "value": "DISTRICT",
                        },
                    ],
                    value="STATE",
                    inline=True,
                ),
                dcc.RadioItems(
                    id="metric-selector",
                    options=[
                        {"label": " Population", "value": "pop_display"},
                        {"label": " Mean Age", "value": "mean_age"},
                    ],
                    value="pop_display",
                    inline=True,
                ),
                html.Button(
                    "Reset to All India",
                    id="reset-btn",
                    n_clicks=0,
                    style={
                        "padding": "6px 14px",
                        "cursor": "pointer",
                        "backgroundColor": "#0f172a",
                        "color": "#ffffff",
                        "border": "none",
                        "borderRadius": "5px",
                        "fontWeight": "500",
                    },
                ),
            ],
        ),

        # Existing map and ranking chart
        html.Div(
    id="dashboard-content",
    style={
        "display": "grid",
        "gridTemplateColumns": "1.4fr 2.2fr 1.5fr",
        "gap": "14px",
        "alignItems": "start",
    },
    children=[

        # LEFT SIDE: Two vertically stacked divs
        html.Div(
            style={
                "display": "grid",
                "gridTemplateRows": "1fr 1fr",
                "gap": "14px",
            },
            children=[

                # TOP LEFT: Religion Distribution
                html.Div(
    id="religion-panel",
    style={
        "backgroundColor": "#ffffff",
        "padding": "15px",
        "borderRadius": "10px",
        "boxShadow": "0 2px 8px rgba(0,0,0,0.08)",
    },
    children=[
        html.H4(
            "Religion Distribution",
            style={
                "margin": "0 0 4px 0",
                "color": "#1e293b",
                "fontSize": "17px",
            },
        ),

        html.P(
            "Population share by religion",
            style={
                "color": "#64748b",
                "fontSize": "12px",
                "marginBottom": "8px",
            },
        ),

        dcc.Graph(
            id="religion-distribution",
            style={
                "height": "340px",
                "width": "100%",
            },
            config={
                "responsive": True,
                "displayModeBar": False,
            },
        ),
    ],
),

                # BOTTOM LEFT: Second chart / future component
                html.Div(
                    id="left-bottom-panel",
                    style={
                        "backgroundColor": "#ffffff",
                        "padding": "12px",
                        "borderRadius": "8px",
                        "boxShadow": "0 1px 3px rgba(0,0,0,0.08)",
                    },
                    children=[
                        html.H4(
                            "Additional Insights",
                            style={
                                "margin": "0 0 6px 0",
                                "color": "#1e293b",
                                "fontSize": "15px",
                            },
                        ),
                        html.Div(
                            "Your next visualization goes here.",
                            style={"color": "#64748b"},
                        ),
                    ],
                ),
            ],
        ),

        # CENTER: INDIA MAP
        html.Div(
            style={
                "backgroundColor": "#ffffff",
                "padding": "12px",
                "borderRadius": "8px",
                "boxShadow": "0 1px 3px rgba(0,0,0,0.08)",
            },
            children=[
                html.H4(
                    id="map-title",
                    children="India — State-Wise View",
                    style={
                        "margin": "0 0 6px 0",
                        "color": "#1e293b",
                    },
                ),
                dcc.Graph(
                    id="india-choropleth",
                    style={
                        "height": "82vh",
                        "width": "100%",
                    },
                    config={
                        "scrollZoom": True,
                        "responsive": True,
                    },
                ),
            ],
        ),

        # RIGHT SIDE: RANKING BAR
        html.Div(
            id="ranking-panel",
            style={
                "backgroundColor": "#ffffff",
                "padding": "12px",
                "borderRadius": "8px",
                "boxShadow": "0 1px 3px rgba(0,0,0,0.08)",
            },
            children=[
                html.H4(
                    id="bar-title",
                    children="Top Regions",
                    style={
                        "margin": "0 0 6px 0",
                        "color": "#1e293b",
                    },
                ),
                dcc.Graph(
                    id="ranking-bar",
                    style={
                        "height": "82vh",
                        "width": "100%",
                    },
                    config={"responsive": True},
                ),
            ],
        ),
    ],
),
        # Browser-session storage isolates each tab's conversation while keeping
        # its opaque API session ID across page navigations within that tab.
        dcc.Store(
            id="querymate-session-store",
            storage_type="session",
            data=None,
        ),
        dcc.Store(
            id="chat-history-store",
            storage_type="session",
            data=[
                {
                    "role": "assistant",
                    "text": "Hello! I am QueryMate. Ask me about Indian demographics.",
                    "status": "welcome",
                }
            ],
        ),

        # Floating chatbot launcher.
        html.Button(
            "💬",
            id="chat-toggle",
            n_clicks=0,
            title="Open QueryMate",
            style={
                "position": "fixed", "right": "24px", "bottom": "24px",
                "width": "58px", "height": "58px", "borderRadius": "50%",
                "border": "none", "backgroundColor": "#2563eb",
                "color": "#ffffff", "fontSize": "26px", "cursor": "pointer",
                "boxShadow": "0 4px 14px rgba(0,0,0,0.25)", "zIndex": "1000",
            },
        ),

        # Existing collapsible panel now displays the server-backed conversation.
        html.Div(
            id="chat-panel",
            style={
                "display": "none", "position": "fixed", "right": "24px",
                "bottom": "24px", "width": "min(390px, calc(100vw - 32px))",
                "height": "min(560px, calc(100vh - 48px))",
                "backgroundColor": "#ffffff", "borderRadius": "14px",
                "boxShadow": "0 8px 30px rgba(15,23,42,0.22)",
                "border": "1px solid #e2e8f0", "zIndex": "1001",
                "flexDirection": "column", "overflow": "hidden",
            },
            children=[
                html.Div(
                    style={
                        "display": "flex", "alignItems": "center",
                        "justifyContent": "space-between", "padding": "15px 18px",
                        "backgroundColor": "#0f172a", "color": "#ffffff",
                    },
                    children=[
                        html.Div([
                            html.Div("QueryMate", style={"fontWeight": "700", "fontSize": "16px"}),
                            html.Div("Demographics AI Assistant", style={"fontSize": "11px", "opacity": "0.8"}),
                        ]),
                        html.Button(
                            "×", id="close-chat", n_clicks=0, title="Close chat",
                            style={
                                "border": "none", "background": "transparent",
                                "color": "#ffffff", "fontSize": "27px", "cursor": "pointer",
                            },
                        ),
                    ],
                ),
                html.Div(
                    style={"flex": "1", "padding": "18px", "overflowY": "auto", "backgroundColor": "#f8fafc"},
                    children=dcc.Loading(
                        id="chat-loading",
                        type="dot",
                        children=html.Div(
                            id="chat-messages",
                            children=[],
                            style={
                                "display": "flex",
                                "flexDirection": "column",
                                "gap": "12px",
                            },
                        ),
                    ),
                ),
                html.Div(
                    style={"display": "flex", "gap": "8px", "padding": "12px", "borderTop": "1px solid #e2e8f0"},
                    children=[
                        dcc.Input(
                            id="chat-input", type="text",
                            placeholder="Ask a demographics question...",
                            n_submit=0,
                            disabled=False,
                            style={"flex": "1", "minWidth": "0", "padding": "11px", "border": "1px solid #cbd5e1", "borderRadius": "8px"},
                        ),
                        html.Button(
                            "➤", id="chat-send", n_clicks=0, disabled=False,
                            style={"width": "42px", "border": "none", "borderRadius": "8px", "backgroundColor": "#2563eb", "color": "#ffffff", "cursor": "pointer"},
                        ),
                    ],
                ),
            ],
        ),
    ],
)


# ============================================================
# 6. CALLBACKS
# ============================================================
@app.callback(
    Output("chat-panel", "style"),
    Output("ranking-panel", "style"),
    Output("dashboard-content", "style"),
    Output("chat-toggle", "style"),
    Output("querymate-session-store", "data"),
    Input("chat-toggle", "n_clicks"),
    Input("close-chat", "n_clicks"),
    State("querymate-session-store", "data"),
    prevent_initial_call=True,
)
def toggle_chat_panel(_open_clicks, _close_clicks, session_data):
    if dash.ctx.triggered_id == "chat-toggle":
        updated_session = session_data or {}
        if not updated_session.get("session_id"):
            try:
                # Create a backend session the first time this tab opens chat;
                # later opens reuse the ID stored in browser session storage.
                updated_session = {
                    "session_id": create_session(),
                    "awaiting_reply": False,
                }
            except QueryMateAPIError as error:
                updated_session = {
                    "session_id": None,
                    "awaiting_reply": False,
                    "error": str(error),
                }

        return (
            {
                "display": "flex", "position": "fixed", "right": "24px",
                "bottom": "24px", "width": "min(390px, calc(100vw - 32px))",
                "height": "min(560px, calc(100vh - 48px))",
                "backgroundColor": "#ffffff", "borderRadius": "14px",
                "boxShadow": "0 8px 30px rgba(15,23,42,0.22)",
                "border": "1px solid #e2e8f0", "zIndex": "1001",
                "flexDirection": "column", "overflow": "hidden",
            },
            {"display": "none"},
            {"display": "grid", "gridTemplateColumns": "1fr", "gap": "14px"},
            {"display": "none"},
            updated_session,
        )

    return (
        {"display": "none"},
        {
            "display": "block", "backgroundColor": "#ffffff", "padding": "12px",
            "borderRadius": "8px", "boxShadow": "0 1px 3px rgba(0,0,0,0.08)",
        },
        {"display": "grid", "gridTemplateColumns": "1.9fr 1fr", "gap": "14px"},
        {
            "position": "fixed", "right": "24px", "bottom": "24px",
            "width": "58px", "height": "58px", "borderRadius": "50%",
            "border": "none", "backgroundColor": "#2563eb", "color": "#ffffff",
            "fontSize": "26px", "cursor": "pointer",
            "boxShadow": "0 4px 14px rgba(0,0,0,0.25)", "zIndex": "1000",
            "display": "block",
        },
        session_data or dash.no_update,
    )


def build_chat_message(item):
    """Render a stored text message and optional records as safe Dash elements."""

    role = item.get("role", "assistant")
    is_user = role == "user"
    text_value = str(item.get("text", ""))
    records = item.get("records")
    options = item.get("options")

    # The backend message may already contain a plaintext table; show its
    # summary alongside structured records to avoid duplicating the table.
    if isinstance(records, list) and records and "\n\n|" in text_value:
        text_value = text_value.split("\n\n|", 1)[0]

    contents = [
        html.Div(
            text_value,
            style={
                "whiteSpace": "pre-wrap",
                "overflowWrap": "anywhere",
            },
        )
    ]

    if isinstance(options, list) and options:
        contents.append(
            html.Ul(
                [
                    html.Li(
                        f"{option.get('number', '')}. "
                        f"{option.get('location', '')}"
                    )
                    for option in options
                    if isinstance(option, dict)
                ],
                style={"margin": "8px 0 0", "paddingLeft": "20px"},
            )
        )

    if isinstance(records, list) and records:
        columns = list(records[0].keys()) if isinstance(records[0], dict) else []
        if columns:
            contents.append(
                html.Div(
                    html.Table(
                        [
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th(
                                            str(column).replace("_", " ").title(),
                                            style={
                                                "padding": "6px",
                                                "textAlign": "left",
                                                "borderBottom": "1px solid #cbd5e1",
                                            },
                                        )
                                        for column in columns
                                    ]
                                )
                            ),
                            html.Tbody(
                                [
                                    html.Tr(
                                        [
                                            html.Td(
                                                "Not available"
                                                if record.get(column) is None
                                                else str(record.get(column)),
                                                style={
                                                    "padding": "6px",
                                                    "borderBottom": "1px solid #e2e8f0",
                                                },
                                            )
                                            for column in columns
                                        ]
                                    )
                                    for record in records
                                    if isinstance(record, dict)
                                ]
                            ),
                        ],
                        style={
                            "borderCollapse": "collapse",
                            "width": "100%",
                            "fontSize": "12px",
                        },
                    ),
                    style={"overflowX": "auto", "marginTop": "8px"},
                )
            )

    return html.Div(
        contents,
        style={
            "alignSelf": "flex-end" if is_user else "flex-start",
            "maxWidth": "90%",
            "backgroundColor": "#dbeafe" if is_user else "#ffffff",
            "padding": "10px 12px",
            "borderRadius": "12px",
            "fontSize": "13px",
            "color": "#334155",
            "boxShadow": "0 1px 3px rgba(0,0,0,0.06)",
        },
    )


@app.callback(
    Output("chat-messages", "children"),
    Output("chat-input", "placeholder"),
    Input("chat-history-store", "data"),
    Input("querymate-session-store", "data"),
)
def render_chat(history, session_data):
    """Render history and expose session-creation errors without raw details."""

    items = history if isinstance(history, list) else []
    messages = [build_chat_message(item) for item in items]
    session_data = session_data or {}

    if session_data.get("error"):
        messages.append(
            build_chat_message({
                "role": "assistant",
                "text": session_data["error"],
            })
        )

    placeholder = (
        "Reply to QueryMate..."
        if session_data.get("awaiting_reply")
        else "Ask a demographics question..."
    )
    return messages, placeholder


@app.callback(
    Output("chat-history-store", "data"),
    Output("querymate-session-store", "data", allow_duplicate=True),
    Output("chat-input", "value"),
    Input("chat-send", "n_clicks"),
    Input("chat-input", "n_submit"),
    State("chat-input", "value"),
    State("chat-history-store", "data"),
    State("querymate-session-store", "data"),
    prevent_initial_call=True,
    running=[
        (Output("chat-send", "disabled"), True, False),
        (Output("chat-input", "disabled"), True, False),
    ],
)
def submit_chat_message(
    _send_clicks,
    _enter_submits,
    text_value,
    history,
    session_data,
):
    """Send one message through FastAPI and append its safe response to history."""

    question_or_reply = (text_value or "").strip()
    if not question_or_reply:
        return dash.no_update, dash.no_update, dash.no_update

    messages, session_data = handle_chat_message(
        question_or_reply,
        history,
        session_data,
    )
    return messages, session_data, ""


@app.callback(
    Output("state-dropdown", "value"),
    Input("india-choropleth", "clickData"),
    Input("reset-btn", "n_clicks"),
    prevent_initial_call=True,
)
def handle_map_click_or_reset(click_data, _n_clicks):
    triggered_id = dash.ctx.triggered_id

    if triggered_id == "reset-btn":
        return "ALL"

    if (
        triggered_id == "india-choropleth"
        and click_data
        and click_data.get("points")
    ):
        point = click_data["points"][0]
        customdata = point.get("customdata")
    
        if customdata and len(customdata) > 0:
            return customdata[0]

    return dash.no_update


@app.callback(
    Output("india-choropleth", "figure"),
    Output("religion-distribution","figure"),
    Output("map-title", "children"),
    Output("ranking-bar", "figure"),
    Output("bar-title", "children"),
    Input("state-dropdown", "value"),
    Input("granularity-selector", "value"),
    Input("metric-selector", "value"),
)
def update_dashboard(selected_state, granularity, metric):
    print("\n--- DASHBOARD CALLBACK ---")
    print("State:", selected_state)
    print("Granularity:", granularity)
    print("Metric:", metric)
    print("Religion columns:", religion_data.columns.tolist())
    metric_label = (
        "Population" if metric == "pop_display" else "Mean Age (Years)"
    )
    color_scale = "Viridis" if metric == "pop_display" else "Plasma"

    if selected_state == "ALL" and granularity == "STATE":
        rel_df=religion_data.groupby('Religion',as_index=False)['population'].sum()
        df = state_map.copy()
        geojson_data = state_geojson_dict
        bar_label_col = "state_name"
        map_text_col = "state_name"
        show_labels = True
        line_width = 1.2
        center = {"lat": 22.8, "lon": 82.8}
        zoom = 4.1
        map_heading = (
            "India — State-Wise View "
            "(Scroll to zoom, click any state)"
        )
        bar_heading = f"Top 15 States by {metric_label}"

    elif selected_state == "ALL" and granularity == "DISTRICT":
        df = district_map.copy()
        rel_df = (religion_data.groupby("Religion", as_index=False)["population"].sum())
        geojson_data = all_districts_geojson_dict
        bar_label_col = "region_label"
        map_text_col = "DISTRICT"
        show_labels = False
        line_width = 0.5
        center = {"lat": 22.8, "lon": 82.8}
        zoom = 4.1
        map_heading = (
            "India — All Districts View "
            "(Scroll to zoom, click any district)"
        )
        bar_heading = f"Top 15 Districts in India by {metric_label}"

    else:
        df = district_map[
            district_map["state_key"] == selected_state
        ].copy()
        rel_df = (
    religion_data[
        religion_data["state_key"] == selected_state].groupby("Religion", as_index=False)["population"].sum())
        geojson_data = json.loads(
            df[["feature_id", "geometry"]].to_json()
        )
        bar_label_col = "DISTRICT"
        map_text_col = "DISTRICT"
        show_labels = True
        line_width = 1.0
        center, zoom = get_bounds_center_zoom(df)

        state_title = (
            df["state_name"].iloc[0]
            if not df.empty
            else selected_state.title()
        )
        map_heading = f"{state_title} — District-Wise View"
        bar_heading = (
            f"{state_title} — Top Districts by {metric_label}"
        )

    # 1. Choropleth layer with dark borders.
    map_fig = go.Figure(
        go.Choroplethmap(
            geojson=geojson_data,
            locations=df["feature_id"],
            featureidkey="properties.feature_id",
            z=df[metric],
            colorscale=color_scale,
            marker_opacity=0.92,
            marker_line_width=line_width,
            marker_line_color="#1f2937",
            colorbar={
                "title": metric_label,
                "orientation": "h",
                "x": 0.5,
                "y": 0.02,
                "xanchor": "center",
                "len": 0.45,
                "thickness": 12,
                "bgcolor": "rgba(255,255,255,0.9)",
            },
            customdata=df[
                ["state_key", "region_label", "pop_display", "age_display"]
            ].to_numpy(),
            hovertemplate=(
                "<b>%{customdata[1]}</b><br>"
                "Population: %{customdata[2]:,}<br>"
                "Mean Age: %{customdata[3]}"
                "<extra></extra>"
            ),
        )
    )

    # 2. Direct text labels on states and zoomed districts.
    if show_labels and not df.empty:
        map_fig.add_trace(
            go.Scattermap(
                lat=df["label_lat"],
                lon=df["label_lon"],
                mode="text",
                text=df[map_text_col],
                textfont={"size": 10, "color": "#111827"},
                hoverinfo="skip",
                showlegend=False,
            )
        )

    map_fig.update_layout(
        map_style="white-bg",
        map_zoom=zoom,
        map_center=center,
        margin={"t": 0, "l": 0, "r": 0, "b": 0},
        autosize=True,
    )

    # 3. Side ranking bar chart.
    bar_df = (
        df.dropna(subset=[metric])
        .sort_values(by=metric, ascending=False)
        .head(15)
        .iloc[::-1]
    )

    bar_fig = px.bar(
        bar_df,
        x=metric,
        y=bar_label_col,
        orientation="h",
        color=metric,
        color_continuous_scale=color_scale,
        labels={metric: metric_label, bar_label_col: ""},
    )

    text_format = (
        "%{x:,}" if metric == "pop_display" else "%{x:.1f}"
    )
    bar_fig.update_traces(
        texttemplate=text_format,
        textposition="outside",
    )
    bar_fig.update_layout(
        coloraxis_showscale=False,
        margin={"t": 10, "l": 10, "r": 40, "b": 20},
        xaxis_title=metric_label,
        yaxis_title="",
        plot_bgcolor="#ffffff",
    )
    # 4. Religion distribution pie chart

    if not rel_df.empty:
        religion_fig = px.pie(
        rel_df,
        names="Religion",
        values="population",
        
        color="Religion",
        color_discrete_sequence=px.colors.qualitative.Set3
    )  # Initialize first

        print("\n--- Religion ---")
        print("State:", selected_state)
        print("Granularity:", granularity)
        print("Metric:", metric)
        

        religion_fig.update_traces(
    textposition="inside",
    textinfo="percent",
    hovertemplate=(
        "<b>%{label}</b><br>"
        "Population: %{value:,.0f}<br>"
        "Share: %{percent}"
        "<extra></extra>"
    ),
    marker=dict(
        line=dict(color="#ffffff", width=2)
    ),
)

        religion_fig.update_layout(
    margin=dict(t=10, b=10, l=5, r=5),
    showlegend=True,
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=-0.18,
        xanchor="center",
        x=0.5,
        font=dict(size=10),
    ),
    paper_bgcolor="#ffffff",
    plot_bgcolor="#ffffff",
)

    else:
        religion_fig = go.Figure()

        religion_fig.add_annotation(
        text="No religion data available",
        showarrow=False
    )

    return (
    map_fig,
    religion_fig,
    map_heading,
    bar_fig,
    bar_heading
)


if __name__ == "__main__":
    app.run(debug=True)
