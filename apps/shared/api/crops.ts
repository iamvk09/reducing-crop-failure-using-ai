/**
 * Crop cycle management API functions.
 */

import { apiClient } from "./client";
import { CropCreateRequest, CropUpdateRequest, FarmCrop } from "../types";

export async function listFarmCrops(
  farmId: string,
  token: string
): Promise<FarmCrop[]> {
  return apiClient<FarmCrop[]>(`/api/v1/farms/${farmId}/crops`, {
    method: "GET",
    token,
  });
}

export async function registerCrop(
  farmId: string,
  payload: CropCreateRequest,
  token: string
): Promise<FarmCrop> {
  return apiClient<FarmCrop>(`/api/v1/farms/${farmId}/crops`, {
    method: "POST",
    body: JSON.stringify(payload),
    token,
  });
}

export async function updateCrop(
  farmId: string,
  cropId: string,
  payload: CropUpdateRequest,
  token: string
): Promise<FarmCrop> {
  return apiClient<FarmCrop>(`/api/v1/farms/${farmId}/crops/${cropId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    token,
  });
}

export async function deleteCrop(
  farmId: string,
  cropId: string,
  token: string
): Promise<void> {
  return apiClient<void>(`/api/v1/farms/${farmId}/crops/${cropId}`, {
    method: "DELETE",
    token,
  });
}
