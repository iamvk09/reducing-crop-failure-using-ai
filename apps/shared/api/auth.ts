/**
 * Authentication and User Profile API functions.
 */

import { apiClient } from "./client";
import { UserProfile, UserProfileUpdateRequest } from "../types";

export async function getUserProfile(token: string): Promise<UserProfile> {
  return apiClient<UserProfile>("/api/v1/me", {
    method: "GET",
    token,
  });
}

export async function updateUserProfile(
  payload: UserProfileUpdateRequest,
  token: string
): Promise<UserProfile> {
  return apiClient<UserProfile>("/api/v1/me", {
    method: "PATCH",
    body: JSON.stringify(payload),
    token,
  });
}
