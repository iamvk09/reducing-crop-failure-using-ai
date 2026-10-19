/**
 * Supabase Browser Client.
 * Uses only public publishable/anonymous key (NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY or NEXT_PUBLIC_SUPABASE_ANON_KEY).
 * NEVER import or expose secret keys (SUPABASE_SECRET_KEY / SUPABASE_SERVICE_ROLE_KEY) to client browsers.
 */

import { createClient, SupabaseClient } from "@supabase/supabase-js";

export interface SupabaseConfigStatus {
  isConfigured: boolean;
  missingVariables: string[];
}

export interface SupabaseRuntimeDiagnostic {
  isConfigured: boolean;
  hasUrl: boolean;
  isPlaceholderUrl: boolean;
  hasPublishableKey: boolean;
  isPlaceholderKey: boolean;
  missingVariables: string[];
}

/**
 * Resolves public Supabase configuration from environment variables or browser runtime globals.
 * NEVER resolves or exposes secret / service role keys to client bundles.
 */
function resolveSupabaseCredentials(): { url: string | undefined; key: string | undefined } {
  const envUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const envKey =
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  // Window fallback in browser if bundler left runtime references on global scope
  const windowUrl =
    typeof window !== "undefined"
      ? (window as any).NEXT_PUBLIC_SUPABASE_URL ||
        ((window as any).process && (window as any).process.env?.NEXT_PUBLIC_SUPABASE_URL)
      : undefined;

  const windowKey =
    typeof window !== "undefined"
      ? (window as any).NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
        (window as any).NEXT_PUBLIC_SUPABASE_ANON_KEY ||
        ((window as any).process &&
          ((window as any).process.env?.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
            (window as any).process.env?.NEXT_PUBLIC_SUPABASE_ANON_KEY))
      : undefined;

  const url = envUrl || windowUrl;
  const key = envKey || windowKey;

  return { url, key };
}

export function getSupabaseRuntimeDiagnostic(): SupabaseRuntimeDiagnostic {
  const { url, key } = resolveSupabaseCredentials();
  const hasUrl = Boolean(url && url.trim().length > 0);
  const isPlaceholderUrl = Boolean(url && url.includes("placeholder.supabase.co"));
  const hasPublishableKey = Boolean(key && key.trim().length > 0);
  const isPlaceholderKey = Boolean(key && key === "placeholder-anon-key");

  const missingVariables: string[] = [];
  if (!hasUrl || isPlaceholderUrl) {
    missingVariables.push("NEXT_PUBLIC_SUPABASE_URL");
  }
  if (!hasPublishableKey || isPlaceholderKey) {
    missingVariables.push("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY (or NEXT_PUBLIC_SUPABASE_ANON_KEY)");
  }

  return {
    isConfigured: missingVariables.length === 0,
    hasUrl,
    isPlaceholderUrl,
    hasPublishableKey,
    isPlaceholderKey,
    missingVariables,
  };
}

export function checkSupabaseConfig(): SupabaseConfigStatus {
  const diag = getSupabaseRuntimeDiagnostic();
  return {
    isConfigured: diag.isConfigured,
    missingVariables: diag.missingVariables,
  };
}

let supabaseInstance: SupabaseClient | null = null;

export function getSupabaseClient(): SupabaseClient {
  if (!supabaseInstance) {
    const { url: rawUrl, key: rawKey } = resolveSupabaseCredentials();
    const diag = getSupabaseRuntimeDiagnostic();

    if (!diag.isConfigured) {
      console.error(
        `[Supabase Client Configuration Error] Missing required public environment variables: ${diag.missingVariables.join(
          ", "
        )}. Ensure NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY are configured in the monorepo root .env or .env.local file.`
      );
    }

    const effectiveUrl =
      rawUrl && !diag.isPlaceholderUrl ? rawUrl : "https://placeholder.supabase.co";
    const effectiveKey =
      rawKey && !diag.isPlaceholderKey ? rawKey : "placeholder-anon-key";

    supabaseInstance = createClient(effectiveUrl, effectiveKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
  }
  return supabaseInstance;
}
