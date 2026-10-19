"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@shared/context/AuthContext";
import { LanguageSelector } from "@shared/components/LanguageSelector";
import { t } from "@shared/translations";

export default function LoginPage() {
  const { user, role, signInWithGoogle, signInWithDevRole, language } = useAuth();
  const router = useRouter();
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [isSigningIn, setIsSigningIn] = React.useState(false);

  React.useEffect(() => {
    if (user) {
      router.push("/dashboard");
    }
  }, [user, router]);

  const handleGoogleSignIn = async () => {
    setErrorMessage(null);
    setIsSigningIn(true);
    try {
      await signInWithGoogle();
    } catch (err: any) {
      console.error("Google sign-in error in LoginPage:", err);
      setErrorMessage(
        err?.message || "Failed to initiate Google sign-in. Please try again."
      );
    } finally {
      setIsSigningIn(false);
    }
  };

  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-4 bg-gradient-to-b from-emerald-50 to-slate-100">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-xl border border-emerald-100 p-6 sm:p-8">
        <div className="flex justify-end mb-4">
          <LanguageSelector />
        </div>

        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-emerald-100 text-3xl mb-3">
            🌾
          </div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
            {t("app_title", language)}
          </h1>
          <p className="text-sm text-gray-600 mt-2">
            {t("app_caption", language)}
          </p>
        </div>

        {errorMessage && (
          <div
            className="mb-4 p-3 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs flex items-start gap-2"
            role="alert"
          >
            <span className="text-base leading-none">⚠️</span>
            <div className="flex-1">
              <p className="font-semibold">Sign-in Notice</p>
              <p className="mt-0.5">{errorMessage}</p>
            </div>
          </div>
        )}

        <div className="space-y-4">
          {/* Primary Google Auth Button */}
          <button
            onClick={handleGoogleSignIn}
            disabled={isSigningIn}
            className={`w-full flex items-center justify-center gap-3 py-3.5 px-4 font-bold rounded-xl shadow-md transition text-base active:scale-[0.99] ${
              isSigningIn
                ? "bg-emerald-600 opacity-80 cursor-wait text-white"
                : "bg-emerald-700 hover:bg-emerald-800 text-white"
            }`}
            aria-label={t("sign_in_google", language)}
          >
            {isSigningIn ? (
              <span className="inline-block animate-spin text-lg">🔄</span>
            ) : (
              <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24">
                <path d="M12.24 10.285V13.4h6.887C18.2 16.033 15.645 18 12.24 18c-3.315 0-6-2.685-6-6s2.685-6 6-6c1.47 0 2.81.53 3.855 1.405l2.405-2.405C16.89 3.49 14.7 2.6 12.24 2.6 7.03 2.6 2.8 6.83 2.8 12.04s4.23 9.44 9.44 9.44c5.445 0 9.075-3.83 9.075-9.24 0-.62-.06-1.22-.175-1.955H12.24z" />
              </svg>
            )}
            <span>
              {isSigningIn
                ? "Connecting to Google..."
                : t("sign_in_google", language)}
            </span>
          </button>

          {/* Local Development Mode Switcher */}
          <div className="mt-8 pt-6 border-t border-gray-200">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider text-center mb-3">
              Developer & Demonstration Access
            </p>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => signInWithDevRole("farmer")}
                className="py-2.5 px-3 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-300 font-bold rounded-lg text-xs transition"
              >
                👨‍🌾 Farmer Persona
              </button>
              <button
                onClick={() => signInWithDevRole("expert")}
                className="py-2.5 px-3 bg-blue-50 hover:bg-blue-100 text-blue-800 border border-blue-300 font-bold rounded-lg text-xs transition"
              >
                🔬 Expert Persona
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
