import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'XAUUSD / BTCUSD Signals — Prop Firm Terminal',
  description:
    'Institutional 3-timeframe confluence scanning system for Gold and Bitcoin with manual review workflow.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
