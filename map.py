import geopandas as gpd
import folium
file_path = r"C:\Users\lenovo\credential\maps-master\Districts\Census_2011\2011_Dist.shp"
# Load shapefile
gdf = gpd.read_file(file_path)

# Convert to WGS84 for Folium
gdf = gdf.to_crs(epsg=4326)

# Create India map
india_map = folium.Map(
    location=[22.5, 82.0],
    zoom_start=5,
    tiles="CartoDB positron"
)

# Add district boundaries
folium.GeoJson(
    gdf,
    name="District Boundaries",
    style_function=lambda feature: {
        "fillColor": "#3388ff",
        "color": "#333333",
        "weight": 0.7,
        "fillOpacity": 0.25
    },
    tooltip=folium.GeoJsonTooltip(
        fields=["ST_NM", "DISTRICT"],
        aliases=["State:", "District:"],
        sticky=True
    )
).add_to(india_map)

# Layer control
folium.LayerControl().add_to(india_map)

# Save map
india_map.save("india_district_map.html")

print("Map generated successfully!")
import webbrowser
webbrowser.open("india_district_map.html")