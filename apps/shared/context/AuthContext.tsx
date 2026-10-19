
"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
} from "react";
import type { User } from "@supabase/supabase-js";
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

const DEV_SESSION_KEY = "crop_ai_dev_session";
const LANG_STORAGE_KEY = "crop_ai_user_lang";

export const AuthProvider: React.FC<{
  children: React.ReactNode;
}> = ({ children }) => {
  const [user, setUser] = useState<{
    id: string;
    email?: string;
  } | null>(null);

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [role, setRole] = useState<UserRole>("farmer");
  const [language, setLanguageState] = useState("en");
  const [isLoading, setIsLoading] = useState(true);

  const setLanguage = (lang: string) => {
    setLanguageState(lang);

    if (typeof window !== "undefined") {
      localStorage.setItem(LANG_STORAGE_KEY, lang);
    }
  };

  // Keep track of the currently processed access token to avoid duplicate fetches
  const currentTokenRef = React.useRef<string | null>(null);

  const applySupabaseUser = async (
    supabaseUser: User,
    accessToken: string
  ) => {
    // If we've already applied this exact token, skip re-fetching
    if (currentTokenRef.current === accessToken && profile) {
      return;
    }
    currentTokenRef.current = accessToken;

    // Real Supabase session takes precedence: clear demo session
    if (typeof window !== "undefined") {
      localStorage.removeItem(DEV_SESSION_KEY);
    }

    setUser({
      id: supabaseUser.id,
      email: supabaseUser.email,
    });
    setToken(accessToken);

    try {
      const liveProfile = await getUserProfile(accessToken);

      setProfile(liveProfile);
      setRole(liveProfile.role);

      if (liveProfile.preferred_language) {
        setLanguageState(liveProfile.preferred_language);
        if (typeof window !== "undefined") {
          localStorage.setItem(
            LANG_STORAGE_KEY,
            liveProfile.preferred_language
          );
        }
      }
    } catch (error) {
      console.error(
        "Authenticated, but failed to load backend profile:",
        error
      );

      // Do not assign a fake profile or mock token.
      // Keep the real Supabase session and report the profile error.
      setProfile(null);
    }
  };

  useEffect(() => {
    let active = true;

    const initializeAuth = async () => {
      try {
        const savedLang = typeof window !== "undefined" ? localStorage.getItem(LANG_STORAGE_KEY) : null;

        if (savedLang && active) {
          setLanguageState(savedLang);
        }

        const { getSupabaseClient } = await import("../supabase/client");
        const supabase = getSupabaseClient();

        // Restore the real Supabase session, including OAuth redirects.
        const { data, error } = await supabase.auth.getSession();

        if (!active) return;

        if (error) {
          console.error("Could not restore Supabase session:", error.message);
        }

        if (data.session?.user && data.session?.access_token) {
          await applySupabaseUser(
            data.session.user,
            data.session.access_token
          );
          return;
        }

        // Restore demo access only if there is no real Supabase session.
        const stored = typeof window !== "undefined" ? localStorage.getItem(DEV_SESSION_KEY) : null;

        if (stored) {
          try {
            const parsed = JSON.parse(stored);

            if (active && parsed?.user && parsed?.token) {
              setToken(parsed.token);
              setUser(parsed.user);
              setRole(parsed.role || "farmer");

              try {
                const liveProfile = await getUserProfile(parsed.token);

                if (!active) return;

                setProfile(liveProfile);
                setRole(liveProfile.role);

                if (liveProfile.preferred_language) {
                  setLanguageState(liveProfile.preferred_language);
                }
              } catch {
                if (!active) return;

                // Preserve the existing demo-mode fallback.
                setProfile({
                  id: parsed.user.id,
                  email: parsed.user.email,
                  full_name:
                    parsed.role === "expert"
                      ? "Dr. Expert Agronomist"
                      : "Farmer Ramesh Patel",
                  role: parsed.role || "farmer",
                  preferred_language: savedLang || "en",
                });
              }
            }
          } catch (error) {
            console.error("Invalid saved demo session:", error);
            if (typeof window !== "undefined") {
              localStorage.removeItem(DEV_SESSION_KEY);
            }
          }
        }
      } catch (error) {
        console.error("Authentication initialization failed:", error);
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    };

    void initializeAuth();

    // Keep React state synchronized with OAuth sign-in and sign-out.
    let unsubscribe: (() => void) | undefined;

    void import("../supabase/client")
      .then(({ getSupabaseClient }) => {
        if (!active) return;

        const supabase = getSupabaseClient();

        const {
          data: { subscription },
        } = supabase.auth.onAuthStateChange(async (event, session) => {
          if (!active) return;

          if (session?.user && session?.access_token) {
            await applySupabaseUser(session.user, session.access_token);
            if (active) {
              setIsLoading(false);
            }
            return;
          }

          if (event === "SIGNED_OUT") {
            currentTokenRef.current = null;
            if (typeof window !== "undefined") {
              localStorage.removeItem(DEV_SESSION_KEY);
            }
            setUser(null);
            setProfile(null);
            setToken(null);
            setRole("farmer");
            if (active) {
              setIsLoading(false);
            }
          }
        });

        unsubscribe = () => subscription.unsubscribe();
      })
      .catch((error) => {
        console.error("Could not subscribe to auth changes:", error);
      });

    return () => {
      active = false;
      unsubscribe?.();
    };
  }, []);

  const signInWithGoogle = async () => {
    try {
      const { getSupabaseClient, checkSupabaseConfig } = await import(
        "../supabase/client"
      );

      const status = checkSupabaseConfig();
      if (!status.isConfigured) {
        const err = new Error(
          `Google OAuth requires valid Supabase credentials. Missing: ${status.missingVariables.join(
            ", "
          )}. Please check your root .env or .env.local file.`
        );
        console.error(err.message);
        throw err;
      }

      const supabase = getSupabaseClient();
      const redirectTo = `${window.location.origin}/auth/callback`;

      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo,
        },
      });

      if (error) {
        console.error("Google sign-in failed:", error.message);
        throw error;
      }
    } catch (error) {
      console.error("Unable to start Google sign-in:", error);
      throw error;
    }
  };

  const signInWithDevRole = async (targetRole: UserRole) => {
    setIsLoading(true);

    try {
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

      localStorage.setItem(
        DEV_SESSION_KEY,
        JSON.stringify(sessionPayload)
      );

      setToken(devToken);
      setUser(devUser);
      setProfile(devProfile);
      setRole(targetRole);
    } finally {
      setIsLoading(false);
    }
  };

  const signOut = async () => {
    try {
      const { getSupabaseClient } = await import("../supabase/client");
      const supabase = getSupabaseClient();

      const { error } = await supabase.auth.signOut();

      if (error) {
        console.error("Supabase sign-out failed:", error.message);
      }
    } catch (error) {
      console.error("Error during sign-out:", error);
    } finally {
      localStorage.removeItem(DEV_SESSION_KEY);
      setUser(null);
      setProfile(null);
      setToken(null);
      setRole("farmer");
    }
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
