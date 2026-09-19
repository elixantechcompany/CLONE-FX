'use client';

import React from 'react';

interface NavbarProps {
  activeTab: 'signals' | 'ea' | 'journal' | 'positions' | 'accounts';
  setActiveTab: (tab: 'signals' | 'ea' | 'journal' | 'positions' | 'accounts') => void;
  eaRunning: boolean;
  onToggleEA: () => void;
  balance: number;
  equity: number;
  accountName?: string;
  isOnline: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  eaRunning,
  onToggleEA,
  balance,
  equity,
  accountName = 'GOLD CLONE',
  isOnline,
}) => {
  return (
    <header className="sticky top-0 z-50 backdrop-blur-xl bg-[#080b11]/90 border-b border-white/[0.08] px-4 py-3 md:px-6">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        {/* Brand Logo & Live Signal Pulse */}
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-500/20 to-yellow-400/20 border border-amber-400/30 text-amber-400 font-bold text-lg shadow-[0_0_15px_rgba(245,200,66,0.2)]">
            <span>FX</span>
            <span className="absolute -top-1 -right-1 flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
            </span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base md:text-lg font-extrabold tracking-tight bg-gradient-to-r from-amber-300 via-yellow-200 to-amber-500 bg-clip-text text-transparent">
                GOLD CLONE
              </h1>
              <span className="text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                PRO EA v2.4
              </span>
            </div>
            <p className="text-[11px] text-slate-400 hidden sm:block">
              Institutional Market Structure & Swing Execution Radar
            </p>
          </div>
        </div>

        {/* Desktop Tab Navigation */}
        <nav className="hidden lg:flex items-center gap-1.5 bg-[#0d121c] p-1.5 rounded-2xl border border-white/[0.06]">
          <button
            onClick={() => setActiveTab('signals')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all duration-200 ${
              activeTab === 'signals'
                ? 'bg-gradient-to-r from-amber-500/20 to-yellow-500/10 text-amber-300 border border-amber-500/30 shadow-[0_0_12px_rgba(245,200,66,0.15)]'
                : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
            }`}
          >
            <span>📡</span>
            <span>Signals Radar</span>
          </button>

          <button
            onClick={() => setActiveTab('ea')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all duration-200 ${
              activeTab === 'ea'
                ? 'bg-gradient-to-r from-emerald-500/20 to-teal-500/10 text-emerald-300 border border-emerald-500/30 shadow-[0_0_12px_rgba(16,185,129,0.15)]'
                : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
            }`}
          >
            <span className={eaRunning ? 'animate-pulse' : ''}>⚡</span>
            <span>EA Automation</span>
            <span
              className={`text-[9px] px-1.5 py-0.2 rounded font-mono ${
                eaRunning ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
              }`}
            >
              {eaRunning ? 'ON' : 'OFF'}
            </span>
          </button>

          <button
            onClick={() => setActiveTab('journal')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all duration-200 ${
              activeTab === 'journal'
                ? 'bg-gradient-to-r from-cyan-500/20 to-blue-500/10 text-cyan-300 border border-cyan-500/30 shadow-[0_0_12px_rgba(6,182,212,0.15)]'
                : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
            }`}
          >
            <span>📖</span>
            <span>Trade Journal</span>
          </button>

          <button
            onClick={() => setActiveTab('positions')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all duration-200 ${
              activeTab === 'positions'
                ? 'bg-gradient-to-r from-purple-500/20 to-indigo-500/10 text-purple-300 border border-purple-500/30 shadow-[0_0_12px_rgba(168,85,247,0.15)]'
                : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
            }`}
          >
            <span>📊</span>
            <span>Positions</span>
          </button>

          <button
            onClick={() => setActiveTab('accounts')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all duration-200 ${
              activeTab === 'accounts'
                ? 'bg-gradient-to-r from-slate-700/50 to-slate-800/50 text-slate-200 border border-slate-600 shadow-[0_0_12px_rgba(148,163,184,0.15)]'
                : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
            }`}
          >
            <span>🏦</span>
            <span>Accounts</span>
          </button>
        </nav>

        {/* Live Account Stats Badge & EA Quick Toggle */}
        <div className="flex items-center gap-2.5">
          {/* Account Chip */}
          <div className="flex items-center gap-2 bg-[#0e131d] border border-white/[0.08] px-3 py-1.5 rounded-xl">
            <div className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#10b981]"></div>
            <div className="text-right">
              <div className="text-[10px] font-medium text-slate-400 flex items-center gap-1 justify-end">
                <span>{accountName}</span>
                <span className="text-[9px] px-1 rounded bg-amber-500/10 text-amber-400 font-mono">Exness</span>
              </div>
              <div className="text-xs font-mono font-bold text-slate-100">
                ${balance.toFixed(2)} <span className="text-[10px] text-emerald-400 font-normal">(${equity.toFixed(2)})</span>
              </div>
            </div>
          </div>

          {/* EA Toggle Pill */}
          <button
            onClick={onToggleEA}
            title={eaRunning ? 'Click to Stop EA' : 'Click to Start EA'}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all shadow-md active:scale-95 ${
              eaRunning
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/30 shadow-[0_0_12px_rgba(16,185,129,0.25)]'
                : 'bg-rose-500/20 text-rose-300 border border-rose-500/40 hover:bg-rose-500/30 shadow-[0_0_12px_rgba(244,63,94,0.25)]'
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${eaRunning ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'}`}></span>
            <span className="hidden sm:inline">{eaRunning ? 'EA RUNNING' : 'EA STOPPED'}</span>
            <span className="sm:hidden">{eaRunning ? 'EA ON' : 'EA OFF'}</span>
          </button>
        </div>
      </div>
    </header>
  );
};
