'use client';

import React, { useState, useEffect } from 'react';
import { JournalEntry, ConfluenceSignal } from '@/lib/types';

interface TradeJournalViewProps {
  entries: JournalEntry[];
  onAddEntry: (entry: Omit<JournalEntry, 'id' | 'created_at'>) => Promise<void>;
  onDeleteEntry: (id: string) => Promise<void>;
  pendingSignalToLog?: ConfluenceSignal | null;
  onClearPendingSignal?: () => void;
}

export const TradeJournalView: React.FC<TradeJournalViewProps> = ({
  entries,
  onAddEntry,
  onDeleteEntry,
  pendingSignalToLog,
  onClearPendingSignal,
}) => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [filterType, setFilterType] = useState<'ALL' | 'WIN' | 'LOSS' | 'OPEN'>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // Form State
  const [symbol, setSymbol] = useState('XAUUSD');
  const [orderAction, setOrderAction] = useState<'BUY' | 'SELL'>('BUY');
  const [orderType, setOrderType] = useState('BUY MARKET');
  const [entryPrice, setEntryPrice] = useState('');
  const [exitPrice, setExitPrice] = useState('');
  const [stopLoss, setStopLoss] = useState('');
  const [takeProfit, setTakeProfit] = useState('');
  const [lotSize, setLotSize] = useState('0.01');
  const [profitUsd, setProfitUsd] = useState('');
  const [rrRatio, setRrRatio] = useState('2.0');
  const [outcome, setOutcome] = useState<'WIN' | 'LOSS' | 'BREAKEVEN' | 'OPEN'>('OPEN');
  const [session, setSession] = useState('London');
  const [setupType, setSetupType] = useState('Liquidity Sweep');
  const [notes, setNotes] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  // Pre-fill form if a signal was sent to log
  useEffect(() => {
    if (pendingSignalToLog) {
      setSymbol(pendingSignalToLog.symbol);
      setOrderAction(pendingSignalToLog.direction === 'SELL' ? 'SELL' : 'BUY');
      setOrderType(pendingSignalToLog.orderType || 'BUY MARKET');
      setEntryPrice(pendingSignalToLog.entryPrice.toString());
      setStopLoss(pendingSignalToLog.stopLoss.toString());
      setTakeProfit(pendingSignalToLog.takeProfit1.toString());
      setRrRatio(pendingSignalToLog.riskReward.toString());
      setSetupType('Institutional D1/H4 Confluence');
      setNotes(pendingSignalToLog.setup_summary || 'Logged from Signals Radar');
      setIsModalOpen(true);
      if (onClearPendingSignal) {
        onClearPendingSignal();
      }
    }
  }, [pendingSignalToLog, onClearPendingSignal]);

  // Analytics calculation
  const totalTrades = entries.length;
  const closedTrades = entries.filter((e) => e.outcome !== 'OPEN');
  const wins = entries.filter((e) => e.outcome === 'WIN');
  const losses = entries.filter((e) => e.outcome === 'LOSS');
  const winRate = closedTrades.length > 0 ? (wins.length / closedTrades.length) * 100 : 0;
  const totalPnL = entries.reduce((acc, curr) => acc + (curr.profit_usd || 0), 0);

  const grossWins = wins.reduce((acc, curr) => acc + (curr.profit_usd || 0), 0);
  const grossLosses = Math.abs(losses.reduce((acc, curr) => acc + (curr.profit_usd || 0), 0));
  const profitFactor = grossLosses > 0 ? grossWins / grossLosses : grossWins > 0 ? 99.9 : 0;

  // Filtered List
  const filteredEntries = entries.filter((e) => {
    if (filterType !== 'ALL' && e.outcome !== filterType) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        e.symbol.toLowerCase().includes(q) ||
        (e.setup_type && e.setup_type.toLowerCase().includes(q)) ||
        (e.notes && e.notes.toLowerCase().includes(q))
      );
    }
    return true;
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!entryPrice || !symbol) return;

    setIsSaving(true);
    try {
      await onAddEntry({
        symbol,
        order_action: orderAction,
        order_type: orderType,
        entry_price: parseFloat(entryPrice) || 0,
        exit_price: exitPrice ? parseFloat(exitPrice) : undefined,
        stop_loss: parseFloat(stopLoss) || 0,
        take_profit: parseFloat(takeProfit) || 0,
        lot_size: parseFloat(lotSize) || 0.01,
        profit_usd: parseFloat(profitUsd) || 0,
        rr_ratio: parseFloat(rrRatio) || 2.0,
        outcome,
        session,
        setup_type: setupType,
        notes,
      });
      setIsModalOpen(false);
      // Reset form
      setEntryPrice('');
      setExitPrice('');
      setProfitUsd('');
      setNotes('');
    } catch (err) {
      console.error('Failed saving trade journal entry:', err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleExportCSV = () => {
    if (entries.length === 0) return;
    const headers = ['Date', 'Symbol', 'Action', 'Type', 'Entry', 'Exit', 'SL', 'TP', 'Lots', 'PnL ($)', 'Outcome', 'Setup', 'Notes'];
    const rows = entries.map((e) => [
      e.created_at,
      e.symbol,
      e.order_action,
      e.order_type,
      e.entry_price,
      e.exit_price || '',
      e.stop_loss,
      e.take_profit,
      e.lot_size,
      e.profit_usd,
      e.outcome,
      `"${e.setup_type || ''}"`,
      `"${e.notes || ''}"`,
    ]);
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `trade_journal_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="flex flex-col gap-6 pb-20 lg:pb-6">
      {/* Top Header & Quick Action Buttons */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-[#0d121c]/90 border border-white/[0.08] p-4 sm:p-5 rounded-2xl backdrop-blur-xl">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl">📖</span>
            <h2 className="text-lg sm:text-xl font-black text-slate-100">
              Institutional Trade Journal & Performance Analytics
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Track execution discipline, review holding swing setups, and audit your win rate.
          </p>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <button
            onClick={handleExportCSV}
            disabled={entries.length === 0}
            className="flex-1 sm:flex-initial flex items-center justify-center gap-1.5 px-3.5 py-2.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 border border-white/[0.08] text-xs font-bold transition-all disabled:opacity-40"
          >
            <span>📥</span>
            <span>Export CSV</span>
          </button>

          <button
            onClick={() => setIsModalOpen(true)}
            className="flex-1 sm:flex-initial flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-white text-xs font-bold transition-all shadow-[0_0_15px_rgba(6,182,212,0.3)] active:scale-95"
          >
            <span>➕</span>
            <span>Add Trade Entry</span>
          </button>
        </div>
      </div>

      {/* Performance Analytics HUD */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 sm:gap-4">
        {/* Win Rate */}
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
          <div className="text-[11px] font-bold uppercase text-slate-400 mb-1">Win Rate</div>
          <div className="text-xl sm:text-2xl font-mono font-extrabold text-emerald-400">
            {winRate.toFixed(1)}%
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">{wins.length}W / {losses.length}L</div>
        </div>

        {/* Realized PnL */}
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
          <div className="text-[11px] font-bold uppercase text-slate-400 mb-1">Total Realized PnL</div>
          <div className={`text-xl sm:text-2xl font-mono font-extrabold ${totalPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {totalPnL >= 0 ? `+$${totalPnL.toFixed(2)}` : `-$${Math.abs(totalPnL).toFixed(2)}`}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Across all setups</div>
        </div>

        {/* Profit Factor */}
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
          <div className="text-[11px] font-bold uppercase text-slate-400 mb-1">Profit Factor</div>
          <div className="text-xl sm:text-2xl font-mono font-extrabold text-cyan-300">
            {profitFactor.toFixed(2)}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Gross Win / Gross Loss</div>
        </div>

        {/* Average R:R */}
        <div className="bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
          <div className="text-[11px] font-bold uppercase text-slate-400 mb-1">Target R:R Ratio</div>
          <div className="text-xl sm:text-2xl font-mono font-extrabold text-amber-300">
            1:2.00+
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Strict Minimum Floor</div>
        </div>

        {/* Total Trades Count */}
        <div className="col-span-2 lg:col-span-1 bg-[#0e131d]/90 border border-white/[0.08] p-4 rounded-2xl backdrop-blur-xl">
          <div className="text-[11px] font-bold uppercase text-slate-400 mb-1">Total Recorded</div>
          <div className="text-xl sm:text-2xl font-mono font-extrabold text-slate-100">
            {totalTrades}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">{entries.filter(e => e.outcome === 'OPEN').length} Open Trades</div>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-[#0d121c]/70 border border-white/[0.06] p-3 rounded-xl">
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          {(['ALL', 'WIN', 'LOSS', 'OPEN'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setFilterType(t)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all whitespace-nowrap ${
                filterType === t
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {t === 'ALL' ? 'All Trades' : t === 'WIN' ? 'Wins 🟢' : t === 'LOSS' ? 'Losses 🔴' : 'Active / Open ⏳'}
            </button>
          ))}
        </div>

        <div className="relative">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by symbol, setup, notes..."
            className="w-full sm:w-64 bg-[#080b11] border border-white/[0.08] rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50"
          />
        </div>
      </div>

      {/* Trade Entries List */}
      {filteredEntries.length === 0 ? (
        <div className="bg-[#0d121c]/50 border border-dashed border-white/[0.1] rounded-2xl p-10 text-center">
          <div className="text-3xl mb-2">📝</div>
          <h3 className="text-sm font-bold text-slate-300">No Journal Entries Found</h3>
          <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
            Log your manual and automated trades to build high-conviction performance insights.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredEntries.map((item) => {
            const isWin = item.outcome === 'WIN';
            const isLoss = item.outcome === 'LOSS';
            const isOpen = item.outcome === 'OPEN';

            return (
              <div
                key={item.id}
                className="bg-[#0e131d]/90 border border-white/[0.08] hover:border-white/[0.15] p-4 rounded-2xl backdrop-blur-xl transition-all flex flex-col md:flex-row items-start md:items-center justify-between gap-4"
              >
                {/* Left: Action & Symbol */}
                <div className="flex items-center gap-3">
                  <span
                    className={`text-xs font-extrabold px-2.5 py-1 rounded-xl uppercase ${
                      item.order_action === 'BUY'
                        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                        : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                    }`}
                  >
                    {item.order_action}
                  </span>

                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-extrabold text-sm text-slate-100">{item.symbol}</span>
                      <span className="text-[10px] text-slate-400 px-1.5 py-0.2 rounded bg-white/[0.04]">
                        {item.lot_size} lots
                      </span>
                      {item.session && (
                        <span className="text-[10px] text-cyan-400 px-1.5 py-0.2 rounded bg-cyan-500/10">
                          {item.session} Session
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-slate-400 mt-0.5">
                      Entry: <span className="font-mono text-slate-200">${item.entry_price.toFixed(2)}</span> • SL: <span className="font-mono text-rose-400">${item.stop_loss.toFixed(2)}</span> • TP: <span className="font-mono text-emerald-400">${item.take_profit.toFixed(2)}</span>
                    </div>
                  </div>
                </div>

                {/* Middle: Setup & Notes */}
                <div className="flex-1 text-xs text-slate-300 md:px-4">
                  {item.setup_type && (
                    <div className="font-semibold text-amber-300/90 mb-0.5">
                      {item.setup_type}
                    </div>
                  )}
                  {item.notes && <div className="text-slate-400 text-[11px] italic">"{item.notes}"</div>}
                </div>

                {/* Right: Outcome, PnL & Delete */}
                <div className="flex items-center justify-between md:justify-end gap-4 w-full md:w-auto pt-2 md:pt-0 border-t md:border-t-0 border-white/[0.06]">
                  <div className="text-right">
                    <span
                      className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${
                        isWin
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                          : isLoss
                          ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                          : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                      }`}
                    >
                      {item.outcome}
                    </span>
                    <div className={`font-mono font-extrabold text-sm mt-0.5 ${
                      item.profit_usd >= 0 ? 'text-emerald-400' : 'text-rose-400'
                    }`}>
                      {item.profit_usd >= 0 ? `+$${item.profit_usd.toFixed(2)}` : `-$${Math.abs(item.profit_usd).toFixed(2)}`}
                    </div>
                  </div>

                  <button
                    onClick={() => onDeleteEntry(item.id)}
                    title="Delete Entry"
                    className="text-slate-500 hover:text-rose-400 p-1.5 rounded-lg transition-colors text-xs"
                  >
                    🗑️
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add Trade Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
          <div className="bg-[#0f1420] border border-white/[0.12] rounded-3xl p-6 max-w-lg w-full shadow-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-extrabold text-slate-100 flex items-center gap-2">
                <span>📝</span>
                <span>Log New Trade Entry</span>
              </h3>
              <button
                onClick={() => setIsModalOpen(false)}
                className="text-slate-400 hover:text-slate-200 text-lg p-1"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4 text-xs">
              {/* Row 1: Symbol & Action */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 font-semibold mb-1">Symbol</label>
                  <select
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                    className="w-full bg-[#080b11] border border-white/[0.08] rounded-xl px-3 py-2 text-slate-100"
                  >
                    <option value="XAUUSD">XAUUSD (Gold)</option>
                    <option value="BTCUSD">BTCUSD (Bitcoin)</option>
                    <option value="EURUSD">EURUSD</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-400 font-semibold mb-1">Direction</label>
                  <select
                    value={orderAction}
                    onChange={(e) => {
                      const act = e.target.value as 'BUY' | 'SELL';
                      setOrderAction(act);
                      setOrderType(`${act} MARKET`);
                    }}
                    className="w-full bg-[#080b11] border border-white/[0.08] rounded-xl px-3 py-2 text-slate-100"
                  >
                    <option value="BUY">BUY (Long)</option>
                    <option value="SELL">SELL (Short)</option>
                  </select>
                </div>
              </div>

              {/* Row 2: Entry, SL, TP */}
              <div className="grid grid-cols-3 gap-2.5">
                <div>
                  <label className="block text-slate-400 font-semibold mb-1">Entry Price</label>
                  <input
                    type="number"
                    step="any"
                    required
                    value={entryPrice}
                    onChange={(e) => setEntryPrice(e.target.value)}
                    placeholder="e.g. 2685.50"
                    className="w-full bg-[#080b11] border border-white/[0.08] rounded-xl px-3 py-2 font-mono text-slate-100"
                  />
                </div>

                <div>
                  <label className="block text-rose-400 font-semibold mb-1">Stop Loss</label>
                  <input
                    type="number"
                    step="any"
                    value={stopLoss}
                    onChange={(e) => setStopLoss(e.target.value)}
                    placeholder="e.g. 2670.00"
                    className="w-full bg-[#080b11] border border-white/[0.08] rounded-xl px-3 py-2 font-mono text-rose-300"
                  />
                </div>

                <div>
                  <label className="block text-emerald-400 font-semibold mb-1">Take Profit</label>
                  <input
                    type="number"
                    step="any"
                    value={takeProfit}
                    onChange={(e) => setTakeProfit(e.target.value)}
                    placeholder="e.g. 2715.50"
                    className="w-full bg-[#080b11] border border-white/[0.08] rounded-xl px-3 py-2 font-mono text-emerald-300"
                  />
                </div>
              </div>

              {/* Row 3: Lots, PnL, Outcome */}
              <div className="grid grid-cols-3 gap-2.5">
                <div>
                  <label className="block text-slate-400 font-semibold mb-1">Lot Size</label>
                  <input
                    type="number"
                    step="0.01"
                    value={lotSize}
                    onChange={(e) => setLotSize(e.target.value)}
                    className="w-full bg-[#080b11] border border-white/[0.08] rounded-xl px-3 py-2 font-mono text-slate-100"
                  />
                </div>

                <div>
                  <label className="block text-slate-400 font-semibold mb-1">PnL ($ USD)</label>
                  <input
                    type="number"
                    step="any"
                    value={profitUsd}
                    onChange={(e) => setProfitUsd(e.target.value)}
                    placeholder="+12.50 or -4.00"
                    className="w-full bg-[#080b11] border border-white/[0.08] rounded-xl px-3 py-2 font-mono text-slate-100"
                  />
                </div>

                <div>
                  <label className="block text-slate-400 font-semibold mb-1">Outcome</label>
                  <select
                    value={outcome}
                    onChange={(e) => setOutcome(e.target.value as any)}
                    className="w-full bg-[#080b11] border border-white/[0.08] rounded-xl px-3 py-2 text-slate-100"
                  >
                    <option value="OPEN">Open (Active)</option>
                    <option value="WIN">Win 🟢</option>
                    <option value="LOSS">Loss 🔴</option>
                    <option value="BREAKEVEN">Breakeven ⚪</option>
                  </select>
                </div>
              </div>

              {/* Row 4: Setup Type & Session */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 font-semibold mb-1">Setup Type</label>
                  <input
                    type="text"
                    value={setupType}
                    onChange={(e) => setSetupType(e.target.value)}
                    placeholder="e.g. Liquidity Sweep, FVG Retest"
                    className="w-full bg-[#080b11] border border-white/[0.08] rounded-xl px-3 py-2 text-slate-100"
                  />
                </div>

                <div>
                  <label className="block text-slate-400 font-semibold mb-1">Session</label>
                  <select
                    value={session}
                    onChange={(e) => setSession(e.target.value)}
                    className="w-full bg-[#080b11] border border-white/[0.08] rounded-xl px-3 py-2 text-slate-100"
                  >
                    <option value="London">London Killzone</option>
                    <option value="New York">New York Killzone</option>
                    <option value="Asian">Asian Session</option>
                    <option value="Weekend">Weekend Swing</option>
                  </select>
                </div>
              </div>

              {/* Row 5: Notes */}
              <div>
                <label className="block text-slate-400 font-semibold mb-1">Trade Notes & Psychology</label>
                <textarea
                  rows={2}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="e.g. Held through 4H pullbacks, respected D1 macro bias..."
                  className="w-full bg-[#080b11] border border-white/[0.08] rounded-xl px-3 py-2 text-slate-100"
                ></textarea>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 rounded-xl bg-white/[0.05] hover:bg-white/[0.1] text-slate-300 font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSaving}
                  className="px-5 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-white font-bold transition-all disabled:opacity-50"
                >
                  {isSaving ? 'Saving...' : 'Save Trade Entry'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
