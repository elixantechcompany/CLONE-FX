'use client';

import React, { useState, useEffect } from 'react';
import {
  ConfluenceSignal,
  MarketSchedule,
  EarlyWarning,
  LivePosition,
  FleetAccount,
  DashboardApiResponse
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
  Flame
} from 'lucide-react';

export default function DashboardPage() {
  // Navigation tabs
  const [activeTab, setActiveTab] = useState<'SIGNALS' | 'LIVE_TRADES' | 'ACCOUNTS' | 'CALCULATOR'>('SIGNALS');

  // Scanner & Live Data
  const [signals, setSignals] = useState<ConfluenceSignal[]>([]);
  const [marketSchedules, setMarketSchedules] = useState<Record<string, MarketSchedule>>({});
  const [earlyWarnings, setEarlyWarnings] = useState<EarlyWarning[]>([]);
  const [positions, setPositions] = useState<LivePosition[]>([]);
  const [accounts, setAccounts] = useState<FleetAccount[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [scanning, setScanning] = useState<boolean>(false);
  const [lastSync, setLastSync] = useState<string>('Just now');

  // Filters
  const [symbolFilter, setSymbolFilter] = useState<'ALL' | 'XAUUSD' | 'BTCUSD'>('ALL');
  const [confluenceFilter, setConfluenceFilter] = useState<'ALL' | '3/3'>('3/3');
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Calculator State
  const [balance, setBalance] = useState<number>(1000);
  const [riskPercent, setRiskPercent] = useState<number>(0.25);
  const [slPoints, setSlPoints] = useState<number>(3.5);
  const [selectedPreset, setSelectedPreset] = useState<string>('BrightFunded');
  const [calcSymbol, setCalcSymbol] = useState<string>('XAUUSD');
  const [soundEnabled, setSoundEnabled] = useState<boolean>(true);

  // Add Account Modal
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

  // Play audio chime
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
    setTimeout(() => setToastMessage(null), 3500);
  };

  // Fetch all dashboard data
  const fetchData = async () => {
    try {
      const [dashRes, sigRes] = await Promise.all([
        fetch('/api/dashboard'),
        fetch('/api/signals').catch(() => null)
      ]);

      if (dashRes.ok) {
        const dashData: DashboardApiResponse = await dashRes.json();
        if (dashData.market_schedules) {
          setMarketSchedules(dashData.market_schedules);
        }
        if (dashData.early_warnings) {
          setEarlyWarnings(dashData.early_warnings);
        }
        if (dashData.positions) {
          setPositions(dashData.positions);
        }
        if (dashData.accounts) {
          setAccounts(dashData.accounts);
        }

        // Combine live scanner setups with historical signals
        const scannerSetups: ConfluenceSignal[] = [
          ...(dashData.perfect_setups || []),
          ...(dashData.forming_setups || [])
        ].map((s: any) => ({
          id: s.id || `setup_${Date.now()}`,
          symbol: s.symbol ? s.symbol.replace('m', '') : 'BTCUSD',
          direction: s.direction || 'BUY',
          entryPrice: s.entry_price || 0,
          stopLoss: s.stop_loss || 0,
          takeProfit1: s.tp1 || 0,
          takeProfit2: s.tp2 || 0,
          riskReward: s.risk_reward || 2.0,
          slDistance: s.sl_distance || 0,
          tpDistance: s.tp_distance || 0,
          confluenceScore: s.conviction_score >= 80 ? '3/3' : '2/3',
          scoreNumeric: s.conviction_score || 80,
          timeframeStack: {
            '4H': 'Trend Aligned',
            '1H': 'Structure Aligned',
            '30M': 'Trigger Confirmed'
          },
          confluences: s.confluences || [],
          status: 'ACTIVE',
          setup_summary: s.setup_summary,
          formed_time: s.formed_time
        }));

        let combined = [...scannerSetups];
        if (sigRes && sigRes.ok) {
          const sigData = await sigRes.json();
          if (sigData.signals && sigData.signals.length > 0) {
            combined = [...combined, ...sigData.signals];
          }
        }

        // Remove duplicates by ID or Symbol+Direction+Entry
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
    } catch (e) {
      console.error('Failed to load dashboard data:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // Auto-poll every 5 seconds to keep live data fresh and never sleep off
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  // Trigger Scanner
  const triggerScan = async () => {
    try {
      setScanning(true);
      const res = await fetch('/api/scan', { method: 'POST' });
      await res.json();
      showToast('Scan completed across active open pairs!');
      await fetchData();
      playChime();
    } catch (e) {
      showToast('Scan request failed');
    } finally {
      setScanning(false);
    }
  };

  // Add Real MT5 Account ($20 Min)
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
      // Reset form
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

  // Copy parameters to clipboard
  const handleCopy = (s: ConfluenceSignal) => {
    const text = `${s.symbol} ${s.direction} | Entry: ${s.entryPrice.toFixed(2)} | SL: ${s.stopLoss.toFixed(2)} | TP1: ${s.takeProfit1.toFixed(2)} [R:R 1:${s.riskReward.toFixed(2)}]`;
    navigator.clipboard.writeText(text);
    showToast(`Copied ${s.symbol} ${s.direction} parameters!`);
  };

  // Filter signals
  const filteredSignals = signals.filter((s) => {
    if (symbolFilter !== 'ALL' && s.symbol !== symbolFilter) return false;
    if (confluenceFilter === '3/3' && s.confluenceScore !== '3/3') return false;
    return true;
  });

  const activeSignals = filteredSignals.filter((s) => s.status === 'ACTIVE');

  // Stats calculation
  const totalOpenTrades = positions.length;
  const totalFloatingPnl = positions.reduce((acc, pos) => acc + (pos.profit || 0), 0);

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
            zIndex: 9999,
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

      {/* Top Header */}
      <header
        className="header-content"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '18px 24px',
          background: 'var(--bg-surface)',
          backdropFilter: 'blur(20px)',
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
            <h1 style={{ fontSize: '20px', fontWeight: 800, letterSpacing: '-0.5px' }}>
              Gold & BTC Institutional Terminal
            </h1>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Dual-Engine: High-Fidelity Scanner + Multi-Terminal Account Fleet Execution
            </p>
          </div>
        </div>

        <div className="header-actions" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            className="btn"
            onClick={triggerScan}
            disabled={scanning}
            style={{ opacity: scanning ? 0.7 : 1 }}
          >
            <RefreshCw size={14} className={scanning ? 'spin' : ''} />
            {scanning ? 'Scanning Open Pairs...' : 'Scan Now'}
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
            WATCHDOG ACTIVE
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

      {/* Market Schedule Awareness Ribbon (Prevents sleeping off / scanning closed markets) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '12px',
        }}
      >
        {/* XAUUSD Market Hours Card */}
        <div
          style={{
            background: 'rgba(15, 18, 26, 0.8)',
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
                <span
                  className={`badge ${
                    marketSchedules.XAUUSD?.is_open ? 'badge-green' : 'badge-red'
                  }`}
                >
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

        {/* BTCUSD Market Hours Card */}
        <div
          style={{
            background: 'rgba(15, 18, 26, 0.8)',
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

      {/* Early Warning System Alert Banner (Detects Trend Change & Profit Retracements Ahead of User) */}
      {earlyWarnings && earlyWarnings.length > 0 ? (
        <div className="early-warning-container">
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <AlertTriangle size={24} className="amber" />
              <div>
                <div style={{ fontWeight: 800, fontSize: '14px', color: 'var(--amber)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  EARLY WARNING SYSTEM ACTIVE • PROFIT DEFENSE PROTOCOL TRIGGERED
                  <span className="badge badge-red">{earlyWarnings.length} ALERTS</span>
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-main)', marginTop: '4px' }}>
                  Lower timeframe shift detected ahead of the charts. Protect profits before retracement gives them back.
                </div>
              </div>
            </div>
            <span className="badge badge-gold">Auto-Defend Armed</span>
          </div>

          <div style={{ marginTop: '14px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
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
      ) : null}

      {/* Navigation Tabs Header */}
      <div className="tabs-nav">
        <button
          className={`tab-btn ${activeTab === 'SIGNALS' ? 'active' : ''}`}
          onClick={() => setActiveTab('SIGNALS')}
        >
          <Target size={15} />
          🎯 Market Signals & Setups ({activeSignals.length})
        </button>

        <button
          className={`tab-btn ${activeTab === 'LIVE_TRADES' ? 'active' : ''}`}
          onClick={() => setActiveTab('LIVE_TRADES')}
        >
          <Activity size={15} />
          💼 Live Account Trades ({totalOpenTrades})
        </button>

        <button
          className={`tab-btn ${activeTab === 'ACCOUNTS' ? 'active' : ''}`}
          onClick={() => setActiveTab('ACCOUNTS')}
        >
          <Wallet size={15} />
          🏦 Account Fleet (${accounts.length} connected)
        </button>

        <button
          className={`tab-btn ${activeTab === 'CALCULATOR' ? 'active' : ''}`}
          onClick={() => setActiveTab('CALCULATOR')}
        >
          <SlidersHorizontal size={15} />
          ⚖️ Risk & Lot Size Calculator
        </button>
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: MARKET SIGNALS & SETUPS (Ahead of Charts with Exact Price Levels)  */}
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
                FILTER PAIR:
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
                CONFLUENCE:
              </span>
              <button
                className={`btn ${confluenceFilter === '3/3' ? 'btn-active' : ''}`}
                onClick={() => setConfluenceFilter('3/3')}
              >
                ⭐ 3/3 Prop Ready Only
              </button>
              <button
                className={`btn ${confluenceFilter === 'ALL' ? 'btn-active' : ''}`}
                onClick={() => setConfluenceFilter('ALL')}
              >
                All Scores
              </button>
            </div>
          </div>

          {/* Active Setups Grid */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <div>
                <h2 style={{ fontSize: '17px', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Zap size={18} className="gold" />
                  Institutional Setups (Verified Across 4H / 1H / 30M)
                </h2>
                <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                  Scanner detects BOS, liquidity sweeps, and fair value gaps ahead of retail charts.
                </p>
              </div>
              <span className="badge badge-gold">{activeSignals.length} Active Setups</span>
            </div>

            {activeSignals.length === 0 ? (
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
                  No 3/3 Setups Currently Triggered
                </div>
                <div style={{ fontSize: '12px', marginTop: '4px' }}>
                  The zero-sleep engine is actively scanning. Setups appear immediately upon multi-timeframe alignment.
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
                {activeSignals.map((sig) => {
                  const isLong = sig.direction === 'LONG' || sig.direction === 'BUY';
                  const is3of3 = sig.confluenceScore === '3/3';

                  return (
                    <div key={sig.id} className={`card ${is3of3 ? 'card-gold-glow' : ''}`}>
                      {/* Card Header */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontSize: '20px', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>
                              {sig.symbol}
                            </span>
                            <span className={`badge ${isLong ? 'badge-green' : 'badge-red'}`}>
                              {isLong ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                              {sig.direction}
                            </span>
                          </div>
                          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                            Stack: 4H Trend + 1H Structure + 30M Trigger
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
                          {sig.confluenceScore} CONFLUENCE
                        </div>
                      </div>

                      {/* Exact Chart Price Levels */}
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
                            ENTRY POINT
                          </div>
                          <div className="mono gold" style={{ fontSize: '16px', fontWeight: 800, marginTop: '2px' }}>
                            {sig.entryPrice.toFixed(2)}
                          </div>
                          <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Market Chart Ref</div>
                        </div>

                        <div>
                          <div style={{ fontSize: '10px', color: 'var(--text-dim)', fontWeight: 700 }}>
                            STOP LOSS
                          </div>
                          <div className="mono red" style={{ fontSize: '16px', fontWeight: 800, marginTop: '2px' }}>
                            {sig.stopLoss.toFixed(2)}
                          </div>
                          <div style={{ fontSize: '10px', color: 'var(--rose)' }}>
                            -{sig.slDistance.toFixed(2)} pts (1.5x ATR)
                          </div>
                        </div>

                        <div>
                          <div style={{ fontSize: '10px', color: 'var(--text-dim)', fontWeight: 700 }}>
                            TAKE PROFIT
                          </div>
                          <div className="mono green" style={{ fontSize: '16px', fontWeight: 800, marginTop: '2px' }}>
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

                      {/* Card Actions Footer */}
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          marginTop: '16px',
                          paddingTop: '12px',
                          borderTop: '1px solid var(--border-subtle)',
                        }}
                      >
                        <button className="btn btn-primary" onClick={() => handleCopy(sig)}>
                          <Copy size={13} /> Copy MT5 Parameters
                        </button>

                        <div style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                          {sig.formed_time ? `Formed ${sig.formed_time}` : 'Live Institutional Alert'}
                        </div>
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
      {/* TAB 2: LIVE ACCOUNT TRADES (Separated from Algorithmic Signals)           */}
      {/* ========================================================================= */}
      {activeTab === 'LIVE_TRADES' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Live Trades Header Banner */}
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
                  LIVE EXECUTED TRADES & OPEN POSITIONS
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                  This table shows active market orders executing on your connected MT5 accounts. Completely isolated from scanner signals.
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <span className="badge badge-green">Real-time P&L Defense</span>
              <span className="badge badge-gold">Auto Break-Even Armed</span>
            </div>
          </div>

          {/* Quick Metrics */}
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
                OPEN POSITIONS
              </div>
              <div className="mono gold" style={{ fontSize: '24px', fontWeight: 800, marginTop: '4px' }}>
                {totalOpenTrades} ACTIVE
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                Across all fleet accounts
              </div>
            </div>

            <div className="card">
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>
                TOTAL FLOATING P&L
              </div>
              <div
                className={`mono ${totalFloatingPnl >= 0 ? 'green' : 'red'}`}
                style={{ fontSize: '24px', fontWeight: 800, marginTop: '4px' }}
              >
                ${totalFloatingPnl.toFixed(2)}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                Unrealized profit/loss
              </div>
            </div>

            <div className="card">
              <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700 }}>
                PROFIT DEFENSE STATUS
              </div>
              <div className="mono cyan" style={{ fontSize: '20px', fontWeight: 800, marginTop: '4px' }}>
                ACTIVE WATCH
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                Early warning scans retracements
              </div>
            </div>
          </div>

          {/* Live Positions Table */}
          <div className="card" style={{ padding: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <span style={{ fontWeight: 800, fontSize: '14px' }}>Open Fleet Orders</span>
              <span className="badge badge-gray">{positions.length} Orders</span>
            </div>

            <div className="table-responsive">
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-dim)' }}>
                    <th style={{ padding: '10px' }}>TICKET</th>
                    <th style={{ padding: '10px' }}>ACCOUNT</th>
                    <th style={{ padding: '10px' }}>SYMBOL</th>
                    <th style={{ padding: '10px' }}>TYPE</th>
                    <th style={{ padding: '10px' }}>LOTS</th>
                    <th style={{ padding: '10px' }}>OPEN PRICE</th>
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
                        <div style={{ fontWeight: 600 }}>No live trades currently open on connected accounts.</div>
                        <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '2px' }}>
                          When algorithmic signals are approved or EA executes on your fleet, active positions will appear here with live retracement warnings.
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
                            <span className={`badge ${p.type === 'BUY' ? 'badge-green' : 'badge-red'}`}>
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
                            <span className="badge badge-gold">Guarded</span>
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
      {/* TAB 3: ACCOUNT FLEET ($20 USD MINIMUM INITIAL BALANCE)                    */}
      {/* ========================================================================= */}
      {activeTab === 'ACCOUNTS' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Header & Add Account CTA */}
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
                All mock demo accounts purged. Connect real trading accounts with minimum $20.00 USD balance.
              </p>
            </div>

            <button className="btn btn-primary" onClick={() => setShowAddAccountModal(true)}>
              <PlusCircle size={15} /> Add MT5 Trading Account ($20 Min)
            </button>
          </div>

          {/* Accounts Grid */}
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
                  No Old Accounts Found (Clean Purge Complete)
                </div>
                <div style={{ fontSize: '12px', marginTop: '4px', maxWidth: '480px', margin: '6px auto 16px' }}>
                  You are ready to connect your real trading accounts. The bot will manage them locally with independent MT5 terminals.
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
                      Min Req: $20.00 USD (Verified)
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
      {/* TAB 4: RISK & LOT SIZE CALCULATOR                                        */}
      {/* ========================================================================= */}
      {activeTab === 'CALCULATOR' && (
        <div className="card" style={{ border: '1px solid var(--border-gold)', background: 'rgba(18, 22, 33, 0.85)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontSize: '20px' }}>⚖️</span>
              <span style={{ fontWeight: 800, fontSize: '16px' }}>Prop Firm & Personal Account Lot Size Calculator</span>
            </div>
            <span className="badge badge-gold" style={{ fontSize: '11px' }}>Pair: {calcSymbol}</span>
          </div>

          {/* Account Presets */}
          <div style={{ marginTop: '14px', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 700, textTransform: 'uppercase' }}>
              Account Preset:
            </span>
            {[
              { label: '$20 (Minimum Micro)', val: 20, key: 'Micro20' },
              { label: '$50 (Cent/Starter)', val: 50, key: 'Starter50' },
              { label: '$100 (Standard Mini)', val: 100, key: 'Exness100' },
              { label: '$1,000 (BrightFunded)', val: 1000, key: 'BrightFunded' },
              { label: '$5,000 (Prop Challenge)', val: 5000, key: 'Prop5K' },
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

          {/* Calculator Inputs & Dynamic Results */}
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

            {/* Computed Results Card */}
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
                  style={{
                    width: '100%',
                    marginTop: '4px',
                    padding: '9px 12px',
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '8px',
                    color: '#fff',
                    fontSize: '13px',
                  }}
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
                    style={{
                      width: '100%',
                      marginTop: '4px',
                      padding: '9px 12px',
                      background: 'rgba(255,255,255,0.04)',
                      border: '1px solid var(--border-gold)',
                      borderRadius: '8px',
                      color: 'var(--gold-primary)',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '14px',
                      fontWeight: 700,
                    }}
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
                    style={{
                      width: '100%',
                      marginTop: '4px',
                      padding: '9px 12px',
                      background: '#161a26',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '8px',
                      color: '#fff',
                      fontSize: '13px',
                    }}
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
                    style={{
                      width: '100%',
                      marginTop: '4px',
                      padding: '9px 12px',
                      background: 'rgba(255,255,255,0.04)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '8px',
                      color: '#fff',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '13px',
                    }}
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
                    style={{
                      width: '100%',
                      marginTop: '4px',
                      padding: '9px 12px',
                      background: 'rgba(255,255,255,0.04)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '8px',
                      color: '#fff',
                      fontSize: '13px',
                    }}
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
                  style={{
                    width: '100%',
                    marginTop: '4px',
                    padding: '9px 12px',
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '8px',
                    color: '#fff',
                    fontSize: '13px',
                  }}
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
                  style={{
                    width: '100%',
                    marginTop: '4px',
                    padding: '9px 12px',
                    background: '#161a26',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '8px',
                    color: '#fff',
                    fontSize: '13px',
                  }}
                >
                  <option value="AUTOMATED_EA">Automated EA (Terminal Copier / Executor)</option>
                  <option value="SIGNAL_ONLY_MANUAL">Signal Only (Manual Execution Notification)</option>
                </select>
              </div>

              <div style={{ display: 'flex', gap: '10px', marginTop: '14px' }}>
                <button
                  type="button"
                  className="btn"
                  style={{ flex: 1 }}
                  onClick={() => setShowAddAccountModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  style={{ flex: 2 }}
                  disabled={addingAccount}
                >
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
