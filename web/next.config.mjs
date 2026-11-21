/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["three", "urdf-loader"],
  // Tipos correctos para los modelos de realidad aumentada (/sala): AR Quick Look espera model/vnd.usdz+zip.
  async headers() {
    return [
      { source: "/ar/:archivo*.usdz", headers: [{ key: "Content-Type", value: "model/vnd.usdz+zip" }] },
      { source: "/ar/:archivo*.glb", headers: [{ key: "Content-Type", value: "model/gltf-binary" }] },
    ];
  },
};

export default nextConfig;
