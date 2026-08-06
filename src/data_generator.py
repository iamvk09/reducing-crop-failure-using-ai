import numpy as np
import pandas as pd


RAW_DISTRICTS = [
    ("Jaipur", "Rajasthan", "Northwest Dryland", 26.9124, 75.7873, "Sandy Loam", "Medium", 78, 31.5, 46),
    ("Jodhpur", "Rajasthan", "Northwest Dryland", 26.2389, 73.0243, "Sandy", "Low", 52, 33.2, 37),
    ("Kota", "Rajasthan", "Central Plateau", 25.2138, 75.8648, "Black", "High", 112, 30.1, 54),
    ("Udaipur", "Rajasthan", "Northwest Dryland", 24.5854, 73.7125, "Sandy Loam", "Medium", 96, 29.4, 52),
    ("Ajmer", "Rajasthan", "Northwest Dryland", 26.4499, 74.6399, "Loam", "Medium", 84, 30.2, 49),
    ("Lucknow", "Uttar Pradesh", "Indo Gangetic Plains", 26.8467, 80.9462, "Alluvial", "High", 132, 28.4, 61),
    ("Kanpur", "Uttar Pradesh", "Indo Gangetic Plains", 26.4499, 80.3319, "Alluvial", "High", 126, 29.0, 58),
    ("Varanasi", "Uttar Pradesh", "Indo Gangetic Plains", 25.3176, 82.9739, "Alluvial", "High", 138, 29.1, 63),
    ("Agra", "Uttar Pradesh", "Indo Gangetic Plains", 27.1767, 78.0081, "Alluvial", "Medium", 92, 29.8, 52),
    ("Meerut", "Uttar Pradesh", "Indo Gangetic Plains", 28.9845, 77.7064, "Loam", "High", 88, 27.6, 56),
    ("Prayagraj", "Uttar Pradesh", "Indo Gangetic Plains", 25.4358, 81.8463, "Alluvial", "High", 104, 29.7, 58),
    ("Gorakhpur", "Uttar Pradesh", "Indo Gangetic Plains", 26.7606, 83.3732, "Alluvial", "High", 154, 28.2, 68),
    ("Patna", "Bihar", "Indo Gangetic Plains", 25.5941, 85.1376, "Alluvial", "High", 146, 28.3, 68),
    ("Gaya", "Bihar", "Indo Gangetic Plains", 24.7914, 85.0002, "Alluvial", "Medium", 118, 28.9, 61),
    ("Muzaffarpur", "Bihar", "Indo Gangetic Plains", 26.1209, 85.3647, "Alluvial", "High", 152, 28.0, 71),
    ("Bhagalpur", "Bihar", "Humid East", 25.2425, 86.9842, "Alluvial", "High", 144, 28.5, 69),
    ("Ranchi", "Jharkhand", "Humid East", 23.3441, 85.3096, "Red Loam", "Medium", 142, 25.7, 68),
    ("Dhanbad", "Jharkhand", "Humid East", 23.7957, 86.4304, "Red Sandy Loam", "Medium", 128, 27.9, 64),
    ("Jamshedpur", "Jharkhand", "Humid East", 22.8046, 86.2029, "Red Loam", "Medium", 136, 27.2, 67),
    ("Kolkata", "West Bengal", "Humid East", 22.5726, 88.3639, "Alluvial", "High", 162, 28.7, 77),
    ("Siliguri", "West Bengal", "Humid East", 26.7271, 88.3953, "Alluvial", "High", 188, 24.6, 79),
    ("Durgapur", "West Bengal", "Humid East", 23.5204, 87.3119, "Laterite", "Medium", 132, 28.4, 66),
    ("Asansol", "West Bengal", "Humid East", 23.6739, 86.9524, "Laterite", "Medium", 126, 28.8, 64),
    ("Bhubaneswar", "Odisha", "Coastal Delta", 20.2961, 85.8245, "Clay Loam", "Medium", 154, 29.1, 76),
    ("Cuttack", "Odisha", "Coastal Delta", 20.4625, 85.8830, "Alluvial", "Medium", 150, 28.9, 75),
    ("Sambalpur", "Odisha", "Humid East", 21.4669, 83.9812, "Red Loam", "Medium", 136, 28.5, 69),
    ("Guwahati", "Assam", "Humid East", 26.1445, 91.7362, "Alluvial", "High", 182, 26.8, 79),
    ("Dibrugarh", "Assam", "Humid East", 27.4728, 94.9120, "Alluvial", "High", 214, 25.6, 83),
    ("Silchar", "Assam", "Humid East", 24.8333, 92.7789, "Clay Loam", "High", 206, 26.2, 84),
    ("Imphal", "Manipur", "Humid East", 24.8170, 93.9368, "Clay Loam", "Medium", 176, 24.5, 81),
    ("Agartala", "Tripura", "Humid East", 23.8315, 91.2868, "Red Loam", "Medium", 196, 26.2, 83),
    ("Shillong", "Meghalaya", "Humid East", 25.5788, 91.8933, "Red Loam", "Medium", 228, 22.4, 86),
    ("Aizawl", "Mizoram", "Humid East", 23.7271, 92.7176, "Red Loam", "Low", 208, 23.7, 84),
    ("Kohima", "Nagaland", "Humid East", 25.6751, 94.1086, "Red Loam", "Low", 188, 23.8, 82),
    ("Itanagar", "Arunachal Pradesh", "Humid East", 27.0844, 93.6053, "Alluvial", "Medium", 224, 24.3, 85),
    ("Gangtok", "Sikkim", "Humid East", 27.3389, 88.6065, "Loam", "Medium", 196, 18.9, 83),
    ("Srinagar", "Jammu and Kashmir", "Himalayan Foothills", 34.0837, 74.7973, "Loam", "Medium", 72, 16.8, 58),
    ("Jammu", "Jammu and Kashmir", "Himalayan Foothills", 32.7266, 74.8570, "Loam", "Medium", 88, 24.9, 56),
    ("Leh", "Ladakh", "Himalayan Foothills", 34.1526, 77.5770, "Sandy", "Low", 18, 11.2, 29),
    ("Shimla", "Himachal Pradesh", "Himalayan Foothills", 31.1048, 77.1734, "Loam", "Medium", 112, 18.6, 63),
    ("Dharamshala", "Himachal Pradesh", "Himalayan Foothills", 32.2190, 76.3234, "Loam", "Medium", 164, 19.1, 71),
    ("Dehradun", "Uttarakhand", "Himalayan Foothills", 30.3165, 78.0322, "Loam", "Medium", 138, 22.9, 67),
    ("Haridwar", "Uttarakhand", "Himalayan Foothills", 29.9457, 78.1642, "Alluvial", "High", 116, 24.8, 62),
    ("Chandigarh", "Punjab", "Northwest Irrigated", 30.7333, 76.7794, "Loam", "High", 104, 25.8, 58),
    ("Ludhiana", "Punjab", "Northwest Irrigated", 30.9010, 75.8573, "Loam", "High", 98, 26.4, 57),
    ("Amritsar", "Punjab", "Northwest Irrigated", 31.6340, 74.8723, "Loam", "High", 86, 26.6, 54),
    ("Jalandhar", "Punjab", "Northwest Irrigated", 31.3260, 75.5762, "Loam", "High", 92, 26.1, 55),
    ("Patiala", "Punjab", "Northwest Irrigated", 30.3398, 76.3869, "Loam", "High", 98, 26.3, 56),
    ("Karnal", "Haryana", "Northwest Irrigated", 29.6857, 76.9905, "Loam", "High", 84, 26.7, 54),
    ("Hisar", "Haryana", "Northwest Dryland", 29.1492, 75.7217, "Sandy Loam", "Medium", 56, 29.7, 42),
    ("Gurugram", "Haryana", "Northwest Dryland", 28.4595, 77.0266, "Sandy Loam", "Medium", 62, 29.5, 44),
    ("Delhi", "Delhi", "Indo Gangetic Plains", 28.6139, 77.2090, "Alluvial", "Medium", 78, 28.9, 49),
    ("Ahmedabad", "Gujarat", "Semi Arid West", 23.0225, 72.5714, "Loamy Sand", "Medium", 82, 31.2, 49),
    ("Surat", "Gujarat", "Coastal Delta", 21.1702, 72.8311, "Black", "Medium", 138, 29.7, 72),
    ("Vadodara", "Gujarat", "Semi Arid West", 22.3072, 73.1812, "Black", "Medium", 102, 30.2, 60),
    ("Rajkot", "Gujarat", "Semi Arid West", 22.3039, 70.8022, "Loamy Sand", "Low", 76, 31.5, 53),
    ("Bhavnagar", "Gujarat", "Semi Arid West", 21.7645, 72.1519, "Loamy Sand", "Low", 72, 31.7, 58),
    ("Mumbai", "Maharashtra", "Coastal Delta", 19.0760, 72.8777, "Clay Loam", "Medium", 218, 28.1, 82),
    ("Pune", "Maharashtra", "Western Plateau", 18.5204, 73.8567, "Medium Black", "Medium", 104, 27.1, 64),
    ("Nagpur", "Maharashtra", "Western Plateau", 21.1458, 79.0882, "Black", "Medium", 112, 29.4, 58),
    ("Nashik", "Maharashtra", "Western Plateau", 19.9975, 73.7898, "Black", "Medium", 98, 27.4, 60),
    ("Aurangabad", "Maharashtra", "Western Plateau", 19.8762, 75.3433, "Black", "Medium", 82, 29.6, 54),
    ("Kolhapur", "Maharashtra", "Coastal Delta", 16.7050, 74.2433, "Black", "High", 164, 26.3, 74),
    ("Bhopal", "Madhya Pradesh", "Central Plateau", 23.2599, 77.4126, "Black", "Medium", 118, 28.8, 56),
    ("Indore", "Madhya Pradesh", "Central Plateau", 22.7196, 75.8577, "Black", "Medium", 108, 28.6, 52),
    ("Gwalior", "Madhya Pradesh", "Central Plateau", 26.2183, 78.1828, "Alluvial", "Medium", 88, 29.5, 48),
    ("Jabalpur", "Madhya Pradesh", "Central Plateau", 23.1815, 79.9864, "Black", "Medium", 128, 28.2, 59),
    ("Ujjain", "Madhya Pradesh", "Central Plateau", 23.1765, 75.7885, "Black", "Medium", 98, 28.7, 54),
    ("Raipur", "Chhattisgarh", "Central Plateau", 21.2514, 81.6296, "Black", "Medium", 138, 28.7, 69),
    ("Bilaspur", "Chhattisgarh", "Central Plateau", 22.0797, 82.1391, "Clay Loam", "Medium", 142, 28.4, 70),
    ("Visakhapatnam", "Andhra Pradesh", "Coastal Delta", 17.6868, 83.2185, "Clay Loam", "Medium", 146, 29.0, 77),
    ("Vijayawada", "Andhra Pradesh", "Coastal Delta", 16.5062, 80.6480, "Alluvial", "High", 128, 30.1, 73),
    ("Guntur", "Andhra Pradesh", "Coastal Delta", 16.3067, 80.4365, "Black", "High", 112, 30.4, 68),
    ("Tirupati", "Andhra Pradesh", "Southern Plateau", 13.6288, 79.4192, "Red Loam", "Medium", 102, 29.6, 69),
    ("Hyderabad", "Telangana", "Deccan Plateau", 17.3850, 78.4867, "Red Sandy Loam", "Medium", 94, 29.8, 57),
    ("Warangal", "Telangana", "Deccan Plateau", 17.9689, 79.5941, "Black", "Medium", 108, 28.8, 61),
    ("Karimnagar", "Telangana", "Deccan Plateau", 18.4386, 79.1288, "Black", "Medium", 102, 29.2, 59),
    ("Nizamabad", "Telangana", "Deccan Plateau", 18.6725, 78.0941, "Black", "Medium", 112, 28.6, 62),
    ("Bengaluru", "Karnataka", "Southern Plateau", 12.9716, 77.5946, "Red Loam", "Medium", 98, 24.8, 66),
    ("Mysuru", "Karnataka", "Southern Plateau", 12.2958, 76.6394, "Red Sandy Loam", "Medium", 92, 25.4, 64),
    ("Hubballi", "Karnataka", "Southern Plateau", 15.3647, 75.1240, "Black", "Medium", 84, 27.9, 57),
    ("Belagavi", "Karnataka", "Southern Plateau", 15.8497, 74.4977, "Black", "Medium", 124, 26.1, 68),
    ("Mangaluru", "Karnataka", "Coastal Delta", 12.9141, 74.8560, "Laterite", "Medium", 228, 27.3, 83),
    ("Chennai", "Tamil Nadu", "Coastal Delta", 13.0827, 80.2707, "Clay Loam", "Medium", 124, 30.4, 72),
    ("Coimbatore", "Tamil Nadu", "Southern Plateau", 11.0168, 76.9558, "Red Loam", "Medium", 86, 28.7, 61),
    ("Madurai", "Tamil Nadu", "Southern Plateau", 9.9252, 78.1198, "Red Loam", "Medium", 92, 29.5, 64),
    ("Salem", "Tamil Nadu", "Southern Plateau", 11.6643, 78.1460, "Red Loam", "Medium", 88, 28.8, 63),
    ("Thanjavur", "Tamil Nadu", "Coastal Delta", 10.7870, 79.1378, "Clay Loam", "High", 136, 28.9, 74),
    ("Thiruvananthapuram", "Kerala", "Coastal Delta", 8.5241, 76.9366, "Laterite", "Medium", 188, 27.9, 83),
    ("Kochi", "Kerala", "Coastal Delta", 9.9312, 76.2673, "Laterite", "Medium", 202, 27.6, 85),
    ("Kozhikode", "Kerala", "Coastal Delta", 11.2588, 75.7804, "Laterite", "Medium", 212, 27.2, 84),
    ("Panaji", "Goa", "Coastal Delta", 15.4909, 73.8278, "Laterite", "Medium", 224, 28.0, 84),
    ("Puducherry", "Puducherry", "Coastal Delta", 11.9416, 79.8083, "Clay Loam", "Medium", 132, 29.4, 76),
]


