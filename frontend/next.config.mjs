/** @type {import('next').NextConfig} */
// Rewrites run on the Next.js server. Local development uses the documented
// host port; the frontend Docker image sets BACKEND_URL at build time to the
// backend service address on the Compose network.
const BACKEND_URL = (
  process.env.BACKEND_URL || process.env.API_INTERNAL_URL || "http://localhost:2357"
).replace(/\/$/, "");

const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // Proxying through Next keeps browser API requests same-origin.
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${BACKEND_URL}/api/v1/:path*` },
    ];
  },
};

export default nextConfig;
