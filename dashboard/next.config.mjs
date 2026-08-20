/** @type {import('next').NextConfig} */
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const nextConfig = {
  reactStrictMode: true,
  typedRoutes: false,
  outputFileTracingRoot: path.join(__dirname),
  async rewrites() {
    const agentUrl = process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8000";
    const homekitUrl = process.env.NEXT_PUBLIC_HOMEKIT_URL ?? "http://localhost:51827";
    const devicesUrl = process.env.NEXT_PUBLIC_DEVICES_URL ?? "http://localhost:8002";
    return [
      { source: "/api/agent/:path*", destination: `${agentUrl}/:path*` },
      { source: "/api/homekit/:path*", destination: `${homekitUrl}/:path*` },
      { source: "/api/devices/:path*", destination: `${devicesUrl}/:path*` },
    ];
  },
};

export default nextConfig;
