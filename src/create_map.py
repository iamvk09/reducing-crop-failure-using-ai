import folium
import pandas as pd


SUMMARY_PATH = "data/district_summary.csv"
MAP_PATH = "maps/india_risk_map.html"


def _marker_color(risk_level):
    if risk_level == "High":
        return "red"
    if risk_level == "Medium":
        return "orange"
    return "green"


def create_map(summary_path=SUMMARY_PATH, output_path=MAP_PATH):
    df = pd.read_csv(summary_path)
    india_map = folium.Map(location=[22.8, 79.8], zoom_start=5, tiles="CartoDB positron")

    for _, row in df.iterrows():
        popup = folium.Popup(
            (
                f"<b>{row['District']}, {row['State']}</b><br>"
                f"Current Crop: {row['CurrentCrop']}<br>"
                f"Recommended Crop: {row['RecommendedCrop']}<br>"
                f"Risk Level: {row['RiskLevel']}<br>"
                f"Consensus Risk: {row['ConsensusRisk'] * 100:.1f}%<br>"
                f"Top Options: {row['TopCropOptions']}"
            ),
            max_width=320,
        )

        folium.CircleMarker(
            location=[row["Latitude"], row["Longitude"]],
            radius=8,
            color=_marker_color(row["RiskLevel"]),
            fill=True,
            fill_color=_marker_color(row["RiskLevel"]),
            fill_opacity=0.8,
            popup=popup,
        ).add_to(india_map)

    india_map.save(output_path)
    print(f"Map saved to {output_path}")


if __name__ == "__main__":
    create_map()
