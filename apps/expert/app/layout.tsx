import React from "react";
import { AuthProvider } from "@shared/context/AuthContext";
import { UserLocationProvider } from "@shared/context/UserLocationContext";
import "../../farmer/app/globals.css";

export const metadata = {
  title: "AI Crop Risk Intelligence | Expert Workbench",
  description: "Agronomic risk analysis, SHAP model explainability, and Digital Twin stress simulations.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-100 text-slate-900 min-h-screen flex flex-col antialiased">
        <AuthProvider>
          <UserLocationProvider>{children}</UserLocationProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
