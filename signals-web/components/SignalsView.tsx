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
  killzoneInfo?: { is_killzone: boolean; session_name: string; trading_allowed: boolean; utc_time: string; };
  adrInfo?: { adr_used_pct: number; range_pts: number; typical_adr: number; is_exhausted: boolean; warning: string; };
  onLogToJournal: (signal: ConfluenceSignal) => void;
  onRefresh: () => void;
  isScanning: boolean;
}

export const SignalsView: React.FC<SignalsViewProps> = ({
  selectedSymbol, setSelectedSymbol, activeSignals, formingSetups,
  marketSchedules, currentPrice, macroBias, killzoneInfo, adrInfo,
  onLogToJournal, onRefresh, isScanning,
}) => {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [calcPips, setCalcPips] = useState<number>(30);
  const [calcLots, setCalcLots] = useState<number>(0.01);

  const currentSchedule = marketSchedules[selectedSymbol];
  const isMarketOpen = currentSchedule ? currentSchedule.is_open : true;
  const topSignal = activeSignals[0] ?? null;
  const isBuy = topSignal ? (topSignal.direction || '').toUpperCase().includes('BUY') : true;
  const scoreNum = topSignal?.scoreNumeric ?? (topSignal ? 3 : 0);

  const handleCopyParams = (sig: ConfluenceSignal) => {
    const text = `ORDER: ${sig.direction}\nSYMBOL: ${sig.symbol}\nTYPE: ${sig.orderType || 'BUY MARKET'}\nENTRY: ${sig.entryPrice.toFixed(2)}\nSTOP LOSS: ${sig.stopLoss.toFixed(2)}\nTAKE PROFIT 1: ${sig.takeProfit1.toFixed(2)}\nTAKE PROFIT 2: ${(sig.takeProfit2 || sig.takeProfit1 * 1.5).toFixed(2)}\nR:R RATIO: 1:${sig.riskReward.toFixed(2)}`;
    navigator.clipboard.writeText(text);
    setCopiedId(sig.id || 'sig-1');
    setTimeout(() => setCopiedId(null), 2000);
  };

  const estimatedProfitDollars = selectedSymbol === 'XAUUSD' ? calcPips * calcLots * 10 : (calcPips / 100) * calcLots * 100;

  return (
    <div className="flex flex-col gap-5 pb-20 lg:pb-6">
      {/* ZONE 1 — STATUS BAR */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-[#0d121c]/90 border border-white/[0.08] p-3.5 sm:p-4 rounded-2xl backdrop-blur-xl">
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <button onClick={() => setSelectedSymbol('XAUUSD')} className={`flex-1 sm:flex-initial flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-bold transition-all ${selectedSymbol === 'XAUUSD' ? 'bg-gradient-to-r from-amber-500/20 to-yellow-500/20 text-amber-300 border border-amber-500/40 shadow-[0_0_15px_rgba(245,200,66,0.2)]' : 'bg-white/[0.03] text-slate-400 hover:text-slate-200 border border-white/[0.05]'}`}>
            <span>🟡</span><span>XAUUSD (Gold)</span>
            {!marketSchedules['XAUUSD']?.is_open && <span className="text-[9px] px-1.5 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">CLOSED</span>}
          </button>
          <button onClick={() => setSelectedSymbol('BTCUSD')} className={`flex-1 sm:flex-initial flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-bold transition-all ${selectedSymbol === 'BTCUSD' ? 'bg-gradient-to-r from-orange-500/20 to-amber-500/20 text-orange-300 border border-orange-500/40 shadow-[0_0_15px_rgba(249,115,22,0.2)]' : 'bg-white/[0.03] text-slate-400 hover:text-slate-200 border border-white/[0.05]'}`}>
            <span>🟠</span><span>BTCUSD (24/7)</span>
            <span className="text-[9px] px-1.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">LIVE</span>
          </button>
        </div>
        <div className="flex items-center justify-between sm:justify-end gap-3 w-full sm:w-auto">
          <div className="text-left sm:text-right">
            <div className="text-[10px] uppercase font-semibold text-slate-400">Live Quote</div>
            <div className="text-base sm:text-lg font-mono font-extrabold text-slate-100">${currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
          </div>
          <button onClick={onRefresh} disabled={isScanning} className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-bold hover:bg-cyan-500/20 transition-all active:scale-95 disabled:opacity-50">
            <span className={isScanning ? 'animate-spin' : ''}>🔄</span>
            <span>{isScanning ? 'Scanning...' : 'Scan Market'}</span>
          </button>
        </div>
      </div>

      {!isMarketOpen && currentSchedule && (
        <div className="bg-gradient-to-r from-amber-500/10 via-rose-500/10 to-amber-500/10 border border-amber-500/30 rounded-2xl p-4 text-xs text-amber-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="text-2xl">⏳</span>
            <div>
              <div className="font-extrabold text-sm text-amber-300">{currentSchedule.status_text}</div>
              <p className="text-slate-300 text-xs mt-0.5">Weekend market structure analysis active. Signals derive from closed D1/H4 candles. Live auto-execution resumes Sunday 22:00 UTC.</p>
            </div>
          </div>
          <span className="px-3 py-1 rounded-full bg-amber-500/20 text-amber-300 font-mono text-[11px] font-bold whitespace-nowrap">AUTO-RESUMES SUN 22:00 UTC</span>
        </div>
      )}

      {/* ZONE 2 — ACTIVE SIGNAL CARD (always visible above fold) */}
      {topSignal ? (
        <div className={`p-5 sm:p-6 rounded-3xl border transition-all backdrop-blur-xl ${isBuy ? 'bg-gradient-to-br from-[#0c1a15] to-[#091210] border-emerald-500/50 shadow-[0_0_40px_rgba(16,185,129,0.15)]' : 'bg-gradient-to-br from-[#1c0f13] to-[#120a0d] border-rose-500/50 shadow-[0_0_40px_rgba(244,63,94,0.15)]'}`}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <span className={`text-sm font-black px-3 py-1.5 rounded-xl tracking-wider ${isBuy ? 'bg-emerald-500 text-black' : 'bg-rose-500 text-white'}`}>{topSignal.direction.toUpperCase().includes('BUY') ? 'LONG' : 'SHORT'}</span>
              <span className="text-base font-black text-slate-100">{topSignal.symbol}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-500/15 border border-amber-500/30">
                {[1, 2, 3].map((i) => <span key={i} className={`w-2 h-2 rounded-full ${i <= scoreNum ? 'bg-amber-400' : 'bg-slate-700'}`} />)}
                <span className="text-xs font-black text-amber-300 ml-1">{scoreNum}/3</span>
              </div>
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">1:{topSignal.riskReward?.toFixed(2) || '2.50'} R:R</span>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 rounded-2xl bg-[#080b11]/80 border border-white/[0.06] mb-4">
            <div><div className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider mb-1">Entry</div><div className="text-xl font-mono font-black text-slate-100">{topSignal.entryPrice?.toFixed(2)}</div></div>
            <div><div className="text-[10px] text-rose-400 font-semibold uppercase tracking-wider mb-1">Stop Loss</div><div className="text-xl font-mono font-black text-rose-300">{topSignal.stopLoss?.toFixed(2)}</div></div>
            <div><div className="text-[10px] text-emerald-400 font-semibold uppercase tracking-wider mb-1">TP1 (50% + BE)</div><div className="text-xl font-mono font-black text-emerald-300">{topSignal.takeProfit1?.toFixed(2)}</div></div>
            <div><div className="text-[10px] text-cyan-400 font-semibold uppercase tracking-wider mb-1">TP2 (Runner)</div><div className="text-xl font-mono font-black text-cyan-300">{(topSignal.takeProfit2 || topSignal.takeProfit1 * 1.5)?.toFixed(2)}</div></div>
          </div>
          <p className="text-xs text-slate-300 leading-relaxed mb-4">{(topSignal as any).reason || topSignal.setup_summary || 'D1 Macro Accumulation + 4H Liquidity Sweep of previous Asian low + 1H structural reclaim with Fair Value Gap fill.'}</p>
          <div className="flex items-center gap-2">
            <button onClick={() => handleCopyParams(topSignal)} className="flex-1 py-2.5 rounded-xl bg-white/[0.05] hover:bg-white/[0.1] text-xs font-bold text-slate-200 border border-white/[0.08] transition-all">{copiedId === (topSignal.id || 'sig-1') ? '✓ Copied!' : 'Copy Order Parameters'}</button>
            <button onClick={() => onLogToJournal(topSignal)} className="flex-1 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-yellow-500 hover:from-amber-400 hover:to-yellow-400 text-black text-xs font-extrabold transition-all shadow-[0_0_12px_rgba(245,200,66,0.3)]">Log to Journal 📖</button>
          </div>
          {activeSignals.length > 1 && <div className="mt-3 pt-3 border-t border-white/[0.06] text-center text-xs text-slate-400">+{activeSignals.length - 1} more confirmed setup{activeSignals.length > 2 ? 's' : ''} — see confluence detail below ↓</div>}
        </div>
      ) : (
        <div className="p-6 sm:p-8 rounded-3xl bg-[#0d121c]/90 border border-white/[0.08] backdrop-blur-xl flex flex-col items-center justify-center gap-4 min-h-[200px] text-center">
          <div className="w-14 h-14 rounded-2xl bg-slate-800/80 border border-white/[0.08] flex items-center justify-center">
            <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="11" y="2" width="6" height="14" rx="1.5" fill="#f5c842" opacity="0.4"/>
              <line x1="14" y1="0" x2="14" y2="2" stroke="#f5c842" strokeWidth="2" strokeLinecap="round" opacity="0.4"/>
              <polyline points="7,18 12,25 22,13" stroke="url(#cg)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none" opacity="0.5"/>
              <defs><linearGradient id="cg" x1="7" y1="18" x2="22" y2="13" gradientUnits="userSpaceOnUse"><stop stopColor="#f5c842"/><stop offset="1" stopColor="#06b6d4"/></linearGradient></defs>
            </svg>
          </div>
          <div>
            <div className="font-extrabold text-sm text-slate-200 mb-1">No confirmed setup — scanning</div>
            <p className="text-xs text-slate-400 max-w-sm leading-relaxed">Waiting for 3/3 confluence (D1 Macro · 4H Sweep · 1H Reclaim). Only fires on high-probability setups.</p>
          </div>
          <button onClick={onRefresh} disabled={isScanning} className="flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-bold hover:bg-cyan-500/20 transition-all disabled:opacity-50">
            <span className={isScanning ? 'animate-spin' : ''}>🔄</span>
            <span>{isScanning ? 'Scanning...' : 'Run Manual Scan'}</span>
          </button>
        </div>
      )}

      {/* ZONE 3 — CONFLUENCE DETAIL (below fold) */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-2 px-1">
          <div className="h-px flex-1 bg-white/[0.06]" />
          <span className="text-[10px] uppercase font-bold text-slate-500 tracking-widest">Confluence Detail</span>
          <div className="h-px flex-1 bg-white/[0.06]" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
          <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
            <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
              <span className="font-bold">1. Macro Bias (D1+H4)</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">{topSignal ? 'ALIGNED ✓' : 'CHECKING'}</span>
            </div>
            <div className="text-sm font-extrabold text-emerald-400 mb-1">{macroBias}</div>
            <p className="text-[11px] text-slate-400 leading-relaxed">Swing holding horizon: 18h – 48h. Invalidation stop below structural swing low.</p>
          </div>
          <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
            <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
              <span className="font-bold">2. Session Gate (H1)</span>
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${killzoneInfo?.is_killzone ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20' : 'bg-slate-700/40 text-slate-500 border-slate-600/20'}`}>{killzoneInfo?.utc_time || 'LIVE UTC'}</span>
            </div>
            <div className="text-sm font-extrabold text-cyan-300 mb-1">{killzoneInfo?.session_name || 'London Killzone (Peak Volume)'}</div>
            <p className="text-[11px] text-slate-400 leading-relaxed">{killzoneInfo?.trading_allowed ? 'High institutional liquidity — execution permitted.' : 'Outside killzone — signals queue, no auto-execution.'}</p>
          </div>
          <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
            <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
              <span className="font-bold">3. ADR Headroom (M15/M30)</span>
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${(adrInfo?.adr_used_pct || 45) > 80 ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' : 'bg-amber-500/10 text-amber-400 border-amber-500/20'}`}>{adrInfo?.adr_used_pct || 45}% USED</span>
            </div>
            <div className="w-full bg-slate-800 rounded-full h-1.5 mb-2 overflow-hidden">
              <div className={`h-full rounded-full transition-all ${(adrInfo?.adr_used_pct || 45) > 80 ? 'bg-rose-500' : 'bg-gradient-to-r from-emerald-500 to-amber-500'}`} style={{ width: `${Math.min(adrInfo?.adr_used_pct || 45, 100)}%` }} />
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">{adrInfo?.warning || 'Normal Daily Range (Clean expansion headroom)'}</p>
          </div>
        </div>
        {formingSetups.length > 0 && (
          <div className="bg-[#0e131d]/80 border border-amber-500/20 rounded-2xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-[10px] uppercase font-bold text-amber-400 tracking-wider">Setups Forming ({formingSetups.length})</span>
              <span className="text-[10px] text-slate-500">— not yet entry confirmed</span>
            </div>
            <div className="space-y-2">
              {formingSetups.slice(0, 3).map((sig, i) => (
                <div key={sig.id || i} className="flex items-center justify-between text-xs p-2 rounded-lg bg-[#080b11]/60 border border-white/[0.04]">
                  <div className="flex items-center gap-2">
                    <span className={`font-black px-2 py-0.5 rounded text-[10px] ${sig.direction.includes('BUY') ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>{sig.direction}</span>
                    <span className="text-slate-300 font-mono">{sig.symbol}</span>
                  </div>
                  <span className="text-slate-500 truncate max-w-[180px]">{sig.setup_summary?.slice(0, 40) || 'Watching for confirmation…'}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Live Profit Simulator */}
      <div className="bg-[#0e131d]/90 border border-white/[0.08] rounded-3xl p-5 sm:p-6 backdrop-blur-xl">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold text-lg">💰</div>
          <div>
            <h3 className="text-sm sm:text-base font-black text-slate-100">Live Profit &amp; Risk Simulator</h3>
            <p className="text-xs text-slate-400">Calculate exact dollar return with fixed lot sizing.</p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-[#080b11] p-4 rounded-2xl border border-white/[0.05]">
            <div className="flex justify-between items-center text-xs mb-2"><span className="text-slate-400 font-semibold">Target Move (Pips)</span><span className="font-mono font-extrabold text-amber-300">{calcPips} Pips</span></div>
            <input type="range" min="10" max="150" step="5" value={calcPips} onChange={(e) => setCalcPips(Number(e.target.value))} className="w-full accent-amber-400 cursor-pointer" />
          </div>
          <div className="bg-[#080b11] p-4 rounded-2xl border border-white/[0.05]">
            <div className="flex justify-between items-center text-xs mb-2"><span className="text-slate-400 font-semibold">Lot Size</span><span className="font-mono font-extrabold text-emerald-400">{calcLots.toFixed(2)} Lot</span></div>
            <input type="range" min={0.01} max={0.10} step={0.01} value={calcLots} onChange={(e) => setCalcLots(Number(e.target.value))} className="w-full accent-emerald-400 cursor-pointer" />
          </div>
          <div className="bg-gradient-to-br from-[#0e1f18] to-[#08140f] p-4 rounded-2xl border border-emerald-500/30 flex flex-col justify-center">
            <div className="text-[11px] text-emerald-300 font-semibold uppercase">Projected Profit</div>
            <div className="text-xl sm:text-2xl font-mono font-black text-emerald-400">+${estimatedProfitDollars.toFixed(2)} USD</div>
            <div className="text-[10px] text-slate-400 mt-0.5">at {calcLots.toFixed(2)} lot · {calcPips} pips</div>
          </div>
        </div>
      </div>
    </div>
  );
};
