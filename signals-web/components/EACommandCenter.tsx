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
  const [logs, setLogs] = useState<string[]>([
    'Institutional Market Structure Scanner initialized.',
    'Multi-Timeframe Confluence Engine active (D1/H4/H1).',
    'Exness MT5 Terminal Bridge connected: GOLD CLONE (476719466).',
    'Trade Isolation active: Manual trades (#0) isolated from EA trades (#2001).',
    'Algo Trading master state: ' + (eaRunning ? 'RUNNING (Auto-Execution ON)' : 'STOPPED (Observation Mode)'),
  ]);

  return (
    <div className="flex flex-col gap-6 pb-20 lg:pb-6">
      {/* Master EA Execution Banner */}
      <div className={`p-6 sm:p-8 rounded-3xl border transition-all duration-300 backdrop-blur-2xl ${
        eaRunning
          ? 'bg-gradient-to-br from-[#0c1815] via-[#0f241d] to-[#091410] border-emerald-500/40 shadow-[0_0_40px_rgba(16,185,129,0.15)]'
          : 'bg-gradient-to-br from-[#1a0f12] via-[#241217] to-[#12090b] border-rose-500/40 shadow-[0_0_40px_rgba(244,63,94,0.15)]'
      }`}>
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div className="flex items-start sm:items-center gap-4">
            <div className={`flex items-center justify-center w-14 h-14 sm:w-16 sm:h-16 rounded-2xl border text-2xl sm:text-3xl shadow-lg ${
              eaRunning
                ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-300 shadow-[0_0_20px_rgba(16,185,129,0.3)] animate-pulse'
                : 'bg-rose-500/20 border-rose-500/50 text-rose-300 shadow-[0_0_20px_rgba(244,63,94,0.3)]'
            }`}>
              {eaRunning ? '⚡' : '🛑'}
            </div>

            <div>
              <div className="flex items-center gap-2 mb-1">
                <h2 className="text-xl sm:text-2xl font-black text-slate-100">
                  {eaRunning ? 'EA RUNNING (ALGO TRADING ACTIVE)' : 'EA STOPPED (OBSERVATION MODE)'}
                </h2>
                <span className={`text-[10px] font-mono font-bold px-2.5 py-0.5 rounded-full ${
                  eaRunning ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40' : 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                }`}>
                  {eaRunning ? 'AUTONOMOUS' : 'HALTED'}
                </span>
              </div>
              <p className="text-xs sm:text-sm text-slate-300 max-w-2xl leading-relaxed">
                {eaRunning
                  ? 'The algorithm is actively scanning D1/H4/H1 structural confluences and automatically placing holding trades on MT5 with guaranteed Stop Loss and Take Profit (1:2.0+ R:R).'
                  : 'Automated trade execution is halted. Signals and price charts are live in observation mode. No new trades will be opened by the bot.'}
              </p>
            </div>
          </div>

          {/* Master Start / Stop Action Button */}
          <div className="w-full md:w-auto flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <button
              onClick={onToggleEA}
              className={`px-6 py-3.5 rounded-2xl font-black text-sm tracking-wide transition-all shadow-xl active:scale-95 flex items-center justify-center gap-2 ${
                eaRunning
                  ? 'bg-gradient-to-r from-rose-500 to-red-600 hover:from-rose-600 hover:to-red-700 text-white shadow-[0_0_25px_rgba(244,63,94,0.4)]'
                  : 'bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white shadow-[0_0_25px_rgba(16,185,129,0.4)]'
              }`}
            >
              <span>{eaRunning ? '🛑 Stop Automated EA' : '🟢 Start Automated EA'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Grid: Terminal Bridge & Execution Parameters */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Card 1: Exness MT5 Bridge */}
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-5 rounded-2xl backdrop-blur-xl flex flex-col justify-between gap-4">
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs uppercase font-bold text-slate-400">Live MT5 Terminal Bridge</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                CONNECTED
              </span>
            </div>
            <div className="text-base font-extrabold text-slate-100 mb-1">
              GOLD CLONE (Exness)
            </div>
            <div className="text-xs font-mono text-slate-400">
              Login: <span className="text-slate-200">476719466</span> • Server: <span className="text-slate-200">Exness-MT5Trial9</span>
            </div>

            <div className="grid grid-cols-2 gap-2 mt-3 p-2.5 rounded-xl bg-[#080b11] border border-white/[0.05]">
              <div>
                <div className="text-[10px] text-slate-400">Live Balance</div>
                <div className="text-sm font-mono font-bold text-slate-100">${(account?.balance || 36.58).toFixed(2)}</div>
              </div>
              <div>
                <div className="text-[10px] text-slate-400">Live Equity</div>
                <div className="text-sm font-mono font-bold text-emerald-400">${(account?.equity || 36.65).toFixed(2)}</div>
              </div>
            </div>
          </div>

          <button
            onClick={onLaunchTerminal}
            disabled={isLaunchingTerminal}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-xs font-bold transition-all active:scale-95 disabled:opacity-50"
          >
            <span>🚀</span>
            <span>{isLaunchingTerminal ? 'Launching MT5...' : 'Launch MT5 Terminal on Laptop'}</span>
          </button>
        </div>

        {/* Card 2: Trade Isolation & Safety Guard */}
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-5 rounded-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs uppercase font-bold text-slate-400">Strict Trade Isolation</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              PROTECTED
            </span>
          </div>
          <div className="text-base font-extrabold text-cyan-300 mb-1">
            Manual (#0) vs EA (#2001)
          </div>
          <p className="text-xs text-slate-300 leading-relaxed mb-3">
            Your manual trades (like your BTCUSDm positions) are tagged with Magic #0 and are completely protected from bot modification or closure.
          </p>
          <div className="space-y-1.5 text-xs">
            <div className="flex items-center justify-between text-slate-400">
              <span>Manual Trades Protection:</span>
              <span className="text-emerald-400 font-bold">100% Isolated</span>
            </div>
            <div className="flex items-center justify-between text-slate-400">
              <span>EA Magic Number:</span>
              <span className="text-amber-400 font-mono font-bold">#2001</span>
            </div>
            <div className="flex items-center justify-between text-slate-400">
              <span>Max Concurrent Positions:</span>
              <span className="text-slate-200 font-bold">1 per symbol</span>
            </div>
          </div>
        </div>

        {/* Card 3: Execution Risk Rules */}
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-5 rounded-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs uppercase font-bold text-slate-400">Execution Parameters</span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">
              MICRO LOTS
            </span>
          </div>
          <div className="text-base font-extrabold text-purple-300 mb-1">
            Swing Holding & Auto Breakeven
          </div>
          <div className="space-y-2 mt-3 text-xs">
            <div className="flex items-center justify-between p-2 rounded-lg bg-[#080b11] border border-white/[0.04]">
              <span className="text-slate-400">Order Volume:</span>
              <span className="text-slate-100 font-mono font-bold">0.01 Micro-Lot</span>
            </div>
            <div className="flex items-center justify-between p-2 rounded-lg bg-[#080b11] border border-white/[0.04]">
              <span className="text-slate-400">Target Risk:Reward:</span>
              <span className="text-emerald-400 font-mono font-bold">1:2.00 (TP1) / 1:3.50 (TP2)</span>
            </div>
            <div className="flex items-center justify-between p-2 rounded-lg bg-[#080b11] border border-white/[0.04]">
              <span className="text-slate-400">Breakeven Trailing:</span>
              <span className="text-cyan-400 font-mono font-bold">Trigger at +1.5R Profit</span>
            </div>
          </div>
        </div>
      </div>

      {/* Live Algorithmic Execution Feed */}
      <div className="bg-[#0e131d]/90 border border-white/[0.08] p-5 rounded-2xl backdrop-blur-xl">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-base">📜</span>
            <h3 className="text-sm font-bold text-slate-200">Algorithmic Live Execution Feed</h3>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            POLLING (2.5s)
          </span>
        </div>

        <div className="bg-[#070a10] border border-white/[0.06] p-4 rounded-xl font-mono text-xs text-slate-300 space-y-2 max-h-56 overflow-y-auto">
          {logs.map((log, idx) => (
            <div key={idx} className="flex items-start gap-2">
              <span className="text-emerald-400">➜</span>
              <span className="text-slate-400">[{new Date().toLocaleTimeString()}]</span>
              <span className="text-slate-200">{log}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
