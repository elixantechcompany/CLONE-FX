'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Navbar } from '@/components/Navbar';
import { PWAInstallBanner } from '@/components/PWAInstallBanner';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { SignalsView } from '@/components/SignalsView';
import { EACommandCenter } from '@/components/EACommandCenter';
import { TradeJournalView } from '@/components/TradeJournalView';
import { PositionsView } from '@/components/PositionsView';
import { AccountsView } from '@/components/AccountsView';
import {
  ConfluenceSignal,
  JournalEntry,
  LivePosition,
  FleetAccount,
  MarketSchedule,
  DashboardApiResponse,
} from '@/lib/types';
import { fetchMarketDataBundle } from '@/lib/marketData';
import { runConfluenceScan } from '@/lib/confluenceEngine';

export default function Home() {
  const [activeTab, setActiveTab] = useState<'signals' | 'ea' | 'journal' | 'positions' | 'accounts'>('signals');
  const [selectedSymbol, setSelectedSymbol] = useState<'XAUUSD' | 'BTCUSD'>('XAUUSD');
  const [eaRunning, setEaRunning] = useState<boolean>(true);
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [isLaunchingTerminal, setIsLaunchingTerminal] = useState<boolean>(false);

  // Live Data State
  const [activeSignals, setActiveSignals] = useState<ConfluenceSignal[]>([]);
  const [formingSetups, setFormingSetups] = useState<ConfluenceSignal[]>([]);
  const [positions, setPositions] = useState<LivePosition[]>([]);
  const [accounts, setAccounts] = useState<FleetAccount[]>([
    {
      id: 'account_d',
      name: 'GOLD CLONE',
      type: 'REAL',
      balance: 36.58,
      equity: 36.65,
      margin: 0,
      free_margin: 36.58,
      profit: 0.07,
      drawdown_pct: 0,
      status: 'CONNECTED',
      execution_mode: 'AUTOMATED_EA',
    },
  ]);
  const [journalEntries, setJournalEntries] = useState<JournalEntry[]>([]);
  const [pendingSignalToLog, setPendingSignalToLog] = useState<ConfluenceSignal | null>(null);

  const [currentPrice, setCurrentPrice] = useState<number>(2695.5);
  const [macroBias, setMacroBias] = useState<string>('INSTITUTIONAL ACCUMULATION (D1+H4 Aligned)');
  const [marketSchedules, setMarketSchedules] = useState<Record<string, MarketSchedule>>({
    XAUUSD: {
      symbol: 'XAUUSD',
      is_open: false,
      status: 'CLOSED',
      status_text: 'MARKET CLOSED (Weekend - Reopens Sun 22:00 UTC)',
      asset_type: 'COMMODITY_FOREX',
    },
    BTCUSD: {
      symbol: 'BTCUSD',
      is_open: true,
      status: 'OPEN',
      status_text: 'MARKET OPEN (24/7 Crypto)',
      asset_type: 'CRYPTO_24_7',
    },
  });

  const [killzoneInfo, setKillzoneInfo] = useState({
    is_killzone: true,
    session_name: 'London Killzone (Peak Volume)',
    trading_allowed: true,
    utc_time: 'LIVE UTC',
  });

  const [adrInfo, setAdrInfo] = useState({
    adr_used_pct: 45,
    range_pts: 14.5,
    typical_adr: 32.0,
    is_exhausted: false,
    warning: 'Normal Daily Range (Clean expansion headroom)',
  });

  // URL Hash Sync for fast deep linking
  useEffect(() => {
    const hash = window.location.hash.replace('#', '') as any;
    if (['signals', 'ea', 'journal', 'positions', 'accounts'].includes(hash)) {
      setActiveTab(hash);
    }
  }, []);

  const handleTabChange = (tab: 'signals' | 'ea' | 'journal' | 'positions' | 'accounts') => {
    setActiveTab(tab);
    window.location.hash = tab;
  };

  // 1. Fetch Dashboard & MT5 Fleet Data
  const fetchDashboardData = useCallback(async () => {
    try {
      const res = await fetch('/api/dashboard', { cache: 'no-store' });
      if (res.ok) {
        const data: DashboardApiResponse = await res.json();
        if (data.master_switch) {
          setEaRunning(!!data.master_switch.algo_trading_active);
        }
        if (data.accounts && data.accounts.length > 0) {
          setAccounts(data.accounts);
        }
        if (data.positions) {
          setPositions(data.positions);
        }
        if (data.perfect_setups && data.perfect_setups.length > 0) {
          setActiveSignals(data.perfect_setups);
        }
        if (data.forming_setups) {
          setFormingSetups(data.forming_setups);
        }
        if (data.market_schedules) {
          setMarketSchedules(data.market_schedules);
        }
        if ((data as any).killzone) {
          setKillzoneInfo((data as any).killzone);
        }
        if ((data as any).adr) {
          setAdrInfo((data as any).adr);
        }
      }
    } catch (e) {
      // Local daemon offline fallback - scan via web market data
    }
  }, []);

  // 1b. Fetch Cloud Signals from Supabase via /api/signals
  const fetchCloudSignals = useCallback(async () => {
    try {
      const res = await fetch('/api/signals', { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        if (data.signals && data.signals.length > 0) {
          const symbolSignals = data.signals.filter((s: ConfluenceSignal) => s.symbol === selectedSymbol);
          const toShow = symbolSignals.length > 0 ? symbolSignals : data.signals;
          setActiveSignals((prev) => (prev.length > 0 ? prev : toShow));
          if (toShow[0]?.htfConfluence?.dailyBias) {
            setMacroBias(toShow[0].htfConfluence.dailyBias);
          }
        }
      }
    } catch (e) {
      console.warn('Could not fetch cloud signals:', e);
    }
  }, [selectedSymbol]);

  // 2. Scan Live Market Confluence (Vercel + Local Universal Fallback)
  const scanMarketData = useCallback(async () => {
    setIsScanning(true);
    try {
      // Trigger server-side scan first
      try {
        const scanRes = await fetch('/api/scan', { method: 'POST', cache: 'no-store' });
        if (scanRes.ok) {
          const scanJson = await scanRes.json();
          if (scanJson.results) {
            const found = scanJson.results.find((r: any) => r.signalFound && r.signal);
            if (found && found.signal) {
              setActiveSignals([found.signal]);
            }
          }
        }
      } catch (e) {}

      const bundle = await fetchMarketDataBundle(selectedSymbol);
      if (bundle) {
        const h4Candles = bundle.timeframes['4h'];
        const h1Candles = bundle.timeframes['1h'];
        const lastH1 = h1Candles[h1Candles.length - 1];
        if (lastH1) {
          setCurrentPrice(lastH1.close);
        }

        const signal = runConfluenceScan(bundle);
        if (signal) {
          setActiveSignals([signal]);
          setMacroBias(signal.htfConfluence?.dailyBias || 'BULLISH EXPANSION');
        }
      }

      await fetchDashboardData();
      await fetchCloudSignals();
    } catch (err) {
      console.warn('Market scan warning:', err);
    } finally {
      setIsScanning(false);
    }
  }, [selectedSymbol, fetchDashboardData, fetchCloudSignals]);

  // 3. Fetch Journal Entries (Supabase + localStorage fallback)
  const fetchJournalEntries = useCallback(async () => {
    try {
      const res = await fetch('/api/journal', { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        if (data.entries && data.entries.length > 0) {
          setJournalEntries(data.entries);
          localStorage.setItem('fx_trade_journal', JSON.stringify(data.entries));
          return;
        }
      }
    } catch (e) {}

    // LocalStorage fallback
    try {
      const cached = localStorage.getItem('fx_trade_journal');
      if (cached) {
        setJournalEntries(JSON.parse(cached));
      }
    } catch (e) {}
  }, []);

  useEffect(() => {
    fetchDashboardData();
    fetchCloudSignals();
    scanMarketData();
    fetchJournalEntries();

    const interval = setInterval(() => {
      fetchDashboardData();
      fetchCloudSignals();
    }, 5000);

    return () => clearInterval(interval);
  }, [fetchDashboardData, fetchCloudSignals, scanMarketData, fetchJournalEntries]);

  // EA Toggle Handler
  const handleToggleEA = async () => {
    const newState = !eaRunning;
    setEaRunning(newState); // Optimistic UI

    try {
      const res = await fetch('/api/ea/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: newState }),
      });
      if (res.ok) {
        const data = await res.json();
        setEaRunning(!!data.algo_trading_active);
      }
    } catch (err) {
      console.warn('EA toggle API warning:', err);
    }
  };

  // Launch MT5 Terminal Handler
  const handleLaunchTerminal = async (): Promise<boolean> => {
    setIsLaunchingTerminal(true);
    try {
      const res = await fetch('/api/accounts/launch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accountId: 'account_d' }),
      });
      const data = await res.json();
      return !!data.success;
    } catch (e) {
      return false;
    } finally {
      setIsLaunchingTerminal(false);
    }
  };

  // Journal Handlers
  const handleAddJournalEntry = async (entryData: Omit<JournalEntry, 'id' | 'created_at'>) => {
    const newEntry: JournalEntry = {
      ...entryData,
      id: `j_${Date.now()}`,
      created_at: new Date().toISOString(),
    };

    const updated = [newEntry, ...journalEntries];
    setJournalEntries(updated);
    try {
      localStorage.setItem('fx_trade_journal', JSON.stringify(updated));
      await fetch('/api/journal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newEntry),
      });
    } catch (e) {}
  };

  const handleDeleteJournalEntry = async (id: string) => {
    const updated = journalEntries.filter((j) => j.id !== id);
    setJournalEntries(updated);
    try {
      localStorage.setItem('fx_trade_journal', JSON.stringify(updated));
      await fetch(`/api/journal?id=${id}`, { method: 'DELETE' });
    } catch (e) {}
  };

  // 1-Click "Log Signal to Journal" action from Signals page
  const handleLogSignalToJournal = (sig: ConfluenceSignal) => {
    setPendingSignalToLog(sig);
    handleTabChange('journal');
  };

  const primaryAccount = accounts[0] || null;

  return (
    <div className="min-h-screen bg-[#07080b] text-slate-100 flex flex-col font-sans selection:bg-amber-500/30 selection:text-amber-200">
      {/* Top Navbar */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={handleTabChange}
        eaRunning={eaRunning}
        onToggleEA={handleToggleEA}
        balance={primaryAccount?.balance || 36.58}
        equity={primaryAccount?.equity || 36.65}
        accountName={primaryAccount?.name || 'GOLD CLONE'}
        isOnline={true}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-3 sm:p-5 md:p-6 transition-all duration-300 flex flex-col gap-4">
        {/* PWA Mobile Installation Prompt Banner */}
        <PWAInstallBanner />

        {activeTab === 'signals' && (
          <SignalsView
            selectedSymbol={selectedSymbol}
            setSelectedSymbol={setSelectedSymbol}
            activeSignals={activeSignals}
            formingSetups={formingSetups}
            marketSchedules={marketSchedules}
            currentPrice={currentPrice}
            macroBias={macroBias}
            killzoneInfo={killzoneInfo}
            adrInfo={adrInfo}
            onLogToJournal={handleLogSignalToJournal}
            onRefresh={scanMarketData}
            isScanning={isScanning}
          />
        )}

        {activeTab === 'ea' && (
          <EACommandCenter
            eaRunning={eaRunning}
            onToggleEA={handleToggleEA}
            account={primaryAccount}
            onLaunchTerminal={handleLaunchTerminal}
            isLaunchingTerminal={isLaunchingTerminal}
          />
        )}

        {activeTab === 'journal' && (
          <TradeJournalView
            entries={journalEntries}
            onAddEntry={handleAddJournalEntry}
            onDeleteEntry={handleDeleteJournalEntry}
            pendingSignalToLog={pendingSignalToLog}
            onClearPendingSignal={() => setPendingSignalToLog(null)}
          />
        )}

        {activeTab === 'positions' && (
          <PositionsView
            positions={positions}
            account={primaryAccount}
            onRefresh={fetchDashboardData}
          />
        )}

        {activeTab === 'accounts' && (
          <AccountsView
            accounts={accounts}
            onLaunchTerminal={handleLaunchTerminal}
            isLaunchingTerminal={isLaunchingTerminal}
            onRefresh={fetchDashboardData}
          />
        )}
      </main>

      {/* Mobile Sticky Bottom Dock */}
      <MobileBottomNav
        activeTab={activeTab}
        setActiveTab={handleTabChange}
        eaRunning={eaRunning}
        positionsCount={positions.length}
      />
    </div>
  );
}
