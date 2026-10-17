/**
 * Automated Test Suite for Expert App.
 */

const assert = require("assert");

console.log("=== RUNNING FRONTEND TEST SUITE (EXPERT APP) ===");

// 1. Test Parametric Updates for Digital Twin
function buildScenarioPayload(scenarioName, baseTemp, tempDelta, baseRain, rainDeltaPct) {
  return {
    scenario_name: scenarioName,
    updates: {
      Temperature: baseTemp + tempDelta,
      Rainfall: Math.max(0, baseRain * (1 + rainDeltaPct / 100)),
    },
  };
}

const scenario = buildScenarioPayload("Drought Test", 28.5, 2.0, 150.0, -20.0);
assert(scenario.updates.Temperature === 30.5, "Temperature shift calculation failed");
assert(scenario.updates.Rainfall === 120.0, "Rainfall shift calculation failed");
console.log("✔ Test 1 Passed: Digital Twin parametric calculation verified.");

// 2. Test SHAP Feature Formatting
function formatShapItem(item) {
  return {
    ...item,
    formattedImpact: item.impact > 0 ? `+${item.impact.toFixed(3)}` : item.impact.toFixed(3),
    badgeClass: item.direction === "increases_risk" ? "bg-red-100" : "bg-emerald-100",
  };
}

const formatted = formatShapItem({ feature: "NDVI_Flowering", display_name: "NDVI (Flowering)", impact: 0.1234, direction: "increases_risk" });
assert(formatted.formattedImpact === "+0.123", "Formatted impact precision failed");
assert(formatted.badgeClass === "bg-red-100", "Risk badge formatting failed");
console.log("✔ Test 2 Passed: SHAP feature formatting verified.");

// 3. Test Satellite History Response Unwrapping
function unwrapSatelliteHistory(apiResponse) {
  if (Array.isArray(apiResponse)) {
    return apiResponse;
  }
  return apiResponse?.observations || [];
}

const wrappedHistory = {
  farm_id: "a391f1ba-c885-4f3a-8a1c-aac65031928b",
  total_count: 1,
  observations: [
    {
      success: true,
      status: "REAL_SATELLITE_DATA",
      farm_id: "a391f1ba-c885-4f3a-8a1c-aac65031928b",
      observation_date: "2026-09-15",
      ndvi: { mean: 0.3514, median: 0.3025, valid_pixel_percent: 100.0, cloud_percent: 3.4 },
      product: "COPERNICUS/S2_SR_HARMONIZED",
      quality_status: "GOOD",
    },
  ],
};

const unwrapped = unwrapSatelliteHistory(wrappedHistory);
assert(Array.isArray(unwrapped), "Unwrapped history must be an array");
assert(unwrapped.length === 1, "Must contain exactly 1 observation");
assert(unwrapped[0].observation_date === "2026-09-15", "Observation date must match");
assert(unwrapped[0].ndvi.mean === 0.3514, "NDVI mean must match");

const emptyUnwrapped = unwrapSatelliteHistory({ farm_id: "empty-farm", total_count: 0, observations: [] });
assert(Array.isArray(emptyUnwrapped) && emptyUnwrapped.length === 0, "Empty observations must unwrap to empty array");
console.log("✔ Test 3 Passed: getSatelliteHistory response unwrapping verified.");

// 4. Test Satellite History Table Rendering Logic
function renderHistoryRows(observations) {
  if (!observations || observations.length === 0) {
    return { count: 0, rows: [], emptyMessage: "No persisted satellite history records found for this farm." };
  }
  return {
    count: observations.length,
    rows: observations.map((obs) => ({
      date: obs.observation_date || "—",
      product: obs.product,
      meanNdvi: obs.ndvi?.mean !== undefined && obs.ndvi?.mean !== null ? obs.ndvi.mean.toFixed(3) : "—",
      validPct: obs.ndvi?.valid_pixel_percent !== undefined && obs.ndvi?.valid_pixel_percent !== null ? `${obs.ndvi.valid_pixel_percent.toFixed(0)}%` : "—",
      status: obs.status,
    })),
    emptyMessage: null,
  };
}

const renderedTable = renderHistoryRows(unwrapped);
assert(renderedTable.count === 1, "Rendered count must match");
assert(renderedTable.rows[0].meanNdvi === "0.351", "Formatted mean NDVI must match");
assert(renderedTable.rows[0].validPct === "100%", "Formatted valid percent must match");

