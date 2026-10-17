"use client";

import React from "react";
import { SUPPORTED_LANGUAGES } from "../translations";
import { useAuth } from "../context/AuthContext";

export const LanguageSelector: React.FC<{ className?: string }> = ({ className = "" }) => {
  const { language, setLanguage } = useAuth();

  return (
    <div className={`inline-flex items-center gap-2 ${className}`}>
      <label htmlFor="lang-select" className="text-xs font-semibold text-gray-700 flex items-center gap-1">
        <span>🌐</span>
        <span className="sr-only">Select Language</span>
      </label>
      <select
        id="lang-select"
        value={language}
        onChange={(e) => setLanguage(e.target.value)}
        className="bg-white border-2 border-emerald-600 text-gray-900 text-sm font-medium rounded-lg px-2.5 py-1.5 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
        aria-label="Interface Language"
      >
        {Object.entries(SUPPORTED_LANGUAGES).map(([code, name]) => (
          <option key={code} value={code}>
            {name}
          </option>
        ))}
      </select>
    </div>
  );
};
