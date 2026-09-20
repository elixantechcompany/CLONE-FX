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
  killzoneInfo?: { is_killzone: boolean; session_name: string; trading_allowed: boolean; utc_time: string };
  adrInfo?: { adr_used_pct: number; range_pts: number; typical_adr: number; is_exhausted: boolean; warning: string };
  onLogToJournal: (signal: ConfluenceSignal) => void;
  onRefresh: () => void;
  isScanning: boolean;
}

const S: Record<string, React.CSSProperties> = {
  row:   { display: 'flex', alignItems: 'center' },
  col:   { display: 'flex', flexDirection: 'column' },
  card:  { background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 16, padding: 16, transition: 'border-color .18s' },
};

function Label({ children }: { children: React.ReactNode }) {
  return <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-dim)', fontFamily: 'var(--font-ui)' }}>{children}</span>;
}

function Mono({ children, size = 14, color = 'var(--text-primary)', bold = true }: { children: React.ReactNode; size?: number; color?: string; bold?: boolean }) {
  return <span style={{ fontFamily: 'var(--font-mono)', fontSize: size, fontWeight: bold ? 700 : 400, color }}>{children}</span>;
}

export const SignalsView: React.FC<SignalsViewProps> = ({
  selectedSymbol, setSelectedSymbol, activeSignals, formingSetups,
  marketSchedules, currentPrice, macroBias, killzoneInfo, adrInfo,
  onLogToJournal, onRefresh, isScanning,
}) => {
  const [copied, setCopied] = useState(false);
  const [calcPips, setCalcPips] = useState(30);
  const [calcLots, setCalcLots] = useState(0.01);

  const schedule  = marketSchedules[selectedSymbol];
  const isOpen    = schedule ? schedule.is_open : true;
  const top       = activeSignals[0] ?? null;
  const isBuy     = top ? (top.direction || '').toUpperCase().includes('BUY') : true;
  const scoreNum  = top?.scoreNumeric ?? (top ? 3 : 0);
  const rr        = top?.riskReward ?? 2.5;
  const rrClean   = Math.min(Math.max(rr, 0.5), 10); // clamp to sane range
  const adrPct    = adrInfo?.adr_used_pct ?? 45;
  const isExhausted = adrPct > 80;
  const profit$   = selectedSymbol === 'XAUUSD' ? calcPips * calcLots * 10 : (calcPips / 100) * calcLots * 100;

  const handleCopy = () => {
    if (!top) return;
    const tp2 = top.takeProfit2 || top.takeProfit1 * 1.5;
    navigator.clipboard.writeText(
      `DIRECTION: ${isBuy ? 'BUY (LONG)' : 'SELL (SHORT)'}\nSYMBOL: ${top.symbol}\nENTRY: ${top.entryPrice.toFixed(2)}\nSTOP LOSS: ${top.stopLoss.toFixed(2)}\nTAKE PROFIT 1: ${top.takeProfit1.toFixed(2)}\nTAKE PROFIT 2: ${tp2.toFixed(2)}\nRISK/REWARD: 1:${rrClean.toFixed(2)}`
    );
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // ── plain-English helpers ──────────────────────────
  const sessionPlain = () => {
    const s = killzoneInfo?.session_name || '';
    if (s.includes('London')) return 'London open — best time to trade';
    if (s.includes('New York') || s.includes('NY')) return 'New York open — high activity';
    if (s.includes('Asian')) return 'Asian session — usually slow';
    if (s.includes('Overlap')) return 'London/NY overlap — peak volume';
    return 'Active session';
  };

  const adrPlain = () => {
    if (adrPct > 80) return 'Gold has already moved a lot today — risk of reversal is higher.';
    if (adrPct > 60) return 'More than half of today\'s typical range is used. Be careful with entries.';
    return 'Plenty of room to move today. Conditions look clean.';
  };

  const biasBrief = () => {
    const b = macroBias.toUpperCase();
    if (b.includes('ACCUM')) return 'Smart money is quietly buying — daily trend is up.';
    if (b.includes('DIST'))  return 'Smart money is quietly selling — daily trend is down.';
    if (b.includes('BULL'))  return 'Daily trend pointing up.';
    if (b.includes('BEAR'))  return 'Daily trend pointing down.';
    return macroBias;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, paddingBottom: 80, fontFamily: 'var(--font-ui)' }}>

      {/* ── Zone 1: Status bar ─────────────────── */}
      <div style={{ ...S.card, display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 10, padding: '12px 16px' }}>
        {/* Symbol switcher */}
        <div style={{ ...S.row, gap: 6 }}>
          {(['XAUUSD', 'BTCUSD'] as const).map(sym => {
            const active = selectedSymbol === sym;
            const isSymOpen = marketSchedules[sym]?.is_open ?? true;
            return (
              <button key={sym} onClick={() => setSelectedSymbol(sym)} style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '7px 13px', borderRadius: 9, cursor: 'pointer',
                border: active ? (sym === 'XAUUSD' ? '1px solid rgba(201,154,18,0.35)' : '1px solid rgba(249,115,22,0.35)') : '1px solid var(--border)',
                background: active ? (sym === 'XAUUSD' ? 'rgba(201,154,18,0.1)' : 'rgba(249,115,22,0.1)') : 'transparent',
                color: active ? (sym === 'XAUUSD' ? '#e0b84a' : '#fb923c') : 'var(--text-dim)',
                fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 700, transition: 'all .14s',
              }}>
                <span style={{ fontSize: 14 }}>{sym === 'XAUUSD' ? '🥇' : '₿'}</span>
                <span>{sym}</span>
                <span style={{
                  fontSize: 9, padding: '1px 5px', borderRadius: 3, fontFamily: 'var(--font-mono)', fontWeight: 700,
                  background: isSymOpen ? 'rgba(0,200,150,0.12)' : 'rgba(232,68,90,0.12)',
                  color: isSymOpen ? '#00c896' : '#e8445a',
                  border: isSymOpen ? '1px solid rgba(0,200,150,0.2)' : '1px solid rgba(232,68,90,0.2)',
                }}>{isSymOpen ? 'OPEN' : 'CLOSED'}</span>
              </button>
            );
          })}
        </div>

        {/* Live price + scan button */}
        <div style={{ ...S.row, gap: 12 }}>
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-dim)', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase' }}>Live Price</div>
            <Mono size={18} color="#e6eaf4">${currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</Mono>
          </div>
          <button onClick={onRefresh} disabled={isScanning} style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '7px 13px', borderRadius: 9,
            border: '1px solid rgba(56,189,248,0.22)', background: 'rgba(56,189,248,0.07)',
            color: '#38bdf8', fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 700,
            cursor: isScanning ? 'not-allowed' : 'pointer', opacity: isScanning ? 0.6 : 1, transition: 'all .14s',
          }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
              style={{ animation: isScanning ? 'spin 1s linear infinite' : 'none' }}>
              <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
            {isScanning ? 'Scanning...' : 'Scan Now'}
          </button>
        </div>
      </div>

      {/* Market closed banner */}
      {!isOpen && schedule && (
        <div style={{
          background: 'rgba(245,158,11,0.07)', border: '1px solid rgba(245,158,11,0.2)',
          borderRadius: 12, padding: '12px 16px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap',
        }}>
          <div style={{ ...S.row, gap: 10 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#f59e0b' }}>Market closed — weekend</div>
              <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 2 }}>Signals shown are based on Friday's close. Auto-trading resumes Sunday 22:00 UTC.</div>
            </div>
          </div>
          <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#f59e0b', padding: '3px 8px', borderRadius: 5, background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.2)', whiteSpace: 'nowrap' }}>REOPENS SUN 22:00 UTC</span>
        </div>
      )}

      {/* ── Zone 2: Active signal card ─────────── */}
      {top ? (
        <div style={{
          ...S.card,
          borderColor: isBuy ? 'rgba(0,200,150,0.3)' : 'rgba(232,68,90,0.3)',
          boxShadow: isBuy ? '0 0 30px rgba(0,200,150,0.08)' : '0 0 30px rgba(232,68,90,0.08)',
          animation: isBuy ? 'glowLong 3s ease-in-out infinite' : 'glowShort 3s ease-in-out infinite',
        }}>
          {/* Header row */}
          <div style={{ ...S.row, justifyContent: 'space-between', marginBottom: 14, flexWrap: 'wrap', gap: 8 }}>
            <div style={{ ...S.row, gap: 8 }}>
              {/* BUY/SELL pill — unmissable */}
              <div style={{
                padding: '6px 14px', borderRadius: 7, fontWeight: 800, fontSize: 13, letterSpacing: '0.06em',
                background: isBuy ? '#00c896' : '#e8445a', color: '#000',
                fontFamily: 'var(--font-ui)',
              }}>
                {isBuy ? '▲ BUY' : '▼ SELL'}
              </div>
              <div style={{ fontWeight: 800, fontSize: 15, color: 'var(--text-primary)' }}>{top.symbol}</div>
              {/* Confluence dots */}
              <div style={{ ...S.row, gap: 4, padding: '5px 10px', borderRadius: 7, background: 'rgba(201,154,18,0.08)', border: '1px solid rgba(201,154,18,0.18)' }}>
                {[1,2,3].map(i => (
                  <span key={i} style={{
                    width: 6, height: 6, borderRadius: '50%', display: 'inline-block',
                    background: i <= scoreNum ? '#e0b84a' : 'rgba(255,255,255,0.07)',
                    boxShadow: i <= scoreNum ? '0 0 4px rgba(201,154,18,0.5)' : 'none',
                  }}/>
                ))}
                <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#e0b84a', marginLeft: 4 }}>{scoreNum}/3 checks</span>
              </div>
            </div>
            {/* R:R badge */}
            <div style={{
              padding: '5px 10px', borderRadius: 7,
              background: 'rgba(56,189,248,0.08)', border: '1px solid rgba(56,189,248,0.18)',
              fontSize: 11, fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#38bdf8',
            }}>
              Risk/Reward 1:{rrClean.toFixed(2)}
            </div>
          </div>

          {/* Price levels */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, padding: '12px 14px', borderRadius: 10, background: 'rgba(2,3,5,0.5)', border: '1px solid var(--border)', marginBottom: 12 }}>
            {[
              { label: 'Entry',        value: top.entryPrice?.toFixed(2),               color: 'var(--text-primary)' },
              { label: 'Stop Loss',    value: top.stopLoss?.toFixed(2),                 color: '#e8445a' },
              { label: 'Target 1',     value: top.takeProfit1?.toFixed(2),              color: '#00c896' },
              { label: 'Target 2',     value: (top.takeProfit2||top.takeProfit1*1.5)?.toFixed(2), color: '#38bdf8' },
            ].map(({ label, value, color }) => (
              <div key={label}>
                <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-dim)', marginBottom: 4 }}>{label}</div>
                <Mono size={16} color={color}>{value}</Mono>
              </div>
            ))}
          </div>

          {/* Plain-English reason */}
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 14, padding: '10px 12px', borderRadius: 8, background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)' }}>
            {(top as any).reason || top.setup_summary || 'Daily trend is bullish. The 4-hour chart swept below a key low (took out stop losses). Price then reclaimed that level on the 1-hour — this is the entry signal.'}
          </div>

          {/* Actions */}
          <div style={{ ...S.row, gap: 8 }}>
            <button onClick={handleCopy} style={{
              flex: 1, padding: '9px 0', borderRadius: 9, border: '1px solid var(--border)',
              background: 'rgba(255,255,255,0.03)', color: 'var(--text-primary)',
              fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 600, cursor: 'pointer', transition: 'all .14s',
            }}>
              {copied ? '✓ Copied to clipboard' : 'Copy order details'}
            </button>
            <button onClick={() => onLogToJournal(top)} style={{
              flex: 1, padding: '9px 0', borderRadius: 9,
              border: '1px solid rgba(201,154,18,0.4)',
              background: 'linear-gradient(135deg,#c99a12 0%,#9a7610 100%)',
              color: '#000', fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 700,
              cursor: 'pointer', transition: 'all .14s',
              boxShadow: '0 2px 10px rgba(201,154,18,0.2)',
            }}>
              Save to Journal
            </button>
          </div>

          {activeSignals.length > 1 && (
            <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border)', textAlign: 'center', fontSize: 11, color: 'var(--text-dim)' }}>
              +{activeSignals.length - 1} more signal{activeSignals.length > 2 ? 's' : ''} confirmed — see breakdown below
            </div>
          )}
        </div>
      ) : (
        /* No signal state */
        <div style={{ ...S.card, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 180, gap: 12, textAlign: 'center' }}>
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--text-dim)" strokeWidth="1.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 4 }}>No trade signal right now</div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', maxWidth: 300, lineHeight: 1.6 }}>
              Waiting for all 3 conditions to line up: daily trend, 4-hour liquidity sweep, and 1-hour entry. Only fires when everything agrees.
            </div>
          </div>
          <button onClick={onRefresh} disabled={isScanning} style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', borderRadius: 9,
            border: '1px solid rgba(56,189,248,0.22)', background: 'rgba(56,189,248,0.07)',
            color: '#38bdf8', fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: 700,
            cursor: isScanning ? 'not-allowed' : 'pointer', opacity: isScanning ? 0.6 : 1,
          }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
              style={{ animation: isScanning ? 'spin 1s linear infinite' : 'none' }}>
              <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
            {isScanning ? 'Scanning...' : 'Check now'}
          </button>
        </div>
      )}

      {/* ── Zone 3: Confluence breakdown ───────── */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <div style={{ flex: 1, height: 1, background: 'var(--border)' }}/>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-micro)' }}>3-Step Signal Breakdown</span>
          <div style={{ flex: 1, height: 1, background: 'var(--border)' }}/>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(200px,1fr))', gap: 10 }}>
          {/* Step 1 */}
          <div style={S.card}>
            <div style={{ ...S.row, justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-dim)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>Step 1 — Daily Trend</span>
              <span style={{ fontSize: 9, fontFamily: 'var(--font-mono)', fontWeight: 700, padding: '1px 6px', borderRadius: 3, background: top ? 'rgba(0,200,150,0.1)' : 'rgba(255,255,255,0.05)', color: top ? '#00c896' : 'var(--text-dim)', border: top ? '1px solid rgba(0,200,150,0.2)' : '1px solid var(--border)' }}>
                {top ? 'ALIGNED' : 'CHECKING'}
              </span>
            </div>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#e0b84a', marginBottom: 6 }}>
              {macroBias.split('(')[0].trim()}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.55 }}>{biasBrief()}</div>
          </div>

          {/* Step 2 */}
          <div style={S.card}>
            <div style={{ ...S.row, justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-dim)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>Step 2 — Session Timing</span>
              <span style={{ fontSize: 9, fontFamily: 'var(--font-mono)', fontWeight: 700, padding: '1px 6px', borderRadius: 3, background: killzoneInfo?.is_killzone ? 'rgba(56,189,248,0.1)' : 'rgba(255,255,255,0.04)', color: killzoneInfo?.is_killzone ? '#38bdf8' : 'var(--text-dim)', border: killzoneInfo?.is_killzone ? '1px solid rgba(56,189,248,0.2)' : '1px solid var(--border)' }}>
                {killzoneInfo?.utc_time || 'LIVE'}
              </span>
            </div>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#38bdf8', marginBottom: 6 }}>
              {sessionPlain().split('—')[0].trim()}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.55 }}>
              {killzoneInfo?.trading_allowed
                ? 'This is a high-activity window — big banks are executing orders. Good time to trade.'
                : 'Low-activity window right now. Bot will wait for a better time before executing.'}
            </div>
          </div>

          {/* Step 3 */}
          <div style={S.card}>
            <div style={{ ...S.row, justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-dim)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>Step 3 — Daily Range</span>
              <span style={{ fontSize: 9, fontFamily: 'var(--font-mono)', fontWeight: 700, padding: '1px 6px', borderRadius: 3, background: isExhausted ? 'rgba(232,68,90,0.1)' : 'rgba(245,158,11,0.1)', color: isExhausted ? '#e8445a' : '#f59e0b', border: isExhausted ? '1px solid rgba(232,68,90,0.2)' : '1px solid rgba(245,158,11,0.2)' }}>
                {adrPct}% USED
              </span>
            </div>
            <div style={{ ...S.row, gap: 6, marginBottom: 8 }}>
              <div style={{ flex: 1, height: 3, background: 'rgba(255,255,255,0.06)', borderRadius: 2, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${Math.min(adrPct,100)}%`, borderRadius: 2, background: isExhausted ? '#e8445a' : 'linear-gradient(90deg,#c99a12,#e0b84a)', transition: 'width .4s' }}/>
              </div>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.55 }}>{adrPlain()}</div>
          </div>
        </div>

        {/* Forming setups */}
        {formingSetups.length > 0 && (
          <div style={{ ...S.card, marginTop: 10, borderColor: 'rgba(245,158,11,0.15)' }}>
            <div style={{ ...S.row, gap: 8, marginBottom: 10 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: '#f59e0b', letterSpacing: '0.07em', textTransform: 'uppercase' }}>Setups forming ({formingSetups.length})</span>
              <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>— not ready to trade yet</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {formingSetups.slice(0,3).map((s,i) => (
                <div key={s.id||i} style={{ ...S.row, justifyContent: 'space-between', fontSize: 11, padding: '7px 10px', borderRadius: 8, background: 'rgba(2,3,5,0.5)', border: '1px solid var(--border)' }}>
                  <div style={{ ...S.row, gap: 6 }}>
                    <span style={{ fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 3, background: s.direction.includes('BUY') ? 'rgba(0,200,150,0.1)' : 'rgba(232,68,90,0.1)', color: s.direction.includes('BUY') ? '#00c896' : '#e8445a', border: s.direction.includes('BUY') ? '1px solid rgba(0,200,150,0.2)' : '1px solid rgba(232,68,90,0.2)', fontFamily: 'var(--font-mono)' }}>
                      {s.direction.includes('BUY') ? 'BUY' : 'SELL'}
                    </span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--text-secondary)' }}>{s.symbol}</span>
                  </div>
                  <span style={{ color: 'var(--text-dim)', fontSize: 10 }}>{s.setup_summary?.slice(0,45) || 'Watching for confirmation...'}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Profit calculator ───────────────────── */}
      <div style={{ ...S.card }}>
        <div style={{ ...S.row, gap: 10, marginBottom: 14 }}>
          <div style={{ width: 36, height: 36, borderRadius: 9, background: 'rgba(0,200,150,0.1)', border: '1px solid rgba(0,200,150,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#00c896" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>Profit Calculator</div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>See how much you'd make per trade before placing it.</div>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
          <div style={{ ...S.card, padding: 12 }}>
            <div style={{ ...S.row, justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-dim)', letterSpacing: '0.05em', textTransform: 'uppercase' }}>Target (pips)</span>
              <Mono size={12} color="#e0b84a">{calcPips}</Mono>
            </div>
            <input type="range" min={10} max={150} step={5} value={calcPips} onChange={e => setCalcPips(+e.target.value)} style={{ width: '100%' }}/>
          </div>
          <div style={{ ...S.card, padding: 12 }}>
            <div style={{ ...S.row, justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-dim)', letterSpacing: '0.05em', textTransform: 'uppercase' }}>Lot size</span>
              <Mono size={12} color="#00c896">{calcLots.toFixed(2)}</Mono>
            </div>
            <input type="range" min={0.01} max={0.10} step={0.01} value={calcLots} onChange={e => setCalcLots(+e.target.value)} className="range-long" style={{ width: '100%' }}/>
          </div>
          <div style={{ background: 'rgba(0,200,150,0.07)', border: '1px solid rgba(0,200,150,0.18)', borderRadius: 12, padding: 12, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: '#00c896', letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: 4 }}>You'd profit</div>
            <Mono size={22} color="#00c896">+${profit$.toFixed(2)}</Mono>
            <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 3 }}>{calcLots.toFixed(2)} lot · {calcPips} pips</div>
          </div>
        </div>
      </div>
    </div>
  );
};
