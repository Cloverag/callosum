import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow HMR / dev resources when the app is opened via the LAN IP, not just localhost.
  allowedDevOrigins: ["192.168.29.45"],
};

export default nextConfig;
