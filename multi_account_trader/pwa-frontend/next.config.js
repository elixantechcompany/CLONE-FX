/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  // PWA configuration will be added with next-pwa plugin
  experimental: {
    optimizeCss: true,
  },
}

module.exports = nextConfig