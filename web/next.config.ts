import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      // The transaction history moved onto the activity page when the dashboard was split
      // up. Keep the old link working rather than 404ing anyone's bookmark.
      { source: "/transactions", destination: "/activity", permanent: true },
    ];
  },
};

export default nextConfig;
