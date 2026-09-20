'use client';

import React from 'react';

interface MobileBottomNavProps {
  activeTab: 'signals' | 'ea' | 'journal' | 'positions' | 'accounts';
  setActiveTab: (tab: 'signals' | 'ea' | 'journal' | 'positions' | 'accounts') => void;
  eaRunning: boolean;
  positionsCount: number;
}

const TABS = [
  {
    id: 'signals' as const, label: 'Signals',
    icon: <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>,
  },
  {
    id: 'ea' as const, label: 'Bot',
    icon: <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>,
  },
  {
    id: 'journal' as const, label: 'Journal',
    icon: <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>,
  },
  {
    id: 'positions' as const, label: 'Trades',
    icon: <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>,
  },
  {
    id: 'accounts' as const, label: 'Account',
    icon: <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>,
  },
];

export const MobileBottomNav: React.FC<MobileBottomNavProps> = ({
  activeTab, setActiveTab, eaRunning, positionsCount,
}) => {
  return (
    <nav style={{
      display: 'flex', position: 'fixed', bottom: 0, left: 0, right: 0,
      background: 'rgba(6,8,16,0.97)',
      backdropFilter: 'blur(24px)', WebkitBackdropFilter: 'blur(24px)',
      borderTop: '1px solid rgba(255,255,255,0.055)',
      padding: '6px 8px',
      paddingBottom: 'calc(6px + env(safe-area-inset-bottom))',
      justifyContent: 'space-around', alignItems: 'center',
      zIndex: 100, fontFamily: 'var(--font-ui)',
    }}>
      {TABS.map(tab => {
        const active = activeTab === tab.id;
        return (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3,
            background: 'none', border: 'none',
            color: active ? 'var(--gold-light)' : 'var(--text-dim)',
            fontSize: 9, fontWeight: 600, padding: '5px 10px', borderRadius: 9,
            cursor: 'pointer', transition: 'all .14s', minWidth: 48,
            letterSpacing: '0.04em', textTransform: 'uppercase', position: 'relative',
          }}>
            {/* EA badge */}
            {tab.id === 'ea' && (
              <span style={{
                position: 'absolute', top: 2, right: 8,
                width: 6, height: 6, borderRadius: '50%',
                background: eaRunning ? '#00c896' : '#e8445a',
                boxShadow: eaRunning ? '0 0 5px #00c896' : 'none',
              }}/>
            )}
            {/* Positions count badge */}
            {tab.id === 'positions' && positionsCount > 0 && (
              <span style={{
                position: 'absolute', top: 2, right: 6,
                fontSize: 8, fontWeight: 800, padding: '0 4px', borderRadius: 3,
                background: '#00c896', color: '#000', fontFamily: 'var(--font-mono)',
              }}>{positionsCount}</span>
            )}
            <span style={{ filter: active ? 'drop-shadow(0 0 4px rgba(201,154,18,0.5))' : 'none' }}>{tab.icon}</span>
            <span>{tab.label}</span>
            {active && <span style={{ width: 4, height: 4, borderRadius: '50%', background: 'var(--gold-light)', boxShadow: '0 0 5px rgba(201,154,18,0.6)' }}/>}
          </button>
        );
      })}
    </nav>
  );
};
