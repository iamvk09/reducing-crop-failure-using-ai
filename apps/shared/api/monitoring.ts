/**
 * Closed-loop farm risk monitoring, feedback, and outcome API client.
 */

import { apiClient } from "./client";
import {
  CropOutcomeRequest,
  CropOutcomeResponse,
  FarmFeedbackRequest,
  FarmFeedbackResponse,
  FarmMonitoringResponse,
  MonitoringDiagnosticsResponse,
  RiskTrendResponse,
} from "../types";

export async function getFarmMonitoring(
  farmId: string,
  token: string
): Promise<FarmMonitoringResponse> {
  return apiClient<FarmMonitoringResponse>(`/api/v1/farms/${farmId}/monitoring`, {
    method: "GET",
    token,
  });
}

export async function getFarmRiskTrend(
  farmId: string,
  token: string
): Promise<RiskTrendResponse> {
  return apiClient<RiskTrendResponse>(`/api/v1/farms/${farmId}/predictions/trend`, {
    method: "GET",
    token,
  });
}

export async function logFarmFeedback(
  farmId: string,
  payload: FarmFeedbackRequest,
  token: string
): Promise<FarmFeedbackResponse> {
  return apiClient<FarmFeedbackResponse>(`/api/v1/farms/${farmId}/feedback`, {
    method: "POST",
    body: JSON.stringify(payload),
    token,
  });
}

export async function listFarmFeedback(
  farmId: string,
  token: string,
  limit: number = 50
): Promise<FarmFeedbackResponse[]> {
  return apiClient<FarmFeedbackResponse[]>(
    `/api/v1/farms/${farmId}/feedback?limit=${limit}`,
    {
      method: "GET",
      token,
    }
  );
}

export async function recordCropOutcome(
  farmId: string,
  cropId: string,
  payload: CropOutcomeRequest,
  token: string
): Promise<CropOutcomeResponse> {
  return apiClient<CropOutcomeResponse>(
    `/api/v1/farms/${farmId}/crops/${cropId}/outcome`,
    {
      method: "POST",
      body: JSON.stringify(payload),
      token,
    }
  );
}

export async function getCropOutcome(
  farmId: string,
  cropId: string,
  token: string
): Promise<CropOutcomeResponse | null> {
  return apiClient<CropOutcomeResponse | null>(
    `/api/v1/farms/${farmId}/crops/${cropId}/outcome`,
    {
      method: "GET",
      token,
    }
  );
}

export async function getMonitoringDiagnostics(
  farmId: string,
  token: string
): Promise<MonitoringDiagnosticsResponse> {
  return apiClient<MonitoringDiagnosticsResponse>(
    `/api/v1/farms/${farmId}/diagnostics`,
    {
      method: "GET",
      token,
    }
  );
}

