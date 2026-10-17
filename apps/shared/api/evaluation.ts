/**
 * Model Evaluation & Ground-Truth Validation API client.
 * Expert and Admin access only. Never call from farmer context.
 */

import { apiClient } from "./client";
import { CropOutcomeResponse, EvaluationReadinessResponse, ModelEvaluationReport } from "../types";

export async function getModelEvaluation(token: string): Promise<ModelEvaluationReport> {
  return apiClient<ModelEvaluationReport>("/api/v1/experts/model-evaluation", {
    method: "GET",
    token,
  });
}

export async function getEvaluationReadiness(token: string): Promise<EvaluationReadinessResponse> {
  return apiClient<EvaluationReadinessResponse>("/api/v1/experts/evaluation-readiness", {
    method: "GET",
    token,
  });
}

export async function verifyCropOutcomeExpert(
  cropId: string,
  payload: { action: "verify" | "reject"; verification_notes?: string },
  farmId?: string,
  token?: string
): Promise<CropOutcomeResponse> {
  const query = farmId ? `?farm_id=${encodeURIComponent(farmId)}` : "";
  return apiClient<CropOutcomeResponse>(`/api/v1/experts/crops/${cropId}/verify-outcome${query}`, {
    method: "POST",
    body: JSON.stringify(payload),
    token,
  });
}
