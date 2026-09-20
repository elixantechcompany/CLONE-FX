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

const NAV_ITEMS = [
  { id: 'signals',   label: 'Signals',   icon: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
  ) },
  { id: 'ea',        label: 'Bot',       icon: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
  ) },
  { id: 'journal',   label: 'Journal',   icon: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
  ) },
  { id: 'positions', label: 'Positions', icon: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
  ) },
  { id: 'accounts',  label: 'Accounts',  icon: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>
  ) },
] as const;

export const Navbar: React.FC<NavbarProps> = ({
  activeTab, setActiveTab, eaRunning, onToggleEA, balance, equity, accountName = 'GOLD CLONE', isOnline,
}) => {
  const profitLoss = equity - balance;
  const isProfit = profitLoss >= 0;

  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 50,
      background: 'rgba(6,8,16,0.97)',
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      borderBottom: '1px solid rgba(255,255,255,0.055)',
      padding: '0 20px',
      fontFamily: 'var(--font-ui)',
    }}>
      <div style={{ maxWidth: 1280, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 12, height: 52 }}>

        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'linear-gradient(135deg,#c99a12 0%,#7a5c08 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 12, fontWeight: 800, color: '#000', letterSpacing: '0.02em',
            boxShadow: '0 0 14px rgba(201,154,18,0.3)',
            flexShrink: 0,
          }}>GC</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 13, fontWeight: 800, color: '#e0b84a', letterSpacing: '0.02em' }}>GOLD CLONE</span>
              <span style={{
                fontSize: 9, fontWeight: 700, padding: '1px 5px', borderRadius: 3,
                background: 'rgba(56,189,248,0.1)', color: '#38bdf8',
                border: '1px solid rgba(56,189,248,0.2)', letterSpacing: '0.06em', fontFamily: 'var(--font-mono)',
              }}>v2.4</span>
            </div>
            <span style={{ fontSize: 10, color: 'var(--text-dim)', display: 'none' }} className="sm-show">Gold & BTC Signal Engine</span>
          </div>
        </div>

        {/* Desktop nav — centred */}
        <nav style={{ display: 'flex', alignItems: 'center', gap: 2, background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: 11, padding: 3, flex: 1, justifyContent: 'center', maxWidth: 480, margin: '0 auto' }}
          className="hide-mobile">
          {NAV_ITEMS.map(item => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id as any)}
              style={{
                display: 'flex', alignItems: 'center', gap: 5,
                padding: '6px 12px', borderRadius: 8,
                border: activeTab === item.id ? '1px solid rgba(201,154,18,0.4)' : '1px solid transparent',
                background: activeTab === item.id ? 'linear-gradient(135deg,#c99a12 0%,#9a7610 100%)' : 'transparent',
                color: activeTab === item.id ? '#000' : 'var(--text-dim)',
                fontFamily: 'var(--font-ui)', fontSize: 12, fontWeight: activeTab === item.id ? 700 : 600,
                cursor: 'pointer', whiteSpace: 'nowrap', transition: 'all 0.14s ease',
                boxShadow: activeTab === item.id ? '0 2px 10px rgba(201,154,18,0.25)' : 'none',
              }}
            >
              {item.icon}
              <span>{item.label}</span>
              {item.id === 'ea' && (
                <span style={{
                  fontSize: 9, padding: '1px 4px', borderRadius: 3, fontFamily: 'var(--font-mono)', fontWeight: 700,
                  background: eaRunning ? 'rgba(0,200,150,0.15)' : 'rgba(232,68,90,0.15)',
                  color: eaRunning ? '#00c896' : '#e8445a',
                  border: eaRunning ? '1px solid rgba(0,200,150,0.25)' : '1px solid rgba(232,68,90,0.25)',
                }}>
                  {eaRunning ? 'ON' : 'OFF'}
                </span>
              )}
            </button>
          ))}
        </nav>

        {/* Right side — account + status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, marginLeft: 'auto' }}>

          {/* Account chip */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 9, padding: '5px 10px',
          }} className="hide-mobile">
            <div style={{
              width: 6, height: 6, borderRadius: '50%',
              background: isOnline ? '#00c896' : '#e8445a',
              boxShadow: isOnline ? '0 0 6px #00c896' : '0 0 6px #e8445a',
            }} />
            <div>
              <div style={{ fontSize: 10, color: 'var(--text-dim)', fontWeight: 600, letterSpacing: '0.03em' }}>{accountName}</div>
              <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 5 }}>
                ${balance.toFixed(2)}
                <span style={{ fontSize: 10, color: isProfit ? '#00c896' : '#e8445a', fontWeight: 600 }}>
                  {isProfit ? '+' : ''}{profitLoss.toFixed(2)}
                </span>
              </div>
            </div>
          </div>

          {/* EA pill — honest status */}
          <button
            onClick={onToggleEA}
            title={eaRunning ? 'Bot is watching for signals (runs on your laptop)' : 'Bot is stopped'}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 11px', borderRadius: 8,
              border: eaRunning ? '1px solid rgba(0,200,150,0.25)' : '1px solid rgba(232,68,90,0.25)',
              background: eaRunning ? 'rgba(0,200,150,0.09)' : 'rgba(232,68,90,0.09)',
              color: eaRunning ? '#00c896' : '#e8445a',
              fontFamily: 'var(--font-ui)', fontSize: 11, fontWeight: 700,
              cursor: 'pointer', transition: 'all 0.14s', letterSpacing: '0.03em',
            }}
          >
            <span style={{
              width: 6, height: 6, borderRadius: '50%',
              background: eaRunning ? '#00c896' : '#e8445a',
              display: 'inline-block',
              animation: eaRunning ? 'pulse 2s ease-in-out infinite' : 'none',
            }} />
            <span className="hide-xs">{eaRunning ? 'BOT WATCHING' : 'BOT STOPPED'}</span>
            <span className="show-xs">{eaRunning ? 'ON' : 'OFF'}</span>
          </button>
        </div>
      </div>

      <style>{`
        @media(max-width:1024px){ .hide-mobile{ display:none !important; } }
        @media(max-width:480px){ .hide-xs{ display:none !important; } .show-xs{ display:inline !important; } }
        .show-xs{ display:none; }
      `}</style>
    </header>
  );
};
