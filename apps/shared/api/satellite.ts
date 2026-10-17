/**
 * Satellite and Vegetation Health API Client Functions.
 */

import { apiClient } from "./client";
import {
  SatelliteObservationResponse,
  SatelliteHistoryResponse,
  FarmVegetationSummary,
} from "../types";

export async function getLatestSatelliteObservation(
  farmId: string,
  token: string
): Promise<SatelliteObservationResponse> {
  return apiClient<SatelliteObservationResponse>(
    `/api/v1/farms/${farmId}/satellite/latest`,
    {
      method: "GET",
      token,
    }
  );
}

export async function getSatelliteHistory(
  farmId: string,
  token: string,
  limit: number = 30,
  offset: number = 0
): Promise<SatelliteObservationResponse[]> {
  const res = await apiClient<SatelliteHistoryResponse | SatelliteObservationResponse[]>(
    `/api/v1/farms/${farmId}/satellite/history?limit=${limit}&offset=${offset}`,
    {
      method: "GET",
      token,
    }
  );
  if (Array.isArray(res)) {
    return res;
  }
  return res.observations || [];
}

export async function getFarmVegetationSummary(
  farmId: string,
  token: string
): Promise<FarmVegetationSummary> {
  return apiClient<FarmVegetationSummary>(
    `/api/v1/farms/${farmId}/vegetation`,
    {
      method: "GET",
      token,
    }
  );
}
