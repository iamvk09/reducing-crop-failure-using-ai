import { apiClient } from "./client";

export interface NeuroFuzzyRuleExplanation {
  rule_index: number;
  rule_name: string;
  description: string;
  firing_strength: number;
  normalized_weight: number;
  consequent_score: number;
  rule_contribution: number;
  antecedent_memberships: Record<string, number>;
}

export interface NeuroFuzzyPredictionResponse {
  model_version: string;
  model_type: string;
  risk_score: number;
  risk_percentage: string;
  risk_band: "Low" | "Medium" | "High";
  failure_predicted: boolean;
  threshold: number;
  dominant_rule: NeuroFuzzyRuleExplanation;
  activated_rules: NeuroFuzzyRuleExplanation[];
  calibrated_probability: number;
  production_model_comparison?: Record<string, any> | null;
  feature_provenance: Record<string, number>;
  disclaimer: string;
}

export interface NeuroFuzzyStatusResponse {
  is_available: boolean;
  version: string;
  n_rules: number;
  optimal_threshold: number;
  feature_names: string[];
  training_metadata: Record<string, any>;
  comparison_summary: Array<Record<string, any>>;
}

export interface NeuroFuzzyPredictionRequest {
  rainfall: number;
  temperature: number;
  humidity: number;
  soil_moisture: number;
  ndvi_flowering: number;
  water_stress: number;
  pest_risk: number;
  suitability_score: number;
  farm_id?: string;
  crop?: string;
}

export async function getNeuroFuzzyStatus(token?: string | null): Promise<NeuroFuzzyStatusResponse> {
  return apiClient<NeuroFuzzyStatusResponse>("/api/v1/experimental/neuro-fuzzy/status", {
    token: token || undefined,
  });
}

export async function predictNeuroFuzzy(
  payload: NeuroFuzzyPredictionRequest,
  token?: string | null
): Promise<NeuroFuzzyPredictionResponse> {
  return apiClient<NeuroFuzzyPredictionResponse>("/api/v1/experimental/neuro-fuzzy/predict", {
    method: "POST",
    body: JSON.stringify(payload),
    token: token || undefined,
  });
}

export async function getNeuroFuzzyComparison(token?: string | null): Promise<Array<Record<string, any>>> {
  return apiClient<Array<Record<string, any>>>("/api/v1/experimental/neuro-fuzzy/comparison", {
    token: token || undefined,
  });
}
