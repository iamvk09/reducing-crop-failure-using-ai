"use client";

import React, { useEffect, useState } from "react";
import { UserProfile, UserRole } from "@shared/types";
import { getUserProfile, updateUserProfile } from "@shared/api/auth";
import {
  ChannelPreferences,
  getNotificationPreferences,
  updateSmsPreferences,
  updateWhatsAppPreferences,
} from "@shared/api/notifications";
import { SUPPORTED_LANGUAGES } from "@shared/translations";

interface UserProfileViewProps {
  token: string | null;
  initialProfile: UserProfile | null;
  language: string;
  onLanguageChange: (lang: string) => void;
  onSignOut: () => void;
}

export default function UserProfileView({
  token,
  initialProfile,
  language,
  onLanguageChange,
  onSignOut,
}: UserProfileViewProps) {
  const [profile, setProfile] = useState<UserProfile | null>(initialProfile);
  const [fullName, setFullName] = useState<string>(initialProfile?.full_name || "");
  const [phoneNumber, setPhoneNumber] = useState<string>(initialProfile?.phone_number || "");
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [saveSuccess, setSaveSuccess] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Notification Preferences State
  const [notifPrefs, setNotifPrefs] = useState<ChannelPreferences | null>(null);
  const [smsConsent, setSmsConsent] = useState<boolean>(false);
  const [whatsappConsent, setWhatsappConsent] = useState<boolean>(false);
  const [isUpdatingNotif, setIsUpdatingNotif] = useState<boolean>(false);
  const [notifSuccess, setNotifSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    getUserProfile(token)
      .then((p) => {
        setProfile(p);
        if (p.full_name) setFullName(p.full_name);
        if (p.phone_number) setPhoneNumber(p.phone_number);
      })
      .catch((e) => console.error("Error refreshing profile:", e));

    getNotificationPreferences(token)
      .then((prefs) => {
        setNotifPrefs(prefs);
        setSmsConsent(prefs.sms_notifications_enabled);
        setWhatsappConsent(prefs.whatsapp_notifications_enabled);
      })
      .catch((e) => console.error("Error fetching notification preferences:", e));
  }, [token]);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setIsSaving(true);
    setSaveSuccess(false);
    setErrorMessage(null);

    try {
      const updated = await updateUserProfile(
        {
          full_name: fullName.trim() || undefined,
          phone_number: phoneNumber.trim() || undefined,
          preferred_language: language,
        },
        token
      );
      setProfile(updated);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 4000);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to update profile settings.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleToggleSms = async (enabled: boolean) => {
    if (!token) return;
    setIsUpdatingNotif(true);
    setNotifSuccess(null);
    try {
      const res = await updateSmsPreferences(
        { sms_notifications_enabled: enabled, phone_number: phoneNumber.trim() || undefined },
        token
      );
      setSmsConsent(res.sms_notifications_enabled);
      setNotifSuccess(
        enabled
          ? (language === "hi" ? "एसएमएस अलर्ट सहमति सुरक्षित रूप से दर्ज की गई।" : "SMS alert consent registered.")
          : (language === "hi" ? "एसएमएस अलर्ट बंद कर दिए गए हैं।" : "SMS alerts disabled.")
      );
      setTimeout(() => setNotifSuccess(null), 4000);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to update SMS preference.");
    } finally {
      setIsUpdatingNotif(false);
    }
  };

  const handleToggleWhatsApp = async (enabled: boolean) => {
    if (!token) return;
    setIsUpdatingNotif(true);
    setNotifSuccess(null);
    try {
      const res = await updateWhatsAppPreferences(
        { whatsapp_notifications_enabled: enabled, phone_number: phoneNumber.trim() || undefined },
        token
      );
      setWhatsappConsent(res.whatsapp_notifications_enabled);
      setNotifSuccess(
        enabled
          ? (language === "hi" ? "व्हाट्सएप अलर्ट सहमति दर्ज की गई।" : "WhatsApp alert consent registered.")
          : (language === "hi" ? "व्हाट्सएप अलर्ट बंद कर दिए गए हैं।" : "WhatsApp alerts disabled.")
      );
      setTimeout(() => setNotifSuccess(null), 4000);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to update WhatsApp preference.");
    } finally {
      setIsUpdatingNotif(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h2 className="text-2xl font-black text-white flex items-center gap-2">
          <span>👤</span> {language === "hi" ? "मेरी प्रोफ़ाइल एवं सेटिंग्स" : "My Profile & Account Settings"}
        </h2>
        <p className="text-xs text-gray-400 mt-0.5">
          {language === "hi"
            ? "अपनी व्यक्तिगत जानकारी, भाषा और अलर्ट सूचना प्राथमिकताओं का प्रबंधन करें।"
            : "Manage your authenticated account identity, language preference, and notification channels."}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Left Column: Account Card */}
        <div className="bg-[#17221b] border border-[#23352a] rounded-2xl p-6 text-center space-y-4">
          <div className="w-20 h-20 rounded-full bg-emerald-900/80 border-2 border-emerald-500/80 flex items-center justify-center text-4xl mx-auto text-white shadow-lg">
            {profile?.role === "expert" ? "🔬" : "👨‍🌾"}
          </div>

          <div>
            <h3 className="text-lg font-bold text-white tracking-tight">
              {profile?.full_name || "Signed-in User"}
            </h3>
            <p className="text-xs text-gray-400">{profile?.email || "Google Authenticated Identity"}</p>
          </div>

          <div className="pt-2 border-t border-[#23352a] space-y-2 text-xs text-left">
            <div className="flex justify-between items-center py-1">
              <span className="text-gray-400">Assigned Role:</span>
              <span className="font-mono font-bold uppercase px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 text-[11px]">
                {profile?.role || "farmer"}
              </span>
            </div>
            <div className="flex justify-between items-center py-1">
              <span className="text-gray-400">User ID:</span>
              <span className="font-mono text-[10px] text-gray-400 truncate max-w-[120px]">
                {profile?.id || "—"}
              </span>
            </div>
            {profile?.created_at && (
              <div className="flex justify-between items-center py-1">
                <span className="text-gray-400">Member Since:</span>
                <span className="text-[11px] text-gray-300">
                  {new Date(profile.created_at).toLocaleDateString()}
                </span>
              </div>
            )}
          </div>

          <div className="pt-4 border-t border-[#23352a]">
            <button
              onClick={onSignOut}
              className="w-full py-2.5 px-4 bg-[#231515] hover:bg-[#321c1c] text-rose-300 border border-rose-800/60 font-bold rounded-xl text-xs transition shadow"
            >
              🚪 {language === "hi" ? "लॉग आउट करें" : "Sign Out"}
            </button>
          </div>
        </div>

        {/* Right Column: Settings & Preferences */}
        <div className="md:col-span-2 space-y-6">
          {/* Personal Information Form */}
          <div className="bg-[#17221b] border border-[#23352a] rounded-2xl p-6 space-y-4">
            <h3 className="text-sm font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-2">
              <span>📝</span> {language === "hi" ? "व्यक्तिगत विवरण" : "Personal Information"}
            </h3>

            {saveSuccess && (
              <div className="p-3 bg-emerald-950/80 border border-emerald-800 rounded-xl text-emerald-200 text-xs">
                ✅ {language === "hi" ? "प्रोफ़ाइल सफलतापूर्वक अपडेट हो गई!" : "Profile updated successfully!"}
              </div>
            )}

            {errorMessage && (
              <div className="p-3 bg-rose-950/80 border border-rose-800 rounded-xl text-rose-200 text-xs">
                ⚠️ {errorMessage}
              </div>
            )}

            <form onSubmit={handleSaveProfile} className="space-y-4 text-xs">
              <div>
                <label className="block text-gray-300 font-semibold mb-1">
                  {language === "hi" ? "पूरा नाम" : "Full Name"}
                </label>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="e.g. Ramesh Patel"
                  className="w-full bg-[#121c15] border border-[#2d4034] rounded-xl px-3.5 py-2.5 text-white focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-gray-300 font-semibold mb-1">
                  {language === "hi" ? "फ़ोन नंबर (वैकल्पिक सूचनाओं के लिए)" : "Phone Number (Optional for Early Warnings)"}
                </label>
                <input
                  type="tel"
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  placeholder="+919876543210"
                  className="w-full bg-[#121c15] border border-[#2d4034] rounded-xl px-3.5 py-2.5 text-white focus:outline-none focus:border-emerald-500 font-mono"
                />
                <span className="text-[10px] text-gray-500 mt-1 block">
                  {language === "hi"
                    ? "मुख्य फसल पूर्वानुमान के लिए फ़ोन नंबर अनिवार्य नहीं है।"
                    : "Phone number is completely optional and never required for core crop prediction."}
                </span>
              </div>

              <div>
                <label className="block text-gray-300 font-semibold mb-1">
                  {language === "hi" ? "पसंदीदा भाषा" : "Preferred Language"}
                </label>
                <select
                  value={language}
                  onChange={(e) => onLanguageChange(e.target.value)}
                  className="w-full bg-[#121c15] border border-[#2d4034] rounded-xl px-3.5 py-2.5 text-white focus:outline-none focus:border-emerald-500"
                >
                  {Object.entries(SUPPORTED_LANGUAGES).map(([code, label]) => (
                    <option key={code} value={code}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  disabled={isSaving}
                  className="px-5 py-2.5 bg-emerald-800 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold rounded-xl transition shadow"
                >
                  {isSaving
                    ? (language === "hi" ? "सहेजा जा रहा है..." : "Saving...")
                    : (language === "hi" ? "परिवर्तन सहेजें" : "Save Changes")}
                </button>
              </div>
            </form>
          </div>

          {/* Early Warning & Alert Notification Preferences */}
          <div className="bg-[#17221b] border border-[#23352a] rounded-2xl p-6 space-y-4">
            <h3 className="text-sm font-bold uppercase tracking-wider text-amber-400 flex items-center gap-2">
              <span>🔔</span> {language === "hi" ? "चेतावनी सूचना प्राथमिकताएं" : "Notification & Early Warning Alerts"}
            </h3>

            {notifSuccess && (
              <div className="p-3 bg-emerald-950/80 border border-emerald-800 rounded-xl text-emerald-200 text-xs">
                ✅ {notifSuccess}
              </div>
            )}

            <p className="text-xs text-gray-400 leading-relaxed">
              {language === "hi"
                ? "जब आपके खेत में सूखे का तनाव या कीट संक्रमण जोखिम चरम स्तर को पार कर जाता है, तो समय पर चेतावनी प्राप्त करें। प्रत्येक चैनल के लिए अलग स्पष्ट सहमति आवश्यक है।"
                : "Receive timely field warnings when environmental drought stress or pest infestation metrics exceed critical thresholds. Each channel requires explicit, revocable consent."}
            </p>

            <div className="space-y-3 pt-2">
              {/* SMS Channel */}
              <div className="bg-[#121c15] border border-[#23352a] p-4 rounded-xl flex items-center justify-between gap-4">
                <div>
                  <h4 className="font-bold text-white text-xs flex items-center gap-2">
                    <span>📱</span> SMS Early Warning Alerts
                  </h4>
                  <p className="text-[11px] text-gray-400 mt-0.5">
                    Critical agro-climatic advisories sent via standard SMS.
                  </p>
                  {notifPrefs?.sms_consent_timestamp && (
                    <span className="text-[10px] text-gray-500 block mt-1">
                      Consent logged: {new Date(notifPrefs.sms_consent_timestamp).toLocaleString()}
                    </span>
                  )}
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={smsConsent}
                    disabled={isUpdatingNotif}
                    onChange={(e) => handleToggleSms(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
                </label>
              </div>

              {/* WhatsApp Channel */}
              <div className="bg-[#121c15] border border-[#23352a] p-4 rounded-xl flex items-center justify-between gap-4">
                <div>
                  <h4 className="font-bold text-white text-xs flex items-center gap-2">
                    <span>💬</span> WhatsApp Early Warning Alerts
                  </h4>
                  <p className="text-[11px] text-gray-400 mt-0.5">
                    Automated agronomic advisories and action recommendations on WhatsApp.
                  </p>
                  {notifPrefs?.whatsapp_consent_timestamp && (
                    <span className="text-[10px] text-gray-500 block mt-1">
                      Consent logged: {new Date(notifPrefs.whatsapp_consent_timestamp).toLocaleString()}
                    </span>
                  )}
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={whatsappConsent}
                    disabled={isUpdatingNotif}
                    onChange={(e) => handleToggleWhatsApp(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
                </label>
              </div>
            </div>

            <p className="text-[10px] text-gray-500 pt-2 border-t border-[#23352a]">
              🔒 Operational notice: Channels operate under strict test safeguards (<code>SMS_ENABLED=false</code>, <code>WHATSAPP_ENABLED=false</code>). Live dispatches are withheld.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
