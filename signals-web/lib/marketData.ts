import { Candle, Timeframe, MarketDataBundle } from './types';

/**
 * Market Data Client supporting:
 * 1. TwelveData API (Free tier: 800 credits/day, supports XAU/USD and BTC/USD)
 * 2. Binance Public API (100% Free, real-time OHLCV for BTCUSDT, no API key required)
 * 3. Fallback Synthesizer / Local Cache (guarantees scanner and UI always operate smoothly)
 */

const TWELVE_DATA_API_KEY = process.env.TWELVE_DATA_API_KEY || '';

/**
 * Maps timeframe string to TwelveData interval
 */
function toTwelveDataInterval(tf: Timeframe): string {
  switch (tf) {
    case '30m':
      return '30min';
    case '1h':
      return '1h';
    case '4h':
      return '4h';
    default:
      return '1h';
  }
}

/**
 * Maps timeframe string to Binance interval
 */
function toBinanceInterval(tf: Timeframe): string {
  switch (tf) {
    case '30m':
      return '30m';
    case '1h':
      return '1h';
    case '4h':
      return '4h';
    default:
      return '1h';
  }
}

/**
 * Fetch candles from Binance Public Spot API (Free, no key required)
 */
async function fetchBinanceCandles(timeframe: Timeframe, count: number = 60): Promise<Candle[] | null> {
  try {
    const interval = toBinanceInterval(timeframe);
    const url = `https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=${interval}&limit=${count}`;
    const res = await fetch(url, { next: { revalidate: 60 } });
    if (!res.ok) return null;

    const data = await res.json();
    if (!Array.isArray(data)) return null;

    return data.map((item: any) => ({
      time: Math.floor(item[0] / 1000),
      open: parseFloat(item[1]),
      high: parseFloat(item[2]),
      low: parseFloat(item[3]),
      close: parseFloat(item[4]),
      volume: parseFloat(item[5]),
    }));
  } catch (e) {
    console.warn(`[MarketData] Binance fetch failed for BTC ${timeframe}:`, e);
    return null;
  }
}

/**
 * Fetch candles from TwelveData API
 */
async function fetchTwelveDataCandles(
  symbol: 'XAUUSD' | 'BTCUSD',
  timeframe: Timeframe,
  count: number = 60
): Promise<Candle[] | null> {
  if (!TWELVE_DATA_API_KEY) return null;

  try {
    const twSymbol = symbol === 'XAUUSD' ? 'XAU/USD' : 'BTC/USD';
    const interval = toTwelveDataInterval(timeframe);
    const url = `https://api.twelvedata.com/time_series?symbol=${encodeURIComponent(
      twSymbol
    )}&interval=${interval}&outputsize=${count}&apikey=${TWELVE_DATA_API_KEY}`;

    const res = await fetch(url, { next: { revalidate: 60 } });
    if (!res.ok) return null;

    const data = await res.json();
    if (!data.values || !Array.isArray(data.values)) return null;

    // TwelveData returns newest first -> reverse to oldest first
    const reversed = [...data.values].reverse();
    return reversed.map((item: any) => ({
      time: Math.floor(new Date(item.datetime).getTime() / 1000),
      open: parseFloat(item.open),
      high: parseFloat(item.high),
      low: parseFloat(item.low),
      close: parseFloat(item.close),
      volume: item.volume ? parseFloat(item.volume) : 100,
    }));
  } catch (e) {
    console.warn(`[MarketData] TwelveData fetch failed for ${symbol} ${timeframe}:`, e);
    return null;
  }
}

/**
 * Fallback realistic candle generator
 * Guarantees zero downtime and lets you test scanner & dashboard offline
 */
export function generateSyntheticCandles(
  symbol: 'XAUUSD' | 'BTCUSD',
  timeframe: Timeframe,
  count: number = 60
): Candle[] {
  const isGold = symbol === 'XAUUSD';
  const basePrice = isGold ? 2735.0 : 92500.0;
  const volatility = isGold ? 1.2 : 120.0;
  const tfMinutes = timeframe === '4h' ? 240 : timeframe === '1h' ? 60 : 30;

  const nowSeconds = Math.floor(Date.now() / 1000);
  const candles: Candle[] = [];

  let currentPrice = basePrice;
  for (let i = count - 1; i >= 0; i--) {
    const time = nowSeconds - i * tfMinutes * 60;
    const change = (Math.sin(i * 0.4) + (Math.random() - 0.48)) * volatility;
    const open = currentPrice;
    const close = open + change;
    const high = Math.max(open, close) + Math.abs(Math.random() * volatility * 0.6);
    const low = Math.min(open, close) - Math.abs(Math.random() * volatility * 0.6);

    candles.push({
      time,
      open: Number(open.toFixed(2)),
      high: Number(high.toFixed(2)),
      low: Number(low.toFixed(2)),
      close: Number(close.toFixed(2)),
      volume: Math.floor(Math.random() * 500) + 50,
    });
    currentPrice = close;
  }

  return candles;
}

/**
 * Fetches 4H, 1H, and 30M candles for a symbol
 */
export async function fetchMarketDataBundle(
  symbol: 'XAUUSD' | 'BTCUSD'
): Promise<MarketDataBundle> {
  const timeframes: Timeframe[] = ['4h', '1h', '30m'];
  const bundleResult: Record<string, Candle[]> = {};

  for (const tf of timeframes) {
    let candles: Candle[] | null = null;

    // For BTC, Binance public API is fast and free
    if (symbol === 'BTCUSD') {
      candles = await fetchBinanceCandles(tf, 60);
    }

    // Try TwelveData if available
    if (!candles && TWELVE_DATA_API_KEY) {
      candles = await fetchTwelveDataCandles(symbol, tf, 60);
    }

    // Fallback if APIs are unconfigured or throttled
    if (!candles || candles.length < 20) {
      candles = generateSyntheticCandles(symbol, tf, 60);
    }

    bundleResult[tf] = candles;
  }

  return {
    symbol,
    timeframes: {
      '4h': bundleResult['4h'],
      '1h': bundleResult['1h'],
      '30m': bundleResult['30m'],
    },
  };
}
