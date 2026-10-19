
"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { getSupabaseClient } from "@shared/supabase/client";
import { useAuth } from "@shared/context/AuthContext";

export default function AuthCallbackPage() {
  const router = useRouter();
  const { user, isLoading } = useAuth();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const redirectedRef = useRef(false);

  useEffect(() => {
    let active = true;

    // Check URL parameters for explicit error from OAuth provider
    if (typeof window !== "undefined") {
      const urlParams = new URLSearchParams(window.location.search);
      const urlError = urlParams.get("error");
      const errorDescription = urlParams.get("error_description");

      if (urlError) {
        console.error("OAuth redirect error from provider:", urlError, errorDescription);
        setErrorMessage(errorDescription || urlError);
        router.replace(`/login?error=${encodeURIComponent(urlError)}`);
        return;
      }
    }

    const supabase = getSupabaseClient();

    // 1. If auth code is present in URL query (PKCE flow), exchange code for session
    const handleExchange = async () => {
      try {
        if (typeof window !== "undefined") {
          const urlParams = new URLSearchParams(window.location.search);
          const code = urlParams.get("code");
          if (code) {
            const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
            if (exchangeError) {
              console.warn("exchangeCodeForSession returned error or already exchanged:", exchangeError.message);
            }
          }
        }
      } catch (err) {
        console.warn("Code exchange attempt error:", err);
      }
    };

    // 2. Subscribe to auth changes to immediately catch SIGNED_IN or INITIAL_SESSION
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (!active) return;
      if (session?.user && !redirectedRef.current) {
        redirectedRef.current = true;
        router.replace("/dashboard");
      }
    });

    // 3. Fallback verification loop with polling (up to 6 seconds)
    const verifySession = async () => {
      await handleExchange();

      const startTime = Date.now();
      const timeoutMs = 6000;
      const pollIntervalMs = 500;

      while (active && Date.now() - startTime < timeoutMs) {
        if (redirectedRef.current) return;

        try {
          const { data, error } = await supabase.auth.getSession();
          if (error) {
            console.error("Error retrieving session in callback:", error);
            throw error;
          }

          if (data?.session?.user) {
            if (active && !redirectedRef.current) {
              redirectedRef.current = true;
              router.replace("/dashboard");
            }
            return;
          }
        } catch (err) {
          if (active && !redirectedRef.current) {
            redirectedRef.current = true;
            router.replace("/login?error=oauth_callback_failed");
          }
          return;
        }

        await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
      }

      if (active && !redirectedRef.current) {
        redirectedRef.current = true;
        router.replace("/login?error=oauth_session_missing");
      }
    };

    void verifySession();

    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, [router]);

  // Secondary effect: if useAuth() successfully resolved user, proceed to dashboard
  useEffect(() => {
    if (!isLoading && user && !redirectedRef.current) {
      redirectedRef.current = true;
      router.replace("/dashboard");
    }
  }, [isLoading, user, router]);

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="text-center">
        <div className="inline-block animate-spin text-4xl mb-3">🔄</div>
        <p className="text-base font-semibold text-gray-700">
          {errorMessage ? `Authentication error: ${errorMessage}` : "Verifying authenticated session..."}
        </p>
      </div>
    </div>
  );
}
