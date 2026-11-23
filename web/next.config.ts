import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false, // no anunciar «Next.js» (revisión de seguridad 2026-11-22, M5)
};

export default nextConfig;
