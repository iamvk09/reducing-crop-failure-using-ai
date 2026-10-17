/**
 * Expert analytics and Digital Twin API functions.
 */

import { apiClient } from "./client";
import {
  ScenarioSimulationRequest,
  ScenarioSimulationResponse,
  ShapExplanationResponse,
} from "../types";

export async function simulateScenario(
  payload: ScenarioSimulationRequest,
  params: { district: string; crop: string; season?: string },
  token: string
): Promise<ScenarioSimulationResponse> {
  const query = new URLSearchParams({
    district: params.district,
    crop: params.crop,
    season: params.season || "Kharif",
  }).toString();

  return apiClient<ScenarioSimulationResponse>(
    `/api/v1/experts/simulate?${query}`,
    {
      method: "POST",
      body: JSON.stringify(payload),
      token,
    }
  );
}

export async function explainPrediction(
  params: { district: string; crop: string; season?: string },
  token: string
): Promise<ShapExplanationResponse> {
  const query = new URLSearchParams({
    district: params.district,
    crop: params.crop,
    season: params.season || "Kharif",
  }).toString();

  return apiClient<ShapExplanationResponse>(
    `/api/v1/experts/explain?${query}`,
    {
      method: "POST",
      token,
    }
  );
}
