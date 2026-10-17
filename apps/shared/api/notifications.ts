/**
 * Notification preferences and history API client.
 */

import { apiClient } from "./client";

export interface ChannelPreferences {
  user_id: string;
  phone_number_masked?: string | null;
  sms_notifications_enabled: boolean;
  sms_consent_timestamp?: string | null;
  whatsapp_notifications_enabled: boolean;
  whatsapp_consent_timestamp?: string | null;
}

export interface NotificationDispatch {
  id: string;
  user_id?: string | null;
  alert_id?: string | null;
  channel: "sms" | "whatsapp";
  status: string;
  recipient_phone_masked?: string | null;
  error_message?: string | null;
  created_at: string;
}

export interface NotificationDispatchList {
  dispatches: NotificationDispatch[];
  total_count: number;
}

export async function getNotificationPreferences(token: string): Promise<ChannelPreferences> {
  return apiClient<ChannelPreferences>("/api/v1/notifications/preferences", {
    method: "GET",
    token,
  });
}

export async function updateSmsPreferences(
  payload: { sms_notifications_enabled: boolean; phone_number?: string },
  token: string
): Promise<{ user_id: string; sms_notifications_enabled: boolean; phone_number_masked?: string | null }> {
  return apiClient("/api/v1/notifications/preferences/sms", {
    method: "PUT",
    body: JSON.stringify(payload),
    token,
  });
}

export async function updateWhatsAppPreferences(
  payload: { whatsapp_notifications_enabled: boolean; phone_number?: string },
  token: string
): Promise<{ user_id: string; whatsapp_notifications_enabled: boolean; phone_number_masked?: string | null }> {
  return apiClient("/api/v1/notifications/preferences/whatsapp", {
    method: "PUT",
    body: JSON.stringify(payload),
    token,
  });
}

export async function listNotificationDispatches(
  token: string,
  limit: number = 50,
  offset: number = 0
): Promise<NotificationDispatchList> {
  return apiClient<NotificationDispatchList>(
    `/api/v1/notifications/dispatches?limit=${limit}&offset=${offset}`,
    {
      method: "GET",
      token,
    }
  );
}
