"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { UserProfile, UserRole } from "../types";
import { getUserProfile } from "../api/auth";

export interface AuthContextType {
  user: { id: string; email?: string } | null;
  profile: UserProfile | null;
  token: string | null;
  role: UserRole;
  language: string;
  isLoading: boolean;
  signInWithGoogle: () => Promise<void>;
  signInWithDevRole: (role: UserRole) => Promise<void>;
  signOut: () => Promise<void>;
  setLanguage: (lang: string) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// In-memory/localStorage mock session helper for local development
const DEV_SESSION_KEY = "crop_ai_dev_session";
const LANG_STORAGE_KEY = "crop_ai_user_lang";

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<{ id: string; email?: string } | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [role, setRole] = useState<UserRole>("farmer");
  const [language, setLanguageState] = useState<string>("en");
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    // Restore language preference
    const savedLang = typeof window !== "undefined" ? localStorage.getItem(LANG_STORAGE_KEY) : null;
    if (savedLang) {
      setLanguageState(savedLang);
    }

    // Check for active dev session or Supabase session
    const loadSession = async () => {
      try {
        const stored = typeof window !== "undefined" ? localStorage.getItem(DEV_SESSION_KEY) : null;
        if (stored) {
          const parsed = JSON.parse(stored);
          setToken(parsed.token);
          setUser(parsed.user);
          setRole(parsed.role || "farmer");
          
          // Attempt to fetch fresh profile from FastAPI
          try {
            const liveProfile = await getUserProfile(parsed.token);
            setProfile(liveProfile);
            setRole(liveProfile.role);
            if (liveProfile.preferred_language) {
              setLanguageState(liveProfile.preferred_language);
            }
          } catch {
            // Use cached profile if offline
            setProfile({
              id: parsed.user.id,
              email: parsed.user.email,
              full_name: parsed.role === "expert" ? "Dr. Expert Agronomist" : "Farmer Ramesh Patel",
              role: parsed.role,
              preferred_language: savedLang || "en",
            });
          }
        }
      } catch (e) {
        console.error("Session restoration error:", e);
      } finally {
        setIsLoading(false);
      }
    };

    loadSession();
  }, []);

  const setLanguage = (lang: string) => {
    setLanguageState(lang);
    if (typeof window !== "undefined") {
      localStorage.setItem(LANG_STORAGE_KEY, lang);
    }
  };

  const signInWithGoogle = async () => {
    try {
      // In production, delegates to Supabase OAuth
      const { getSupabaseClient } = await import("../supabase/client");
      const supabase = getSupabaseClient();
      await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
        },
      });
    } catch (err) {
      console.warn("Supabase OAuth initialization fallback to Dev Farmer mode");
      await signInWithDevRole("farmer");
    }
  };

  const signInWithDevRole = async (targetRole: UserRole) => {
    setIsLoading(true);
    const userId =
      targetRole === "expert"
        ? "33333333-3333-3333-3333-333333333333"
        : targetRole === "admin"
        ? "44444444-4444-4444-4444-444444444444"
        : "11111111-1111-1111-1111-111111111111";

    const devToken = `mock-dev-token-${targetRole}`;
    const devUser = {
      id: userId,
      email: `${targetRole}@cropai.local`,
    };

    const devProfile: UserProfile = {
      id: userId,
      email: devUser.email,
      full_name:
        targetRole === "expert"
          ? "Dr. Swaminathan (Agronomist)"
          : targetRole === "admin"
          ? "System Administrator"
          : "Ramesh Patel (Farmer)",
      role: targetRole,
      preferred_language: language,
    };

    const sessionPayload = {
      token: devToken,
      user: devUser,
      role: targetRole,
    };

    if (typeof window !== "undefined") {
      localStorage.setItem(DEV_SESSION_KEY, JSON.stringify(sessionPayload));
    }

    setToken(devToken);
    setUser(devUser);
    setProfile(devProfile);
    setRole(targetRole);
    setIsLoading(false);
  };

  const signOut = async () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem(DEV_SESSION_KEY);
    }
    try {
      const { getSupabaseClient } = await import("../supabase/client");
      const supabase = getSupabaseClient();
      await supabase.auth.signOut();
    } catch {
      // Ignored in dev
    }
    setUser(null);
    setProfile(null);
    setToken(null);
    setRole("farmer");
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        profile,
        token,
        role,
        language,
        isLoading,
        signInWithGoogle,
        signInWithDevRole,
        signOut,
        setLanguage,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
