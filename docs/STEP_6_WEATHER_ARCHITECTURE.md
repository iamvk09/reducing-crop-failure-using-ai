# Weather Architecture Documentation (Step 6)

## 1. Executive Summary

Step 6 introduces a clean, provider-independent Agrometeorological Weather Data Foundation for the **AI Crop Failure Decision-Support Platform**. This layer decouples external weather providers from downstream agronomic prediction pipelines and user interfaces while maintaining complete backward compatibility with the existing Open-Meteo integration and machine learning runtime bundle.

---

## 2. End-to-End Architectural Flow

```
[Farmer / Expert Dashboard]
             │
             ▼
[FastAPI Weather & Farm Endpoints]
  ├─ GET /api/v1/farms/{farm_id}/weather/current
  ├─ GET /api/v1/farms/{farm_id}/weather/forecast
  ├─ GET /api/v1/farms/{farm_id}/weather/history
  ├─ GET /api/v1/weather/current
  └─ GET /api/v1/weather/forecast
             │
             ▼
      [WeatherService]
  ├─ In-Memory TTL Cache (15 min default)
  ├─ Coordinate Resolution (from Farm or Params)
  ├─ Fallback / Offline Resilience
  └─ Telemetry Persistence (WeatherRepository)
             │
             ▼
   [WeatherProvider ABC]
             │
             ▼
    [OpenMeteoProvider]
  ├─ Real-Time REST API (v1/forecast)
  ├─ 4-Layer Soil Moisture Aggregation (0-27 cm)
  ├─ 7-Day / Multi-Day Agronomic Projections
  └─ Timeout & Exception Normalization
             │
             ▼
[Supabase `weather_observations` Table]
```

---

## 3. Provider Abstraction Interface (`WeatherProvider`)

The core abstraction is defined in `backend/app/services/weather/providers/base.py`:

```python
class WeatherProvider(ABC):
    @abstractmethod
    def get_current_weather(
        self,
        latitude: float,
        longitude: float,
        farm_id: Optional[str] = None,
    ) -> CurrentWeatherResponse:
        """Fetch current weather observation for coordinate."""
        pass

    @abstractmethod
    def get_forecast(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
        farm_id: Optional[str] = None,
    ) -> WeatherForecastResponse:
        """Fetch multi-day weather forecast."""
        pass
```

Future providers (e.g. IMD, ECMWF, AWS IoT weather stations) can be added simply by implementing `WeatherProvider` without modifying upstream API routes or downstream ML prediction pipelines.

---

## 4. Root-Zone Soil Moisture Formulation

Open-Meteo returns four volumetric soil moisture layers ($m^3/m^3$):
- `soil_moisture_0_to_1cm`
- `soil_moisture_1_to_3cm`
- `soil_moisture_3_to_9cm`
- `soil_moisture_9_to_27cm`

The provider aggregates these layers across the root zone ($0\text{--}27\text{ cm}$):

$$\theta_{\text{root}} = \frac{1}{4}\sum_{i=1}^{4} \theta_i \quad [\text{m}^3/\text{m}^3]$$

To normalize volumetric fraction to agronomic percentage saturation (scaled against an assumed average field capacity of $0.45\,\text{m}^3/\text{m}^3$):

$$\text{SoilMoisture}_{\%} = \min\left(\max\left(\text{round}\left(\frac{\theta_{\text{root}}}{0.45} \times 100, 1\right), 5.0\right), 95.0\right)$$

This provides continuity with existing ML training distributions while preserving volumetric metrics for precision agrometeorology.

---

## 5. Forecast Scope & Disclaimer Policy

> [!IMPORTANT]
> All forecast endpoints and UI displays strictly include the canonical planning notice:
> **"This is numerical meteorological forecast data provided for agronomic planning and is not a crop-failure risk assessment."**
> 
> Crop failure risk evaluation remains explicitly bound to the validated ML prediction engine and requires farm/crop context.

---

## 6. Caching Strategy & Persistence

1. **In-Memory TTL Caching:**
   - Keys: `{lat:.4f}:{lon:.4f}:current` and `{lat:.4f}:{lon:.4f}:forecast:{days}`
   - Default TTL: 900 seconds (15 minutes), configurable via `WEATHER_CACHE_TTL_SECONDS`.
   - Prevents external API rate limiting and provides sub-millisecond response times for concurrent requests.

2. **Supabase PostgreSQL Persistence (`weather_observations`):**
   - Migration `004_weather_data.sql` establishes schema with composite index `idx_weather_obs_farm_time ON weather_observations (farm_id, observation_time DESC)`.
   - Observation history is isolated per tenant with Row-Level Security (RLS).
