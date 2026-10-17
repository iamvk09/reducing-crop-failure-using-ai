/**
 * Weather API Client Functions.
 */

import { apiClient } from "./client";
import {
  CurrentWeatherResponse,
  WeatherForecastResponse,
  WeatherObservationRecord,
} from "../types";

export async function getCurrentWeather(
  farmId: string,
  token: string
): Promise<CurrentWeatherResponse> {
  return apiClient<CurrentWeatherResponse>(
    `/api/v1/farms/${farmId}/weather/current`,
    {
      method: "GET",
      token,
    }
  );
}

export async function getForecast(
  farmId: string,
  token: string,
  days: number = 7
): Promise<WeatherForecastResponse> {
  return apiClient<WeatherForecastResponse>(
    `/api/v1/farms/${farmId}/weather/forecast?days=${days}`,
    {
      method: "GET",
      token,
    }
  );
}

export const getWeatherForecast = getForecast;

export async function getWeatherHistory(
  farmId: string,
  token: string,
  limit: number = 50,
  offset: number = 0
): Promise<WeatherObservationRecord[]> {
  return apiClient<WeatherObservationRecord[]>(
    `/api/v1/farms/${farmId}/weather/history?limit=${limit}&offset=${offset}`,
    {
      method: "GET",
      token,
    }
  );
}

export async function getCurrentWeatherByCoords(
  latitude: number,
  longitude: number,
  token: string
): Promise<CurrentWeatherResponse> {
  return apiClient<CurrentWeatherResponse>(
    `/api/v1/weather/current?latitude=${latitude}&longitude=${longitude}`,
    {
      method: "GET",
      token,
    }
  );
}

export async function getForecastByCoords(
  latitude: number,
  longitude: number,
  token: string,
  days: number = 7
): Promise<WeatherForecastResponse> {
  return apiClient<WeatherForecastResponse>(
    `/api/v1/weather/forecast?latitude=${latitude}&longitude=${longitude}&days=${days}`,
    {
      method: "GET",
      token,
    }
  );
}

export interface ReverseGeocodeResult {
  success: boolean;
  latitude: number;
  longitude: number;
  place_name: string;
  locality: string;
  city?: string;
  district?: string;
  state: string;
  country?: string;
  display_name: string;
  provider?: string;
}

export async function reverseGeocodeCoords(
  latitude: number,
  longitude: number,
  token: string
): Promise<ReverseGeocodeResult> {
  return apiClient<ReverseGeocodeResult>(
    `/api/v1/weather/reverse-geocode?latitude=${latitude}&longitude=${longitude}`,
    {
      method: "GET",
      token,
    }
  );
}


