'use client';

import { useState, useEffect } from 'react';
import { supabase } from '@/lib/supabase';
import { TradingSignal } from '@/lib/types';

export default function SignalsPage() {
  const [signals, setSignals] = useState<TradingSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  const fetchSignals = async () => {
    try {
      const response = await fetch('/api/signals?limit=10');
      const data = await response.json();
      setSignals(data.signals || []);
    } catch (error) {
      console.error('Error fetching signals:', error);
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopyFeedback(label);
    setTimeout(() => setCopyFeedback(null), 2000);
  };

  const copyFullSignal = (signal: TradingSignal) => {
    const signalText = `${signal.direction} ${signal.symbol}\nEntry: ${signal.entry_price}\nSL: ${signal.stop_loss}\nTP: ${signal.take_profit}\nR:R: ${signal.risk_reward_ratio.toFixed(2)}`;
    copyToClipboard(signalText, 'Full signal copied!');
  };

  useEffect(() => {
    fetchSignals();
    // Refresh signals every 30 seconds
    const interval = setInterval(fetchSignals, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-400">Loading trading signals...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black text-white p-4 pb-24">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-amber-500 mb-2">Trading Signals</h1>
        <p className="text-gray-400 text-sm">Real-time signals with 5-minute freshness</p>
      </div>

      {/* Copy Feedback */}
      {copyFeedback && (
        <div className="bg-green-900/50 border border-green-500 text-green-200 p-3 rounded-xl mb-4 text-center">
          {copyFeedback}
        </div>
      )}

      {/* Signals List */}
      {signals.length === 0 ? (
        <div className="bg-gray-900 rounded-xl p-8 text-center border border-gray-800">
          <p className="text-gray-400 mb-4">No active signals available</p>
          <p className="text-gray-500 text-sm">Signals are generated when market conditions align with the 50 EMA strategy</p>
        </div>
      ) : (
        <div className="space-y-4">
          {signals.map((signal) => {
            const freshness = signal.freshness;
            const isExpired = !freshness?.is_fresh;
            const directionColor = signal.direction === 'BUY' ? 'text-green-500' : 'text-red-500';
            const bgColor = signal.direction === 'BUY' ? 'bg-green-900/20' : 'bg-red-900/20';
            const borderColor = signal.direction === 'BUY' ? 'border-green-500/30' : 'border-red-500/30';

            return (
              <div
                key={signal.id}
                className={`${bgColor} rounded-xl p-4 border ${borderColor} transition-all`}
                style={{
                  opacity: isExpired ? 0.3 : (freshness?.opacity || 1),
                  filter: isExpired ? 'grayscale(100%)' : 'none'
                }}
              >
                {/* Signal Header */}
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-2xl font-bold ${directionColor}`}>
                        {signal.direction}
                      </span>
                      <span className="text-gray-400 text-sm">{signal.symbol}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs px-2 py-1 rounded ${
                        isExpired ? 'bg-gray-700 text-gray-400' : 'bg-amber-500/20 text-amber-500'
                      }`}>
                        {isExpired ? 'EXPIRED' : 'ACTIVE'}
                      </span>
                      <span className="text-xs text-gray-400">
                        {freshness?.age_text || 'Unknown'}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={() => copyFullSignal(signal)}
                    className="bg-amber-500/20 hover:bg-amber-500/30 text-amber-500 px-3 py-1 rounded-lg text-sm font-medium transition-colors"
                  >
                    Copy All
                  </button>
                </div>

                {/* Signal Parameters */}
                <div className="grid grid-cols-3 gap-3 mb-3">
                  <div className="bg-black/30 rounded-lg p-3">
                    <p className="text-gray-400 text-xs mb-1">Entry</p>
                    <div className="flex items-center justify-between">
                      <p className="text-lg font-bold text-white">{signal.entry_price.toFixed(2)}</p>
                      <button
                        onClick={() => copyToClipboard(signal.entry_price.toFixed(2), 'Entry copied!')}
                        className="text-gray-400 hover:text-amber-500 transition-colors"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                      </button>
                    </div>
                  </div>
                  <div className="bg-black/30 rounded-lg p-3">
                    <p className="text-gray-400 text-xs mb-1">Stop Loss</p>
                    <div className="flex items-center justify-between">
                      <p className="text-lg font-bold text-red-500">{signal.stop_loss.toFixed(2)}</p>
                      <button
                        onClick={() => copyToClipboard(signal.stop_loss.toFixed(2), 'SL copied!')}
                        className="text-gray-400 hover:text-amber-500 transition-colors"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                      </button>
                    </div>
                  </div>
                  <div className="bg-black/30 rounded-lg p-3">
                    <p className="text-gray-400 text-xs mb-1">Take Profit</p>
                    <div className="flex items-center justify-between">
                      <p className="text-lg font-bold text-green-500">{signal.take_profit.toFixed(2)}</p>
                      <button
                        onClick={() => copyToClipboard(signal.take_profit.toFixed(2), 'TP copied!')}
                        className="text-gray-400 hover:text-amber-500 transition-colors"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>

                {/* Additional Info */}
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div className="flex justify-between items-center bg-black/20 rounded-lg p-2">
                    <span className="text-gray-400 text-xs">Risk/Reward</span>
                    <span className="text-amber-500 font-bold">1:{signal.risk_reward_ratio.toFixed(1)}</span>
                  </div>
                  <div className="flex justify-between items-center bg-black/20 rounded-lg p-2">
                    <span className="text-gray-400 text-xs">ATR Value</span>
                    <span className="text-white font-medium">{signal.atr_value?.toFixed(2) || 'N/A'}</span>
                  </div>
                </div>

                {/* Trend Info */}
                <div className="bg-black/20 rounded-lg p-3 mb-3">
                  <p className="text-gray-400 text-xs mb-2">Trend Alignment</p>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="flex justify-between">
                      <span className="text-gray-400">H4 EMA50:</span>
                      <span className={signal.h4_price_above_ema ? 'text-green-500' : 'text-red-500'}>
                        {signal.h4_price_above_ema ? 'Above' : 'Below'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">H1 EMA50:</span>
                      <span className={signal.h1_price_above_ema ? 'text-green-500' : 'text-red-500'}>
                        {signal.h1_price_above_ema ? 'Above' : 'Below'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Timestamp */}
                <div className="text-center">
                  <p className="text-xs text-gray-500">
                    Generated: {new Date(signal.created_at).toLocaleString()}
                  </p>
                  {isExpired && (
                    <p className="text-xs text-red-400 mt-1">
                      This signal has expired and should not be used for trading
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Refresh Button */}
      <button
        onClick={fetchSignals}
        className="w-full mt-6 bg-gray-800 hover:bg-gray-700 text-white font-semibold py-3 rounded-xl border border-gray-700 transition-colors"
      >
        Refresh Signals
      </button>

      {/* Bottom Navigation */}
      <div className="fixed bottom-0 left-0 right-0 bg-gray-900 border-t border-gray-800 p-4">
        <div className="flex justify-around">
          <button className="flex flex-col items-center text-gray-400">
            <svg className="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
            </svg>
            <span className="text-xs">Dashboard</span>
          </button>
          <button className="flex flex-col items-center text-amber-500">
            <svg className="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
            <span className="text-xs">Signals</span>
          </button>
          <button className="flex flex-col items-center text-gray-400">
            <svg className="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <span className="text-xs">Accounts</span>
          </button>
        </div>
      </div>
    </div>
  );
}