DISTRICTS = [
    {
        "District": district,
        "State": state,
        "Region": region,
        "Latitude": latitude,
        "Longitude": longitude,
        "SoilType": soil_type,
        "IrrigationLevel": irrigation_level,
        "BaseRainfall": base_rainfall,
        "BaseTemperature": base_temperature,
        "BaseHumidity": base_humidity,
    }
    for district, state, region, latitude, longitude, soil_type, irrigation_level, base_rainfall, base_temperature, base_humidity in RAW_DISTRICTS
]


CROPS = [
    {
        "Crop": "Rice",
        "Season": "Kharif",
        "IdealTemperature": 28,
        "IdealRainfall": 170,
        "IdealHumidity": 78,
        "IdealSoilMoisture": 78,
        "PreferredSoils": {"Alluvial", "Clay Loam"},
    },
    {
        "Crop": "Maize",
        "Season": "Kharif",
        "IdealTemperature": 27,
        "IdealRainfall": 115,
        "IdealHumidity": 62,
        "IdealSoilMoisture": 58,
        "PreferredSoils": {"Alluvial", "Loam", "Red Loam"},
    },
    {
        "Crop": "Cotton",
        "Season": "Kharif",
        "IdealTemperature": 29,
        "IdealRainfall": 92,
        "IdealHumidity": 56,
        "IdealSoilMoisture": 52,
        "PreferredSoils": {"Black", "Medium Black"},
    },
    {
        "Crop": "Soybean",
        "Season": "Kharif",
        "IdealTemperature": 26,
        "IdealRainfall": 108,
        "IdealHumidity": 64,
        "IdealSoilMoisture": 60,
        "PreferredSoils": {"Black", "Loam"},
    },
    {
        "Crop": "Wheat",
        "Season": "Rabi",
        "IdealTemperature": 21,
        "IdealRainfall": 84,
        "IdealHumidity": 52,
        "IdealSoilMoisture": 50,
        "PreferredSoils": {"Alluvial", "Loam", "Clay Loam"},
    },
    {
        "Crop": "Mustard",
        "Season": "Rabi",
        "IdealTemperature": 22,
        "IdealRainfall": 62,
        "IdealHumidity": 45,
        "IdealSoilMoisture": 42,
        "PreferredSoils": {"Sandy Loam", "Loam", "Alluvial"},
    },
    {
        "Crop": "Chickpea",
        "Season": "Rabi",
        "IdealTemperature": 23,
        "IdealRainfall": 58,
        "IdealHumidity": 42,
        "IdealSoilMoisture": 40,
        "PreferredSoils": {"Black", "Loam", "Alluvial"},
    },
    {
        "Crop": "Groundnut",
        "Season": "Zaid",
        "IdealTemperature": 30,
        "IdealRainfall": 72,
        "IdealHumidity": 50,
        "IdealSoilMoisture": 46,
        "PreferredSoils": {"Sandy", "Loamy Sand", "Red Sandy Loam"},
    },
    {
        "Crop": "Millet",
        "Season": "Zaid",
        "IdealTemperature": 31,
        "IdealRainfall": 48,
        "IdealHumidity": 38,
        "IdealSoilMoisture": 34,
        "PreferredSoils": {"Sandy", "Sandy Loam", "Red Sandy Loam"},
    },
]


