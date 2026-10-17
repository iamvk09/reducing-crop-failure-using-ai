"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@shared/context/AuthContext";

export default function HomePage() {
  const { user, role, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading) {
      if (!user) {
        router.push("/login");
      } else {
        router.push("/dashboard");
      }
    }
  }, [user, isLoading, router]);

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="text-center">
        <div className="inline-block animate-spin text-4xl mb-3">🌱</div>
        <p className="text-base font-semibold text-gray-700">Loading Crop Risk Platform...</p>
      </div>
    </div>
  );
}
