/**
 * Centralized, reusable API Client for FastAPI backend communications.
 * Automatically injects Supabase JWT access tokens into request headers.
 */

export class ApiError extends Error {
  public statusCode: number;
  public details?: any;

  constructor(message: string, statusCode: number, details?: any) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.details = details;
  }
}

export interface RequestOptions extends RequestInit {
  token?: string | null;
  timeoutMs?: number;
}

const STORAGE_KEY_API_BASE_URL = "crop_ai_active_api_base_url";

function getInitialBaseUrl(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof window !== "undefined") {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY_API_BASE_URL);
      if (saved) return saved;
    } catch {}
  }
  return "http://localhost:8000";
}

let activeBaseUrl = getInitialBaseUrl();

export function getActiveApiBaseUrl(): string {
  return activeBaseUrl;
}

export function setActiveApiBaseUrl(url: string): void {
  activeBaseUrl = url;
  if (typeof window !== "undefined") {
    try {
      sessionStorage.setItem(STORAGE_KEY_API_BASE_URL, url);
    } catch {}
  }
}

async function executeFetch<T>(
  baseUrl: string,
  endpoint: string,
  options: RequestOptions
): Promise<T> {
  const { token, timeoutMs = 20000, headers, ...customConfig } = options;

  const url = endpoint.startsWith("http")
    ? endpoint
    : `${baseUrl}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

  const requestHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...(headers as Record<string, string>),
  };

  if (token) {
    requestHeaders["Authorization"] = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...customConfig,
      headers: requestHeaders,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (response.status === 204) {
      return {} as T;
    }

    let responseData: any;
    const contentType = response.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
      responseData = await response.json();
    } else {
      responseData = await response.text();
    }

    if (!response.ok) {
      const errorMessage =
        (typeof responseData === "object" && responseData?.detail) ||
        (typeof responseData === "string" && responseData) ||
        `API Request Failed with status ${response.status}`;

      throw new ApiError(errorMessage, response.status, responseData);
    }

    return responseData as T;
  } catch (error: any) {
    clearTimeout(timeoutId);
    if (error.name === "AbortError") {
      throw new ApiError("Network request timed out.", 408);
    }
    if (error instanceof ApiError) {
      throw error;
    }
    const rawMsg = error?.message || "";
    const isConnRefused =
      rawMsg.toLowerCase().includes("failed to fetch") ||
      rawMsg.toLowerCase().includes("networkerror") ||
      rawMsg.toLowerCase().includes("econnrefused") ||
      rawMsg.toLowerCase().includes("connection refused");

    const userFriendlyMsg = isConnRefused
      ? `Cannot connect to API backend at ${baseUrl}. Ensure the FastAPI server is running.`
      : rawMsg || "Unable to communicate with the backend server.";

    throw new ApiError(userFriendlyMsg, 0, { originalError: rawMsg, baseUrl });
  }
}

export async function apiClient<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  try {
    return await executeFetch<T>(activeBaseUrl, endpoint, options);
  } catch (err: any) {
    // If a connection error occurs (statusCode 0) and we are using standard localhost ports,
    // seamlessly probe the fallback port (8000 <-> 8001) to support environments where port 8000 is occupied.
    if (err instanceof ApiError && err.statusCode === 0 && !endpoint.startsWith("http")) {
      const fallbackUrl = activeBaseUrl.includes("8000")
        ? activeBaseUrl.replace("8000", "8001")
        : activeBaseUrl.includes("8001")
        ? activeBaseUrl.replace("8001", "8000")
        : null;

      if (fallbackUrl) {
        try {
          const res = await executeFetch<T>(fallbackUrl, endpoint, options);
          setActiveApiBaseUrl(fallbackUrl); // Update and persist active port for subsequent requests
          return res;
        } catch (_) {
          // Re-throw original error with useful connection context
          throw err;
        }
      }
    }
    throw err;
  }
}
