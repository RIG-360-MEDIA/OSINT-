import type { NextConfig } from "next";

const WM_INTERNAL_URL = process.env.WM_INTERNAL_URL || "http://rig-worldmonitor:8080";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/world-monitor-app/:path*",
        destination: `${WM_INTERNAL_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
