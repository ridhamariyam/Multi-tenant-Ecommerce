import type { NextConfig } from "next";

const SECURITY_HEADERS = [
  { key: 'Strict-Transport-Security', value: 'max-age=31536000; includeSubDomains' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async redirects() {
    /* Shop entry points that have no page of their own. */
    return [
      ...['/shop', '/bestseller', '/bestsellers', '/best-sellers'].map(source => ({
        source,
        destination: '/products',
        permanent: false,
      })),
      /* The old ZEEN home is gone; the CliQ. runway at / is the home page. */
      { source: '/home', destination: '/', permanent: false },
      /* Duplicate template pages, removed: each URL lands on the one real page. */
      ...[
        ['/cart-items', '/cart'],
        ['/shop-cart', '/cart'],
        ['/check-out', '/checkout'],
        ['/my-account', '/account'],
        ['/my-orders', '/account/orders'],
        ['/payment-history', '/account/orders'],
        ['/order-details/:id*', '/account/orders'],
        ['/order-success/:id*', '/account/orders'],
        ['/invoice/:id*', '/account/orders'],
        ['/shop-wishlist', '/wishlist'],
        ['/shop-list', '/products'],
        ['/single-product/:id', '/products/:id'],
        ['/login', '/signin'],
        ['/signup', '/signin'],
        ['/registration', '/signin'],
        ['/otp-verification', '/signin'],
      ].map(([source, destination]) => ({ source, destination, permanent: true })),
    ];
  },
  async headers() {
    return [
      { source: '/:path*', headers: SECURITY_HEADERS },
      {
        source: '/signin',
        headers: [
          {
            key: 'Cross-Origin-Opener-Policy',
            value: 'same-origin-allow-popups',
          },
        ],
      },
    ];
  },
  images: {
    /* Product images are served by the API host, and the seed data by picsum. */

    remotePatterns: [
      { protocol: "https", hostname: "picsum.photos" },
      { protocol: "https", hostname: "fastly.picsum.photos" },
      { protocol: "http", hostname: "localhost", port: "58000" },
      { protocol: "https", hostname: "i.pinimg.com" },
    ],
  },
};

export default nextConfig;
