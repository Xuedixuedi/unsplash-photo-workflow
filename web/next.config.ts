import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Sentry is optional and starts from instrumentation.ts only when SENTRY_DSN is set.
  // next.config is intentionally not wrapped by a Sentry plugin.
  serverExternalPackages: ["@neondatabase/serverless"],
};

export default nextConfig;
