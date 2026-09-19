import './globals.css';
import type { Metadata, Viewport } from 'next';

export const viewport: Viewport = {
  themeColor: '#07080b',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: 'cover',
};

export const metadata: Metadata = {
  title: 'GOLD CLONE FX — Institutional Trading Terminal',
  description:
    'Institutional 3-timeframe confluence scanning & automated execution engine for Gold (XAUUSD) & Bitcoin (BTCUSD).',
  manifest: '/manifest.json',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'GOLD CLONE FX',
  },
  icons: {
    icon: '/icon.svg',
    apple: '/icon-192.png',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="manifest" href="/manifest.json" />
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="theme-color" content="#07080b" />
      </head>
      <body>{children}</body>
    </html>
  );
}

