/**
 * Early Warning & Alert Engine API Client.
 */

import { apiClient } from "./client";
import { FarmAlert } from "../types";

export interface AlertFilterParams {
  status?: string;
  severity?: string;
  alert_type?: string;
  limit?: number;
  offset?: number;
}

export async function listFarmAlerts(
  farmId: string,
  token: string,
  params?: AlertFilterParams
): Promise<FarmAlert[]> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.severity) query.set("severity", params.severity);
  if (params?.alert_type) query.set("alert_type", params.alert_type);
  if (params?.limit) query.set("limit", params.limit.toString());
  if (params?.offset) query.set("offset", params.offset.toString());

  const qs = query.toString() ? `?${query.toString()}` : "";
  return apiClient<FarmAlert[]>(`/api/v1/farms/${farmId}/alerts${qs}`, {
    method: "GET",
    token,
  });
}

export async function acknowledgeFarmAlert(
  farmId: string,
  alertId: string,
  token: string,
  notes?: string
): Promise<FarmAlert> {
  return apiClient<FarmAlert>(`/api/v1/farms/${farmId}/alerts/${alertId}/acknowledge`, {
    method: "POST",
    body: JSON.stringify(notes ? { notes } : {}),
    token,
  });
}

export async function resolveFarmAlert(
  farmId: string,
  alertId: string,
  token: string,
  resolutionNotes?: string
): Promise<FarmAlert> {
  return apiClient<FarmAlert>(`/api/v1/farms/${farmId}/alerts/${alertId}/resolve`, {
    method: "POST",
    body: JSON.stringify(resolutionNotes ? { resolution_notes: resolutionNotes } : {}),
    token,
  });
}

export async function listExpertAlerts(
  token: string,
  params?: AlertFilterParams
): Promise<FarmAlert[]> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.severity) query.set("severity", params.severity);
  if (params?.alert_type) query.set("alert_type", params.alert_type);
  if (params?.limit) query.set("limit", params.limit.toString());
  if (params?.offset) query.set("offset", params.offset.toString());

  const qs = query.toString() ? `?${query.toString()}` : "";
  return apiClient<FarmAlert[]>(`/api/v1/experts/alerts${qs}`, {
    method: "GET",
    token,
  });
}

