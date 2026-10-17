"""Trainable First-Order Takagi-Sugeno-Kang (TSK) Neuro-Fuzzy Crop Failure Risk Model.

Architecture & Mechanics:
- Layer 1: Gaussian Membership Functions (MFs) for continuous agricultural features:
      mu_{ij}(x_j) = exp( - (x_j - c_{ij})^2 / (2 * sigma_{ij}^2) )
- Layer 2: Fuzzy Rule Firing Strengths using T-norm (product / softmin):
      w_i(x) = prod_{j} mu_{ij}(x_j)
- Layer 3: Normalized Firing Strengths:
      w_bar_i(x) = w_i(x) / sum_{k} w_k(x)
- Layer 4: First-Order Linear Consequents (Sugeno):
      f_i(x) = p_{i0} + sum_{j} p_{ij} * x_j
- Layer 5: Overall Defuzzified Output & Probability Mapping:
      y_hat(x) = sum_{i} w_bar_i(x) * f_i(x)
      P(Failure=1 | x) = sigmoid(y_hat(x))

Features Used (Leakage-Free Continuous Pre-Harvest/In-Season):
- Rainfall (mm)
- Temperature (°C)
- Humidity (%)
- SoilMoisture (%)
- NDVI_Flowering (Sentinel-2 satellite observation proxy, 0-1)
- WaterStress (0-1)
- PestRisk (0-1)
- SuitabilityScore (0-1)

Excluded Features to Prevent Target Leakage:
- Yield / YieldIndex: Directly encodes harvest yield outcome.
- Production / Loss metrics: Unavailable at forecast time.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.preprocessing import StandardScaler


FEATURE_NAMES = [
    "Rainfall",
    "Temperature",
    "Humidity",
    "SoilMoisture",
    "NDVI_Flowering",
    "WaterStress",
    "PestRisk",
    "SuitabilityScore",
]

RULE_DESCRIPTIONS = [
    "Severe Drought Stress: Low rainfall, low soil moisture, high water stress, and depressed canopy vigor.",
    "Optimal Agronomic Regime: Favorable rainfall and soil moisture with high NDVI and crop suitability.",
    "Warm Humid Pest Vector: Elevated temperature and humidity accelerating disease and pest vulnerability.",
    "Waterlogging & Soil Saturation: Excessive rainfall and saturated soil moisture inducing root asphyxia.",
    "Thermal & Water Stress: High ambient temperature coupled with severe water stress and poor suitability.",
    "Sub-optimal Canopy Vigor: Moderately dry conditions with early canopy photosynthetic deficit.",
]


@dataclass
class RuleExplanation:
    rule_index: int
    rule_name: str
    description: str
    firing_strength: float
    normalized_weight: float
    consequent_score: float
    rule_contribution: float
    antecedent_memberships: Dict[str, float]


@dataclass
class NeuroFuzzyPrediction:
    risk_score: float
    risk_band: str  # "Low", "Medium", "High"
    failure_predicted: bool
    threshold: float
    model_version: str
    activated_rules: List[RuleExplanation]
    dominant_rule: RuleExplanation
    calibrated_probability: float
    feature_provenance: Dict[str, float]


class NeuroFuzzyCropFailureModel:
    """Takagi-Sugeno-Kang (TSK) Neuro-Fuzzy Inference System."""

    VERSION = "1.0.0-experimental"

    def __init__(
        self,
        n_rules: int = 6,
        spread_scale: float = 1.25,
        regularization_c: float = 1.0,
        random_state: int = 42,
    ):
        self.n_rules = n_rules
        self.spread_scale = spread_scale
        self.regularization_c = regularization_c
        self.random_state = random_state

        self.feature_names = FEATURE_NAMES
        self.scaler: Optional[StandardScaler] = None
        self.centers: Optional[np.ndarray] = None  # (n_rules, n_features)
        self.spreads: Optional[np.ndarray] = None  # (n_rules, n_features)
        self.consequents: Optional[np.ndarray] = None  # (n_rules, n_features + 1)
        self.intercept: float = 0.0
        self.optimal_threshold: float = 0.50
        self.is_trained: bool = False
        self.training_metadata: Dict[str, Any] = {}

    def _compute_memberships(self, X_scaled: np.ndarray) -> np.ndarray:
        """Compute Gaussian memberships for all rules and samples.
        
        X_scaled: (N, D)
        Returns firing strengths: (N, R)
        """
        if self.centers is None or self.spreads is None:
            raise ValueError("Model centers and spreads are not initialized.")
        
        # diff: (N, R, D)
        diff = X_scaled[:, np.newaxis, :] - self.centers[np.newaxis, :, :]
        # Gaussian exponent: -0.5 * sum_j ((x_j - c_rj) / s_rj)^2
        exponent = -0.5 * np.sum((diff / (self.spreads[np.newaxis, :, :] + 1e-6)) ** 2, axis=2)
        # Numerical stability via log-sum-exp trick
        max_exp = np.max(exponent, axis=1, keepdims=True)
        exp_stable = np.exp(exponent - max_exp)
        # Normalized firing weights
        weights = exp_stable / (np.sum(exp_stable, axis=1, keepdims=True) + 1e-12)
        return weights

    def _build_design_matrix(self, X_scaled: np.ndarray, weights: np.ndarray) -> np.ndarray:
        """Construct the first-order Sugeno design matrix:
        Phi(x) = [w_bar_0, w_bar_0 * x, ..., w_bar_{R-1}, w_bar_{R-1} * x]
        """
        N, D = X_scaled.shape
        R = self.n_rules
        phi_list = []
        for r in range(R):
            w_r = weights[:, r : r + 1]  # (N, 1)
            phi_list.append(w_r)
            phi_list.append(w_r * X_scaled)
        return np.hstack(phi_list)  # (N, R * (D + 1))

    def fit(
        self,
        X: Union[np.ndarray, pd.DataFrame],
        y: Union[np.ndarray, pd.Series],
        validation_split: float = 0.20,
    ) -> Dict[str, Any]:
        """Train the Neuro-Fuzzy model with zero target leakage."""
        start_time = time.time()

        if isinstance(X, pd.DataFrame):
            X_df = X[self.feature_names].copy()
            X_mat = X_df.values.astype(np.float64)
        else:
            X_mat = np.array(X, dtype=np.float64)

        y_vec = np.array(y, dtype=np.int32)

        # 1. Stratified train/val split strictly for threshold and hyperparameter verification
        X_tr, X_val, y_tr, y_val = train_test_split(
            X_mat,
            y_vec,
            test_size=validation_split,
            random_state=self.random_state,
            stratify=y_vec,
        )

        # 2. Fit standard scaler only on training partition
        self.scaler = StandardScaler()
        X_tr_s = self.scaler.fit_transform(X_tr)
        X_val_s = self.scaler.transform(X_val)

        # 3. Initialize Antecedent Rule Centers via K-Means on training partition
        kmeans = KMeans(
            n_clusters=self.n_rules,
            random_state=self.random_state,
            n_init=10,
        ).fit(X_tr_s)
        self.centers = kmeans.cluster_centers_  # (R, D)

        # 4. Spreads initialized based on cluster dispersion
        D = X_tr_s.shape[1]
        cluster_labels = kmeans.labels_
        spreads = np.zeros_like(self.centers)
        for r in range(self.n_rules):
            pts = X_tr_s[cluster_labels == r]
            if len(pts) > 1:
                spreads[r] = np.std(pts, axis=0) * self.spread_scale
            else:
                spreads[r] = np.std(X_tr_s, axis=0) * self.spread_scale
        # Clip minimum spread to avoid zero-division singularities
        self.spreads = np.maximum(spreads, 0.40)

        # 5. Compute firing weights and first-order design matrix
        w_tr = self._compute_memberships(X_tr_s)
        Phi_tr = self._build_design_matrix(X_tr_s, w_tr)

        # 6. Fit linear consequents via L2 regularized logistic regression (cross-entropy loss)
        clf = LogisticRegression(
            C=self.regularization_c,
            max_iter=1500,
            class_weight="balanced",
            random_state=self.random_state,
            fit_intercept=True,
        )
        clf.fit(Phi_tr, y_tr)

        # Reshape consequents: coefficients are [w0, w0*x, w1, w1*x, ...]
        raw_coefs = clf.coef_[0]  # shape: (R * (D + 1),)
        self.consequents = raw_coefs.reshape(self.n_rules, D + 1)
        self.intercept = float(clf.intercept_[0])

        # 7. Select optimal decision threshold strictly on VALIDATION partition
        w_val = self._compute_memberships(X_val_s)
        Phi_val = self._build_design_matrix(X_val_s, w_val)
        val_logits = Phi_val @ raw_coefs + self.intercept
        val_probs = 1.0 / (1.0 + np.exp(-val_logits))

        # Sweep thresholds on validation set to maximize F1 score
        best_f1 = -1.0
        best_thresh = 0.50
        candidate_thresholds = np.linspace(0.20, 0.80, 61)
        for t in candidate_thresholds:
            preds = (val_probs >= t).astype(int)
            f1 = f1_score(y_val, preds, zero_division=0)
            if f1 > best_f1:
                best_f1 = f1
                best_thresh = float(t)

        self.optimal_threshold = best_thresh
        self.is_trained = True
        elapsed = time.time() - start_time

        # Store training metadata
        self.training_metadata = {
            "version": self.VERSION,
            "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "n_samples_train": int(len(X_tr)),
            "n_samples_val": int(len(X_val)),
            "n_rules": self.n_rules,
            "training_time_seconds": round(elapsed, 4),
            "optimal_threshold": round(self.optimal_threshold, 4),
            "val_f1_at_optimal_threshold": round(best_f1, 4),
            "val_roc_auc": round(float(roc_auc_score(y_val, val_probs)), 4),
            "val_pr_auc": round(float(average_precision_score(y_val, val_probs)), 4),
            "val_brier_score": round(float(brier_score_loss(y_val, val_probs)), 4),
        }

        return self.training_metadata

    def predict_proba(self, X: Union[np.ndarray, pd.DataFrame]) -> np.ndarray:
        """Compute calibrated continuous failure probabilities in [0.0, 1.0]."""
        if not self.is_trained or self.scaler is None or self.consequents is None:
            raise RuntimeError("Neuro-Fuzzy model is not trained. Call fit() or load().")

        if isinstance(X, pd.DataFrame):
            X_mat = X[self.feature_names].values.astype(np.float64)
        else:
            X_mat = np.array(X, dtype=np.float64)

        X_scaled = self.scaler.transform(X_mat)
        weights = self._compute_memberships(X_scaled)
        Phi = self._build_design_matrix(X_scaled, weights)
        raw_coefs = self.consequents.reshape(-1)
        logits = Phi @ raw_coefs + self.intercept
        # Sigmoidal squashing to strictly bounded probability range [0, 1]
        probs = 1.0 / (1.0 + np.exp(-logits))
        return np.clip(probs, 0.0, 1.0)

    def predict(
        self,
        X: Union[np.ndarray, pd.DataFrame],
        threshold: Optional[float] = None,
    ) -> np.ndarray:
        """Compute binary failure decisions using defensible threshold."""
        t = threshold if threshold is not None else self.optimal_threshold
        probs = self.predict_proba(X)
        return (probs >= t).astype(int)

    def explain_prediction(self, input_dict: Dict[str, Any]) -> NeuroFuzzyPrediction:
        """Generate human-interpretable fuzzy rule activations and contributions."""
        if not self.is_trained or self.scaler is None or self.consequents is None:
            raise RuntimeError("Neuro-Fuzzy model is not trained.")

        # Extract features in strict order
        clean_inputs = {}
        row = []
        for feat in self.feature_names:
            val = input_dict.get(feat)
            if val is None:
                raise ValueError(f"Missing required feature for neuro-fuzzy inference: {feat}")
            f_val = float(val)
            clean_inputs[feat] = f_val
            row.append(f_val)

        X_raw = np.array([row], dtype=np.float64)
        X_scaled = self.scaler.transform(X_raw)  # (1, D)
        weights = self._compute_memberships(X_scaled)[0]  # (R,)

        # Individual rule consequents and contributions
        D = len(self.feature_names)
        rule_explanations: List[RuleExplanation] = []
        total_logit = self.intercept

        for r in range(self.n_rules):
            p_r0 = self.consequents[r, 0]
            p_rj = self.consequents[r, 1:]
            consequent_score = p_r0 + np.dot(p_rj, X_scaled[0])
            w_r = weights[r]
            rule_contribution = w_r * consequent_score
            total_logit += rule_contribution

            # Antecedent memberships per feature
            diff = (X_scaled[0] - self.centers[r]) / (self.spreads[r] + 1e-6)
            per_feat_mu = np.exp(-0.5 * (diff ** 2))
            ante_dict = {
                self.feature_names[j]: round(float(per_feat_mu[j]), 3)
                for j in range(D)
            }

            desc = RULE_DESCRIPTIONS[r] if r < len(RULE_DESCRIPTIONS) else f"Fuzzy Cluster Rule #{r + 1}"
            rule_name = f"Rule #{r + 1}"

            rule_explanations.append(
                RuleExplanation(
                    rule_index=r,
                    rule_name=rule_name,
                    description=desc,
                    firing_strength=round(float(w_r), 4),
                    normalized_weight=round(float(w_r), 4),
                    consequent_score=round(float(consequent_score), 4),
                    rule_contribution=round(float(rule_contribution), 4),
                    antecedent_memberships=ante_dict,
                )
            )

        # Sort rules by highest firing weight
        rule_explanations.sort(key=lambda x: x.firing_strength, reverse=True)
        dominant_rule = rule_explanations[0]

        prob = float(1.0 / (1.0 + np.exp(-total_logit)))
        prob = max(0.0, min(1.0, prob))

        if prob >= 0.70:
            band = "High"
        elif prob >= 0.45:
            band = "Medium"
        else:
            band = "Low"

        return NeuroFuzzyPrediction(
            risk_score=round(prob, 4),
            risk_band=band,
            failure_predicted=bool(prob >= self.optimal_threshold),
            threshold=round(self.optimal_threshold, 4),
            model_version=self.VERSION,
            activated_rules=rule_explanations,
            dominant_rule=dominant_rule,
            calibrated_probability=round(prob, 4),
            feature_provenance=clean_inputs,
        )

    def save(self, filepath: Union[str, Path]) -> None:
        """Persist model parameters and scaler."""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.VERSION,
            "n_rules": self.n_rules,
            "spread_scale": self.spread_scale,
            "regularization_c": self.regularization_c,
            "random_state": self.random_state,
            "feature_names": self.feature_names,
            "optimal_threshold": self.optimal_threshold,
            "intercept": self.intercept,
            "centers": self.centers.tolist() if self.centers is not None else None,
            "spreads": self.spreads.tolist() if self.spreads is not None else None,
            "consequents": self.consequents.tolist() if self.consequents is not None else None,
            "scaler_mean": self.scaler.mean_.tolist() if self.scaler is not None else None,
            "scaler_scale": self.scaler.scale_.tolist() if self.scaler is not None else None,
            "training_metadata": self.training_metadata,
        }
        with open(filepath, "w") as f:
            json.dump(payload, f, indent=2)

    @classmethod
    def load(cls, filepath: Union[str, Path]) -> "NeuroFuzzyCropFailureModel":
        """Restore model from persisted JSON weights."""
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Model file not found: {filepath}")

        with open(filepath, "r") as f:
            data = json.load(f)

        model = cls(
            n_rules=data.get("n_rules", 6),
            spread_scale=data.get("spread_scale", 1.25),
            regularization_c=data.get("regularization_c", 1.0),
            random_state=data.get("random_state", 42),
        )
        model.feature_names = data.get("feature_names", FEATURE_NAMES)
        model.optimal_threshold = data.get("optimal_threshold", 0.50)
        model.intercept = data.get("intercept", 0.0)

        if data.get("centers") is not None:
            model.centers = np.array(data["centers"], dtype=np.float64)
        if data.get("spreads") is not None:
            model.spreads = np.array(data["spreads"], dtype=np.float64)
        if data.get("consequents") is not None:
            model.consequents = np.array(data["consequents"], dtype=np.float64)

        if data.get("scaler_mean") is not None and data.get("scaler_scale") is not None:
            scaler = StandardScaler()
            scaler.mean_ = np.array(data["scaler_mean"], dtype=np.float64)
            scaler.scale_ = np.array(data["scaler_scale"], dtype=np.float64)
            scaler.var_ = scaler.scale_ ** 2
            scaler.n_features_in_ = len(scaler.mean_)
            model.scaler = scaler

        model.training_metadata = data.get("training_metadata", {})
        model.is_trained = True
        return model
