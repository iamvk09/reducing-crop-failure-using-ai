/**
 * Common TypeScript domain models matching FastAPI backend schemas.
 */

export type UserRole = "farmer" | "expert" | "admin";

export type RiskLevel = "Low" | "Medium" | "High";

export interface UserProfile {
  id: string;
  email: string | null;
  full_name: string | null;
  role: UserRole;
  phone_number?: string | null;
  preferred_language: string;
  sms_notifications_enabled?: boolean;
  sms_consent_timestamp?: string | null;
  whatsapp_notifications_enabled?: boolean;
  whatsapp_consent_timestamp?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface UserProfileUpdateRequest {
  full_name?: string;
  phone_number?: string;
  preferred_language?: string;
  sms_notifications_enabled?: boolean;
  whatsapp_notifications_enabled?: boolean;
}

export interface Farm {
  id: string;
  user_id: string;
  name: string;
  state: string;
  district: string;
  region?: string | null;
  latitude: number;
  longitude: number;
  area_hectares?: number | null;
  village?: string | null;
  soil_type?: string | null;
  irrigation_level?: string | null;
  boundary_geojson?: Record<string, any> | null;
  created_at: string;
  updated_at: string;
}

export interface FarmCreateRequest {
  name: string;
  state: string;
  district: string;
  latitude: number;
  longitude: number;
  area_hectares?: number | null;
  village?: string | null;
  region?: string | null;
  soil_type?: string | null;
  irrigation_level?: string | null;
  boundary_geojson?: Record<string, any> | null;
}

export interface FarmUpdateRequest {
  name?: string;
  latitude?: number;
  longitude?: number;
  area_hectares?: number | null;
  village?: string | null;
  soil_type?: string | null;
  irrigation_level?: string | null;
  boundary_geojson?: Record<string, any> | null;
}

export interface FarmCrop {
  id: string;
  farm_id: string;
  crop: string;
  season: string;
  soil_type?: string | null;
  irrigation_level?: string | null;
  sowing_date?: string | null;
  expected_harvest_date?: string | null;
  growth_stage?: string | null;
  status: "active" | "harvested" | "failed" | string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CropCreateRequest {
  crop: string;
  season: string;
  soil_type?: string | null;
  irrigation_level?: string | null;
  sowing_date?: string | null;
  expected_harvest_date?: string | null;
  growth_stage?: string | null;
  status?: string;
}

export interface CropUpdateRequest {
  crop?: string;
  season?: string;
  soil_type?: string | null;
  irrigation_level?: string | null;
  sowing_date?: string | null;
  expected_harvest_date?: string | null;
  growth_stage?: string | null;
  status?: string;
  is_active?: boolean;
}

export interface CurrentWeatherResponse {
  success: boolean;
  farm_id?: string | null;
  latitude: number;
  longitude: number;
  timestamp: string;
  timezone: string;
  temperature?: number | null;
  relative_humidity?: number | null;
  precipitation?: number | null;
  wind_speed_10m?: number | null;
  soil_moisture_m3m3?: number | null;
  soil_moisture_percentage?: number | null;
  weather_code?: number | null;
  source: string;
  is_forecast: boolean;
  is_estimate: boolean;
  is_cached: boolean;
  precipitation_sum_7d?: number | null;
  error?: string | null;
}

export interface DailyForecastItem {
  date: string;
  temperature_max?: number | null;
  temperature_min?: number | null;
  precipitation_sum?: number | null;
  precipitation_probability_max?: number | null;
  weather_code?: number | null;
  soil_moisture_mean?: number | null;
}

export interface WeatherForecastResponse {
  success: boolean;
  farm_id?: string | null;
  latitude: number;
  longitude: number;
  timezone: string;
  source: string;
  is_forecast: boolean;
  is_cached: boolean;
  forecast_days: number;
  daily: DailyForecastItem[];
  disclaimer: string;
  error?: string | null;
}

export interface WeatherObservationRecord {
  id: string;
  farm_id: string;
  latitude?: number | null;
  longitude?: number | null;
  observation_time: string;
  temperature_c?: number | null;
  humidity_pct?: number | null;
  precipitation_mm?: number | null;
  soil_moisture_pct?: number | null;
  soil_moisture_m3m3?: number | null;
  weather_code?: number | null;
  source: string;
  is_forecast: boolean;
  created_at: string;
}

export interface WeatherSummary {
  temperature_c: number | null;
  humidity_pct: number | null;
  precipitation_mm: number | null;
  soil_moisture_pct: number | null;
  source: string;
  updated_at: string;
}

export interface RecommendationDetails {
  recommended_crop?: string | null;
  top_options?: Array<{ crop: string; probability: number; percentage: string }>;
  advisory_summary?: string;
}

export interface FarmPredictionRequest {
  crop_id?: string;
  rainfall_override?: number;
  temperature_override?: number;
  humidity_override?: number;
  soil_moisture_override?: number;
  ndvi_override?: number;
  water_stress_override?: number;
  pest_risk_override?: number;
  suitability_score_override?: number;
  yield_index_override?: number;
}

export interface PredictionRequest {
  farm_id?: string;
  crop_id?: string;
  state: string;
  district: string;
  crop: string;
  season: string;
  soil_type?: string;
  irrigation_level?: string;
  rainfall_override?: number;
  temperature_override?: number;
  humidity_override?: number;
  soil_moisture_override?: number;
  ndvi_override?: number;
  water_stress_override?: number;
  pest_risk_override?: number;
  suitability_score_override?: number;
  yield_index_override?: number;
}

export interface PredictionDataQuality {
  live_feature_count: number;
  baseline_feature_count: number;
  derived_feature_count: number;
  total_feature_count: number;
  live_feature_percentage: number;
  satellite_status: "live_fresh" | "stage_deferred" | "stale_fallback" | "baseline" | string;
  weather_status: "live_fresh" | "live_cached" | "stale_fallback" | "baseline" | string;
  summary_label?: string;
}

export interface ShapFeatureContribution {
  feature_name: string;
  display_name: string;
  feature_value: any;
  formatted_value: string;
  attribution_value: number;
  abs_attribution: number;
  direction: "increases_risk" | "reduces_risk" | "neutral" | string;
  direction_label: string;
  farmer_text: string;
  provenance_source?: string | null;
  is_live: boolean;
  is_baseline: boolean;
  freshness_status?: string | null;
}

export interface PredictionExplanation {
  explainer_type: string;
  output_space: string;
  base_value: number;
  sum_shap: number;
  margin_value: number;
  top_risk_increasing: ShapFeatureContribution[];
  top_risk_reducing: ShapFeatureContribution[];
  all_features: ShapFeatureContribution[];
  summary_narrative: string;
  disclaimer: string;
}

export interface PredictionResponse {
  prediction_id?: string | null;
  farm_id?: string | null;
  crop_id?: string | null;
  crop: string;
  district: string;
  state: string;
  season: string;
  risk_probability: number;
  risk_percentage: string;
  risk_level: RiskLevel;
  prediction_class: number;
  best_model_name: string;
  global_risk?: number | null;
  region_risk?: number | null;
  crop_risk?: number | null;
  consensus_risk?: number | null;
  input_features: Record<string, any>;
  provenance: Record<string, string>;
  data_quality?: PredictionDataQuality | null;
  explanation?: PredictionExplanation | null;
  weather_data?: Record<string, any> | null;
  recommendations?: RecommendationDetails | null;
  disclaimer: string;
  created_at: string;
}

export interface ScenarioSimulationRequest {
  scenario_name: string;
  updates: Record<string, number>;
}

export interface ScenarioSimulationResponse {
  scenario: string;
  risk_score: number;
  risk_percentage: string;
  adjusted_features: {
    Rainfall: number;
    Temperature: number;
    Humidity: number;
    SoilMoisture: number;
    NDVI_Flowering: number;
    WaterStress: number;
  };
}

export interface ShapFeatureItem {
  feature: string;
  display_name: string;
  impact: number;
  abs_impact: number;
  direction: "increases_risk" | "reduces_risk" | "neutral" | string;
}

export interface ShapExplanationResponse {
  explainer_type: string;
  summary: string;
  top_features: ShapFeatureItem[];
}

export type SatelliteObservationStatus =
  | "REAL_SATELLITE_DATA"
  | "SATELLITE_PENDING"
  | "SATELLITE_NOT_CONFIGURED"
  | "SATELLITE_NO_VALID_OBSERVATION"
  | "SATELLITE_ERROR"
  | "MOCK_DEVELOPMENT";

export interface NDVIStatistics {
  mean?: number | null;
  median?: number | null;
  min?: number | null;
  max?: number | null;
  std?: number | null;
  valid_pixel_percent?: number | null;
  scene_cloud_percent?: number | null;
  cloud_percent?: number | null;
  total_pixels?: number | null;
  valid_pixels?: number | null;
}

export interface SatelliteObservationResponse {
  success: boolean;
  status: SatelliteObservationStatus;
  farm_id?: string | null;
  observation_date?: string | null;
  ndvi?: NDVIStatistics | null;
  source: string;
  provider: string;
  satellite: string;
  product: string;
  geometry_type: string;
  quality_status: string;
  disclaimer: string;
  raw_metadata?: Record<string, any>;
  is_cached: boolean;
  error?: string | null;
  created_at: string;
}

export interface SatelliteHistoryResponse {
  farm_id: string;
  total_count: number;
  observations: SatelliteObservationResponse[];
}

export interface FarmVegetationSummary {
  farm_id: string;
  has_observation: boolean;
  status: SatelliteObservationStatus;
  vegetation_health: string;
  latest_ndvi?: number | null;
  observation_date?: string | null;
  valid_pixel_percent?: number | null;
  scene_cloud_percent?: number | null;
  data_source: string;
  quality_label: string;
  message: string;
  disclaimer: string;
}

export interface RiskTrend {
  current_risk_probability: number;
  previous_risk_probability?: number | null;
  risk_delta_percentage_points?: number | null;
  trend_direction: "increasing" | "decreasing" | "stable" | "insufficient_history";
  trend_label: string;
  trend_description: string;
  assessment_count: number;
  current_prediction_id?: string | null;
  previous_prediction_id?: string | null;
  current_prediction_timestamp?: string | null;
  previous_prediction_timestamp?: string | null;
}

export interface TelemetryChangeItem {
  feature_name: string;
  display_name: string;
  current_value: any;
  previous_value: any;
  delta?: number | null;
  formatted_current?: string;
  formatted_previous?: string;
  unit?: string;
  change_type: string;
  direction?: string;
  statement?: string;
  description: string;
  observation_time_current?: string | null;
  observation_time_previous?: string | null;
}

export interface ShapAttributionShiftItem {
  feature_name: string;
  display_name: string;
  current_attribution: number;
  previous_attribution: number;
  delta_attribution: number;
  shift_direction: "increased_risk_impact" | "reduced_risk_impact" | "stable_impact";
  farmer_text: string;
}

export interface ShapTrendComparison {
  newly_increasing: ShapAttributionShiftItem[];
  newly_reducing: ShapAttributionShiftItem[];
  all_shifts: ShapAttributionShiftItem[];
  summary: string;
}

export interface FarmFeedbackRequest {
  action_type:
    | "recommendation_viewed"
    | "recommendation_acknowledged"
    | "irrigation_applied"
    | "fertilizer_applied"
    | "pest_control_applied"
    | "farmer_note";
  prediction_id?: string | null;
  notes?: string;
  action_date?: string | null;
}

export interface FarmFeedbackResponse {
  id: string;
  farm_id: string;
  user_id: string;
  prediction_id?: string | null;
  action_type: string;
  action_label: string;
  notes?: string;
  action_date: string;
  created_at: string;
}

export interface CropOutcomeRequest {
  crop_status: "active" | "harvested" | "failed";
  actual_harvest_date?: string | null;
  reported_yield_kg_per_ha?: number | null;
  outcome_notes?: string | null;
}

export interface CropOutcomeResponse {
  crop_id: string;
  farm_id: string;
  crop: string;
  season: string;
  status: string;
  actual_harvest_date?: string | null;
  reported_yield_kg_per_ha?: number | null;
  outcome_notes?: string | null;
  recorded_at: string;
}

export interface RiskTrendResponse {
  farm_id: string;
  risk_trend: RiskTrend;
  telemetry_changes: TelemetryChangeItem[];
  shap_comparison?: ShapTrendComparison | null;
  telemetry_summary: string;
}

export interface FarmAlert {
  id: string;
  alert_id?: string;
  farm_id: string;
  crop_id?: string | null;
  created_at: string;
  alert_type: string;
  severity: "info" | "warning" | "critical";
  status: "active" | "acknowledged" | "resolved";
  trigger_reason: string;
  prediction_id?: string | null;
  risk_probability: number;
  risk_percentage?: string;
  previous_risk_probability?: number | null;
  risk_delta_pp?: number | null;
  recommended_action?: {
    title: string;
    priority?: string;
    action_items?: string[];
    summary?: string;
  } | null;
  shap_context?: {
    summary?: string;
    explainer_type?: string;
    top_contributors?: Array<{
      feature_name: string;
      display_name?: string;
      shap_value: number;
      feature_value?: any;
      direction?: string;
    }>;
  } | null;
  acknowledged_at?: string | null;
  acknowledged_by?: string | null;
  resolved_at?: string | null;
  resolved_by?: string | null;
  resolution_notes?: string | null;
}

export interface FarmMonitoringResponse {
  farm_id: string;
  farm_name: string;
  district: string;
  state: string;
  active_crop?: string | null;
  growth_stage?: string | null;
  monitoring_status: "optimal" | "active" | "attention_needed" | "insufficient_history";
  status_reason: string;
  latest_prediction?: PredictionResponse | null;
  previous_prediction?: PredictionResponse | null;
  risk_trend: RiskTrend;
  telemetry_changes: TelemetryChangeItem[];
  shap_comparison?: ShapTrendComparison | null;
  telemetry_freshness?: PredictionDataQuality | null;
  latest_satellite_date?: string | null;
  latest_weather_timestamp?: string | null;
  latest_recommendations?: RecommendationDetails | null;
  recent_actions: FarmFeedbackResponse[];
  crop_outcome?: CropOutcomeResponse | null;
  active_alert_count?: number;
  unacknowledged_alert_count?: number;
  highest_active_severity?: "info" | "warning" | "critical" | null;
  latest_alert?: FarmAlert | null;
  last_evaluated_at: string;
}

export interface MonitoringDiagnosticsResponse {
  total_predictions: number;
  farm_count: number;
  risk_distribution: Record<string, number>;
  average_live_feature_coverage: number;
  fallback_frequency: Record<string, number>;
  stale_telemetry_rate: number;
  shap_availability_rate: number;
  feedback_count: number;
  outcomes_recorded_count: number;
  total_alerts?: number;
  active_alerts?: number;
  acknowledged_alerts?: number;
  resolved_alerts?: number;
  alerts_by_severity?: Record<string, number>;
  alerts_by_type?: Record<string, number>;
  alert_deduplication_count?: number;
  stale_data_alerts_count?: number;
  disclaimer: string;
}

// ---------------------------------------------------------------------------
// Model Evaluation & Ground-Truth Validation types (Milestone 11)
// Expert/Admin access only — never display to farmers.
// ---------------------------------------------------------------------------

export interface ConfusionMatrix {
  true_positive: number;
  false_positive: number;
  true_negative: number;
  false_negative: number;
  total: number;
}

export interface ClassificationMetrics {
  n_eligible_pairs: number;
  accuracy?: number | null;
  precision?: number | null;
  recall?: number | null;
  f1_score?: number | null;
  specificity?: number | null;
  false_positive_rate?: number | null;
  false_negative_rate?: number | null;
  roc_auc?: number | null;
  pr_auc?: number | null;
  brier_score?: number | null;
  confusion_matrix?: ConfusionMatrix | null;
  threshold_used: number;
  notes?: string | null;
}

export interface CalibrationBin {
  bin_lower: number;
  bin_upper: number;
  bin_center: number;
  predicted_mean_probability: number;
  actual_fraction_positive: number;
  n_samples: number;
  calibration_gap: number;
}

export interface SubgroupMetrics {
  subgroup_key: string;
  subgroup_value: string;
  n_pairs: number;
  accuracy?: number | null;
  precision?: number | null;
  recall?: number | null;
  f1_score?: number | null;
  roc_auc?: number | null;
  false_positive_rate?: number | null;
  false_negative_rate?: number | null;
  notes?: string | null;
}

export interface ShapErrorRecord {
  prediction_id: string;
  error_type: "false_positive" | "false_negative";
  ground_truth_label: number;
  predicted_class: number;
  risk_probability: number;
  top_shap_contributors: Array<{
    feature_name?: string;
    display_name?: string;
    shap_value?: number;
    feature_value?: any;
    direction?: string;
    formatted_value?: string;
  }>;
  disclaimer: string;
}

export interface DataLeakageAudit {
  feature_name: string;
  leakage_risk: "none" | "low" | "medium" | "high";
  reason: string;
  training_source?: string | null;
  live_source?: string | null;
  provenance_type?: "LIVE" | "DERIVED" | "BASELINE" | string;
  recommendation?: string | null;
}

export interface TrainTestProvenanceRecord {
  dataset_file: string;
  total_rows: number;
  feature_count: number;
  target_column: string;
  class_distribution: Record<string, number>;
  class_balance_ratio: number;
  test_size: number;
  test_rows: number;
  train_rows: number;
  random_state: number;
  stratified: boolean;
  model_selection_metric: string;
  best_model_name: string;
  best_model_roc_auc: number;
  best_model_f1: number;
  all_model_results: Array<{ model_name: string; roc_auc: number; f1_score: number }>;
}

export interface ModelVersionRecord {
  artifact_file: string;
  best_model_name: string;
  models_in_bundle: string[];
  feature_count: number;
  numeric_features: string[];
  categorical_features: string[];
  target_column: string;
  training_dataset_rows?: number | null;
  training_roc_auc?: number | null;
  training_f1?: number | null;
  note: string;
}

export interface ModelEvaluationReport {
  report_generated_at: string;
  evaluation_period_label: string;
  total_predictions_in_db: number;
  total_crop_cycles_with_outcome: number;
  eligible_pair_count: number;
  ineligible_pair_count: number;
  eligibility_filter_rules: string[];
  metrics?: ClassificationMetrics | null;
  calibration_bins: CalibrationBin[];
  calibration_note?: string | null;
  subgroup_analysis: SubgroupMetrics[];
  subgroup_analysis_note?: string | null;
  lead_time_groups: SubgroupMetrics[];
  lead_time_analysis_note?: string | null;
  false_positive_examples: ShapErrorRecord[];
  false_negative_examples: ShapErrorRecord[];
  shap_error_analysis_note: string;
  leakage_audit: DataLeakageAudit[];
  train_test_provenance?: TrainTestProvenanceRecord | null;
  model_version?: ModelVersionRecord | null;
  disclaimer: string;
}

// ---------------------------------------------------------------------------
// Milestone 12: Evaluation Readiness & Outcome Verification Types
// ---------------------------------------------------------------------------

export interface PendingEvaluationCropItem {
  farm_id: string;
  farm_name: string;
  crop_id: string;
  crop: string;
  season: string;
  status: string;
  sowing_date?: string | null;
  expected_harvest_date?: string | null;
  prediction_count: number;
  earliest_prediction_date?: string | null;
  latest_prediction_date?: string | null;
  readiness_status: string;
}

export interface OutcomeVerificationQueueItem {
  farm_id: string;
  farm_name: string;
  crop_id: string;
  crop: string;
  season: string;
  status: string;
  actual_harvest_date?: string | null;
  reported_yield_kg_per_ha?: number | null;
  outcome_notes?: string | null;
  recorded_at?: string | null;
  prediction_count: number;
  potential_eligible_pairs_count: number;
  verification_status: "pending" | "verified" | "synthetic" | "invalid" | string;
  is_verified_ground_truth: boolean;
  is_synthetic: boolean;
  verified_by?: string | null;
  verified_at?: string | null;
  verification_notes?: string | null;
}

export interface EvaluationReadinessSummary {
  total_predictions: number;
  total_crop_cycles: number;
  predictions_awaiting_outcome: number;
  crop_cycles_awaiting_outcome: number;
  verified_outcomes: number;
  unverified_outcomes: number;
  synthetic_outcomes: number;
  invalid_outcomes: number;
  eligible_prediction_outcome_pairs: number;
  ineligible_predictions: number;
  evaluation_coverage_percentage: number;
  coverage_definition: string;
}

export interface EvaluationReadinessResponse {
  report_generated_at: string;
  summary: EvaluationReadinessSummary;
  pending_queue: PendingEvaluationCropItem[];
  verification_queue: OutcomeVerificationQueueItem[];
  exclusions_breakdown: Record<string, number>;
  average_lead_time_days?: number | null;
  lead_time_distribution: Record<string, number>;
  model_version_breakdown: Record<string, number>;
  disclaimer: string;
}

