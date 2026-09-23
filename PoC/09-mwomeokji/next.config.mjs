/** @type {import('next').NextConfig} */
const nextConfig = {
  basePath: '/poc/mwomeokji',
  trailingSlash: true,
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [{ source: '/:path*', headers: [
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'Referrer-Policy', value: 'no-referrer' },
      { key: 'Permissions-Policy', value: 'microphone=(self), camera=()' }
    ] }];
  }
};
export default nextConfig;
