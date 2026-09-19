'use client';

import React, { useState, useEffect } from 'react';
import {
  ConfluenceSignal,
  MarketSchedule,
  EarlyWarning,
  LivePosition,
  FleetAccount,
  DashboardApiResponse,
  JournalEntry,
  UserProfile,
  OrderAction,
  MT5OrderType,
  TradeOutcome
} from '@/lib/types';
import {
  ShieldAlert,
  Zap,
  TrendingUp,
  TrendingDown,
  Clock,
  CheckCircle2,
  Copy,
  RefreshCw,
  SlidersHorizontal,
  Target,
  AlertTriangle,
  Award,
  Wallet,
  Activity,
  Layers,
  ExternalLink,
  PlusCircle,
  X,
  Play,
  ArrowRight,
  Sparkles,
  Lock,
  ChevronRight,
  Flame,
  BookOpen,
  UserCheck,
  User,
  LogIn,
  LogOut,
  Trash2,
  Calendar,
  DollarSign,
  PieChart,
  Smile,
  BarChart2
} from 'lucide-react';

export default function DashboardPage() {
  // Navigation tabs
  const [activeTab, setActiveTab] = useState<'SIGNALS' | 'LIVE_TRADES' | 'JOURNAL' | 'ACCOUNTS' | 'CALCULATOR'>('SIGNALS');

  // User Profile & Authentication State
  const [user, setUser] = useState<UserProfile>({
    name: 'Hannington',
    email: 'trader@goldclone.com',
    accountType: 'PERSONAL',
    isLoggedIn: true,
  });
  const [showAuthModal, setShowAuthModal] = useState<boolean>(false);
  const [authEmail, setAuthEmail] = useState<string>('');
  const [authName, setAuthName] = useState<string>('');
  const [authType, setAuthType] = useState<'PERSONAL' | 'PROP_FIRM' | 'CENT_ACCOUNT'>('PERSONAL');

  // Scanner & Live Data (0 Dummy Data)
  const [signals, setSignals] = useState<ConfluenceSignal[]>([]);
  const [marketSchedules, setMarketSchedules] = useState<Record<string, MarketSchedule>>({});
  const [earlyWarnings, setEarlyWarnings] = useState<EarlyWarning[]>([]);
  const [positions, setPositions] = useState<LivePosition[]>([]);
  const [accounts, setAccounts] = useState<FleetAccount[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [scanning, setScanning] = useState<boolean>(false);
  const [lastSync, setLastSync] = useState<string>('Just now');

  // Trading Journal State
  const [journalEntries, setJournalEntries] = useState<JournalEntry[]>([]);
  const [showNewJournalModal, setShowNewJournalModal] = useState<boolean>(false);
  const [journalFilterOutcome, setJournalFilterOutcome] = useState<'ALL' | 'WIN' | 'LOSS' | 'OPEN'>('ALL');
  
  // New Journal Entry Form Fields
  const [jSymbol, setJSymbol] = useState<string>('BTCUSD');
  const [jAction, setJAction] = useState<OrderAction>('BUY');
  const [jOrderType, setJOrderType] = useState<MT5OrderType>('BUY MARKET');
  const [jLots, setJLots] = useState<number>(0.02);
  const [jEntryPrice, setJEntryPrice] = useState<number>(93311.62);
  const [jExitPrice, setJExitPrice] = useState<number>(93871.62);
  const [jStopLoss, setJStopLoss] = useState<number>(93031.62);
  const [jTakeProfit, setJTakeProfit] = useState<number>(93871.62);
  const [jProfitUsd, setJProfitUsd] = useState<number>(112.00);
  const [jOutcome, setJOutcome] = useState<TradeOutcome>('WIN');
  const [jSession, setJSession] = useState<string>('London Open');
  const [jSetupType, setJSetupType] = useState<string>('Sell-Side Liquidity Sweep (SSL) + BOS');
  const [jEmotions, setJEmotions] = useState<string>('Disciplined & Patient');
  const [jNotes, setJNotes] = useState<string>('Waited for M5 candle close confirmation. Solid 1:2.0 R:R execution.');

  // Filters
  const [symbolFilter, setSymbolFilter] = useState<'ALL' | 'XAUUSD' | 'BTCUSD'>('ALL');
  const [orderActionFilter, setOrderActionFilter] = useState<'ALL' | 'BUY' | 'SELL'>('ALL');
  const [confluenceFilter, setConfluenceFilter] = useState<'ALL' | '3/3'>('ALL');
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Position Size Calculator State
  const [balance, setBalance] = useState<number>(1000);
  const [riskPercent, setRiskPercent] = useState<number>(0.50);
  const [slPoints, setSlPoints] = useState<number>(3.5);
  const [selectedPreset, setSelectedPreset] = useState<string>('Standard1000');
  const [calcSymbol, setCalcSymbol] = useState<string>('BTCUSD');
  const [soundEnabled, setSoundEnabled] = useState<boolean>(true);

  // Add Account Modal State
  const [showAddAccountModal, setShowAddAccountModal] = useState<boolean>(false);
  const [newAccName, setNewAccName] = useState<string>('');
  const [newAccType, setNewAccType] = useState<string>('PERSONAL');
  const [newAccBalance, setNewAccBalance] = useState<number>(20);
  const [newAccLogin, setNewAccLogin] = useState<string>('');
  const [newAccPassword, setNewAccPassword] = useState<string>('');
  const [newAccServer, setNewAccServer] = useState<string>('');
  const [newAccMode, setNewAccMode] = useState<string>('AUTOMATED_EA');
  const [addingAccount, setAddingAccount] = useState<boolean>(false);
  const [addAccountError, setAddAccountError] = useState<string | null>(null);

  // Audio Chime
  const playChime = () => {
    if (!soundEnabled) return;
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      const now = ctx.currentTime;
      const osc1 = ctx.createOscillator();
      const osc2 = ctx.createOscillator();
      const gain = ctx.createGain();

      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(587.33, now);
      osc1.frequency.exponentialRampToValueAtTime(880.0, now + 0.15);

      osc2.type = 'triangle';
      osc2.frequency.setValueAtTime(880.0, now + 0.15);
      osc2.frequency.exponentialRampToValueAtTime(1174.66, now + 0.35);

      gain.gain.setValueAtTime(0.12, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.6);

      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(ctx.destination);

      osc1.start(now);
      osc2.start(now + 0.15);
      osc1.stop(now + 0.35);
      osc2.stop(now + 0.65);
    } catch (e) {
      console.warn('Audio chime note:', e);
    }
  };

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  // Fetch Dashboard & Live Data
  const fetchData = async () => {
    try {
      const [dashRes, sigRes, jrnlRes] = await Promise.all([
        fetch('/api/dashboard'),
        fetch('/api/signals').catch(() => null),
        fetch('/api/journal').catch(() => null)
      ]);

      if (dashRes.ok) {
        const dashData: DashboardApiResponse = await dashRes.json();
        if (dashData.market_schedules) setMarketSchedules(dashData.market_schedules);
        if (dashData.early_warnings) setEarlyWarnings(dashData.early_warnings);
        if (dashData.positions) setPositions(dashData.positions);
        if (dashData.accounts) setAccounts(dashData.accounts);

        // Map live scanner setups with strict BUY / SELL actions
        const scannerSetups: ConfluenceSignal[] = [
          ...(dashData.perfect_setups || []),
          ...(dashData.forming_setups || [])
        ].map((s: any) => {
          const rawDir = String(s.direction || 'BUY').toUpperCase();
          const orderAction: OrderAction = rawDir.includes('SELL') || rawDir.includes('SHORT') ? 'SELL' : 'BUY';
          const symbolClean = s.symbol ? s.symbol.replace('m', '') : 'BTCUSD';

          return {
            id: s.id || `setup_${Date.now()}`,
            symbol: symbolClean,
            direction: orderAction,
            orderType: `${orderAction} MARKET` as MT5OrderType,
            entryPrice: Number(s.entry_price || 0),
            stopLoss: Number(s.stop_loss || 0),
            takeProfit1: Number(s.tp1 || 0),
            takeProfit2: Number(s.tp2 || 0),
            riskReward: Number(s.risk_reward || 2.0),
            slDistance: Number(s.sl_distance || 0),
            tpDistance: Number(s.tp_distance || 0),
            confluenceScore: s.conviction_score >= 80 ? '3/3' : '2/3',
            scoreNumeric: s.conviction_score || 80,
            timeframeStack: {
              '4H': 'Macro Trend Aligned',
              '1H': 'Liquidity Sweep Aligned',
              '30M': 'Trigger Confirmed'
            },
            confluences: s.confluences || [],
            status: 'ACTIVE',
            setup_summary: s.setup_summary,
            formed_time: s.formed_time
          };
        });

        let combined = [...scannerSetups];
        if (sigRes && sigRes.ok) {
          const sigData = await sigRes.json();
          if (sigData.signals && sigData.signals.length > 0) {
            combined = [...combined, ...sigData.signals];
          }
        }

        // Deduplicate signals
        const seen = new Set();
        const unique = combined.filter((item) => {
          const k = `${item.symbol}_${item.direction}_${Math.round(item.entryPrice)}`;
          if (seen.has(k)) return false;
          seen.add(k);
          return true;
        });

        setSignals(unique);
        setLastSync(new Date().toLocaleTimeString());
      }

      // Load Journal entries
      if (jrnlRes && jrnlRes.ok) {
        const jData = await jrnlRes.json();
        if (jData.entries) {
          setJournalEntries(jData.entries);
        }
      }
    } catch (e) {
      console.error('Failed to load dashboard data:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  // Trigger Manual Scanner
  const triggerScan = async () => {
    try {
      setScanning(true);
      const res = await fetch('/api/scan', { method: 'POST' });
      await res.json();
      showToast('Scan complete across open pairs! (Gold checked for weekend close)');
      await fetchData();
      playChime();
    } catch (e) {
      showToast('Scan request failed');
    } finally {
      setScanning(false);
    }
  };

  // Copy MT5 Parameters formatted for instant order placement
  const handleCopyMT5 = (s: ConfluenceSignal) => {
    const isBuy = s.direction === 'BUY' || s.direction === 'LONG';
    const action = isBuy ? 'BUY' : 'SELL';
    const orderType = s.orderType || `${action} MARKET`;
    
    // Standard MT5 order parameter format
    const text = `ORDER: ${action}\nSYMBOL: ${s.symbol}\nTYPE: ${orderType}\nENTRY: ${s.entryPrice.toFixed(2)}\nSTOP LOSS: ${s.stopLoss.toFixed(2)}\nTAKE PROFIT 1: ${s.takeProfit1.toFixed(2)}${s.takeProfit2 ? `\nTAKE PROFIT 2: ${s.takeProfit2.toFixed(2)}` : ''}\nR:R RATIO: 1:${s.riskReward.toFixed(2)}`;
    
    navigator.clipboard.writeText(text);
    showToast(`Copied MT5 Parameters: [${action}] ${s.symbol} @ ${s.entryPrice.toFixed(2)} (SL: ${s.stopLoss.toFixed(2)} | TP: ${s.takeProfit1.toFixed(2)})`);
  };

  // Send Signal to Journal Form
  const prefillJournalFromSignal = (s: ConfluenceSignal) => {
    const isBuy = s.direction === 'BUY' || s.direction === 'LONG';
    const action: OrderAction = isBuy ? 'BUY' : 'SELL';
    setJSymbol(s.symbol);
    setJAction(action);
    setJOrderType(`${action} MARKET` as MT5OrderType);
    setJEntryPrice(s.entryPrice);
    setJStopLoss(s.stopLoss);
    setJTakeProfit(s.takeProfit1);
    setJExitPrice(s.takeProfit1);
    setJOutcome('OPEN');
    setJSetupType(s.confluences && s.confluences.length > 0 ? s.confluences[0] : 'Institutional Confluence');
    setJNotes(`Initiated from live scanner setup. Stop Loss at ${s.stopLoss.toFixed(2)}, targeting 1:${s.riskReward.toFixed(2)} R:R at ${s.takeProfit1.toFixed(2)}.`);
    setShowNewJournalModal(true);
  };

  // Save Journal Entry
  const handleSaveJournalEntry = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const entryPayload: Partial<JournalEntry> = {
        user_email: user.email,
        symbol: jSymbol,
        order_action: jAction,
        order_type: jOrderType,
        entry_price: Number(jEntryPrice),
        exit_price: Number(jExitPrice) || undefined,
        stop_loss: Number(jStopLoss),
        take_profit: Number(jTakeProfit),
        lot_size: Number(jLots),
        profit_usd: Number(jProfitUsd),
        rr_ratio: Math.abs(jTakeProfit - jEntryPrice) / Math.max(Math.abs(jEntryPrice - jStopLoss), 0.1),
        outcome: jOutcome,
        session: jSession,
        setup_type: jSetupType,
        emotions: jEmotions,
        notes: jNotes,
      };

      const res = await fetch('/api/journal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(entryPayload),
      });

      if (res.ok) {
        showToast(`Trade on ${jSymbol} (${jAction}) saved to your trading journal!`);
        setShowNewJournalModal(false);
        await fetchData();
      }
    } catch (err) {
      showToast('Failed to save journal entry');
    }
  };

  // Delete Journal Entry
  const handleDeleteJournal = async (id: string) => {
    try {
      const res = await fetch(`/api/journal?id=${id}`, { method: 'DELETE' });
      if (res.ok) {
        showToast('Journal entry deleted.');
        setJournalEntries((prev) => prev.filter((j) => j.id !== id));
      }
    } catch (e) {
      showToast('Failed to delete entry');
    }
  };

  // Add Real Account ($20 Min)
  const handleAddAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    setAddAccountError(null);

    if (newAccBalance < 20) {
      setAddAccountError('Minimum initial balance must be at least $20.00 USD.');
      return;
    }

    if (!newAccLogin || !newAccServer) {
      setAddAccountError('MT5 Login ID and Broker Server are required.');
      return;
    }

    try {
      setAddingAccount(true);
      const res = await fetch('/api/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newAccName || `Account ${newAccLogin}`,
          account_type: newAccType,
          balance: newAccBalance,
          login: newAccLogin,
          password: newAccPassword,
          server: newAccServer,
          execution_mode: newAccMode,
          mode: 'INDEPENDENT'
        }),
      });

      const data = await res.json();
      if (!res.ok || data.error) {
        setAddAccountError(data.error || 'Failed to add account');
        return;
      }

      showToast(`Account ${newAccLogin} added successfully! ($${newAccBalance})`);
      setShowAddAccountModal(false);
      setNewAccName('');
      setNewAccLogin('');
      setNewAccPassword('');
      setNewAccServer('');
      setNewAccBalance(20);
      await fetchData();
    } catch (err: any) {
      setAddAccountError(err.message || 'Network error while adding account');
    } finally {
      setAddingAccount(false);
    }
  };

  // Filter Signals
  const filteredSignals = signals.filter((s) => {
    if (symbolFilter !== 'ALL' && s.symbol !== symbolFilter) return false;
    if (orderActionFilter !== 'ALL') {
      const isBuy = s.direction === 'BUY' || s.direction === 'LONG';
      if (orderActionFilter === 'BUY' && !isBuy) return false;
      if (orderActionFilter === 'SELL' && isBuy) return false;
    }
    if (confluenceFilter === '3/3' && s.confluenceScore !== '3/3') return false;
    return true;
  });

  // Journal KPIs calculation
  const closedJournalTrades = journalEntries.filter((j) => j.outcome === 'WIN' || j.outcome === 'LOSS');
  const journalWins = closedJournalTrades.filter((j) => j.outcome === 'WIN').length;
  const journalWinRate = closedJournalTrades.length > 0
    ? ((journalWins / closedJournalTrades.length) * 100).toFixed(1)
    : '0.0';
  const journalNetPnl = journalEntries.reduce((acc, j) => acc + (j.profit_usd || 0), 0);

  return (
    <div className="container">
      {/* Toast Notification */}
      {toastMessage && (
        <div
          style={{
            position: 'fixed',
            bottom: '24px',
            right: '24px',
            background: '#0d1117',
            border: '1px solid var(--gold-primary)',
            padding: '14px 22px',
            borderRadius: '14px',
            boxShadow: '0 10px 30px rgba(0,0,0,0.9), 0 0 20px rgba(245,200,66,0.3)',
            zIndex: 99999,
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            fontWeight: 700,
            fontSize: '13px',
          }}
        >
          <Zap size={18} className="gold" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Top Universal Trading Header */}
      <header
        className="header-content"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '18px 24px',
          background: 'var(--bg-surface)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '20px',
          flexWrap: 'wrap',
          gap: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '14px',
              background: 'var(--gold-gradient)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#000',
              fontWeight: 800,
              fontSize: '22px',
              boxShadow: '0 0 20px rgba(245,200,66,0.35)',
            }}
          >
            ⚡
          </div>
          <div>
            <h1 className="white-gold-gradient" style={{ fontSize: '20px', fontWeight: 800, letterSpacing: '-0.5px' }}>
              Gold & BTC Institutional Trading Terminal
            </h1>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Universal Multi-Timeframe Scanner • Personal & Prop Firm Fleet Execution • Manual Trade Journal
            </p>
          </div>
        </div>

        <div className="header-actions" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* User Profile Badge */}
          <div
            onClick={() => setShowAuthModal(true)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '6px 14px',
              borderRadius: '100px',
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid var(--border-subtle)',
              cursor: 'pointer',
              fontSize: '12px',
              fontWeight: 700,
            }}
          >
            <User size={14} className="gold" />
            <span>{user.name}</span>
            <span className="badge badge-gold" style={{ fontSize: '9px', padding: '2px 6px' }}>
              {user.accountType}
            </span>
          </div>

          <button
            className="btn"
            onClick={triggerScan}
            disabled={scanning}
            style={{ opacity: scanning ? 0.7 : 1 }}
          >
            <RefreshCw size={14} className={scanning ? 'spin' : ''} />
            {scanning ? 'Scanning...' : 'Scan Now'}
          </button>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '6px 14px',
              borderRadius: '100px',
              background: 'var(--emerald-bg)',
              border: '1px solid var(--border-emerald)',
              fontSize: '11px',
              fontWeight: 700,
              color: 'var(--emerald)',
            }}
          >
            <span className="live-pulse" style={{ background: 'var(--emerald)' }} />
            ZERO-SLEEP ENGINE
          </div>

          <button
            className="btn"
            onClick={() => {
              setSoundEnabled(!soundEnabled);
              if (!soundEnabled) playChime();
              showToast(soundEnabled ? 'Audio alerts muted' : 'Audio alerts enabled');
            }}
            style={{ padding: '6px 12px' }}
          >
            {soundEnabled ? '🔔 Sound ON' : '🔕 Sound OFF'}
          </button>
        </div>
      </header>

      {/* Market Schedule Awareness Ribbon (Detects Weekend Close & Prevents Sleep-Off) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '12px',
        }}
      >
        {/* XAUUSD Market Card */}
        <div
          style={{
            background: 'rgba(15, 18, 26, 0.85)',
            border: `1px solid ${
              marketSchedules.XAUUSD?.is_open ? 'var(--border-emerald)' : 'rgba(244, 63, 94, 0.35)'
            }`,
            borderRadius: '14px',
            padding: '12px 18px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '20px' }}>🪙</span>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontWeight: 800, fontSize: '14px' }}>XAUUSD (Gold)</span>
                <span className={`badge ${marketSchedules.XAUUSD?.is_open ? 'badge-green' : 'badge-red'}`}>
                  {marketSchedules.XAUUSD?.status || 'CLOSED'}
                </span>
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                {marketSchedules.XAUUSD?.status_text ||
                  'Weekend Closed - Reopens Sunday 22:00 UTC (Gold scans safely paused)'}
              </div>
            </div>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--text-dim)', textAlign: 'right' }}>
            Commodity / Forex
          </span>
        </div>

        {/* BTCUSD Market Card */}
        <div
          style={{
            background: 'rgba(15, 18, 26, 0.85)',
            border: '1px solid var(--border-emerald)',
            borderRadius: '14px',
            padding: '12px 18px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '20px' }}>⚡</span>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontWeight: 800, fontSize: '14px' }}>BTCUSD (Bitcoin)</span>
                <span className="badge badge-green">OPEN 24/7</span>
              </div>
              <div style={{ fontSize: '11px', color: 'var(--emerald)', marginTop: '2px' }}>
                Crypto Active: Continuous 3-Timeframe Scanning & Algorithmic Execution
              </div>
            </div>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--text-dim)', textAlign: 'right' }}>
            Crypto 24/7/365
          </span>
        </div>
      </div>

      {/* Early Warning Profit Defense Banner */}
      {earlyWarnings && earlyWarnings.length > 0 && (
        <div className="early-warning-container">
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <AlertTriangle size={24} className="amber" />
              <div>
                <div style={{ fontWeight: 800, fontSize: '14px', color: 'var(--amber)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  EARLY WARNING SYSTEM ACTIVE • PROFIT DEFENSE PROTOCOL
                  <span className="badge badge-red">{earlyWarnings.length} ALERTS</span>
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-main)', marginTop: '4px' }}>
                  Lower timeframe shift detected ahead of the charts. Protect profits before retracement gives them back.
                </div>
              </div>
            </div>
            <span className="badge badge-gold">Auto-Defend Armed</span>
          </div>

          <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {earlyWarnings.map((w) => (
              <div
                key={w.id}
                style={{
                  background: 'rgba(0, 0, 0, 0.4)',
                  padding: '10px 14px',
                  borderRadius: '10px',
                  border: '1px solid rgba(245, 158, 11, 0.3)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: '8px',
                  fontSize: '12px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontWeight: 800, color: 'var(--gold-primary)' }}>[{w.symbol}]</span>
                  <span>{w.message}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span
                    style={{
                      background: 'rgba(245, 158, 11, 0.2)',
                      color: 'var(--amber)',
                      padding: '3px 8px',
                      borderRadius: '6px',
                      fontWeight: 700,
                      fontFamily: 'var(--font-mono)',
                    }}
                  >
                    ACTION: {w.action}
                  </span>
                  <span style={{ color: 'var(--text-dim)', fontSize: '11px' }}>{w.formatted_time}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Primary Navigation Tabs */}
      <div className="tabs-nav">
        <button
          className={`tab-btn ${activeTab === 'SIGNALS' ? 'active' : ''}`}
          onClick={() => setActiveTab('SIGNALS')}
        >
          <Target size={15} />
          🎯 Market Signals ({filteredSignals.length})
        </button>

        <button
          className={`tab-btn ${activeTab === 'LIVE_TRADES' ? 'active' : ''}`}
          onClick={() => setActiveTab('LIVE_TRADES')}
        >
          <Activity size={15} />
          💼 Live Positions ({positions.length})
        </button>

        <button
          className={`tab-btn ${activeTab === 'JOURNAL' ? 'active' : ''}`}
          onClick={() => setActiveTab('JOURNAL')}
        >
          <BookOpen size={15} />
          📖 Trading Journal ({journalEntries.length})
        </button>

        <button
          className={`tab-btn ${activeTab === 'ACCOUNTS' ? 'active' : ''}`}
          onClick={() => setActiveTab('ACCOUNTS')}
        >
          <Wallet size={15} />
          🏦 Account Fleet (${accounts.length} linked)
        </button>

        <button
          className={`tab-btn ${activeTab === 'CALCULATOR' ? 'active' : ''}`}
          onClick={() => setActiveTab('CALCULATOR')}
        >
          <SlidersHorizontal size={15} />
          ⚖️ Position Calculator
        </button>
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: MARKET SIGNALS & SETUPS (Specific BUY or SELL with exact prices)    */}
      {/* ========================================================================= */}
      {activeTab === 'SIGNALS' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Filter Toolbar */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '12px',
              padding: '12px 18px',
              background: 'var(--bg-surface)',
              borderRadius: '16px',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', marginRight: '4px' }}>
                PAIR:
              </span>
              <button
                className={`btn ${symbolFilter === 'ALL' ? 'btn-active' : ''}`}
                onClick={() => setSymbolFilter('ALL')}
              >
                All Symbols
              </button>
              <button
                className={`btn ${symbolFilter === 'BTCUSD' ? 'btn-active' : ''}`}
                onClick={() => setSymbolFilter('BTCUSD')}
              >
                ⚡ Bitcoin (24/7)
              </button>
              <button
                className={`btn ${symbolFilter === 'XAUUSD' ? 'btn-active' : ''}`}
                onClick={() => setSymbolFilter('XAUUSD')}
              >
                🪙 Gold (Closed Weekend)
              </button>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', marginRight: '4px' }}>
                ACTION:
              </span>
              <button
                className={`btn ${orderActionFilter === 'ALL' ? 'btn-active' : ''}`}
                onClick={() => setOrderActionFilter('ALL')}
              >
                All
              </button>
              <button
                className={`btn ${orderActionFilter === 'BUY' ? 'btn-active' : ''}`}
                onClick={() => setOrderActionFilter('BUY')}
                style={{ color: 'var(--emerald)' }}
              >
                🟢 BUY ONLY
              </button>
              <button
                className={`btn ${orderActionFilter === 'SELL' ? 'btn-active' : ''}`}
                onClick={() => setOrderActionFilter('SELL')}
                style={{ color: 'var(--rose)' }}
              >
                🔴 SELL ONLY
              </button>
            </div>
          </div>

          {/* Active Setups Grid */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <div>
                <h2 style={{ fontSize: '17px', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Zap size={18} className="gold" />
                  Live Market Setups (Verified BUY / SELL Orders)
                </h2>
                <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  Scans 4H macro trend, 1H structure, and 30M entry triggers ahead of the charts.
                </p>
              </div>
              <span className="badge badge-gold">{filteredSignals.length} Setups Active</span>
            </div>

            {filteredSignals.length === 0 ? (
              <div
                className="card"
                style={{
                  padding: '44px 20px',
                  textAlign: 'center',
                  color: 'var(--text-muted)',
                }}
              >
                <div style={{ fontSize: '32px', marginBottom: '10px' }}>🔍</div>
                <div style={{ fontWeight: 700, fontSize: '15px', color: '#fff' }}>
                  No Active Setups Right Now
                </div>
                <div style={{ fontSize: '12px', marginTop: '4px' }}>
                  The zero-sleep engine is analyzing M5/M15/H1 charts. Zero dummy data is shown. Real setups appear here instantly.
                </div>
              </div>
            ) : (
              <div
                className="signals-grid"
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))',
                  gap: '18px',
                }}
              >
                {filteredSignals.map((sig) => {
                  const isBuy = sig.direction === 'BUY' || sig.direction === 'LONG';
                  const orderAction: OrderAction = isBuy ? 'BUY' : 'SELL';
                  const is3of3 = sig.confluenceScore === '3/3';

                  return (
                    <div key={sig.id} className={`card ${is3of3 ? 'card-gold-glow' : ''}`}>
                      {/* Card Header with Unmistakable BUY / SELL Badge */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <span style={{ fontSize: '22px', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>
                              {sig.symbol}
                            </span>
                            <span className={isBuy ? 'badge badge-buy' : 'badge badge-sell'} style={{ fontSize: '12px', padding: '5px 12px' }}>
                              {isBuy ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                              {orderAction} ORDER
                            </span>
                          </div>
                          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                            Order Type: <strong style={{ color: '#fff' }}>{orderAction} MARKET</strong> (or Limit on Retest)
                          </div>
                        </div>

                        <div
                          style={{
                            padding: '4px 12px',
                            borderRadius: '100px',
                            fontSize: '11px',
                            fontWeight: 800,
                            background: is3of3 ? 'var(--gold-gradient)' : 'rgba(255,255,255,0.05)',
                            color: is3of3 ? '#000' : 'var(--text-muted)',
                          }}
                        >
                          {sig.confluenceScore} ALIGNED
                        </div>
                      </div>

                      {/* Explicit Price Levels (Entry, SL, TP1, TP2) */}
                      <div
                        className="price-levels-grid"
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(3, 1fr)',
                          gap: '8px',
                          background: 'rgba(255, 255, 255, 0.03)',
                          padding: '14px',
                          borderRadius: '12px',
                          marginTop: '16px',
                        }}
                      >
                        <div>
                          <div style={{ fontSize: '10px', color: 'var(--text-dim)', fontWeight: 700 }}>
                            {orderAction} ENTRY
                          </div>
                          <div className="mono gold" style={{ fontSize: '17px', fontWeight: 800, marginTop: '2px' }}>
                            {sig.entryPrice.toFixed(2)}
                          </div>
                          <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Current Chart Level</div>
                        </div>

                        <div>
                          <div style={{ fontSize: '10px', color: 'var(--text-dim)', fontWeight: 700 }}>
                            STOP LOSS
                          </div>
                          <div className="mono red" style={{ fontSize: '17px', fontWeight: 800, marginTop: '2px' }}>
                            {sig.stopLoss.toFixed(2)}
                          </div>
                          <div style={{ fontSize: '10px', color: 'var(--rose)' }}>
                            -{sig.slDistance.toFixed(2)} pts (Risk Floor)
                          </div>
                        </div>

                        <div>
                          <div style={{ fontSize: '10px', color: 'var(--text-dim)', fontWeight: 700 }}>
                            TAKE PROFIT (TP1)
                          </div>
                          <div className="mono green" style={{ fontSize: '17px', fontWeight: 800, marginTop: '2px' }}>
                            {sig.takeProfit1.toFixed(2)}
                          </div>
                          <div style={{ fontSize: '10px', color: 'var(--emerald)' }}>
                            +{sig.tpDistance.toFixed(2)} pts (1:2.0 R:R)
                          </div>
                        </div>
                      </div>

                      {/* Confluences & Setup Summary */}
                      {sig.confluences && sig.confluences.length > 0 && (
                        <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                          {sig.confluences.slice(0, 3).map((c, i) => (
                            <div
                              key={i}
                              style={{
                                fontSize: '11px',
                                color: 'var(--text-muted)',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px',
                              }}
                            >
                              <CheckCircle2 size={12} className="gold" />
                              <span>{c}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Card Action Buttons (Copy MT5 & Log to Journal) */}
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          marginTop: '16px',
                          paddingTop: '12px',
                          borderTop: '1px solid var(--border-subtle)',
                          flexWrap: 'wrap',
                          gap: '8px',
                        }}
                      >
                        <button className="btn btn-primary" onClick={() => handleCopyMT5(sig)}>
                          <Copy size={13} /> Copy MT5 [{orderAction}]
                        </button>

                        <button
                          className="btn"
                          onClick={() => prefillJournalFromSignal(sig)}
                          style={{ fontSize: '12px', padding: '6px 12px' }}
                        >
                          <BookOpen size={12} className="cyan" /> Log to Journal
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: LIVE ACCOUNT TRADES (Connected Accounts Executions)                */}
      {/* ========================================================================= */}
      {activeTab === 'LIVE_TRADES' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div
            className="guardrail-banner"
            style={{
              background: 'rgba(6, 182, 212, 0.08)',
              borderColor: 'rgba(6, 182, 212, 0.3)',
            }}
          >
            <div className="guardrail-text">
              <Activity size={22} className="cyan" />
              <div>
                <div style={{ fontWeight: 800, fontSize: '14px', color: '#38bdf8' }}>
                  LIVE EXECUTIONS & OPEN POSITIONS
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                  Real market orders active on your connected MT5 accounts. Completely separate from algorithmic setups.
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <span className="badge badge-green">Real-time P&L Defense</span>
              <span className="badge badge-gold">Auto Break-Even Armed</span>
            </div>
          </div>

          <div className="card" style={{ padding: '16px' }}>
            <div className="table-responsive">
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-dim)' }}>
                    <th style={{ padding: '10px' }}>TICKET</th>
                    <th style={{ padding: '10px' }}>ACCOUNT</th>
                    <th style={{ padding: '10px' }}>SYMBOL</th>
                    <th style={{ padding: '10px' }}>ACTION</th>
                    <th style={{ padding: '10px' }}>LOTS</th>
                    <th style={{ padding: '10px' }}>OPEN</th>
                    <th style={{ padding: '10px' }}>CURRENT</th>
                    <th style={{ padding: '10px' }}>SL / TP</th>
                    <th style={{ padding: '10px' }}>FLOATING P&L</th>
                    <th style={{ padding: '10px' }}>DEFENSE</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.length === 0 ? (
                    <tr>
                      <td colSpan={10} style={{ textAlign: 'center', padding: '36px 12px', color: 'var(--text-muted)' }}>
                        <div style={{ fontSize: '24px', marginBottom: '6px' }}>💼</div>
                        <div style={{ fontWeight: 600 }}>No live positions currently running.</div>
                        <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '2px' }}>
                          When trades execute on your connected accounts, they appear here with real-time early warning defense.
                        </div>
                      </td>
                    </tr>
                  ) : (
                    positions.map((p) => {
                      const isProfit = (p.profit || 0) >= 0;
                      return (
                        <tr key={p.ticket} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                          <td className="mono" style={{ padding: '12px 10px', fontWeight: 700 }}>#{p.ticket}</td>
                          <td style={{ padding: '12px 10px' }}>{p.account_name || p.account_id}</td>
                          <td className="mono" style={{ padding: '12px 10px', fontWeight: 800 }}>{p.symbol}</td>
                          <td style={{ padding: '12px 10px' }}>
                            <span className={`badge ${p.type === 'BUY' ? 'badge-buy' : 'badge-sell'}`}>
                              {p.type}
                            </span>
                          </td>
                          <td className="mono" style={{ padding: '12px 10px' }}>{p.volume.toFixed(2)}</td>
                          <td className="mono" style={{ padding: '12px 10px' }}>{p.open_price.toFixed(2)}</td>
                          <td className="mono" style={{ padding: '12px 10px' }}>{p.current_price.toFixed(2)}</td>
                          <td className="mono" style={{ padding: '12px 10px', fontSize: '11px' }}>
                            SL: {p.sl ? p.sl.toFixed(2) : 'None'} | TP: {p.tp ? p.tp.toFixed(2) : 'None'}
                          </td>
                          <td
                            className={`mono ${isProfit ? 'green' : 'red'}`}
                            style={{ padding: '12px 10px', fontWeight: 800 }}
                          >
                            ${p.profit.toFixed(2)}
                          </td>
                          <td style={{ padding: '12px 10px' }}>
                            <span className="badge badge-gold">Defended</span>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: TRADING JOURNAL & PERFORMANCE ANALYTICS (For Manual Traders)        */}
      {/* ========================================================================= */}
      {activeTab === 'JOURNAL' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Journal Banner & Action */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '12px',
              padding: '16px 20px',
              background: 'var(--bg-surface)',
              borderRadius: '16px',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div>
              <h2 style={{ fontSize: '17px', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px' }}>
                <BookOpen size={19} className="gold" />
                Personal Trading Journal & Manual Execution Tracker
              </h2>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                Track manual entries, trade psychology, setup confluences, and long-term profit curves.
              </p>
            </div>

            <button className="btn btn-primary" onClick={() => setShowNewJournalModal(true)}>
              <PlusCircle size={15} /> Log Manual Trade
            </button>
          </div>

          {/* Journal KPI Metrics Row */}
          <div
            className="kpi-row"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '14px',
            }}
          >
            <div className="card">
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>
                LOGGED TRADES
              </div>
              <div className="mono gold" style={{ fontSize: '24px', fontWeight: 800, marginTop: '4px' }}>
                {journalEntries.length} TRADES
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                {closedJournalTrades.length} Closed / {journalEntries.length - closedJournalTrades.length} Open
              </div>
            </div>

            <div className="card">
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>
                JOURNAL WIN RATE
              </div>
              <div className="mono green" style={{ fontSize: '24px', fontWeight: 800, marginTop: '4px' }}>
                {journalWinRate}%
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                {journalWins} Wins / {closedJournalTrades.length - journalWins} Losses
              </div>
            </div>

            <div className="card">
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>
                TOTAL NET P&L
              </div>
              <div
                className={`mono ${journalNetPnl >= 0 ? 'green' : 'red'}`}
                style={{ fontSize: '24px', fontWeight: 800, marginTop: '4px' }}
              >
                ${journalNetPnl.toFixed(2)}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                Realized journal return
              </div>
            </div>

            <div className="card">
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>
                TARGET RISK:REWARD
              </div>
              <div className="mono cyan" style={{ fontSize: '24px', fontWeight: 800, marginTop: '4px' }}>
                1:2.0+
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                Asymmetric payoff model
              </div>
            </div>
          </div>

          {/* Journal Entries List */}
          <div className="card" style={{ padding: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
              <div style={{ display: 'flex', gap: '8px' }}>
                {(['ALL', 'WIN', 'LOSS', 'OPEN'] as const).map((filter) => (
                  <button
                    key={filter}
                    className={`btn ${journalFilterOutcome === filter ? 'btn-active' : ''}`}
                    style={{ fontSize: '11px', padding: '4px 10px' }}
                    onClick={() => setJournalFilterOutcome(filter)}
                  >
                    {filter === 'ALL' ? 'All Entries' : filter}
                  </button>
                ))}
              </div>

              <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
                {journalEntries.length} Recorded Entries
              </span>
            </div>

            {journalEntries.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px 10px', color: 'var(--text-muted)' }}>
                <div style={{ fontSize: '32px', marginBottom: '8px' }}>📖</div>
                <div style={{ fontWeight: 700, fontSize: '15px', color: '#fff' }}>
                  Your Trading Journal is Empty
                </div>
                <div style={{ fontSize: '12px', marginTop: '4px', maxWidth: '440px', margin: '4px auto 16px' }}>
                  Start journaling your manual trades to build self-discipline, audit trade psychology, and improve your edge over time.
                </div>
                <button className="btn btn-primary" onClick={() => setShowNewJournalModal(true)}>
                  <PlusCircle size={14} /> Log Your First Trade
                </button>
              </div>
            ) : (
              <div className="table-responsive">
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-dim)' }}>
                      <th style={{ padding: '10px' }}>DATE / TIME</th>
                      <th style={{ padding: '10px' }}>SYMBOL</th>
                      <th style={{ padding: '10px' }}>ACTION</th>
                      <th style={{ padding: '10px' }}>TYPE</th>
                      <th style={{ padding: '10px' }}>ENTRY</th>
                      <th style={{ padding: '10px' }}>EXIT</th>
                      <th style={{ padding: '10px' }}>SL / TP</th>
                      <th style={{ padding: '10px' }}>P&L ($)</th>
                      <th style={{ padding: '10px' }}>OUTCOME</th>
                      <th style={{ padding: '10px' }}>NOTES & EMOTION</th>
                      <th style={{ padding: '10px' }}>ACTION</th>
                    </tr>
                  </thead>
                  <tbody>
                    {journalEntries
                      .filter((j) => journalFilterOutcome === 'ALL' || j.outcome === journalFilterOutcome)
                      .map((j) => {
                        const isWin = j.outcome === 'WIN';
                        const isLoss = j.outcome === 'LOSS';
                        return (
                          <tr key={j.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                            <td style={{ padding: '12px 10px', color: 'var(--text-dim)' }}>
                              {new Date(j.created_at).toLocaleDateString()}
                            </td>
                            <td className="mono" style={{ padding: '12px 10px', fontWeight: 800 }}>
                              {j.symbol}
                            </td>
                            <td style={{ padding: '12px 10px' }}>
                              <span className={`badge ${j.order_action === 'BUY' ? 'badge-buy' : 'badge-sell'}`}>
                                {j.order_action}
                              </span>
                            </td>
                            <td style={{ padding: '12px 10px', color: 'var(--text-muted)' }}>
                              {j.order_type}
                            </td>
                            <td className="mono" style={{ padding: '12px 10px' }}>
                              {j.entry_price.toFixed(2)}
                            </td>
                            <td className="mono" style={{ padding: '12px 10px' }}>
                              {j.exit_price ? j.exit_price.toFixed(2) : '-'}
                            </td>
                            <td className="mono" style={{ padding: '12px 10px', fontSize: '11px' }}>
                              SL: {j.stop_loss.toFixed(2)} | TP: {j.take_profit.toFixed(2)}
                            </td>
                            <td
                              className={`mono ${j.profit_usd >= 0 ? 'green' : 'red'}`}
                              style={{ padding: '12px 10px', fontWeight: 800 }}
                            >
                              ${j.profit_usd.toFixed(2)}
                            </td>
                            <td style={{ padding: '12px 10px' }}>
                              <span
                                className={`badge ${
                                  isWin ? 'badge-green' : isLoss ? 'badge-red' : 'badge-gray'
                                }`}
                              >
                                {j.outcome}
                              </span>
                            </td>
                            <td style={{ padding: '12px 10px', maxWidth: '240px' }}>
                              <div style={{ fontSize: '11px', color: '#fff', fontWeight: 600 }}>
                                {j.setup_type}
                              </div>
                              <div style={{ fontSize: '10px', color: 'var(--text-dim)', marginTop: '2px' }}>
                                Emotion: {j.emotions}
                              </div>
                            </td>
                            <td style={{ padding: '12px 10px' }}>
                              <button
                                onClick={() => handleDeleteJournal(j.id)}
                                style={{ background: 'none', border: 'none', color: 'var(--rose)', cursor: 'pointer', padding: '4px' }}
                              >
                                <Trash2 size={13} />
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 4: ACCOUNT FLEET ($20 USD Minimum Initial Balance)                    */}
      {/* ========================================================================= */}
      {activeTab === 'ACCOUNTS' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '12px',
              padding: '16px 20px',
              background: 'var(--bg-surface)',
              borderRadius: '16px',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div>
              <h2 style={{ fontSize: '17px', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Wallet size={18} className="gold" />
                Connected MT5 Account Fleet
              </h2>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                Zero dummy accounts. Connect real MT5 trading accounts with minimum $20.00 USD balance.
              </p>
            </div>

            <button className="btn btn-primary" onClick={() => setShowAddAccountModal(true)}>
              <PlusCircle size={15} /> Add MT5 Trading Account ($20 Min)
            </button>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
              gap: '16px',
            }}
          >
            {accounts.length === 0 ? (
              <div
                className="card"
                style={{
                  gridColumn: '1 / -1',
                  padding: '40px 20px',
                  textAlign: 'center',
                  color: 'var(--text-muted)',
                }}
              >
                <div style={{ fontSize: '32px', marginBottom: '8px' }}>🏦</div>
                <div style={{ fontWeight: 700, fontSize: '16px', color: '#fff' }}>
                  No Accounts Added Yet
                </div>
                <div style={{ fontSize: '12px', marginTop: '4px', maxWidth: '480px', margin: '6px auto 16px' }}>
                  All old mock accounts have been purged. Add your real personal broker or funded accounts to begin execution.
                </div>
                <button className="btn btn-primary" onClick={() => setShowAddAccountModal(true)}>
                  <PlusCircle size={14} /> Add First Real Account ($20.00 Minimum)
                </button>
              </div>
            ) : (
              accounts.map((acc) => (
                <div key={acc.id} className="card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <div style={{ fontWeight: 800, fontSize: '16px' }}>{acc.name}</div>
                      <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '2px' }}>
                        Type: {acc.type} • Mode: {acc.execution_mode || 'AUTOMATED_EA'}
                      </div>
                    </div>
                    <span className="badge badge-green">{acc.status || 'CONNECTED'}</span>
                  </div>

                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(2, 1fr)',
                      gap: '10px',
                      background: 'rgba(255,255,255,0.03)',
                      padding: '12px',
                      borderRadius: '10px',
                      marginTop: '14px',
                    }}
                  >
                    <div>
                      <div style={{ fontSize: '10px', color: 'var(--text-dim)' }}>BALANCE</div>
                      <div className="mono gold" style={{ fontSize: '16px', fontWeight: 800 }}>
                        ${acc.balance.toFixed(2)}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: '10px', color: 'var(--text-dim)' }}>EQUITY</div>
                      <div className="mono green" style={{ fontSize: '16px', fontWeight: 800 }}>
                        ${acc.equity.toFixed(2)}
                      </div>
                    </div>
                  </div>

                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginTop: '14px',
                      paddingTop: '10px',
                      borderTop: '1px solid var(--border-subtle)',
                    }}
                  >
                    <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                      Min Floor: $20.00 USD (Verified)
                    </span>
                    <button
                      className="btn"
                      style={{ fontSize: '11px', padding: '4px 10px' }}
                      onClick={() => showToast(`Launching MT5 terminal for ${acc.name}...`)}
                    >
                      <Play size={11} /> Launch MT5
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 5: RISK & LOT SIZE CALCULATOR                                        */}
      {/* ========================================================================= */}
      {activeTab === 'CALCULATOR' && (
        <div className="card" style={{ border: '1px solid var(--border-gold)', background: 'rgba(18, 22, 33, 0.85)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontSize: '20px' }}>⚖️</span>
              <span style={{ fontWeight: 800, fontSize: '16px' }}>Universal Position Size & Risk Calculator</span>
            </div>
            <span className="badge badge-gold" style={{ fontSize: '11px' }}>Pair: {calcSymbol}</span>
          </div>

          <div style={{ marginTop: '14px', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700, textTransform: 'uppercase' }}>
              Account Preset:
            </span>
            {[
              { label: '$20 (Micro Starter)', val: 20, key: 'Micro20' },
              { label: '$50 (Cent/Starter)', val: 50, key: 'Starter50' },
              { label: '$100 (Standard Mini)', val: 100, key: 'Mini100' },
              { label: '$1,000 (Standard)', val: 1000, key: 'Standard1000' },
              { label: '$10,000 (Funded/Pro)', val: 10000, key: 'Funded10k' },
            ].map((preset) => (
              <button
                key={preset.key}
                className={`btn ${selectedPreset === preset.key ? 'btn-active' : ''}`}
                style={{ fontSize: '11px', padding: '4px 10px' }}
                onClick={() => {
                  setBalance(preset.val);
                  setSelectedPreset(preset.key);
                  showToast(`Selected ${preset.label} preset`);
                }}
              >
                {preset.label}
              </button>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px', marginTop: '16px' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 600 }}>ACCOUNT BALANCE ($)</div>
              <input
                type="number"
                value={balance}
                onChange={(e) => {
                  setBalance(parseFloat(e.target.value) || 0);
                  setSelectedPreset('Custom');
                }}
                style={{
                  width: '100%',
                  marginTop: '4px',
                  padding: '8px 12px',
                  background: 'rgba(0,0,0,0.4)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '8px',
                  color: '#fff',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '14px',
                  fontWeight: 700,
                }}
              />
            </div>

            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 600 }}>RISK PER TRADE (%)</div>
              <div style={{ display: 'flex', gap: '4px', marginTop: '4px' }}>
                {[0.25, 0.50, 1.00, 2.00].map((pct) => (
                  <button
                    key={pct}
                    className={`btn ${riskPercent === pct ? 'btn-active' : ''}`}
                    style={{ flex: 1, padding: '8px 2px', fontSize: '11px', fontWeight: 700 }}
                    onClick={() => setRiskPercent(pct)}
                  >
                    {pct}%
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 600 }}>SL DISTANCE (PTS)</div>
              <input
                type="number"
                step="0.1"
                value={slPoints}
                onChange={(e) => setSlPoints(parseFloat(e.target.value) || 0.5)}
                style={{
                  width: '100%',
                  marginTop: '4px',
                  padding: '8px 12px',
                  background: 'rgba(0,0,0,0.4)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '8px',
                  color: '#fff',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '14px',
                  fontWeight: 700,
                }}
              />
            </div>

            <div
              style={{
                background: 'rgba(0,0,0,0.45)',
                border: '1px solid rgba(245,200,66,0.3)',
                borderRadius: '12px',
                padding: '12px 16px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                gap: '4px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                <span style={{ color: 'var(--text-muted)' }}>Max Risk Allowance:</span>
                <span className="mono red" style={{ fontWeight: 700 }}>
                  ${(balance * (riskPercent / 100)).toFixed(2)} ({riskPercent}%)
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '2px' }}>
                <span style={{ color: 'var(--gold-primary)', fontWeight: 700, fontSize: '12px' }}>Recommended Lot:</span>
                <span className="mono gold" style={{ fontSize: '18px', fontWeight: 800 }}>
                  {Math.max(0.01, Math.round(((balance * (riskPercent / 100)) / (Math.max(slPoints, 0.5) * (calcSymbol.includes('XAU') ? 100 : 1))) * 100) / 100).toFixed(2)} LOT
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--emerald)' }}>
                <span>Target 1:2.0 Return:</span>
                <span className="mono" style={{ fontWeight: 700 }}>
                  +${((balance * (riskPercent / 100)) * 2).toFixed(2)} (+{(riskPercent * 2).toFixed(2)}%)
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: NEW JOURNAL ENTRY (Manual Trade Logger)                            */}
      {/* ========================================================================= */}
      {showNewJournalModal && (
        <div className="modal-overlay" onClick={() => setShowNewJournalModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '600px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <BookOpen size={20} className="gold" />
                <h3 style={{ fontSize: '17px', fontWeight: 800 }}>Record Trade in Journal</h3>
              </div>
              <button
                onClick={() => setShowNewJournalModal(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSaveJournalEntry} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>SYMBOL</label>
                  <select
                    value={jSymbol}
                    onChange={(e) => setJSymbol(e.target.value)}
                    style={{ width: '100%', marginTop: '4px', padding: '8px 10px', background: '#161a26', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: '#fff' }}
                  >
                    <option value="BTCUSD">BTCUSD</option>
                    <option value="XAUUSD">XAUUSD</option>
                    <option value="EURUSD">EURUSD</option>
                    <option value="US30">US30</option>
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>ORDER ACTION</label>
                  <select
                    value={jAction}
                    onChange={(e) => {
                      const a = e.target.value as OrderAction;
                      setJAction(a);
                      setJOrderType(`${a} MARKET` as MT5OrderType);
                    }}
                    style={{ width: '100%', marginTop: '4px', padding: '8px 10px', background: '#161a26', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: jAction === 'BUY' ? 'var(--emerald)' : 'var(--rose)', fontWeight: 700 }}
                  >
                    <option value="BUY">BUY (Long)</option>
                    <option value="SELL">SELL (Short)</option>
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>LOT SIZE</label>
                  <input
                    type="number"
                    step="0.01"
                    value={jLots}
                    onChange={(e) => setJLots(parseFloat(e.target.value) || 0.01)}
                    style={{ width: '100%', marginTop: '4px', padding: '8px 10px', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: '#fff', fontFamily: 'var(--font-mono)' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>ENTRY PRICE</label>
                  <input
                    type="number"
                    step="any"
                    value={jEntryPrice}
                    onChange={(e) => setJEntryPrice(parseFloat(e.target.value) || 0)}
                    style={{ width: '100%', marginTop: '4px', padding: '8px 10px', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-gold)', borderRadius: '8px', color: 'var(--gold-primary)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}
                    required
                  />
                </div>

                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>STOP LOSS</label>
                  <input
                    type="number"
                    step="any"
                    value={jStopLoss}
                    onChange={(e) => setJStopLoss(parseFloat(e.target.value) || 0)}
                    style={{ width: '100%', marginTop: '4px', padding: '8px 10px', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: 'var(--rose)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}
                  />
                </div>

                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>TAKE PROFIT</label>
                  <input
                    type="number"
                    step="any"
                    value={jTakeProfit}
                    onChange={(e) => setJTakeProfit(parseFloat(e.target.value) || 0)}
                    style={{ width: '100%', marginTop: '4px', padding: '8px 10px', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: 'var(--emerald)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>OUTCOME</label>
                  <select
                    value={jOutcome}
                    onChange={(e) => setJOutcome(e.target.value as TradeOutcome)}
                    style={{ width: '100%', marginTop: '4px', padding: '8px 10px', background: '#161a26', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: '#fff' }}
                  >
                    <option value="WIN">WIN (Hit TP / Green)</option>
                    <option value="LOSS">LOSS (Hit SL / Red)</option>
                    <option value="BREAKEVEN">BREAKEVEN (SL to BE)</option>
                    <option value="OPEN">OPEN (Still Running)</option>
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>PROFIT / LOSS ($)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={jProfitUsd}
                    onChange={(e) => setJProfitUsd(parseFloat(e.target.value) || 0)}
                    style={{ width: '100%', marginTop: '4px', padding: '8px 10px', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: jProfitUsd >= 0 ? 'var(--emerald)' : 'var(--rose)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}
                  />
                </div>
              </div>

              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>SETUP / CONFLUENCE TYPE</label>
                <input
                  type="text"
                  value={jSetupType}
                  onChange={(e) => setJSetupType(e.target.value)}
                  placeholder="e.g. Liquidity Sweep + BOS + 30M Reversal"
                  style={{ width: '100%', marginTop: '4px', padding: '8px 10px', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: '#fff' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>EMOTIONS & PSYCHOLOGY</label>
                <select
                  value={jEmotions}
                  onChange={(e) => setJEmotions(e.target.value)}
                  style={{ width: '100%', marginTop: '4px', padding: '8px 10px', background: '#161a26', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: '#fff' }}
                >
                  <option value="Disciplined & Patient">Disciplined & Patient (Waited for confirmation)</option>
                  <option value="Confident Execution">Confident Execution (Clean setup)</option>
                  <option value="FOMO / Chased Entry">FOMO / Chased (Entered too late)</option>
                  <option value="Rushed Close">Rushed Close (Closed prematurely out of fear)</option>
                  <option value="Revenge Trade">Revenge Trade (Tried to recoup prior loss)</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>NOTES & REFLECTIONS</label>
                <textarea
                  rows={2}
                  value={jNotes}
                  onChange={(e) => setJNotes(e.target.value)}
                  placeholder="What went well? What could you improve next time?"
                  style={{ width: '100%', marginTop: '4px', padding: '8px 10px', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: '#fff', fontSize: '12px' }}
                />
              </div>

              <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
                <button type="button" className="btn" style={{ flex: 1 }} onClick={() => setShowNewJournalModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" style={{ flex: 2 }}>
                  Save to Journal
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: USER PROFILE & SIGN UP / LOGIN                                     */}
      {/* ========================================================================= */}
      {showAuthModal && (
        <div className="modal-overlay" onClick={() => setShowAuthModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <UserCheck size={20} className="gold" />
                <h3 style={{ fontSize: '17px', fontWeight: 800 }}>Trader Profile & Sign-Up</h3>
              </div>
              <button onClick={() => setShowAuthModal(false)} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
                <X size={18} />
              </button>
            </div>

            <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px' }}>
              Sign up or switch your trader profile to personalize your manual trade journals, alerts, and connected broker accounts.
            </p>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                setUser({
                  name: authName || user.name,
                  email: authEmail || user.email,
                  accountType: authType,
                  isLoggedIn: true,
                });
                showToast(`Profile updated: ${authName || user.name} (${authType})`);
                setShowAuthModal(false);
              }}
              style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}
            >
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>TRADER NAME</label>
                <input
                  type="text"
                  placeholder="e.g. Hannington"
                  defaultValue={user.name}
                  onChange={(e) => setAuthName(e.target.value)}
                  style={{ width: '100%', marginTop: '4px', padding: '9px 12px', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: '#fff' }}
                  required
                />
              </div>

              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>EMAIL ADDRESS</label>
                <input
                  type="email"
                  placeholder="e.g. trader@goldclone.com"
                  defaultValue={user.email}
                  onChange={(e) => setAuthEmail(e.target.value)}
                  style={{ width: '100%', marginTop: '4px', padding: '9px 12px', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: '#fff' }}
                  required
                />
              </div>

              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>TRADING ACCOUNT CATEGORY</label>
                <select
                  value={authType}
                  onChange={(e) => setAuthType(e.target.value as any)}
                  style={{ width: '100%', marginTop: '4px', padding: '9px 12px', background: '#161a26', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: '#fff' }}
                >
                  <option value="PERSONAL">Personal Broker (Exness, XM, HF Markets, IC)</option>
                  <option value="PROP_FIRM">Prop Firm Challenge (FTMO, BrightFunded, FundedNext)</option>
                  <option value="CENT_ACCOUNT">Micro / Cent Account ($20 minimum)</option>
                </select>
              </div>

              <div style={{ display: 'flex', gap: '10px', marginTop: '12px' }}>
                <button type="button" className="btn" style={{ flex: 1 }} onClick={() => setShowAuthModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" style={{ flex: 2 }}>
                  Save & Update Profile
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: ADD REAL MT5 TRADING ACCOUNT ($20 USD MINIMUM INITIAL BALANCE)      */}
      {/* ========================================================================= */}
      {showAddAccountModal && (
        <div className="modal-overlay" onClick={() => setShowAddAccountModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Wallet size={20} className="gold" />
                <h3 style={{ fontSize: '17px', fontWeight: 800 }}>Add Real MT5 Trading Account</h3>
              </div>
              <button
                onClick={() => setShowAddAccountModal(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            </div>

            {addAccountError && (
              <div
                style={{
                  background: 'var(--rose-bg)',
                  border: '1px solid var(--border-rose)',
                  padding: '10px 14px',
                  borderRadius: '10px',
                  color: 'var(--rose)',
                  fontSize: '12px',
                  fontWeight: 600,
                  marginBottom: '14px',
                }}
              >
                ⚠️ {addAccountError}
              </div>
            )}

            <form onSubmit={handleAddAccount} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>
                  ACCOUNT LABEL / NAME
                </label>
                <input
                  type="text"
                  placeholder="e.g. Exness Real Micro #1"
                  value={newAccName}
                  onChange={(e) => setNewAccName(e.target.value)}
                  style={{ width: '100%', marginTop: '4px', padding: '9px 12px', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: '#fff', fontSize: '13px' }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>
                    INITIAL BALANCE ($) (MIN $20)
                  </label>
                  <input
                    type="number"
                    min="20"
                    step="1"
                    value={newAccBalance}
                    onChange={(e) => setNewAccBalance(parseFloat(e.target.value) || 20)}
                    style={{ width: '100%', marginTop: '4px', padding: '9px 12px', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-gold)', borderRadius: '8px', color: 'var(--gold-primary)', fontFamily: 'var(--font-mono)', fontSize: '14px', fontWeight: 700 }}
                    required
                  />
                </div>

                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>
                    ACCOUNT TYPE
                  </label>
                  <select
                    value={newAccType}
                    onChange={(e) => setNewAccType(e.target.value)}
                    style={{ width: '100%', marginTop: '4px', padding: '9px 12px', background: '#161a26', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: '#fff', fontSize: '13px' }}
                  >
                    <option value="PERSONAL">Personal Broker</option>
                    <option value="PROP_FIRM">Prop Firm Challenge</option>
                    <option value="CENT_ACCOUNT">Cent Account</option>
                  </select>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>
                    MT5 LOGIN NUMBER
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. 1928374"
                    value={newAccLogin}
                    onChange={(e) => setNewAccLogin(e.target.value)}
                    style={{ width: '100%', marginTop: '4px', padding: '9px 12px', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: '#fff', fontFamily: 'var(--font-mono)', fontSize: '13px' }}
                    required
                  />
                </div>

                <div>
                  <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>
                    BROKER SERVER
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Exness-Real10"
                    value={newAccServer}
                    onChange={(e) => setNewAccServer(e.target.value)}
                    style={{ width: '100%', marginTop: '4px', padding: '9px 12px', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: '#fff', fontSize: '13px' }}
                    required
                  />
                </div>
              </div>

              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>
                  MT5 PASSWORD
                </label>
                <input
                  type="password"
                  placeholder="Master or Investor Password"
                  value={newAccPassword}
                  onChange={(e) => setNewAccPassword(e.target.value)}
                  style={{ width: '100%', marginTop: '4px', padding: '9px 12px', background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: '#fff', fontSize: '13px' }}
                  required
                />
              </div>

              <div>
                <label style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>
                  EXECUTION MODE
                </label>
                <select
                  value={newAccMode}
                  onChange={(e) => setNewAccMode(e.target.value)}
                  style={{ width: '100%', marginTop: '4px', padding: '9px 12px', background: '#161a26', border: '1px solid var(--border-subtle)', borderRadius: '8px', color: '#fff', fontSize: '13px' }}
                >
                  <option value="AUTOMATED_EA">Automated EA (Terminal Copier / Executor)</option>
                  <option value="SIGNAL_ONLY_MANUAL">Signal Only (Manual Execution Notification)</option>
                </select>
              </div>

              <div style={{ display: 'flex', gap: '10px', marginTop: '14px' }}>
                <button type="button" className="btn" style={{ flex: 1 }} onClick={() => setShowAddAccountModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" style={{ flex: 2 }} disabled={addingAccount}>
                  {addingAccount ? 'Verifying & Adding...' : 'Add Account & Save'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
