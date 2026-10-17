"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@shared/context/AuthContext";

export default function AuthCallbackPage() {
  const router = useRouter();
  const { user, role } = useAuth();

  useEffect(() => {
    // Process OAuth token and redirect
    if (user) {
      if (role === "farmer") {
        router.push("/farmer");
      } else {
        router.push("/farmer");
      }
    } else {
      router.push("/login");
    }
  }, [user, role, router]);

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="text-center">
        <div className="inline-block animate-spin text-4xl mb-3">🔄</div>
        <p className="text-base font-semibold text-gray-700">Verifying authenticated session...</p>
      </div>
    </div>
  );
}
