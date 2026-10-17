"use client";

import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import { CurrentWeatherResponse, WeatherForecastResponse } from "../types";
import { getCurrentWeatherByCoords, getForecastByCoords, reverseGeocodeCoords } from "../api/weather";
import { useAuth } from "./AuthContext";

export interface UserLocationState {
  latitude: number | null;
  longitude: number | null;
  placeName: string | null;
  locality: string | null;
  city: string | null;
  district: string | null;
  state: string | null;
  country: string | null;
  isGpsVerified: boolean;
  status: "idle" | "detecting" | "granted" | "denied" | "unavailable" | "manual";
  errorMessage: string | null;
}

export interface UserLocationContextType {
  location: UserLocationState;
  weather: CurrentWeatherResponse | null;
  forecast: WeatherForecastResponse | null;
  forecastHorizon: 7 | 14;
  isWeatherLoading: boolean;
  isForecastLoading: boolean;
  isGeocodingLoading: boolean;
  weatherError: string | null;
  forecastError: string | null;
  requestLocation: () => void;
  setManualLocation: (lat: number, lon: number, localityName?: string) => void;
  setForecastHorizon: (days: 7 | 14) => void;
  refreshWeather: () => void;
}

const LOCATION_STORAGE_KEY = "crop_ai_user_location_cache";

const UserLocationContext = createContext<UserLocationContextType | undefined>(undefined);

