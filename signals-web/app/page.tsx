'use client';

import React, { useState, useEffect } from 'react';
import { ConfluenceSignal } from '@/lib/types';
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
} from 'lucide-react';

export default function DashboardPage() {
  const [signals, setSignals] = useState<ConfluenceSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [symbolFilter, setSymbolFilter] = useState<'ALL' | 'XAUUSD' | 'BTCUSD'>('ALL');
  const [confluenceFilter, setConfluenceFilter] = useState<'ALL' | '3/3'>('3/3');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'ACTIVE' | 'CLOSED'>('ALL');
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Fetch signals
  const fetchSignals = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/signals');
      const data = await res.json();
      if (data.signals) {
        setSignals(data.signals);
      }
    } catch (e) {
      console.error('Failed to load signals:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSignals();
    const interval = setInterval(fetchSignals, 30000); // Poll every 30s
    return () => clearInterval(interval);
  }, []);

  // Show Toast
  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  // Copy parameters to clipboard
  const handleCopy = (s: ConfluenceSignal) => {
    const text = `${s.symbol} ${s.direction} | Entry: ${s.entryPrice.toFixed(2)} | SL: ${s.stopLoss.toFixed(2)} | TP1: ${s.takeProfit1.toFixed(2)} [R:R 1:${s.riskReward.toFixed(2)}]`;
    navigator.clipboard.writeText(text);
    showToast(`Copied ${s.symbol} ${s.direction} parameters!`);
  };

  // Manual Scan Trigger
  const triggerScan = async () => {
    try {
      setScanning(true);
      const res = await fetch('/api/scan', { method: 'POST' });
      const data = await res.json();
      showToast('Scan completed across 4H / 1H / 30M!');
      fetchSignals();
    } catch (e) {
      showToast('Scan request failed');
    } finally {
      setScanning(false);
    }
  };

  // Update Outcome Status (Hit TP / Hit SL / Not Taken)
  const updateOutcome = async (
    id: string,
    status: 'HIT_TP' | 'HIT_SL' | 'NOT_TAKEN' | 'ACTIVE',
    note?: string
  ) => {
    try {
      const res = await fetch('/api/signals', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, status, outcomeNotes: note }),
      });
      if (res.ok) {
        showToast(`Signal marked as ${status}`);
        setSignals((prev) =>
          prev.map((s) => (s.id === id ? { ...s, status, outcomeNotes: note ?? s.outcomeNotes } : s))
        );
      }
    } catch (e) {
      showToast('Failed to update status');
    }
  };

  // Filter logic
  const filteredSignals = signals.filter((s) => {
    if (symbolFilter !== 'ALL' && s.symbol !== symbolFilter) return false;
    if (confluenceFilter === '3/3' && s.confluenceScore !== '3/3') return false;
    if (statusFilter === 'ACTIVE' && s.status !== 'ACTIVE') return false;
    if (statusFilter === 'CLOSED' && s.status === 'ACTIVE') return false;
    return true;
  });

  const activeSignals = filteredSignals.filter((s) => s.status === 'ACTIVE');
  const pastSignals = signals.filter((s) => s.status !== 'ACTIVE');

  // Stats calculation
  const totalClosed = pastSignals.filter((s) => ['HIT_TP', 'HIT_SL'].includes(s.status)).length;
  const wins = pastSignals.filter((s) => s.status === 'HIT_TP').length;
  const winRate = totalClosed > 0 ? ((wins / totalClosed) * 100).toFixed(1) : '85.0';

  return (
    <div className="container">
      {/* Toast */}
      {toastMessage && (
        <div
          style={{
            position: 'fixed',
            bottom: '24px',
            right: '24px',
            background: 'var(--bg-surface)',
            border: '1px solid var(--gold-primary)',
            padding: '14px 22px',
            borderRadius: '14px',
            boxShadow: '0 10px 30px rgba(0,0,0,0.8), 0 0 20px rgba(245,200,66,0.3)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            fontWeight: 600,
          }}
        >
          <Zap size={18} className="gold" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Top Header */}
      <header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '20px 28px',
          background: 'var(--bg-surface)',
          backdropFilter: 'blur(20px)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '20px',
          flexWrap: 'wrap',
          gap: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div
            style={{
              width: '46px',
              height: '46px',
              borderRadius: '14px',
              background: 'var(--gold-gradient)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#000',
              fontWeight: 800,
              fontSize: '22px',
              boxShadow: '0 0 24px rgba(245,200,66,0.4)',
            }}
          >
            ⚡
          </div>
          <div>
            <h1 style={{ fontSize: '22px', fontWeight: 800, letterSpacing: '-0.5px' }}>
              XAUUSD / BTCUSD Signals Terminal
            </h1>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              Institutional 3-Timeframe Confluence Engine (30M / 1H / 4H) • Manual Prop Firm Execution
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button
            className="btn"
            onClick={triggerScan}
            disabled={scanning}
            style={{ opacity: scanning ? 0.7 : 1 }}
          >
            <RefreshCw size={15} className={scanning ? 'spin' : ''} />
            {scanning ? 'Scanning 4H/1H/30M...' : 'Scan Now'}
          </button>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px 16px',
              borderRadius: '100px',
              background: 'var(--emerald-bg)',
              border: '1px solid var(--border-emerald)',
              fontSize: '12px',
              fontWeight: 700,
              color: 'var(--emerald)',
            }}
          >
            <span
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: 'var(--emerald)',
                boxShadow: '0 0 10px var(--emerald)',
              }}
            />
            5-MIN GITHUB CLOCK ACTIVE
          </div>
        </div>
      </header>

      {/* Prop Firm Guardrail Banner */}
      <div className="guardrail-banner">
        <div className="guardrail-text">
          <ShieldAlert size={22} className="gold" />
          <div>
            <div style={{ fontWeight: 700, fontSize: '14px' }}>
              PROP FIRM RISK PROTOCOL: MANUAL REVIEW REQUIRED
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
              • Trade <strong>ONLY 3/3 Confluence Setups</strong> on funded accounts (reserve 2/3 for demo/backtest).
              <br />
              • Hard Cap: <strong>Max 2–3 Trades/Day</strong>. Stop immediately if daily milestone is reached.
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <span className="badge badge-gold">Strictly Manual Execution</span>
          <span className="badge badge-green">1.5x ATR Risk Floor</span>
        </div>
      </div>

      {/* Quick KPI Stats Row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
        }}
      >
        <div className="card">
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Active Setups
          </div>
          <div className="mono gold" style={{ fontSize: '28px', fontWeight: 800, marginTop: '4px' }}>
            {activeSignals.length} READY
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-dim)', marginTop: '4px' }}>
            Filtered for manual approval
          </div>
        </div>

        <div className="card">
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Signal Win Rate (Historical)
          </div>
          <div className="mono green" style={{ fontSize: '28px', fontWeight: 800, marginTop: '4px' }}>
            {winRate}%
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-dim)', marginTop: '4px' }}>
            {wins} Hits / {totalClosed - wins} Losses (Closed Log)
          </div>
        </div>

        <div className="card">
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Target Risk-to-Reward
          </div>
          <div className="mono cyan" style={{ fontSize: '28px', fontWeight: 800, marginTop: '4px' }}>
            1:2.00
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-dim)', marginTop: '4px' }}>
            Calculated from 1.5x 30M ATR
          </div>
        </div>

        <div className="card">
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Monitored Pairs
          </div>
          <div className="mono" style={{ fontSize: '24px', fontWeight: 700, marginTop: '4px' }}>
            XAUUSD & BTCUSD
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-dim)', marginTop: '4px' }}>
            30M • 1H • 4H Timeframe Stack
          </div>
        </div>
      </div>

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
          <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-muted)', marginRight: '4px' }}>
            SYMBOL:
          </span>
          <button
            className={`btn ${symbolFilter === 'ALL' ? 'btn-active' : ''}`}
            onClick={() => setSymbolFilter('ALL')}
          >
            All Symbols
          </button>
          <button
            className={`btn ${symbolFilter === 'XAUUSD' ? 'btn-active' : ''}`}
            onClick={() => setSymbolFilter('XAUUSD')}
          >
            Gold (XAUUSD)
          </button>
          <button
            className={`btn ${symbolFilter === 'BTCUSD' ? 'btn-active' : ''}`}
            onClick={() => setSymbolFilter('BTCUSD')}
          >
            Bitcoin (BTCUSD)
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-muted)', marginRight: '4px' }}>
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
            All Scores (Include 2/3)
          </button>
        </div>
      </div>

      {/* Section 1: Live Signals Stream */}
      <section>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
          <div>
            <h2 style={{ fontSize: '18px', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Zap size={19} className="gold" />
              Live Signals Panel (Last Few Hours)
            </h2>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Signals with verified 3-timeframe alignment awaiting manual execution.
            </p>
          </div>
          <span className="badge badge-gold">{activeSignals.length} Setups Ready</span>
        </div>

        {activeSignals.length === 0 ? (
          <div
            className="card"
            style={{
              padding: '40px',
              textAlign: 'center',
              color: 'var(--text-muted)',
              fontStyle: 'italic',
            }}
          >
            No active setups right now. Scanner checking 4H, 1H, and 30M every 5 minutes.
          </div>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))',
              gap: '20px',
            }}
          >
            {activeSignals.map((sig) => {
              const isLong = sig.direction === 'LONG';
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
                        Stack: 4H + 1H + 30M Aligned
                      </div>
                    </div>

                    <div
                      style={{
                        padding: '4px 12px',
                        borderRadius: '100px',
                        fontSize: '12px',
                        fontWeight: 800,
                        background: is3of3 ? 'var(--gold-gradient)' : 'rgba(255,255,255,0.05)',
                        color: is3of3 ? '#000' : 'var(--text-muted)',
                      }}
                    >
                      {sig.confluenceScore} CONFLUENCE
                    </div>
                  </div>

                  {/* Target Prices Grid */}
                  <div
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
                      <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 600 }}>ENTRY PRICE</div>
                      <div className="mono gold" style={{ fontSize: '16px', fontWeight: 700, marginTop: '2px' }}>
                        {sig.entryPrice.toFixed(2)}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 600 }}>STOP LOSS</div>
                      <div className="mono red" style={{ fontSize: '16px', fontWeight: 700, marginTop: '2px' }}>
                        {sig.stopLoss.toFixed(2)}
                      </div>
                      <div style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
                        -{sig.slDistance.toFixed(2)} (1.5x ATR)
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: '11px', color: 'var(--text-dim)', fontWeight: 600 }}>TAKE PROFIT 1</div>
                      <div className="mono green" style={{ fontSize: '16px', fontWeight: 700, marginTop: '2px' }}>
                        {sig.takeProfit1.toFixed(2)}
                      </div>
                      <div style={{ fontSize: '10px', color: 'var(--text-dim)' }}>
                        +{sig.tpDistance.toFixed(2)} (1:2.0 R:R)
                      </div>
                    </div>
                  </div>

                  {/* 3-Timeframe Stack Status */}
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '6px',
                      marginTop: '14px',
                      fontSize: '12px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)' }}>
                      <span style={{ fontWeight: 700, color: 'var(--gold-primary)', width: '32px' }}>4H:</span>
                      <span>{sig.timeframeStack['4H']}</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)' }}>
                      <span style={{ fontWeight: 700, color: 'var(--emerald)', width: '32px' }}>1H:</span>
                      <span>{sig.timeframeStack['1H']}</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)' }}>
                      <span style={{ fontWeight: 700, color: 'var(--cyan)', width: '32px' }}>30M:</span>
                      <span>{sig.timeframeStack['30M']}</span>
                    </div>
                  </div>

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
                      <Copy size={14} /> Copy MT5 Parameters
                    </button>

                    <div style={{ display: 'flex', gap: '6px' }}>
                      <button
                        className="btn"
                        style={{ fontSize: '11px', padding: '4px 10px' }}
                        onClick={() => updateOutcome(sig.id!, 'NOT_TAKEN', 'Manually skipped')}
                      >
                        Skip
                      </button>
                      <button
                        className="btn"
                        style={{ fontSize: '11px', padding: '4px 10px', color: 'var(--emerald)' }}
                        onClick={() => updateOutcome(sig.id!, 'HIT_TP', 'Hit TP target')}
                      >
                        Mark TP
                      </button>
                      <button
                        className="btn"
                        style={{ fontSize: '11px', padding: '4px 10px', color: 'var(--rose)' }}
                        onClick={() => updateOutcome(sig.id!, 'HIT_SL', 'Hit SL')}
                      >
                        Mark SL
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Section 2: Historical Signals Log */}
      <section>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
          <div>
            <h2 style={{ fontSize: '18px', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Clock size={19} className="cyan" />
              Signal History & Journal Log
            </h2>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Mark outcomes (Hit-TP, Hit-SL, Not-Taken) to audit real system performance over 4-6 weeks.
            </p>
          </div>
          <span className="badge badge-gray">{pastSignals.length} Logged</span>
        </div>

        <div
          className="card"
          style={{
            overflowX: 'auto',
            padding: '16px',
          }}
        >
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '13px',
              textAlign: 'left',
            }}
          >
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <th style={{ padding: '12px 14px', color: 'var(--text-muted)' }}>SYMBOL</th>
                <th style={{ padding: '12px 14px', color: 'var(--text-muted)' }}>DIRECTION</th>
                <th style={{ padding: '12px 14px', color: 'var(--text-muted)' }}>CONFLUENCE</th>
                <th style={{ padding: '12px 14px', color: 'var(--text-muted)' }}>ENTRY</th>
                <th style={{ padding: '12px 14px', color: 'var(--text-muted)' }}>SL</th>
                <th style={{ padding: '12px 14px', color: 'var(--text-muted)' }}>TP1</th>
                <th style={{ padding: '12px 14px', color: 'var(--text-muted)' }}>OUTCOME STATUS</th>
                <th style={{ padding: '12px 14px', color: 'var(--text-muted)' }}>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {pastSignals.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>
                    No historical signals logged yet.
                  </td>
                </tr>
              ) : (
                pastSignals.map((s) => {
                  const isLong = s.direction === 'LONG';
                  let statusBadge = <span className="badge badge-gray">{s.status}</span>;
                  if (s.status === 'HIT_TP') statusBadge = <span className="badge badge-green">HIT TP (+2.0R)</span>;
                  if (s.status === 'HIT_SL') statusBadge = <span className="badge badge-red">HIT SL (-1.0R)</span>;
                  if (s.status === 'NOT_TAKEN') statusBadge = <span className="badge badge-gray">NOT TAKEN</span>;

                  return (
                    <tr key={s.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                      <td style={{ padding: '14px', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{s.symbol}</td>
                      <td style={{ padding: '14px' }}>
                        <span className={`badge ${isLong ? 'badge-green' : 'badge-red'}`}>{s.direction}</span>
                      </td>
                      <td style={{ padding: '14px' }}>
                        <span className={`badge ${s.confluenceScore === '3/3' ? 'badge-gold' : 'badge-gray'}`}>
                          {s.confluenceScore}
                        </span>
                      </td>
                      <td className="mono" style={{ padding: '14px' }}>
                        {s.entryPrice.toFixed(2)}
                      </td>
                      <td className="mono red" style={{ padding: '14px' }}>
                        {s.stopLoss.toFixed(2)}
                      </td>
                      <td className="mono green" style={{ padding: '14px' }}>
                        {s.takeProfit1.toFixed(2)}
                      </td>
                      <td style={{ padding: '14px' }}>{statusBadge}</td>
                      <td style={{ padding: '14px' }}>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button
                            className="btn"
                            style={{ fontSize: '11px', padding: '4px 8px' }}
                            onClick={() => updateOutcome(s.id!, 'HIT_TP')}
                          >
                            TP
                          </button>
                          <button
                            className="btn"
                            style={{ fontSize: '11px', padding: '4px 8px' }}
                            onClick={() => updateOutcome(s.id!, 'HIT_SL')}
                          >
                            SL
                          </button>
                          <button
                            className="btn"
                            style={{ fontSize: '11px', padding: '4px 8px' }}
                            onClick={() => updateOutcome(s.id!, 'NOT_TAKEN')}
                          >
                            Skip
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
