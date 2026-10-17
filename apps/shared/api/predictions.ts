/**
 * Crop failure risk prediction API client.
 */

import { apiClient } from "./client";
import {
  FarmPredictionRequest,
  PredictionRequest,
  PredictionResponse,
} from "../types";

export async function predictForFarm(
  farmId: string,
  payload: FarmPredictionRequest = {},
  token: string
): Promise<PredictionResponse> {
  return apiClient<PredictionResponse>(`/api/v1/farms/${farmId}/predictions`, {
    method: "POST",
    body: JSON.stringify(payload),
    token,
  });
}

export async function listFarmPredictions(
  farmId: string,
  token: string
): Promise<PredictionResponse[]> {
  return apiClient<PredictionResponse[]>(`/api/v1/farms/${farmId}/predictions`, {
    method: "GET",
    token,
  });
}

export async function getPrediction(
  predictionId: string,
  token: string
): Promise<PredictionResponse> {
  return apiClient<PredictionResponse>(`/api/v1/predictions/${predictionId}`, {
    method: "GET",
    token,
  });
}

export async function listMyPredictions(
  token: string,
  limit: number = 50,
  offset: number = 0
): Promise<PredictionResponse[]> {
  return apiClient<PredictionResponse[]>(`/api/v1/predictions/history?limit=${limit}&offset=${offset}`, {
    method: "GET",
    token,
  });
}
