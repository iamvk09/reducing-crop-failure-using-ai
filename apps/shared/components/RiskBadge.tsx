"use client";

import React from "react";
import { RiskLevel } from "../types";
import { t } from "../translations";

interface RiskBadgeProps {
  level: RiskLevel | string;
  language?: string;
  className?: string;
}

export const RiskBadge: React.FC<RiskBadgeProps> = ({
  level,
  language = "en",
  className = "",
}) => {
  const normLevel = (level || "Low").toLowerCase();

  if (normLevel === "high") {
    return (
      <span
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full font-bold text-sm bg-red-100 text-red-800 border-2 border-red-500 ${className}`}
        role="status"
        aria-label="High Crop Failure Risk"
      >
        <span aria-hidden="true">⚠️</span>
        <span>{t("high_risk", language)}</span>
      </span>
    );
  }

  if (normLevel === "medium") {
    return (
      <span
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full font-bold text-sm bg-amber-100 text-amber-900 border-2 border-amber-500 ${className}`}
        role="status"
        aria-label="Medium Crop Failure Risk"
      >
        <span aria-hidden="true">⚡</span>
        <span>{t("medium_risk", language)}</span>
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full font-bold text-sm bg-emerald-100 text-emerald-800 border-2 border-emerald-500 ${className}`}
      role="status"
      aria-label="Low Crop Failure Risk"
    >
      <span aria-hidden="true">✅</span>
      <span>{t("low_risk", language)}</span>
    </span>
  );
};