SEASON_OFFSETS = {
    "Kharif": {"rainfall": 42, "temperature": 1.5, "humidity": 10, "soil_moisture": 12},
    "Rabi": {"rainfall": -24, "temperature": -6.5, "humidity": -8, "soil_moisture": -10},
    "Zaid": {"rainfall": -36, "temperature": 3.8, "humidity": -12, "soil_moisture": -14},
}


IRRIGATION_SCORES = {"Low": 0.25, "Medium": 0.55, "High": 0.8}


def _clip(value, low, high):
    return max(low, min(high, value))


def _build_crop_row(district, crop, year, rng):
    season = crop["Season"]
    season_shift = SEASON_OFFSETS[season]

    rainfall = district["BaseRainfall"] + season_shift["rainfall"] + rng.normal(0, 16)
    temperature = district["BaseTemperature"] + season_shift["temperature"] + rng.normal(0, 2.2)
    humidity = district["BaseHumidity"] + season_shift["humidity"] + rng.normal(0, 7)
    soil_moisture = 46 + season_shift["soil_moisture"] + rng.normal(0, 8)

    rainfall = _clip(rainfall, 18, 240)
    temperature = _clip(temperature, 14, 41)
    humidity = _clip(humidity, 25, 92)
    soil_moisture = _clip(soil_moisture, 18, 90)

    irrigation_score = IRRIGATION_SCORES[district["IrrigationLevel"]]
    soil_match = district["SoilType"] in crop["PreferredSoils"]

    temp_gap = abs(temperature - crop["IdealTemperature"]) / 16
    rain_gap = abs(rainfall - crop["IdealRainfall"]) / 150
    humidity_gap = abs(humidity - crop["IdealHumidity"]) / 70
    moisture_gap = abs(soil_moisture - crop["IdealSoilMoisture"]) / 65
    soil_penalty = 0 if soil_match else 0.12
    irrigation_bonus = 0.10 * irrigation_score
    yearly_volatility = abs(year - 2021) * 0.01

    suitability = 1.04 - (
        0.35 * temp_gap
        + 0.28 * rain_gap
        + 0.15 * humidity_gap
        + 0.17 * moisture_gap
        + soil_penalty
        + yearly_volatility
    )
    suitability += irrigation_bonus + rng.normal(0, 0.03)
    suitability = _clip(suitability, 0.05, 0.98)

    ndvi = _clip(0.32 + (0.48 * suitability) + rng.normal(0, 0.03), 0.18, 0.92)
    water_stress = _clip(
        0.15
        + max(0, crop["IdealSoilMoisture"] - soil_moisture) / 70
        + max(0, crop["IdealRainfall"] - rainfall) / 180
        - 0.08 * irrigation_score
        + rng.normal(0, 0.03),
        0.02,
        0.98,
    )
    pest_risk = _clip(
        0.18
        + (humidity / 100) * 0.25
        + (temperature / 40) * 0.16
        + rng.normal(0, 0.04),
        0.04,
        0.92,
    )
    yield_index = _clip(
        42 + (58 * suitability) - (18 * water_stress) - (10 * pest_risk) + rng.normal(0, 4.5),
        15,
        100,
    )

    failure_probability = _clip(
        0.92
        - suitability
        + (0.28 * water_stress)
        + (0.14 * pest_risk)
        + (0.08 if not soil_match else 0)
        + rng.normal(0, 0.03),
        0.02,
        0.95,
    )
    failure = int(rng.random() < failure_probability)

    return {
        "District": district["District"],
        "State": district["State"],
        "Region": district["Region"],
        "Year": year,
        "Season": season,
        "Crop": crop["Crop"],
        "Latitude": district["Latitude"],
        "Longitude": district["Longitude"],
        "SoilType": district["SoilType"],
        "IrrigationLevel": district["IrrigationLevel"],
        "Rainfall": round(rainfall, 2),
        "Temperature": round(temperature, 2),
        "Humidity": round(humidity, 2),
        "SoilMoisture": round(soil_moisture, 2),
        "NDVI_Flowering": round(ndvi, 3),
        "WaterStress": round(water_stress, 3),
        "PestRisk": round(pest_risk, 3),
        "SuitabilityScore": round(suitability, 3),
        "YieldIndex": round(yield_index, 2),
        "Failure": failure,
    }


def generate_dataset(output_path="data/district_dataset.csv", random_state=42):
    rng = np.random.default_rng(random_state)
    rows = []

    for district in DISTRICTS:
        for year in range(2018, 2027):
            for crop in CROPS:
                rows.append(_build_crop_row(district, crop, year, rng))

    df = pd.DataFrame(rows)
    best_crop = (
        df.sort_values("SuitabilityScore", ascending=False)
        .groupby(["District", "Year", "Season"], as_index=False)
        .first()[["District", "Year", "Season", "Crop"]]
        .rename(columns={"Crop": "RecommendedCrop"})
    )
    df = df.merge(best_crop, on=["District", "Year", "Season"], how="left")
    df["IsRecommendedCrop"] = (df["Crop"] == df["RecommendedCrop"]).astype(int)

    df.to_csv(output_path, index=False)

    print(f"Dataset saved to {output_path}")
    print(df[["Failure", "IsRecommendedCrop"]].sum())
    print(f"Rows: {len(df)} | Districts: {df['District'].nunique()} | Crops: {df['Crop'].nunique()}")


if __name__ == "__main__":
    generate_dataset()
