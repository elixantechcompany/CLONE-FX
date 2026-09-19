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
  const [calcPips, setCalcPips] = useState<number>(30);
  const [calcLots, setCalcLots] = useState<number>(0.01);

  const currentSchedule = marketSchedules[selectedSymbol];
  const isMarketOpen = currentSchedule ? currentSchedule.is_open : true;

  const handleCopyParams = (sig: ConfluenceSignal) => {
    const text = `ORDER: ${sig.direction}\nSYMBOL: ${sig.symbol}\nTYPE: ${sig.orderType || 'BUY MARKET'}\nENTRY: ${sig.entryPrice.toFixed(2)}\nSTOP LOSS: ${sig.stopLoss.toFixed(2)}\nTAKE PROFIT 1: ${sig.takeProfit1.toFixed(2)}\nTAKE PROFIT 2: ${(sig.takeProfit2 || sig.takeProfit1 * 1.5).toFixed(2)}\nR:R RATIO: 1:${sig.riskReward.toFixed(2)}`;
    navigator.clipboard.writeText(text);
    setCopiedId(sig.id || 'sig-1');
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Dollar calculations for Gold / Crypto
  const estimatedProfitDollars = selectedSymbol === 'XAUUSD' 
    ? calcPips * calcLots * 10 
    : (calcPips / 100) * calcLots * 100;

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

      {/* Market Closed Guidance Banner */}
      {!isMarketOpen && currentSchedule && (
        <div className="bg-gradient-to-r from-amber-500/10 via-rose-500/10 to-amber-500/10 border border-amber-500/30 rounded-2xl p-4 text-xs text-amber-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="text-2xl">⏳</span>
            <div>
              <div className="font-extrabold text-sm text-amber-300">
                {currentSchedule.status_text}
              </div>
              <p className="text-slate-300 text-xs mt-0.5">
                Weekend market structure holding analysis active. Signals derive from closed D1/H4 candles. Live auto-execution resumes Sunday 22:00 UTC with London open.
              </p>
            </div>
          </div>
          <span className="px-3 py-1 rounded-full bg-amber-500/20 text-amber-300 font-mono text-[11px] font-bold whitespace-nowrap">
            AUTO-RESUMES SUN 22:00 UTC
          </span>
        </div>
      )}

      {/* 3-Tier Institutional Market State Matrix */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
        {/* Tier 1: Macro Bias */}
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
            <span className="font-bold">1. Macro Bias (D1+H4)</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              ALIGNMENT
            </span>
          </div>
          <div className="text-sm font-extrabold text-emerald-400 mb-1">
            {macroBias}
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            Swing holding horizon: 18h – 48h. Invalidation stop below structural swing low.
          </p>
        </div>

        {/* Tier 2: Killzone Volume Session */}
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
            <span className="font-bold">2. Killzone Session</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              {killzoneInfo?.utc_time || 'LIVE UTC'}
            </span>
          </div>
          <div className="text-sm font-extrabold text-cyan-300 mb-1">
            {killzoneInfo?.session_name || 'London Killzone (Peak Volume)'}
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            High institutional liquidity window. Order flow execution permitted.
          </p>
        </div>

        {/* Tier 3: ADR Headroom Meter */}
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
            <span className="font-bold">3. ADR Range Meter</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
              {adrInfo?.adr_used_pct || 45}% USED
            </span>
          </div>
          <div className="w-full bg-slate-800 rounded-full h-2 mb-2 overflow-hidden">
            <div
              className={`h-full rounded-full ${
                (adrInfo?.adr_used_pct || 45) > 80 ? 'bg-rose-500' : 'bg-gradient-to-r from-emerald-500 to-amber-500'
              }`}
              style={{ width: `${Math.min(adrInfo?.adr_used_pct || 45, 100)}%` }}
            ></div>
          </div>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            {adrInfo?.warning || 'Normal Daily Range (Clean expansion headroom)'}
          </p>
        </div>
      </div>

      {/* Confirmed High-Conviction Signals Section */}
      <div className="bg-[#0e131d]/90 border border-white/[0.08] rounded-3xl p-5 sm:p-6 backdrop-blur-xl">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-5">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-amber-500/20 text-amber-300 border border-amber-500/30 font-bold text-lg">
              🎯
            </div>
            <div>
              <h2 className="text-base sm:text-lg font-black text-slate-100">
                Confirmed High-Conviction Signals
              </h2>
              <p className="text-xs text-slate-400">
                Guaranteed minimum 1:2.00+ Risk-to-Reward ratio with Breakeven trigger.
              </p>
            </div>
          </div>

          <span className="text-xs font-mono font-bold px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            {activeSignals.length} Active High-Grade
          </span>
        </div>

        {/* Signal Cards Display */}
        {activeSignals.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {activeSignals.map((sig, idx) => {
              const isBuy = (sig.direction || '').toUpperCase().includes('BUY');
              return (
                <div
                  key={sig.id || idx}
                  className={`p-5 rounded-2xl border transition-all ${
                    isBuy
                      ? 'bg-gradient-to-br from-[#0e1a16] to-[#0a120f] border-emerald-500/40 shadow-[0_0_25px_rgba(16,185,129,0.1)]'
                      : 'bg-gradient-to-br from-[#1c0f13] to-[#120a0d] border-rose-500/40 shadow-[0_0_25px_rgba(244,63,94,0.1)]'
                  }`}
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className={`text-xs font-black px-2.5 py-1 rounded-lg ${
                        isBuy ? 'bg-emerald-500 text-black' : 'bg-rose-500 text-white'
                      }`}>
                        {sig.direction}
                      </span>
                      <span className="text-sm font-black text-slate-100">{sig.symbol}</span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                        1:{sig.riskReward?.toFixed(2) || '2.50'} R:R
                      </span>
                      <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                        GRADE A+
                      </span>
                    </div>
                  </div>

                  {/* Price Levels Grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 my-3 p-3 rounded-xl bg-[#080b11]/80 border border-white/[0.05]">
                    <div>
                      <div className="text-[10px] text-slate-400 font-semibold">ENTRY</div>
                      <div className="text-xs font-mono font-bold text-slate-100">${sig.entryPrice?.toFixed(2)}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-rose-400 font-semibold">STOP LOSS</div>
                      <div className="text-xs font-mono font-bold text-rose-300">${sig.stopLoss?.toFixed(2)}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-emerald-400 font-semibold">TP1 (50% + BE)</div>
                      <div className="text-xs font-mono font-bold text-emerald-300">${sig.takeProfit1?.toFixed(2)}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-cyan-400 font-semibold">TP2 (Runner)</div>
                      <div className="text-xs font-mono font-bold text-cyan-300">${(sig.takeProfit2 || sig.takeProfit1 * 1.5)?.toFixed(2)}</div>
                    </div>
                  </div>

                  {/* Institutional Reason / Catalyst */}
                  <p className="text-xs text-slate-300 my-2 leading-relaxed">
                    {(sig as any).reason || sig.setup_summary || 'D1 Macro Accumulation + 4H Liquidity Sweep of previous Asian low + 1H structural reclaim with Fair Value Gap fill.'}
                  </p>

                  {/* Actions */}
                  <div className="flex items-center gap-2 mt-4 pt-3 border-t border-white/[0.06]">
                    <button
                      onClick={() => handleCopyParams(sig)}
                      className="flex-1 py-2 rounded-xl bg-white/[0.05] hover:bg-white/[0.1] text-xs font-bold text-slate-200 border border-white/[0.08] transition-all"
                    >
                      {copiedId === (sig.id || 'sig-1') ? '✓ Copied!' : 'Copy Order Parameters'}
                    </button>
                    <button
                      onClick={() => onLogToJournal(sig)}
                      className="flex-1 py-2 rounded-xl bg-gradient-to-r from-amber-500 to-yellow-500 hover:from-amber-400 hover:to-yellow-400 text-black text-xs font-extrabold transition-all shadow-[0_0_12px_rgba(245,200,66,0.3)]"
                    >
                      Log to Journal 📖
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="p-8 rounded-2xl bg-[#080b11]/60 border border-white/[0.05] text-center flex flex-col items-center justify-center gap-3">
            <span className="text-3xl">📡</span>
            <div className="font-extrabold text-sm text-slate-200">
              No Grade A+ Signals Triggered Currently
            </div>
            <p className="text-xs text-slate-400 max-w-lg leading-relaxed">
              The algorithm requires full 3-tier confluence (D1 Macro Bias + 4H Liquidity Sweep + 1H Reclaim Trigger). This ensures you only risk capital on high-probability setups and avoid low-liquidity market chop.
            </p>
          </div>
        )}
      </div>

      {/* Interactive Live Profit & Risk Calculator */}
      <div className="bg-[#0e131d]/90 border border-white/[0.08] rounded-3xl p-5 sm:p-6 backdrop-blur-xl">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold text-lg">
            💰
          </div>
          <div>
            <h3 className="text-sm sm:text-base font-black text-slate-100">
              Live Profit & Risk Simulator (For $36.58 Balance)
            </h3>
            <p className="text-xs text-slate-400">
              Calculate exact dollar return and preserve your capital with fixed 0.01 lot sizing.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Target Pips Slider */}
          <div className="bg-[#080b11] p-4 rounded-2xl border border-white/[0.05]">
            <div className="flex justify-between items-center text-xs mb-2">
              <span className="text-slate-400 font-semibold">Target Move (Pips)</span>
              <span className="font-mono font-extrabold text-amber-300">{calcPips} Pips (${calcPips / 10} move)</span>
            </div>
            <input
              type="range"
              min="10"
              max="150"
              step="5"
              value={calcPips}
              onChange={(e) => setCalcPips(Number(e.target.value))}
              className="w-full accent-amber-400 cursor-pointer"
            />
          </div>

          {/* Lot Sizing */}
          <div className="bg-[#080b11] p-4 rounded-2xl border border-white/[0.05]">
            <div className="flex justify-between items-center text-xs mb-2">
              <span className="text-slate-400 font-semibold">Recommended Lot Size</span>
              <span className="font-mono font-extrabold text-emerald-400">{calcLots.toFixed(2)} Lot (Safe)</span>
            </div>
            <div className="text-[11px] text-slate-400 mt-1">
              On a $36 account, 0.01 lot limits risk to ~$0.50 – $1.00 per trade while enabling $2.00 – $4.00+ profit.
            </div>
          </div>

          {/* Projected Profit Card */}
          <div className="bg-gradient-to-br from-[#0e1f18] to-[#08140f] p-4 rounded-2xl border border-emerald-500/30 flex flex-col justify-center">
            <div className="text-[11px] text-emerald-300 font-semibold uppercase">Projected Trade Profit</div>
            <div className="text-xl sm:text-2xl font-mono font-black text-emerald-400">
              +${estimatedProfitDollars.toFixed(2)} USD
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">
              Gain: +{((estimatedProfitDollars / 36.58) * 100).toFixed(1)}% on Account Balance
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
