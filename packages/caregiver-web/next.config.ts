import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const engineUrl = process.env.MEMORY_ENGINE_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/engine/:path*",
        destination: `${engineUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