export const UserLocationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { token: authToken } = useAuth();

  const [location, setLocation] = useState<UserLocationState>({
    latitude: null,
    longitude: null,
    placeName: null,
    locality: null,
    city: null,
    district: null,
    state: null,
    country: null,
    isGpsVerified: false,
    status: "idle",
    errorMessage: null,
  });

  const [weather, setWeather] = useState<CurrentWeatherResponse | null>(null);
  const [forecast, setForecast] = useState<WeatherForecastResponse | null>(null);
  const [forecastHorizon, setForecastHorizon] = useState<7 | 14>(7);
  const [isWeatherLoading, setIsWeatherLoading] = useState<boolean>(false);
  const [isForecastLoading, setIsForecastLoading] = useState<boolean>(false);
  const [isGeocodingLoading, setIsGeocodingLoading] = useState<boolean>(false);
  const [weatherError, setWeatherError] = useState<string | null>(null);
  const [forecastError, setForecastError] = useState<string | null>(null);


  const hasRequestedLocationRef = useRef<boolean>(false);

  // Helper to resolve the authenticated token
  const getEffectiveToken = useCallback(() => {
    if (authToken) return authToken;
    if (typeof window !== "undefined") {
      try {
        const stored = localStorage.getItem("crop_ai_dev_session");
        if (stored) {
          const parsed = JSON.parse(stored);
          if (parsed?.token) return parsed.token;
        }
      } catch {}
    }
    return "mock-dev-token-farmer";
  }, [authToken]);

  // Fetch weather and forecast when coordinates change
  const fetchWeatherForLocation = useCallback(
    async (lat: number, lon: number, horizon: 7 | 14 = forecastHorizon) => {
      const activeToken = getEffectiveToken();

      setIsWeatherLoading(true);
      setWeatherError(null);
      try {
        const cw = await getCurrentWeatherByCoords(lat, lon, activeToken);
        setWeather(cw);
      } catch (err: any) {
        setWeatherError(err?.message || "Weather observation unavailable");
      } finally {
        setIsWeatherLoading(false);
      }

      setIsForecastLoading(true);
      setForecastError(null);
      try {
        const fc = await getForecastByCoords(lat, lon, activeToken, horizon);
        setForecast(fc);
      } catch (err: any) {
        setForecastError(err?.message || "Weather forecast unavailable");
      } finally {
        setIsForecastLoading(false);
      }
    },
    [forecastHorizon, getEffectiveToken]
  );

  // Reverse geocode and update location
  const updateLocationWithCoords = useCallback(
    async (lat: number, lon: number, isGps: boolean, fallbackLocality?: string) => {
      const activeToken = getEffectiveToken();
      let placeName = fallbackLocality || null;
      let locality = fallbackLocality || null;
      let cityName: string | null = null;
      let districtName: string | null = null;
      let stateName: string | null = null;
      let countryName: string | null = null;

      setIsGeocodingLoading(true);

      // Pre-set coordinates immediately so weather fetch can start without delay
      const initialLoc: UserLocationState = {
        latitude: lat,
        longitude: lon,
        placeName: fallbackLocality || null,
        locality: fallbackLocality || null,
        city: null,
        district: null,
        state: null,
        country: null,
        isGpsVerified: isGps,
        status: isGps ? "granted" : "manual",
        errorMessage: null,
      };
      setLocation(initialLoc);

      try {
        const geo = await reverseGeocodeCoords(lat, lon, activeToken);
        if (geo?.place_name) placeName = geo.place_name;
        if (geo?.locality) locality = geo.locality;
        if (geo?.city) cityName = geo.city;
        if (geo?.district) districtName = geo.district;
        if (geo?.state) stateName = geo.state;
        if (geo?.country) countryName = geo.country;
      } catch {
        // Fallback gracefully
        if (!placeName) placeName = `${lat.toFixed(4)}°N, ${lon.toFixed(4)}°E`;
        if (!locality) locality = `${lat.toFixed(4)}°N, ${lon.toFixed(4)}°E`;
      } finally {
        setIsGeocodingLoading(false);
      }

      const finalLoc: UserLocationState = {
        latitude: lat,
        longitude: lon,
        placeName: placeName || `${lat.toFixed(4)}°N, ${lon.toFixed(4)}°E`,
        locality: locality || `${lat.toFixed(4)}°N, ${lon.toFixed(4)}°E`,
        city: cityName,
        district: districtName,
        state: stateName,
        country: countryName,
        isGpsVerified: isGps,
        status: isGps ? "granted" : "manual",
        errorMessage: null,
      };

      setLocation(finalLoc);
      if (typeof window !== "undefined") {
        try {
          sessionStorage.setItem(LOCATION_STORAGE_KEY, JSON.stringify(finalLoc));
        } catch {}
      }

      fetchWeatherForLocation(lat, lon);
    },
    [fetchWeatherForLocation, getEffectiveToken]
  );

  // Request browser geolocation via navigator.geolocation
  const requestLocation = useCallback(() => {
    if (typeof window === "undefined" || !navigator.geolocation) {
      setLocation((prev) => ({
        ...prev,
        status: "unavailable",
        errorMessage: "Browser geolocation is not supported in this environment.",
      }));
      return;
    }

    setLocation((prev) => ({ ...prev, status: "detecting", errorMessage: null }));

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const lat = position.coords.latitude;
        const lon = position.coords.longitude;
        updateLocationWithCoords(lat, lon, true);
      },
      (error) => {
        let msg = "Location request denied or unavailable.";
        let st: UserLocationState["status"] = "unavailable";
        if (error.code === error.PERMISSION_DENIED) {
          msg = "Geolocation permission was denied by the browser.";
          st = "denied";
        } else if (error.code === error.TIMEOUT) {
          msg = "Geolocation request timed out.";
          st = "unavailable";
        }
        setLocation((prev) => ({
          ...prev,
          status: st,
          errorMessage: msg,
        }));
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
    );
  }, [updateLocationWithCoords]);

  // Set manual coordinates fallback
  const setManualLocation = useCallback(
    (lat: number, lon: number, localityName?: string) => {
      updateLocationWithCoords(lat, lon, false, localityName);
    },
    [updateLocationWithCoords]
  );

  // Refresh weather on demand
  const refreshWeather = useCallback(() => {
    if (location.latitude !== null && location.longitude !== null) {
      fetchWeatherForLocation(location.latitude, location.longitude, forecastHorizon);
    }
  }, [location.latitude, location.longitude, forecastHorizon, fetchWeatherForLocation]);

  // Handle forecast horizon changes
  const handleSetForecastHorizon = useCallback(
    (days: 7 | 14) => {
      setForecastHorizon(days);
      if (location.latitude !== null && location.longitude !== null) {
        fetchWeatherForLocation(location.latitude, location.longitude, days);
      }
    },
    [location.latitude, location.longitude, fetchWeatherForLocation]
  );

  // Restore cached location or auto-request on initial mount only
  useEffect(() => {
    if (hasRequestedLocationRef.current) return;
    hasRequestedLocationRef.current = true;

    if (typeof window !== "undefined") {
      try {
        const cached = sessionStorage.getItem(LOCATION_STORAGE_KEY);
        if (cached) {
          const parsed: UserLocationState = JSON.parse(cached);
          if (parsed.latitude && parsed.longitude) {
            setLocation(parsed);
            fetchWeatherForLocation(parsed.latitude, parsed.longitude);
            return;
          }
        }
      } catch {}
    }

    // Auto-request location once upon entry/login
    requestLocation();
  }, [fetchWeatherForLocation, requestLocation]);

  return (
    <UserLocationContext.Provider
      value={{
        location,
        weather,
        forecast,
        forecastHorizon,
        isWeatherLoading,
        isForecastLoading,
        isGeocodingLoading,
        weatherError,
        forecastError,
        requestLocation,
        setManualLocation,
        setForecastHorizon: handleSetForecastHorizon,
        refreshWeather,
      }}
    >
      {children}
    </UserLocationContext.Provider>
  );
};

export const useUserLocation = () => {
  const context = useContext(UserLocationContext);
  if (!context) {
    throw new Error("useUserLocation must be used within a UserLocationProvider");
  }
  return context;
};
