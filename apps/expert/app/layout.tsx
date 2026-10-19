import React from "react";
import { AuthProvider } from "@shared/context/AuthContext";
import { UserLocationProvider } from "@shared/context/UserLocationContext";
import "../../farmer/app/globals.css";

export const metadata = {
  title: "AI Crop Risk Intelligence | Expert Workbench",
  description: "Agronomic risk analysis, SHAP model explainability, and Digital Twin stress simulations.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const publicSupabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
  const publicSupabaseKey =
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
    "";

  return (
    <html lang="en">
      <head>
        <script
          id="supabase-client-env"
          dangerouslySetInnerHTML={{
            __html: `window.NEXT_PUBLIC_SUPABASE_URL = ${JSON.stringify(
              publicSupabaseUrl
            )}; window.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = ${JSON.stringify(
              publicSupabaseKey
            )};`,
          }}
        />
      </head>
      <body className="bg-slate-100 text-slate-900 min-h-screen flex flex-col antialiased">
        <AuthProvider>
          <UserLocationProvider>{children}</UserLocationProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
