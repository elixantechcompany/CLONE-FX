import { fetchTradingViewSnapshot, fetchMarketDataBundle } from '../lib/marketData.js';
import { runConfluenceScan, evaluateD1Bias, evaluate4HSetup, evaluate1HTrigger } from '../lib/confluenceEngine.js';

async function test() {
  console.log("Testing TradingView Snapshot for XAUUSD...");
  try {
    const snap = await fetchTradingViewSnapshot('XAUUSD');
    console.log("TV Snapshot XAUUSD:", JSON.stringify(snap, null, 2));
  } catch (e) {
    console.error("TV Snapshot failed:", e);
  }

  console.log("\nTesting MarketDataBundle for XAUUSD...");
  try {
    const bundle = await fetchMarketDataBundle('XAUUSD');
    console.log("Bundle timeframes:", Object.keys(bundle.timeframes));
    console.log("D1 candle count:", bundle.timeframes['1d']?.length);
    console.log("4H candle count:", bundle.timeframes['4h']?.length);
    console.log("1H candle count:", bundle.timeframes['1h']?.length);

    const bias = evaluateD1Bias(bundle.timeframes['1d'] || bundle.timeframes['4h']);
    console.log("Bias D1:", bias);

    const setup = evaluate4HSetup(bundle.timeframes['4h'], bias);
    console.log("Setup 4H:", setup);

    const trigger = evaluate1HTrigger(bundle.timeframes['1h'], bias, setup);
    console.log("Trigger 1H:", trigger);

    const signal = runConfluenceScan(bundle);
    console.log("Signal result:", signal);
  } catch (e) {
    console.error("Bundle scan failed:", e);
  }
}

test();
