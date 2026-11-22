/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  distDir: process.env.VIAZ_NEXT_DIST_DIR || ".next",
  async headers() {
    return [{
      source: "/viaz/kr210-portada.247ff18b.glb",
      headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
    }];
  },
  transpilePackages: ["three", "urdf-loader"],
};

export default nextConfig;
