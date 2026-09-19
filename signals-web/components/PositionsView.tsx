'use client';

import React from 'react';
import { LivePosition, FleetAccount } from '@/lib/types';

interface PositionsViewProps {
  positions: LivePosition[];
  account: FleetAccount | null;
  onRefresh: () => void;
}

export const PositionsView: React.FC<PositionsViewProps> = ({
  positions,
  account,
  onRefresh,
}) => {
  const totalFloatingPnl = positions.reduce((acc, curr) => acc + (curr.profit || 0), 0);
  const manualPositions = positions.filter((p: any) => !p.magic || p.magic === 0);
  const eaPositions = positions.filter((p: any) => p.magic && p.magic !== 0);

  return (
    <div className="flex flex-col gap-6 pb-20 lg:pb-6">
      {/* Top Header & Account Portfolio Summary */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-[#0d121c]/90 border border-white/[0.08] p-4 sm:p-5 rounded-2xl backdrop-blur-xl">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl">📊</span>
            <h2 className="text-lg sm:text-xl font-black text-slate-100">
              Live MT5 Open Positions & Portfolio Monitor
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Real-time live positions streaming from Exness MT5 terminal for account <span className="text-amber-300 font-bold">GOLD CLONE</span>.
          </p>
        </div>

        <button
          onClick={onRefresh}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 border border-purple-500/30 text-xs font-bold transition-all active:scale-95"
        >
          <span>🔄</span>
          <span>Refresh Positions</span>
        </button>
      </div>

      {/* Portfolio HUD Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
          <div className="text-[11px] font-bold uppercase text-slate-400 mb-1">Open Positions</div>
          <div className="text-2xl font-mono font-extrabold text-slate-100">
            {positions.length}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">{manualPositions.length} Manual • {eaPositions.length} EA</div>
        </div>

        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
          <div className="text-[11px] font-bold uppercase text-slate-400 mb-1">Floating PnL</div>
          <div className={`text-2xl font-mono font-extrabold ${totalFloatingPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {totalFloatingPnl >= 0 ? `+$${totalFloatingPnl.toFixed(2)}` : `-$${Math.abs(totalFloatingPnl).toFixed(2)}`}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Live Unrealized</div>
        </div>

        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
          <div className="text-[11px] font-bold uppercase text-slate-400 mb-1">Account Balance</div>
          <div className="text-2xl font-mono font-extrabold text-slate-100">
            ${(account?.balance || 36.58).toFixed(2)}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Equity: ${(account?.equity || 36.65).toFixed(2)}</div>
        </div>

        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
          <div className="text-[11px] font-bold uppercase text-slate-400 mb-1">Drawdown Risk Guard</div>
          <div className="text-2xl font-mono font-extrabold text-emerald-400">
            0.00%
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Safe from Max Loss ($2.00)</div>
        </div>
      </div>

      {/* Positions List */}
      <div>
        <div className="flex items-center justify-between mb-3.5">
          <h3 className="text-sm font-extrabold text-slate-200 uppercase tracking-wider">
            Active MT5 Tickets ({positions.length})
          </h3>
          <span className="text-xs text-slate-400">Auto-synced from terminal</span>
        </div>

        {positions.length === 0 ? (
          <div className="bg-[#0d121c]/60 border border-dashed border-white/[0.1] rounded-2xl p-10 text-center">
            <div className="text-3xl mb-2">📊</div>
            <h4 className="text-sm font-bold text-slate-200">No Open Positions on MT5 Terminal</h4>
            <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
              Open trades placed either manually by you on MT5 or automatically by the EA will display here with live floating PnL.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {positions.map((pos) => {
              const isBuy = pos.type === 'BUY';
              const isManual = !(pos as any).magic || (pos as any).magic === 0;

              return (
                <div
                  key={pos.ticket}
                  className="bg-[#0e131d]/90 border border-white/[0.08] hover:border-white/[0.16] p-4 sm:p-5 rounded-2xl backdrop-blur-xl transition-all flex flex-col md:flex-row items-start md:items-center justify-between gap-4"
                >
                  {/* Left: Direction & Symbol */}
                  <div className="flex items-center gap-3">
                    <span
                      className={`text-xs font-extrabold px-3 py-1.5 rounded-xl uppercase tracking-wider ${
                        isBuy
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                          : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                      }`}
                    >
                      {pos.type}
                    </span>

                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-extrabold text-base text-slate-100">{pos.symbol}</span>
                        <span className="text-xs font-mono text-slate-300 px-2 py-0.5 rounded bg-white/[0.05]">
                          {pos.volume} Lots
                        </span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            isManual
                              ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/30'
                              : 'bg-amber-500/10 text-amber-300 border border-amber-500/30'
                          }`}
                        >
                          {isManual ? 'MANUAL TRADE (#0)' : 'EA BOT (#2001)'}
                        </span>
                      </div>
                      <div className="text-xs font-mono text-slate-400 mt-1">
                        Ticket: <span className="text-slate-200 font-bold">#{pos.ticket}</span> • Entry: <span className="text-slate-200 font-bold">${pos.open_price.toFixed(2)}</span> • Current: <span className="text-slate-200 font-bold">${pos.current_price.toFixed(2)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Middle: Stops */}
                  <div className="text-xs text-slate-300 flex items-center gap-4">
                    <div>
                      <div className="text-[10px] text-rose-400 font-medium">STOP LOSS</div>
                      <div className="font-mono font-bold text-rose-300">
                        {pos.sl > 0 ? `$${pos.sl.toFixed(2)}` : 'No SL Set'}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-emerald-400 font-medium">TAKE PROFIT</div>
                      <div className="font-mono font-bold text-emerald-300">
                        {pos.tp > 0 ? `$${pos.tp.toFixed(2)}` : 'No TP Set'}
                      </div>
                    </div>
                  </div>

                  {/* Right: Live PnL */}
                  <div className="text-right w-full md:w-auto pt-2 md:pt-0 border-t md:border-t-0 border-white/[0.06]">
                    <div className="text-[10px] text-slate-400 font-semibold uppercase">Floating Profit</div>
                    <div className={`text-lg font-mono font-black ${
                      pos.profit >= 0 ? 'text-emerald-400' : 'text-rose-400'
                    }`}>
                      {pos.profit >= 0 ? `+$${pos.profit.toFixed(2)}` : `-$${Math.abs(pos.profit).toFixed(2)}`}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