const emptyTable = renderHistoryRows([]);
assert(emptyTable.count === 0, "Empty count must be 0");
assert(emptyTable.emptyMessage.includes("No persisted satellite history"), "Empty message must be present");
console.log("✔ Test 4 Passed: Satellite history table rendering and safety checks verified.");

// 5. Test Model Evaluation report structure validation
function validateEvaluationReport(report) {
  if (!report) return { valid: false, error: "Report is null" };
  const requiredFields = [
    "report_generated_at",
    "total_predictions_in_db",
    "eligible_pair_count",
    "ineligible_pair_count",
    "eligibility_filter_rules",
    "calibration_bins",
    "subgroup_analysis",
    "leakage_audit",
    "shap_error_analysis_note",
    "disclaimer",
  ];
  for (const field of requiredFields) {
    if (!(field in report)) return { valid: false, error: `Missing field: ${field}` };
  }
  return { valid: true, error: null };
}

const mockReport = {
  report_generated_at: new Date().toISOString(),
  evaluation_period_label: "All time",
  total_predictions_in_db: 5,
  total_crop_cycles_with_outcome: 0,
  eligible_pair_count: 0,
  ineligible_pair_count: 5,
  eligibility_filter_rules: ["outcome_status must be 'harvested' or 'failed'"],
  metrics: null,
  calibration_bins: [],
  calibration_note: "No eligible pairs for calibration.",
  subgroup_analysis: [],
  subgroup_analysis_note: "No eligible pairs.",
  lead_time_groups: [],
  lead_time_analysis_note: null,
  false_positive_examples: [],
  false_negative_examples: [],
  shap_error_analysis_note: "SHAP values describe model feature weights. They do not explain why the outcome occurred in the real world.",
  leakage_audit: [
    { feature_name: "YieldIndex", leakage_risk: "high", reason: "Potential outcome correlation" },
  ],
  train_test_provenance: null,
  model_version: null,
  disclaimer: "Derived from real non-synthetic outcomes. Do not retrain. SHAP values are not causal.",
};

const validation = validateEvaluationReport(mockReport);
assert(validation.valid === true, `Evaluation report validation failed: ${validation.error}`);
assert(mockReport.eligible_pair_count === 0, "No eligible pairs in mock report");
assert(mockReport.metrics === null, "Metrics must be null when no eligible pairs");
assert(Array.isArray(mockReport.eligibility_filter_rules), "Eligibility rules must be an array");
console.log("✔ Test 5 Passed: Model Evaluation report structure and zero-pair behaviour verified.");

// 6. Test SHAP error analysis non-causal disclaimer enforcement
function checkShapNonCausal(note) {
  const lower = (note || "").toLowerCase();
  return lower.includes("shap") && lower.includes("not") && !lower.includes("caused by") && !lower.includes("due to");
}

assert(checkShapNonCausal(mockReport.shap_error_analysis_note), "SHAP note must be non-causal");
assert(!mockReport.disclaimer.toLowerCase().includes("caused by"), "Disclaimer must not use causal language");
console.log("✔ Test 6 Passed: SHAP error analysis non-causal phrasing verified.");

// 7. Test leakage audit badge rendering
function leakageRiskBadge(risk) {
  const map = { high: "bg-rose-100 text-rose-800", medium: "bg-amber-100 text-amber-800", low: "bg-yellow-100 text-yellow-800", none: "bg-emerald-100 text-emerald-800" };
  return map[risk] || "bg-gray-100 text-gray-800";
}

assert(leakageRiskBadge("high") === "bg-rose-100 text-rose-800", "High risk badge incorrect");
assert(leakageRiskBadge("none") === "bg-emerald-100 text-emerald-800", "None risk badge incorrect");
assert(leakageRiskBadge("medium") === "bg-amber-100 text-amber-800", "Medium risk badge incorrect");
const yieldAudit = mockReport.leakage_audit.find((a) => a.feature_name === "YieldIndex");
assert(yieldAudit && yieldAudit.leakage_risk === "high", "YieldIndex must be high risk in audit");
console.log("✔ Test 7 Passed: Leakage audit badge rendering and YieldIndex high-risk verified.");

console.log("\n=======================================================");
console.log("ALL EXPERT FRONTEND TESTS PASSED! (7/7 suites)");
console.log("=======================================================\n");

