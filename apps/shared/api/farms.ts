/**
 * Farm management API functions.
 */

import { apiClient } from "./client";
import { Farm, FarmCreateRequest, FarmUpdateRequest } from "../types";

export async function listFarms(token: string): Promise<Farm[]> {
  return apiClient<Farm[]>("/api/v1/farms", {
    method: "GET",
    token,
  });
}

export async function getFarm(farmId: string, token: string): Promise<Farm> {
  return apiClient<Farm>(`/api/v1/farms/${farmId}`, {
    method: "GET",
    token,
  });
}

export async function createFarm(
  payload: FarmCreateRequest,
  token: string
): Promise<Farm> {
  return apiClient<Farm>("/api/v1/farms", {
    method: "POST",
    body: JSON.stringify(payload),
    token,
  });
}

export async function updateFarm(
  farmId: string,
  payload: FarmUpdateRequest,
  token: string
): Promise<Farm> {
  return apiClient<Farm>(`/api/v1/farms/${farmId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    token,
  });
}

export async function deleteFarm(
  farmId: string,
  token: string
): Promise<void> {
  return apiClient<void>(`/api/v1/farms/${farmId}`, {
    method: "DELETE",
    token,
  });
}
