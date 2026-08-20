/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    typedRoutes: false,
  },
  async rewrites() {
    const agentUrl = process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8000";
    const homekitUrl = process.env.NEXT_PUBLIC_HOMEKIT_URL ?? "http://localhost:51827";
    return [
      { source: "/api/agent/:path*", destination: `${agentUrl}/:path*` },
      { source: "/api/homekit/:path*", destination: `${homekitUrl}/:path*` },
    ];
  },
};

export default nextConfig;