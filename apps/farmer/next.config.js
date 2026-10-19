const path = require("path");
const { loadEnvConfig } = require("@next/env");

// Load monorepo root environment variables (.env, .env.local) into Next.js runtime
// Must pass forceReload = true so it overrides any empty/stale process.env cached by Next.js cli
const projectRootDir = path.resolve(__dirname, "../../");
const { combinedEnv } = loadEnvConfig(projectRootDir, true, console, true);

// Explicitly provide NEXT_PUBLIC_* variables to nextConfig.env and process.env
const publicEnv = {};
if (combinedEnv) {
  for (const key in combinedEnv) {
    if (key.startsWith("NEXT_PUBLIC_")) {
      publicEnv[key] = combinedEnv[key];
      process.env[key] = combinedEnv[key];
    }
  }
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@crop-risk/shared"],
  outputFileTracingRoot: projectRootDir,
  env: publicEnv,
  webpack: (config) => {
    config.resolve.alias["@shared"] = path.resolve(__dirname, "../shared");
    return config;
  },
};

module.exports = nextConfig;
