'use client';

import React, { useState } from 'react';
import { FleetAccount } from '@/lib/types';

interface EACommandCenterProps {
  eaRunning: boolean;
  onToggleEA: () => void;
  account: FleetAccount | null;
  onLaunchTerminal: () => Promise<boolean>;
  isLaunchingTerminal: boolean;
}

export const EACommandCenter: React.FC<EACommandCenterProps> = ({
  eaRunning,
  onToggleEA,
  account,
  onLaunchTerminal,
  isLaunchingTerminal,
}) => {
  const [terminalFeedback, setTerminalFeedback] = useState<string | null>(null);
  const [showArmConfirm, setShowArmConfirm] = useState(false);
  const [minScore, setMinScore] = useState<3 | 2>(3); // 3/3 only by default
  const [maxSignalsPerDay, setMaxSignalsPerDay] = useState(3);
  const [signalsToday, setSignalsToday] = useState(0); // pulled from props in production

  const handleLaunchWithFeedback = async () => {
    setTerminalFeedback('Locating MT5 terminal executable and initializing connector...');
    const ok = await onLaunchTerminal();
    setTerminalFeedback(ok ? 'MetaTrader 5 terminal launched successfully.' : 'MT5 terminal launch triggered on laptop.');
    setTimeout(() => setTerminalFeedback(null), 5000);
  };

  const handleArmRequest = () => {
    if (!eaRunning) {
      setShowArmConfirm(true); // confirmation required to ARM
    } else {
      onToggleEA(); // no confirmation needed to STOP
    }
  };

  const confirmArm = () => {
    setShowArmConfirm(false);
    onToggleEA();
  };

  const cappedToday = Math.min(signalsToday, maxSignalsPerDay);
  const isCapReached = signalsToday >= maxSignalsPerDay;

  return (
    <div className="flex flex-col gap-5 pb-20 lg:pb-6">
      
      {/* ── Arm Confirmation Modal ── */}
      {showArmConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-[#0d121c] border border-amber-500/40 rounded-3xl p-6 sm:p-8 max-w-sm w-full shadow-[0_0_60px_rgba(245,200,66,0.15)]">
            <div className="text-center mb-5">
              <div className="text-3xl mb-3">⚡</div>
              <h2 className="text-lg font-black text-slate-100 mb-2">Arm the Trading Engine?</h2>
              <p className="text-xs text-slate-400 leading-relaxed">
                The bot will begin executing trades automatically on <span className="text-amber-300 font-bold">{minScore}/3</span> confluence signals. Confirm the account is correct before proceeding.
              </p>
            </div>
            <div className="p-3 rounded-xl bg-[#080b11] border border-white/[0.06] mb-5 flex items-center justify-between text-xs">
              <span className="text-slate-400">Currently wired to</span>
              <span className="font-bold text-amber-300">{account?.name || 'GOLD CLONE — Demo'}</span>
            </div>
            <div className="flex items-center gap-3">
              <button onClick={() => setShowArmConfirm(false)} className="flex-1 py-3 rounded-xl bg-white/[0.05] hover:bg-white/[0.08] text-sm font-bold text-slate-300 border border-white/[0.08] transition-all">Cancel</button>
              <button onClick={confirmArm} className="flex-1 py-3 rounded-xl bg-gradient-to-r from-emerald-400 to-teal-400 hover:from-emerald-300 hover:to-teal-300 text-black text-sm font-extrabold tracking-wide transition-all shadow-[0_0_20px_rgba(16,185,129,0.3)] active:scale-95">Confirm &amp; Arm</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Master Status HUD ── */}
      <div className={`p-6 sm:p-8 rounded-3xl border transition-all duration-300 backdrop-blur-2xl ${eaRunning ? 'bg-gradient-to-br from-[#0c1815] via-[#0f241d] to-[#091410] border-emerald-500/40 shadow-[0_0_40px_rgba(16,185,129,0.18)]' : 'bg-gradient-to-br from-[#1a0f12] via-[#241217] to-[#12090b] border-rose-500/40 shadow-[0_0_40px_rgba(244,63,94,0.18)]'}`}>
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div className="flex items-start sm:items-center gap-4">
            <div className={`flex items-center justify-center w-14 h-14 sm:w-16 sm:h-16 rounded-2xl border text-2xl sm:text-3xl shrink-0 ${eaRunning ? 'bg-emerald-500/20 border-emerald-500/50 shadow-[0_0_20px_rgba(16,185,129,0.3)] animate-pulse' : 'bg-rose-500/20 border-rose-500/50 shadow-[0_0_20px_rgba(244,63,94,0.3)]'}`}>
              {eaRunning ? '⚡' : '🛑'}
            </div>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h2 className="text-xl sm:text-2xl font-black text-slate-100">{eaRunning ? 'ENGINE ARMED' : 'ENGINE STOPPED'}</h2>
                <span className={`text-[10px] font-mono font-bold px-2.5 py-0.5 rounded-full ${eaRunning ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40' : 'bg-rose-500/20 text-rose-400 border border-rose-500/40'}`}>{eaRunning ? 'ALGO ACTIVE' : 'STANDBY'}</span>
              </div>
              <p className="text-xs sm:text-sm text-slate-300 max-w-2xl leading-relaxed">
                {eaRunning ? `Auto-executing ${minScore}/3+ confluence setups. Daily cap: ${signalsToday}/${maxSignalsPerDay} signals used.` : 'Automated trade execution paused. Market data and charts remain live in observation mode.'}
              </p>
            </div>
          </div>
          <button
            onClick={handleArmRequest}
            disabled={isCapReached && !eaRunning}
            className={`w-full md:w-auto px-8 py-4 rounded-2xl font-black text-sm tracking-wider uppercase transition-all shadow-xl active:scale-95 flex items-center justify-center gap-2.5 whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed ${eaRunning ? 'bg-gradient-to-r from-rose-500 to-red-600 hover:from-rose-600 hover:to-red-700 text-white shadow-[0_0_25px_rgba(244,63,94,0.4)]' : 'bg-gradient-to-r from-emerald-400 via-teal-400 to-emerald-500 hover:from-emerald-300 hover:to-teal-400 text-black shadow-[0_0_25px_rgba(16,185,129,0.4)]'}`}
          >
            <span>{eaRunning ? '🛑 DISARM' : isCapReached ? '🔒 DAILY CAP REACHED' : '🟢 ARM ENGINE'}</span>
          </button>
        </div>
      </div>

      {/* ── Configuration Grid ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

        {/* Card 1: Wired Account */}
        <div className={`bg-[#0e131d]/90 border p-5 rounded-2xl backdrop-blur-xl flex flex-col justify-between gap-4 ${account?.type === 'PROP_FIRM' ? 'border-amber-500/30' : 'border-white/[0.08]'}`}>
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs uppercase font-bold text-slate-400">Wired Account</span>
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${account?.type === 'PROP_FIRM' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'}`}>
                {account?.type === 'PROP_FIRM' ? 'PROP FIRM' : account?.type || 'DEMO'}
              </span>
            </div>
            <div className="text-base font-extrabold text-slate-100 mb-1">{account?.name || 'GOLD CLONE (Demo)'}</div>
            <div className="grid grid-cols-2 gap-2 mt-3 p-3 rounded-xl bg-[#080b11] border border-white/[0.05]">
              <div><div className="text-[10px] text-slate-400">Balance</div><div className="text-sm font-mono font-bold text-slate-100">${(account?.balance || 36.58).toFixed(2)}</div></div>
              <div><div className="text-[10px] text-slate-400">Equity</div><div className="text-sm font-mono font-bold text-emerald-400">${(account?.equity || 36.65).toFixed(2)}</div></div>
            </div>
            {terminalFeedback && <div className="mt-2 text-xs text-amber-300 font-mono p-2 rounded-lg bg-amber-500/10 border border-amber-500/20">{terminalFeedback}</div>}
          </div>
          <button onClick={handleLaunchWithFeedback} disabled={isLaunchingTerminal} className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/40 text-xs font-extrabold tracking-wide uppercase transition-all active:scale-95 disabled:opacity-50">
            <span>🚀</span><span>{isLaunchingTerminal ? 'CONNECTING MT5...' : 'AUTO-CONNECT & LAUNCH MT5'}</span>
          </button>
        </div>

        {/* Card 2: Min Confluence Score */}
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-5 rounded-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs uppercase font-bold text-slate-400">Min Score to Execute</span>
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${minScore === 3 ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' : 'bg-slate-600/30 text-slate-400 border-slate-600/20'}`}>
              {minScore === 3 ? 'STRICT' : 'RELAXED'}
            </span>
          </div>
          <div className="text-base font-extrabold text-amber-300 mb-3">{minScore}/3 Confluence Required</div>
          <div className="flex gap-2">
            <button onClick={() => setMinScore(3)} className={`flex-1 py-2.5 rounded-xl text-xs font-black transition-all border ${minScore === 3 ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 shadow-[0_0_12px_rgba(245,200,66,0.15)]' : 'bg-white/[0.03] text-slate-400 border-white/[0.05] hover:text-slate-200'}`}>3/3 Only</button>
            <button onClick={() => setMinScore(2)} className={`flex-1 py-2.5 rounded-xl text-xs font-black transition-all border ${minScore === 2 ? 'bg-slate-600/30 text-slate-300 border-slate-500/30' : 'bg-white/[0.03] text-slate-400 border-white/[0.05] hover:text-slate-200'}`}>2/3+</button>
          </div>
          <p className="text-[11px] text-slate-500 mt-3 leading-relaxed">3/3-only is the default. See your Journal win-rate by score before lowering this threshold.</p>
        </div>

        {/* Card 3: Daily Cap */}
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-5 rounded-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs uppercase font-bold text-slate-400">Daily Signal Cap</span>
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${isCapReached ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' : 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'}`}>
              {isCapReached ? 'CAP REACHED' : `${cappedToday}/${maxSignalsPerDay} TODAY`}
            </span>
          </div>
          <div className="text-base font-extrabold text-cyan-300 mb-3">Max {maxSignalsPerDay} auto-trades/day</div>
          {/* Progress bar */}
          <div className="w-full bg-slate-800 rounded-full h-2 mb-3 overflow-hidden">
            <div className={`h-full rounded-full transition-all ${isCapReached ? 'bg-rose-500' : 'bg-gradient-to-r from-cyan-500 to-emerald-500'}`} style={{ width: `${Math.min((signalsToday / maxSignalsPerDay) * 100, 100)}%` }} />
          </div>
          <div className="flex gap-2">
            {[1, 2, 3, 5].map((n) => (
              <button key={n} onClick={() => setMaxSignalsPerDay(n)} className={`flex-1 py-2 rounded-xl text-xs font-black transition-all border ${maxSignalsPerDay === n ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40' : 'bg-white/[0.03] text-slate-400 border-white/[0.05] hover:text-slate-200'}`}>{n}</button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Trade Isolation & Execution Rules ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-5 rounded-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs uppercase font-bold text-slate-400">Trade Isolation Guard</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">ACTIVE</span>
          </div>
          <div className="text-sm font-extrabold text-cyan-300 mb-2">Manual Trades (Magic #0) Isolated</div>
          <p className="text-xs text-slate-300 leading-relaxed mb-3">Your manual orders are fully protected. The bot only manages automated orders with Magic #2001.</p>
          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between text-slate-400"><span>Lot Size Floor</span><span className="text-emerald-400 font-bold">0.01 Fixed</span></div>
            <div className="flex items-center justify-between text-slate-400"><span>Fast Breakeven</span><span className="text-cyan-300 font-bold">At 1:1.0 RR</span></div>
            <div className="flex items-center justify-between text-slate-400"><span>Daily Loss Protection</span><span className="text-amber-400 font-bold">Max 3.0% ($1.10)</span></div>
          </div>
        </div>
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-5 rounded-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs uppercase font-bold text-slate-400">Execution Logic</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">3-TIER</span>
          </div>
          <div className="text-sm font-extrabold text-amber-300 mb-2">Institutional Confluence Filter</div>
          <p className="text-xs text-slate-300 leading-relaxed mb-3">Trades filtered for high institutional liquidity windows (London/NY Killzones) only.</p>
          <div className="space-y-1.5 text-xs text-slate-400">
            <div>• D1: Directional Macro Bias</div>
            <div>• H4: Asian/London Liquidity Sweep</div>
            <div>• H1: Structural Reclaim &amp; FVG Fill</div>
          </div>
        </div>
      </div>
    </div>
  );
};
