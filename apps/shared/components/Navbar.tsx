"use client";

import React from "react";
import { useAuth } from "../context/AuthContext";
import { LanguageSelector } from "./LanguageSelector";
import { t } from "../translations";

interface NavbarProps {
  appName?: string;
  portalType: "farmer" | "expert";
}

export const Navbar: React.FC<NavbarProps> = ({ portalType }) => {
  const { user, profile, role, signOut, language } = useAuth();

  return (
    <header className="bg-emerald-800 text-white shadow-md">
      <div className="max-w-6xl mx-auto px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="text-2xl" aria-hidden="true">🌱</span>
          <div>
            <h1 className="text-lg font-bold tracking-tight leading-none">
              {t("app_title", language)}
            </h1>
            <p className="text-xs text-emerald-200 mt-0.5">
              {portalType === "farmer" ? t("farmer_portal", language) : t("expert_portal", language)}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3 ml-auto">
          <LanguageSelector />

          {user && (
            <div className="flex items-center gap-2">
              <span className="text-xs hidden sm:inline bg-emerald-700/60 px-2.5 py-1 rounded-full text-emerald-100 font-medium">
                {profile?.full_name || user.email || role}
              </span>
              <button
                onClick={() => signOut()}
                className="bg-emerald-950/80 hover:bg-emerald-950 text-white text-xs font-semibold px-3 py-1.5 rounded-lg border border-emerald-600 transition"
                aria-label="Sign Out"
              >
                {t("sign_out", language)}
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
