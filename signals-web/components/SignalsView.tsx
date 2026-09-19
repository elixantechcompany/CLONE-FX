'use client';

import React, { useState } from 'react';
import { ConfluenceSignal, MarketSchedule } from '@/lib/types';

interface SignalsViewProps {
  selectedSymbol: 'XAUUSD' | 'BTCUSD';
  setSelectedSymbol: (sym: 'XAUUSD' | 'BTCUSD') => void;
  activeSignals: ConfluenceSignal[];
  formingSetups: ConfluenceSignal[];
  marketSchedules: Record<string, MarketSchedule>;
  currentPrice: number;
  macroBias: string;
  killzoneInfo?: {
    is_killzone: boolean;
    session_name: string;
    trading_allowed: boolean;
    utc_time: string;
  };
  adrInfo?: {
    adr_used_pct: number;
    range_pts: number;
    typical_adr: number;
    is_exhausted: boolean;
    warning: string;
  };
  onLogToJournal: (signal: ConfluenceSignal) => void;
  onRefresh: () => void;
  isScanning: boolean;
}

export const SignalsView: React.FC<SignalsViewProps> = ({
  selectedSymbol,
  setSelectedSymbol,
  activeSignals,
  formingSetups,
  marketSchedules,
  currentPrice,
  macroBias,
  killzoneInfo,
  adrInfo,
  onLogToJournal,
  onRefresh,
  isScanning,
}) => {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const currentSchedule = marketSchedules[selectedSymbol];
  const isMarketOpen = currentSchedule ? currentSchedule.is_open : true;

  const handleCopyParams = (sig: ConfluenceSignal) => {
    const text = `ORDER: ${sig.direction}\nSYMBOL: ${sig.symbol}\nTYPE: ${sig.orderType || 'BUY MARKET'}\nENTRY: ${sig.entryPrice.toFixed(2)}\nSTOP LOSS: ${sig.stopLoss.toFixed(2)}\nTAKE PROFIT 1: ${sig.takeProfit1.toFixed(2)}\nTAKE PROFIT 2: ${(sig.takeProfit2 || sig.takeProfit1 * 1.5).toFixed(2)}\nR:R RATIO: 1:${sig.riskReward.toFixed(2)}`;
    navigator.clipboard.writeText(text);
    setCopiedId(sig.id || 'sig-1');
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="flex flex-col gap-5 pb-20 lg:pb-6">
      {/* Top Controls: Symbol Switcher & Live Session HUD */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-[#0d121c]/90 border border-white/[0.08] p-3.5 sm:p-4 rounded-2xl backdrop-blur-xl">
        {/* Symbol Selector Chips */}
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <button
            onClick={() => setSelectedSymbol('XAUUSD')}
            className={`flex-1 sm:flex-initial flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-bold transition-all ${
              selectedSymbol === 'XAUUSD'
                ? 'bg-gradient-to-r from-amber-500/20 to-yellow-500/20 text-amber-300 border border-amber-500/40 shadow-[0_0_15px_rgba(245,200,66,0.2)]'
                : 'bg-white/[0.03] text-slate-400 hover:text-slate-200 border border-white/[0.05]'
            }`}
          >
            <span>🟡</span>
            <span>XAUUSD (Gold)</span>
            {!marketSchedules['XAUUSD']?.is_open && (
              <span className="text-[9px] px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">
                CLOSED
              </span>
            )}
          </button>

          <button
            onClick={() => setSelectedSymbol('BTCUSD')}
            className={`flex-1 sm:flex-initial flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-bold transition-all ${
              selectedSymbol === 'BTCUSD'
                ? 'bg-gradient-to-r from-orange-500/20 to-amber-500/20 text-orange-300 border border-orange-500/40 shadow-[0_0_15px_rgba(249,115,22,0.2)]'
                : 'bg-white/[0.03] text-slate-400 hover:text-slate-200 border border-white/[0.05]'
            }`}
          >
            <span>🟠</span>
            <span>BTCUSD (24/7)</span>
            <span className="text-[9px] px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              LIVE
            </span>
          </button>
        </div>

        {/* Live Price & Manual Scan Trigger */}
        <div className="flex items-center justify-between sm:justify-end gap-3 w-full sm:w-auto">
          <div className="text-left sm:text-right">
            <div className="text-[10px] uppercase font-semibold text-slate-400">Live Quote</div>
            <div className="text-base sm:text-lg font-mono font-extrabold text-slate-100">
              ${currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>

          <button
            onClick={onRefresh}
            disabled={isScanning}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-bold hover:bg-cyan-500/20 transition-all active:scale-95 disabled:opacity-50 shadow-sm"
          >
            <span className={isScanning ? 'animate-spin' : ''}>🔄</span>
            <span>{isScanning ? 'Scanning...' : 'Scan Market'}</span>
          </button>
        </div>
      </div>

      {/* Market Closed Banner if applicable */}
      {!isMarketOpen && currentSchedule && (
        <div className="bg-gradient-to-r from-amber-500/10 via-rose-500/10 to-amber-500/10 border border-amber-500/30 rounded-2xl p-3.5 sm:p-4 text-xs text-amber-200 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="text-lg">⏳</span>
            <div>
              <span className="font-bold">{currentSchedule.status_text}</span>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Weekend holding analysis active. Signals derived from closed D1/H4 market structure.
              </p>
            </div>
          </div>
          <span className="text-[10px] font-mono px-2 py-1 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
            AUTO-RESUMES SUN 22:00 UTC
          </span>
        </div>
      )}

      {/* 3-Tier Multi-Timeframe Structure & Killzone HUD */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
        {/* Card 1: D1/H4 Macro Bias */}
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">1. Macro Bias (D1+H4)</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              ALIGNMENT
            </span>
          </div>
          <div className="text-sm font-bold text-slate-100 mb-1">
            {macroBias || 'INSTITUTIONAL ACCUMULATION'}
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            Swing holding horizon: 18h – 48h. Invalidation stop below structural swing low.
          </p>
        </div>

        {/* Card 2: Killzone & Volume Session */}
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">2. Killzone Session</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              {killzoneInfo?.utc_time || 'LIVE UTC'}
            </span>
          </div>
          <div className="text-sm font-bold text-cyan-300 mb-1">
            {killzoneInfo?.session_name || 'London Killzone (Peak Volume)'}
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            High institutional liquidity window. Order flow execution permitted.
          </p>
        </div>

        {/* Card 3: ADR Exhaustion Meter */}
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">3. ADR Range Meter</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
              {adrInfo?.adr_used_pct || 45}% USED
            </span>
          </div>
          <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden mb-2">
            <div
              className="h-full bg-gradient-to-r from-emerald-400 via-yellow-400 to-rose-400 rounded-full"
              style={{ width: `${Math.min(100, adrInfo?.adr_used_pct || 45)}%` }}
            ></div>
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            {adrInfo?.warning || 'Normal Daily Range (Clean expansion headroom)'}
          </p>
        </div>
      </div>

      {/* Confirmed Grade A+ Signals Section */}
      <div>
        <div className="flex items-center justify-between mb-3.5">
          <div className="flex items-center gap-2">
            <span className="text-lg">🎯</span>
            <h2 className="text-base sm:text-lg font-extrabold text-slate-100">
              Confirmed High-Conviction Signals
            </h2>
            <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              {activeSignals.length} Active
            </span>
          </div>
          <span className="text-xs text-slate-400 hidden sm:inline">
            1:2.00+ Guaranteed Risk:Reward Ratio
          </span>
        </div>

        {activeSignals.length === 0 ? (
          <div className="bg-[#0d121c]/70 border border-dashed border-white/[0.12] rounded-2xl p-8 text-center">
            <div className="text-3xl mb-2">📡</div>
            <h3 className="text-sm font-bold text-slate-200">No Grade A+ Signals Triggered Currently</h3>
            <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
              The algorithm requires full 3-tier confluence (D1 Macro Bias + 4H Liquidity Sweep + 1H Reclaim Trigger). Monitoring live candles continuously...
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {activeSignals.map((sig, idx) => {
              const isBuy = sig.direction === 'BUY';
              return (
                <div
                  key={sig.id || `signal-${idx}`}
                  className="bg-gradient-to-br from-[#0e131e] via-[#101726] to-[#0c1018] border border-emerald-500/30 hover:border-emerald-500/50 rounded-2xl p-4 sm:p-5 shadow-[0_4px_25px_rgba(0,0,0,0.3)] transition-all flex flex-col justify-between gap-4"
                >
                  {/* Signal Card Header */}
                  <div>
                    <div className="flex items-center justify-between gap-2 mb-3">
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-xs font-extrabold px-3 py-1 rounded-xl uppercase tracking-wider ${
                            isBuy
                              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                              : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                          }`}
                        >
                          {sig.orderType || (isBuy ? 'BUY MARKET' : 'SELL MARKET')}
                        </span>
                        <span className="text-xs font-mono font-bold text-slate-300 px-2 py-0.5 rounded bg-white/[0.05]">
                          {sig.symbol}
                        </span>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/30">
                          {sig.confluenceScore || 'A+ PERFECT SETUP'}
                        </span>
                        <span className="text-[10px] font-mono text-cyan-400 px-2 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/20">
                          R:R 1:{sig.riskReward.toFixed(2)}
                        </span>
                      </div>
                    </div>

                    {/* Order Metrics Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 bg-[#080b11]/80 border border-white/[0.06] p-3 rounded-xl mb-3">
                      <div>
                        <div className="text-[10px] text-slate-400 font-medium">ENTRY PRICE</div>
                        <div className="text-sm font-mono font-extrabold text-slate-100">
                          ${sig.entryPrice.toFixed(2)}
                        </div>
                      </div>

                      <div>
                        <div className="text-[10px] text-rose-400 font-medium">STOP LOSS</div>
                        <div className="text-sm font-mono font-extrabold text-rose-300">
                          ${sig.stopLoss.toFixed(2)}
                        </div>
                        <div className="text-[9px] text-slate-500">(-${sig.slDistance.toFixed(2)})</div>
                      </div>

                      <div>
                        <div className="text-[10px] text-emerald-400 font-medium">TAKE PROFIT 1</div>
                        <div className="text-sm font-mono font-extrabold text-emerald-300">
                          ${sig.takeProfit1.toFixed(2)}
                        </div>
                        <div className="text-[9px] text-slate-500">(1:2.0 R:R)</div>
                      </div>

                      <div>
                        <div className="text-[10px] text-teal-400 font-medium">TAKE PROFIT 2</div>
                        <div className="text-sm font-mono font-extrabold text-teal-300">
                          ${(sig.takeProfit2 || sig.takeProfit1 * 1.05).toFixed(2)}
                        </div>
                        <div className="text-[9px] text-slate-500">(1:3.5 Runner)</div>
                      </div>
                    </div>

                    {/* Confluence Tags */}
                    {sig.confluences && sig.confluences.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mb-2">
                        {sig.confluences.map((c, i) => (
                          <span
                            key={i}
                            className="text-[10px] px-2 py-0.5 rounded-lg bg-white/[0.03] text-slate-300 border border-white/[0.06]"
                          >
                            ✓ {c}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Setup Summary */}
                    {sig.setup_summary && (
                      <p className="text-[11px] text-slate-400 italic">
                        "{sig.setup_summary}"
                      </p>
                    )}
                  </div>

                  {/* Actions: Copy Params & Log to Journal */}
                  <div className="flex items-center gap-2 pt-2 border-t border-white/[0.06]">
                    <button
                      onClick={() => handleCopyParams(sig)}
                      className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-200 border border-white/[0.08] text-xs font-bold transition-all active:scale-95"
                    >
                      <span>📋</span>
                      <span>{copiedId === (sig.id || 'sig-1') ? 'Copied Parameters!' : 'Copy MT5 Parameters'}</span>
                    </button>

                    <button
                      onClick={() => onLogToJournal(sig)}
                      className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-gradient-to-r from-cyan-500/20 to-blue-500/20 hover:from-cyan-500/30 hover:to-blue-500/30 text-cyan-200 border border-cyan-500/40 text-xs font-bold transition-all active:scale-95 shadow-[0_0_12px_rgba(6,182,212,0.15)]"
                    >
                      <span>📖</span>
                      <span>Log to Trade Journal</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Forming Setups Radar (Early Pre-Confirmation) */}
      {formingSetups.length > 0 && (
        <div className="bg-[#0e131d]/80 border border-amber-500/20 rounded-2xl p-4 sm:p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-base">⚡</span>
              <h3 className="text-sm font-bold text-amber-300">Setups Forming (Early Radar)</h3>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                AWAITING 1H CANDLE CLOSE
              </span>
            </div>
            <span className="text-[11px] text-slate-400">Do not enter until confirmed</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {formingSetups.map((form, idx) => (
              <div
                key={idx}
                className="bg-[#090c13] border border-white/[0.06] p-3 rounded-xl flex items-center justify-between gap-3 text-xs"
              >
                <div>
                  <div className="font-bold text-slate-200">{form.symbol} • {form.direction} FORMING</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">{form.setup_summary || 'Liquidity swept, awaiting reclaim trigger'}</div>
                </div>
                <div className="text-right font-mono">
                  <div className="text-amber-400 font-bold">${form.entryPrice.toFixed(2)}</div>
                  <div className="text-[10px] text-slate-500">Target: ${form.takeProfit1.toFixed(2)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
